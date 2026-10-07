import { HttpException, HttpStatus, Injectable, Logger } from '@nestjs/common';
import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { CodexService } from '../codex/codex.service';
import { MrwActionRegistryService } from './mrw-action-registry.service';
import { MrwBackendClient } from './mrw-backend.client';
import { MrwEventBus } from './mrw-event-bus';
import type {
  MrwBindResult,
  MrwConfirmRequest,
  MrwConfirmResult,
  MrwDispatchResult,
  MrwDynamicToolCallParams,
  MrwPendingAction,
  MrwPreparedEnvironment,
  MrwSkillDescriptor,
  MrwTurnSkillInput,
  MrwRequestCredentials,
} from './mrw.types';

const TURN_INPUT_WAIT_MS = 30_000;

/**
 * Orchestrates the WebUI side of the macro host transport: prepares/binds
 * native threads, forwards dynamic tool calls to the backend, and turns a
 * user confirmation into a re-dispatched call plus the original RPC response.
 */
@Injectable()
export class MrwService {
  private readonly logger = new Logger(MrwService.name);
  private readonly preparedSkills = new Map<string, MrwSkillDescriptor[]>();
  private readonly threadSkills = new Map<string, MrwSkillDescriptor[]>();
  private readonly boundThreads = new Map<
    string,
    { turnId?: string; credentials?: MrwRequestCredentials }
  >();
  private readonly activeSkillRoots = new Set<string>();
  private readonly threadInputReadiness = new Map<
    string,
    {
      promise: Promise<void>;
      resolve: () => void;
      reject: (error: Error) => void;
    }
  >();
  private readonly confirmInFlight = new Map<
    string,
    Promise<MrwConfirmResult>
  >();

  constructor(
    private readonly backend: MrwBackendClient,
    private readonly registry: MrwActionRegistryService,
    private readonly codex: CodexService,
    private readonly events: MrwEventBus,
  ) {}

  prepareThread(projectKey: string): Promise<MrwPreparedEnvironment> {
    return this.backend.prepare(projectKey);
  }

  async bindThread(
    bindingId: string,
    threadId: string,
  ): Promise<MrwBindResult> {
    const result = await this.backend.bind(bindingId, threadId);
    this.threadSkills.set(threadId, this.preparedSkills.get(bindingId) ?? []);
    this.boundThreads.set(threadId, {});
    this.preparedSkills.delete(bindingId);
    return result;
  }

  /**
   * Projects the resolved skill bytes onto the host Codex app-server and verifies
   * the exact observed path and content digest. The backend descriptor may carry
   * a container absolute path, so the trusted MRW_SKILL_SOURCE_ROOT resolves the
   * real host location instead of substituting a guessed prefix.
   */
  async mountSkillEnvironment(prepared: MrwPreparedEnvironment): Promise<void> {
    const skills = prepared.skills ?? [];
    if (skills.length === 0) {
      this.preparedSkills.set(prepared.bindingId, []);
      return;
    }

    const sourceRoot = (process.env.MRW_SKILL_SOURCE_ROOT ?? '').trim();
    if (!sourceRoot) {
      throw new HttpException(
        'MRW skill source root is not configured',
        HttpStatus.SERVICE_UNAVAILABLE,
      );
    }

    const resolved = new Map<string, string>();
    for (const skill of skills) {
      resolved.set(
        skill.name,
        await this.resolveAndVerifySkill(sourceRoot, skill),
      );
    }

    const roots = new Set<string>();
    for (const realPath of resolved.values()) {
      roots.add(path.dirname(path.dirname(realPath)));
    }
    for (const root of roots) {
      this.activeSkillRoots.add(root);
    }
    await this.codex.request('skills/extraRoots/set', {
      extraRoots: [...this.activeSkillRoots],
    });
    const observed = (await this.codex.request('skills/list', {
      forceReload: true,
    })) as { data?: Array<{ skills?: Array<{ path?: string }> }> };
    const observedPaths = new Set(
      (observed.data ?? []).flatMap((entry) =>
        (entry.skills ?? []).map((skill) => skill.path ?? ''),
      ),
    );
    for (const [name, realPath] of resolved) {
      if (!observedPaths.has(realPath)) {
        throw new HttpException(
          `skill ${name} is not mounted at ${realPath}`,
          HttpStatus.NOT_FOUND,
        );
      }
    }
    this.preparedSkills.set(
      prepared.bindingId,
      skills.map((skill) => ({
        ...skill,
        path: resolved.get(skill.name) ?? skill.path,
      })),
    );
  }

  listPending(threadId: string): MrwPendingAction[] {
    return this.registry.listForThread(threadId);
  }

  isBound(threadId: string): boolean {
    return this.boundThreads.has(threadId);
  }

  /**
   * Distinguishes a plain native thread (404) from a lost MRW binding (409 or a
   * live backend binding that this process no longer tracks). Only `ordinary`
   * is safe to continue without the macro host transport.
   */
  async probeEnvironment(
    threadId: string,
  ): Promise<'ordinary' | 'rebind_required'> {
    try {
      await this.backend.environment(threadId);
      return 'rebind_required';
    } catch (error) {
      if (error instanceof HttpException) {
        if (error.getStatus() === HttpStatus.NOT_FOUND) return 'ordinary';
        if (error.getStatus() === HttpStatus.CONFLICT) return 'rebind_required';
      }
      throw error;
    }
  }

  /** Verifies a live binding is still fresh before a model turn is started. */
  async checkEnvironmentFresh(threadId: string): Promise<void> {
    const environment = await this.backend.environment(threadId);
    if (environment.environmentStale) {
      throw new HttpException(
        'MRW environment is stale; rebind required',
        HttpStatus.CONFLICT,
      );
    }
  }

  turnSkillInputs(threadId: string): MrwTurnSkillInput[] {
    return (this.threadSkills.get(threadId) ?? []).map((skill) => ({
      type: 'skill',
      name: skill.name,
      path: skill.path,
    }));
  }

  beginTurnInput(threadId: string): void {
    if (this.threadInputReadiness.has(threadId)) return;
    let resolve!: () => void;
    let reject!: (error: Error) => void;
    const promise = new Promise<void>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    // Observe the deferred rejection so a turn with no in-flight tool call does
    // not surface an unhandled rejection; waitForThreadInput still observes it.
    void promise.catch(() => undefined);
    this.threadInputReadiness.set(threadId, { promise, resolve, reject });
  }

  recordInput(
    threadId: string,
    turnId: string,
    content: string,
    credentials?: MrwRequestCredentials,
  ): Promise<unknown> {
    const readiness = this.threadInputReadiness.get(threadId);
    const binding = this.boundThreads.get(threadId);
    const promise = this.backend.recordInput(
      threadId,
      turnId,
      content,
      credentials,
    );
    void promise.then(
      () => {
        if (binding && this.boundThreads.get(threadId) === binding)
          this.boundThreads.set(threadId, { turnId, credentials });
        readiness?.resolve();
        this.threadInputReadiness.delete(threadId);
      },
      (error: unknown) => {
        readiness?.reject(
          error instanceof Error ? error : new Error(String(error)),
        );
        this.threadInputReadiness.delete(threadId);
      },
    );
    return promise;
  }

  releaseTurnInput(threadId: string): void {
    const readiness = this.threadInputReadiness.get(threadId);
    this.threadInputReadiness.delete(threadId);
    readiness?.resolve();
  }

  /**
   * Cancels every held-back action for a thread being deleted. Each pending RPC
   * is answered with an explicit failure so the app-server is never left blocked,
   * then the local record is cleared and a resolved event is emitted.
   */
  cancelForThread(threadId: string): void {
    this.boundThreads.delete(threadId);
    for (const record of this.registry.getForThread(threadId)) {
      this.respond(record.requestId, {
        success: false,
        contentItems: [
          { type: 'inputText', text: 'MRW action cancelled: thread deleted' },
        ],
      });
      this.registry.remove(record.actionId);
      this.events.emitActionResolved(record.actionId, record.threadId);
    }
  }

  cancelForTurn(threadId: string, turnId: string): void {
    const binding = this.boundThreads.get(threadId);
    if (binding && (!binding.turnId || binding.turnId === turnId))
      this.boundThreads.set(threadId, {});
    for (const record of this.registry.getForThread(threadId)) {
      if (record.turnId !== turnId) continue;
      this.respond(record.requestId, {
        success: false,
        contentItems: [
          { type: 'inputText', text: 'MRW action cancelled: turn ended' },
        ],
      });
      this.registry.remove(record.actionId);
      this.events.emitActionResolved(record.actionId, record.threadId);
    }
  }

  endTurn(threadId: string, turnId: string): Promise<unknown> {
    const binding = this.boundThreads.get(threadId);
    if (binding && (!binding.turnId || binding.turnId === turnId))
      this.boundThreads.set(threadId, {});
    return this.backend.endTurn(threadId, turnId);
  }

  /** Clears all pending actions after an app-server restart invalidates them. */
  expireAll(): void {
    for (const threadId of this.boundThreads.keys())
      this.boundThreads.set(threadId, {});
    for (const record of this.registry.getAll()) {
      this.respond(record.requestId, {
        success: false,
        contentItems: [
          {
            type: 'inputText',
            text: 'MRW action cancelled: app-server restarted',
          },
        ],
      });
      this.registry.remove(record.actionId);
      this.events.emitActionResolved(record.actionId, record.threadId);
    }
  }

  /**
   * Handles an app-server dynamic tool call. On first contact the backend asks
   * for approval: the RPC stays pending and a card is emitted. Otherwise the
   * app-server is answered directly with the backend's result.
   */
  async handleDynamicToolCall(
    requestId: string | number,
    params: MrwDynamicToolCallParams,
  ): Promise<void> {
    try {
      await this.waitForThreadInput(params.threadId);
    } catch {
      this.respond(requestId, {
        success: false,
        contentItems: [
          {
            type: 'inputText',
            text: 'MRW host input was not recorded for this turn',
          },
        ],
      });
      return;
    }

    let dispatch: MrwDispatchResult;
    try {
      dispatch = await this.backend.dispatch(
        params,
        this.turnCredentials(params.threadId, params.turnId),
      );
    } catch (error) {
      this.respond(requestId, {
        success: false,
        contentItems: [{ type: 'inputText', text: this.describe(error) }],
      });
      return;
    }

    const pending = dispatch.pendingAction;
    if (pending) {
      this.registry.record({
        ...pending,
        callId: params.callId,
        requestId,
        namespace: params.namespace,
        tool: params.tool,
      });
      this.events.emitActionRequired({ ...pending, callId: params.callId });
      return;
    }

    this.respond(requestId, dispatch);
  }

  /**
   * Confirms one held-back action, re-dispatches the exact original call, and
   * finally answers the app-server request that has been waiting since the card.
   */
  confirmAction(req: MrwConfirmRequest): Promise<MrwConfirmResult> {
    const existing = this.confirmInFlight.get(req.actionId);
    if (existing) return existing;
    const promise = this.doConfirmAction(req).finally(() => {
      if (this.confirmInFlight.get(req.actionId) === promise) {
        this.confirmInFlight.delete(req.actionId);
      }
    });
    this.confirmInFlight.set(req.actionId, promise);
    return promise;
  }

  private async doConfirmAction(
    req: MrwConfirmRequest,
  ): Promise<MrwConfirmResult> {
    const record = this.registry.get(req.actionId);
    if (!record) {
      throw new HttpException('MRW action not found', HttpStatus.NOT_FOUND);
    }
    if (record.threadId !== req.threadId || record.turnId !== req.turnId) {
      throw new HttpException(
        'MRW action no longer matches the active turn',
        HttpStatus.CONFLICT,
      );
    }

    await this.backend.confirm(req);
    const dispatch = await this.backend.dispatch(
      {
        threadId: record.threadId,
        turnId: record.turnId,
        callId: record.callId,
        namespace: record.namespace,
        tool: record.tool,
        arguments: record.arguments,
      },
      this.turnCredentials(record.threadId, record.turnId),
    );

    try {
      this.respond(record.requestId, dispatch);
    } catch (error) {
      // The app-server generation that issued the request is gone. Clear the
      // card and record the resolved state rather than leaving it ambiguous.
      this.logger.warn(
        `MRW action ${req.actionId} resolved but the pending RPC could not be answered: ${this.describe(error)}`,
      );
    }

    this.registry.remove(req.actionId);
    this.events.emitActionResolved(req.actionId, req.threadId);
    return {
      confirmed: true,
      actionId: req.actionId,
      approved: req.approved,
      threadId: req.threadId,
    };
  }

  private turnCredentials(
    threadId: string,
    turnId: string,
  ): MrwRequestCredentials | undefined {
    const binding = this.boundThreads.get(threadId);
    return binding?.turnId === turnId ? binding.credentials : undefined;
  }

  private respond(
    requestId: string | number,
    dispatch: MrwDispatchResult,
  ): void {
    try {
      this.codex.getClient().respondToServerRequest(requestId, {
        success: dispatch.success,
        contentItems: dispatch.contentItems ?? [],
      });
    } catch (error) {
      this.logger.warn(
        `MRW dynamic tool response could not be sent: ${this.describe(error)}`,
      );
    }
  }

  private describe(error: unknown): string {
    if (error instanceof Error) return error.message;
    return String(error);
  }

  private withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error('MRW host input recording timed out')),
        ms,
      );
      promise.then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        },
      );
    });
  }

  private async waitForThreadInput(threadId: string): Promise<void> {
    const readiness = this.threadInputReadiness.get(threadId);
    if (!readiness) return;
    await this.withTimeout(readiness.promise, TURN_INPUT_WAIT_MS);
  }

  private async resolveAndVerifySkill(
    sourceRoot: string,
    skill: MrwSkillDescriptor,
  ): Promise<string> {
    const relative = (skill.relativePath ?? '').trim();
    if (
      !relative ||
      path.isAbsolute(relative) ||
      relative.split(/[\\/]/).includes('..')
    ) {
      throw new HttpException(
        `skill ${skill.name} has an unsafe relative path`,
        HttpStatus.BAD_REQUEST,
      );
    }

    const root = path.resolve(sourceRoot);
    const candidate = path.resolve(root, relative);
    if (candidate !== root && !candidate.startsWith(root + path.sep)) {
      throw new HttpException(
        `skill ${skill.name} escapes the trusted source root`,
        HttpStatus.BAD_REQUEST,
      );
    }

    let realPath: string;
    try {
      realPath = await fs.realpath(candidate);
    } catch {
      throw new HttpException(
        `skill ${skill.name} is missing`,
        HttpStatus.NOT_FOUND,
      );
    }
    if (realPath !== root && !realPath.startsWith(root + path.sep)) {
      throw new HttpException(
        `skill ${skill.name} symlink escapes the trusted source root`,
        HttpStatus.BAD_REQUEST,
      );
    }

    if (skill.contentDigest) {
      const bytes = await fs.readFile(realPath);
      const digest = createHash('sha256').update(bytes).digest('hex');
      if (digest !== skill.contentDigest) {
        throw new HttpException(
          `skill ${skill.name} content digest mismatch`,
          HttpStatus.CONFLICT,
        );
      }
    }
    return realPath;
  }
}
