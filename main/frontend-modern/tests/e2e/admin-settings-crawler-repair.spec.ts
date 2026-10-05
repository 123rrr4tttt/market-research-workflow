import { expect, test, type Page, type Route } from '@playwright/test'

const PROJECT = 'default'
const CRAWLER = 'mock-crawler'
const env = { SERPAPI_KEY: 'search-key', DATABASE_URL: 'postgres://mock/default', OPENAI_API_KEY: 'model-key' }
const template = {
  id: 1, service_name: 'market_outline', model: 'mock-model', enabled: true,
  temperature: 0.2, top_p: 1, max_tokens: 1200, presence_penalty: 0,
  frequency_penalty: 0, system_prompt: 'Evidence first', user_prompt_template: '{{topic}}',
}
const crawler = {
  id: 1, project_key: CRAWLER, name: 'Mock crawler', status: 'enabled', provider: 'scrapy',
  current_version: 'v1', deployed_version: 'v1',
  source_uri: `https://example.com/${'long-repository-name/'.repeat(12)}crawler.git`,
}

async function ok(route: Route, data: unknown) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok', data, error: null, meta: { mock: true, real_backend_proof: false } }),
  })
}

async function shell(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('market_project_key', 'default')
    localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.route('**/api/v1/**', (route) => ok(route, {}))
  await page.route('**/api/v1/health**', (route) => ok(route, { status: 'ok' }))
  await page.route('**/api/v1/projects**', (route) => ok(route, [
    { project_key: PROJECT, name: 'Mock project', enabled: true, is_active: true },
  ]))
  await page.route('**/api/v1/codex-auth/status**', (route) => ok(route, { authenticated: true }))
}

for (const size of [{ width: 1440, height: 1000 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test(`settings variants keep responsibilities and width at ${size.width} (mock)`, async ({ page }) => {
    await shell(page)
    await page.route(/\/api\/v1\/config\/env(?:\?.*)?$/, (route) => ok(route, env))
    await page.route(/\/api\/v1\/llm-config\/projects\/default(?:\?.*)?$/, (route) => ok(route, { items: [template] }))
    await page.setViewportSize(size)
    await page.goto('/#/admin/settings')
    const settings = page.locator('.settings-page')
    await expect(settings.locator('[data-env-key="SERPAPI_KEY"] input')).toHaveValue('search-key')
    await expect(settings.locator('[data-env-key="OPENAI_API_KEY"]')).toHaveCount(0)
    await expect(settings.locator('.settings-templates-section')).toHaveCount(0)
    await settings.getByText('存储与运行', { exact: true }).click()
    await expect(settings.locator('[data-env-key="DATABASE_URL"] input')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width)
    await settings.getByRole('link', { name: '模型与模板', exact: true }).click()
    await expect(page).toHaveURL(/#\/admin\/settings\/llm/)
    await expect(settings.locator('[data-env-key="OPENAI_API_KEY"] input')).toHaveValue('model-key')
    await expect(settings.locator('[data-env-key="DATABASE_URL"]')).toHaveCount(0)
    await expect(settings.locator('.settings-preferences')).toHaveCount(0)
    const templates = settings.locator('.settings-templates-section')
    await templates.getByRole('button', { name: '编辑', exact: true }).click()
    await expect(templates.getByRole('textbox', { name: '模型', exact: true })).toBeVisible()
    await expect(templates.getByLabel('top_p', { exact: true })).not.toBeVisible()
    await templates.getByText('高级参数与提示词', { exact: true }).click()
    await expect(templates.getByLabel('top_p', { exact: true })).toBeVisible()
    await expect(templates.getByRole('textbox', { name: 'system_prompt', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width)
  })
}

test('settings saves retain global environment and current-project template scope (mock)', async ({ page }) => {
  await shell(page)
  const saved: Array<{ pathname: string; method: string; body: Record<string, unknown> }> = []
  await page.route(/\/api\/v1\/config\/env(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      saved.push({ pathname: new URL(route.request().url()).pathname, method: 'POST', body: route.request().postDataJSON() })
      await ok(route, { updated: ['SERPAPI_KEY'] })
    } else await ok(route, env)
  })
  await page.route('**/api/v1/llm-config/projects/default**', async (route) => {
    const method = route.request().method()
    if (method === 'PUT' || method === 'POST') {
      saved.push({ pathname: new URL(route.request().url()).pathname, method, body: route.request().postDataJSON() })
      await ok(route, method === 'POST' ? { copied: 1, skipped: 0 } : { ok: true })
    } else await ok(route, { items: [template] })
  })
  await page.goto('/#/admin/settings')
  await page.locator('[data-env-key="SERPAPI_KEY"] input').fill('new-search-key')
  await page.locator('.settings-page').getByRole('button', { name: '保存配置', exact: true }).click()
  await expect.poll(() => saved.length).toBe(1)
  expect(saved[0]).toMatchObject({ pathname: '/api/v1/config/env', method: 'POST', body: { SERPAPI_KEY: 'new-search-key', OPENAI_API_KEY: 'model-key' } })
  await page.goto('/#/admin/settings/llm')
  const templates = page.locator('.settings-templates-section')
  await templates.getByRole('button', { name: '编辑', exact: true }).click()
  await templates.getByRole('textbox', { name: '模型', exact: true }).fill('revised-model')
  await templates.getByText('高级参数与提示词', { exact: true }).click()
  await templates.getByLabel('top_p', { exact: true }).fill('0.8')
  await templates.getByRole('button', { name: '保存 market_outline', exact: true }).click()
  await expect.poll(() => saved.length).toBe(2)
  expect(saved[1]).toMatchObject({ pathname: '/api/v1/llm-config/projects/default/market_outline', method: 'PUT', body: { model: 'revised-model', top_p: 0.8, enabled: true, system_prompt: 'Evidence first' } })
  await templates.getByRole('textbox', { name: '来源 project_key' }).fill('template-source')
  await templates.getByRole('checkbox', { name: '覆盖已存在模板' }).check()
  await templates.getByRole('button', { name: '从项目复制模板', exact: true }).click()
  await expect.poll(() => saved.length).toBe(3)
  expect(saved[2]).toMatchObject({ pathname: '/api/v1/llm-config/projects/default/copy-from', method: 'POST', body: { source_project_key: 'template-source', overwrite: true } })
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
})

test('crawler import/deploy use only Celery identities while rollback preserves Scrapyd identity (mock)', async ({ page }) => {
  await shell(page)
  const taskReads: string[] = []
  const effects: string[] = []
  await page.route(/\/api\/v1\/crawler\/projects(?:\?.*)?$/, (route) => ok(route, [crawler]))
  await page.route(/\/api\/v1\/crawler\/projects\/mock-crawler(?:\?.*)?$/, (route) => ok(route, crawler))
  await page.route('**/api/v1/crawler/projects/mock-crawler/deploy-runs?**', (route) => ok(route, [
    { id: 42, action: 'deploy', status: 'success', external_job_id: 'scrapyd-only-42', finished_at: '2026-10-05T08:00:00Z' },
  ]))
  await page.route(/\/api\/v1\/crawler\/projects\/import(?:\?.*)?$/, (route) => {
    effects.push('import')
    return ok(route, { ...crawler, task_id: 'celery-import-42' })
  })
  await page.route(/\/api\/v1\/crawler\/projects\/mock-crawler\/deploy(?:\?.*)?$/, (route) => {
    effects.push('deploy')
    return ok(route, { run: { id: 43, action: 'deploy', status: 'queued' }, task_id: 'celery-deploy-43' })
  })
  await page.route(/\/api\/v1\/crawler\/projects\/mock-crawler\/rollback(?:\?.*)?$/, (route) => {
    effects.push('rollback')
    return ok(route, { run: { id: 44, action: 'rollback', status: 'queued', external_job_id: 'scrapyd-only-44' } })
  })
  await page.route('**/api/v1/process/celery-**', (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)!
    taskReads.push(id)
    return ok(route, { task_id: id, status: 'SUCCESS' })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/admin/crawlers')
  const crawlers = page.locator('.crawler-management-page')
  await expect(crawlers.getByText('scrapyd-only-42', { exact: true })).toBeAttached()
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
  await expect(crawlers.locator('.crawler-import-panel')).not.toHaveAttribute('open')
  await crawlers.locator('.crawler-import-panel > summary').click()
  await crawlers.getByLabel('Git URL', { exact: true }).fill('https://example.com/mock-repository.git')
  await crawlers.getByRole('button', { name: '导入爬虫项目', exact: true }).click()
  await expect(page.getByTestId('task-submission-notice')).toContainText('celery-import-42')
  await crawlers.getByRole('button', { name: '提交部署', exact: true }).click()
  await expect(page.getByTestId('task-submission-notice')).toContainText('celery-deploy-43')
  await expect(page.getByTestId('task-submission-notice').getByRole('link')).toHaveAttribute('href', /task_id=celery-deploy-43/)
  await expect.poll(() => taskReads.includes('celery-deploy-43')).toBe(true)
  await crawlers.getByRole('button', { name: '提交回滚', exact: true }).click()
  await expect(crawlers.getByRole('status').filter({ hasText: '回滚已提交' })).toContainText('external_job_id=scrapyd-only-44')
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
  expect(effects).toEqual(['import', 'deploy', 'rollback'])
  expect(taskReads.every((id) => id.startsWith('celery-'))).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('crawler polling observes existing runs, stops at terminal and refreshes project detail (mock)', async ({ page }) => {
  await shell(page)
  let runsRead = 0
  let detailRead = 0
  let terminal = false
  let effects = 0
  await page.route('**/api/v1/crawler/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== 'GET') effects += 1
    if (path.endsWith('/deploy-runs')) {
      runsRead += 1
      return ok(route, [{ id: 51, action: 'deploy', status: terminal ? 'success' : 'running', finished_at: terminal ? '2026-10-05T08:00:00Z' : null }])
    }
    if (path.endsWith('/projects')) return ok(route, [crawler])
    detailRead += 1
    return ok(route, crawler)
  })
  await page.goto('/#/admin/crawlers')
  await expect(page.locator('.crawler-detail-panel tbody').first()).toContainText('running')
  const detailBeforeTerminal = detailRead
  terminal = true
  await expect(page.locator('.crawler-detail-panel tbody').first()).toContainText('success', { timeout: 8000 })
  await expect.poll(() => detailRead).toBeGreaterThan(detailBeforeTerminal)
  const settledReads = runsRead
  await page.waitForTimeout(3500)
  expect(runsRead).toBe(settledReads)
  expect(effects).toBe(0)
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
})

for (const action of ['deploy', 'rollback'] as const) {
  test(`crawler ${action} refuses async:false task receipts from nested run responses (mock)`, async ({ page }) => {
    await shell(page)
    let effectCalls = 0
    const taskReads: string[] = []
    await page.route('**/api/v1/crawler/**', (route) => {
      const path = new URL(route.request().url()).pathname
      if (route.request().method() === 'POST') {
        effectCalls += 1
        expect(path).toBe(`/api/v1/crawler/projects/${CRAWLER}/${action}`)
        return ok(route, {
          run: { id: 70, action, status: 'success', finished_at: '2026-10-05T08:00:00Z' },
          task_id: `not-async-${action}`, async: false, trace_id: 'sync-trace',
        })
      }
      if (path.endsWith('/projects')) return ok(route, [crawler])
      if (path.endsWith('/deploy-runs')) return ok(route, [])
      return ok(route, crawler)
    })
    await page.route(/\/api\/v1\/process\/not-async-[^/?]+(?:\?.*)?$/, (route) => {
      taskReads.push(new URL(route.request().url()).pathname)
      return ok(route, { status: 'SUCCESS' })
    })
    await page.goto('/#/admin/crawlers')
    const crawlers = page.locator('.crawler-management-page')
    const button = action === 'deploy' ? '提交部署' : '提交回滚'
    const message = action === 'deploy' ? '部署已提交' : '回滚已提交'
    await expect(crawlers.getByRole('button', { name: button, exact: true })).toBeEnabled()
    await crawlers.getByRole('button', { name: button, exact: true }).click()
    await expect(crawlers.getByRole('status').filter({ hasText: message })).toContainText('id=70')
    await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
    expect(effectCalls).toBe(1)
    expect(taskReads).toEqual([])
  })
}

test('crawler running observation is bounded and keeps read errors visible (mock)', async ({ page }) => {
  await shell(page)
  await page.clock.install()
  let runsRead = 0
  let fail = false
  await page.route(/\/api\/v1\/crawler\/projects(?:\?.*)?$/, (route) => ok(route, [crawler]))
  await page.route(/\/api\/v1\/crawler\/projects\/mock-crawler(?:\?.*)?$/, (route) => ok(route, crawler))
  await page.route('**/api/v1/crawler/projects/mock-crawler/deploy-runs?**', async (route) => {
    runsRead += 1
    if (fail) {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ status: 'error', data: null, error: { message: 'read failed', code: 'READ_FAILED' } }) })
    } else await ok(route, [{ id: 61, action: 'deploy', status: 'running' }])
  })
  await page.goto('/#/admin/crawlers')
  await expect(page.locator('.crawler-detail-panel tbody').first()).toContainText('running')
  await page.clock.fastForward(123000)
  await expect(page.getByText('自动观察已结束，可手动刷新运行记录')).toBeVisible()
  const boundedReads = runsRead
  await page.clock.fastForward(10000)
  expect(runsRead).toBe(boundedReads)
  fail = true
  await page.locator('.crawler-detail-panel').getByRole('button', { name: '刷新', exact: true }).click()
  await page.clock.fastForward(10000)
  await expect(page.getByText('部署运行读取失败')).toBeVisible()
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
})
