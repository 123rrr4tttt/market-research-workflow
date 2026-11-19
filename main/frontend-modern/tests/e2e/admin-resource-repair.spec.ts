import { expect, test, type Route } from '@playwright/test'

type CapturedRequest = {
  method: string
  pathname: string
  payload?: unknown
}

function okEnvelope(data: unknown, meta?: Record<string, unknown>) {
  return {
    status: 'success',
    data,
    error: null,
    meta,
  }
}

async function fulfillJson(route: Route, data: unknown, meta?: Record<string, unknown>) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(okEnvelope(data, meta)),
  })
}

function pageMeta(page: number, total: number) {
  const totalPages = Math.max(1, Math.ceil(total / 24))
  return { pagination: { page, page_size: 24, total, total_pages: totalPages } }
}

const sourceItems = [
  {
    item_key: 'market.news.system',
    name: 'Market News Cluster',
    channel_key: 'handler.cluster',
    scope: 'effective',
    enabled: true,
    params: { site_entries: ['https://example.com/search?q={query}'] },
  },
]

const siteEntries = [
  {
    id: 1,
    site_url: 'https://example.com/search?q={query}',
    domain: 'example.com',
    entry_type: 'search_template',
    source: 'source_library',
    enabled: true,
    scope: 'project',
    lifecycle_state: 'needs_review',
    review_closure: {
      status: 'needs_review',
      state: 'needs_review',
      next_actions: [{ action: 'collect_source_library_run', enabled: false, blocked: true }],
    },
  },
  {
    id: 2,
    site_url: 'https://example.org/feed.xml',
    domain: 'example.org',
    entry_type: 'rss',
    source: 'source_library',
    enabled: true,
    scope: 'project',
    lifecycle_state: 'needs_review',
    review_closure: {
      status: 'needs_review',
      state: 'needs_review',
      next_actions: [{ action: 'collect_source_library_run', enabled: false, blocked: true }],
    },
  },
]

const stableProject = { project_key: 'resource_e2e', name: 'Resource E2E', enabled: true }

async function mockAdminShell(page: import('@playwright/test').Page, captured: CapturedRequest[]) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    captured.push({ method: request.method(), pathname: url.pathname })
    await fulfillJson(route, {})
  })

  await page.route('**/api/v1/health**', (route) => fulfillJson(route, { status: 'ok' }))
  await page.route('**/api/v1/config/env**', (route) => fulfillJson(route, { variables: {} }))
  await page.route('**/api/v1/projects?**', (route) => fulfillJson(route, [stableProject]))
  await page.route('**/api/v1/codex-auth/status**', (route) => fulfillJson(route, { authenticated: true }))
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'resource_e2e')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
})

test('resource page keeps current tables compact and reviews the visible page item by item', async ({ page }) => {
  const captured: CapturedRequest[] = []
  let firstFailureUsed = false
  await mockAdminShell(page, captured)

  await page.route('**/api/v1/source_library/items?**', (route) => fulfillJson(route, sourceItems))
  await page.route('**/api/v1/source_library/items/grouped?**', (route) =>
    fulfillJson(route, { by_handler: {} }),
  )
  await page.route('**/api/v1/source_library/channels?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/resource_pool/urls?**', (route) =>
    fulfillJson(route, { items: [] }, pageMeta(1, 0)),
  )
  await page.route('**/api/v1/resource_pool/site_entries?**', (route) =>
    fulfillJson(route, { items: siteEntries }, pageMeta(1, 2)),
  )
  await page.route('**/api/v1/resource_pool/site_entries/lifecycle?**', async (route) => {
    const request = route.request()
    const payload = request.postDataJSON() as Record<string, unknown>
    captured.push({ method: request.method(), pathname: new URL(request.url()).pathname, payload })
    if (payload.site_url === 'https://example.org/feed.xml' && !firstFailureUsed) {
      firstFailureUsed = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'error',
          data: null,
          error: { code: 'REVIEW_FAILED', message: 'review guard rejected' },
        }),
      })
      return
    }
    await fulfillJson(route, {
      ...payload,
      lifecycle_state: 'accepted',
      enabled: true,
    })
  })

  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/#/admin/resources')

  await expect(page.getByRole('tab', { name: '来源项' })).toBeVisible()
  await expect(page.getByText('market.news.system')).toBeVisible()
  await expect(page.locator('.resource-page__advanced')).not.toHaveAttribute('open')
  await expect(page.getByText('来源项编辑')).not.toBeVisible()

  await page.getByRole('tab', { name: '站点入口' }).click()
  await page.getByRole('button', { name: '采纳当前页' }).click()

  await expect(page.getByText('已采纳 1/2；失败 1').first()).toBeVisible()
  await expect(page.getByText('https://example.org/feed.xml: review guard rejected')).toBeVisible()
  expect(captured.filter((item) => item.pathname.endsWith('/lifecycle'))).toHaveLength(2)
  expect(captured.some((item) => item.pathname === '/api/v1/ingest/source-library/run')).toBe(false)

  await page.getByRole('button', { name: '重试失败项' }).click()
  await expect(page.getByText('已采纳 1/1；失败 0').first()).toBeVisible()
  expect(captured.filter((item) => item.pathname.endsWith('/lifecycle'))).toHaveLength(3)

  await page.getByRole('button', { name: '详情', exact: true }).first().click()
  await expect(page.locator('.resource-page__detail-row').first()).toBeVisible()
  const tableUsesOwnScroll = await page.locator('.resource-page__table-wrap').first().evaluate((element) => (
    element.scrollWidth >= element.clientWidth
  ))
  expect(tableUsesOwnScroll).toBe(true)
  const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(documentWidth).toBeLessThanOrEqual(1440)
})

test('project management keeps the current project until activation succeeds', async ({ page }) => {
  await mockAdminShell(page, [])
  await page.route('**/api/v1/projects?**', (route) => fulfillJson(route, [
    stableProject,
    { project_key: 'project_b', name: 'Project B', enabled: true },
  ]))
  let attempts = 0
  await page.route('**/api/v1/projects/project_b/activate?**', (route) => {
    if (++attempts === 1) return route.fulfill({ status: 409, json: { detail: 'project is archived/disabled' } })
    return fulfillJson(route, { active_project_key: 'project_b' })
  })

  await page.goto('/#/admin/projects')
  const switchButton = page.getByTestId('projects-list').getByRole('row', { name: /Project B/ }).getByRole('button', { name: '切换', exact: true })
  const firstActivation = page.waitForResponse((response) =>
    new URL(response.url()).pathname === '/api/v1/projects/project_b/activate',
  )
  await switchButton.click()
  expect((await firstActivation).status()).toBe(409)
  await expect(switchButton).toBeEnabled()
  expect(await page.evaluate(() => localStorage.getItem('market_project_key'))).toBe('resource_e2e')

  await switchButton.click()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('market_project_key'))).toBe('project_b')
})

test('switching projects cancels the remaining current-page review work', async ({ page }) => {
  const captured: CapturedRequest[] = []
  let releaseFirstPatch: (() => void) | null = null
  const firstPatchGate = new Promise<void>((resolve) => {
    releaseFirstPatch = resolve
  })
  await mockAdminShell(page, captured)

  await page.route('**/api/v1/projects?**', (route) =>
    fulfillJson(route, [
      stableProject,
      { project_key: 'project_b', name: 'Project B', enabled: true },
    ]),
  )
  await page.route('**/api/v1/projects/project_b/activate?**', (route) => {
    captured.push({ method: 'POST', pathname: '/api/v1/projects/project_b/activate' })
    return fulfillJson(route, { project_key: 'project-b' })
  })
  await page.route('**/api/v1/source_library/items?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/source_library/items/grouped?**', (route) => fulfillJson(route, { by_handler: {} }))
  await page.route('**/api/v1/source_library/channels?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/resource_pool/urls?**', (route) =>
    fulfillJson(route, { items: [] }, pageMeta(1, 0)),
  )
  await page.route('**/api/v1/resource_pool/site_entries?**', (route) =>
    fulfillJson(route, { items: siteEntries }, pageMeta(1, 2)),
  )
  await page.route('**/api/v1/resource_pool/site_entries/lifecycle?**', async (route) => {
    const request = route.request()
    const payload = request.postDataJSON() as Record<string, unknown>
    captured.push({
      method: request.method(),
      pathname: new URL(request.url()).pathname,
      payload,
    })
    if (captured.filter((item) => item.pathname.endsWith('/lifecycle')).length === 1) {
      await firstPatchGate
    }
    await fulfillJson(route, { ...payload, lifecycle_state: 'accepted', enabled: true })
  })

  await page.goto('/#/admin/resources')
  await page.getByRole('tab', { name: '站点入口' }).click()
  const firstRequest = page.waitForRequest((request) => request.url().includes('/site_entries/lifecycle'))
  await page.getByRole('button', { name: '采纳当前页' }).click()
  await firstRequest

  await page.locator('.kernel-admin__project-bar select').selectOption('project_b')
  await page.getByRole('button', { name: '切换项目', exact: true }).click()
  await expect(page.getByText('当前项目: project_b')).toBeVisible()
  releaseFirstPatch?.()

  await expect(page.getByText(/项目已切换，本次当前页操作已停止/)).toBeVisible()
  await expect(page.getByRole('button', { name: '重试失败项' })).toHaveCount(0)
  await page.waitForTimeout(100)
  expect(captured.filter((item) => item.pathname.endsWith('/lifecycle'))).toHaveLength(1)
  expect(captured.some((item) => item.pathname === '/api/v1/ingest/source-library/run')).toBe(false)
})

test('extract route shows an extraction-only workspace and a real task detail link', async ({ page }) => {
  const captured: CapturedRequest[] = []
  await mockAdminShell(page, captured)
  await page.route('**/api/v1/source_library/items?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/source_library/items/grouped?**', (route) => fulfillJson(route, { by_handler: {} }))
  await page.route('**/api/v1/source_library/channels?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/resource_pool/urls?**', (route) =>
    fulfillJson(
      route,
      {
        items: [
          {
            id: 1,
            url: 'https://example.com/report.pdf',
            domain: 'example.com',
            source: 'document',
            created_at: '2026-10-05T08:00:00Z',
          },
        ],
      },
      pageMeta(1, 1),
    ),
  )
  await page.route('**/api/v1/resource_pool/site_entries?**', (route) =>
    fulfillJson(route, { items: [] }, pageMeta(1, 0)),
  )
  await page.route('**/api/v1/resource_pool/extract/from-materials?**', (route) => {
    captured.push({ method: 'POST', pathname: '/api/v1/resource_pool/extract/from-materials' })
    return fulfillJson(route, { task_id: 'resource-extract-e2e', async: true, trace_id: 'trace-e2e' })
  })
  await page.route('**/api/v1/process/resource-extract-e2e?**', (route) =>
    fulfillJson(route, { task_id: 'resource-extract-e2e', status: 'SUCCESS' }),
  )

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/admin/resources/extract')

  await expect(page.getByRole('heading', { name: '提取与资源沉淀' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '来源项' })).toHaveCount(0)
  await expect(page.locator('.resource-page__advanced')).toHaveCount(0)
  await expect(page.getByText('https://example.com/report.pdf')).toBeVisible()

  await page.getByRole('button', { name: '提取 URL' }).click()
  const notice = page.getByTestId('task-submission-notice')
  await expect(notice).toContainText('resource-extract-e2e')
  await expect(notice.getByRole('link', { name: '查看任务' })).toHaveAttribute(
    'href',
    /#\/admin\/process\?task_id=resource-extract-e2e/,
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('resource pagination facade accepts legacy arrays and surfaces a 200 error envelope', async ({ page }) => {
  const captured: CapturedRequest[] = []
  let returnErrorEnvelope = false
  await mockAdminShell(page, captured)
  await page.route('**/api/v1/source_library/items?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/source_library/items/grouped?**', (route) => fulfillJson(route, { by_handler: {} }))
  await page.route('**/api/v1/source_library/channels?**', (route) => fulfillJson(route, []))
  await page.route('**/api/v1/resource_pool/site_entries?**', (route) =>
    fulfillJson(route, { items: [] }, pageMeta(1, 0)),
  )
  await page.route('**/api/v1/resource_pool/urls?**', async (route) => {
    if (returnErrorEnvelope) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'error',
          data: null,
          error: { code: 'READ_FAILED', message: 'resource read failed' },
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 7,
          url: 'https://example.com/legacy-array.pdf',
          domain: 'example.com',
          source: 'document',
          created_at: '2026-10-05T09:00:00Z',
        },
      ]),
    })
  })

  await page.goto('/#/admin/resources')
  await page.getByRole('tab', { name: 'URL 池' }).click()
  await expect(page.getByText('https://example.com/legacy-array.pdf')).toBeVisible()

  returnErrorEnvelope = true
  await page.getByRole('button', { name: '刷新列表' }).click()
  await expect(page.getByText('读取失败: resource read failed')).toBeVisible()
})
