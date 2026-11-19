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
  material_id?: unknown
  material_ref?: unknown
  topology_ref?: unknown
  uri?: unknown
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

type AdminMaterialPayload = {
  id: unknown
  material_id?: unknown
  uri?: unknown
}

function requireAdminMaterials(data: unknown, label: string) {
  const payload = requireObject(data, label)
  if (!Array.isArray(payload.items)) {
    throw new Error(`${label} is missing its items array.`)
  }
  return payload.items as AdminMaterialPayload[]
}

function projectedMaterialId(item: AdminMaterialPayload) {
  const materialId = Number(item.material_id ?? item.id)
  return Number.isSafeInteger(materialId) && materialId > 0 ? materialId : null
}

function truncate(value: string) {
  return value.length > 500 ? `${value.slice(0, 500)}...` : value
}

test('@live real-backend business line smoke [line_key=ingest] classifies endpoint, data, and browser failures', async ({ page, request }) => {
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

test('@live real-backend business line smoke [line_key=search_discovery_index] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'search_discovery_index'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, lineKey, '/api/v1/search?q=smoke&limit=1&rank=bm25', {
    requireData: (data) => {
      const payload = requireObject(data, 'Search response')
      if (typeof payload.query !== 'string' || !Array.isArray(payload.results)) {
        throw new Error('Search response is missing query/results evidence.')
      }
    },
  })

  await bootstrapRealBackendPage(page)
  const legacyCatalogRequests: string[] = []
  page.on('request', (request) => {
    if (/\/api\/v1\/(topics|products)(?:[/?]|$)/.test(request.url())) {
      legacyCatalogRequests.push(request.url())
    }
  })
  await page.goto('/#/visual/catalog')
  await expectVisible(lineKey, page.getByRole('heading', { level: 2, name: '统计视图' }))
  await expectVisible(lineKey, page.getByText('当前统计视图暂无指标。'))
  expect(legacyCatalogRequests).toEqual([])
})

test('@live real-backend business line smoke [line_key=dashboard_admin_governance] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'dashboard_admin_governance'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, lineKey, '/api/v1/dashboard/stats', {
    requireData: (data) => {
      const payload = requireObject(data, 'Dashboard stats')
      if (!payload.materials && !payload.sources && !payload.tasks) {
        throw new Error('Dashboard stats payload is missing materials/sources/tasks evidence.')
      }
    },
  })

  await bootstrapRealBackendPage(page)
  const statsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/stats') && response.status() === 200
  })
  await page.goto('/#/admin/ops')
  await statsResponse
  await expectVisible(lineKey, page.getByRole('heading', { name: '材料治理', exact: true }))
})

test('@live real-backend business line smoke [line_key=projects_config_workflow] classifies endpoint, data, and browser failures', async ({ page, request }) => {
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

test('@live real-backend business line smoke [line_key=writing_knowledge_graph_agent] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'writing_knowledge_graph_agent'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, `${lineKey} graph config`, '/api/v1/project-customization/graph-config', {
    requireData: (data) => requireObject(data, 'Graph config'),
  })
  const marketGraph = requireGraphArrays(
    await probeEndpoint(request, `${lineKey} market graph`, '/api/v1/admin/market-graph?view=market_deep_entities&limit=100', {
    }),
    'Market graph',
  )
  const adminMaterials = requireAdminMaterials(
    await probeEndpoint(request, `${lineKey} materials`, '/api/v1/admin/materials/list', {
      method: 'POST',
      body: {
        page: 1,
        page_size: 100,
        state: null,
        material_type: null,
        has_extracted_data: null,
        search: null,
        sort_by: 'created_at',
        sort_order: 'desc',
      },
    }),
    'Admin materials',
  )
  const projectedMaterials = adminMaterials.flatMap((item) => {
    const materialId = projectedMaterialId(item)
    return materialId == null ? [] : [{ item, materialId }]
  })
  expect(new Set(projectedMaterials.map(({ materialId }) => materialId)).size).toBe(projectedMaterials.length)

  await bootstrapRealBackendPage(page)
  const graphConfigResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/project-customization/graph-config') && response.status() === 200
  })
  const marketGraphResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/market-graph') && response.status() === 200
  })
  const materialListResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/materials/list') && response.status() === 200
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
  const browserAdminMaterials = await materialListResponse.then(async (response) => {
    const body = await response.text()
    if (!response.ok()) {
      throw new Error(`Browser material list response failed: status=${response.status()} body=${truncate(body)}`)
    }
    return requireAdminMaterials(unwrapEnvelope(parseJsonOrText(body)), 'Browser admin materials')
  })
  expect(browserAdminMaterials.map(projectedMaterialId)).toEqual(adminMaterials.map(projectedMaterialId))
  await expectVisible(lineKey, page.getByRole('heading', { name: '市场图谱' }))
  const expectedNodeKeys = [
    ...marketGraph.nodes.map(graphNodeKey),
    ...projectedMaterials.map(({ materialId }) => `material:${materialId}`),
  ]
  expect(new Set(expectedNodeKeys).size).toBe(expectedNodeKeys.length)
  await expect.poll(async () => page.evaluate(() => {
    const graphPage = window as Window & {
      __graphPageE2E?: { getGraphSnapshot: () => { nodes: unknown[] } }
    }
    return graphPage.__graphPageE2E?.getGraphSnapshot().nodes.length ?? -1
  })).toBe(expectedNodeKeys.length)

  const browserGraphSnapshot = await page.evaluate(() => {
    const graphPage = window as Window & {
      __graphPageE2E?: {
        getGraphSnapshot: () => { nodes: GraphNodePayload[]; edges: GraphEdgePayload[] }
      }
    }
    return graphPage.__graphPageE2E?.getGraphSnapshot()
  })
  if (!browserGraphSnapshot) {
    throw new Error('GraphPage did not expose its realized graph snapshot for real-backend verification.')
  }
  expect(browserGraphSnapshot.nodes.map(graphNodeKey).sort()).toEqual(expectedNodeKeys.sort())
  expect(browserGraphSnapshot.edges.map(graphEdgeKey).sort()).toEqual(marketGraph.edges.map(graphEdgeKey).sort())
  for (const { item, materialId } of projectedMaterials) {
    const materialNode = browserGraphSnapshot.nodes.find((node) => graphNodeKey(node) === `material:${materialId}`)
    expect(materialNode).toBeDefined()
    const canonicalRef = {
      project_key: PROJECT_KEY,
      module_id: 'materials',
      namespace: 'materials',
      type_id: 'material',
      local_id: String(materialId),
    }
    expect(materialNode?.material_id).toBe(materialId)
    expect(materialNode?.material_ref).toEqual(canonicalRef)
    expect(materialNode?.topology_ref).toEqual(canonicalRef)
    expect(materialNode?.uri ?? null).toBe(item.uri ?? null)
  }

  const nodeSummary = page.locator('.gv2-macro-stat').filter({
    has: page.getByText('节点总数', { exact: true }),
  }).locator('strong')
  const edgeSummary = page.locator('.gv2-macro-stat').filter({
    has: page.getByText('边总数', { exact: true }),
  }).locator('strong')
  await expectVisible(lineKey, nodeSummary)
  await expectVisible(lineKey, edgeSummary)
  await expect(nodeSummary).toHaveText(String(expectedNodeKeys.length))
  await expect(edgeSummary).toHaveText(String(marketGraph.edges.length))
})

test('@live real-backend business line smoke [line_key=resource_source_library] classifies endpoint, data, and browser failures', async ({ page, request }) => {
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

test('@live real-backend business line smoke [line_key=runtime_ops] classifies endpoint, data, and browser failures', async ({ page, request }) => {
  const lineKey: CanonicalBusinessLineKey = 'runtime_ops'
  skipWhenBackendCheckBypassed()
  await probeEndpoint(request, `${lineKey} health`, '/api/v1/health', {
    requireData: (data) => requireObject(data, 'Ops health'),
  })
  await probeEndpoint(request, `${lineKey} admin stats`, '/api/v1/admin/stats', {
    requireData: (data) => requireObject(data, 'Ops admin stats'),
  })
  await probeEndpoint(request, `${lineKey} documents`, '/api/v1/admin/materials/list', {
    method: 'POST',
    body: { page: 1, page_size: 20 },
    requireData: (data) => requireObject(data, 'Ops documents list'),
  })

  await bootstrapRealBackendPage(page)
  const healthResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/health') && response.status() === 200
  })
  await page.goto('/#/admin/backend')
  await healthResponse
  await expectVisible(lineKey, page.getByRole('heading', { name: '运行态状态' }))
})
