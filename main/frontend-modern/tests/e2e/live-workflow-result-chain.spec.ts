import { execFileSync } from 'node:child_process'
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

function withProject(path: string) {
  const query = `project_key=${encodeURIComponent(PROJECT_KEY)}`
  return `${path}${path.includes('?') ? '&' : '?'}${query}`
}

async function apiSend<T>(
  request: APIRequestContext,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  payload?: unknown,
) {
  const response = await request.fetch(withProject(path), {
    method,
    headers,
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
  expect(databaseUrl, 'live workflow chain must use the isolated completion database').toContain(
    '127.0.0.1:55436/mrw_completion_test',
  )
  expect(apiTarget, 'live workflow chain must use the isolated backend').toContain('127.0.0.1:18086')
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
  })

  test.afterAll(async ({ request }) => {
    await deleteE2eProject(request, PROJECT_KEY)
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

    const run = await apiSend<RunResult>(request, 'POST', '/api/v1/workflow-graph/run', {
      project_key: PROJECT_KEY,
      graph_id: SUCCESS_GRAPH_ID,
      run_id: SUCCESS_RUN_ID,
      input: { query: 'Hong Kong water policy research', topic: 'Hong Kong water' },
      trace_id: `${PROJECT_KEY}:success`,
    })
    expect(run.run_id).toBe(SUCCESS_RUN_ID)
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
      ['run.queued', null],
      ['run.running', null],
      ['node.running', 'retrieve'],
      ['node.succeeded', 'retrieve'],
      ['node.running', 'draft'],
      ['node.succeeded', 'draft'],
      ['node.running', 'combine'],
      ['node.succeeded', 'combine'],
      ['run.succeeded', null],
    ])

    const dbCompiled = psqlJson(
      `SELECT payload_json FROM workflow_graph_compiled_artifacts WHERE graph_id = '${SUCCESS_GRAPH_ID}'`,
    ) as {
      graph_id?: string
      checksum?: string
      topo_order?: string[]
      platform?: { program_digest?: string; plan_digest?: string; catalog_digest?: string }
    }
    expect(dbCompiled.graph_id).toBe(SUCCESS_GRAPH_ID)
    expect(dbCompiled.checksum).toBe(compiled.checksum)
    expect(dbCompiled.topo_order).toEqual(['retrieve', 'draft', 'combine'])
    expect(dbCompiled.platform?.program_digest).toMatch(/^[0-9a-f]{64}$/)
    expect(dbCompiled.platform?.plan_digest).toMatch(/^[0-9a-f]{64}$/)
    expect(dbCompiled.platform?.catalog_digest).toMatch(/^[0-9a-f]{64}$/)

    const dbRun = psqlJson(
      `SELECT jsonb_build_object('run_id', run_id, 'workflow_id', workflow_id, 'status', status, 'node_statuses', node_statuses, 'metadata', metadata, 'results', results) FROM workflow_graph_runs WHERE run_id = '${SUCCESS_RUN_ID}'`,
    ) as {
      run_id?: string
      workflow_id?: string
      status?: string
      node_statuses?: Record<string, string>
      metadata?: { project_key?: string; program_digest?: string; plan_digest?: string }
      results?: Record<string, Record<string, unknown>>
    }
    expect(dbRun.run_id).toBe(SUCCESS_RUN_ID)
    expect(dbRun.workflow_id).toBe(SUCCESS_GRAPH_ID)
    expect(dbRun.status).toBe('succeeded')
    expect(dbRun.node_statuses).toEqual(run.node_statuses)
    expect(dbRun.metadata?.project_key).toBe(PROJECT_KEY)
    expect(dbRun.metadata?.program_digest).toBe(dbCompiled.platform?.program_digest)
    expect(dbRun.metadata?.plan_digest).toBe(dbCompiled.platform?.plan_digest)
    expect(dbRun.results?.draft?.degraded).toBe(false)
    expect(dbRun.results?.combine?.sources).toEqual(['draft', 'retrieve'])
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

    const run = await apiSend<RunResult>(request, 'POST', '/api/v1/workflow-graph/run', {
      project_key: PROJECT_KEY,
      graph_id: FAILURE_GRAPH_ID,
      run_id: FAILURE_RUN_ID,
      input: {},
      trace_id: `${PROJECT_KEY}:failure`,
    })
    expect(run.run_id).toBe(FAILURE_RUN_ID)
    expect(run.status).toBe('failed')
    expect(run.node_statuses).toEqual({
      missing_prompt: 'failed',
      not_started_join: 'queued',
    })

    const events = await apiSend<RunEvents>(request, 'GET', `/api/v1/workflow-graph/runs/${FAILURE_RUN_ID}/events`)
    const failedEvent = events.items?.find((event) => (event.type || event.event_type) === 'node.failed')
    expect(failedEvent?.node_id).toBe('missing_prompt')
    expect(failedEvent?.payload?.failure_family).toBe('workflow_graph.failure')
    expect(failedEvent?.payload?.failure_code).toBe('required_input_missing')
    expect(failedEvent?.payload?.error).toContain('required_for_live_failure')

    const stateful = await apiSend<StatefulReplay>(
      request,
      'GET',
      `/api/v1/workflow-graph/runs/${FAILURE_RUN_ID}/replay?replay_mode=stateful`,
    )
    expect(stateful.replay_consistency?.consistent).toBe(true)
    expect(stateful.results).toEqual({})

    const dbFailure = psqlJson(
      `SELECT jsonb_build_object('status', status, 'node_statuses', node_statuses, 'metadata', metadata, 'results', results) FROM workflow_graph_runs WHERE run_id = '${FAILURE_RUN_ID}'`,
    ) as { status?: string; node_statuses?: Record<string, string>; metadata?: { project_key?: string } }
    expect(dbFailure.status).toBe('failed')
    expect(dbFailure.node_statuses).toEqual(run.node_statuses)
    expect(dbFailure.metadata?.project_key).toBe(PROJECT_KEY)

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
