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

    expect(mockBackend.dispatch).toHaveBeenCalledWith(callParams);
    expect(mockEvents.emitActionRequired).toHaveBeenCalledWith(
      expect.objectContaining({ actionId: 'a1', callId: 'call1' }),
    );
    expect(respond).not.toHaveBeenCalled();
    expect(service.listPending('t1')).toHaveLength(1);
  });

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
    mockCodex.request
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ data: [{ skills: [{ path: realPath }] }] });

    try {
      await service.mountSkillEnvironment({
        bindingId: 'b1',
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
    mockCodex.request
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ data: [{ skills: [{ path: realPath }] }] });
    mockBackend.bind.mockResolvedValue({ threadId: 't1', bindingId: 'b1' });

    try {
      await service.mountSkillEnvironment({
        bindingId: 'b1',
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
      await service.bindThread('b1', 't1');

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
    mockBackend.bind.mockResolvedValue({ threadId: 't1', bindingId: 'b1' });

    await service.mountSkillEnvironment({
      bindingId: 'b1',
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
      skills: [],
    });
    await service.bindThread('b1', 't1');

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
      .mockResolvedValueOnce({ data: [{ skills: [{ path: pathA }] }] })
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ data: [{ skills: [{ path: pathB }] }] });
    mockBackend.bind.mockResolvedValue({});

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
          { name: 'a', path: '/app/a/SKILL.md', contentDigest: digest, relativePath: 'a/SKILL.md' },
        ],
      });
      await service.mountSkillEnvironment({
        ...base,
        bindingId: 'b2',
        skills: [
          { name: 'b', path: '/app/b/SKILL.md', contentDigest: digest, relativePath: 'b/SKILL.md' },
        ],
      });
      await service.bindThread('b1', 't1');
      await service.bindThread('b2', 't2');

      expect(service.turnSkillInputs('t1').map((item) => item.name)).toEqual(['a']);
      expect(service.turnSkillInputs('t2').map((item) => item.name)).toEqual(['b']);
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

    await service.recordInput('t1', 'turn1', 'original user words');

    expect(mockBackend.recordInput).toHaveBeenCalledWith(
      't1',
      'turn1',
      'original user words',
    );
  });

  it('waits for an in-flight host input recording before dispatching', async () => {
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
        { type: 'inputText', text: 'MRW host input was not recorded for this turn' },
      ],
    });
  });

  it('blocks a tool call that arrives before host input registration completes', async () => {
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

    service.beginTurnInput('t1');
    await service.recordInput('t1', 'turn2', 'again');
    await service.handleDynamicToolCall(9, { ...callParams, turnId: 'turn2' });

    expect(mockBackend.dispatch).toHaveBeenCalled();
  });
});
