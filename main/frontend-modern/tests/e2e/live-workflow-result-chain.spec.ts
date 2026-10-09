import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import {
  buildE2eProjectKey,
  createE2eProject,
  deleteE2eProject,
} from './helpers/project-fixtures'

const PROJECT_KEY = buildE2eProjectKey('e2e_live_workflow')
const GRAPH_ID = `cg_${PROJECT_KEY}`
const SUCCESS_GRAPH_ID = `compiled_${PROJECT_KEY}_success`
const FAILURE_GRAPH_ID = `compiled_${PROJECT_KEY}_failure`
const TEMPLATE_ID = `tpl_${PROJECT_KEY}_failure`
const SUCCESS_RUN_ID = `run_${Date.now().toString(36)}_success`
const FAILURE_RUN_ID = `run_${Date.now().toString(36)}_failure`

type ApiEnvelope<T> = {
  status: string
  data: T
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
}

type CuratedDsl = {
  version?: string
  options?: Record<string, unknown>
  nodes?: Array<Record<string, unknown>>
  edges?: Array<Record<string, unknown>>
}

type CompileResult = {
  graph_id?: string
  checksum?: string
  topo_order?: string[]
}

type RunResult = {
  run_id?: string
  status?: string
  node_statuses?: Record<string, string>
  metadata?: {
    project_key?: string
    program_id?: string
    program_digest?: string
    plan_id?: string
    plan_digest?: string
    runtime_state?: string
  }
}

type StatefulReplay = {
  run_id?: string
  status?: string
  node_statuses?: Record<string, string>
  results?: Record<string, Record<string, unknown>>
  events?: Array<{ seq?: number; event_type?: string; type?: string; node_id?: string | null; payload?: Record<string, unknown> }>
  replay_consistency?: { consistent?: boolean }
}

type RunEvents = {
  items?: Array<{ event_type?: string; type?: string; node_id?: string | null; payload?: Record<string, unknown>; seq?: number }>
}

const headers = { 'X-Project-Key': PROJECT_KEY }
const workflowBearerToken = process.env.MRW_E2E_WORKFLOW_BEARER_TOKEN || ''

type LiveWorkflowResourceContract = {
  databaseName: string
  databaseHost: string
  databasePort: number
  apiOrigin: string
}

let liveWorkflowResource: LiveWorkflowResourceContract | undefined

function withProject(path: string) {
  const query = `project_key=${encodeURIComponent(PROJECT_KEY)}`
  return `${path}${path.includes('?') ? '&' : '?'}${query}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function requiredString(source: Record<string, unknown>, key: string, label: string) {
  expect(Object.hasOwn(source, key), `${label} must contain ${key}`).toBe(true)
  const value = source[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${label}.${key} must be a non-empty string`)
  }
  return value
}

function requiredNumber(source: Record<string, unknown>, key: string, label: string) {
  expect(Object.hasOwn(source, key), `${label} must contain ${key}`).toBe(true)
  const value = source[key]
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0 || value >= 65_536) {
    throw new Error(`${label}.${key} must be a valid port`)
  }
  return value
}

function requiredBoolean(source: Record<string, unknown>, key: string, label: string) {
  expect(Object.hasOwn(source, key), `${label} must contain ${key}`).toBe(true)
  if (typeof source[key] !== 'boolean') {
    throw new Error(`${label}.${key} must be a boolean`)
  }
  return source[key]
}

function liveWorkflowResourceContract(): LiveWorkflowResourceContract {
  if (!liveWorkflowResource) {
    throw new Error('live workflow resource contract was not initialized')
  }
  return liveWorkflowResource
}

async function apiSend<T>(
  request: APIRequestContext,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  payload?: unknown,
) {
  const response = await request.fetch(withProject(path), {
    method,
    headers: { ...headers, Authorization: `Bearer ${workflowBearerToken}` },
    data: payload === undefined ? undefined : payload,
  })
  const text = await response.text()
  expect(response.ok(), `${method} ${path}: ${text}`).toBeTruthy()
  const body = JSON.parse(text) as ApiEnvelope<T>
  expect(body.status).toBe('ok')
  return body.data
}

function assertIsolatedLiveEnvironment() {
  const databaseUrl = process.env.DATABASE_URL || ''
  const apiTarget = process.env.VITE_API_PROXY_TARGET || ''
  if (!databaseUrl || !apiTarget) {
    throw new Error('live workflow lane requires both DATABASE_URL and VITE_API_PROXY_TARGET')
  }

  const claimsPath = process.env.MRW_E2E_WORKFLOW_RESOURCE_CLAIMS || ''
  if (!claimsPath) {
    throw new Error('integration must supply MRW_E2E_WORKFLOW_RESOURCE_CLAIMS for the live workflow lane')
  }

  let parsedClaims: unknown
  try {
    parsedClaims = JSON.parse(readFileSync(claimsPath, 'utf8'))
  } catch (error) {
    throw new Error(`unable to read integration resource claims at ${claimsPath}: ${error instanceof Error ? error.message : String(error)}`)
  }
  expect(isRecord(parsedClaims), 'integration resource claims must be a JSON object').toBe(true)
  if (!isRecord(parsedClaims)) throw new Error('unreachable resource claims guard')
  expect(parsedClaims.schema).toBe('mrw.local-release-resource-claims.v1')
  expect(isRecord(parsedClaims.postgres), 'resource claims must declare postgres').toBe(true)
  if (!isRecord(parsedClaims.postgres)) throw new Error('unreachable postgres claim guard')
  expect(isRecord(parsedClaims.live_workflow), 'resource claims must declare live_workflow').toBe(true)
  if (!isRecord(parsedClaims.live_workflow)) throw new Error('unreachable live workflow claim guard')
  const liveWorkflow = parsedClaims.live_workflow

  const status = requiredString(liveWorkflow, 'status', 'live_workflow claim')
  if (status !== 'ready') {
    throw new Error(`integration live workflow resource is ${status}, not ready`)
  }

  const expectedDatabaseName = requiredString(liveWorkflow, 'database_name', 'live_workflow claim')
  const expectedDatabaseHost = requiredString(liveWorkflow, 'database_host', 'live_workflow claim')
  const expectedDatabasePort = requiredNumber(liveWorkflow, 'database_port', 'live_workflow claim')
  const expectedApiOrigin = requiredString(liveWorkflow, 'api_origin', 'live_workflow claim')
  const postgresHost = requiredString(parsedClaims.postgres, 'host', 'resource claims postgres')
  const postgresPort = requiredNumber(parsedClaims.postgres, 'port', 'resource claims postgres')
  const postgresExclusiveDatabase = requiredString(
    parsedClaims.postgres,
    'live_workflow_exclusive',
    'resource claims postgres',
  )
  expect(requiredBoolean(liveWorkflow, 'loopback_only', 'live_workflow claim')).toBe(true)
  expect(requiredBoolean(liveWorkflow, 'requires_postgres_slot', 'live_workflow claim')).toBe(true)
  expect(PROJECT_KEY.startsWith('e2e_live_workflow_'), 'live workflow project scope mismatch').toBe(true)
  expect(expectedDatabaseHost).toBe(postgresHost)
  expect(expectedDatabaseHost).toBe('127.0.0.1')
  expect(expectedDatabasePort).toBe(postgresPort)
  expect(expectedDatabaseName).toBe(postgresExclusiveDatabase)

  expect(isRecord(liveWorkflow.required_env), 'live_workflow claim must declare required_env').toBe(true)
  if (!isRecord(liveWorkflow.required_env)) throw new Error('unreachable required env guard')
  const declaredClaimsPath = requiredString(
    liveWorkflow.required_env,
    'MRW_E2E_WORKFLOW_RESOURCE_CLAIMS',
    'live_workflow required_env',
  )
  expect(declaredClaimsPath).toBe(claimsPath)

  const parsedDatabaseUrl = new URL(databaseUrl)
  expect(parsedDatabaseUrl.protocol, 'live workflow DATABASE_URL must use the SQLAlchemy PostgreSQL scheme').toBe('postgresql+psycopg2:')
  expect(parsedDatabaseUrl.hostname, 'live workflow DATABASE_URL host must exactly match the claim').toBe(expectedDatabaseHost)
  expect(Number(parsedDatabaseUrl.port), 'live workflow DATABASE_URL port must exactly match the claim').toBe(expectedDatabasePort)
  expect(
    decodeURIComponent(parsedDatabaseUrl.pathname.replace(/^\//, '')),
    'live workflow DATABASE_URL database must exactly match the claim',
  ).toBe(expectedDatabaseName)
  expect(parsedDatabaseUrl.search, 'live workflow DATABASE_URL must not add query parameters').toBe('')
  expect(parsedDatabaseUrl.hash).toBe('')

  const parsedApiOrigin = new URL(expectedApiOrigin)
  expect(parsedApiOrigin.protocol).toBe('http:')
  expect(parsedApiOrigin.hostname).toBe('127.0.0.1')
  expect(parsedApiOrigin.pathname).toBe('/')
  expect(parsedApiOrigin.username).toBe('')
  expect(parsedApiOrigin.password).toBe('')
  expect(parsedApiOrigin.search).toBe('')
  expect(parsedApiOrigin.hash).toBe('')
  expect(Number(parsedApiOrigin.port)).toBeGreaterThan(0)
  expect(apiTarget, 'live workflow API target must exactly match the integration claim').toBe(expectedApiOrigin)

  if (!Array.isArray(parsedClaims.preserved_resources)) {
    throw new Error('resource claims must declare preserved_resources')
  }
  const preservedPorts = parsedClaims.preserved_resources.flatMap((resource) => {
    return typeof resource === 'string' ? [...resource.matchAll(/\d+/g)].map((match) => Number(match[0])) : []
  })
  expect(preservedPorts, 'live workflow DB must not use a preserved port').not.toContain(expectedDatabasePort)
  expect(preservedPorts, 'live workflow API must not use a preserved port').not.toContain(Number(parsedApiOrigin.port))

  expect(Boolean(workflowBearerToken), 'configure the isolated backend E2E Bearer credential').toBe(true)

  liveWorkflowResource = {
    databaseName: expectedDatabaseName,
    databaseHost: expectedDatabaseHost,
    databasePort: expectedDatabasePort,
    apiOrigin: expectedApiOrigin,
  }
}

function psqlJson(query: string) {
  const databaseUrl = (process.env.DATABASE_URL || '').replace('postgresql+psycopg2://', 'postgresql://')
  const output = execFileSync(
    'psql',
    ['-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-d', databaseUrl, '-c', query],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
  )
  return JSON.parse(output.trim()) as unknown
}

function installIsolatedWorkflowFixture() {
  const backend = resolve(process.cwd(), '../backend')
  const repository = resolve(backend, '../..')
  const resource = liveWorkflowResourceContract()
  // Project CRUD creates the business schema; this explicit admin fixture installs Runtime authority.
  execFileSync(resolve(backend, '.venv311/bin/python'), ['-c', `
import os, sys
from datetime import UTC, datetime, timedelta
import sqlalchemy as sa
from app.composition.production_runtime import install_runtime_authority
from app.services.request_identity import RequestActorContext, actor_id_from_secret
from app.successor_runtime.capabilities.workflow_native_contribution import build_workflow_runtime_definition, WORKFLOW_RUNTIME_OWNER
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope, AuthorityResourceCeiling, AuthorityResourceLimit
from app.successor_runtime.runtime.resources import ResourceClass, ResourcePolicySnapshot
from app.successor_runtime.substrate.postgres.authority import AuthorityGrant, CapabilityAuthority
from app.successor_runtime.substrate.postgres.models import PUBLIC_METADATA, PUBLIC_TABLES, project_tables
from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver, compute_scope_digest

project, expected_host, expected_port, expected_database = sys.argv[1:]
url = sa.engine.make_url(os.environ['DATABASE_URL'])
assert url.host == expected_host and url.port == int(expected_port) and url.database == expected_database
assert project.startswith('e2e_live_workflow_')
engine = sa.create_engine(url)
definition = build_workflow_runtime_definition()
operations = tuple(definition.operation_for_node_type(kind) for kind in ('vector_search', 'llm_call', 'join'))
actor = actor_id_from_secret('actor:codex-token', os.environ['MRW_E2E_WORKFLOW_BEARER_TOKEN'])
now = datetime.now(UTC)
admin = RequestActorContext('e2e-workflow-admin', 'deployment', True, 'localdev-installation')
with engine.begin() as connection:
    PUBLIC_METADATA.create_all(connection, checkfirst=True)
    for name in ('project_scope_registry', 'runtime_authority_grants'):
        table = PUBLIC_TABLES[name]
        assert connection.execute(sa.select(table).where(table.c.project_key == project)).first() is None
    schema = connection.execute(sa.text('SELECT schema_name FROM public.projects WHERE project_key=:project'), {'project': project}).scalar_one()
    incarnation = 'e2e-scope:' + project
    digest = compute_scope_digest(project, schema, 1, incarnation)
    metadata = sa.MetaData()
    project_tables(metadata, schema)
    metadata.create_all(connection, checkfirst=True)
    connection.execute(sa.insert(PUBLIC_TABLES['project_scope_registry']).values(
        project_key=project, registry_revision=1, resolved_schema=schema,
        scope_digest=digest, incarnation=incarnation, state='ACTIVE', updated_by=admin.actor_id))
    scope = ServerProjectScopeResolver(connection=connection).resolve(project)
    capability = CapabilityAuthority(WORKFLOW_RUNTIME_OWNER, 'on', 1, True, False,
        canonical_digest((project, 'allow')), canonical_digest((project, 'config')), now,
        'e2e-admin:workflow', 'e2e-admin:workflow-disabled')
    resource_classes = sorted({op.profiles.resource.resource_classes[0] for op in operations})
    install_runtime_authority(connection, administrator=admin, project_scope=scope,
        capability=capability, installed=definition.registry,
        resource=tuple(ResourcePolicySnapshot(project, WORKFLOW_RUNTIME_OWNER, ResourceClass(resource_class),
            1, canonical_digest((project, resource_class)), 1, 1, 1, 1, 1) for resource_class in resource_classes),
        grant=AuthorityGrant('e2e-grant:' + project, actor, WORKFLOW_RUNTIME_OWNER,
            AuthorityOperationScope.from_content(operation_kinds=tuple(op.contract.ref.kind for op in operations), project_scope_digest=digest),
            AuthorityResourceCeiling.from_content(limits=tuple(AuthorityResourceLimit(resource_class=resource_class, units=1)
                for resource_class in resource_classes), max_active=1),
            None, 1, now + timedelta(hours=1)))
engine.dispose()
`, PROJECT_KEY, resource.databaseHost, String(resource.databasePort), resource.databaseName], {
    cwd: backend,
    env: { ...process.env, PYTHONPATH: [repository, resolve(repository, 'src'), backend].join(':') },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
}

async function waitForRun(request: APIRequestContext, runId: string, status: string) {
  await expect.poll(async () => (
    await apiSend<RunResult>(request, 'GET', `/api/v1/workflow-graph/runs/${runId}`)
  ).status, { timeout: 90_000, intervals: [15_000] }).toBe(status)
  return apiSend<RunResult>(request, 'GET', `/api/v1/workflow-graph/runs/${runId}`)
}

async function openGraphBuilder(page: Page) {
  await page.addInitScript((projectKey) => {
    window.localStorage.clear()
    window.localStorage.setItem('market_project_key', projectKey)
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  }, PROJECT_KEY)
  const response = await page.goto('/#graph-template-new.html')
  expect(response?.ok()).toBeTruthy()
  await expect(page.getByRole('heading', { level: 1, name: '新建图谱', exact: true })).toBeVisible()
  const advanced = page.getByTestId('graph-view-advanced-toggle')
  await expect(advanced).toBeVisible()
  if (await advanced.getAttribute('aria-pressed') !== 'true') {
    await advanced.click()
  }
  await expect(advanced).toHaveAttribute('aria-pressed', 'true')
}

async function addWorkflowNode(page: Page, nodeType: string, nodeId: string, nodeName: string) {
  const editSection = page.locator('section.gv2-control-section').filter({ hasText: '编辑' }).first()
  await editSection.locator('label.gv2-control-chip').filter({ hasText: '新节点类型' }).locator('input').fill(nodeType)
  await editSection.locator('label.gv2-control-chip').filter({ hasText: '新节点名称' }).locator('input').fill(nodeName)
  await editSection.getByRole('button', { name: '新增节点', exact: true }).click()

  const idInput = editSection.locator('label.gv2-control-chip').filter({ hasText: 'ID' }).last().locator('input')
  await expect(idInput).toBeEditable()
  await idInput.fill(nodeId)
  await editSection.getByRole('button', { name: '应用节点字段', exact: true }).click()
}

async function addWorkflowEdge(page: Page, sourceKey: string, targetKey: string, relation: string) {
  const editSection = page.locator('section.gv2-control-section').filter({ hasText: '编辑' }).first()
  await editSection.locator('label.gv2-control-chip').filter({ hasText: '边 Source' }).locator('select').selectOption(sourceKey)
  await editSection.locator('label.gv2-control-chip').filter({ hasText: '边 Target' }).locator('select').selectOption(targetKey)
  await editSection.locator('label.gv2-control-chip').filter({ hasText: '关系' }).last().locator('input').fill(relation)
  await editSection.getByRole('button', { name: /创建边|Create Edge/ }).click()
}

async function createFailureTemplate(request: APIRequestContext) {
  await apiSend(request, 'POST', '/api/v1/workflow-graph/templates', {
    project_key: PROJECT_KEY,
    template_id: TEMPLATE_ID,
    name: `Live workflow failure ${PROJECT_KEY}`,
  })
  const version = await apiSend<{ version?: { version_id?: string } }>(request, 'POST', `/api/v1/workflow-graph/templates/${TEMPLATE_ID}/versions`, {
    project_key: PROJECT_KEY,
    version_id: 'missing-required-input-v1',
    graph_object_kind: 'template_graph',
    dsl: {
      version: '1.0',
      options: {},
      nodes: [
        {
          node_id: 'missing_prompt',
          node_type: 'llm_call',
          config: { prompt_template: 'Answer this required variable: {required_for_live_failure}' },
        },
        { node_id: 'not_started_join', node_type: 'join', config: { field: 'text' } },
      ],
      edges: [{ from: 'missing_prompt', to: 'not_started_join' }],
    },
  })
  expect(version.version?.version_id).toBe('missing-required-input-v1')
  await apiSend(request, 'POST', `/api/v1/workflow-graph/templates/${TEMPLATE_ID}/versions/missing-required-input-v1/activate`, {
    project_key: PROJECT_KEY,
  })
}

test.describe('live workflow result chain', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(async ({ request }) => {
    assertIsolatedLiveEnvironment()
    await createE2eProject(request, PROJECT_KEY)
    installIsolatedWorkflowFixture()
  })

  test.afterAll(async ({ request }, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus) return
    const activeRuns = psqlJson(`SELECT count(*) FROM public.runtime_runs
      WHERE project_key = '${PROJECT_KEY}' AND state NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'SUPERSEDED')`)
    if (activeRuns === 0) {
      await deleteE2eProject(request, PROJECT_KEY)
    }
  })

  test('GraphPage edit, current compile/run, live kernels, and persistent API/DB readback', async ({
    page,
    request,
    browser,
  }) => {
    test.setTimeout(180_000)
    await openGraphBuilder(page)
    await expect(page.getByText(/Draft: nodes=0 edges=0/)).toBeVisible({ timeout: 30_000 })

    await addWorkflowNode(page, 'vector_search', 'retrieve', 'Live retrieval')
    await addWorkflowNode(page, 'llm_call', 'draft', 'Live model call')
    await addWorkflowNode(page, 'join', 'combine', 'Live result join')
    await addWorkflowEdge(page, 'vector_search:retrieve', 'llm_call:draft', 'retrieved_context')
    await addWorkflowEdge(page, 'vector_search:retrieve', 'join:combine', 'retrieved_evidence')
    await addWorkflowEdge(page, 'llm_call:draft', 'join:combine', 'model_answer')
    await expect(page.getByText(/Draft: nodes=3 edges=3/)).toBeVisible()

    await page.getByTestId('graph-curated-graph-id').fill(GRAPH_ID)
    const draftResponsePromise = page.waitForResponse((response) => (
      response.url().includes(`/workflow-graph/curated/${GRAPH_ID}/draft`)
      && response.request().method() === 'POST'
    ))
    const submitResponsePromise = page.waitForResponse((response) => (
      response.url().includes(`/workflow-graph/curated/${GRAPH_ID}/submit`)
      && response.request().method() === 'POST'
    ))
    await page.getByTestId('graph-curated-submit').click()
    const draftResponse = await draftResponsePromise
    const submitResponse = await submitResponsePromise
    expect(draftResponse.ok()).toBeTruthy()
    expect(submitResponse.ok()).toBeTruthy()
    expect(draftResponse.request().url()).toContain(`project_key=${PROJECT_KEY}`)
    await expect(page.getByTestId('graph-curated-status')).toContainText('submitted r1')

    const curated = await apiSend<{ server_snapshot?: { dsl?: CuratedDsl }, active_version_id?: string }>(
      request,
      'POST',
      `/api/v1/workflow-graph/curated/${GRAPH_ID}/sync`,
      { project_key: PROJECT_KEY, since_revision: 1 },
    )
    const persistedDsl = curated.server_snapshot?.dsl
    expect(persistedDsl?.nodes?.map((node) => [node.node_id, node.node_type])).toEqual([
      ['retrieve', 'vector_search'],
      ['draft', 'llm_call'],
      ['combine', 'join'],
    ])
    expect(persistedDsl?.edges?.map((edge) => [edge.from_node_id, edge.to_node_id])).toEqual([
      ['retrieve', 'draft'],
      ['retrieve', 'combine'],
      ['draft', 'combine'],
    ])

    const compiled = await apiSend<CompileResult>(request, 'POST', '/api/v1/workflow-graph/compile', {
      project_key: PROJECT_KEY,
      graph_id: SUCCESS_GRAPH_ID,
      dsl: persistedDsl,
    })
    expect(compiled.graph_id).toBe(SUCCESS_GRAPH_ID)
    expect(compiled.checksum).toMatch(/^[0-9a-f]{64}$/)
    expect(compiled.topo_order).toEqual(['retrieve', 'draft', 'combine'])

    const runPayload = {
      project_key: PROJECT_KEY,
      graph_id: SUCCESS_GRAPH_ID,
      run_id: SUCCESS_RUN_ID,
      input: { query: 'Hong Kong water policy research', topic: 'Hong Kong water' },
      trace_id: `${PROJECT_KEY}:success`,
    }
    for (const untrustedHeaders of [headers, { ...headers, 'X-Actor-Id': 'forged-e2e-actor' }]) {
      const denied = await request.post(withProject('/api/v1/workflow-graph/run'), {
        headers: untrustedHeaders,
        data: runPayload,
      })
      expect(denied.status()).toBe(403)
      expect((await denied.json()).error?.details?.reason_code).toBe('trusted_actor_required')
      expect(psqlJson(`SELECT jsonb_build_object(
        'runs', (SELECT count(*) FROM public.runtime_runs WHERE run_id = '${SUCCESS_RUN_ID}'),
        'attempts', (SELECT count(*) FROM public.runtime_effect_attempts WHERE run_id = '${SUCCESS_RUN_ID}')
      )`)).toEqual({ runs: 0, attempts: 0 })
    }
    const submitted = await apiSend<RunResult>(request, 'POST', '/api/v1/workflow-graph/run', runPayload)
    expect(submitted.run_id).toBe(SUCCESS_RUN_ID)
    const run = await waitForRun(request, SUCCESS_RUN_ID, 'succeeded')
    expect(run.status).toBe('succeeded')
    expect(run.node_statuses).toEqual({
      retrieve: 'succeeded',
      draft: 'succeeded',
      combine: 'succeeded',
    })

    await page.context().close()
    const recoveredContext = await browser.newContext()
    const recoveredPage = await recoveredContext.newPage()
    await openGraphBuilder(recoveredPage)
    await expect(recoveredPage.getByText(/Draft: nodes=0 edges=0/)).toBeVisible({ timeout: 30_000 })
    await recoveredPage.getByTestId('graph-curated-graph-id').fill(GRAPH_ID)
    await recoveredPage.getByTestId('graph-curated-sync').click()
    await expect(recoveredPage.getByText(/Draft: nodes=3 edges=3/)).toBeVisible({ timeout: 30_000 })
    await recoveredContext.close()

    const runDetail = await apiSend<RunResult>(request, 'GET', `/api/v1/workflow-graph/runs/${SUCCESS_RUN_ID}`)
    expect(runDetail.run_id).toBe(SUCCESS_RUN_ID)
    expect(runDetail.status).toBe('succeeded')
    expect(runDetail.node_statuses).toEqual(run.node_statuses)

    const stateful = await apiSend<StatefulReplay>(
      request,
      'GET',
      `/api/v1/workflow-graph/runs/${SUCCESS_RUN_ID}/replay?replay_mode=stateful`,
    )
    expect(stateful.replay_consistency?.consistent).toBe(true)
    expect(stateful.results?.retrieve?.node_type).toBe('vector_search')
    expect(stateful.results?.retrieve?.degraded).toBe(false)
    expect(stateful.results?.draft?.node_type).toBe('llm_call')
    expect(stateful.results?.draft?.degraded).toBe(false)
    expect(String(stateful.results?.draft?.text)).not.toContain('[fallback-llm]')
    expect(stateful.results?.combine?.node_type).toBe('join')
    expect(stateful.results?.combine?.sources).toEqual(['draft', 'retrieve'])

    const events = await apiSend<RunEvents>(request, 'GET', `/api/v1/workflow-graph/runs/${SUCCESS_RUN_ID}/events`)
    const eventOrder = events.items
      ?.filter((event) => !String(event.type || event.event_type || '').startsWith('agent_session.'))
      .map((event) => [event.type || event.event_type, event.node_id])
    expect(eventOrder).toEqual([
      ['ProgramAccepted', null],
      ['CompileSucceeded', null],
      ['PlanCompiled', null],
      ['QualificationActivated', null],
      ['StepActivated', 'retrieve'],
      ['StepClaimed', 'retrieve'],
      ['EffectStarted', 'retrieve'],
      ['RuntimeValueProduced', 'retrieve'],
      ['StepActivated', 'draft'],
      ['StepClaimed', 'draft'],
      ['EffectStarted', 'draft'],
      ['RuntimeValueProduced', 'draft'],
      ['StepActivated', 'combine'],
      ['StepClaimed', 'combine'],
      ['EffectStarted', 'combine'],
      ['RuntimeValueProduced', 'combine'],
      ['RunCompletionDerived', null],
    ])

    const dbCompiled = psqlJson(
      `SELECT payload_json FROM workflow_graph_compiled_artifacts WHERE graph_id = '${SUCCESS_GRAPH_ID}'`,
    ) as {
      graph_id?: string
      checksum?: string
      topo_order?: string[]
      binding_version?: string
      dsl_content_digest?: string
      dsl?: CuratedDsl
    }
    expect(dbCompiled.graph_id).toBe(SUCCESS_GRAPH_ID)
    expect(dbCompiled.checksum).toBe(compiled.checksum)
    expect(dbCompiled.topo_order).toEqual(['retrieve', 'draft', 'combine'])
    expect(dbCompiled.binding_version).toBe('workflow-graph.domain.v1')
    expect(dbCompiled.dsl_content_digest).toMatch(/^[0-9a-f]{64}$/)
    expect(dbCompiled.dsl?.nodes?.map((node) => [node.node_id, node.node_type])).toEqual([
      ['retrieve', 'vector_search'],
      ['draft', 'llm_call'],
      ['combine', 'join'],
    ])

    const dbRun = psqlJson(
      `SELECT jsonb_build_object(
        'run_id', run.run_id,
        'project_key', run.project_key,
        'state', run.state,
        'program_id', run.program_id,
        'program_digest', run.program_digest,
        'plan_id', run.plan_id,
        'plan_digest', run.plan_digest,
        'installed_program_id', program.program_id,
        'installed_program_digest', program.program_digest,
        'installed_program_storage_ref', program.project_storage_ref,
        'installed_plan_id', plan.plan_id,
        'installed_plan_digest', plan.plan_digest,
        'installed_plan_program_digest', plan.program_digest
      )
      FROM public.runtime_runs AS run
      JOIN public.runtime_program_refs AS program
        ON program.project_key = run.project_key AND program.program_id = run.program_id
      JOIN public.runtime_plan_refs AS plan
        ON plan.project_key = run.project_key AND plan.plan_id = run.plan_id
      WHERE run.run_id = '${SUCCESS_RUN_ID}'`,
    ) as {
      run_id?: string
      project_key?: string
      state?: string
      program_id?: string
      program_digest?: string
      plan_id?: string
      plan_digest?: string
      installed_program_id?: string
      installed_program_digest?: string
      installed_program_storage_ref?: string
      installed_plan_id?: string
      installed_plan_digest?: string
      installed_plan_program_digest?: string
    }
    expect(dbRun.run_id).toBe(SUCCESS_RUN_ID)
    expect(dbRun.project_key).toBe(PROJECT_KEY)
    expect(dbRun.state).toBe('COMPLETED')
    expect(dbRun.program_id).toBe(`workflow-program:${SUCCESS_RUN_ID}`)
    expect(dbRun.program_digest).toMatch(/^[0-9a-f]{64}$/)
    expect(dbRun.plan_id).toBeTruthy()
    expect(dbRun.plan_digest).toMatch(/^[0-9a-f]{64}$/)
    expect(dbRun.installed_program_id).toBe(dbRun.program_id)
    expect(dbRun.installed_program_digest).toBe(dbRun.program_digest)
    expect(dbRun.installed_program_storage_ref).toBeTruthy()
    expect(dbRun.installed_plan_id).toBe(dbRun.plan_id)
    expect(dbRun.installed_plan_digest).toBe(dbRun.plan_digest)
    expect(dbRun.installed_plan_program_digest).toBe(dbRun.program_digest)
    expect(runDetail.metadata?.program_id).toBe(dbRun.program_id)
    expect(runDetail.metadata?.program_digest).toBe(dbRun.program_digest)
    expect(runDetail.metadata?.plan_id).toBe(dbRun.plan_id)
    expect(runDetail.metadata?.plan_digest).toBe(dbRun.plan_digest)
    expect(runDetail.metadata?.runtime_state).toBe('COMPLETED')
  })

  test('template edit API and current run persist a bounded kernel failure', async ({ request }) => {
    test.setTimeout(120_000)
    await createFailureTemplate(request)

    const compiled = await apiSend<CompileResult>(request, 'POST', '/api/v1/workflow-graph/compile', {
      project_key: PROJECT_KEY,
      graph_id: FAILURE_GRAPH_ID,
      template_id: TEMPLATE_ID,
      version_id: 'missing-required-input-v1',
    })
    expect(compiled.topo_order).toEqual(['missing_prompt', 'not_started_join'])

    const submitted = await apiSend<RunResult>(request, 'POST', '/api/v1/workflow-graph/run', {
      project_key: PROJECT_KEY,
      graph_id: FAILURE_GRAPH_ID,
      run_id: FAILURE_RUN_ID,
      input: {},
      trace_id: `${PROJECT_KEY}:failure`,
    })
    expect(submitted.run_id).toBe(FAILURE_RUN_ID)
    const run = await waitForRun(request, FAILURE_RUN_ID, 'failed')
    expect(run.status).toBe('failed')
    expect(run.node_statuses).toEqual({
      missing_prompt: 'failed',
      not_started_join: 'queued',
    })

    const events = await apiSend<RunEvents>(request, 'GET', `/api/v1/workflow-graph/runs/${FAILURE_RUN_ID}/events`)
    const failedEvent = events.items?.find((event) => (event.type || event.event_type) === 'EffectFailed')
    expect(failedEvent?.node_id).toBe('missing_prompt')
    expect(failedEvent?.payload?.failure_family).toBe('workflow_graph.failure')
    expect(failedEvent?.payload?.failure_code).toBe('required_input_missing')
    expect(failedEvent?.payload?.error).toContain('required_for_live_failure')
    const projectSchema = psqlJson(`SELECT to_json(schema_name) FROM public.projects WHERE project_key = '${PROJECT_KEY}'`)
    expect(projectSchema).toMatch(/^[a-z0-9_]+$/)
    const persistedFailure = psqlJson(`SELECT jsonb_build_object(
      'failure_ref', attempt.failure_ref, 'failure_digest', attempt.failure_digest,
      'value_ref', 'project-value:' || value.value_id, 'value_digest', value.content_digest,
      'object_type', value.object_type, 'body', convert_from(value.content_bytes, 'UTF8')::jsonb
    ) FROM public.runtime_effect_attempts AS attempt
    JOIN "${projectSchema}".successor_values AS value ON value.content_digest = attempt.failure_digest
    WHERE attempt.run_id = '${FAILURE_RUN_ID}'`) as {
      failure_ref: string; failure_digest: string; value_ref: string; value_digest: string
      object_type: string; body: { schema_version: string; run_id: string; domain_failure: Record<string, unknown> }
    }
    expect(persistedFailure.failure_ref).toBe(failedEvent?.payload?.failure_ref)
    expect(persistedFailure.failure_digest).toBe(failedEvent?.payload?.failure_digest)
    expect(persistedFailure.value_ref).toBe(persistedFailure.failure_ref)
    expect(persistedFailure.value_digest).toBe(persistedFailure.failure_digest)
    expect(persistedFailure.object_type).toBe('RuntimeFailure.v2')
    expect(persistedFailure.body.schema_version).toBe('mrw.runtime.failure.v2')
    expect(persistedFailure.body.run_id).toBe(FAILURE_RUN_ID)
    expect(persistedFailure.body.domain_failure).toEqual({
      family: failedEvent?.payload?.failure_family, code: failedEvent?.payload?.failure_code,
      message: failedEvent?.payload?.error, context: failedEvent?.payload?.context,
    })

    const stateful = await apiSend<StatefulReplay>(
      request,
      'GET',
      `/api/v1/workflow-graph/runs/${FAILURE_RUN_ID}/replay?replay_mode=stateful`,
    )
    expect(stateful.replay_consistency?.consistent).toBe(true)
    expect(stateful.results).toEqual({})

    const dbFailure = psqlJson(
      `SELECT jsonb_build_object(
        'state', state,
        'project_key', project_key,
        'program_digest', program_digest,
        'plan_digest', plan_digest
      ) FROM public.runtime_runs WHERE run_id = '${FAILURE_RUN_ID}'`,
    ) as { state?: string; project_key?: string; program_digest?: string; plan_digest?: string }
    expect(dbFailure.state).toBe('FAILED')
    expect(dbFailure.project_key).toBe(PROJECT_KEY)
    expect(dbFailure.program_digest).toMatch(/^[0-9a-f]{64}$/)
    expect(dbFailure.plan_digest).toMatch(/^[0-9a-f]{64}$/)

    const templateState = psqlJson(
      `SELECT payload FROM ingest_config WHERE project_key = '${PROJECT_KEY}' AND config_key = 'workflow_graph_templates_v1'`,
    ) as { templates?: Record<string, { versions?: Record<string, { dsl?: CuratedDsl }> }> }
    const persistedVersion = templateState.templates?.[TEMPLATE_ID]?.versions?.['missing-required-input-v1']?.dsl
    expect(persistedVersion?.nodes?.[0]).toEqual(expect.objectContaining({
      node_id: 'missing_prompt',
      node_type: 'llm_call',
    }))
    expect(persistedVersion?.nodes?.[1]?.node_id).toBe('not_started_join')
  })
})
