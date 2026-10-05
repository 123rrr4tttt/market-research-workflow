import { expect, test, type Page, type Route } from '@playwright/test'

async function ok(route: Route, data: unknown) {
  await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', data, error: null, meta: { mock: true } }) })
}

async function shell(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('market_project_key', 'default')
    localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.route('**/api/v1/**', (route) => ok(route, {}))
  await page.route('**/api/v1/projects**', (route) => ok(route, [{ project_key: 'default', name: 'Project', enabled: true, is_active: true }]))
  await page.route('**/api/v1/crawler/projects**', (route) => ok(route, { items: [] }))
  await page.route('**/api/v1/codex-auth/status**', (route) => ok(route, { authenticated: true }))
}

const moduleEntry = {
  id: 'concept_workbench.project_wiring', title: '概念工作台接线', status: 'registered', available: true,
  cell_ref: 'agent.macro.base', reason: null,
  targets: [{ id: 'mrw', label: 'MRW 本机项目' }],
  methods: [{ id: 'workbench-authoring', title: 'Workbench authoring' }, { id: 'functorial-programming-foundations', title: 'Functorial programming foundations' }],
  operations: [{ id: 'scan', title: 'Scan', effect: 'read_only' }, { id: 'sync', title: 'Sync', effect: 'write' }],
}

for (const width of [1440, 390]) {
  test(`Agent module is separate from crawler deployment at ${width}px (mock)`, async ({ page }, info) => {
    await shell(page)
    const requests: string[] = []
    await page.route('**/api/v1/crawler/agent-modules**', (route) => {
      requests.push(route.request().url())
      expect(route.request().headers()['x-project-key']).toBe('default')
      return ok(route, { items: [moduleEntry] })
    })
    await page.setViewportSize({ width, height: 984 })
    await page.goto('/#/admin/crawlers')
    await expect(page.getByRole('tab', { name: '采集工程', exact: true })).toHaveAttribute('aria-selected', 'true')
    expect(requests).toHaveLength(0)
    await page.getByRole('tab', { name: 'Agent 接线', exact: true }).click()
    const panel = page.getByRole('tabpanel', { name: 'Agent 接线', exact: true })
    await expect(panel.getByText('已注册', { exact: true })).toBeVisible()
    await expect(panel.getByText('MRW 本机项目', { exact: true })).toBeVisible()
    await expect(panel.getByText('Functorial programming foundations', { exact: true })).toBeVisible()
    await expect(page.locator('.crawler-projects-panel')).not.toBeVisible()
    await panel.getByText('注册详情', { exact: true }).click()
    await expect(panel.getByText('agent.macro.base', { exact: true })).toBeVisible()
    await expect(panel.getByText('sync', { exact: true })).toBeVisible()
    await panel.getByRole('button', { name: '刷新模块', exact: true }).click()
    await expect.poll(() => requests.length).toBe(2)
    expect(new URL(requests[0]).searchParams.get('project_key')).toBe('default')
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await page.screenshot({ path: info.outputPath(`agent-module-${width}.png`), fullPage: true })
    await expect(panel.getByRole('link', { name: '打开 Agent', exact: true })).toHaveAttribute('href', '#/workbench/agent')
    await expect(panel.getByRole('link', { name: '查看胞腔', exact: true })).toHaveAttribute('href', '#/workbench/cell')
    await page.getByRole('tab', { name: '采集工程', exact: true }).click()
    await expect(page.locator('.crawler-projects-panel')).toBeVisible()
  })
}

test('unavailable module and failed readback never claim registration (mock)', async ({ page }) => {
  await shell(page)
  let failed = false
  await page.route('**/api/v1/crawler/agent-modules**', async (route) => {
    if (failed) await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'error', data: null, error: { code: 'unavailable', message: 'unavailable' } }) })
    else await ok(route, { items: [{ ...moduleEntry, available: false, status: 'unavailable', reason: 'Target root unavailable', targets: [], methods: [] }] })
  })
  await page.goto('/#/admin/crawlers')
  await page.getByRole('tab', { name: 'Agent 接线', exact: true }).click()
  const panel = page.locator('#crawler-agent')
  await expect(panel.getByText('未连接', { exact: true })).toBeVisible()
  await expect(panel.getByRole('link', { name: '打开 Agent', exact: true })).toHaveCount(0)
  failed = true
  await panel.getByRole('button', { name: '刷新模块', exact: true }).click()
  await expect(panel.getByRole('alert')).toHaveText('模块状态读取失败', { timeout: 20000 })
  await expect(panel.getByText('已注册', { exact: true })).toHaveCount(0)
})
