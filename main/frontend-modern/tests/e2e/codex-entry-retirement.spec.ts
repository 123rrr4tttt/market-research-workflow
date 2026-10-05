import { expect, test, type Page } from '@playwright/test'
import { parseLegacyHashToMode } from '../../src/app/kernel/legacyHashAdapter'
import { resolveKernelRoute } from '../../src/app/kernel/routes'

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
  await page.route('http://127.0.0.1:8172/?mrw=macro-host-v1', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body><main id="codex-webui">Codex WebUI</main></body></html>',
    }),
  )
}

async function expectCodexPage(page: Page) {
  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', 'http://127.0.0.1:8172/?mrw=macro-host-v1')
  await expect(page.locator('.agent-chat-page')).toHaveCount(0)
  await expect(page.getByTestId('agent-chat-compat-link')).toHaveCount(0)
}

test('canonical Codex routes mount the host Codex WebUI', async ({ page }) => {
  await mockShellApis(page)
  for (const path of ['/#/workbench/agent', '/#codex-workbench.html']) {
    await page.goto(path)
    await expectCodexPage(page)
  }
})

test('retired agentchat hashes no longer resolve to Codex', () => {
  for (const hash of ['#agent-chat.html', '#agent-chat-compat.html', '#agent.html']) {
    expect(parseLegacyHashToMode(hash)).toBeNull()
    expect(resolveKernelRoute(hash).source).toBe('retired')
  }
  expect(parseLegacyHashToMode('#codex-workbench.html')).toBe('flowCodex')
  expect(resolveKernelRoute('#codex-workbench.html').moduleKey).toBe('flowCodex')
  expect(resolveKernelRoute('#not-a-page.html').source).toBe('unknown')
  expect(resolveKernelRoute('').source).toBe('default')
})

test('retired agentchat hashes do not request old chat APIs', async ({ page }) => {
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
    await expect(page.getByTestId('retired-route')).toBeVisible()
    await expect(page.getByTestId('retired-route')).toContainText('旧入口已退役')
    await expect(page.getByTestId('codex-agent-page')).toHaveCount(0)
    await expect(page.locator('.app-status-bar')).toHaveCount(0)
    await expect(page.locator('.figma-side-nav')).toHaveCount(0)
    await expect(page.locator('.kernel-workbench')).toHaveCount(0)
    await expect(page.locator('.kernel-admin')).toHaveCount(0)
    await expect(page.locator('.kernel-visual')).toHaveCount(0)
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
  await page.route('http://127.0.0.1:8172/?mrw=macro-host-v1', (route) =>
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
    'http://127.0.0.1:8172/?mrw=macro-host-v1',
  )
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 已授权')
  await expect(page.getByTestId('codex-agent-auth-panel')).toHaveCount(0)
  expect(proxiedFrameRequested).toBe(false)
})

async function mockRemoteOrigin(page: Page) {
  const baseURL = test.info().project.use.baseURL!
  const remoteOrigin = `http://remote.mrw.test:${new URL(baseURL).port}`
  await page.route(`${remoteOrigin}/**`, async (route) => {
    const requestUrl = new URL(route.request().url())
    const localUrl = `${baseURL}${requestUrl.pathname}${requestUrl.search}`
    return route.fulfill({ response: await page.request.get(localUrl) })
  })
  return remoteOrigin
}

test('remote token-sink-only host identity remains on the connection panel', async ({ page }) => {
  const remoteOrigin = await mockRemoteOrigin(page)
  await mockCommonShellApis(page, {
    authenticated: false,
    token_sink_authenticated: true,
    codex_oauth_enabled: true,
  })
  await page.route('http://127.0.0.1:8172/?mrw=macro-host-v1', (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '' }),
  )

  await page.goto(`${remoteOrigin}/#/workbench/agent`)

  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-auth-panel')).toContainText(
    '当前页面不是明确本机 loopback 入口',
  )
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 已授权')
  await expect(page.getByTestId('codex-agent-frame')).toHaveCount(0)
})

test('remote browser-auth status stays retryable before mounting WebUI', async ({ page }) => {
  const remoteOrigin = await mockRemoteOrigin(page)
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

  await page.goto(`${remoteOrigin}/#/workbench/agent`)
  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveCount(0)
  await expect(page.getByTestId('codex-agent-auth-panel')).toContainText('浏览器认证状态读取失败')
  await expect(page.getByTestId('codex-agent-auth-retry')).toBeEnabled()
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 状态未知')

  allowAuthenticatedStatus = true
  await page.getByTestId('codex-agent-auth-retry').click()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', '/codex/?mrw=macro-host-v1')
})

test('local iframe survives auth expiry and status failures without reloading', async ({ page }) => {
  await mockShellApis(page)
  let status: object | null = { authenticated: true, token_sink_authenticated: true }
  await page.route('**/api/v1/codex-auth/status**', (route) =>
    route.fulfill({
      status: status ? 200 : 503,
      contentType: 'application/json',
      body: JSON.stringify({ status: status ? 'ok' : 'unavailable', data: status }),
    }),
  )
  let frameLoads = 0
  await page.route('http://127.0.0.1:8172/?mrw=macro-host-v1', (route) => {
    frameLoads += 1
    return route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body><input aria-label="Draft" /></body></html>',
    })
  })
  await page.goto('/#/workbench/agent')
  const draft = page.frameLocator('[data-testid="codex-agent-frame"]').getByLabel('Draft')
  await draft.fill('Keep this conversation open')

  for (const nextStatus of [
    { authenticated: false, token_sink_authenticated: true },
    { authenticated: false, token_sink_authenticated: false },
    null,
    { authenticated: true, token_sink_authenticated: true },
  ]) {
    status = nextStatus
    const response = page.waitForResponse('**/api/v1/codex-auth/status**')
    await page.getByRole('button', { name: '刷新连接状态', exact: true }).click()
    await response
    await expect(page.getByRole('button', { name: '刷新连接状态', exact: true })).toBeEnabled()
    await expectCodexPage(page)
    await expect(draft).toHaveValue('Keep this conversation open')
  }
  expect(frameLoads).toBe(1)
})

test('local WebUI mounts even when the initial status request fails', async ({ page }) => {
  await mockShellApis(page, false)
  await page.goto('/#/workbench/agent')
  await expectCodexPage(page)
  await expect(page.getByTestId('codex-agent-auth-panel')).toHaveCount(0)
  await expect(page.getByTestId('codex-agent-host-auth')).toHaveText('宿主 CLI 状态未知')
})
