import { expect, test, type Page } from '@playwright/test'

async function mockShell(page: Page) {
  await page.route('**/api/v1/health**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: { ok: true } }) })
  })
  await page.route('**/api/v1/config/env**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: { variables: {} } }) })
  })
  await page.route('**/api/v1/projects**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: [] }) })
  })
  await page.route('**/api/v1/codex-auth/status**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: { authenticated: true } }) })
  })
}

async function mockTaskDetail(page: Page, taskId: string, status = 'STARTED') {
  await page.route(`**/api/v1/process/${taskId}*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          task_id: taskId,
          name: 'e2e.ingest.task',
          status,
          worker: 'e2e-worker',
          progress: { stage: 'collecting', completed: 1, total: 3 },
        },
      }),
    })
  })
}

test('ingest async responses keep Celery task identity and preserve business metadata', async ({ page }) => {
  await mockShell(page)
  await mockTaskDetail(page, 'ingest-celery-e2e-1', 'STARTED')
  await page.route('**/api/v1/source_library/items**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: [] }) })
  })
  await page.route('**/api/v1/resource_pool/site_entries/grouped**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: { by_entry_type: {} } }) })
  })
  await page.route('**/api/v1/ingest/history**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data: [] }) })
  })
  await page.route('**/api/v1/ingest/market?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          task_id: 'ingest-celery-e2e-1',
          async: true,
          status: 'queued',
          trace_id: 'trace-ingest-e2e-1',
          submission_id: 'submission-ingest-e2e-1',
          trace_chain: {
            submission_id: 'submission-ingest-e2e-1',
            task_id: 'ingest-celery-e2e-1',
            trace_id: 'trace-ingest-e2e-1',
            retrieval_run_id: 'retrieval-run-e2e-1',
          },
        },
      }),
    })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'ingest-receipt-e2e')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.goto('/#/workbench/ingest')
  await page.getByRole('textbox', { name: '查询词' }).fill('battery market')
  await page.getByRole('button', { name: '市场采集' }).click()

  const notice = page.getByTestId('task-submission-notice')
  await expect(notice).toBeVisible()
  await expect(notice).toContainText('市场采集')
  await expect(notice).toContainText('正在执行')
  await expect(notice).toContainText('ingest-celery-e2e-1')
  await expect(notice).not.toContainText('submission-ingest-e2e-1')
  await expect(notice).not.toContainText('retrieval-run-e2e-1')
  await expect(page.getByTestId('ingest-action-status')).toContainText('submission_id: submission-ingest-e2e-1')
  await expect(page.getByTestId('ingest-action-status')).toContainText('检索运行: retrieval-run-e2e-1')

  await notice.getByRole('link', { name: '查看任务' }).click()
  await expect(page).toHaveURL(/task_id=ingest-celery-e2e-1/)
})

test('raw import async response tracks a real task while synchronous output stays plain', async ({ page }) => {
  await mockShell(page)
  await mockTaskDetail(page, 'raw-import-celery-e2e-1', 'STARTED')
  await page.route('**/api/v1/admin/materials/raw-import?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          task_id: 'raw-import-celery-e2e-1',
          async: true,
          inserted: 0,
          updated: 0,
          skipped: 0,
          error_count: 0,
        },
      }),
    })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'raw-receipt-e2e')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.goto('/#/workbench/raw-data')
  await page.locator('textarea').fill('raw import text')
  await page.getByRole('button', { name: '提交导入' }).click()

  const notice = page.getByTestId('task-submission-notice')
  await expect(notice).toBeVisible()
  await expect(notice).toContainText('raw-import-celery-e2e-1')
  await expect(page.getByText('inserted: 0')).toBeVisible()
  await notice.getByRole('link', { name: '查看任务' }).click()
  await expect(page).toHaveURL(/task_id=raw-import-celery-e2e-1/)
})

test('raw import without an async task receipt shows only synchronous result data', async ({ page }) => {
  await mockShell(page)
  await page.route('**/api/v1/admin/materials/raw-import?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { inserted: 2, updated: 1, skipped: 3, error_count: 0 } }),
    })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'raw-receipt-e2e')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.goto('/#/workbench/raw-data')
  await page.locator('textarea').fill('synchronous raw import')
  await page.getByRole('button', { name: '提交导入' }).click()

  await expect(page.getByText('inserted: 2')).toBeVisible()
  await expect(page.getByTestId('task-submission-notice')).toHaveCount(0)
})
