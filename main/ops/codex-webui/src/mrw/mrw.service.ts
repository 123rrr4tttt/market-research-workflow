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
  MrwTurnAdmission,
  MrwRequestCredentials,
  MrwTurnAttachment,
} from './mrw.types';

const TURN_INPUT_WAIT_MS = 30_000;
const SYSTEM_INSTRUCTIONS_BUDGET = 600;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * Orchestrates the WebUI side of the macro host transport: prepares/binds
 * native threads, forwards dynamic tool calls to the backend, and turns a
 * user confirmation into a re-dispatched call plus the original RPC response.
 */
@Injectable()
export class MrwService {
  private readonly logger = new Logger(MrwService.name);
  private readonly preparedSkills = new Map<string, MrwSkillDescriptor[]>();
  private readonly preparedTools = new Map<string, string>();
  private readonly preparedSystemInstructions = new Map<string, string>();
  private readonly threadSkills = new Map<string, MrwSkillDescriptor[]>();
  private readonly boundThreads = new Map<
    string,
    {
      tools: string;
      systemInstructions: string;
      admissionId?: string;
      turnId?: string;
      credentials?: MrwRequestCredentials;
    }
  >();
  private readonly preparingTurns = new Map<string, object>();
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

  private assertSystemInstructions(value: string): string {
    if (typeof value !== 'string' || value.trim().length === 0) {
      throw new HttpException(
        'MRW backend returned empty systemInstructions',
        HttpStatus.BAD_GATEWAY,
      );
    }
    if (value.length > SYSTEM_INSTRUCTIONS_BUDGET) {
      throw new HttpException(
        'MRW backend systemInstructions exceeds its wire budget',
        HttpStatus.BAD_GATEWAY,
      );
    }
    return value;
  }

  async prepareThread(projectKey: string): Promise<MrwPreparedEnvironment> {
    const prepared = await this.backend.prepare(projectKey);
    this.assertSystemInstructions(prepared.systemInstructions);
    this.preparedTools.set(
      prepared.bindingId,
      canonical(prepared.dynamicTools),
    );
    this.preparedSystemInstructions.set(
      prepared.bindingId,
      prepared.systemInstructions,
    );
    return prepared;
  }

  async bindThread(
    bindingId: string,
    threadId: string,
  ): Promise<MrwBindResult> {
    const result = await this.backend.bind(bindingId, threadId);
    const preparedInstructions = this.preparedSystemInstructions.get(bindingId);
    if (preparedInstructions === undefined) {
      throw new HttpException(
        'native_rebind_required: prepared system instructions are missing',
        HttpStatus.CONFLICT,
      );
    }
    const systemInstructions = this.assertSystemInstructions(
      result.systemInstructions,
    );
    if (systemInstructions !== preparedInstructions) {
      throw new HttpException(
        'native_rebind_required: system instructions changed during bind',
        HttpStatus.CONFLICT,
      );
    }
    this.threadSkills.set(threadId, this.preparedSkills.get(bindingId) ?? []);
    this.boundThreads.set(threadId, {
      tools:
        this.preparedTools.get(bindingId) ??
        canonical(result.dynamicTools ?? []),
      systemInstructions,
    });
    this.preparedSkills.delete(bindingId);
    this.preparedTools.delete(bindingId);
    this.preparedSystemInstructions.delete(bindingId);
    return result;
  }

  /**
   * Projects the resolved skill bytes onto the host Codex app-server and verifies
   * the exact observed path and content digest. The backend descriptor may carry
   * a container absolute path, so the trusted MRW_SKILL_SOURCE_ROOT resolves the
   * real host location instead of substituting a guessed prefix.
   */
  async mountSkillEnvironment(
    prepared: Pick<MrwPreparedEnvironment, 'bindingId' | 'skills'>,
  ): Promise<void> {
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
    })) as {
      data?: Array<{ skills?: Array<{ name?: string; path?: string }> }>;
    };
    const observedSkills = new Set(
      (observed.data ?? []).flatMap((entry) =>
        (entry.skills ?? []).map(
          (skill) => `${skill.name ?? ''}\u0000${skill.path ?? ''}`,
        ),
      ),
    );
    for (const [name, realPath] of resolved) {
      if (!observedSkills.has(`${name}\u0000${realPath}`)) {
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

  async prepareTurn(threadId: string): Promise<MrwTurnAdmission> {
    const binding = this.boundThreads.get(threadId);
    if (!binding)
      throw new HttpException(
        'MRW thread requires rebind',
        HttpStatus.CONFLICT,
      );
    if (binding.admissionId || this.preparingTurns.has(threadId)) {
      throw new HttpException(
        'MRW thread already has a pending or active turn admission',
        HttpStatus.CONFLICT,
      );
    }
    this.preparingTurns.set(threadId, binding);
    try {
      const admission = await this.backend.prepareTurn(threadId);
      if (
        admission.threadId !== threadId ||
        admission.environmentStatus !== 'configured'
      ) {
        throw new HttpException(
          'MRW turn environment is not ready',
          HttpStatus.CONFLICT,
        );
      }
      if (canonical(admission.dynamicTools) !== binding.tools) {
        throw new HttpException(
          'native_rebind_required: dynamic tool mount changed',
          HttpStatus.CONFLICT,
        );
      }
      const systemInstructions = this.assertSystemInstructions(
        admission.systemInstructions,
      );
      if (systemInstructions !== binding.systemInstructions) {
        throw new HttpException(
          'native_rebind_required: system instructions changed',
          HttpStatus.CONFLICT,
        );
      }
      if (admission.skills.some((skill) => !skill.contentDigest)) {
        throw new HttpException(
          'MRW turn skill digest is missing',
          HttpStatus.CONFLICT,
        );
      }
      await this.mountSkillEnvironment({
        bindingId: admission.admissionId,
        skills: admission.skills,
      });
      const expiresAt = Date.parse(admission.expiresAt);
      if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
        this.preparedSkills.delete(admission.admissionId);
        throw new HttpException(
          'MRW turn admission expired before native start',
          HttpStatus.CONFLICT,
        );
      }
      const mounted = this.preparedSkills.get(admission.admissionId) ?? [];
      this.preparedSkills.delete(admission.admissionId);
      if (
        this.boundThreads.get(threadId) !== binding ||
        this.preparingTurns.get(threadId) !== binding
      ) {
        throw new HttpException(
          'MRW turn admission was cancelled before native start',
          HttpStatus.CONFLICT,
        );
      }
      this.threadSkills.set(threadId, mounted);
      this.boundThreads.set(threadId, {
        ...binding,
        admissionId: admission.admissionId,
        turnId: undefined,
      });
      return admission;
    } finally {
      if (this.preparingTurns.get(threadId) === binding)
        this.preparingTurns.delete(threadId);
    }
  }

  abortTurnInput(threadId: string): void {
    this.preparingTurns.delete(threadId);
    const binding = this.boundThreads.get(threadId);
    if (binding)
      this.boundThreads.set(threadId, {
        tools: binding.tools,
        systemInstructions: binding.systemInstructions,
      });
    const readiness = this.threadInputReadiness.get(threadId);
    this.threadInputReadiness.delete(threadId);
    readiness?.reject(new Error('MRW turn input aborted'));
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
    attachments: MrwTurnAttachment[] = [],
  ): Promise<unknown> {
    const readiness = this.threadInputReadiness.get(threadId);
    const binding = this.boundThreads.get(threadId);
    if (
      !binding?.admissionId ||
      (binding.turnId && binding.turnId !== turnId)
    ) {
      throw new HttpException(
        'MRW turn admission is missing or mismatched',
        HttpStatus.CONFLICT,
      );
    }
    const promise = this.backend.recordInput(
      threadId,
      turnId,
      content,
      binding.admissionId,
      credentials,
      attachments,
    );
    void promise.then(
      () => {
        if (binding && this.boundThreads.get(threadId) === binding)
          this.boundThreads.set(threadId, { ...binding, turnId, credentials });
        readiness?.resolve();
        if (this.threadInputReadiness.get(threadId) === readiness)
          this.threadInputReadiness.delete(threadId);
      },
      (error: unknown) => {
        if (this.boundThreads.get(threadId) === binding)
          this.boundThreads.set(threadId, {
            tools: binding.tools,
            systemInstructions: binding.systemInstructions,
          });
        readiness?.reject(
          error instanceof Error ? error : new Error(String(error)),
        );
        if (this.threadInputReadiness.get(threadId) === readiness)
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
    this.threadSkills.delete(threadId);
    this.abortTurnInput(threadId);
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
    this.preparingTurns.delete(threadId);
    const binding = this.boundThreads.get(threadId);
    if (binding && (!binding.turnId || binding.turnId === turnId))
      this.boundThreads.set(threadId, {
        tools: binding.tools,
        systemInstructions: binding.systemInstructions,
      });
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
    this.preparingTurns.delete(threadId);
    const binding = this.boundThreads.get(threadId);
    if (binding && (!binding.turnId || binding.turnId === turnId))
      this.boundThreads.set(threadId, {
        tools: binding.tools,
        systemInstructions: binding.systemInstructions,
      });
    return this.backend.endTurn(threadId, turnId);
  }

  /** Clears all pending actions after an app-server restart invalidates them. */
  expireAll(): void {
    for (const threadId of this.boundThreads.keys())
      this.abortTurnInput(threadId);
    this.boundThreads.clear();
    this.threadSkills.clear();
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
