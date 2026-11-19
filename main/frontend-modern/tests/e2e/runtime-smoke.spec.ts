import { expect, test, type Route } from '@playwright/test'
import { requireRealBackendReadiness, SKIP_BACKEND_CHECK, type RealBackendReadinessResult } from './helpers/backend-readiness'

function skipWhenBackendCheckBypassed(backendReadiness: RealBackendReadinessResult) {
  test.skip(
    backendReadiness?.skipped === true,
    `${SKIP_BACKEND_CHECK}=1 bypasses live-backend readiness; this real-backend proof was not run.`,
  )
}

function apiEnvelope(data: unknown) {
  return {
    status: 'success',
    data,
    error: null,
    meta: { trace_id: 'dashboard-runtime-smoke-mock' },
  }
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(apiEnvelope(data)),
  })
}

test('@live homepage runtime smoke uses live backend', async ({ page, request }) => {
  const backendReadiness = await requireRealBackendReadiness(request)
  skipWhenBackendCheckBypassed(backendReadiness)
  await page.addInitScript(() => {
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  const projectsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/projects') && response.status() === 200
  })

  const response = await page.goto('/')
  expect(response?.ok()).toBeTruthy()
  await projectsResponse

  await expect(page.getByRole('heading', { level: 1, name: '运行记录', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: '目标项目', exact: true })).toBeVisible()
})

test('@live graph runtime smoke loads against live graph endpoints', async ({ page, request }) => {
  const backendReadiness = await requireRealBackendReadiness(request)
  skipWhenBackendCheckBypassed(backendReadiness)
  const graphConfigResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/project-customization/graph-config') && response.status() === 200
  })
  const marketGraphResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/market-graph') && response.status() === 200
  })

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await graphConfigResponse
  await marketGraphResponse

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  await expect(page.getByText('节点总数', { exact: true })).toBeVisible()
  await expect(page.getByText('边总数', { exact: true })).toBeVisible()
})

test('statistics landing does not start dashboard queries or report operations', async ({ page }) => {
  const calls: string[] = []
  await page.addInitScript(() => {
    localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    calls.push(path)
    if (path === '/api/v1/projects') {
      await fulfillJson(route, { items: [{ project_key: 'default', enabled: true }] })
    } else if (path.startsWith('/api/v1/health')) {
      await fulfillJson(route, { status: 'ok' })
    } else {
      await route.fulfill({ status: 404, body: '' })
    }
  })

  const response = await page.goto('/#dashboard.html')
  expect(response?.ok()).toBeTruthy()
  await expect(page.getByRole('heading', { level: 2, name: '统计视图' })).toBeVisible()
  await expect(page.getByText('当前统计视图暂无指标。')).toBeVisible()
  expect(calls.filter((path) => /^\/api\/v1\/(dashboard|search\/runs|reports|writing\/export|llm-report\/export)\//.test(path))).toEqual([])
})

test('runtime health reports dependency failures without consulting historical evidence', async ({ page }) => {
  const calls: string[] = []
  await page.addInitScript(() => {
    localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    calls.push(path)
    switch (path) {
      case '/api/v1/projects':
        await fulfillJson(route, { items: [{ project_key: 'default', enabled: true }] })
        break
      case '/api/v1/health':
        await fulfillJson(route, { status: 'ok', provider: 'test', env: 'dev' })
        break
      case '/api/v1/health/deep':
        await route.fulfill({ json: {
          status: 'degraded',
          database: 'ok',
          database_pool: 'ok',
          elasticsearch: 'error: ping failed',
          details: {},
        } })
        break
      default:
        await route.fulfill({ status: 404, body: '' })
    }
  })

  await page.goto('/#/admin/backend')
  await expect(page.getByRole('heading', { name: '运行态状态' })).toBeVisible()
  await expect(page.getByRole('row', { name: /elasticsearch.*error: ping failed/ })).toBeVisible()
  expect(calls).toContain('/api/v1/health/deep')
  expect(calls.some((path) => path.startsWith('/api/v1/business-lines/'))).toBe(false)
})
