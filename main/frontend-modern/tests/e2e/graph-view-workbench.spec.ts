import { expect, test, type Locator, type Page, type Route } from '@playwright/test'
import {
  applyProjectGraphView,
  projectGraphEdgeKey,
  projectGraphNodeKey,
  normalizeProjectGraphViewSpec,
  type ProjectGraphViewSpec,
} from '../../src/pages/graph/realizer/projectGraphView'
import type { GraphEdgeItem, GraphNodeItem } from '../../src/lib/types'
import { buildProjectGraphTypeGraph } from '../../src/pages/graph/realizer/projectGraphTypeGraph'

function source(nodes: GraphNodeItem[], edges: GraphEdgeItem[]) {
  return { nodes, edges }
}

function node(id: string, type: string): GraphNodeItem {
  return { id, type, name: `${type}:${id}`, entry_id: id }
}

function edge(
  id: string,
  from: string,
  to: string,
  kind = 'belongs_to',
  fromType = 'product',
  toType = 'company',
): GraphEdgeItem {
  return { id, type: kind, predicate: kind, from: { id: from, type: fromType }, to: { id: to, type: toType } }
}

function canonicalSpec(spec: ProjectGraphViewSpec): ProjectGraphViewSpec {
  const normalized = normalizeProjectGraphViewSpec(spec)
  if (!normalized) throw new Error('test fixture must be a valid project graph view')
  return normalized
}

test.describe('project graph view realizer', () => {
test('type graph preserves direction, parallel type edges and self relations with endpoint closure', () => {
  const nodes = [node('1:colon', 'product'), node('2', 'product'), node('3', 'company')]
  const edges = [
    edge('one', '1:colon', '3'), edge('two', '2', '3'),
    edge('parallel', '1:colon', '3', 'influences'),
    edge('reverse', '3', '1:colon', 'belongs_to', 'company', 'product'),
    edge('self', '1:colon', '2', 'resembles', 'product', 'product'),
    edge('dangling', 'missing', '3', 'influences', 'ghost'),
  ]
  const graph = buildProjectGraphTypeGraph(nodes, edges, ['watchpoint'], [{ sourceType: 'watchpoint', targetType: 'company', relation: 'supervises' }])
  expect(graph.nodeTypes).toEqual(expect.arrayContaining(['ProductEntity', 'company', 'watchpoint']))
  expect(graph.nodeTypes).toHaveLength(3)
  expect(graph.relations).toHaveLength(5)
  expect(graph.relations).toEqual(expect.arrayContaining([
    { sourceType: 'ProductEntity', targetType: 'company', relation: 'belongs_to' },
    { sourceType: 'ProductEntity', targetType: 'company', relation: 'influences' },
    { sourceType: 'company', targetType: 'ProductEntity', relation: 'belongs_to' },
    { sourceType: 'ProductEntity', targetType: 'ProductEntity', relation: 'resembles' },
    { sourceType: 'watchpoint', targetType: 'company', relation: 'supervises' },
  ]))
  expect(buildProjectGraphTypeGraph([...nodes].reverse(), [...edges].reverse(), ['watchpoint'], [{ sourceType: 'watchpoint', targetType: 'company', relation: 'supervises' }])).toEqual(graph)
  const domainRelation = { ...edges[0], relation_token: 'manages', predicate: 'from' }
  expect(buildProjectGraphTypeGraph(nodes, [domainRelation], [], []).relations[0].relation).toBe('manages')
})
test('type declarations normalize and never create instance data', () => {
  const view: ProjectGraphViewSpec = {
    schema: 'project-graph-view/v1', mode: 'all', nodeKeys: [], hiddenNodeTypes: [], hiddenEdgeKinds: [],
    additionalNodes: [], additionalEdges: [],
    declaredNodeTypes: [' watchpoint '],
    declaredRelationTypes: [{ sourceType: 'watchpoint', targetType: 'company', relation: ' Supervises ' }],
  }
  const normalized = canonicalSpec(view)
  expect(normalized.declaredNodeTypes).toEqual(['watchpoint'])
  expect(normalized.declaredRelationTypes).toEqual([{ sourceType: 'watchpoint', targetType: 'company', relation: 'supervises' }])
  const nodes = [node('1', 'company')]
  expect(applyProjectGraphView(nodes, [], normalized)).toEqual(source(nodes, []))
  expect(normalizeProjectGraphViewSpec({ ...view, declaredNodeTypes: ['product', 'ProductEntity'] })).toBeNull()
  expect(normalizeProjectGraphViewSpec({ ...view, declaredRelationTypes: [{ sourceType: 'watchpoint', targetType: '', relation: 'supervises' }] })).toBeNull()
  expect(normalizeProjectGraphViewSpec({ ...view, declaredRelationTypes: [view.declaredRelationTypes![0], { ...view.declaredRelationTypes![0], relation: 'supervises' }] })).toBeNull()
})
test('normalizes only the v1 project graph view contract', () => {
    const view: ProjectGraphViewSpec = {
      schema: 'project-graph-view/v1',
      mode: 'selection',
      nodeKeys: ['product:source-1'],
      hiddenNodeTypes: ['policy'],
      hiddenEdgeKinds: ['regulated_by'],
      additionalNodes: [],
      additionalEdges: [],
    }

    expect(normalizeProjectGraphViewSpec(view)).toEqual({
      ...view,
      nodeKeys: ['ProductEntity:source-1'],
      hiddenNodeTypes: ['Policy'],
    })
    expect(normalizeProjectGraphViewSpec({ ...view, schema: 'project-graph-view/v2' })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, schema: 'PROJECT-GRAPH-VIEW/V1' })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, mode: 'snapshot' })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, mode: 'ALL' })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, display: { renderMode: '3d' } })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, display: {} })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, display: { renderMode: '2d', quality: 'high' } })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, unexpected: true })).toBeNull()
    expect(normalizeProjectGraphViewSpec({ ...view, additionalNodes: [{ id: 'x' }] })).toBeNull()
    expect(normalizeProjectGraphViewSpec(null)).toBeNull()
  })

  test('all mode preserves current source identities', () => {
    const input = source([node('hk-source-1', 'product'), node('hk-source-2', 'company')], [
      edge('e1', 'hk-source-1', 'hk-source-2'),
    ])
    const output = applyProjectGraphView(input.nodes, input.edges, canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: [],
      hiddenEdgeKinds: [],
      additionalNodes: [],
      additionalEdges: [],
    }))

    expect(output.nodes.map(projectGraphNodeKey)).toEqual([
      'ProductEntity:hk-source-1',
      'company:hk-source-2',
    ])
    expect(output.edges.map(projectGraphEdgeKey)).toEqual([projectGraphEdgeKey({ ...edge('e1', 'hk-source-1', 'hk-source-2') })])
  })

  test('selection uses the exact induced endpoint closure without dangling edges', () => {
    const input = source([
      node('seed', 'product'),
      node('neighbor', 'company'),
      node('outside', 'company'),
      node('unreachable', 'company'),
    ], [
      edge('seed-neighbor', 'seed', 'neighbor'),
      edge('seed-outside', 'seed', 'outside'),
      edge('outside-unreachable', 'outside', 'unreachable'),
      edge('unreachable-alone', 'unreachable', 'unreachable'),
    ])
    const output = applyProjectGraphView(input.nodes, input.edges, canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'selection',
      nodeKeys: ['product:seed', 'company:neighbor'],
      hiddenNodeTypes: [],
      hiddenEdgeKinds: [],
      additionalNodes: [],
      additionalEdges: [],
    }))

    expect(output.nodes.map((item) => item.id).sort()).toEqual(['neighbor', 'seed'])
    expect(output.edges.map((item) => item.id)).toEqual(['seed-neighbor'])
  })

  test('type and edge masks filter without discarding source identities', () => {
    const input = source([
      node('product-1', 'product'),
      node('company-1', 'company'),
      node('company-2', 'company'),
      node('policy-1', 'policy'),
    ], [
      edge('product-company', 'product-1', 'company-1'),
      edge('policy-company', 'policy-1', 'company-1', 'regulated_by', 'policy', 'company'),
      edge('masked-company-edge', 'company-1', 'company-2', 'regulated_by', 'company', 'company'),
    ])
    const output = applyProjectGraphView(input.nodes, input.edges, canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: ['policy'],
      hiddenEdgeKinds: ['pred:regulated_by'],
      additionalNodes: [],
      additionalEdges: [],
    }))

    expect(output.nodes.map((item) => item.id)).toEqual(['product-1', 'company-1', 'company-2'])
    expect(output.edges.map((item) => item.id)).toEqual(['product-company'])
  })

  test('additions extend the current source and never overwrite the same source identity', () => {
    const input = source([node('source-1', 'product')], [])
    const output = applyProjectGraphView(input.nodes, input.edges, canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: [],
      hiddenEdgeKinds: [],
      additionalNodes: [
        { ...node('source-1', 'product'), name: 'stale source name' },
        node('external-1', 'operation'),
      ],
      additionalEdges: [edge('external-edge', 'external-1', 'source-1', 'belongs_to', 'operation', 'product')],
    }))

    expect(output.nodes).toEqual([
      expect.objectContaining({ id: 'source-1', type: 'product', name: 'product:source-1' }),
      expect.objectContaining({ id: 'external-1', type: 'operation' }),
    ])
    expect(output.edges).toHaveLength(1)
  })

test('saved filters recompute against a changed source without stale snapshot identity', () => {
    const saved: ProjectGraphViewSpec = {
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: ['policy'],
      hiddenEdgeKinds: [],
      additionalNodes: [],
      additionalEdges: [],
    }
    const changed = source([
      node('company-current', 'company'),
      node('policy-old', 'policy'),
      node('operation-new', 'operation'),
    ], [])
    const output = applyProjectGraphView(changed.nodes, changed.edges, canonicalSpec(saved))

    expect(output.nodes.map((item) => item.id).sort()).toEqual(['company-current', 'operation-new'])
  })

  test('a hidden duplicate source addition is not reintroduced', () => {
    const input = source([node('duplicate-1', 'product')], [])
    const output = applyProjectGraphView(input.nodes, input.edges, canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: ['product'],
      hiddenEdgeKinds: [],
      additionalNodes: [node('duplicate-1', 'product')],
      additionalEdges: [],
    }))

    expect(output.nodes).toEqual([])
  })

  test('hidden type mask applies to custom additions', () => {
    const output = applyProjectGraphView([], [], canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: ['operation'],
      hiddenEdgeKinds: [],
      additionalNodes: [node('custom-1', 'operation'), node('kept-1', 'company')],
      additionalEdges: [],
    }))

    expect(output.nodes.map((item) => item.id)).toEqual(['kept-1'])
  })

  test('parallel edges with the same class and different predicates remain distinct', () => {
    const nodes = [node('source-1', 'product'), node('target-1', 'company')]
    const additional = (predicate: string): GraphEdgeItem => ({
      id: `parallel-${predicate}`,
      type: 'custom_relation',
      relation_class: 'custom_relation',
      predicate,
      predicate_raw: predicate,
      from: { id: 'source-1', type: 'product' },
      to: { id: 'target-1', type: 'company' },
    })
    const output = applyProjectGraphView(nodes, [], canonicalSpec({
      schema: 'project-graph-view/v1',
      mode: 'all',
      nodeKeys: [],
      hiddenNodeTypes: [],
      hiddenEdgeKinds: [],
      additionalNodes: [],
      additionalEdges: [additional('influences'), additional('monitors')],
    }))

    expect(output.edges.map((item) => item.id)).toEqual(['parallel-influences', 'parallel-monitors'])
  })
})

type ApiRecord = { method: string; path: string; project: string | undefined }

type BoundElement = {
  type_id: string
  local_id: string
  attributes: Record<string, unknown>
  structural_role?: string
  endpoints?: Array<{ role: string; target: { type_id: string; local_id: string } }>
}

function topologyElement(element: BoundElement, revision = 'rev-1') {
  const ref = {
    ref: { project_key: 'nav_alpha', module_id: 'graph', namespace: 'hk', type_id: element.type_id, local_id: element.local_id },
    observed_revision: revision,
    content_digest: `${element.local_id}-digest`,
  }
  return {
    ref,
    attributes: { structural_role: element.structural_role ?? 'element', ...element.attributes },
    endpoints: (element.endpoints || []).map((endpoint) => ({
      role: endpoint.role,
      target: {
        ref: {
          project_key: 'nav_alpha',
          module_id: 'graph',
          namespace: 'hk',
          type_id: endpoint.target.type_id,
          local_id: endpoint.target.local_id,
        },
        observed_revision: revision,
        content_digest: `${endpoint.target.local_id}-digest`,
      },
    })),
  }
}

function topologyItems(hiddenProduct: boolean, changedSource = false) {
  const elements = [
    topologyElement({ type_id: 'domain_vocabulary', local_id: 'vocabulary', structural_role: 'annotation', attributes: {
      name: 'HK retrieval',
      edge_types: ['belongs_to', 'regulated_by'],
      edge_style_bindings: { belongs_to: { width: 2 } },
    } }),
    topologyElement({ type_id: 'product', local_id: 'product-1', attributes: { name: 'Harbour product' } }),
    topologyElement({ type_id: 'company', local_id: 'company-1', attributes: { name: 'Harbour company' } }),
    topologyElement({ type_id: 'operation', local_id: 'operation-new', attributes: { name: 'New operation' } }),
    topologyElement({
      type_id: 'belongs_to',
      local_id: 'relation-1',
      structural_role: 'relation',
      attributes: { relation_token: 'belongs_to', relation_axis: ['from', 'to'] },
      endpoints: [
        { role: 'from', target: { type_id: 'product', local_id: 'product-1' } },
        { role: 'to', target: { type_id: 'company', local_id: 'company-1' } },
      ],
    }),
  ]
  if (changedSource) {
    elements.push(topologyElement({ type_id: 'company', local_id: 'company-refresh', attributes: { name: 'Refreshed company' } }))
  }
  if (hiddenProduct) return elements.filter((element) => element.ref.ref.local_id !== 'product-1')
  if (changedSource) {
    return elements.filter((element) => {
      const localId = element.ref.ref.local_id
      return localId !== 'product-1' && localId !== 'relation-1'
    })
  }
  return elements
}

async function setupGraphWorkbench(page: Page, options: { activationFailures?: number } = {}) {
  const requests: ApiRecord[] = []
  const savedVersions: string[] = []
  const savedVersionDsl = new Map<string, unknown>()
  let savedDsl: unknown
  let savedTemplateKey: string | null = null
  let templateCreated = false
  let templateCreateCount = 0
  let versionSaveCount = 0
  let activationAttempts = 0
  let sourceActivated = false
  let legacySnapshotRead = false
  let sourceRead = 0
  let activationFailuresRemaining = options.activationFailures || 0
  const sourceState = { hiddenProduct: false, changedSource: false, sourceMode: 'topology' as 'topology' | 'admin' }
  const forbidden: string[] = []

  await page.addInitScript(() => {
    localStorage.setItem('market_project_key', 'nav_alpha')
    localStorage.setItem('app_theme_v1', 'dark')
    localStorage.setItem('app_locale_v1', 'en-US')
  })

  const ok = async (route: Route, data: unknown) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok', data }),
  })

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const project = request.headers()['x-project-key']
    requests.push({ method, path, project })
    if (/curated|publish|\/template\/stage|\/promote|\/runs?\/|workflows\/.*\/run/.test(path)) forbidden.push(`${method} ${path}`)
    if (path === '/api/v1/health') return ok(route, { status: 'ok' })
    if (path === '/api/v1/health/deep') return ok(route, { database: 'ok' })
    if (path === '/api/v1/config/env') return ok(route, { DATABASE_URL: 'mock', OPENAI_API_KEY: 'mock' })
    if (path === '/api/v1/projects') return ok(route, { items: [{ project_key: 'nav_alpha', name: 'NAV Alpha', enabled: true }] })
    if (path === '/api/v1/codex-auth/status') return ok(route, { authenticated: false, codex_oauth_enabled: true })
    if (/\/projects\/nav_alpha\/activate$/.test(path)) return ok(route, { activated: true })
    if (path === '/api/v1/project-customization/graph-config') {
      return ok(route, {
        graph_node_types: { market: ['product', 'company', 'operation'] },
        graph_node_labels: { product: 'Product', company: 'Company', operation: 'Operation' },
        graph_relation_labels: { belongs_to: 'belongs to', regulated_by: 'regulated by' },
      })
    }
    if (path === '/api/v1/information-topology/topologies') {
      sourceRead += 1
      if (sourceState.sourceMode === 'admin') return ok(route, { items: [], total: 0 })
      const items = topologyItems(sourceState.hiddenProduct, sourceState.changedSource)
      return ok(route, { items: [{
        topology_ref: { module_id: 'graph', namespace: 'hk', state_id: 'current' },
        profile_id: 'retrieval.domain.hk',
        profile_version: '1',
        revision: 2,
        digest: sourceState.hiddenProduct ? 'source-v2' : sourceState.changedSource ? 'source-refresh' : 'source-v1',
        element_count: items.length,
        topology: { profile_id: 'retrieval.domain.hk', profile_version: '1', elements: items },
      }], total: 1 })
    }
    if (path === '/api/v1/information-topology/topologies/read') return ok(route, { topology: { profile_id: 'retrieval.domain.hk', profile_version: '1', elements: [] }, revision: 2, digest: 'not-used' })
    if (/\/admin\/(market|policy|content|social)-graph$/.test(path)) {
      return ok(route, { nodes: [{ id: 'forbidden-source', type: 'product', name: 'forbidden source' }], edges: [] })
    }
    if (path === '/api/v1/workflow-graph/templates' && method === 'POST') {
      const body = request.postDataJSON()
      templateCreated = true
      templateCreateCount += 1
      savedTemplateKey = body.template_id
      expect(body.template_id).toMatch(/^view-/)
      expect(typeof body.name).toBe('string')
      expect(body.name.trim()).not.toBe('')
      return ok(route, { template: { template_id: body.template_id, name: body.name, active_version_id: null }, template_id: body.template_id, created: true })
    }
    if (path === '/api/v1/workflow-graph/templates') {
      return ok(route, {
        items: templateCreated
          ? [{ template_id: savedTemplateKey, name: 'Project view', active_version_id: savedVersions.at(-1) || null }]
          : [{ template_id: 'alpha-water', name: 'Legacy water', active_version_id: 'v-active' }],
      })
    }
    if (/\/workflow-graph\/templates\/alpha-water\/versions$/.test(path)) {
      return ok(route, { active_version_id: 'v-active', items: [{ version_id: 'v-active', version_name: 'Active version', activated: true }] })
    }
    if (/\/workflow-graph\/templates\/[^/]+\/versions$/.test(path) && method === 'POST') {
      const body = request.postDataJSON()
      versionSaveCount += 1
      const versionKey = `v-${versionSaveCount}`
      savedDsl = body.dsl
      savedVersionDsl.set(versionKey, body.dsl)
      savedVersions.push(versionKey)
      return ok(route, { template_id: savedTemplateKey, version_id: versionKey, version: { version_id: versionKey, dsl: body.dsl }, created: true })
    }
    if (/\/workflow-graph\/templates\/[^/]+\/versions\/v-\d+\/activate$/.test(path) && method === 'POST') {
      activationAttempts += 1
      if (activationFailuresRemaining > 0) {
        activationFailuresRemaining -= 1
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'activation unavailable' }) })
        return
      }
      sourceActivated = true
      return ok(route, { template_id: savedTemplateKey, version_id: savedVersions.at(-1), activated: true })
    }
    if (/\/workflow-graph\/templates\/[^/]+\/versions$/.test(path)) {
      return ok(route, {
        active_version_id: savedVersions.at(-1) || null,
        items: savedVersions.map((version_id, index) => ({ version_id, version_name: `Saved view ${index + 1}`, activated: index === savedVersions.length - 1 })),
      })
    }
    const savedVersionPath = path.match(/\/workflow-graph\/templates\/[^/]+\/versions\/(v-\d+)$/)
    if (savedVersionPath && method === 'GET') {
      const versionKey = savedVersionPath[1]
      return ok(route, {
        template_id: savedTemplateKey,
        version_id: versionKey,
        version: { version_id: versionKey, dsl: savedVersionDsl.get(versionKey) },
      })
    }
    if (/\/workflow-graph\/templates\/alpha-water\/versions\/v-active$/.test(path) && method === 'GET') {
      legacySnapshotRead = true
      return ok(route, {
        template_id: 'alpha-water',
        version_id: 'v-active',
        version: { version_id: 'v-active', dsl: { nodes: [node('snapshot-1', 'product'), node('snapshot-2', 'company')], edges: [] } },
      })
    }
    if (/\/workflow-graph\/templates\/alpha-water/.test(path)) {
      return ok(route, { items: [{ template_id: 'alpha-water', name: 'Legacy water', active_version_id: 'v-active' }] })
    }
    return ok(route, { items: [] })
  })

  return {
    get templateCreateCount() { return templateCreateCount },
    get versionSaveCount() { return versionSaveCount },
    get savedVersions() { return savedVersions },
    get savedTemplateKey() { return savedTemplateKey },
    get activationAttempts() { return activationAttempts },
    get forbidden() { return forbidden },
    get savedDsl() { return savedDsl },
    get sourceActivated() { return sourceActivated },
    get sourceRead() { return sourceRead },
    setSourceMode(mode: 'topology' | 'admin') {
      sourceState.sourceMode = mode
    },
    markSourceChanged() {
      sourceState.changedSource = true
    },
    markSourceHidden() {
      sourceState.hiddenProduct = true
    },
    get legacySnapshotRead() { return legacySnapshotRead },
    get requests() { return requests },
  }
}

const checkedType = (page: Page, type: string) => page.locator(`[data-testid="graph-view-type-${type}"] input, input[data-testid="graph-view-type-${type}"]`)

async function optionValueByText(panel: Locator, text: string) {
  const escaped = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const option = panel.getByRole('option', { name: new RegExp(`^${escaped}\\s*\\(`) }).first()
  const value = await option.getAttribute('value')
  expect(value).toBeTruthy()
  return value as string
}

async function addInstanceExtras(page: Page) {
  const controls = page.locator('.gv2-floating-controls')
  await controls.getByLabel('New Node Type', { exact: true }).fill('watchpoint')
  await controls.getByLabel('New Node Name', { exact: true }).fill('Custom watchpoint')
  await controls.getByRole('button', { name: 'Add Node', exact: true }).click()
  await controls.getByLabel('Edge Source').selectOption(await optionValueByText(controls, 'Custom watchpoint'))
  await controls.getByLabel('Edge Target').selectOption(await optionValueByText(controls, 'Harbour company'))
  await controls.getByLabel('Relation', { exact: true }).fill('supervises')
  await controls.getByRole('button', { name: 'Create Edge source->target', exact: true }).click()
}

test('project topology hides unsupported business filters and retains local graph controls', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  for (const view of ['builder', 'policy', 'social']) {
    await page.goto(`/#/visual/graph/${view}`)
    if (view === 'builder') {
      await page.getByTestId('graph-view-advanced-toggle').click()
    } else {
      const panelToggle = page.getByRole('button', { name: /^(Expand|Collapse) Panel$/ })
      await expect(panelToggle).toBeVisible()
      if (await panelToggle.textContent() === 'Expand Panel') await panelToggle.click()
      await expect(panelToggle).toHaveText('Collapse Panel')
    }
    const controls = page.locator('.gv2-floating-controls')
    await expect(controls.getByRole('slider', { name: /^Limit\s*\d+$/ })).toBeVisible()
    await expect(controls.getByRole('combobox', { name: 'Ranking Strategy', exact: true })).toBeVisible()
    await expect(controls.getByRole('button', { name: 'Apply Filters', exact: true })).toBeEnabled()
    await expect.poll(() => state.sourceRead).toBeGreaterThan(0)
    for (const label of ['Start Date', 'End Date', 'State', 'Policy Type', 'Platform', 'Topic', 'Game']) {
      await expect(controls.getByLabel(label, { exact: true })).toHaveCount(0)
    }

    if (view === 'builder') {
      await page.getByTestId('graph-view-projection-toggle').click()
      await expect(checkedType(page, 'ProductEntity')).toBeVisible()
      await expect(page.getByRole('group', { name: 'Relation types', exact: true }).getByRole('checkbox').first()).toBeVisible()
      await checkedType(page, 'ProductEntity').uncheck()
      await expect(checkedType(page, 'ProductEntity')).not.toBeChecked()
      await checkedType(page, 'ProductEntity').check()
    }
  }
  expect(state.requests.filter((request) => /\/admin\/(market|policy|content|social)-graph$/.test(request.path))).toEqual([])
})

test('builder saves a filtered project view and reopens it against current source', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder')
  await expect(page.getByTestId('graph-view-projection-toggle')).toBeVisible()
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByTestId('graph-view-advanced-toggle')).toHaveAttribute('aria-pressed', 'true')
  const templateSelection = page.getByTestId('graph-template-select')
  await expect(templateSelection).toBeVisible()
  await expect(templateSelection).toHaveValue('')
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByTestId('graph-view-advanced-toggle')).toHaveAttribute('aria-pressed', 'false')

  await page.getByTestId('graph-view-projection-toggle').click()
  await expect(page.getByTestId('graph-view-mode-all')).toBeVisible()
  await page.getByTestId('graph-view-mode-all').click()
  await checkedType(page, 'ProductEntity').uncheck()
  await expect(page.getByTestId('graph-view-node-toggle')).toBeVisible()
  await expect(page.getByTestId('graph-view-edge-toggle')).toBeVisible()

  await page.getByTestId('graph-view-save-toggle').click()
  await page.getByTestId('graph-view-name').fill('Project view')
  await page.getByTestId('graph-view-save').click()

  await expect.poll(() => state.savedVersions).toEqual(['v-1'])
  await expect.poll(() => state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
  expect(state.savedDsl).toEqual(expect.objectContaining({
    nodes: expect.any(Array),
    edges: expect.any(Array),
    project_view: expect.objectContaining({
      schema: 'project-graph-view/v1',
      mode: 'all',
      hiddenNodeTypes: expect.arrayContaining(['ProductEntity']),
    }),
  }))
  expect(state.sourceActivated).toBe(true)
  expect(state.forbidden).toEqual([])
  expect(state.requests.filter((request) => /\/admin\/(market|policy|content|social)-graph$/.test(request.path))).toEqual([])
  expect(state.requests.filter((request) => /curated|publish|\/template\/stage|\/promote|\/runs?\/|workflows\/.*\/run/.test(request.path))).toEqual([])

  state.markSourceChanged()
  await page.goto(`/#/visual/graph/builder?template=${state.savedTemplateKey}&version=v-1`)
  await page.reload()
  await expect(page.getByTestId('graph-view-projection-toggle')).toHaveAttribute('aria-expanded', /true|false/)
  await page.getByTestId('graph-view-projection-toggle').click()
  await expect(checkedType(page, 'ProductEntity')).not.toBeChecked()
  await expect(checkedType(page, 'operation')).toBeChecked()
  await page.getByTestId('graph-view-edge-toggle').click()
  await expect(page.getByRole('dialog', { name: 'Add relation type' }).getByLabel('Source type')
    .locator('option[value="company"]')).toHaveCount(1)
  expect(state.sourceRead).toBeGreaterThanOrEqual(2)
  expect(state.forbidden).toEqual([])
})

test('saving an active project view appends a version without creating another template', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder')
  await page.getByTestId('graph-view-save-toggle').click()
  await page.getByTestId('graph-view-name').fill('Project view')
  await page.getByTestId('graph-view-save').click()

  await expect.poll(() => state.savedVersions).toEqual(['v-1'])
  await expect.poll(() => state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
  expect(state.templateCreateCount).toBe(1)
  expect(state.sourceActivated).toBe(true)

  await expect(page.getByTestId('graph-view-name')).toHaveValue('Project view')
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
  await page.getByTestId('graph-view-save').click()

  await expect.poll(() => state.savedVersions).toEqual(['v-1', 'v-2'])
  await expect.poll(() => state.activationAttempts).toBe(2)
  await expect.poll(() => state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
  expect(state.templateCreateCount).toBe(1)
  expect(state.versionSaveCount).toBe(2)
  expect(state.activationAttempts).toBe(2)
  expect(state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
})

test('a failed activation retry appends once while retaining the created template identity', async ({ page }) => {
  const state = await setupGraphWorkbench(page, { activationFailures: 1 })
  await page.goto('/#/visual/graph/builder')
  await page.getByTestId('graph-view-save-toggle').click()
  await page.getByTestId('graph-view-name').fill('Retry view')
  await page.getByTestId('graph-view-save').click()

  await expect.poll(() => state.activationAttempts).toBe(1)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
  expect(state.templateCreateCount).toBe(1)
  expect(state.savedVersions).toEqual(['v-1'])
  expect(state.sourceActivated).toBe(false)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()

  await page.getByTestId('graph-view-save').click()
  await expect.poll(() => state.activationAttempts).toBe(2)
  await expect.poll(() => state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
  expect(state.templateCreateCount).toBe(1)
  expect(state.versionSaveCount).toBe(2)
  expect(state.savedVersions).toEqual(['v-1', 'v-2'])
  expect(state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()
})

test('custom nodes and relations remain local additions through save and reload', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder')

  await page.getByTestId('graph-view-advanced-toggle').click()
  await addInstanceExtras(page)
  await expect(page.getByTestId('graph-view-advanced-toggle')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText(/Draft: nodes=4 edges=2/)).toBeVisible()

  await page.getByTestId('graph-view-save-toggle').click()
  await page.getByTestId('graph-view-name').fill('Custom extras')
  await page.getByTestId('graph-view-save').click()
  await expect.poll(() => state.savedVersions).toEqual(['v-1'])
  await expect.poll(() => state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()

  expect(state.savedDsl).toEqual(expect.objectContaining({
    nodes: expect.arrayContaining([
      expect.objectContaining({ type: 'watchpoint', name: 'Custom watchpoint' }),
    ]),
    edges: expect.arrayContaining([
      expect.objectContaining({ predicate: 'supervises' }),
    ]),
    project_view: expect.objectContaining({
      additionalNodes: expect.arrayContaining([
        expect.objectContaining({ type: 'watchpoint', name: 'Custom watchpoint' }),
      ]),
      additionalEdges: expect.arrayContaining([
        expect.objectContaining({ predicate: 'supervises' }),
      ]),
    }),
  }))
  await expect(page.getByText(/Draft: nodes=4 edges=2/)).toBeVisible()

  await page.goto(`/#/visual/graph/builder?template=${state.savedTemplateKey}&version=v-1`)
  await page.reload()
  await expect(page.getByTestId('graph-view-advanced-toggle')).toBeVisible()
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByText(/Draft: nodes=4 edges=2/)).toBeVisible()
})

test('builder defines types without adding instances and reads them back after save', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder')
  await expect(page.getByTestId('graph-type-view')).toBeVisible()
  await page.getByTestId('graph-view-node-toggle').click()
  const nodePanel = page.getByRole('dialog', { name: 'Add node type' })
  await expect(nodePanel.getByLabel('New Node Name')).toHaveCount(0)
  await nodePanel.getByLabel('New Node Type').fill('watchpoint')
  await nodePanel.getByRole('button', { name: 'Add node type', exact: true }).click()
  await expect(nodePanel.getByRole('status')).toHaveText('Type added, pending save')
  await page.getByTestId('graph-view-edge-toggle').click()
  const edgePanel = page.getByRole('dialog', { name: 'Add relation type' })
  await expect(edgePanel.getByLabel('Edge Source')).toHaveCount(0)
  await edgePanel.getByLabel('Source type').selectOption('watchpoint')
  await edgePanel.getByLabel('Target type').selectOption('company')
  await edgePanel.getByLabel('Relation', { exact: true }).fill('supervises')
  await edgePanel.getByRole('button', { name: 'Add relation type', exact: true }).click()
  await expect(edgePanel.getByRole('status')).toHaveText('Type added, pending save')

  await page.getByTestId('graph-view-save-toggle').click()
  await page.getByTestId('graph-view-name').fill('Type definitions')
  await page.getByTestId('graph-view-save').click()
  await expect.poll(() => state.sourceActivated).toBe(true)
  expect(state.savedDsl).toEqual(expect.objectContaining({
    nodes: expect.any(Array), edges: expect.any(Array),
    project_view: expect.objectContaining({
      declaredNodeTypes: ['watchpoint'],
      declaredRelationTypes: [{ sourceType: 'watchpoint', targetType: 'company', relation: 'supervises' }],
      additionalNodes: [], additionalEdges: [],
    }),
  }))
  const saved = state.savedDsl as { nodes: unknown[]; edges: unknown[] }
  expect(saved.nodes).toHaveLength(3)
  expect(saved.edges).toHaveLength(1)
  expect(state.forbidden).toEqual([])
  await page.goto(`/#/visual/graph/builder?template=${state.savedTemplateKey}&version=v-1`)
  await page.reload()
  await page.getByTestId('graph-view-edge-toggle').click()
  await expect(page.getByRole('dialog', { name: 'Add relation type' }).getByLabel('Source type').locator('option[value="watchpoint"]')).toHaveCount(1)
  await expect(page.getByTestId('graph-type-view')).toContainText('supervises')
  await page.getByTestId('graph-view-projection-toggle').click()
  await checkedType(page, 'watchpoint').uncheck()
  await expect(page.getByTestId('graph-type-view')).not.toContainText('supervises')
  await checkedType(page, 'watchpoint').check()
  await expect(page.getByTestId('graph-type-view')).toContainText('supervises')
})

test('type graph is separately framed below the instance view and renders at desktop and mobile sizes', async ({ page }, testInfo) => {
  await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder')
  for (const width of [1333, 390]) {
    await page.setViewportSize({ width, height: 977 })
    const chart = page.getByTestId('graph-type-chart')
    await chart.scrollIntoViewIfNeeded()
    await expect.poll(() => chart.evaluate((element) => {
      let colored = 0
      for (const canvas of element.querySelectorAll('canvas')) {
        const context = canvas.getContext('2d')
        if (!context) continue
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
        for (let index = 0; index < pixels.length; index += 16) {
          if (pixels[index + 3] > 0 && pixels[index] + pixels[index + 1] + pixels[index + 2] > 140) colored += 1
        }
      }
      return colored
    }), { timeout: 15000 }).toBeGreaterThan(100)
    const chartBox = await chart.boundingBox()
    const instanceBox = await page.locator('#graph-projection-panel').boundingBox()
    expect(chartBox!.y).toBeGreaterThan(instanceBox!.y + instanceBox!.height)
    expect(chartBox!.width).toBeGreaterThan(300)
    await expect(page.getByTestId('graph-type-view')).not.toContainText('Harbour product')
    await expect(page.getByTestId('graph-type-view')).toContainText('belongs_to')
    await expect(chart).toHaveAttribute('aria-description', /Operation/)
    await page.getByTestId('graph-type-relation-filter').selectOption('belongs_to')
    await expect(page.getByTestId('graph-type-relation-filter')).toHaveValue('belongs_to')
    await page.getByRole('button', { name: 'Fit view', exact: true }).click()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByTestId('graph-type-view').screenshot({ path: testInfo.outputPath(`type-graph-${width}.png`) })
    await page.getByTestId('graph-type-relation-filter').selectOption('')
  }
})

test('same-page source deletion and addition preserve unsaved custom extras', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder')
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByText(/Draft: nodes=3 edges=1/)).toBeVisible()

  await addInstanceExtras(page)
  await expect(page.getByText(/Draft: nodes=4 edges=2/)).toBeVisible()

  state.markSourceChanged()
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect.poll(() => state.sourceRead).toBeGreaterThanOrEqual(2)
  await expect(page.getByText(/Draft: nodes=4 edges=1/)).toBeVisible()

  await page.getByTestId('graph-view-save-toggle').click()
  await page.getByTestId('graph-view-name').fill('Refreshed additions')
  await page.getByTestId('graph-view-save').click()
  await expect.poll(() => state.savedVersions).toEqual(['v-1'])
  await expect.poll(() => state.sourceActivated).toBe(true)
  await expect(page.getByTestId('graph-view-save')).toBeEnabled()

  const dsl = state.savedDsl as {
    nodes: Array<Record<string, unknown>>
    edges: Array<Record<string, unknown>>
    project_view: {
      additionalNodes: Array<Record<string, unknown>>
      additionalEdges: Array<Record<string, unknown>>
    }
  }
  expect(dsl.nodes.some((item) => item.entry_id === 'product-1')).toBe(false)
  expect(dsl.nodes.some((item) => item.entry_id === 'company-refresh')).toBe(true)
  expect(dsl.project_view.additionalNodes).toEqual([
    expect.objectContaining({
      type: 'watchpoint',
      name: 'Custom watchpoint',
      id: expect.stringMatching(/^draft-/),
    }),
  ])
  expect(dsl.project_view.additionalEdges).toEqual([
    expect.objectContaining({ predicate: 'supervises' }),
  ])
})

test('same-page source refresh does not overwrite a loaded legacy snapshot', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder?template=alpha-water&version=v-active')
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByText(/Draft: nodes=2 edges=0/)).toBeVisible()

  state.setSourceMode('admin')
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect.poll(() => state.sourceRead).toBeGreaterThanOrEqual(2)
  await expect(page.getByText(/Draft: nodes=2 edges=0/)).toBeVisible()
})

test('legacy snapshot deep link retains saved DSL instead of substituting current source', async ({ page }) => {
  const state = await setupGraphWorkbench(page)
  await page.goto('/#/visual/graph/builder?template=alpha-water&version=v-active')
  await expect(page.getByTestId('graph-view-advanced-toggle')).toBeVisible()
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByTestId('graph-template-version-select')).toHaveValue('v-active')
  expect(state.legacySnapshotRead).toBe(true)
})

test('sidebar toggle changes graph width while retaining route and project context', async ({ page }) => {
  await setupGraphWorkbench(page)
  await page.setViewportSize({ width: 1333, height: 977 })
  await page.goto('/#/visual/graph/market')
  const toggle = page.getByTestId('visual-sidebar-toggle')
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('#visual-project-navigation')).toBeVisible()
  const expanded = await page.getByTestId('graph-chart-2d').boundingBox()
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(page.locator('#visual-project-navigation')).toBeHidden()
  const collapsed = await page.getByTestId('graph-chart-2d').boundingBox()
  expect(collapsed!.width).toBeGreaterThan(expanded!.width + 40)
  expect(collapsed!.x).toBeLessThan(expanded!.x)
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page).toHaveURL(/#\/visual\/graph\/market$/)
  await expect(page.locator('select.kernel-visual__project-field select, .kernel-visual__project-field select')).toHaveValue('nav_alpha')
})

async function resizePanel(page: Page, testId: string) {
  const scene = page.locator('#graph-projection-panel')
  const handle = page.getByTestId(testId)
  const panel = handle.locator('..')
  await expect(scene).toBeVisible()
  await expect(panel).toBeVisible()
  const sceneBox = await scene.boundingBox()
  let panelBox = await panel.boundingBox()
  const handleBox = await handle.boundingBox()
  expect(sceneBox).not.toBeNull()
  expect(panelBox).not.toBeNull()
  expect(handleBox).not.toBeNull()
  const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value))
  const dragOnce = async (sign: number) => {
    const currentHandle = await handle.boundingBox()
    const centerX = currentHandle!.x + currentHandle!.width / 2
    const centerY = currentHandle!.y + currentHandle!.height / 2
    await page.mouse.move(centerX, centerY)
    await page.mouse.down()
    await page.mouse.move(
      clamp(centerX + sign * 65, sceneBox!.x + 2, sceneBox!.x + sceneBox!.width - 2),
      clamp(centerY + sign * 45, sceneBox!.y + 2, sceneBox!.y + sceneBox!.height - 2),
      { steps: 5 },
    )
    await page.mouse.up()
  }

  const anchor = testId.includes('controls') ? 'right' : 'left'
  await dragOnce(anchor === 'right' ? -1 : 1)
  const afterPointerRetry = await panel.boundingBox()
  expect(
    afterPointerRetry!.width !== panelBox!.width ||
    afterPointerRetry!.height !== panelBox!.height,
  ).toBe(true)

  panelBox = await panel.boundingBox()
  const growLeft = anchor === 'left' ? 'ArrowRight' : 'ArrowLeft'
  const shrinkLeft = anchor === 'left' ? 'ArrowLeft' : 'ArrowRight'
  const widthRoom = anchor === 'left'
    ? sceneBox!.x + sceneBox!.width - 4 - (panelBox!.x + panelBox!.width)
    : panelBox!.x + panelBox!.width - sceneBox!.x - 4
  const primaryWidthKey = panelBox!.width + 16 <= widthRoom ? growLeft : shrinkLeft
  await handle.focus()
  await handle.press(primaryWidthKey)
  const afterKeyboardHorizontal = await panel.boundingBox()
  if (afterKeyboardHorizontal!.width === panelBox!.width) {
    await handle.focus()
    await handle.press(primaryWidthKey === growLeft ? shrinkLeft : growLeft)
  }
  expect((await panel.boundingBox())!.width).not.toBe(panelBox!.width)

  panelBox = await panel.boundingBox()
  const downRoom = sceneBox!.y + sceneBox!.height - 4 - (panelBox!.y + panelBox!.height)
  const upRoom = panelBox!.y + panelBox!.height - sceneBox!.y - 4
  const primaryHeightKey = panelBox!.height + 16 <= downRoom ? 'ArrowDown' : upRoom >= panelBox!.height + 16 ? 'ArrowUp' : 'ArrowUp'
  await handle.focus()
  await handle.press(primaryHeightKey)
  const afterKeyboardVertical = await panel.boundingBox()
  if (afterKeyboardVertical!.height === panelBox!.height) {
    await handle.focus()
    await handle.press(primaryHeightKey === 'ArrowDown' ? 'ArrowUp' : 'ArrowDown')
  }
  expect((await panel.boundingBox())!.height).not.toBe(panelBox!.height)

  const bounded = await panel.boundingBox()
  expect(bounded!.x).toBeGreaterThanOrEqual(sceneBox!.x - 1)
  expect(bounded!.y).toBeGreaterThanOrEqual(sceneBox!.y - 1)
  expect(bounded!.x + bounded!.width).toBeLessThanOrEqual(sceneBox!.x + sceneBox!.width + 1)
  expect(bounded!.y + bounded!.height).toBeLessThanOrEqual(sceneBox!.y + sceneBox!.height + 1)
}

test('projection panels resize through pointer and keyboard within the canvas', async ({ page }) => {
  await setupGraphWorkbench(page)
  await page.setViewportSize({ width: 1333, height: 977 })
  await page.goto('/#/visual/graph/market')
  await page.getByRole('button', { name: '3D Mode', exact: true }).click()
  await expect(page.locator('#graph-projection-panel')).toBeVisible()
  await expect(page.locator('.gv2-main')).toHaveCount(0)
  await expect(page.getByTestId('graph-topology-panel')).toHaveCount(0)
  await expect(page.locator('.gv2-root > #graph-projection-panel')).toBeVisible()
  for (const testId of ['graph-legend-resize', 'graph-controls-resize']) {
    await resizePanel(page, testId)
  }
})

test('graph shell stays within desktop and mobile viewports', async ({ page }, testInfo) => {
  await setupGraphWorkbench(page)
  await page.setViewportSize({ width: 1333, height: 977 })
  await page.goto('/#/visual/graph/market')
  await expect(page.getByTestId('graph-chart-2d')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('projection-desktop.png'), fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByTestId('graph-chart-2d')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  await page.screenshot({ path: testInfo.outputPath('projection-mobile.png'), fullPage: true })
})
