import { expect, test } from '@playwright/test'

const enabled =
  process.env.CODEX_AUTH_PROXY_E2E === '1' &&
  Boolean(process.env.CODEX_AUTH_PROXY_BROWSER_SESSION_ID)

test.skip(!enabled, 'Real Codex auth proxy verification requires an isolated browser session')

test('authenticated browser enters proxied Codex through the MRW exchange', async ({
  page,
  request,
}) => {
  const baseURL = test.info().project.use.baseURL
  const proxyOrigin = baseURL || process.env.CODEX_AUTH_PROXY_BASE_URL!
  await page.context().addCookies([
    {
      name: 'codex_session',
      value: process.env.CODEX_AUTH_PROXY_BROWSER_SESSION_ID!,
      url: proxyOrigin,
      httpOnly: true,
      sameSite: 'Lax',
    },
  ])

  const publicBootstrapRequests: string[] = []
  page.on('request', (incomingRequest) => {
    if (incomingRequest.url().includes('/codex/api/auth/bootstrap')) {
      publicBootstrapRequests.push(incomingRequest.url())
    }
  })

  const exchangeResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/codex-auth/webui/bootstrap') &&
      response.request().method() === 'POST' &&
      response.status() === 200,
    { timeout: 20_000 },
  )
  const webuiStatusResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/codex/api/codex/status') &&
      response.request().method() === 'GET' &&
      response.status() === 200,
    { timeout: 20_000 },
  )

  // Exercise the authenticated proxy independently of the local host-page route.
  await page.goto('/codex/')

  await expect((await exchangeResponse).headers()['cache-control'] ?? '').toContain(
    'no-store',
  )
  await webuiStatusResponse

  await expect(page.locator('#root')).toBeAttached()
  const hasWebUiToken = await page.evaluate(() =>
    Boolean(window.localStorage.getItem('codex.webui.jwt')),
  )
  expect(hasWebUiToken).toBe(true)
  expect(publicBootstrapRequests).toEqual([])

  const publicBootstrap = await request.get('/codex/api/auth/bootstrap', {
    headers: {
      'X-Forwarded-For': '127.0.0.1',
      'X-Real-IP': '127.0.0.1',
      Origin: proxyOrigin,
      'Sec-Fetch-Site': 'same-origin',
    },
  })
  expect(publicBootstrap.status()).toBe(401)
  expect(publicBootstrap.headers()['cache-control'] ?? '').toContain('no-store')
})
