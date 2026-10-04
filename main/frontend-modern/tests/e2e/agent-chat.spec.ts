import { expect, test, type Page } from '@playwright/test'

async function mockShellApis(page: Page, codexStatusOk = true) {
  await page.route('**/api/v1/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { ok: true } }),
    }),
  )
  await page.route('**/api/v1/config/env**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { variables: {} } }),
    }),
  )
  await page.route('**/api/v1/projects**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    }),
  )
  await page.route('**/api/v1/codex-auth/status**', (route) =>
    route.fulfill({
      status: codexStatusOk ? 200 : 503,
      contentType: 'application/json',
      body: codexStatusOk
        ? JSON.stringify({
            status: 'ok',
            data: { authenticated: true, token_sink_authenticated: true },
          })
        : JSON.stringify({ status: 'unavailable', data: null }),
    }),
  )
  await page.route('**/codex/api/auth/bootstrap', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ accessToken: 'test-token' }),
    }),
  )
  await page.route('**/codex/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body><main id="codex-webui">Codex WebUI</main></body></html>',
    }),
  )
}

async function expectCodexPage(page: Page) {
  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', '/codex/')
  await expect(page.locator('.agent-chat-page')).toHaveCount(0)
  await expect(page.getByTestId('agent-chat-compat-link')).toHaveCount(0)
}

test('canonical agent route mounts the embedded Codex WebUI', async ({ page }) => {
  await mockShellApis(page)
  await page.goto('/#/workbench/agent')

  await expectCodexPage(page)
})

test('legacy agent hashes navigate to Codex without opening old chat APIs', async ({ page }) => {
  await mockShellApis(page)
  const retiredApiCalls: string[] = []
  page.on('request', (request) => {
    const url = request.url()
    if (url.includes('/api/v1/agent-chat/') || url.includes('/api/v1/agent-sessions/')) {
      retiredApiCalls.push(url)
    }
  })

  for (const hash of ['#agent-chat.html', '#agent-chat-compat.html', '#agent.html']) {
    await page.goto(`/${hash}`)
    await expectCodexPage(page)
  }

  expect(retiredApiCalls).toEqual([])
})

async function mockCommonShellApis(page: Page, codexStatus: object) {
  await page.route('**/api/v1/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { ok: true } }),
    }),
  )
  await page.route('**/api/v1/config/env**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { variables: {} } }),
    }),
  )
  await page.route('**/api/v1/projects**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    }),
  )
  await page.route('**/api/v1/codex-auth/status**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: codexStatus }),
    }),
  )
}

test('local token-sink-only host identity mounts the direct loopback WebUI', async ({ page }) => {
  await mockCommonShellApis(page, {
    authenticated: false,
    token_sink_authenticated: true,
    codex_oauth_enabled: true,
  })
  let proxiedFrameRequested = false
  await page.route('**/codex/**', (route) => {
    proxiedFrameRequested = true
    return route.fulfill({ status: 200, contentType: 'text/html', body: '' })
  })
  await page.route('http://127.0.0.1:8172/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body><main id="direct-codex-webui">Direct WebUI</main></body></html>',
    }),
  )

  await page.goto('/#/workbench/agent')

  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute(
    'src',
    'http://127.0.0.1:8172/',
  )
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 已授权')
  await expect(page.getByTestId('codex-agent-auth-panel')).toHaveCount(0)
  expect(proxiedFrameRequested).toBe(false)
})

test('remote token-sink-only host identity remains on the connection panel', async ({ page }) => {
  await page.route('http://remote.mrw.test:14173/**', async (route) => {
    const requestUrl = new URL(route.request().url())
    const localUrl = `http://127.0.0.1:14173${requestUrl.pathname}${requestUrl.search}`
    return route.fulfill({ response: await page.request.get(localUrl) })
  })
  await mockCommonShellApis(page, {
    authenticated: false,
    token_sink_authenticated: true,
    codex_oauth_enabled: true,
  })
  await page.route('http://127.0.0.1:8172/', (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '' }),
  )

  await page.goto('http://remote.mrw.test:14173/#/workbench/agent')

  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-auth-panel')).toContainText(
    '当前页面不是明确本机 loopback 入口',
  )
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 已授权')
  await expect(page.getByTestId('codex-agent-frame')).toHaveCount(0)
})

test('failed browser-auth status stays retryable before mounting WebUI', async ({ page }) => {
  let allowAuthenticatedStatus = false
  await page.route('**/api/v1/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { ok: true } }),
    }),
  )
  await page.route('**/api/v1/config/env**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { variables: {} } }),
    }),
  )
  await page.route('**/api/v1/projects**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    }),
  )
  await page.route('**/api/v1/codex-auth/status**', (route) => {
    if (!allowAuthenticatedStatus) {
      return route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'unavailable', data: null }),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: { authenticated: true, token_sink_authenticated: true },
      }),
    })
  })
  await page.route('**/codex/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body><main id="codex-webui">Codex WebUI</main></body></html>',
    }),
  )

  await page.goto('/#/workbench/agent')
  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveCount(0)
  await expect(page.getByTestId('codex-agent-auth-panel')).toContainText('浏览器认证状态读取失败')
  await expect(page.getByTestId('codex-agent-auth-retry')).toBeEnabled()
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 状态未知')

  allowAuthenticatedStatus = true
  await page.getByTestId('codex-agent-auth-retry').click()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', '/codex/')
})
