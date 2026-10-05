import { expect, test, type Page, type Route } from '@playwright/test'

const PROJECT_KEY = 'ops_repair_mock'
const TASK_ID = 'ops-repair-celery-task'
const LONG_TITLE = `Project evidence ${'with a long document title '.repeat(9)}`
const LONG_WORKER_HEALTH_URL = `https://mocked-worker.example.test/health/${'long-worker-health-path-'.repeat(20)}`

async function fulfill(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok', data, meta: { mock: true, real_backend_proof: false } }),
  })
}

async function mockOps(page: Page, options: { documentError?: boolean; synchronous?: boolean; taskError?: boolean } = {}) {
  const state = { completed: false, documentReads: 0, previews: 0, writes: 0, sessionReads: 0, diagnosticReads: 0 }
  await page.addInitScript((projectKey) => {
    localStorage.setItem('market_project_key', projectKey)
    localStorage.setItem('app_locale_v1', 'en-US')
  }, PROJECT_KEY)
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path === '/api/v1/health' || path === '/api/v1/health/deep') {
      return fulfill(route, { status: 'ok', runtime_mode: 'mocked', services: { worker: { status: 'ok', mode: 'mocked', health_url: LONG_WORKER_HEALTH_URL, port_hint: 8787, missing_dependencies: [] } } })
    }
    if (path === '/api/v1/projects') return fulfill(route, [{ project_key: PROJECT_KEY, name: 'Mocked Ops Project', enabled: true, is_active: true }])
    if (path === '/api/v1/config/env') return fulfill(route, { variables: {} })
    if (path === '/api/v1/codex-auth/status') return fulfill(route, { authenticated: true })
    if (path === '/api/v1/admin/stats') return fulfill(route, { documents: { total: 1, recent_today: 0 }, social_data: { total: 0 }, sources: { total: 0 }, search_history: { total: 0 } })
    if (path === '/api/v1/admin/materials/list') {
      state.documentReads += 1
      if (options.documentError) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'error', error: { message: 'mocked document readback unavailable' } }) })
      return fulfill(route, { items: [{ id: 101, title: state.completed ? 'Terminal task refreshed this document' : LONG_TITLE, uri: `https://example.test/${'long-path-'.repeat(20)}`, doc_type: 'report', state: 'ready', has_extracted_data: false }], total: 1, page: 1, page_size: 20 })
    }
    if (['/api/v1/admin/materials/re-extract', '/api/v1/admin/materials/topic-extract', '/api/v1/governance/aggregator/sync'].includes(path)) {
      state.writes += 1
      return fulfill(route, { task_id: TASK_ID, async: !options.synchronous, trace_id: 'ops-repair-trace' })
    }
    if (path === `/api/v1/process/${TASK_ID}`) {
      if (options.taskError) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'error', error: { message: 'mocked task readback unavailable' } }) })
      return fulfill(route, { task_id: TASK_ID, status: state.completed ? 'SUCCESS' : 'STARTED', name: 'mocked.ops.extract', worker: 'mock-worker', progress: {} })
    }
    if (path === '/api/v1/admin/materials/bulk/extracted-data' || path === '/api/v1/admin/materials/delete') {
      const payload = route.request().postDataJSON() as { preview?: boolean }
      const preview = payload.preview === true
      if (preview) state.previews += 1
      else state.writes += 1
      return fulfill(route, {
        preview,
        task_id: preview ? 'not-an-executed-preview-task' : undefined,
        action_kind: 'bulk_structured_write',
        source_query: { project_key: PROJECT_KEY, ids: [101] },
        source_refs: [{ id: 'document:101', type: 'document' }],
        trace_chain: { trace_id: 'mock-preview-only' },
        evidence_preview: { execution_result_available: false },
        would_affect_count: 1,
      })
    }
    if (path.startsWith('/api/v1/business-lines/')) {
      state.diagnosticReads += 1
      return fulfill(route, { lines: [], lanes: [], summary: [], completion_boundary: [], diagnostics: {}, contract_version: 'mocked-observation-only' })
    }
    if (path === '/api/v1/agent-sessions' && method === 'GET') {
      state.sessionReads += 1
      return fulfill(route, { sessions: [] })
    }
    if (path === '/api/v1/admin/search-history') return fulfill(route, [])
    return fulfill(route, { items: [], total: 0 })
  })
  return state
}

test('ops/backend variants expose distinct responsibilities and progressive details (mocked)', async ({ page }) => {
  const state = await mockOps(page)
  await page.goto('/#/admin/ops')
  const ops = page.locator('.ops-page')
  await expect(ops.getByRole('tab', { name: 'Materials', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(ops.locator('.ops-documents-panel')).toBeVisible()
  await expect(ops.locator('.ops-runtime-panel')).toHaveCount(0)
  await expect(ops.locator('.ops-agent-session-panel')).toHaveCount(0)
  await expect(ops.getByRole('button', { name: 'Preview Bulk Write', exact: true })).toHaveCount(0)
  await expect.poll(() => state.sessionReads + state.diagnosticReads).toBe(0)
  await ops.getByRole('button', { name: 'Show advanced details', exact: true }).click()
  await expect(ops.getByRole('button', { name: 'Preview Bulk Write', exact: true })).toBeVisible()
  await ops.getByRole('link', { name: 'View system runtime' }).click()
  await expect(page).toHaveURL(/admin\/backend/)
  await expect(ops.locator('.ops-runtime-panel')).toBeVisible()
  await expect(ops.locator('.ops-documents-panel')).toHaveCount(0)
  await expect(ops.getByRole('tab', { name: 'Materials', exact: true })).toHaveCount(0)
  await ops.getByRole('tab', { name: 'Agent sessions', exact: true }).click()
  await expect(ops.locator('.ops-agent-session-panel')).toBeVisible()
  await expect.poll(() => state.sessionReads).toBeGreaterThan(0)
  await ops.getByRole('tab', { name: 'Technical diagnostics', exact: true }).click()
  await expect(page.getByTestId('ops-business-line-evidence-matrix')).toHaveCount(0)
  await ops.getByRole('button', { name: 'Show advanced details', exact: true }).click()
  await expect(page.getByTestId('ops-business-line-evidence-matrix')).toBeVisible()
  await expect.poll(() => state.diagnosticReads).toBeGreaterThan(0)
})

for (const action of ['Re-extract Materials', 'Topic Extract', 'Sync Aggregator']) {
  test(`${action} retains real task identity and refreshes documents on terminal readback (mocked)`, async ({ page }) => {
    const state = await mockOps(page)
    await page.goto('/#/admin/ops')
    const ops = page.locator('.ops-page')
    await expect(ops.locator('.ops-documents-panel')).toContainText(LONG_TITLE)
    await ops.getByRole('tab', { name: 'Governance', exact: true }).click()
    await ops.getByRole('button', { name: action, exact: true }).click()
    const notice = page.getByTestId('task-submission-notice')
    await expect(notice).toContainText(TASK_ID)
    await expect(notice).toContainText('Running')
    await expect(notice.getByRole('link', { name: 'View task' })).toHaveAttribute('href', new RegExp(`task_id=${TASK_ID}`))
    state.completed = true
    await notice.getByRole('button', { name: 'Refresh task status' }).click()
    await expect(notice).toContainText('Completed')
    await ops.getByRole('tab', { name: 'Materials', exact: true }).click()
    await expect(ops.locator('.ops-documents-panel')).toContainText('Terminal task refreshed this document')
  })
}

test('governance previews preserve nonexecution and missing execution evidence stays explicit (mocked)', async ({ page }) => {
  const state = await mockOps(page)
  await page.goto('/#/admin/ops')
  const ops = page.locator('.ops-page')
  await ops.getByRole('button', { name: 'Select Current Page', exact: true }).click()
  await ops.getByRole('button', { name: 'Show advanced details', exact: true }).click()
  await ops.getByRole('button', { name: 'Preview Bulk Write', exact: true }).click()
  const preview = page.getByTestId('ops-document-governance-preview')
  await expect(preview).toBeVisible()
  await expect(preview).toContainText('Preview mode did not execute writes')
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
  expect(state.previews).toBe(1)
  expect(state.writes).toBe(0)
  await ops.getByRole('button', { name: 'Bulk Write Structured Data', exact: true }).click()
  await expect(ops.getByRole('status')).toContainText('Execution result not yet read back')
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
})

test('async false never fabricates an asynchronous task receipt (mocked)', async ({ page }) => {
  await mockOps(page, { synchronous: true })
  await page.goto('/#/admin/ops')
  await page.locator('.ops-page').getByRole('tab', { name: 'Governance', exact: true }).click()
  await page.locator('.ops-page').getByRole('button', { name: 'Re-extract Materials', exact: true }).click()
  await expect(page.locator('.ops-page').getByRole('status')).toContainText('completed')
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
})

test('task readback unavailable retains receipt and documents query failures stay visible (mocked)', async ({ page }) => {
  await mockOps(page, { documentError: true, taskError: true })
  await page.goto('/#/admin/ops')
  await expect(page.locator('.ops-documents-panel').getByRole('alert')).toBeVisible()
  await page.locator('.ops-page').getByRole('tab', { name: 'Governance', exact: true }).click()
  await page.locator('.ops-page').getByRole('button', { name: 'Re-extract Materials', exact: true }).click()
  const notice = page.getByTestId('task-submission-notice')
  await expect(notice).toContainText(TASK_ID)
  await expect(notice).toContainText('Status unavailable; submission receipt retained', { timeout: 15000 })
  await expect(notice).not.toContainText('Completed')
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test(`ops/backend stay within ${viewport.width}px viewport with long content (mocked)`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockOps(page)
    await page.goto('/#/admin/ops')
    await expect(page.locator('.ops-documents-panel')).toContainText(LONG_TITLE)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`ops-${viewport.width}.png`), fullPage: true })
    await page.locator('.ops-page').getByRole('button', { name: 'Show advanced details', exact: true }).click()
    await expect(page.locator('#ops-document-tools')).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.locator('.ops-page').getByRole('link', { name: 'View system runtime' }).click()
    await expect(page.locator('.ops-runtime-panel')).toContainText(LONG_WORKER_HEALTH_URL)
    await expect(page.locator('.ops-runtime-panel')).toContainText(':8787')
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`backend-${viewport.width}.png`), fullPage: true })
  })
}
