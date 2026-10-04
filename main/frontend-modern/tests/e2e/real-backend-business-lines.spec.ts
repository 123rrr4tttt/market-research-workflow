import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test'
import {
  buildClassifiedBackendFailure,
  requireRealBackendReadiness,
  SKIP_BACKEND_CHECK,
  type BackendFailureClassification,
  type RealBackendReadinessResult,
} from './helpers/backend-readiness'

const PROJECT_KEY = process.env.FRONTEND_E2E_PROJECT_KEY || 'default'
const PAGE_ORIGIN = `http://127.0.0.1:${process.env.FRONTEND_E2E_PORT || '4173'}`
const GRAPH_FIXTURE_MODE = process.env.FRONTEND_E2E_GRAPH_FIXTURE || 'generic'

let backendReadiness: RealBackendReadinessResult | undefined

type CanonicalBusinessLineKey =
  | 'ingest'
  | 'search_discovery_index'
  | 'resource_source_library'
  | 'projects_config_workflow'
  | 'dashboard_admin_governance'
  | 'writing_knowledge_graph_agent'
  | 'runtime_ops'

type EndpointProbeOptions = {
  method?: 'GET' | 'POST'
  body?: unknown
  requireData?: (data: unknown) => void
}

test.beforeAll(async ({ request }) => {
  backendReadiness = await requireRealBackendReadiness(request)
})

function skipWhenBackendCheckBypassed() {
  test.skip(
    backendReadiness?.skipped === true,
    `${SKIP_BACKEND_CHECK}=1 skips real-backend browser proof; no real-backend smoke is counted as passed.`,
  )
}

async function bootstrapRealBackendPage(page: Page) {
  await page.addInitScript((projectKey) => {
    window.localStorage.setItem('market_project_key', projectKey)
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  }, PROJECT_KEY)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], {
    origin: PAGE_ORIGIN,
  })
}

function withProjectKey(path: string) {
  const url = new URL(path, PAGE_ORIGIN)
  url.searchParams.set('project_key', PROJECT_KEY)
  return `${url.pathname}${url.search}`
}

async function probeEndpoint(
  request: APIRequestContext,
  lineName: string,
  path: string,
  options: EndpointProbeOptions = {},
) {
  const endpoint = withProjectKey(path)
  let response
  try {
    response = options.method === 'POST'
      ? await request.post(endpoint, {
          data: options.body ?? {},
          headers: { 'X-Project-Key': PROJECT_KEY },
          timeout: 10000,
        })
      : await request.get(endpoint, {
          headers: { 'X-Project-Key': PROJECT_KEY },
          timeout: 10000,
        })
  } catch (error) {
    throw new Error(
      buildClassifiedBackendFailure({
        title: `Real-backend ${lineName} endpoint probe was blocked before the browser smoke could run.`,
        classification: 'blocked_by_environment',
        checkedEndpoints: [endpoint],
        details: [`request_error: ${error instanceof Error ? error.message : String(error)}`],
      }),
    )
  }

  const body = await response.text()
  if (!response.ok()) {
    throw new Error(
      buildClassifiedBackendFailure({
        title: `Real-backend ${lineName} endpoint probe failed.`,
        classification: classifyStatus(response.status()),
        checkedEndpoints: [endpoint],
        details: [`status=${response.status()}`, `body=${truncate(body)}`],
      }),
    )
  }

  const data = unwrapEnvelope(parseJsonOrText(body))
  if (options.requireData) {
    try {
      options.requireData(data)
    } catch (error) {
      throw new Error(
        buildClassifiedBackendFailure({
          title: `Real-backend ${lineName} endpoint data setup is incomplete.`,
          classification: 'data_setup_missing',
          checkedEndpoints: [endpoint],
          details: [error instanceof Error ? error.message : String(error), `body=${truncate(body)}`],
        }),
      )
    }
  }

  return data
}

async function expectVisible(lineName: string, locator: Locator) {
  try {
    await expect(locator).toBeVisible()
  } catch (error) {
    throw new Error(
      buildClassifiedBackendFailure({
        title: `Real-backend ${lineName} browser smoke reached the backend but the UI assertion failed.`,
        classification: 'functional_failure',
        checkedEndpoints: [],
        details: [error instanceof Error ? error.message : String(error)],
      }),
    )
  }
}

function classifyStatus(status: number): BackendFailureClassification {
  if ([401, 403, 502, 503, 504].includes(status)) return 'blocked_by_environment'
  if ([400, 404, 405, 409, 422].includes(status)) return 'functional_failure'
  return status >= 500 ? 'functional_failure' : 'data_setup_missing'
}

function parseJsonOrText(body: string) {
  if (!body.trim()) return null
  try {
    return JSON.parse(body)
  } catch {
    return body
  }
}

function unwrapEnvelope(value: unknown) {
  if (value && typeof value === 'object' && 'status' in value && 'data' in value) {
    return (value as { data?: unknown }).data
  }
  return value
}

function requireObject(data: unknown, label: string) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(`${label} did not return an object payload.`)
  }
  return data as Record<string, unknown>
}

function requirePayload(data: unknown, label: string) {
  if (data == null || (typeof data === 'string' && !data.trim())) {
    throw new Error(`${label} returned an empty payload.`)
  }
}

function requireNonEmptyList(data: unknown, label: string) {
  const list = Array.isArray(data)
    ? data
    : data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)
      ? (data as { items: unknown[] }).items
      : []
  if (!list.length) {
    throw new Error(`${label} returned no rows for project_key=${PROJECT_KEY}.`)
  }
}

type GraphNodePayload = {
  type: unknown
  id: unknown
}

type GraphEdgePayload = {
  type: unknown
  from: GraphNodePayload
  to: GraphNodePayload
}

function graphNodeKey(node: GraphNodePayload) {
  return `${String(node.type)}:${String(node.id)}`
}

function graphEdgeKey(edge: GraphEdgePayload) {
  return [
    String(edge.type),
    graphNodeKey(edge.from),
    graphNodeKey(edge.to),
  ].join('>')
}

function requireGraphArrays(data: unknown, label: string) {
  const payload = requireObject(data, label)
  if (!Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
    throw new Error(`${label} is missing nodes/edges arrays.`)
  }
  return { nodes: payload.nodes as GraphNodePayload[], edges: payload.edges as GraphEdgePayload[] }
}

function requireSimp11NonEmptyMarketGraph(data: unknown) {
  const { nodes, edges } = requireGraphArrays(data, 'Market graph')
  const actualNodeKeys = nodes.map(graphNodeKey).sort()
  const actualEdgeKeys = edges.map(graphEdgeKey).sort()
  const expectedNodeKeys = [
    'MarketData:41101',
    'MarketData:41102',
    'State:CA',
    'Segment:ai-terminal',
    'Segment:research-agent',
  ].sort()
  const expectedEdgeKeys = [
    'IN_STATE>MarketData:41101>State:CA',
    'IN_STATE>MarketData:41102>State:CA',
    'HAS_SEGMENT>MarketData:41101>Segment:ai-terminal',
    'HAS_SEGMENT>MarketData:41102>Segment:research-agent',
  ].sort()

  if (actualNodeKeys.length < 2 || actualEdgeKeys.length < 1) {
    throw new Error('Market graph returned an empty or near-empty graph.')
  }
  if (JSON.stringify(actualNodeKeys) !== JSON.stringify(expectedNodeKeys)) {
    throw new Error(`Market graph node identities mismatch: ${JSON.stringify(actualNodeKeys)}`)
  }
  if (JSON.stringify(actualEdgeKeys) !== JSON.stringify(expectedEdgeKeys)) {
    throw new Error(`Market graph edge identities mismatch: ${JSON.stringify(actualEdgeKeys)}`)
  }
}

function requireSelectedGraphFixtureMode() {
  if (GRAPH_FIXTURE_MODE !== 'generic' && GRAPH_FIXTURE_MODE !== 'simp11_nonempty') {
    throw new Error(
      `FRONTEND_E2E_GRAPH_FIXTURE must be 'simp11_nonempty' for the fixture oracle or unset for generic graph proof; received ${JSON.stringify(GRAPH_FIXTURE_MODE)}.`,
    )
  }
  return GRAPH_FIXTURE_MODE
}

function truncate(value: string) {
  return value.length > 500 ? `${value.slice(0, 500)}...` : value
}

test('real-backend business line smoke [line_key=ingest] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'ingest'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, lineKey, '/api/v1/ingest/history?limit=1', {
    requireData: (data) => requirePayload(data, 'Ingest history'),
  })

  await bootstrapRealBackendPage(page)
  const historyResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/ingest/history') && response.status() === 200
  })
  await page.goto('/#/workbench/ingest/specialized')
  await historyResponse
  await expectVisible(lineKey, page.getByText('特化采集 / source-library + single-url'))
  await expectVisible(lineKey, page.getByRole('heading', { name: '单 URL 入库' }))
})

test('real-backend business line smoke [line_key=search_discovery_index] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'search_discovery_index'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, lineKey, '/api/v1/search?q=smoke&limit=1', {
    requireData: (data) => {
      const payload = requireObject(data, 'Search response')
      if (typeof payload.query !== 'string' || !Array.isArray(payload.results)) {
        throw new Error('Search response is missing query/results evidence.')
      }
    },
  })

  await bootstrapRealBackendPage(page)
  const topicsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/topics') && response.status() === 200
  })
  const productsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/products') && response.status() === 200
  })
  await page.goto('/#/visual/catalog')
  await topicsResponse
  await productsResponse
  await expectVisible(lineKey, page.getByRole('heading', { level: 1, name: '行业公司/商品/经营' }))
  await expectVisible(lineKey, page.getByRole('heading', { name: '主题管理' }))
})

test('real-backend business line smoke [line_key=dashboard_admin_governance] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'dashboard_admin_governance'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, lineKey, '/api/v1/dashboard/stats', {
    requireData: (data) => {
      const payload = requireObject(data, 'Dashboard stats')
      if (!payload.documents && !payload.sources && !payload.tasks) {
        throw new Error('Dashboard stats payload is missing documents/sources/tasks evidence.')
      }
    },
  })

  await bootstrapRealBackendPage(page)
  const statsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/dashboard/stats') && response.status() === 200
  })
  await page.goto('/#/visual/dashboard')
  await statsResponse
  await expectVisible(lineKey, page.getByRole('heading', { name: '数据仪表盘' }))
})

test('real-backend business line smoke [line_key=projects_config_workflow] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'projects_config_workflow'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, lineKey, '/api/v1/projects', {
    requireData: (data) => requireNonEmptyList(data, 'Projects list'),
  })

  await bootstrapRealBackendPage(page)
  const projectsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/projects') && response.status() === 200
  })
  await page.goto('/#/admin/projects')
  await projectsResponse
  await expectVisible(lineKey, page.getByRole('heading', { name: '项目与模板' }))
  await expectVisible(lineKey, page.getByTestId('projects-list'))
})

test('real-backend business line smoke [line_key=writing_knowledge_graph_agent] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'writing_knowledge_graph_agent'
  const graphFixtureMode = requireSelectedGraphFixtureMode()
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, `${lineKey} graph config`, '/api/v1/project-customization/graph-config', {
    requireData: (data) => requireObject(data, 'Graph config'),
  })
  const marketGraph = requireGraphArrays(
    await probeEndpoint(request, `${lineKey} market graph`, '/api/v1/admin/market-graph?view=market_deep_entities&limit=100', {
      requireData: graphFixtureMode === 'simp11_nonempty'
        ? requireSimp11NonEmptyMarketGraph
        : (data) => requireGraphArrays(data, 'Market graph'),
    }),
    'Market graph',
  )

  await bootstrapRealBackendPage(page)
  const graphConfigResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/project-customization/graph-config') && response.status() === 200
  })
  const marketGraphResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/market-graph') && response.status() === 200
  })
  await page.goto('/#/visual/graph/market')
  await graphConfigResponse
  const browserMarketGraph = await marketGraphResponse.then(async (response) => {
    const body = await response.text()
    if (!response.ok()) {
      throw new Error(`Browser market graph response failed: status=${response.status()} body=${truncate(body)}`)
    }
    return unwrapEnvelope(parseJsonOrText(body))
  })
  const browserGraph = requireGraphArrays(browserMarketGraph, 'Browser market graph')
  expect(browserGraph.nodes.map(graphNodeKey).sort()).toEqual(marketGraph.nodes.map(graphNodeKey).sort())
  expect(browserGraph.edges.map(graphEdgeKey).sort()).toEqual(marketGraph.edges.map(graphEdgeKey).sort())
  await expectVisible(lineKey, page.getByRole('heading', { name: '市场图谱' }))

  const nodeSummary = page.locator('.gv2-macro-stat').filter({
    has: page.getByText('节点总数', { exact: true }),
  }).locator('strong')
  const edgeSummary = page.locator('.gv2-macro-stat').filter({
    has: page.getByText('边总数', { exact: true }),
  }).locator('strong')
  await expectVisible(lineKey, nodeSummary)
  await expectVisible(lineKey, edgeSummary)
  await expect(nodeSummary).toHaveText(String(marketGraph.nodes.length))
  await expect(edgeSummary).toHaveText(String(marketGraph.edges.length))

  if (graphFixtureMode === 'simp11_nonempty') {
    const selected = await page.evaluate(() => {
      const graphPage = window as Window & {
        __graphPageE2E?: { selectNode: (nodeId: string) => boolean }
      }
      return graphPage.__graphPageE2E?.selectNode('41101') === true
    })
    if (!selected) {
      throw new Error('Market graph browser state did not contain the persisted MarketData:41101 node.')
    }
    const selectedNodeCard = page.getByTestId('graph-selected-node-card')
    await expectVisible(lineKey, selectedNodeCard)
    await expect(selectedNodeCard).toContainText('SIMP11 nonempty graph market 41101')
    await expect(selectedNodeCard).toContainText('MarketData')
    await expect(selectedNodeCard).toContainText('41101')
    await expect(selectedNodeCard).toContainText('CA')
    await expect(selectedNodeCard).toContainText('ai-terminal')
    await expectVisible(lineKey, selectedNodeCard.getByRole('button', { name: 'IN_STATE (1)' }))
    await expectVisible(lineKey, selectedNodeCard.getByRole('button', { name: 'HAS_SEGMENT (1)' }))

    await selectedNodeCard.getByRole('button', { name: 'IN_STATE (1)' }).click()
    await expectVisible(lineKey, selectedNodeCard.getByText('出 · CA'))
    await selectedNodeCard.getByRole('button', { name: 'HAS_SEGMENT (1)' }).click()
    await expectVisible(lineKey, selectedNodeCard.getByText('出 · ai-terminal'))
  }
})

test('real-backend business line smoke [line_key=resource_source_library] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'resource_source_library'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, `${lineKey} source library`, '/api/v1/source_library/items?scope=effective', {
    requireData: (data) => requirePayload(data, 'Source library items'),
  })
  await probeEndpoint(request, `${lineKey} site entries`, '/api/v1/resource_pool/site_entries/grouped', {
    requireData: (data) => requireObject(data, 'Resource site entries grouped'),
  })

  await bootstrapRealBackendPage(page)
  const sourceItemsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/source_library/items') && response.status() === 200
  })
  const siteEntriesResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/resource_pool/site_entries') && response.status() === 200
  })
  await page.goto('/#/admin/resources')
  await sourceItemsResponse
  await siteEntriesResponse
  await expectVisible(lineKey, page.getByRole('heading', { name: '信息资源库管理' }).first())
})

test('real-backend business line smoke [line_key=runtime_ops] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'runtime_ops'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, `${lineKey} health`, '/api/v1/health', {
    requireData: (data) => requireObject(data, 'Ops health'),
  })
  await probeEndpoint(request, `${lineKey} admin stats`, '/api/v1/admin/stats', {
    requireData: (data) => requireObject(data, 'Ops admin stats'),
  })
  await probeEndpoint(request, `${lineKey} documents`, '/api/v1/admin/documents/list', {
    method: 'POST',
    body: { page: 1, page_size: 20 },
    requireData: (data) => requireObject(data, 'Ops documents list'),
  })

  await bootstrapRealBackendPage(page)
  const healthResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/health') && response.status() === 200
  })
  const adminStatsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/stats') && response.status() === 200
  })
  await page.goto('/#/admin/ops')
  await healthResponse
  await adminStatsResponse
  await expectVisible(lineKey, page.getByRole('heading', { name: '运行态状态' }))
})
