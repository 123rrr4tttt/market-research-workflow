import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { moduleManifestByKey } from '../../src/app/kernel/moduleManifest'
import {
  SUCCESSOR_ENVELOPE_STATUSES,
  SUCCESSOR_V2_COMMAND_URL,
  SUCCESSOR_V2_QUERY_URL,
  decodeSuccessorTypedRejection,
  deriveSuccessorUiObservation,
  fetchSuccessorQuery,
  resetSuccessorProjectionClock,
  type SuccessorEnvelope,
  type SuccessorEnvelopeStatus,
} from '../../src/lib/api/domains/successor-runtime'
import {
  SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID,
  SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY,
  buildSuccessorRuntimeObservationQueryOptions,
} from '../../src/pages/successorRuntimeConfig'

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const pageSourcePath = path.resolve(currentDir, '../../src/pages/SuccessorRuntimePage.tsx')
const DIGEST_64 = 'a'.repeat(64)

function scopeRef(overrides: Record<string, unknown> = {}) {
  return {
    project_key: 'demo',
    resolved_schema: 'public',
    project_registry_revision: 0,
    incarnation: 'inc-1',
    scope_digest: DIGEST_64,
    ...overrides,
  }
}

function queryMeta(overrides: Record<string, unknown> = {}) {
  return {
    project_key: 'demo',
    trace_id: 'trace-1',
    query_id: SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID,
    project_scope_ref: scopeRef(),
    ...overrides,
  }
}

function projectionMeta(overrides: Record<string, unknown> = {}) {
  return {
    project_key: 'demo',
    trace_id: 'trace-1',
    projection_id: SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID,
    project_scope_ref: scopeRef(),
    projection_generation: 1,
    offset_revision: 0,
    projection_revision: 1,
    source_digest: DIGEST_64,
    cursor: 0,
    ...SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY,
    ...overrides,
  }
}

function projectionData(meta: Record<string, unknown>) {
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
    offset_ref: 'offset-ref-1',
    candidate_values: [],
  }
}

function fixtureEnvelope(status: SuccessorEnvelopeStatus): SuccessorEnvelope {
  if (status === 'ok' || status === 'waiting') {
    const meta = projectionMeta()
    return {
      status,
      data: projectionData(meta),
      error: null,
      meta,
      control_feedback: false,
    }
  }
  return {
    status,
    data: null,
    error: {
      code: status === 'conflict' ? 'CONFLICT' : status === 'error' ? 'SCOPE_RESOLUTION_FAILED' : `${status.toUpperCase()}_CODE`,
      message: `${status} fixture`,
      details: {},
    },
    meta: queryMeta(),
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

function projectionEnvelopeFromBody(body: Record<string, unknown>, status: 'ok' | 'waiting'): Record<string, unknown> {
  const params = body.params as Record<string, unknown>
  const meta = {
    project_key: String(body.project_locator),
    trace_id: String(body.trace_id),
    projection_id: String(params.projection_id),
    project_scope_ref: scopeRef({ project_key: String(body.project_locator) }),
    projection_generation: 1,
    offset_revision: 0,
    projection_revision: 1,
    source_digest: DIGEST_64,
    cursor: 0,
    projector_id: String(params.projector_id),
    projector_version: String(params.projector_version),
    source_kind: String(params.source_kind),
    source_ref: String(params.source_ref),
    source_incarnation: String(params.source_incarnation),
  }
  return {
    status,
    data: projectionData(meta),
    error: null,
    meta,
    control_feedback: false,
  }
}

function rejectionEnvelopeFromBody(body: Record<string, unknown>, status: 'conflict' | 'error'): Record<string, unknown> {
  return {
    status,
    data: null,
    error: {
      code: status === 'conflict' ? 'CONFLICT' : 'SCOPE_RESOLUTION_FAILED',
      message: `${status} rejection`,
      details: {},
    },
    meta: queryMeta({
      project_key: String(body.project_locator),
      trace_id: String(body.trace_id),
      query_id: String(body.query_id),
      project_scope_ref: scopeRef({ project_key: String(body.project_locator) }),
    }),
    control_feedback: false,
  }
}

test('kernel manifest registers sysSuccessorRuntime as a read-only admin module', () => {
  const entry = moduleManifestByKey.sysSuccessorRuntime
  expect(entry.layerId).toBe('C')
  expect(entry.entryRoute).toBe('/admin/successor-runtime')
  expect(entry.surfaceKind).toBe('management')
  expect(entry.visibleInNav).toBeTruthy()
  expect(entry.keepLoops).toContain('status-review')
})

test('successor runtime page builds only read-only projection snapshot queries', () => {
  const source = readFileSync(pageSourcePath, 'utf8')
  expect(source).not.toContain('submitSuccessorCommand')
  expect(source).not.toContain(SUCCESSOR_V2_COMMAND_URL)

  const options = buildSuccessorRuntimeObservationQueryOptions('demo_proj')
  expect(options.queryKind).toBe('projection_snapshot')
  expect(options.params.params_kind).toBe('projection_snapshot')
  expect(options.params.projection_id).toBe(SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID)
  expect(options.params.projector_id).toBe(SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY.projector_id)
  expect(options.params.source_ref).toBe(SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY.source_ref)
  expect(options).not.toHaveProperty('actorRef')
  expect(options).not.toHaveProperty('expectedBaseToken')
  expect(options).not.toHaveProperty('approvalLocator')
})

test('six envelope statuses keep their observation semantics under the page vocabulary', () => {
  expect(SUCCESSOR_ENVELOPE_STATUSES).toHaveLength(6)
  for (const status of SUCCESSOR_ENVELOPE_STATUSES) {
    const envelope = fixtureEnvelope(status)
    const observation = deriveSuccessorUiObservation({
      phase: 'settled',
      envelope,
      clientError: null,
    })
    if (status === 'ok') expect(observation).toBe('SUCCEEDED')
    if (status === 'waiting') expect(observation).toBe('IN_FLIGHT')
    if (status === 'blocked' || status === 'unavailable') expect(observation).toBe('OUTCOME_UNKNOWN')
    if (status === 'conflict') expect(observation).toBe('REJECTED_TYPED')
    if (status === 'error') expect(observation).toBe('REJECTED_TYPED')
  }
})

test('page query transport emits only query fetches and observes success plus typed rejection', async () => {
  installLocalStorageShim()
  resetSuccessorProjectionClock()

  let queryCount = 0
  const harness = installFetchHarness((call) => {
    const body = JSON.parse(String(call.init.body || '{}')) as Record<string, unknown>
    if (call.url.includes('/commands')) return jsonResponse({ unexpected: true }, 500)
    const params = body.params as Record<string, unknown> | undefined
    if (params?.params_kind !== 'projection_snapshot') return jsonResponse({ unexpected: true }, 500)
    queryCount += 1
    if (queryCount === 1) return jsonResponse(projectionEnvelopeFromBody(body, 'ok'))
    return jsonResponse(rejectionEnvelopeFromBody(body, 'conflict'))
  })

  try {
    const options = buildSuccessorRuntimeObservationQueryOptions('demo')
    const success = await fetchSuccessorQuery(options)
    expect(success.status).toBe('ok')
    expect(decodeSuccessorTypedRejection(success)).toBeNull()
    expect(deriveSuccessorUiObservation({ phase: 'settled', envelope: success, clientError: null })).toBe('SUCCEEDED')

    const conflictingOptions = { ...options, queryId: 'q:conflict' }
    const conflict = await fetchSuccessorQuery(conflictingOptions)
    expect(conflict.status).toBe('conflict')
    const reason = decodeSuccessorTypedRejection(conflict)
    expect(reason?.code).toBe('CONFLICT')
    expect(deriveSuccessorUiObservation({ phase: 'settled', envelope: conflict, clientError: null })).toBe('REJECTED_TYPED')

    expect(harness.calls.filter((call) => call.url.includes(SUCCESSOR_V2_COMMAND_URL))).toHaveLength(0)
    expect(harness.calls.filter((call) => call.url.includes(SUCCESSOR_V2_QUERY_URL)).length).toBeGreaterThanOrEqual(2)
  } finally {
    harness.restore()
    resetSuccessorProjectionClock()
  }
})

test('kernel browser page mounts the read-only successor observation panel', async ({ page }) => {
  const commandRequests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes(SUCCESSOR_V2_COMMAND_URL)) commandRequests.push(request.url())
  })

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const requestBody = route.request().method() === 'POST' ? route.request().postDataJSON() : null
    if (url.pathname.endsWith('/successor-runtime/v2/queries')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(projectionEnvelopeFromBody(requestBody, 'ok')),
      })
      return
    }
    if (url.pathname.endsWith('/successor-runtime/v2/commands')) {
      await route.fulfill({ status: 403, contentType: 'application/json', body: '{}' })
      return
    }
    let data: unknown = {}
    if (url.pathname.endsWith('/projects')) data = [{ project_key: 'demo_proj', name: 'Demo', enabled: true, is_active: true }]
    if (url.pathname.endsWith('/health') || url.pathname.endsWith('/health/deep')) data = { status: 'ok' }
    if (url.pathname.endsWith('/codex-auth/status')) data = { authenticated: false, token_sink_authenticated: false, codex_oauth_enabled: true }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data, error: null, meta: {} }),
    })
  })

  await page.goto('/#/admin/successor-runtime')
  await expect(page.getByTestId('successor-runtime-page-status')).toBeVisible()
  await expect(page.locator('[data-observation="SUCCEEDED"]')).toBeVisible()
  await expect(page.locator('[data-status="ok"]')).toBeVisible()
  await expect(page.locator('[data-read-only-boundary="true"]')).toHaveText('read-only')
  expect(commandRequests).toEqual([])
})
