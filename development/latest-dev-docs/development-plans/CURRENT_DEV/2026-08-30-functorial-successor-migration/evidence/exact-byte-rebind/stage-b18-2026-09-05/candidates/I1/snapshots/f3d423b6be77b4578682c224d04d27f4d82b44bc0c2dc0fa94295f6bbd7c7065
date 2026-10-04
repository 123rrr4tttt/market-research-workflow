import { expect, test } from '@playwright/test'
import {
  SUCCESSOR_ENVELOPE_STATUSES,
  SUCCESSOR_PENDING_COMMANDS_KEY,
  SUCCESSOR_PROJECT_PREFERENCE_KEY,
  SUCCESSOR_V2_COMMAND_URL,
  SUCCESSOR_V2_QUERY_URL,
  SuccessorBindingError,
  SuccessorConflictError,
  SuccessorDecodeError,
  SuccessorRequestError,
  SuccessorRuntimeError,
  SuccessorScopeError,
  SuccessorStaleError,
  assertSuccessorProjectionSnapshotData,
  clearSuccessorProjectPreference,
  computeSuccessorRollbackReceiptDigest,
  computeSuccessorCommandFingerprint,
  createSuccessorQueryRefetcher,
  decodeSuccessorRollbackTransitionReceipt,
  decodeSuccessorEnvelope,
  fetchSuccessorQuery,
  getSuccessorProjectPreference,
  readSuccessorPendingCommands,
  resetSuccessorProjectionClock,
  setSuccessorProjectPreference,
  sha256Hex,
  submitSuccessorCommand,
  type SuccessorCommandOptions,
  type SuccessorEnvelope,
  type SuccessorEnvelopeMeta,
  type SuccessorEnvelopeStatus,
  type SuccessorProjectionMeta,
  type SuccessorRollbackTransitionReceipt,
  type SuccessorQueryOptions,
} from '../../src/lib/api/domains/successor-runtime'

const DIGEST_64 = 'a'.repeat(64)

function scopeRef(overrides: Record<string, unknown> = {}) {
  return {
    project_key: 'demo',
    resolved_schema: 'public',
    project_registry_revision: 1,
    incarnation: 'inc-1',
    scope_digest: DIGEST_64,
    ...overrides,
  }
}

function sourceKey(overrides: Record<string, unknown> = {}) {
  return {
    projector_id: 'projector-1',
    projector_version: 'v1',
    source_kind: 'legacy',
    source_ref: 'ref://demo/proj',
    source_incarnation: 'inc-2',
    ...overrides,
  }
}

function commandMeta(overrides: Record<string, unknown> = {}): SuccessorEnvelopeMeta {
  return {
    project_key: 'demo',
    trace_id: 'trace-1',
    command_id: 'cmd-1',
    project_scope_ref: scopeRef(),
    ...overrides,
  }
}

function queryMeta(overrides: Record<string, unknown> = {}): SuccessorEnvelopeMeta {
  return {
    project_key: 'demo',
    trace_id: 'trace-1',
    query_id: 'q-1',
    project_scope_ref: scopeRef(),
    ...overrides,
  }
}

function projectionMeta(overrides: Record<string, unknown> = {}): SuccessorProjectionMeta {
  return {
    project_key: 'demo',
    trace_id: 'trace-1',
    projection_id: 'proj-1',
    project_scope_ref: scopeRef(),
    projection_generation: 1,
    offset_revision: 0,
    projection_revision: 1,
    source_digest: DIGEST_64,
    cursor: 0,
    ...sourceKey(),
    ...overrides,
  }
}

function pendingKey(projectLocator: string, commandId: string): string {
  return JSON.stringify([projectLocator, commandId])
}

function projectionData(
  meta: Record<string, unknown>,
  offsetRef = 'offset-ref-1',
  candidateValues: unknown[] = [],
  rollbackTransition?: unknown,
) {
  const data: Record<string, unknown> = {
    projection_id: meta.projection_id,
    projector_id: meta.projector_id,
    projector_version: meta.projector_version,
    source_kind: meta.source_kind,
    source_ref: meta.source_ref,
    source_incarnation: meta.source_incarnation,
    projection_generation: meta.projection_generation,
    offset_revision: meta.offset_revision,
    projection_revision: meta.projection_revision,
    source_digest: meta.source_digest,
    cursor: meta.cursor,
    offset_ref: offsetRef,
    candidate_values: candidateValues,
  }
  if (rollbackTransition !== undefined) {
    data.rollback_transition = rollbackTransition
  }
  return data
}

function projectionEnvelope(
  metaOverrides: Record<string, unknown> = {},
  status: 'ok' | 'waiting' = 'ok',
  dataOverrides: {
    offsetRef?: string
    candidateValues?: unknown[]
    rollbackTransition?: unknown
  } = {},
): SuccessorEnvelope {
  const meta = projectionMeta(metaOverrides)
  return envelope(status, {
    meta,
    data: projectionData(
      meta,
      dataOverrides.offsetRef ?? 'offset-ref-1',
      dataOverrides.candidateValues ?? [],
      dataOverrides.rollbackTransition,
    ),
  })
}

function rollbackPayload(overrides: Record<string, unknown> = {}) {
  return {
    payload_kind: 'rollback_projection' as const,
    projection_id: 'proj-1',
    ...sourceKey(),
    target_generation: 3,
    expected_active_generation: 4,
    expected_offset_revision: 7,
    ...overrides,
  }
}

function position(overrides: Record<string, unknown> = {}) {
  return {
    projection_generation: 3,
    offset_revision: 8,
    projection_revision: 5,
    source_digest: DIGEST_64,
    cursor: 7,
    offset_ref: 'ref-active',
    ...overrides,
  }
}

function rollbackReceipt(overrides: Record<string, unknown> = {}): SuccessorRollbackTransitionReceipt {
  const receipt = {
    contract: 'C9RollbackTransitionReceipt.v1' as const,
    ref: 'rollback-1',
    digest: '',
    projection_id: 'proj-1',
    ...sourceKey(),
    from: position({ projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 }),
    to: position(),
    generation_completeness_digest: DIGEST_64,
    ...overrides,
  } as SuccessorRollbackTransitionReceipt
  if (!receipt.digest) {
    receipt.digest = computeSuccessorRollbackReceiptDigest(receipt)
  }
  return receipt
}

function rollbackSnapshotEnvelope(
  receipt: SuccessorRollbackTransitionReceipt,
  metaOverrides: Record<string, unknown> = {},
  offsetRef = 'ref-active',
  traceId = 'trace-rbq',
): SuccessorEnvelope {
  const meta = projectionMeta({
    trace_id: traceId,
    projection_generation: receipt.to.projection_generation,
    offset_revision: receipt.to.offset_revision,
    projection_revision: receipt.to.projection_revision,
    source_digest: receipt.to.source_digest,
    cursor: receipt.to.cursor,
    ...metaOverrides,
  })
  return envelope('ok', { meta, data: projectionData(meta, offsetRef, [], receipt) })
}

function envelope(
  status: SuccessorEnvelopeStatus,
  overrides: Partial<SuccessorEnvelope> = {},
): SuccessorEnvelope {
  const base: SuccessorEnvelope = {
    status,
    data: status === 'ok' || status === 'waiting' ? { ok: true } : null,
    error:
      status === 'blocked' || status === 'unavailable' || status === 'conflict' || status === 'error'
        ? { code: `${status}_code`, message: `${status} message`, details: {} }
        : null,
    meta: projectionMeta(),
    control_feedback: false,
  }
  return { ...base, ...overrides }
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function localStorageKeys(): string[] {
  const keys: string[] = []
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index)
    if (key) keys.push(key)
  }
  return keys.sort()
}

function installLocalStorageShim() {
  const store = new Map<string, string>()
  const shim: Storage = {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key)
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
  }
  ;(globalThis as Record<string, unknown>).localStorage = shim
  return { shim, store }
}

type FetchCall = { url: string; init: RequestInit }

function installFetchHarness(respond: (call: FetchCall) => Response | Promise<Response>) {
  const calls: FetchCall[] = []
  const previous = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    const call = { url, init: init ?? {} }
    calls.push(call)
    return respond(call)
  }) as typeof fetch
  return {
    calls,
    restore() {
      globalThis.fetch = previous
    },
  }
}

test.beforeEach(() => {
  installLocalStorageShim()
  resetSuccessorProjectionClock()
})

test('sha256 fingerprint matches known vectors', () => {
  expect(sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  expect(sha256Hex('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
})

test('decoder mirrors the six v2 envelope variants and preserves full meta', () => {
  expect(SUCCESSOR_ENVELOPE_STATUSES).toEqual([
    'ok',
    'waiting',
    'blocked',
    'unavailable',
    'conflict',
    'error',
  ])

  const ok = decodeSuccessorEnvelope(
    envelope('ok', {
      data: { ready: true, lanes: 3 },
      meta: commandMeta({ command_id: 'cmd-ok' }),
    }),
  )
  expect(ok.status).toBe('ok')
  expect(ok.data).toEqual({ ready: true, lanes: 3 })
  expect(ok.error).toBeNull()
  expect(ok.control_feedback).toBe(false)
  expect(ok.meta).toMatchObject({
    project_key: 'demo',
    trace_id: 'trace-1',
    command_id: 'cmd-ok',
    project_scope_ref: {
      project_key: 'demo',
      resolved_schema: 'public',
      project_registry_revision: 1,
      incarnation: 'inc-1',
      scope_digest: DIGEST_64,
    },
  })

  const waiting = decodeSuccessorEnvelope(envelope('waiting'))
  expect(waiting.status).toBe('waiting')
  expect(waiting.data).not.toBeNull()

  for (const status of ['blocked', 'unavailable', 'conflict', 'error'] as const) {
    const decoded = decodeSuccessorEnvelope(envelope(status))
    expect(decoded.status).toBe(status)
    expect(decoded.data).toBeNull()
    expect(decoded.error).toMatchObject({ code: `${status}_code`, message: `${status} message` })
  }

  const projection = decodeSuccessorEnvelope(
    envelope('ok', {
      meta: projectionMeta({
        projection_id: 'proj-9',
        projection_revision: 7,
        source_digest: 'b'.repeat(64),
        cursor: 42,
      }),
    }),
  )
  expect(projection.meta).toMatchObject({
    projection_id: 'proj-9',
    projection_revision: 7,
    source_digest: 'b'.repeat(64),
    cursor: 42,
  })
})

test('decoder accepts UNRESOLVED transport meta and rejects scope-carrying unresolved meta', () => {
  const unresolved = decodeSuccessorEnvelope({
    status: 'error',
    data: null,
    error: { code: 'SCOPE_RESOLUTION_FAILED', message: 'locator unresolved', details: {} },
    meta: {
      project_key: 'demo',
      trace_id: 'trace-1',
      request_id: 'cmd-9',
      resolution_state: 'UNRESOLVED',
    },
    control_feedback: false,
  })
  expect(unresolved.status).toBe('error')
  expect(unresolved.error?.code).toBe('SCOPE_RESOLUTION_FAILED')
  expect(unresolved.meta).toEqual({
    project_key: 'demo',
    trace_id: 'trace-1',
    request_id: 'cmd-9',
    resolution_state: 'UNRESOLVED',
  })

  const malformed: unknown[] = [
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: {
        project_key: 'demo',
        trace_id: 'trace-1',
        request_id: 'cmd-9',
        resolution_state: 'UNRESOLVED',
      },
      control_feedback: false,
    },
    {
      status: 'error',
      data: null,
      error: { code: 'X', message: 'x', details: {} },
      meta: {
        project_key: 'demo',
        trace_id: 'trace-1',
        request_id: 'cmd-9',
        resolution_state: 'RESOLVED',
      },
      control_feedback: false,
    },
    {
      status: 'error',
      data: null,
      error: { code: 'X', message: 'x', details: {} },
      meta: {
        project_key: 'demo',
        trace_id: 'trace-1',
        resolution_state: 'UNRESOLVED',
      },
      control_feedback: false,
    },
    {
      status: 'error',
      data: null,
      error: { code: 'X', message: 'x', details: {} },
      meta: {
        project_key: 'demo',
        trace_id: 'trace-1',
        request_id: 'cmd-9',
        resolution_state: 'UNRESOLVED',
        project_scope_ref: scopeRef(),
      },
      control_feedback: false,
    },
    {
      status: 'error',
      data: null,
      error: { code: 'X', message: 'x', details: {} },
      meta: {
        project_key: 'demo',
        trace_id: 'trace-1',
        request_id: 'cmd-9',
        resolution_state: 'UNRESOLVED',
        command_id: 'cmd-9',
      },
      control_feedback: false,
    },
  ]

  for (const raw of malformed) {
    expect(() => decodeSuccessorEnvelope(raw)).toThrow(SuccessorDecodeError)
  }
})

test('decoder enforces exact ok/waiting and error-family variant rules', () => {
  expect(() =>
    decodeSuccessorEnvelope({
      status: 'ok',
      data: null,
      error: null,
      meta: commandMeta(),
      control_feedback: false,
    }),
  ).toThrow(SuccessorDecodeError)

  expect(() =>
    decodeSuccessorEnvelope({
      status: 'waiting',
      data: { ok: true },
      error: { code: 'unexpected', message: 'must be null', details: {} },
      meta: projectionMeta(),
      control_feedback: false,
    }),
  ).toThrow(SuccessorDecodeError)

  expect(() =>
    decodeSuccessorEnvelope({
      status: 'blocked',
      data: null,
      error: null,
      meta: projectionMeta(),
      control_feedback: false,
    }),
  ).toThrow(SuccessorDecodeError)

  expect(() =>
    decodeSuccessorEnvelope({
      status: 'conflict',
      data: { unexpected: true },
      error: { code: 'conflict_code', message: 'conflict message', details: {} },
      meta: projectionMeta(),
      control_feedback: false,
    }),
  ).toThrow(SuccessorDecodeError)
})

test('malformed status, missing/invalid meta and control feedback fail closed', () => {
  const malformed: unknown[] = [
    null,
    [],
    'ok',
    { status: 'completed', data: { ok: true }, error: null, meta: projectionMeta() },
    { status: 'ok', data: { ok: true }, error: null, meta: undefined },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: { ...projectionMeta(), project_key: '' },
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: { ...projectionMeta(), trace_id: '' },
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: { ...projectionMeta(), project_scope_ref: undefined },
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta({
        project_scope_ref: scopeRef({ scope_digest: 'not-hex' }),
      }),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta({ projection_revision: -1 }),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta({ source_digest: 'short' }),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta({ cursor: -1 }),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: { ...commandMeta(), projection_id: 'proj-1' },
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: { ...commandMeta(), command_id: undefined },
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta(),
      control_feedback: true,
    },
    {
      status: 'ok',
      data: [],
      error: null,
      meta: projectionMeta(),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta(),
      control_feedback: false,
      hidden: 1,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta(),
    },
    {
      status: 'error',
      data: null,
      error: { code: 'x', message: 'y', hidden: 1 },
      meta: projectionMeta(),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta({ hidden: 1 }),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: projectionMeta({ project_scope_ref: scopeRef({ hidden: 1 }) }),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { execute: true },
      error: null,
      meta: projectionMeta(),
      control_feedback: false,
    },
    {
      status: 'ok',
      data: { ok: true },
      error: null,
      meta: {
        project_key: 'demo',
        trace_id: 'trace-1',
        projection_id: 'proj-1',
        project_scope_ref: scopeRef(),
        projection_revision: 1,
        source_digest: DIGEST_64,
        cursor: 0,
      },
      control_feedback: false,
    },
  ]

  for (const raw of malformed) {
    expect(() => decodeSuccessorEnvelope(raw)).toThrow(SuccessorDecodeError)
  }
})

test('localStorage stores only preference and pending identity; fetch has no project authority', async () => {
  const harness = installFetchHarness(() =>
    jsonResponse(envelope('waiting', { meta: commandMeta({ command_id: 'cmd-1', trace_id: 'trace-abc' }) })),
  )
  try {
    setSuccessorProjectPreference('demo')
    await submitSuccessorCommand({
      commandId: 'cmd-1',
      commandKind: 'rebuild_projection',
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: {
        payload_kind: 'rebuild_projection',
        projection_id: 'proj-1',
        mode: 'FULL',
        ...sourceKey(),
      },
      traceId: 'trace-abc',
    })

    expect(harness.calls).toHaveLength(1)
    const call = harness.calls[0]
    expect(new URL(call.url).searchParams.has('project_key')).toBe(false)
    const headerKeys = Object.keys(call.init.headers ?? {})
    expect(headerKeys.some((key) => key.toLowerCase() === 'x-project-key')).toBe(false)

    const requestBody = JSON.parse(String(call.init.body))
    expect(Object.keys(requestBody).sort()).toEqual([
      'command_id',
      'command_kind',
      'payload',
      'project_locator',
      'trace_id',
    ])
    expect(requestBody.command_kind).toBe(requestBody.payload.payload_kind)
    expect(Object.keys(requestBody.payload).sort()).toEqual([
      'mode',
      'payload_kind',
      'projection_id',
      'projector_id',
      'projector_version',
      'source_incarnation',
      'source_kind',
      'source_ref',
    ])
    for (const forbidden of ['actor', 'scope', 'schema', 'approval', 'authority', 'execute', 'control']) {
      expect(Object.keys(requestBody).includes(forbidden)).toBe(false)
      expect(Object.keys(requestBody.payload).includes(forbidden)).toBe(false)
    }

    expect(localStorageKeys()).toEqual(
      [SUCCESSOR_PROJECT_PREFERENCE_KEY, SUCCESSOR_PENDING_COMMANDS_KEY].sort(),
    )
    expect(getSuccessorProjectPreference()).toBe('demo')

    const pending = readSuccessorPendingCommands()
    expect(pending[pendingKey('demo', 'cmd-1')]).toEqual({
      command_id: 'cmd-1',
      command_kind: 'rebuild_projection',
      project_locator: 'demo',
      endpoint: SUCCESSOR_V2_COMMAND_URL,
      payload_digest: computeSuccessorCommandFingerprint(
        SUCCESSOR_V2_COMMAND_URL,
        'demo',
        'cmd-1',
        'rebuild_projection',
        {
          payload_kind: 'rebuild_projection',
          projection_id: 'proj-1',
          mode: 'FULL',
          ...sourceKey(),
        },
      ),
    })
    expect(Object.keys(pending[pendingKey('demo', 'cmd-1')]).sort()).toEqual([
      'command_id',
      'command_kind',
      'endpoint',
      'payload_digest',
      'project_locator',
    ])
  } finally {
    harness.restore()
  }
})

test('exact retry reuses id/fingerprint; changed payload conflicts; new id dispatches', async () => {
  const responses = [
    envelope('waiting', { meta: commandMeta({ command_id: 'cmd-retry', trace_id: 'trace-retry' }) }),
    envelope('ok', { meta: commandMeta({ command_id: 'cmd-retry', trace_id: 'trace-retry' }) }),
    envelope('ok', { meta: commandMeta({ command_id: 'cmd-new', trace_id: 'trace-retry' }) }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const baseOptions = {
      commandId: 'cmd-retry',
      commandKind: 'rebuild_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      traceId: 'trace-retry',
    }

    const first = await submitSuccessorCommand({
      ...baseOptions,
      payload: {
        payload_kind: 'rebuild_projection',
        projection_id: 'proj-a',
        mode: 'FULL',
        ...sourceKey(),
      },
    })
    expect(first.status).toBe('waiting')
    expect(readSuccessorPendingCommands()[pendingKey('demo', 'cmd-retry')]).toBeDefined()
    expect(harness.calls).toHaveLength(1)

    await expect(
      submitSuccessorCommand({
        ...baseOptions,
        payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-b', ...sourceKey() },
      }),
    ).rejects.toThrow(SuccessorConflictError)
    expect(harness.calls).toHaveLength(1)

    const retried = await submitSuccessorCommand({
      ...baseOptions,
      payload: {
        payload_kind: 'rebuild_projection',
        projection_id: 'proj-a',
        mode: 'FULL',
        ...sourceKey(),
      },
    })
    expect(retried.status).toBe('ok')
    expect(harness.calls).toHaveLength(2)
    expect(readSuccessorPendingCommands()[pendingKey('demo', 'cmd-retry')]).toBeUndefined()

    const fresh = await submitSuccessorCommand({
      ...baseOptions,
      commandId: 'cmd-new',
      payload: {
        payload_kind: 'rebuild_projection',
        projection_id: 'proj-a',
        mode: 'FULL',
        ...sourceKey(),
      },
    })
    expect(fresh.status).toBe('ok')
    expect(harness.calls).toHaveLength(3)
    expect(readSuccessorPendingCommands()[pendingKey('demo', 'cmd-new')]).toBeUndefined()
    expect(JSON.parse(localStorage.getItem(SUCCESSOR_PENDING_COMMANDS_KEY) ?? '{}')).toEqual({})
  } finally {
    harness.restore()
  }
})

test('command fingerprint binds expected base token and approval locator', async () => {
  const payload = {
    payload_kind: 'rebuild_projection' as const,
    projection_id: 'proj-1',
    mode: 'FULL' as const,
    ...sourceKey(),
  }
  const base = computeSuccessorCommandFingerprint(SUCCESSOR_V2_COMMAND_URL, 'demo', 'cmd-x', 'rebuild_projection', payload)
  const boundBase = computeSuccessorCommandFingerprint(
    SUCCESSOR_V2_COMMAND_URL,
    'demo',
    'cmd-x',
    'rebuild_projection',
    payload,
    { expectedBaseToken: 'base-1' },
  )
  const boundApproval = computeSuccessorCommandFingerprint(
    SUCCESSOR_V2_COMMAND_URL,
    'demo',
    'cmd-x',
    'rebuild_projection',
    payload,
    { approvalLocator: 'approval-1' },
  )
  expect(boundBase).not.toBe(base)
  expect(boundApproval).not.toBe(base)
  expect(
    computeSuccessorCommandFingerprint(
      SUCCESSOR_V2_COMMAND_URL,
      'demo',
      'cmd-x',
      'rebuild_projection',
      payload,
      { expectedBaseToken: 'base-1' },
    ),
  ).toBe(boundBase)
})

test('changed base/approval binding with same command id conflicts while pending', async () => {
  const harness = installFetchHarness(() =>
    jsonResponse(
      envelope('waiting', { meta: commandMeta({ command_id: 'cmd-bind', trace_id: 'trace-bind' }) }),
    ),
  )
  try {
    const options = {
      commandId: 'cmd-bind',
      commandKind: 'rebuild_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: { payload_kind: 'rebuild_projection' as const, projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-bind',
    }
    const first = await submitSuccessorCommand(options)
    expect(first.status).toBe('waiting')
    expect(harness.calls).toHaveLength(1)

    await expect(submitSuccessorCommand({ ...options, expectedBaseToken: 'base-2' })).rejects.toThrow(
      SuccessorConflictError,
    )
    expect(harness.calls).toHaveLength(1)

    const retried = await submitSuccessorCommand(options)
    expect(retried.status).toBe('waiting')
    expect(harness.calls).toHaveLength(2)
  } finally {
    harness.restore()
  }
})

test('in-flight dedupe collapses double-click to one fetch', async () => {
  let release!: (response: Response) => void
  const gate = new Promise<Response>((resolve) => {
    release = resolve
  })
  const harness = installFetchHarness(() => gate)
  try {
    const options = {
      commandId: 'cmd-dedupe',
      commandKind: 'invalidate_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: { payload_kind: 'invalidate_projection', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-dedupe',
    }
    const first = submitSuccessorCommand(options)
    const second = submitSuccessorCommand(options)
    expect(harness.calls).toHaveLength(1)

    release(
      jsonResponse(
        envelope('ok', { meta: commandMeta({ command_id: 'cmd-dedupe', trace_id: 'trace-dedupe' }) }),
      ),
    )
    const results = await Promise.all([first, second])
    expect(results[0].status).toBe('ok')
    expect(results[1].status).toBe('ok')
    expect(results[0]).toBe(results[1])
    expect(harness.calls).toHaveLength(1)
  } finally {
    harness.restore()
  }
})

test('stale projection responses and scope mismatch fail closed', async () => {
  const responses = [
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 2,
      source_digest: DIGEST_64,
      cursor: 1,
    }),
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 1,
      source_digest: DIGEST_64,
      cursor: 0,
    }),
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 2,
      source_digest: DIGEST_64,
      cursor: 0,
    }),
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 2,
      source_digest: 'b'.repeat(64),
      cursor: 1,
    }),
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 3,
      offset_revision: 1,
      source_digest: DIGEST_64,
      cursor: 2,
    }),
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 4,
      offset_revision: 2,
      source_digest: DIGEST_64,
      cursor: 2,
      project_scope_ref: scopeRef({ scope_digest: 'c'.repeat(64) }),
    }),
    projectionEnvelope({
      trace_id: 'trace-q',
      projection_revision: 2,
      source_digest: DIGEST_64,
      cursor: 1,
    }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const options = {
      queryId: 'q-stale',
      queryKind: 'projection_snapshot' as const,
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot' as const, projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-q',
    }

    const fresh = await fetchSuccessorQuery(options)
    expect(fresh.meta).toMatchObject({ projection_revision: 2, cursor: 1 })

    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    const advanced = await fetchSuccessorQuery(options)
    expect(advanced.meta).toMatchObject({ projection_revision: 3, offset_revision: 1, cursor: 2 })
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorScopeError)

    resetSuccessorProjectionClock()
    const replay = await fetchSuccessorQuery(options)
    expect(replay.meta).toMatchObject({ projection_revision: 2, cursor: 1 })
  } finally {
    harness.restore()
  }
})

test('query with UNRESOLVED transport meta passes through without freshness suppression', async () => {
  const unresolvedEnvelope = {
    status: 'error' as const,
    data: null,
    error: { code: 'SCOPE_RESOLUTION_FAILED', message: 'unresolved locator', details: {} },
    meta: {
      project_key: 'demo',
      trace_id: 'trace-q',
      request_id: 'q-unresolved',
      resolution_state: 'UNRESOLVED' as const,
    },
    control_feedback: false,
  }
  const responses = [
    projectionEnvelope({ trace_id: 'trace-q', projection_revision: 2, source_digest: DIGEST_64, cursor: 1 }),
    unresolvedEnvelope,
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const options = {
      queryId: 'q-unresolved',
      queryKind: 'projection_snapshot' as const,
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot' as const, projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-q',
    }
    const fresh = await fetchSuccessorQuery(options)
    expect(fresh.meta).toMatchObject({ projection_revision: 2, cursor: 1 })
    const unresolved = await fetchSuccessorQuery(options)
    expect(unresolved.status).toBe('error')
    expect(unresolved.error?.code).toBe('SCOPE_RESOLUTION_FAILED')
    expect(unresolved.meta).toMatchObject({ resolution_state: 'UNRESOLVED', request_id: 'q-unresolved' })
  } finally {
    harness.restore()
  }
})

test('query refetch is read-only and never dispatches commands or control', async () => {
  const harness = installFetchHarness(() =>
    jsonResponse(projectionEnvelope({ trace_id: 'trace-refetch' })),
  )
  try {
    const refetch = createSuccessorQueryRefetcher({
      queryId: 'q-refetch',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: {
        params_kind: 'projection_snapshot',
        projection_id: 'proj-1',
        ...sourceKey(),
        page_size: 10,
      },
      traceId: 'trace-refetch',
    })
    const result = await refetch()
    expect(result.status).toBe('ok')
    expect(harness.calls).toHaveLength(1)

    const call = harness.calls[0]
    expect(call.init.method ?? 'POST').toBe('POST')
    expect(SUCCESSOR_V2_QUERY_URL).not.toContain('/commands')
    expect(call.url).toContain(SUCCESSOR_V2_QUERY_URL)
    expect(call.url).not.toContain('/commands')
    expect(new URL(call.url).searchParams.has('project_key')).toBe(false)

    const body = JSON.parse(String(call.init.body))
    expect(Object.keys(body).sort()).toEqual([
      'params',
      'project_locator',
      'query_id',
      'query_kind',
      'trace_id',
    ])
    expect(body.params).toEqual({
      params_kind: 'projection_snapshot',
      projection_id: 'proj-1',
      projector_id: 'projector-1',
      projector_version: 'v1',
      source_kind: 'legacy',
      source_ref: 'ref://demo/proj',
      source_incarnation: 'inc-2',
      page_size: 10,
    })
    for (const forbidden of ['execute', 'authority', 'control', 'completion']) {
      expect(Object.keys(body).includes(forbidden)).toBe(false)
    }
  } finally {
    harness.restore()
  }
})

test('request validation rejects kind mismatch and invalid params without dispatching', async () => {
  const harness = installFetchHarness(() => jsonResponse(envelope('ok')))
  try {
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-bad',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: { payload_kind: 'invalidate_projection', projection_id: 'proj-1' },
      }),
    ).rejects.toThrow(SuccessorRequestError)

    await expect(
      fetchSuccessorQuery({
        queryId: 'q-bad',
        queryKind: 'projection_events',
        projectLocator: 'demo',
        params: { params_kind: 'projection_snapshot' },
      }),
    ).rejects.toThrow(SuccessorRequestError)

    await expect(
      fetchSuccessorQuery({
        queryId: 'q-bad-2',
        queryKind: 'projection_snapshot',
        projectLocator: 'demo',
        params: {
          params_kind: 'projection_snapshot',
          projection_id: 'proj-1',
          ...sourceKey(),
          page_size: 0,
        },
      }),
    ).rejects.toThrow(SuccessorRequestError)

    await expect(
      fetchSuccessorQuery({
        queryId: 'q-bad-3',
        queryKind: 'projection_snapshot',
        projectLocator: 'demo',
        params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', page_size: 10 },
      }),
    ).rejects.toThrow(SuccessorRequestError)

    expect(harness.calls).toHaveLength(0)
  } finally {
    harness.restore()
  }
})

test('response exact-bind rejects wrong id, project, projection and source key', async () => {
  const responses = [
    envelope('ok', { meta: commandMeta({ command_id: 'other', trace_id: 'trace-x' }) }),
    envelope('ok', {
      meta: commandMeta({
        command_id: 'cmd-x',
        trace_id: 'trace-x',
        project_key: 'other',
        project_scope_ref: scopeRef({ project_key: 'other' }),
      }),
    }),
    envelope('ok', { meta: queryMeta({ query_id: 'other', trace_id: 'trace-q' }) }),
    envelope('ok', { meta: projectionMeta({ projection_id: 'other', trace_id: 'trace-q' }) }),
    envelope('ok', { meta: projectionMeta({ projector_id: 'other', trace_id: 'trace-q' }) }),
    envelope('ok', { meta: projectionMeta({ source_kind: 'other', trace_id: 'trace-q' }) }),
    envelope('ok', {
      meta: projectionMeta({
        trace_id: 'trace-q',
        project_key: 'other',
        project_scope_ref: scopeRef({ project_key: 'other' }),
      }),
    }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const commandOptions: SuccessorCommandOptions = {
      commandId: 'cmd-x',
      commandKind: 'rebuild_projection',
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-x',
    }
    await expect(submitSuccessorCommand(commandOptions)).rejects.toThrow(SuccessorBindingError)
    await expect(submitSuccessorCommand(commandOptions)).rejects.toThrow(SuccessorBindingError)

    const queryOptions: SuccessorQueryOptions = {
      queryId: 'q-x',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-q',
    }
    await expect(fetchSuccessorQuery(queryOptions)).rejects.toThrow(SuccessorBindingError)
    await expect(fetchSuccessorQuery(queryOptions)).rejects.toThrow(SuccessorBindingError)
    await expect(fetchSuccessorQuery(queryOptions)).rejects.toThrow(SuccessorBindingError)
    await expect(fetchSuccessorQuery(queryOptions)).rejects.toThrow(SuccessorBindingError)
    await expect(fetchSuccessorQuery(queryOptions)).rejects.toThrow(SuccessorBindingError)
  } finally {
    harness.restore()
  }
})

test('custom url and headers are rejected without dispatch', async () => {
  const harness = installFetchHarness(() => jsonResponse(envelope('ok')))
  try {
    const commandOptions: SuccessorCommandOptions = {
      commandId: 'cmd-u',
      commandKind: 'rebuild_projection',
      projectLocator: 'demo',
      payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-u',
    }
    await expect(
      submitSuccessorCommand({ ...commandOptions, url: 'https://evil.example/commands' } as SuccessorCommandOptions),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      submitSuccessorCommand({ ...commandOptions, headers: { Authorization: 'Bearer x' } } as SuccessorCommandOptions),
    ).rejects.toThrow(SuccessorRequestError)

    const queryOptions: SuccessorQueryOptions = {
      queryId: 'q-u',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-q',
    }
    await expect(
      fetchSuccessorQuery({ ...queryOptions, url: 'https://evil.example/queries' } as SuccessorQueryOptions),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      fetchSuccessorQuery({ ...queryOptions, headers: { 'X-Custom': '1' } } as SuccessorQueryOptions),
    ).rejects.toThrow(SuccessorRequestError)
    expect(harness.calls).toHaveLength(0)
  } finally {
    harness.restore()
  }
})

test('payload and params reject control and unknown fields', async () => {
  const harness = installFetchHarness(() => jsonResponse(envelope('ok')))
  try {
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-p',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: {
          payload_kind: 'rebuild_projection',
          projection_id: 'proj-1',
          execute: true,
          ...sourceKey(),
        },
      }),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-p2',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: {
          payload_kind: 'rebuild_projection',
          projection_id: 'proj-1',
          hidden: 1,
          ...sourceKey(),
        },
      }),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      fetchSuccessorQuery({
        queryId: 'q-p',
        queryKind: 'projection_snapshot',
        projectLocator: 'demo',
        params: {
          params_kind: 'projection_snapshot',
          projection_id: 'proj-1',
          actor: 'user-1',
          ...sourceKey(),
        },
      }),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      fetchSuccessorQuery({
        queryId: 'q-p2',
        queryKind: 'projection_snapshot',
        projectLocator: 'demo',
        params: {
          params_kind: 'projection_snapshot',
          projection_id: 'proj-1',
          hidden: 1,
          ...sourceKey(),
        },
      }),
    ).rejects.toThrow(SuccessorRequestError)
    expect(harness.calls).toHaveLength(0)
  } finally {
    harness.restore()
  }
})

test('cross-project same command id does not dedupe or conflict', async () => {
  const responses = [
    envelope('waiting', {
      meta: commandMeta({
        command_id: 'cmd-cross',
        trace_id: 'trace-a',
        project_key: 'alpha',
        project_scope_ref: scopeRef({ project_key: 'alpha' }),
      }),
    }),
    envelope('waiting', {
      meta: commandMeta({
        command_id: 'cmd-cross',
        trace_id: 'trace-b',
        project_key: 'beta',
        project_scope_ref: scopeRef({ project_key: 'beta' }),
      }),
    }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const payload = {
      payload_kind: 'rebuild_projection' as const,
      projection_id: 'proj-1',
      ...sourceKey(),
    }
    const alpha = submitSuccessorCommand({
      commandId: 'cmd-cross',
      commandKind: 'rebuild_projection',
      projectLocator: 'alpha',
      actorRef: 'actor-1',
      payload,
      traceId: 'trace-a',
    })
    const beta = submitSuccessorCommand({
      commandId: 'cmd-cross',
      commandKind: 'rebuild_projection',
      projectLocator: 'beta',
      actorRef: 'actor-1',
      payload,
      traceId: 'trace-b',
    })
    expect(harness.calls).toHaveLength(2)

    const results = await Promise.all([alpha, beta])
    expect(results[0].status).toBe('waiting')
    expect(results[1].status).toBe('waiting')
    expect(results[0]).not.toBe(results[1])
    expect(readSuccessorPendingCommands()[pendingKey('alpha', 'cmd-cross')]).toBeDefined()
    expect(readSuccessorPendingCommands()[pendingKey('beta', 'cmd-cross')]).toBeDefined()
  } finally {
    harness.restore()
  }
})

test('projection clock enforces the partial order across cursor, digest, position and offset revision', async () => {
  const responses = [
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 5, projection_revision: 2, source_digest: DIGEST_64, cursor: 1 }, 'ok', { offsetRef: 'ref-1' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 2, offset_revision: 7, projection_revision: 3, source_digest: DIGEST_64, cursor: 0 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 6, projection_revision: 2, source_digest: 'b'.repeat(64), cursor: 1 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 0, offset_revision: 7, projection_revision: 3, source_digest: DIGEST_64, cursor: 2 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 7, projection_revision: 1, source_digest: DIGEST_64, cursor: 2 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 4, projection_revision: 3, source_digest: DIGEST_64, cursor: 2 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 2, offset_revision: 5, projection_revision: 3, source_digest: DIGEST_64, cursor: 2 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 6, projection_revision: 2, source_digest: DIGEST_64, cursor: 1 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 6, projection_revision: 2, source_digest: DIGEST_64, cursor: 1 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 7, projection_revision: 2, source_digest: DIGEST_64, cursor: 2 }, 'ok', { offsetRef: 'ref-2' }),
    projectionEnvelope({ trace_id: 'trace-clock', projection_generation: 1, offset_revision: 7, projection_revision: 2, source_digest: DIGEST_64, cursor: 3 }, 'ok', { offsetRef: 'ref-2' }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const options: SuccessorQueryOptions = {
      queryId: 'q-clock',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-clock',
    }
    const fresh = await fetchSuccessorQuery(options)
    expect(fresh.meta).toMatchObject({ projection_generation: 1, offset_revision: 5, cursor: 1 })

    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
    const offsetAdvanced = await fetchSuccessorQuery(options)
    expect(offsetAdvanced.meta).toMatchObject({ projection_generation: 1, offset_revision: 6, cursor: 1 })
    const identical = await fetchSuccessorQuery(options)
    expect(identical.meta).toMatchObject({ projection_generation: 1, offset_revision: 6, cursor: 1 })
    const cursorAdvanced = await fetchSuccessorQuery(options)
    expect(cursorAdvanced.meta).toMatchObject({ projection_generation: 1, offset_revision: 7, cursor: 2 })
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorStaleError)
  } finally {
    harness.restore()
  }
})

test('response trace and unresolved request identity exact-bind', async () => {
  const responses = [
    envelope('waiting', { meta: commandMeta({ command_id: 'cmd-t', trace_id: 'other' }) }),
    {
      status: 'error' as const,
      data: null,
      error: { code: 'SCOPE_RESOLUTION_FAILED', message: 'unresolved', details: {} },
      meta: {
        project_key: 'demo',
        trace_id: 'trace-t',
        request_id: 'other',
        resolution_state: 'UNRESOLVED' as const,
      },
      control_feedback: false,
    },
    projectionEnvelope({ trace_id: 'other' }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const commandOptions: SuccessorCommandOptions = {
      commandId: 'cmd-t',
      commandKind: 'rebuild_projection',
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-t',
    }
    await expect(submitSuccessorCommand(commandOptions)).rejects.toThrow(SuccessorBindingError)
    await expect(submitSuccessorCommand(commandOptions)).rejects.toThrow(SuccessorBindingError)

    const queryOptions: SuccessorQueryOptions = {
      queryId: 'q-t',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-t',
    }
    await expect(fetchSuccessorQuery(queryOptions)).rejects.toThrow(SuccessorBindingError)
  } finally {
    harness.restore()
  }
})

test('query meta bypass is rejected for ok/waiting and allowed only for error-family', async () => {
  const responses = [
    envelope('ok', { meta: queryMeta({ query_id: 'q-m', trace_id: 'trace-q' }) }),
    envelope('error', { meta: queryMeta({ query_id: 'q-m', trace_id: 'trace-q' }) }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const options: SuccessorQueryOptions = {
      queryId: 'q-m',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-q',
    }
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorDecodeError)
    const errorFamily = await fetchSuccessorQuery(options)
    expect(errorFamily.status).toBe('error')
    expect('query_id' in errorFamily.meta).toBe(true)
  } finally {
    harness.restore()
  }
})

test('projection snapshot data must exact-match meta', async () => {
  const meta = projectionMeta({
    trace_id: 'trace-d',
    projection_generation: 1,
    offset_revision: 5,
    projection_revision: 2,
    cursor: 1,
  })
  assertSuccessorProjectionSnapshotData(meta, projectionData(meta, 'ref-d'))

  const responses = [
    envelope('ok', { meta: projectionMeta({ trace_id: 'trace-d' }), data: { ok: true } }),
    envelope('ok', {
      meta: projectionMeta({ trace_id: 'trace-d' }),
      data: { ...projectionData(projectionMeta({ trace_id: 'trace-d' }), 'ref-d'), projector_id: 'other' },
    }),
    envelope('ok', {
      meta: projectionMeta({ trace_id: 'trace-d' }),
      data: { ...projectionData(projectionMeta({ trace_id: 'trace-d' }), 'ref-d'), projection_generation: 9 },
    }),
    envelope('ok', {
      meta: projectionMeta({ trace_id: 'trace-d' }),
      data: { ...projectionData(projectionMeta({ trace_id: 'trace-d' }), '') },
    }),
    envelope('ok', {
      meta: projectionMeta({ trace_id: 'trace-d' }),
      data: { ...projectionData(projectionMeta({ trace_id: 'trace-d' }), 'ref-d'), hidden: 1 },
    }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const options: SuccessorQueryOptions = {
      queryId: 'q-d',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-d',
    }
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorDecodeError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorDecodeError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorDecodeError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorDecodeError)
    await expect(fetchSuccessorQuery(options)).rejects.toThrow(SuccessorDecodeError)
  } finally {
    harness.restore()
  }
})

test('backend serialized fixture decodes with typed candidate values', async () => {
  const fixture = {
    status: 'ok',
    data: {
      projection_id: 'proj-1',
      projector_id: 'projector-1',
      projector_version: 'v1',
      source_kind: 'legacy',
      source_ref: 'ref://demo/proj',
      source_incarnation: 'inc-2',
      projection_generation: 3,
      offset_revision: 7,
      projection_revision: 5,
      source_digest: DIGEST_64,
      cursor: 9,
      offset_ref: 'offset-ref-9',
      candidate_values: [
        {
          value_id: 'value-1',
          value_ref: 'project-value:value-1',
          content_digest: DIGEST_64,
          byte_size: 128,
          sink: 'postgres',
          payload: { rows: 1 },
        },
      ],
    },
    error: null,
    meta: {
      project_key: 'demo',
      trace_id: 'trace-fixture',
      projection_id: 'proj-1',
      project_scope_ref: {
        project_key: 'demo',
        resolved_schema: 'public',
        project_registry_revision: 1,
        incarnation: 'inc-1',
        scope_digest: DIGEST_64,
      },
      projector_id: 'projector-1',
      projector_version: 'v1',
      source_kind: 'legacy',
      source_ref: 'ref://demo/proj',
      source_incarnation: 'inc-2',
      projection_generation: 3,
      offset_revision: 7,
      projection_revision: 5,
      source_digest: DIGEST_64,
      cursor: 9,
    },
    control_feedback: false,
  }
  const harness = installFetchHarness(() => jsonResponse(fixture))
  try {
    const result = await fetchSuccessorQuery({
      queryId: 'q-fixture',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-fixture',
    })
    expect(result.status).toBe('ok')
    expect(result.meta).toMatchObject({ projection_generation: 3, offset_revision: 7, cursor: 9 })
    const data = assertSuccessorProjectionSnapshotData(result.meta as SuccessorProjectionMeta, result.data)
    expect(data.offset_ref).toBe('offset-ref-9')
    expect(data.candidate_values).toEqual([
      {
        value_id: 'value-1',
        value_ref: 'project-value:value-1',
        content_digest: DIGEST_64,
        byte_size: 128,
        sink: 'postgres',
        payload: { rows: 1 },
      },
    ])
  } finally {
    harness.restore()
  }
})

test('candidate values decode strictly and unknown fields fail closed', async () => {
  const meta = projectionMeta({ trace_id: 'trace-cv', projection_generation: 1, offset_revision: 0 })
  const good = {
    value_id: 'v1',
    value_ref: 'project-value:v1',
    content_digest: DIGEST_64,
    byte_size: 8,
    sink: 'postgres',
    payload: { rows: 2 },
  }
  assertSuccessorProjectionSnapshotData(meta, projectionData(meta, 'ref-cv', [good]))

  const badCandidates = [
    { ...good, value_id: '' },
    { ...good, value_ref: '' },
    { ...good, content_digest: 'short' },
    { ...good, byte_size: -1 },
    { ...good, byte_size: 1.5 },
    { ...good, hidden: 1 },
    { ...good, sink: '' },
    { ...good, payload: 'not-object' },
    { ...good, payload: { rows: 1, execute: true } },
  ]
  for (const candidate of badCandidates) {
    expect(() =>
      assertSuccessorProjectionSnapshotData(meta, projectionData(meta, 'ref-cv', [candidate])),
    ).toThrow(SuccessorDecodeError)
  }
  expect(() =>
    assertSuccessorProjectionSnapshotData(meta, projectionData(meta, 'ref-cv', 'not-array' as never)),
  ).toThrow(SuccessorDecodeError)
})

test('unknown discriminator fails before localStorage or fetch', async () => {
  const harness = installFetchHarness(() => jsonResponse(envelope('ok')))
  try {
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-unknown',
        commandKind: 'evil' as never,
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      }),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      fetchSuccessorQuery({
        queryId: 'q-unknown',
        queryKind: 'evil' as never,
        projectLocator: 'demo',
        params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      }),
    ).rejects.toThrow(SuccessorRequestError)
    expect(harness.calls).toHaveLength(0)
    expect(localStorage.getItem(SUCCESSOR_PENDING_COMMANDS_KEY)).toBeNull()
  } finally {
    harness.restore()
  }
})

test('poisoned pending store fails closed before fetch', async () => {
  localStorage.setItem(
    SUCCESSOR_PENDING_COMMANDS_KEY,
    JSON.stringify({
      [pendingKey('demo', 'cmd-p')]: {
        command_id: 'cmd-p',
        command_kind: 'evil',
        project_locator: 'demo',
        endpoint: SUCCESSOR_V2_COMMAND_URL,
        payload_digest: DIGEST_64,
      },
      [pendingKey('demo', 'cmd-q')]: {
        command_id: 'cmd-q',
        command_kind: 'rebuild_projection',
        project_locator: 'demo',
        endpoint: SUCCESSOR_V2_COMMAND_URL,
        payload_digest: DIGEST_64,
        authority: 'smuggled',
      },
    }),
  )
  const harness = installFetchHarness(() => jsonResponse(envelope('ok')))
  try {
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-p',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      }),
    ).rejects.toThrow(SuccessorRuntimeError)
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-q',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      }),
    ).rejects.toThrow(SuccessorRuntimeError)
    expect(harness.calls).toHaveLength(0)
  } finally {
    harness.restore()
  }
})

test('composite keys are collision-free under colon ambiguity', async () => {
  const responses = [
    projectionEnvelope({
      trace_id: 'trace-c',
      project_key: 'a:b',
      project_scope_ref: scopeRef({ project_key: 'a:b' }),
      projection_id: 'proj',
      projection_revision: 2,
      cursor: 1,
    }),
    projectionEnvelope({
      trace_id: 'trace-c',
      project_key: 'a',
      project_scope_ref: scopeRef({ project_key: 'a' }),
      projection_id: 'b:proj',
      projection_revision: 1,
      cursor: 0,
    }),
    envelope('waiting', {
      meta: commandMeta({
        command_id: 'x',
        trace_id: 'trace-p',
        project_key: 'a:b',
        project_scope_ref: scopeRef({ project_key: 'a:b' }),
      }),
    }),
    envelope('waiting', {
      meta: commandMeta({
        command_id: 'b:x',
        trace_id: 'trace-p',
        project_key: 'a',
        project_scope_ref: scopeRef({ project_key: 'a' }),
      }),
    }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const optionsA: SuccessorQueryOptions = {
      queryId: 'q-c',
      queryKind: 'projection_snapshot',
      projectLocator: 'a:b',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj', ...sourceKey() },
      traceId: 'trace-c',
    }
    const optionsB: SuccessorQueryOptions = {
      queryId: 'q-c',
      queryKind: 'projection_snapshot',
      projectLocator: 'a',
      params: { params_kind: 'projection_snapshot', projection_id: 'b:proj', ...sourceKey() },
      traceId: 'trace-c',
    }
    const first = await fetchSuccessorQuery(optionsA)
    expect(first.meta).toMatchObject({ projection_id: 'proj', projection_revision: 2 })
    const second = await fetchSuccessorQuery(optionsB)
    expect(second.meta).toMatchObject({ projection_id: 'b:proj', projection_revision: 1 })

    const payload = {
      payload_kind: 'rebuild_projection' as const,
      projection_id: 'proj-1',
      ...sourceKey(),
    }
    await submitSuccessorCommand({
      commandId: 'x',
      commandKind: 'rebuild_projection',
      projectLocator: 'a:b',
      actorRef: 'actor-1',
      payload,
      traceId: 'trace-p',
    })
    await submitSuccessorCommand({
      commandId: 'b:x',
      commandKind: 'rebuild_projection',
      projectLocator: 'a',
      actorRef: 'actor-1',
      payload,
      traceId: 'trace-p',
    })
    expect(readSuccessorPendingCommands()[pendingKey('a:b', 'x')]).toBeDefined()
    expect(readSuccessorPendingCommands()[pendingKey('a', 'b:x')]).toBeDefined()
    expect(pendingKey('a:b', 'x')).not.toBe(pendingKey('a', 'b:x'))
  } finally {
    harness.restore()
  }
})

test('explicit empty trace is rejected before storage or fetch', async () => {
  const harness = installFetchHarness(() => jsonResponse(envelope('ok')))
  try {
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-et',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        actorRef: 'actor-1',
        payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
        traceId: '   ',
      }),
    ).rejects.toThrow(SuccessorRequestError)
    await expect(
      fetchSuccessorQuery({
        queryId: 'q-et',
        queryKind: 'projection_snapshot',
        projectLocator: 'demo',
        params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
        traceId: '   ',
      }),
    ).rejects.toThrow(SuccessorRequestError)
    expect(harness.calls).toHaveLength(0)
    expect(localStorage.getItem(SUCCESSOR_PENDING_COMMANDS_KEY)).toBeNull()
  } finally {
    harness.restore()
  }
})

test('explicit trace mismatch while in flight conflicts without a second fetch', async () => {
  let release!: (response: Response) => void
  const gate = new Promise<Response>((resolve) => {
    release = resolve
  })
  const harness = installFetchHarness(() => gate)
  try {
    const options = {
      commandId: 'cmd-tt',
      commandKind: 'rebuild_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: { payload_kind: 'rebuild_projection' as const, projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-tt-1',
    }
    const first = submitSuccessorCommand(options)
    expect(harness.calls).toHaveLength(1)

    await expect(submitSuccessorCommand({ ...options, traceId: 'trace-tt-2' })).rejects.toThrow(
      SuccessorConflictError,
    )
    expect(harness.calls).toHaveLength(1)

    release(
      jsonResponse(
        envelope('waiting', {
          meta: commandMeta({ command_id: 'cmd-tt', trace_id: 'trace-tt-1' }),
        }),
      ),
    )
    const result = await first
    expect(result.status).toBe('waiting')
  } finally {
    harness.restore()
  }
})

test('second caller without explicit trace joins the in-flight command', async () => {
  let release!: (response: Response) => void
  const gate = new Promise<Response>((resolve) => {
    release = resolve
  })
  const harness = installFetchHarness(() => gate)
  try {
    const options = {
      commandId: 'cmd-join',
      commandKind: 'rebuild_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: { payload_kind: 'rebuild_projection' as const, projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-join-1',
    }
    const first = submitSuccessorCommand(options)
    const joined = submitSuccessorCommand({ ...options, traceId: undefined })
    expect(harness.calls).toHaveLength(1)

    release(
      jsonResponse(
        envelope('waiting', {
          meta: commandMeta({ command_id: 'cmd-join', trace_id: 'trace-join-1' }),
        }),
      ),
    )
    const results = await Promise.all([first, joined])
    expect(results[0]).toBe(results[1])
    expect(results[1].status).toBe('waiting')
    expect(harness.calls).toHaveLength(1)
  } finally {
    harness.restore()
  }
})

test('rollback command payload allowlist and pending identity', async () => {
  const harness = installFetchHarness(() =>
    jsonResponse(
      envelope('waiting', { meta: commandMeta({ command_id: 'cmd-rb', trace_id: 'trace-rb' }) }),
    ),
  )
  try {
    await submitSuccessorCommand({
      commandId: 'cmd-rb',
      commandKind: 'rollback_projection',
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: rollbackPayload(),
      traceId: 'trace-rb',
    })
    expect(harness.calls).toHaveLength(1)
    const body = JSON.parse(String(harness.calls[0].init.body))
    expect(body.command_kind).toBe('rollback_projection')
    expect(body.payload.payload_kind).toBe('rollback_projection')
    expect(Object.keys(body.payload).sort()).toEqual([
      'expected_active_generation',
      'expected_offset_revision',
      'payload_kind',
      'projection_id',
      'projector_id',
      'projector_version',
      'source_incarnation',
      'source_kind',
      'source_ref',
      'target_generation',
    ])
    for (const forbidden of ['actor', 'scope', 'schema', 'approval', 'authority', 'execute', 'control']) {
      expect(Object.keys(body.payload).includes(forbidden)).toBe(false)
    }
    expect(readSuccessorPendingCommands()[pendingKey('demo', 'cmd-rb')]).toMatchObject({
      command_id: 'cmd-rb',
      command_kind: 'rollback_projection',
      project_locator: 'demo',
      endpoint: SUCCESSOR_V2_COMMAND_URL,
    })
  } finally {
    harness.restore()
  }
})

test('rollback duplicate click is one fetch and changed intent conflicts', async () => {
  let release!: (response: Response) => void
  const gate = new Promise<Response>((resolve) => {
    release = resolve
  })
  const harness = installFetchHarness(() => gate)
  try {
    const options = {
      commandId: 'cmd-rb2',
      commandKind: 'rollback_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: rollbackPayload(),
      traceId: 'trace-rb2',
    }
    const first = submitSuccessorCommand(options)
    const second = submitSuccessorCommand(options)
    expect(harness.calls).toHaveLength(1)

    await expect(
      submitSuccessorCommand({ ...options, payload: rollbackPayload({ target_generation: 2 }) }),
    ).rejects.toThrow(SuccessorConflictError)
    expect(harness.calls).toHaveLength(1)

    release(
      jsonResponse(
        envelope('waiting', { meta: commandMeta({ command_id: 'cmd-rb2', trace_id: 'trace-rb2' }) }),
      ),
    )
    const results = await Promise.all([first, second])
    expect(results[0]).toBe(results[1])
    expect(results[1].status).toBe('waiting')
    expect(harness.calls).toHaveLength(1)
  } finally {
    harness.restore()
  }
})

test('rollback transition receipt decodes strictly from backend fixture', () => {
  const receipt = rollbackReceipt()
  const decoded = decodeSuccessorRollbackTransitionReceipt(receipt)
  expect(decoded.contract).toBe('C9RollbackTransitionReceipt.v1')
  expect(decoded.ref).toBe('rollback-1')
  expect(decoded.digest).toBe(computeSuccessorRollbackReceiptDigest(receipt))
  expect(decoded.digest).toBe('a179e8bb0430aaab5fe6e443f6d58d06d17dcf5a2101ba4081e48c8b7dbe4b60')
  expect(decoded.from).toEqual(receipt.from)
  expect(decoded.to).toEqual(receipt.to)
  expect(decoded.projection_id).toBe('proj-1')
  expect(decoded.projector_id).toBe('projector-1')
  expect(decoded.source_kind).toBe('legacy')
  expect(decoded.source_ref).toBe('ref://demo/proj')
  expect(decoded.generation_completeness_digest).toBe(DIGEST_64)

  expect(() => decodeSuccessorRollbackTransitionReceipt({ ...receipt, hidden: 1 })).toThrow(
    SuccessorDecodeError,
  )
  expect(() =>
    decodeSuccessorRollbackTransitionReceipt({ ...receipt, from: { ...receipt.from, extra: 1 } }),
  ).toThrow(SuccessorDecodeError)
  expect(() => decodeSuccessorRollbackTransitionReceipt({ ...receipt, digest: 'short' })).toThrow(
    SuccessorDecodeError,
  )
  expect(() => decodeSuccessorRollbackTransitionReceipt({ ...receipt, ref: '' })).toThrow(
    SuccessorDecodeError,
  )
  expect(() =>
    decodeSuccessorRollbackTransitionReceipt({ ...receipt, to: { ...receipt.to, offset_ref: '' } }),
  ).toThrow(SuccessorDecodeError)
  expect(() =>
    decodeSuccessorRollbackTransitionReceipt({ ...receipt, from: { ...receipt.from, offset_ref: '  ' } }),
  ).toThrow(SuccessorDecodeError)
  const withoutContract = { ...receipt }
  delete (withoutContract as { contract?: string }).contract
  expect(() => decodeSuccessorRollbackTransitionReceipt(withoutContract)).toThrow(SuccessorDecodeError)
  expect(() =>
    decodeSuccessorRollbackTransitionReceipt({ ...receipt, contract: 'WrongContract.v1' }),
  ).toThrow(SuccessorDecodeError)
})

test('sanctioned rollback transitions the projection clock with a valid receipt', async () => {
  const target = position()
  const receipt = rollbackReceipt({
    from: position({ projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 }),
    to: target,
  })
  const responses = [
    projectionEnvelope(
      { trace_id: 'trace-rbq', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
      'ok',
      { offsetRef: 'ref-active' },
    ),
    rollbackSnapshotEnvelope(receipt, {}, 'ref-active', 'trace-rbq'),
    projectionEnvelope(
      { trace_id: 'trace-rbq', projection_generation: 3, offset_revision: 8, projection_revision: 5, cursor: 7 },
      'ok',
      { offsetRef: 'ref-active' },
    ),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rbq',
    }
    const active = await fetchSuccessorQuery(snapshotOptions)
    expect(active.meta).toMatchObject({ projection_generation: 4, cursor: 8 })
    const transition = await fetchSuccessorQuery(snapshotOptions)
    expect(transition.status).toBe('ok')
    const afterRollback = await fetchSuccessorQuery(snapshotOptions)
    expect(afterRollback.meta).toMatchObject({ projection_generation: 3, offset_revision: 8, cursor: 7 })
  } finally {
    harness.restore()
  }
})

test('unsanctioned rollback transitions fail closed', async () => {
  const target = position({ offset_ref: 'ref-u' })
  const activeSnapshot = projectionEnvelope(
    { trace_id: 'trace-rbu', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
    'ok',
    { offsetRef: 'ref-u' },
  )
  const goodFrom = position({
    projection_generation: 4,
    offset_revision: 7,
    projection_revision: 6,
    cursor: 8,
    offset_ref: 'ref-u',
  })
  const receipt = rollbackReceipt({ from: goodFrom, to: target })
  const transitionEnvelope = (
    dataReceipt: SuccessorRollbackTransitionReceipt,
    metaOverrides: Record<string, unknown> = {},
  ) => rollbackSnapshotEnvelope(dataReceipt, metaOverrides, 'ref-u', 'trace-rbu')
  const responses = [
    transitionEnvelope(receipt),
    activeSnapshot,
    transitionEnvelope(rollbackReceipt({ from: goodFrom, to: { ...target, offset_revision: 7 } }), {
      offset_revision: 7,
    }),
    transitionEnvelope(receipt, {
      project_scope_ref: scopeRef({ scope_digest: 'c'.repeat(64) }),
    }),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-u',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rbu',
    }
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
    const active = await fetchSuccessorQuery(snapshotOptions)
    expect(active.meta).toMatchObject({ projection_generation: 4, cursor: 8 })
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorScopeError)
  } finally {
    harness.restore()
  }
})

test('same rollback transition repeat is idempotent and refetch does not mutate clock', async () => {
  const target = position({ offset_ref: 'ref-r' })
  const receipt = rollbackReceipt({
    from: position({
      projection_generation: 4,
      offset_revision: 7,
      projection_revision: 6,
      cursor: 8,
      offset_ref: 'ref-r',
    }),
    to: target,
  })
  const transition = rollbackSnapshotEnvelope(receipt, {}, 'ref-r', 'trace-rbr')
  const responses = [
    projectionEnvelope(
      { trace_id: 'trace-rbr', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
      'ok',
      { offsetRef: 'ref-r' },
    ),
    transition,
    transition,
    projectionEnvelope(
      { trace_id: 'trace-rbr', projection_generation: 3, offset_revision: 8, projection_revision: 5, cursor: 7 },
      'ok',
      { offsetRef: 'ref-r' },
    ),
    projectionEnvelope(
      { trace_id: 'trace-rbr', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
      'ok',
      { offsetRef: 'ref-r' },
    ),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-r',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rbr',
    }
    await fetchSuccessorQuery(snapshotOptions)
    const first = await fetchSuccessorQuery(snapshotOptions)
    expect(first.status).toBe('ok')
    const refetched = await createSuccessorQueryRefetcher(snapshotOptions)()
    expect(refetched.status).toBe('ok')
    const rolledBackSnapshot = await fetchSuccessorQuery(snapshotOptions)
    expect(rolledBackSnapshot.meta).toMatchObject({ projection_generation: 3, cursor: 7 })
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
  } finally {
    harness.restore()
  }
})

test('rollback command is observed only through projection_snapshot refetch', async () => {
  const target = position({ offset_ref: 'ref-o' })
  const receipt = rollbackReceipt({
    from: position({
      projection_generation: 4,
      offset_revision: 7,
      projection_revision: 6,
      cursor: 8,
      offset_ref: 'ref-o',
    }),
    to: target,
  })
  const responses = [
    envelope('waiting', {
      meta: commandMeta({ command_id: 'cmd-rb-ob', trace_id: 'trace-rbo2' }),
    }),
    projectionEnvelope(
      { trace_id: 'trace-rbo2', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
      'ok',
      { offsetRef: 'ref-o' },
    ),
    rollbackSnapshotEnvelope(receipt, {}, 'ref-o', 'trace-rbo2'),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    await submitSuccessorCommand({
      commandId: 'cmd-rb-ob',
      commandKind: 'rollback_projection',
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: rollbackPayload(),
      traceId: 'trace-rbo2',
    })
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-o',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rbo2',
    }
    await fetchSuccessorQuery(snapshotOptions)
    const transition = await createSuccessorQueryRefetcher(snapshotOptions)()
    expect(transition.status).toBe('ok')
    expect(harness.calls).toHaveLength(3)
    expect(harness.calls[0].url).toContain('/commands')
    for (const call of harness.calls.slice(1)) {
      expect(call.url).toContain(SUCCESSOR_V2_QUERY_URL)
      expect(call.url).not.toContain('/commands')
    }
  } finally {
    harness.restore()
  }
})

test('rollback receipt tampering fails canonical digest recomputation', async () => {
  const active = projectionEnvelope(
    { trace_id: 'trace-tamper', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
    'ok',
    { offsetRef: 'ref-t' },
  )
  const target = position({ offset_ref: 'ref-t' })
  const goodFrom = position({
    projection_generation: 4,
    offset_revision: 7,
    projection_revision: 6,
    cursor: 8,
    offset_ref: 'ref-t',
  })
  const goodReceipt = rollbackReceipt({ from: goodFrom, to: target })
  const badReceipts = [
    { ...goodReceipt, digest: 'b'.repeat(64) },
    { ...goodReceipt, ref: 'other' },
    { ...goodReceipt, generation_completeness_digest: 'c'.repeat(64) },
    { ...goodReceipt, to: { ...goodReceipt.to, offset_ref: 'other' } },
    rollbackReceipt({ from: { ...goodFrom, source_digest: 'b'.repeat(64) }, to: target }),
    rollbackReceipt({ from: goodFrom, to: position({ projection_generation: 2, offset_revision: 9, projection_revision: 4, cursor: 6, offset_ref: 'ref-t' }) }),
  ]
  const responses = [
    active,
    ...badReceipts.map((receipt) =>
      rollbackSnapshotEnvelope(receipt, {}, 'ref-t', 'trace-tamper'),
    ),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-t',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-tamper',
    }
    await fetchSuccessorQuery(snapshotOptions)
    for (let index = 0; index < badReceipts.length; index += 1) {
      await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
    }
  } finally {
    harness.restore()
  }
})

test('rollback and other command kinds cannot reuse the same pending id', async () => {
  const harness = installFetchHarness(() =>
    jsonResponse(
      envelope('waiting', { meta: commandMeta({ command_id: 'cmd-k', trace_id: 'trace-k' }) }),
    ),
  )
  try {
    const rollback = {
      commandId: 'cmd-k',
      commandKind: 'rollback_projection' as const,
      projectLocator: 'demo',
      actorRef: 'actor-1',
      payload: rollbackPayload(),
      traceId: 'trace-k',
    }
    const first = await submitSuccessorCommand(rollback)
    expect(first.status).toBe('waiting')
    await expect(
      submitSuccessorCommand({
        ...rollback,
        commandKind: 'rebuild_projection',
        payload: { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
      }),
    ).rejects.toThrow(SuccessorConflictError)
    expect(harness.calls).toHaveLength(1)

    const rollbackDigest = computeSuccessorCommandFingerprint(
      SUCCESSOR_V2_COMMAND_URL,
      'demo',
      'cmd-k',
      'rollback_projection',
      rollbackPayload(),
    )
    const rebuildDigest = computeSuccessorCommandFingerprint(
      SUCCESSOR_V2_COMMAND_URL,
      'demo',
      'cmd-k',
      'rebuild_projection',
      { payload_kind: 'rebuild_projection', projection_id: 'proj-1', ...sourceKey() },
    )
    expect(rollbackDigest).not.toBe(rebuildDigest)
  } finally {
    harness.restore()
  }
})

test('rollback to.offset_ref comes from the receipt and binds the new clock', async () => {
  const target = position({ offset_ref: 'ref-b' })
  const receipt = rollbackReceipt({
    from: position({
      projection_generation: 4,
      offset_revision: 7,
      projection_revision: 6,
      cursor: 8,
      offset_ref: 'ref-a',
    }),
    to: target,
  })
  const responses = [
    projectionEnvelope(
      { trace_id: 'trace-rbo', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
      'ok',
      { offsetRef: 'ref-a' },
    ),
    rollbackSnapshotEnvelope(receipt, {}, 'ref-b', 'trace-rbo'),
    projectionEnvelope(
      { trace_id: 'trace-rbo', projection_generation: 3, offset_revision: 8, projection_revision: 5, cursor: 7 },
      'ok',
      { offsetRef: 'ref-b' },
    ),
    projectionEnvelope(
      { trace_id: 'trace-rbo', projection_generation: 3, offset_revision: 8, projection_revision: 5, cursor: 7 },
      'ok',
      { offsetRef: 'ref-a' },
    ),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-bo',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rbo',
    }
    const active = await fetchSuccessorQuery(snapshotOptions)
    expect(active.meta).toMatchObject({ projection_generation: 4, cursor: 8 })
    const transition = await fetchSuccessorQuery(snapshotOptions)
    expect(transition.status).toBe('ok')
    const boundSnapshot = await fetchSuccessorQuery(snapshotOptions)
    expect(boundSnapshot.meta).toMatchObject({ projection_generation: 3, cursor: 7 })
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
  } finally {
    harness.restore()
  }
})

test('rollback from.offset_ref must exact-bind the prior clock', async () => {
  const active = projectionEnvelope(
    { trace_id: 'trace-rbf', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
    'ok',
    { offsetRef: 'ref-a' },
  )
  const receipt = rollbackReceipt({
    from: position({
      projection_generation: 4,
      offset_revision: 7,
      projection_revision: 6,
      cursor: 8,
      offset_ref: 'other',
    }),
    to: position({ offset_ref: 'ref-b' }),
  })
  const responses = [
    active,
    rollbackSnapshotEnvelope(receipt, {}, 'ref-b', 'trace-rbf'),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-bf',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rbf',
    }
    await fetchSuccessorQuery(snapshotOptions)
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
  } finally {
    harness.restore()
  }
})

test('new rollback receipts bind the current clock; exact retry of the same receipt is idempotent', async () => {
  const positionA = position({
    projection_generation: 4,
    offset_revision: 7,
    projection_revision: 6,
    cursor: 8,
    offset_ref: 'ref-a',
  })
  const positionB = position({
    projection_generation: 3,
    offset_revision: 8,
    projection_revision: 5,
    cursor: 7,
    offset_ref: 'ref-a',
  })
  const positionC = position({
    projection_generation: 2,
    offset_revision: 9,
    projection_revision: 4,
    cursor: 6,
    offset_ref: 'ref-a',
  })
  const receiptOne = rollbackReceipt({ from: positionA, to: positionB })
  const receiptTwo = rollbackReceipt({ from: positionB, to: positionC })
  const staleFrom = position({
    projection_generation: 4,
    offset_revision: 6,
    projection_revision: 6,
    cursor: 8,
    offset_ref: 'ref-a',
  })
  const receiptStale = rollbackReceipt({
    from: staleFrom,
    to: position({ projection_generation: 1, offset_revision: 10, projection_revision: 3, cursor: 5, offset_ref: 'ref-a' }),
  })
  const responses = [
    projectionEnvelope(
      { trace_id: 'trace-aba', projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8 },
      'ok',
      { offsetRef: 'ref-a' },
    ),
    rollbackSnapshotEnvelope(receiptOne, {}, 'ref-a', 'trace-aba'),
    rollbackSnapshotEnvelope(receiptOne, {}, 'ref-a', 'trace-aba'),
    rollbackSnapshotEnvelope(receiptTwo, {}, 'ref-a', 'trace-aba'),
    rollbackSnapshotEnvelope(receiptStale, {}, 'ref-a', 'trace-aba'),
    projectionEnvelope(
      { trace_id: 'trace-aba', projection_generation: 2, offset_revision: 9, projection_revision: 4, cursor: 6 },
      'ok',
      { offsetRef: 'ref-a' },
    ),
  ]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const snapshotOptions: SuccessorQueryOptions = {
      queryId: 'q-snap-aba',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-aba',
    }
    const active = await fetchSuccessorQuery(snapshotOptions)
    expect(active.meta).toMatchObject({ projection_generation: 4, offset_revision: 7 })
    const first = await fetchSuccessorQuery(snapshotOptions)
    expect(first.meta).toMatchObject({ projection_generation: 3, offset_revision: 8 })
    const retried = await fetchSuccessorQuery(snapshotOptions)
    expect(retried.meta).toMatchObject({ projection_generation: 3, offset_revision: 8 })
    const second = await fetchSuccessorQuery(snapshotOptions)
    expect(second.meta).toMatchObject({ projection_generation: 2, offset_revision: 9 })
    await expect(fetchSuccessorQuery(snapshotOptions)).rejects.toThrow(SuccessorStaleError)
    const settled = await fetchSuccessorQuery(snapshotOptions)
    expect(settled.meta).toMatchObject({ projection_generation: 2, offset_revision: 9 })
  } finally {
    harness.restore()
  }
})

test('backend model_dump snapshot with candidate sink/payload and nested rollback receipt roundtrips', async () => {
  const scope = {
    project_key: 'demo',
    resolved_schema: 'public',
    project_registry_revision: 1,
    incarnation: 'inc-1',
    scope_digest: DIGEST_64,
  }
  const activeMeta = {
    project_key: 'demo',
    trace_id: 'trace-rt',
    projection_id: 'proj-1',
    project_scope_ref: scope,
    projector_id: 'projector-1',
    projector_version: 'v1',
    source_kind: 'legacy',
    source_ref: 'ref://demo/proj',
    source_incarnation: 'inc-2',
    projection_generation: 4,
    offset_revision: 7,
    projection_revision: 6,
    source_digest: DIGEST_64,
    cursor: 8,
  }
  const activeBody = {
    status: 'ok',
    data: {
      projection_id: 'proj-1',
      projector_id: 'projector-1',
      projector_version: 'v1',
      source_kind: 'legacy',
      source_ref: 'ref://demo/proj',
      source_incarnation: 'inc-2',
      projection_generation: 4,
      offset_revision: 7,
      projection_revision: 6,
      source_digest: DIGEST_64,
      cursor: 8,
      offset_ref: 'ref-rt',
      candidate_values: [
        {
          value_id: 'v1',
          value_ref: 'project-value:v1',
          content_digest: DIGEST_64,
          byte_size: 12,
          sink: 'postgres',
          payload: { rows: 1 },
        },
      ],
    },
    error: null,
    meta: activeMeta,
    control_feedback: false,
  }
  const receipt = rollbackReceipt({
    from: position({ projection_generation: 4, offset_revision: 7, projection_revision: 6, cursor: 8, offset_ref: 'ref-rt' }),
    to: position({ projection_generation: 3, offset_revision: 8, projection_revision: 5, cursor: 7, offset_ref: 'ref-rt' }),
  })
  const transitionBody = {
    status: 'ok',
    data: {
      projection_id: 'proj-1',
      projector_id: 'projector-1',
      projector_version: 'v1',
      source_kind: 'legacy',
      source_ref: 'ref://demo/proj',
      source_incarnation: 'inc-2',
      projection_generation: 3,
      offset_revision: 8,
      projection_revision: 5,
      source_digest: DIGEST_64,
      cursor: 7,
      offset_ref: 'ref-rt',
      candidate_values: [],
      rollback_transition: receipt,
    },
    error: null,
    meta: {
      ...activeMeta,
      projection_generation: 3,
      offset_revision: 8,
      projection_revision: 5,
      cursor: 7,
    },
    control_feedback: false,
  }
  const responses = [activeBody, transitionBody]
  let responseIndex = 0
  const harness = installFetchHarness(() => jsonResponse(responses[responseIndex++]))
  try {
    const options: SuccessorQueryOptions = {
      queryId: 'q-rt',
      queryKind: 'projection_snapshot',
      projectLocator: 'demo',
      params: { params_kind: 'projection_snapshot', projection_id: 'proj-1', ...sourceKey() },
      traceId: 'trace-rt',
    }
    const active = await fetchSuccessorQuery(options)
    const activeData = assertSuccessorProjectionSnapshotData(
      active.meta as SuccessorProjectionMeta,
      active.data,
    )
    expect(activeData.candidate_values[0]).toMatchObject({
      sink: 'postgres',
      payload: { rows: 1 },
    })
    const transition = await fetchSuccessorQuery(options)
    const transitionData = assertSuccessorProjectionSnapshotData(
      transition.meta as SuccessorProjectionMeta,
      transition.data,
    )
    expect(transition.meta).toMatchObject({ projection_generation: 3, offset_revision: 8, cursor: 7 })
    expect(transitionData.rollback_transition?.ref).toBe('rollback-1')
    expect(transitionData.rollback_transition?.contract).toBe('C9RollbackTransitionReceipt.v1')
    expect(transitionData.rollback_transition?.digest).toBe(
      computeSuccessorRollbackReceiptDigest(transitionData.rollback_transition!),
    )
  } finally {
    harness.restore()
  }
})

test('preference functions are localStorage-scoped and non-authoritative', () => {
  expect(getSuccessorProjectPreference()).toBeNull()
  setSuccessorProjectPreference('beta')
  expect(getSuccessorProjectPreference()).toBe('beta')
  clearSuccessorProjectPreference()
  expect(getSuccessorProjectPreference()).toBeNull()
  expect(() => setSuccessorProjectPreference('  ')).toThrow(SuccessorRequestError)
})
