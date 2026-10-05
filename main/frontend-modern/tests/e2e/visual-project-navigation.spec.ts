import { expect, test, type Page, type Route } from '@playwright/test'
import { parseLegacyHashToMode } from '../../src/app/kernel/legacyHashAdapter'
import { buildGraphTemplateRoute, getGraphTemplateKeyFromHash, getGraphTemplateRouteFromHash } from '../../src/pages/graph/realizer/workspaceNavigation'

type Project = 'nav_alpha' | 'nav_beta'
type Template = { template_id: string; name: string; active_version_id: string }
type ApiRequest = { path: string; method: string; project: string; queryProject: string | null }

const graphModules = ['graphDeep', 'graphPolicy', 'graphMarket', 'graphSocial', 'graphCompany', 'graphProduct', 'graphOperation', 'graphBuilder']
const labels = {
  nav_alpha: ['Alpha total', 'Alpha policy', 'Alpha water', 'Create graph'],
  nav_beta: ['Beta total', 'Beta policy', 'Beta transport', 'Create graph'],
}

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data }) })
}

async function setup(page: Page, options: { betaTemplates?: 'empty' | 'error' } = {}) {
  const requests: ApiRequest[] = []
  const templates: Record<Project, Template[]> = {
    nav_alpha: [{ template_id: 'alpha-water', name: 'Alpha saved water', active_version_id: 'v-active' }],
    nav_beta: [{ template_id: 'beta-transport', name: 'Beta saved transport', active_version_id: 'v-active' }],
  }
  await page.addInitScript(() => {
    localStorage.setItem('market_project_key', 'nav_alpha')
    localStorage.setItem('app_theme_v1', 'dark')
    localStorage.setItem('app_locale_v1', 'en-US')
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const project = request.headers()['x-project-key'] as Project
    requests.push({ path, method: request.method(), project, queryProject: url.searchParams.get('project_key') })
    if (path === '/api/v1/health') return json(route, { status: 'ok', provider: 'mock' })
    if (path === '/api/v1/health/deep') return json(route, { database: 'ok' })
    if (path === '/api/v1/config/env') return json(route, { DATABASE_URL: 'mock', OPENAI_API_KEY: 'mock' })
    if (path === '/api/v1/projects') return json(route, { items: Object.keys(templates).map((project_key) => ({ project_key, name: project_key, enabled: true })) })
    if (/\/projects\/[^/]+\/activate$/.test(path)) return json(route, { activated: true })
    if (path === '/api/v1/codex-auth/status') return json(route, { authenticated: false, codex_oauth_enabled: true })
    if (path === '/api/v1/project-customization/graph-config') {
      const names = labels[project] || labels.nav_alpha
      return json(route, {
        graph_node_types: { market: ['product', 'company'] },
        graph_projections: graphModules.map((id) => ({
          id,
          label: id === 'graphDeep' ? names[0] : id === 'graphPolicy' ? names[1] : id === 'graphMarket' ? names[2] : names[3],
          hidden: !['graphDeep', 'graphPolicy', 'graphMarket', 'graphBuilder'].includes(id),
        })),
      })
    }
    if (path === '/api/v1/information-topology/topologies/read') {
      return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: { error: { code: 'NOT_FOUND', message: 'No topology' } } }) })
    }
    if (/\/admin\/(market|policy|content)-graph$/.test(path)) {
      return json(route, { nodes: [{ id: 'base-node', type: 'product', name: `${project} source node` }], edges: [] })
    }
    if (path === '/api/v1/workflow-graph/templates') {
      if (request.method() === 'POST') {
        const body = request.postDataJSON() as { template_id: string; name: string }
        templates[project].push({ ...body, active_version_id: 'v-active' })
        return json(route, { template_id: body.template_id, created: true })
      }
      if (project === 'nav_beta' && options.betaTemplates === 'error') {
        return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Template service unavailable' }) })
      }
      return json(route, { items: project === 'nav_beta' && options.betaTemplates === 'empty' ? [] : templates[project] || [] })
    }
    const templatePath = path.match(/^\/api\/v1\/workflow-graph\/templates\/([^/]+)(?:\/versions(?:\/([^/]+))?)?$/)
    if (templatePath) {
      const templateId = decodeURIComponent(templatePath[1])
      const versionId = templatePath[2]
      if (request.method() === 'PATCH') {
        const item = templates[project].find((entry) => entry.template_id === templateId)
        if (item) item.name = (request.postDataJSON() as { name: string }).name
        return json(route, { template_id: templateId, updated: true })
      }
      if (request.method() === 'DELETE') {
        templates[project] = templates[project].filter((entry) => entry.template_id !== templateId)
        return json(route, { template_id: templateId, deleted: true })
      }
      if (versionId) {
        return json(route, {
          template_id: templateId,
          version_id: versionId,
          version: {
            version_id: versionId,
            dsl: {
              nodes: Array.from({ length: versionId === 'v-previous' ? 5 : project === 'nav_alpha' ? 3 : 2 }, (_, index) => ({ id: `${templateId}-${index}`, type: 'product', name: `${templateId} saved node ${index}` })),
              edges: [],
            },
          },
        })
      }
      return json(route, { active_version_id: 'v-active', items: [
        { version_id: 'v-active', version_name: 'Saved version', activated: true },
        { version_id: 'v-previous', version_name: 'Previous version', activated: false },
      ] })
    }
    return json(route, { items: [], total: 0 })
  })
  return { requests, templates }
}

function sidebar(page: Page) {
  return page.locator('.kernel-visual__sidebar')
}

async function switchProject(page: Page, project: Project) {
  const control = page.locator('.kernel-visual__project-switch')
  await control.locator('select').selectOption(project)
  await control.locator('button').click()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('market_project_key'))).toBe(project)
}

test('legacy topic dashboard URLs retain their topic-specific destination', () => {
  for (const [topic, moduleKey] of [
    ['company', 'graphCompany'], ['product', 'graphProduct'], ['commodity', 'graphProduct'],
    ['operation', 'graphOperation'], ['ecom', 'graphOperation'], ['policy', 'dataPolicy'],
    ['social', 'dataSocial'], ['public-opinion', 'dataSocial'], ['market', 'dataMarket'],
  ]) {
    expect(parseLegacyHashToMode(`#topic-dashboard.html?topic=${topic}`)).toBe(moduleKey)
  }
  expect(parseLegacyHashToMode('#topic-dashboard.html')).toBe('dataCatalog')
  expect(parseLegacyHashToMode('#dashboard.html#market')).toBe('dataMarket')
  expect(parseLegacyHashToMode('#dashboard.html')).toBe('dataDashboard')
})

test('saved graph route round trips template and version identities', () => {
  const templateKey = 'Water & Energy/A'
  const versionKey = 'Review #2 + revised'
  const hash = `#${buildGraphTemplateRoute(templateKey, versionKey)}`
  expect(getGraphTemplateRouteFromHash(hash)).toEqual({ templateKey, versionKey })
  expect(getGraphTemplateKeyFromHash(hash)).toBe(templateKey)
  expect(getGraphTemplateRouteFromHash(`#${buildGraphTemplateRoute(templateKey)}`)).toEqual({ templateKey, versionKey: '' })
  expect(getGraphTemplateRouteFromHash('#/visual/graph/builder?version=v1')).toEqual({ templateKey: '', versionKey: '' })
  expect(getGraphTemplateRouteFromHash('#/visual/graph/market?template=A&version=v1')).toEqual({ templateKey: '', versionKey: '' })
})

test('project projection bindings drive sidebar labels, order, visibility and tab navigation', async ({ page }) => {
  await setup(page)
  await page.goto('/#/visual/graph/market')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Alpha water')
  await expect(page.locator('.gv2-projection-tabs [role="tab"]')).toHaveText(labels.nav_alpha)
  const visibleProjections = sidebar(page).locator('.kernel-visual__section').filter({ has: page.getByRole('button', { name: 'Alpha total', exact: true }) })
  await expect(visibleProjections.getByRole('button')).toHaveText(labels.nav_alpha)
  await expect(sidebar(page).getByRole('button', { name: 'Alpha saved water', exact: true })).toBeVisible()
  for (const module of ['graphSocial', 'graphCompany', 'graphProduct', 'graphOperation']) {
    await expect(page.getByTestId(`graph-workspace-tab-${module}`)).toHaveCount(0)
  }
  await sidebar(page).getByRole('button', { name: 'Alpha policy', exact: true }).click()
  await expect(page).toHaveURL(/#\/visual\/graph\/policy$/)
  await expect(page.getByTestId('graph-workspace-tab-graphPolicy')).toHaveAttribute('aria-selected', 'true')
})

test('a direct market route remains usable when all project projections are hidden', async ({ page }) => {
  await setup(page)
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.route('**/project-customization/graph-config**', async (route) => {
    await json(route, {
      graph_node_types: { market: ['product', 'company'] },
      graph_projections: graphModules.map((id) => ({
        id,
        label: id === 'graphMarket' ? 'Hidden market binding' : `Hidden ${id}`,
        hidden: true,
      })),
    })
  })
  await page.goto('/#/visual/graph/market')
  await expect(page.locator('.gv2-root')).toBeVisible()
  await expect(page.locator('.gv2-macro-stat strong').nth(0)).toHaveText('Hidden market binding')
  await expect(page.locator('.gv2-macro-stat strong').nth(1)).toHaveText('1')
  await expect(page.locator('.gv2-projection-tabs [role="tab"]')).toHaveCount(0)
  await expect(page).toHaveURL(/#\/visual\/graph\/market$/)
  expect(pageErrors).toEqual([])
})

test('a hidden current projection retains its own label and topology filter', async ({ page }) => {
  const state = await setup(page)
  await page.route('**/project-customization/graph-config**', async (route) => {
    await json(route, {
      graph_node_types: { market: ['product'] },
      graph_projections: graphModules.map((id) => ({
        id,
        label: id === 'graphMarket' ? 'Hidden water view' : 'Visible transport view',
        hidden: id !== 'graphDeep',
        topology_filter: { attribute: 'sector', contains_any: [id === 'graphMarket' ? 'water' : 'transport'] },
      })),
    })
  })
  await page.route(/\/information-topology\/topologies(?:\?.*)?$/, async (route) => {
    const elements = ['water', 'water', 'transport'].map((sector, index) => ({
      ref: {
        ref: { project_key: 'nav_alpha', module_id: 'graph', namespace: 'navigation', type_id: 'product', local_id: `sector-${index}` },
        observed_revision: '1',
        content_digest: `sector-${index}-digest`,
      },
      attributes: { structural_role: 'element', name: `${sector} product ${index}`, sector },
      endpoints: [],
    }))
    await json(route, { items: [{
      topology_ref: { module_id: 'graph', namespace: 'navigation', state_id: 'current' },
      profile_id: 'retrieval.domain.navigation',
      profile_version: '1',
      revision: 1,
      digest: 'navigation-sectors',
      element_count: elements.length,
      topology: { profile_id: 'retrieval.domain.navigation', profile_version: '1', elements },
    }], total: 1 })
  })
  await page.goto('/#/visual/graph/market')
  await expect(sidebar(page).getByRole('button', { name: 'Visible transport view', exact: true })).toBeVisible()
  await expect(page.locator('.gv2-projection-tabs [role="tab"]')).toHaveCount(0)
  await expect(page.getByTestId('graph-workspace-tab-graphMarket')).toHaveCount(0)
  await expect(page.locator('.gv2-macro-stat strong').nth(0)).toHaveText('Hidden water view')
  // Own binding keeps two water nodes; the first visible binding keeps one,
  // and dropping the filter would retain all three.
  await expect(page.locator('.gv2-macro-stat strong').nth(1)).toHaveText('2')
  await expect(page).toHaveURL(/#\/visual\/graph\/market$/)
  expect(state.requests.filter((request) => /\/admin\/(market|policy|content)-graph$/.test(request.path))).toEqual([])
})

test('switching projects replaces both projection and saved-template navigation with scoped requests', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/#/visual/dashboard')
  await expect(sidebar(page).getByRole('button', { name: 'Alpha saved water', exact: true })).toBeVisible()
  await switchProject(page, 'nav_beta')
  await expect(sidebar(page).getByRole('button', { name: 'Beta saved transport', exact: true })).toBeVisible()
  await expect(sidebar(page)).not.toContainText('Alpha')
  await sidebar(page).getByRole('button', { name: 'Beta transport', exact: true }).click()
  await expect(page.locator('.gv2-projection-tabs [role="tab"]')).toHaveText(labels.nav_beta)
  const projectReads = state.requests.filter((entry) => entry.path === '/api/v1/project-customization/graph-config' || entry.path === '/api/v1/workflow-graph/templates')
  expect(new Set(projectReads.map((entry) => entry.project))).toEqual(new Set(['nav_alpha', 'nav_beta']))
  for (const entry of projectReads) expect(entry.queryProject).toBe(entry.project)
})

test('saved-template navigation opens the requested active version and draft', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/#/visual/dashboard')
  await sidebar(page).getByRole('button', { name: 'Alpha saved water', exact: true }).click()
  await expect(page).toHaveURL(/#\/visual\/graph\/builder\?template=alpha-water$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Alpha saved water')
  await expect(page.getByTestId('graph-template-select')).toHaveValue('alpha-water')
  await expect(page.getByTestId('graph-template-version-select')).toHaveValue('v-active')
  const advanced = page.getByTestId('graph-view-advanced-toggle')
  if (await advanced.isVisible()) await advanced.click()
  await expect(page.getByText(/Draft: nodes=3 edges=0/)).toBeVisible()
  expect(state.requests.some((entry) => entry.path.endsWith('/templates/alpha-water/versions/v-active') && entry.project === 'nav_alpha')).toBe(true)
})

test('explicit saved-template versions reload when only the route version changes', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/#/visual/graph/builder?template=alpha-water&version=v-previous')
  await page.getByTestId('graph-view-advanced-toggle').click()
  await expect(page.getByTestId('graph-template-version-select')).toHaveValue('v-previous')
  await expect(page.getByText(/Draft: nodes=5 edges=0/)).toBeVisible()
  expect(state.requests.some((entry) => entry.path.endsWith('/templates/alpha-water/versions/v-active'))).toBe(false)

  await page.evaluate(() => { window.location.hash = '#/visual/graph/builder?template=alpha-water&version=v-active' })
  await expect(page.getByTestId('graph-template-version-select')).toHaveValue('v-active')
  await expect(page.getByText(/Draft: nodes=3 edges=0/)).toBeVisible()
  await page.evaluate(() => { window.location.hash = '#/visual/graph/builder?template=alpha-water&version=v-previous' })
  await expect(page.getByTestId('graph-template-version-select')).toHaveValue('v-previous')
  await expect(page.getByText(/Draft: nodes=5 edges=0/)).toBeVisible()
})

for (const kind of ['legacy', 'project-view'] as const) {
  test(`creating a graph after a saved ${kind} clears the loaded view without reloading the page`, async ({ page }) => {
    await setup(page)
    if (kind === 'project-view') {
      await page.route('**/workflow-graph/templates/alpha-water/versions/v-active**', async (route) => {
        await json(route, { version: { dsl: { project_view: {
          schema: 'project-graph-view/v1',
          mode: 'selection',
          nodeKeys: [],
          hiddenNodeTypes: ['product'],
          hiddenEdgeKinds: [],
          additionalNodes: [{ id: 'saved-extra', type: 'company', name: 'Saved extra' }],
          additionalEdges: [],
        } } } })
      })
    }
    await page.goto('/#/visual/graph/builder?template=alpha-water')
    await page.getByTestId('graph-view-advanced-toggle').click()
    await expect(page.getByTestId('graph-template-select')).toHaveValue('alpha-water')
    await expect(page.getByText(kind === 'legacy' ? /Draft: nodes=3 edges=0/ : /Draft: nodes=2 edges=0/)).toBeVisible()
    if (kind === 'project-view') {
      await page.getByTestId('graph-view-projection-toggle').click()
      await expect(page.getByTestId('graph-view-mode-selection')).toHaveAttribute('aria-pressed', 'true')
      await page.getByTestId('graph-view-projection-toggle').click()
    }
    await sidebar(page).getByRole('button', { name: 'Create graph', exact: true }).click()
    await expect(page).toHaveURL(/#\/visual\/graph\/builder$/)
    await expect(page.getByTestId('graph-view-advanced-toggle')).toHaveAttribute('aria-pressed', 'false')
    await page.getByTestId('graph-view-advanced-toggle').click()
    await expect(page.getByTestId('graph-template-select')).toHaveValue('')
    await expect(page.getByText(/Draft: nodes=1 edges=0/)).toBeVisible()
    if (kind === 'project-view') {
      await page.getByTestId('graph-view-projection-toggle').click()
      await expect(page.getByTestId('graph-view-mode-all')).toHaveAttribute('aria-pressed', 'true')
      await expect(page.getByTestId('graph-view-type-ProductEntity')).toBeChecked()
    }
  })
}

test('template create, rename and delete refresh sidebar without a page reload', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/#/visual/graph/builder?template=alpha-water')
  const advanced = page.getByTestId('graph-view-advanced-toggle')
  if (await advanced.isVisible()) await advanced.click()
  await expect(page.getByTestId('graph-template-create-name')).toBeEnabled()
  await page.getByTestId('graph-template-create-name').fill('Created graph')
  await page.getByTestId('graph-template-create').click()
  await expect(sidebar(page).getByRole('button', { name: 'Created graph', exact: true })).toBeVisible()
  await sidebar(page).getByRole('button', { name: 'Created graph', exact: true }).click()
  await expect(page.getByTestId('graph-template-select')).toHaveValue('Created_graph')
  await expect(page.getByTestId('graph-template-rename-name')).toBeEnabled()
  await page.getByTestId('graph-template-rename-name').fill('Renamed saved graph')
  await page.getByTestId('graph-template-rename').click()
  await expect(sidebar(page).getByRole('button', { name: 'Renamed saved graph', exact: true })).toBeVisible()
  await expect(sidebar(page).getByRole('button', { name: 'Created graph', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Renamed saved graph')
  await page.getByTestId('graph-template-delete').click()
  await expect(sidebar(page).getByRole('button', { name: 'Renamed saved graph', exact: true })).toHaveCount(0)
  expect(state.templates.nav_alpha.map((entry) => entry.template_id)).toEqual(['alpha-water'])
})

test('refreshing saved templates preserves a manual builder selection', async ({ page }) => {
  const state = await setup(page)
  state.templates.nav_alpha.push({ template_id: 'alpha-second', name: 'Alpha secondary', active_version_id: 'v-active' })
  await page.goto('/#/visual/graph/builder')
  const advanced = page.getByTestId('graph-view-advanced-toggle')
  await expect(advanced).toBeVisible()
  await advanced.click()
  await expect(advanced).toHaveAttribute('aria-pressed', 'true')
  const selection = page.getByTestId('graph-template-select')
  await expect(selection).toBeVisible()
  await expect(selection).toBeEnabled()
  await selection.selectOption('alpha-second')
  await expect(page.getByTestId('graph-template-version-select')).toHaveValue('v-active')
  await page.getByTestId('graph-template-rename-name').fill('Renamed secondary')
  await page.getByTestId('graph-template-rename').click()
  await expect(sidebar(page).getByRole('button', { name: 'Renamed secondary', exact: true })).toBeVisible()
  await expect(selection).toHaveValue('alpha-second')
  await expect(selection).toBeEnabled()
})

test('an old project version response cannot overwrite the newly opened project draft', async ({ page }) => {
  await setup(page)
  let releaseVersion!: () => void
  let versionRequested = false
  const pendingVersion = new Promise<void>((resolve) => { releaseVersion = resolve })
  await page.route('**/workflow-graph/templates/alpha-water/versions/v-active**', async (route) => {
    versionRequested = true
    await pendingVersion
    await json(route, { version: { dsl: { nodes: [
      { id: 'stale-one', type: 'product', name: 'Stale project node' },
    ], edges: [] } } })
  })
  try {
    await page.goto('/#/visual/graph/builder?template=alpha-water')
    await expect.poll(() => versionRequested).toBe(true)
    await switchProject(page, 'nav_beta')
    await sidebar(page).getByRole('button', { name: 'Beta saved transport', exact: true }).click()
    const advanced = page.getByTestId('graph-view-advanced-toggle')
    if (await advanced.isVisible()) await advanced.click()
    await expect(page.getByText(/Draft: nodes=2 edges=0/)).toBeVisible()
    const oldResponse = page.waitForResponse((response) => response.url().includes('/templates/alpha-water/versions/v-active'))
    releaseVersion()
    await oldResponse
    await expect(page.getByTestId('graph-template-select')).toHaveValue('beta-transport')
    await expect(page.getByText(/Draft: nodes=2 edges=0/)).toBeVisible()
  } finally {
    releaseVersion()
  }
})

test('legacy statistics and review URLs show one quiet statistics surface', async ({ page }) => {
  const state = await setup(page)
  for (const route of ['/visual/dashboard', '/visual/dashboard/social', '/visual/analysis', '/visual/board']) {
    await page.goto(`/#${route}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Statistics')
    await expect(page.locator('.kernel-visual__stats-empty')).toBeVisible()
    await expect(sidebar(page).locator('.kernel-visual__nav-item.is-active')).toHaveCount(1)
    await expect(sidebar(page)).not.toContainText(/Review|Sentiment|Data Dashboard|Analysis|Board/)
    await expect(page.locator('body')).not.toContainText(/scheduled_completion_proof|reset_empty_warning_view|ui_event_log_only/)
    await expect(page.locator('.kernel-visual__status-strip button')).toHaveCount(0)
  }
  expect(state.requests.filter((entry) => entry.path === '/api/v1/dashboard/stats')).toHaveLength(0)
})

test('desktop graph shell is compact and flat, with translucent graph controls', async ({ page }, testInfo) => {
  await setup(page)
  await page.setViewportSize({ width: 1333, height: 977 })
  await page.goto('/#/visual/graph/market')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Alpha water')
  await expect(page.locator('.gv2-root > .gv2-projection-tabs')).toBeVisible()
  await expect(page.locator('.gv2-projection-tab-track')).toHaveCount(0)
  await expect(page.locator('.panel .gv2-projection-tabs')).toHaveCount(0)
  await expect(page.locator('main.kernel-visual__stage')).toBeVisible()
  await expect(page.locator('main > section.kernel-visual__stage')).toHaveCount(0)
  const masthead = await page.locator('.kernel-visual__masthead').boundingBox()
  expect(masthead?.height).toBeLessThan(120)
  const color = await page.locator('.gv2-overlay-top .gv2-select-mode-btn').first().evaluate((element) => getComputedStyle(element).backgroundColor)
  const channels = color.match(/[\d.]+/g)?.map(Number) || []
  expect(channels).toHaveLength(4)
  expect(channels[2]).toBeGreaterThan(channels[0])
  expect(channels[3]).toBeGreaterThan(0)
  expect(channels[3]).toBeLessThan(1)
  await page.screenshot({ path: testInfo.outputPath('visual-graph-desktop.png'), fullPage: true })
})

test('mobile graph shell fits a 390px viewport and keeps project controls reachable', async ({ page }, testInfo) => {
  await setup(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/visual/graph/market')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Alpha water')
  await expect(page.locator('.gv2-projection-tabs')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  const projectControl = await page.locator('.kernel-visual__project-switch select').boundingBox()
  expect(projectControl).not.toBeNull()
  expect(projectControl!.x).toBeGreaterThanOrEqual(0)
  expect(projectControl!.x + projectControl!.width).toBeLessThanOrEqual(390)
  await page.screenshot({ path: testInfo.outputPath('visual-graph-mobile.png'), fullPage: true })
})

for (const state of ['empty', 'error'] as const) {
  test(`a ${state} template list in the next project never keeps previous-project navigation`, async ({ page }) => {
    await setup(page, { betaTemplates: state })
    await page.goto('/#/visual/dashboard')
    await expect(sidebar(page).getByRole('button', { name: 'Alpha saved water', exact: true })).toBeVisible()
    await switchProject(page, 'nav_beta')
    await expect(sidebar(page).getByRole('button', { name: 'Beta transport', exact: true })).toBeVisible()
    await expect(sidebar(page).locator('.kernel-visual__nav-item--template')).toHaveCount(0)
    await expect(sidebar(page)).not.toContainText('Alpha')
    if (state === 'error') {
      await expect(sidebar(page).getByRole('status')).toHaveText('Template list load failed')
    } else {
      await expect(sidebar(page).locator('.kernel-visual__section--graph-templates')).toHaveCount(0)
    }
  })
}
