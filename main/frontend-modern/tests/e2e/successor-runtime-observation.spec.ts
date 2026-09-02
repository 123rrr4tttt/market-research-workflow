import { expect, test } from '@playwright/test'
import {
  SUCCESSOR_TYPED_REJECTION_CODES,
  SUCCESSOR_UI_OBSERVATION_STATES,
  SUCCESSOR_V2_COMMAND_URL,
  SuccessorDecodeError,
  SuccessorRequestError,
  SuccessorRuntimeError,
  SuccessorScopeError,
  decodeSuccessorTypedRejection,
  deriveSuccessorUiObservation,
  projectSuccessorServerScope,
  resetSuccessorProjectionClock,
  resolveSuccessorServerResolvedScope,
  submitSuccessorCommand,
  type SuccessorCommandOptions,
  type SuccessorEnvelope,
  type SuccessorEnvelopeMeta,
  type SuccessorEnvelopeStatus,
  type SuccessorProjectionMeta,
  type SuccessorTypedRejectionCode,
  type SuccessorTypedRejectionReason,
  type SuccessorUiObservationState,
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

function projectionData(
  meta: Record<string, unknown>,
  offsetRef = 'offset-ref-1',
  candidateValues: unknown[] = [],
) {
  return {
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
}

function projectionEnvelope(
  metaOverrides: Record<string, unknown> = {},
  status: 'ok' | 'waiting' = 'ok',
): SuccessorEnvelope {
  const meta = projectionMeta(metaOverrides)
  return envelope(status, {
    meta,
    data: projectionData(meta),
  })
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

function rejectionEnvelope(
  status: 'conflict' | 'error',
  code: string,
  meta: SuccessorEnvelopeMeta = commandMeta(),
): SuccessorEnvelope {
  return {
    status,
    data: null,
    error: { code, message: `${code} message`, details: { cause: 'test-rejection' } },
    meta,
    control_feedback: false,
  }
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
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

test('observation state vocabulary preserves exact six-state order', () => {
  const first: SuccessorUiObservationState = SUCCESSOR_UI_OBSERVATION_STATES[0]
  expect(first).toBe('NOT_STARTED')
  expect(SUCCESSOR_UI_OBSERVATION_STATES).toEqual([
    'NOT_STARTED',
    'IN_FLIGHT',
    'SUCCEEDED',
    'FAILED',
    'OUTCOME_UNKNOWN',
    'REJECTED_TYPED',
  ])
})

test('typed rejection codes match the exact seven-code set', () => {
  const conflictCode: SuccessorTypedRejectionCode = 'CONFLICT'
  expect(conflictCode).toBe('CONFLICT')
  expect(SUCCESSOR_TYPED_REJECTION_CODES).toEqual([
    'INVALID_INPUT',
    'NOT_FOUND',
    'CONFLICT',
    'UNAUTHORIZED',
    'FORBIDDEN',
    'RATE_LIMITED',
    'SCOPE_RESOLUTION_FAILED',
  ])
})

test('derive maps not_started and in_flight phases', () => {
  const notStarted: SuccessorUiObservationState = deriveSuccessorUiObservation({ phase: 'not_started' })
  expect(notStarted).toBe('NOT_STARTED')
  expect(deriveSuccessorUiObservation({ phase: 'in_flight' })).toBe('IN_FLIGHT')
})

test('derive maps settled ok envelope to SUCCEEDED', () => {
  expect(deriveSuccessorUiObservation({ phase: 'settled', envelope: envelope('ok') })).toBe('SUCCEEDED')
})

test('derive maps settled waiting envelope to IN_FLIGHT', () => {
  expect(deriveSuccessorUiObservation({ phase: 'settled', envelope: envelope('waiting') })).toBe('IN_FLIGHT')
})

test('derive maps settled conflict with typed CONFLICT code to REJECTED_TYPED', () => {
  const conflict = rejectionEnvelope('conflict', 'CONFLICT')
  expect(deriveSuccessorUiObservation({ phase: 'settled', envelope: conflict })).toBe('REJECTED_TYPED')
})

test('derive maps settled error with unknown code to OUTCOME_UNKNOWN', () => {
  expect(
    deriveSuccessorUiObservation({
      phase: 'settled',
      envelope: rejectionEnvelope('error', 'UPSTREAM_FAILURE'),
    }),
  ).toBe('OUTCOME_UNKNOWN')
})

test('derive maps blocked and unavailable envelopes to OUTCOME_UNKNOWN', () => {
  for (const status of ['blocked', 'unavailable'] as const) {
    expect(deriveSuccessorUiObservation({ phase: 'settled', envelope: envelope(status) })).toBe(
      'OUTCOME_UNKNOWN',
    )
  }
})

test('derive maps client error to FAILED before envelope status', () => {
  const clientError = new SuccessorRequestError('client rejected submit', { reason: 'validation' })
  expect(
    deriveSuccessorUiObservation({ phase: 'settled', envelope: envelope('ok'), clientError }),
  ).toBe('FAILED')
})

test('derive fails closed on missing settled inputs and invalid phase', () => {
  expect(() => deriveSuccessorUiObservation({ phase: 'settled' })).toThrow(SuccessorDecodeError)
  expect(() => deriveSuccessorUiObservation({ phase: 'unknown_phase' } as never)).toThrow(
    SuccessorDecodeError,
  )
})

test('typed rejection decode recognizes SCOPE_RESOLUTION_FAILED with UNRESOLVED meta', () => {
  const unresolvedMeta: SuccessorEnvelopeMeta = {
    project_key: 'demo',
    trace_id: 'trace-1',
    request_id: 'req-1',
    resolution_state: 'UNRESOLVED',
  }
  const reason: SuccessorTypedRejectionReason | null = decodeSuccessorTypedRejection(
    rejectionEnvelope('error', 'SCOPE_RESOLUTION_FAILED', unresolvedMeta),
  )
  expect(reason).not.toBeNull()
  expect(reason?.code).toBe('SCOPE_RESOLUTION_FAILED')
  expect(reason?.message).toBe('SCOPE_RESOLUTION_FAILED message')
  expect(reason?.details).toEqual({ cause: 'test-rejection' })
  expect(reason?.meta).toEqual(unresolvedMeta)
})

test('typed rejection decode returns null for non-rejection statuses and unknown codes', () => {
  for (const status of ['ok', 'waiting', 'blocked', 'unavailable'] as const) {
    expect(decodeSuccessorTypedRejection(envelope(status))).toBeNull()
  }
  for (const code of ['UPSTREAM_FAILURE', 'INTERNAL_FAILURE', 'CUSTOM_UNKNOWN']) {
    expect(decodeSuccessorTypedRejection(rejectionEnvelope('error', code))).toBeNull()
  }
})

test('resolved scope requires matching projection meta and rejects mismatch or unresolved meta', () => {
  expect(resolveSuccessorServerResolvedScope('demo', projectionEnvelope())).toEqual(scopeRef())

  const mismatched = projectionEnvelope({
    project_key: 'other',
    project_scope_ref: scopeRef({ project_key: 'other' }),
  })
  expect(() => resolveSuccessorServerResolvedScope('demo', mismatched)).toThrow(SuccessorScopeError)

  const scopeRefMismatch = projectionEnvelope({
    project_scope_ref: scopeRef({ project_key: 'other' }),
  })
  expect(() => resolveSuccessorServerResolvedScope('demo', scopeRefMismatch)).toThrow(SuccessorScopeError)

  const unresolved: SuccessorEnvelope = {
    status: 'error',
    data: null,
    error: { code: 'SCOPE_RESOLUTION_FAILED', message: 'unresolved locator', details: {} },
    meta: {
      project_key: 'demo',
      trace_id: 'trace-1',
      request_id: 'req-1',
      resolution_state: 'UNRESOLVED',
    },
    control_feedback: false,
  }
  expect(() => resolveSuccessorServerResolvedScope('demo', unresolved)).toThrow(SuccessorScopeError)
})

test('project server scope decodes projection snapshots and rejects command or error-family envelopes', () => {
  const okEnvelope = projectionEnvelope({ projection_id: 'proj-obs', trace_id: 'trace-obs' })
  const result = projectSuccessorServerScope('demo', okEnvelope)
  expect(result.scope).toEqual(scopeRef())
  expect(result.envelope).toBe(okEnvelope)
  expect(result.snapshot.projection_id).toBe('proj-obs')

  const commandEnvelope = envelope('ok', {
    meta: commandMeta({ command_id: 'cmd-obs', trace_id: 'trace-obs' }),
  })
  expect(() => projectSuccessorServerScope('demo', commandEnvelope)).toThrow(SuccessorDecodeError)

  const errorProjection = envelope('error', { meta: projectionMeta({ projection_id: 'proj-obs' }) })
  expect(() => projectSuccessorServerScope('demo', errorProjection)).toThrow(SuccessorRuntimeError)
})

test('submit rejects missing actorRef without dispatching', async () => {
  const harness = installFetchHarness(() => jsonResponse(envelope('waiting')))
  try {
    await expect(
      submitSuccessorCommand({
        commandId: 'cmd-missing-actor',
        commandKind: 'rebuild_projection',
        projectLocator: 'demo',
        payload: {
          payload_kind: 'rebuild_projection',
          projection_id: 'proj-1',
          ...sourceKey(),
        },
        traceId: 'trace-missing-actor',
      } as SuccessorCommandOptions),
    ).rejects.toThrow(SuccessorRequestError)
    expect(harness.calls).toHaveLength(0)
  } finally {
    harness.restore()
  }
})

test('submit keeps actorRef out of the wire body and returns waiting envelope', async () => {
  const harness = installFetchHarness(() =>
    jsonResponse(
      envelope('waiting', { meta: commandMeta({ command_id: 'cmd-actor-1', trace_id: 'trace-actor-1' }) }),
    ),
  )
  try {
    const result = await submitSuccessorCommand({
      commandId: 'cmd-actor-1',
      commandKind: 'rebuild_projection',
      projectLocator: 'demo',
      payload: {
        payload_kind: 'rebuild_projection',
        projection_id: 'proj-1',
        mode: 'FULL',
        ...sourceKey(),
      },
      traceId: 'trace-actor-1',
      actorRef: 'actor-1',
    })
    expect(result.status).toBe('waiting')
    expect(harness.calls).toHaveLength(1)
    expect(harness.calls[0].url).toContain(SUCCESSOR_V2_COMMAND_URL)

    const requestBody = JSON.parse(String(harness.calls[0].init.body)) as Record<string, unknown>
    expect(Object.keys(requestBody).sort()).toEqual([
      'command_id',
      'command_kind',
      'payload',
      'project_locator',
      'trace_id',
    ])
    const payload = requestBody.payload as Record<string, unknown>
    for (const forbidden of ['actor', 'actor_ref', 'scope', 'authority', 'execute', 'control']) {
      expect(Object.keys(requestBody).includes(forbidden)).toBe(false)
      expect(Object.keys(payload).includes(forbidden)).toBe(false)
    }
  } finally {
    harness.restore()
  }
})
