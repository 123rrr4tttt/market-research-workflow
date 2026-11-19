import { HttpException, HttpStatus } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { CodexService } from '../codex/codex.service';
import { MrwActionRegistryService } from './mrw-action-registry.service';
import { MrwBackendClient } from './mrw-backend.client';
import { MrwEventBus } from './mrw-event-bus';
import { MrwService } from './mrw.service';
import type { MrwDynamicToolCallParams } from './mrw.types';

describe('MrwService', () => {
  let service: MrwService;
  const respond = vi.fn();
  const mockBackend = {
    prepare: vi.fn(),
    prepareTurn: vi.fn(),
    bind: vi.fn(),
    dispatch: vi.fn(),
    confirm: vi.fn(),
    recordInput: vi.fn(),
    endTurn: vi.fn(),
  };
  const mockCodex = {
    getClient: vi.fn().mockReturnValue({ respondToServerRequest: respond }),
    request: vi.fn(),
  };
  const mockEvents = {
    emitActionRequired: vi.fn(),
    emitActionResolved: vi.fn(),
  };

  const callParams: MrwDynamicToolCallParams = {
    threadId: 't1',
    turnId: 'turn1',
    callId: 'call1',
    namespace: 'demo',
    tool: 'write',
    arguments: { target: 'a' },
  };
  const systemInstructions =
    'You are the MRW native Agent. Follow the mounted system navigation.';

  beforeEach(async () => {
    vi.restoreAllMocks();
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        MrwService,
        MrwActionRegistryService,
        { provide: MrwBackendClient, useValue: mockBackend },
        { provide: CodexService, useValue: mockCodex },
        { provide: MrwEventBus, useValue: mockEvents },
      ],
    }).compile();

    service = module.get(MrwService);
    vi.clearAllMocks();
    respond.mockClear();
    mockCodex.request.mockReset();
    mockCodex.getClient.mockReturnValue({ respondToServerRequest: respond });
    mockBackend.prepare.mockResolvedValue({
      bindingId: 'b1',
      dynamicTools: [],
      systemInstructions,
    });
    mockBackend.bind.mockResolvedValue({
      threadId: 't1',
      dynamicTools: [],
      systemInstructions,
    });
    mockBackend.prepareTurn.mockResolvedValue({
      admissionId: 'admission-1',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skills: [],
      skillRoots: [],
      systemInstructions,
      expiresAt: '2999-01-01T00:00:00Z',
    });
  });

  async function bindPrepared(): Promise<void> {
    await service.prepareThread('p1');
    await service.bindThread('b1', 't1');
  }

  async function admit(): Promise<void> {
    await bindPrepared();
    await service.prepareTurn('t1');
  }

  it('rejects concurrent and active same-thread admissions until the turn ends', async () => {
    await bindPrepared();
    let resolveFirst!: (value: unknown) => void;
    const firstBackendCall = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    mockBackend.prepareTurn.mockImplementationOnce(() => firstBackendCall);

    const first = service.prepareTurn('t1');
    await expect(service.prepareTurn('t1')).rejects.toMatchObject({
      status: 409,
    });
    expect(mockBackend.prepareTurn).toHaveBeenCalledTimes(1);

    resolveFirst({
      admissionId: 'first',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skills: [],
      systemInstructions,
      expiresAt: '2999-01-01T00:00:00Z',
    });
    await first;
    await expect(service.prepareTurn('t1')).rejects.toMatchObject({
      status: 409,
    });
    expect(mockBackend.prepareTurn).toHaveBeenCalledTimes(1);

    await service.endTurn('t1', 'turn1');
    await expect(service.prepareTurn('t1')).resolves.toMatchObject({
      admissionId: 'admission-1',
    });
  });

  it('cannot install a cancelled preparation over a later admission', async () => {
    await bindPrepared();
    let resolveFirst!: (value: unknown) => void;
    const firstBackendCall = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    mockBackend.prepareTurn.mockImplementationOnce(() => firstBackendCall);

    const cancelled = service.prepareTurn('t1');
    service.abortTurnInput('t1');
    await service.prepareTurn('t1');
    resolveFirst({
      admissionId: 'cancelled',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skills: [],
      systemInstructions,
      expiresAt: '2999-01-01T00:00:00Z',
    });
    await expect(cancelled).rejects.toMatchObject({ status: 409 });
    await expect(service.prepareTurn('t1')).rejects.toMatchObject({
      status: 409,
    });
  });

  it('refuses a changed native tool schema before mounting or starting a turn', async () => {
    mockBackend.prepare.mockResolvedValue({
      bindingId: 'b1',
      dynamicTools: [{ name: 'read', inputSchema: { type: 'object' } }],
      systemInstructions,
    });
    await bindPrepared();
    mockBackend.prepareTurn.mockResolvedValue({
      admissionId: 'a2',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [{ name: 'read', inputSchema: { type: 'string' } }],
      skills: [],
      systemInstructions,
    });

    await expect(service.prepareTurn('t1')).rejects.toMatchObject({
      status: 409,
    });
    expect(mockCodex.request).not.toHaveBeenCalled();
  });

  it('rejects an MRW prepare without valid bounded system instructions', async () => {
    mockBackend.prepare.mockResolvedValue({
      bindingId: 'b1',
      dynamicTools: [],
      systemInstructions: '',
    });

    await expect(service.prepareThread('p1')).rejects.toMatchObject({
      status: HttpStatus.BAD_GATEWAY,
    });
  });

  it('refuses bind when the prepared system instructions changed', async () => {
    mockBackend.prepare.mockResolvedValue({
      bindingId: 'b1',
      dynamicTools: [],
      systemInstructions,
    });
    await service.prepareThread('p1');
    mockBackend.bind.mockResolvedValue({
      threadId: 't1',
      dynamicTools: [],
      systemInstructions: 'changed instructions',
    });

    await expect(service.bindThread('b1', 't1')).rejects.toMatchObject({
      status: HttpStatus.CONFLICT,
    });
    await expect(service.bindThread('b1', 't1')).rejects.toThrow(
      'native_rebind_required: system instructions changed during bind',
    );
    expect(service.isBound('t1')).toBe(false);
  });

  it('refuses bind without an actual prepared instruction load', async () => {
    mockBackend.bind.mockResolvedValue({
      threadId: 't1',
      dynamicTools: [],
      systemInstructions,
    });

    await expect(service.bindThread('b1', 't1')).rejects.toThrow(
      'native_rebind_required: prepared system instructions are missing',
    );
    expect(service.isBound('t1')).toBe(false);
  });

  it('requires native rebind when admitted instructions differ from thread load', async () => {
    await bindPrepared();
    mockBackend.prepareTurn.mockResolvedValue({
      admissionId: 'a2',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skills: [],
      systemInstructions: 'changed instructions',
    });

    await expect(service.prepareTurn('t1')).rejects.toThrow(
      'native_rebind_required: system instructions changed',
    );
    expect(mockCodex.request).not.toHaveBeenCalled();
  });

  it('refuses turn skills without a verifiable content digest', async () => {
    await bindPrepared();
    mockBackend.prepareTurn.mockResolvedValue({
      admissionId: 'a2',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skills: [{ name: 'demo', path: '/app/demo/SKILL.md' }],
      systemInstructions,
    });

    await expect(service.prepareTurn('t1')).rejects.toMatchObject({
      status: 409,
    });
    expect(mockCodex.request).not.toHaveBeenCalled();
  });

  it('refuses an admission that expires before native turn start', async () => {
    await bindPrepared();
    mockBackend.prepareTurn.mockResolvedValue({
      admissionId: 'expired',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skills: [],
      systemInstructions,
      expiresAt: '2000-01-01T00:00:00Z',
    });
    await expect(service.prepareTurn('t1')).rejects.toMatchObject({
      status: 409,
    });
    expect(service.turnSkillInputs('t1')).toEqual([]);
  });

  it('rechecks skill bytes on every admitted turn', async () => {
    const previous = process.env.MRW_SKILL_SOURCE_ROOT;
    process.env.MRW_SKILL_SOURCE_ROOT = '/tmp/mrw-skills';
    vi.spyOn(fs, 'realpath').mockResolvedValue('/tmp/mrw-skills/demo/SKILL.md');
    vi.spyOn(fs, 'readFile').mockResolvedValue(Buffer.from('changed'));
    await bindPrepared();
    mockBackend.prepareTurn.mockResolvedValue({
      admissionId: 'a2',
      threadId: 't1',
      environmentStatus: 'configured',
      dynamicTools: [],
      skillRoots: [],
      skills: [
        {
          name: 'demo',
          path: '/app/demo/SKILL.md',
          relativePath: 'demo/SKILL.md',
          contentDigest: createHash('sha256').update('original').digest('hex'),
        },
      ],
      systemInstructions,
    });

    try {
      await expect(service.prepareTurn('t1')).rejects.toMatchObject({
        status: 409,
      });
      expect(mockCodex.request).not.toHaveBeenCalled();
    } finally {
      if (previous === undefined) delete process.env.MRW_SKILL_SOURCE_ROOT;
      else process.env.MRW_SKILL_SOURCE_ROOT = previous;
    }
  });

  it('holds back a call that needs approval and emits the card', async () => {
    mockBackend.dispatch.mockResolvedValue({
      success: false,
      contentItems: [],
      pendingAction: {
        actionId: 'a1',
        toolName: 'demo.write',
        arguments: { target: 'a' },
        projectKey: 'p1',
        threadId: 't1',
        turnId: 'turn1',
        actionDigest: 'd'.repeat(64),
      },
    });

    await service.handleDynamicToolCall(9, callParams);

    expect(mockBackend.dispatch).toHaveBeenCalledWith(callParams, undefined);
    expect(mockEvents.emitActionRequired).toHaveBeenCalledWith(
      expect.objectContaining({ actionId: 'a1', callId: 'call1' }),
    );
    expect(respond).not.toHaveBeenCalled();
    expect(service.listPending('t1')).toHaveLength(1);
  });

  it('binds original credentials to the accepted turn and clears them on end', async () => {
    mockBackend.bind.mockResolvedValue({
      threadId: 't1',
      systemInstructions,
    });
    mockBackend.recordInput.mockResolvedValue({ recorded: true });
    mockBackend.dispatch.mockResolvedValue({ success: true, contentItems: [] });
    const credentials = { sessionCookie: 'codex_session=original-session' };
    await admit();
    await service.recordInput('t1', 'turn1', 'read', credentials);
    await service.handleDynamicToolCall(1, callParams);
    expect(mockBackend.dispatch).toHaveBeenLastCalledWith(
      callParams,
      credentials,
    );
    await service.handleDynamicToolCall(2, {
      ...callParams,
      turnId: 'other-turn',
    });
    expect(mockBackend.dispatch).toHaveBeenLastCalledWith(
      { ...callParams, turnId: 'other-turn' },
      undefined,
    );
    await service.endTurn('t1', 'turn1');
    await service.handleDynamicToolCall(3, callParams);
    expect(mockBackend.dispatch).toHaveBeenLastCalledWith(
      callParams,
      undefined,
    );
  });

  it.each(['thread', 'turn', 'end', 'expire'])(
    'does not restore credentials when pending input settles after %s cleanup',
    async (cleanup) => {
      mockBackend.bind.mockResolvedValue({
        threadId: 't1',
        systemInstructions,
      });
      mockBackend.dispatch.mockResolvedValue({
        success: true,
        contentItems: [],
      });
      let resolve!: (value: unknown) => void;
      mockBackend.recordInput.mockReturnValue(
        new Promise((done) => {
          resolve = done;
        }),
      );
      await admit();
      const pending = service.recordInput('t1', 'turn1', 'read', {
        codexAuth: 'original-token',
      });
      if (cleanup === 'thread') service.cancelForThread('t1');
      else if (cleanup === 'turn') service.cancelForTurn('t1', 'turn1');
      else if (cleanup === 'end') await service.endTurn('t1', 'turn1');
      else service.expireAll();
      resolve({ recorded: true });
      await pending;
      await service.handleDynamicToolCall(1, callParams);
      expect(mockBackend.dispatch).toHaveBeenLastCalledWith(
        callParams,
        undefined,
      );
    },
  );

  it('answers the app-server directly for a completed call', async () => {
    mockBackend.dispatch.mockResolvedValue({
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });

    await service.handleDynamicToolCall(10, callParams);

    expect(respond).toHaveBeenCalledWith(10, {
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });
    expect(mockEvents.emitActionRequired).not.toHaveBeenCalled();
  });

  it('confirms, re-dispatches, and resolves the original RPC', async () => {
    mockBackend.dispatch
      .mockResolvedValueOnce({
        success: false,
        contentItems: [],
        pendingAction: {
          actionId: 'a1',
          toolName: 'demo.write',
          arguments: { target: 'a' },
          projectKey: 'p1',
          threadId: 't1',
          turnId: 'turn1',
        },
      })
      .mockResolvedValueOnce({
        success: true,
        contentItems: [{ type: 'inputText', text: 'ran' }],
      });
    mockBackend.confirm.mockResolvedValue({ confirmed: true });

    await service.handleDynamicToolCall(9, callParams);
    const result = await service.confirmAction({
      threadId: 't1',
      turnId: 'turn1',
      actionId: 'a1',
      approved: true,
      userText: 'approval:a1 Allow once',
    });

    expect(mockBackend.confirm).toHaveBeenCalledWith({
      threadId: 't1',
      turnId: 'turn1',
      actionId: 'a1',
      approved: true,
      userText: 'approval:a1 Allow once',
    });
    expect(mockBackend.dispatch).toHaveBeenCalledTimes(2);
    expect(respond).toHaveBeenCalledWith(9, {
      success: true,
      contentItems: [{ type: 'inputText', text: 'ran' }],
    });
    expect(mockEvents.emitActionResolved).toHaveBeenCalledWith('a1', 't1');
    expect(service.listPending('t1')).toHaveLength(0);
    expect(result).toEqual({
      confirmed: true,
      actionId: 'a1',
      approved: true,
      threadId: 't1',
    });
  });

  it('rejects a confirmation for an unknown action', async () => {
    let caught: unknown;
    try {
      await service.confirmAction({
        threadId: 't1',
        turnId: 'turn1',
        actionId: 'missing',
        approved: true,
      });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(HttpException);
    expect((caught as HttpException).getStatus()).toBe(HttpStatus.NOT_FOUND);
  });

  it('mounts skills with cross-host path and content digest verification', async () => {
    const sourceRoot = '/tmp/mrw-skills';
    const previous = process.env.MRW_SKILL_SOURCE_ROOT;
    process.env.MRW_SKILL_SOURCE_ROOT = sourceRoot;
    const realPath = path.join(sourceRoot, 'demo', 'SKILL.md');
    const digest = createHash('sha256').update('skill-body').digest('hex');
    vi.spyOn(fs, 'realpath').mockResolvedValue(realPath);
    vi.spyOn(fs, 'readFile').mockResolvedValue(Buffer.from('skill-body'));
    mockCodex.request.mockResolvedValueOnce(undefined).mockResolvedValueOnce({
      data: [{ skills: [{ name: 'demo', path: realPath }] }],
    });

    try {
      await service.mountSkillEnvironment({
        bindingId: 'b1',
        skills: [
          {
            name: 'demo',
            path: '/app/skills/demo/SKILL.md',
            contentDigest: digest,
            sourceRoot: '/app/skills',
            relativePath: 'demo/SKILL.md',
          },
        ],
      });

      expect(mockCodex.request).toHaveBeenCalledWith('skills/extraRoots/set', {
        extraRoots: [sourceRoot],
      });
      expect(mockCodex.request).toHaveBeenCalledWith('skills/list', {
        forceReload: true,
      });
    } finally {
      if (previous === undefined) delete process.env.MRW_SKILL_SOURCE_ROOT;
      else process.env.MRW_SKILL_SOURCE_ROOT = previous;
    }
  });

  it('rejects a skill whose relative path escapes the trusted root', async () => {
    const previous = process.env.MRW_SKILL_SOURCE_ROOT;
    process.env.MRW_SKILL_SOURCE_ROOT = '/tmp/mrw-skills';
    try {
      await expect(
        service.mountSkillEnvironment({
          bindingId: 'b1',
          skills: [
            {
              name: 'bad',
              path: '/app/skills/bad/SKILL.md',
              contentDigest: 'x',
              relativePath: '../etc/passwd',
            },
          ],
        }),
      ).rejects.toBeInstanceOf(HttpException);
    } finally {
      if (previous === undefined) delete process.env.MRW_SKILL_SOURCE_ROOT;
      else process.env.MRW_SKILL_SOURCE_ROOT = previous;
    }
  });

  it('binds a thread and returns only that thread mapped skill inputs', async () => {
    const sourceRoot = '/tmp/mrw-skills';
    const previous = process.env.MRW_SKILL_SOURCE_ROOT;
    process.env.MRW_SKILL_SOURCE_ROOT = sourceRoot;
    const realPath = path.join(sourceRoot, 'demo', 'SKILL.md');
    const digest = createHash('sha256').update('skill-body').digest('hex');
    vi.spyOn(fs, 'realpath').mockResolvedValue(realPath);
    vi.spyOn(fs, 'readFile').mockResolvedValue(Buffer.from('skill-body'));
    mockCodex.request.mockResolvedValueOnce(undefined).mockResolvedValueOnce({
      data: [{ skills: [{ name: 'demo', path: realPath }] }],
    });
    mockBackend.bind.mockResolvedValue({
      threadId: 't1',
      bindingId: 'b1',
      systemInstructions,
    });

    try {
      await service.mountSkillEnvironment({
        bindingId: 'b1',
        skills: [
          {
            name: 'demo',
            path: '/app/skills/demo/SKILL.md',
            contentDigest: digest,
            sourceRoot: '/app/skills',
            relativePath: 'demo/SKILL.md',
          },
        ],
      });
      await bindPrepared();

      expect(service.isBound('t1')).toBe(true);
      expect(service.isBound('t2')).toBe(false);
      expect(service.turnSkillInputs('t1')).toEqual([
        { type: 'skill', name: 'demo', path: realPath },
      ]);
      expect(service.turnSkillInputs('t2')).toEqual([]);
    } finally {
      if (previous === undefined) delete process.env.MRW_SKILL_SOURCE_ROOT;
      else process.env.MRW_SKILL_SOURCE_ROOT = previous;
    }
  });

  it('treats an empty base environment as bound with no skill inputs', async () => {
    mockBackend.bind.mockResolvedValue({
      threadId: 't1',
      bindingId: 'b1',
      systemInstructions,
    });

    await service.mountSkillEnvironment({
      bindingId: 'b1',
      skills: [],
    });
    await bindPrepared();

    expect(service.isBound('t1')).toBe(true);
    expect(service.turnSkillInputs('t1')).toEqual([]);
    expect(mockCodex.request).not.toHaveBeenCalled();
  });

  it('isolates skills per thread and unions their skill roots', async () => {
    const sourceRoot = '/tmp/mrw-skills';
    const previous = process.env.MRW_SKILL_SOURCE_ROOT;
    process.env.MRW_SKILL_SOURCE_ROOT = sourceRoot;
    const digest = createHash('sha256').update('skill-body').digest('hex');
    const pathA = path.join(sourceRoot, 'a', 'SKILL.md');
    const pathB = path.join(sourceRoot, 'b', 'SKILL.md');
    vi.spyOn(fs, 'readFile').mockResolvedValue(Buffer.from('skill-body'));
    vi.spyOn(fs, 'realpath')
      .mockResolvedValueOnce(pathA)
      .mockResolvedValueOnce(pathB);
    mockCodex.request
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({
        data: [{ skills: [{ name: 'a', path: pathA }] }],
      })
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({
        data: [{ skills: [{ name: 'b', path: pathB }] }],
      });
    mockBackend.bind.mockResolvedValue({ systemInstructions });

    const base = {
      projectKey: 'p1',
      packageId: null,
      packageVersion: null,
      sessionId: null,
      threadId: null,
      status: 'configured',
      environmentStatus: 'configured',
      environmentDigest: 'd',
      dynamicTools: [],
      skillRoots: [],
    };

    try {
      await service.mountSkillEnvironment({
        ...base,
        bindingId: 'b1',
        skills: [
          {
            name: 'a',
            path: '/app/a/SKILL.md',
            contentDigest: digest,
            relativePath: 'a/SKILL.md',
          },
        ],
      });
      await service.mountSkillEnvironment({
        ...base,
        bindingId: 'b2',
        skills: [
          {
            name: 'b',
            path: '/app/b/SKILL.md',
            contentDigest: digest,
            relativePath: 'b/SKILL.md',
          },
        ],
      });
      await service.prepareThread('p1');
      await service.bindThread('b1', 't1');
      mockBackend.prepare.mockResolvedValue({
        bindingId: 'b2',
        dynamicTools: [],
        systemInstructions,
      });
      await service.prepareThread('p1');
      await service.bindThread('b2', 't2');

      expect(service.turnSkillInputs('t1').map((item) => item.name)).toEqual([
        'a',
      ]);
      expect(service.turnSkillInputs('t2').map((item) => item.name)).toEqual([
        'b',
      ]);
      expect(mockCodex.request).toHaveBeenCalledWith('skills/extraRoots/set', {
        extraRoots: [sourceRoot],
      });
    } finally {
      if (previous === undefined) delete process.env.MRW_SKILL_SOURCE_ROOT;
      else process.env.MRW_SKILL_SOURCE_ROOT = previous;
    }
  });

  it('records only the original user text through the backend', async () => {
    mockBackend.recordInput.mockResolvedValue({ recorded: true });
    await admit();

    await service.recordInput('t1', 'turn1', 'original user words');

    expect(mockBackend.recordInput).toHaveBeenCalledWith(
      't1',
      'turn1',
      'original user words',
      'admission-1',
      undefined,
      [],
    );
  });

  it('waits for an in-flight host input recording before dispatching', async () => {
    await admit();
    const respond = vi.fn();
    mockCodex.getClient.mockReturnValue({ respondToServerRequest: respond });
    let resolveRecord!: (value: unknown) => void;
    const recordPromise = new Promise((resolve) => {
      resolveRecord = resolve;
    });
    mockBackend.recordInput.mockReturnValue(recordPromise);
    mockBackend.dispatch.mockResolvedValue({
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });

    service.beginTurnInput('t1');
    const recordCall = service.recordInput('t1', 'turn1', 'hello');
    const dispatchCall = service.handleDynamicToolCall(9, callParams);

    await Promise.resolve();
    expect(mockBackend.dispatch).not.toHaveBeenCalled();

    resolveRecord({ recorded: true });
    await Promise.all([recordCall, dispatchCall]);

    expect(mockBackend.dispatch).toHaveBeenCalled();
    expect(respond).toHaveBeenCalledWith(9, {
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });
  });

  it('answers a clear tool failure when in-flight host input recording rejects', async () => {
    await admit();
    const respond = vi.fn();
    mockCodex.getClient.mockReturnValue({ respondToServerRequest: respond });
    let rejectRecord!: (error: Error) => void;
    const recordPromise = new Promise((_, reject) => {
      rejectRecord = reject;
    });
    mockBackend.recordInput.mockReturnValue(recordPromise);
    mockBackend.dispatch.mockResolvedValue({
      success: true,
      contentItems: [],
    });

    service.beginTurnInput('t1');
    const recordCall = service.recordInput('t1', 'turn1', 'hello');
    const dispatchCall = service.handleDynamicToolCall(9, callParams);

    await Promise.resolve();
    rejectRecord(new Error('backend down'));
    await recordCall.catch(() => undefined);
    await dispatchCall;

    expect(mockBackend.dispatch).not.toHaveBeenCalled();
    expect(respond).toHaveBeenCalledWith(9, {
      success: false,
      contentItems: [
        {
          type: 'inputText',
          text: 'MRW host input was not recorded for this turn',
        },
      ],
    });
  });

  it('blocks a tool call that arrives before host input registration completes', async () => {
    await admit();
    const respond = vi.fn();
    mockCodex.getClient.mockReturnValue({ respondToServerRequest: respond });
    mockBackend.dispatch.mockResolvedValue({
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });
    mockBackend.recordInput.mockResolvedValue({ recorded: true });

    service.beginTurnInput('t1');
    const dispatchCall = service.handleDynamicToolCall(9, callParams);
    await Promise.resolve();
    expect(mockBackend.dispatch).not.toHaveBeenCalled();

    await service.recordInput('t1', 'turn1', 'hello');
    await dispatchCall;

    expect(mockBackend.dispatch).toHaveBeenCalled();
    expect(respond).toHaveBeenCalledWith(9, {
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });
  });

  it('clears a rejected input gate so a later turn starts fresh', async () => {
    await admit();
    mockBackend.recordInput
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue({ recorded: true });
    mockBackend.dispatch.mockResolvedValue({
      success: true,
      contentItems: [{ type: 'inputText', text: 'done' }],
    });
    mockCodex.getClient.mockReturnValue({
      respondToServerRequest: vi.fn(),
    });

    service.beginTurnInput('t1');
    await service.recordInput('t1', 'turn1', 'hello').catch(() => undefined);

    await service.prepareTurn('t1');
    service.beginTurnInput('t1');
    await service.recordInput('t1', 'turn2', 'again');
    await service.handleDynamicToolCall(9, { ...callParams, turnId: 'turn2' });

    expect(mockBackend.dispatch).toHaveBeenCalled();
  });
});
