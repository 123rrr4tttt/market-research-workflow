import { expect, test, type Page, type Route } from '@playwright/test'

type ProcessMockMode = 'measured' | 'indeterminate' | 'detail-error'

type ProcessMockState = {
  status?: string
  progress?: Record<string, unknown>
  detailProgress?: Record<string, unknown>
  detailResult?: Record<string, unknown>
  detailTask?: Record<string, unknown>
}

const runningTask = {
  task_id: 'task-process-e2e',
  name: 'resource_url_extract',
  status: 'active',
  worker: 'worker.ingest',
  started_at: '2026-10-05T08:00:00Z',
  updated_at: '2026-10-05T08:05:00Z',
  kwargs: { scope: 'document_pool' },
  display_meta: { stage: 'extract', inserted: 12, rejected_count: 1 },
}

const runningProgress = {
  measured: { stage: 'extract', completed: 12, total: 20 },
  indeterminate: { stage: 'normalize', percent: 62 },
  'detail-error': { stage: 'extract', completed: 3, total: 9 },
}

const explicitProgressPairs = [
  ['completed', 'total'],
  ['processed_count', 'total_count'],
  ['batches_completed', 'batches_total'],
  ['processed', 'total_items'],
] as const

function apiEnvelope(data: unknown) {
  return {
    status: 'ok',
    data,
  }
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(apiEnvelope(data)),
  })
}

async function mockProcessPage(page: Page, mode: ProcessMockMode, state: ProcessMockState = {}) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname

    if (pathname === '/api/v1/health') {
      await fulfillJson(route, { status: 'ok' })
      return
    }
    if (pathname === '/api/v1/config/env') {
      await fulfillJson(route, { variables: {} })
      return
    }
    if (pathname === '/api/v1/projects') {
      await fulfillJson(route, { items: [{ project_key: 'process_e2e', name: 'Process E2E', enabled: true }] })
      return
    }
    if (pathname === '/api/v1/codex-auth/status') {
      await fulfillJson(route, { authenticated: true })
      return
    }
    if (pathname === '/api/v1/process/list') {
      await fulfillJson(route, {
        tasks: [{
          ...runningTask,
          status: state.status || runningTask.status,
          progress: state.progress || runningProgress[mode],
        }],
        stats: { total_tasks: 1, active_tasks: 1, pending_tasks: 0 },
      })
      return
    }
    if (pathname === '/api/v1/process/stats') {
      await fulfillJson(route, {
        active_tasks: 1,
        scheduled_tasks: 0,
        reserved_tasks: 0,
        total_running: 1,
        workers: 1,
        worker_names: ['worker.ingest'],
      })
      return
    }
    if (pathname === '/api/v1/process/history') {
      await fulfillJson(route, {
        history: [
          {
            id: 91,
            task_id: 'history-task-e2e',
            task_name: '历史入库任务',
            job_type: 'ingest',
            status: 'failed',
            params: { topic: '储能', error: 'source timeout', urls_extracted: 317 },
            started_at: '2026-10-05T07:00:00Z',
            finished_at: '2026-10-05T07:02:00Z',
            duration_seconds: 120,
            error: 'source timeout',
            source: 'history',
          },
        ],
        total: 1,
      })
      return
    }
    if (pathname === `/api/v1/process/${runningTask.task_id}`) {
      if (mode === 'detail-error') {
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'error' }) })
        return
      }
      await fulfillJson(route, {
        ...runningTask,
        ...state.detailTask,
        status: state.status || runningTask.status,
        progress: state.detailProgress || state.progress || runningProgress[mode],
        result: state.detailResult || { inserted: 12 },
      })
      return
    }
    if (pathname === `/api/v1/process/${runningTask.task_id}/logs`) {
      await fulfillJson(route, {
        task_id: runningTask.task_id,
        tail: 200,
        filtered: true,
        text: [
          `task_id=${runningTask.task_id}`,
          'status=STARTED',
          '2026-10-05 worker.ingest resource_url_extract extract started',
        ].join('\n'),
        log_file: '/var/log/celery/worker.log',
      })
      return
    }

    await fulfillJson(route, { items: [], total: 0 })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'process_e2e')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
}

test('task deep link opens an accessible drawer with measured progress', async ({ page }) => {
  await mockProcessPage(page, 'measured')
  await page.goto(`/#/admin/process?task_id=${runningTask.task_id}&source=e2e`)

  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer).toBeVisible()
  await expect(drawer).toHaveAttribute('role', 'dialog')
  await expect(drawer).toHaveAttribute('aria-modal', 'true')
  await expect(drawer.getByRole('heading', { level: 2, name: 'resource_url_extract' })).toBeVisible()
  await expect(drawer.locator('.process-detail-drawer__identity').getByText('task-process-e2e', { exact: true })).toBeVisible()
  await expect(drawer.locator('.process-detail-summary')).toContainText('extract')
  await expect(drawer.getByRole('progressbar', { name: /进度/ })).toHaveAttribute('aria-valuenow', '12')
  await expect(drawer.getByText('12 / 20 (60%)')).toBeVisible()
  await expect(drawer.locator('pre').first()).toBeHidden()
  const historyRow = page.getByRole('row').filter({ has: page.getByRole('cell', { name: '91', exact: true }) })
  await expect(historyRow).toContainText('历史入库任务')
  await expect(historyRow).toContainText('URL 317')

  await drawer.getByText('技术诊断').click()
  const logsBlock = drawer.getByText('logs (tail 200)').locator('..')
  await expect(logsBlock).toContainText('task_id=task-process-e2e')
  await expect(logsBlock).toContainText('resource_url_extract extract started')

  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
})

test('drawer close returns focus to the invoking row action', async ({ page }) => {
  await mockProcessPage(page, 'measured')
  await page.goto('/#/admin/process')

  const details = page
    .getByRole('cell', { name: runningTask.task_id, exact: true })
    .locator('..')
    .getByRole('button', { name: '详情', exact: true })
  await details.click()
  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(details).toBeFocused()
})

test('processing route uses running focus without inventing progress', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockProcessPage(page, 'indeterminate')
  await page.goto('/#/admin/process/processing')

  await expect(page.getByRole('tab', { name: '进行中' })).toHaveAttribute('aria-selected', 'true')
  await page
    .getByRole('cell', { name: runningTask.task_id, exact: true })
    .locator('..')
    .getByRole('button', { name: '详情', exact: true })
    .click()
  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer.getByRole('status')).toContainText('运行中')
  await expect(drawer.getByRole('progressbar')).toHaveCount(0)

  const spinner = drawer.locator('.process-progress__spinner')
  await expect(spinner).toBeVisible()
  await expect(spinner).toHaveCSS('animation-name', 'none')
})

test('measured progress accepts only strict pairs from one record', async ({ page }) => {
  const state: Required<ProcessMockState> = {
    status: 'STARTED',
    progress: {},
    detailProgress: {},
    detailResult: {},
    detailTask: {},
  }
  await mockProcessPage(page, 'measured', state)
  await page.goto(`/#/admin/process?task_id=${runningTask.task_id}`)

  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer).toBeVisible()
  const refresh = drawer.getByRole('button', { name: '刷新', exact: true })

  const applyFixture = async (
    detailProgress: Record<string, unknown>,
    detailResult: Record<string, unknown> = {},
  ) => {
    state.progress = { stage: 'queue' }
    state.detailProgress = detailProgress
    state.detailResult = detailResult
    await refresh.click()
  }

  for (const [numeratorKey, denominatorKey] of explicitProgressPairs) {
    await applyFixture(
      { stage: 'outer' },
      { progress: { stage: 'nested', [numeratorKey]: 3, [denominatorKey]: 7 } },
    )
    const bar = drawer.getByRole('progressbar', { name: /进度/ })
    await expect(bar).toHaveAttribute('aria-valuenow', '3')
    await expect(bar).toHaveAttribute('aria-valuemax', '7')
    await expect(drawer.getByText('3 / 7 (42%)')).toBeVisible()

    for (const invalidNumerator of [null, true, '']) {
      await applyFixture({ stage: 'invalid', [numeratorKey]: invalidNumerator, [denominatorKey]: 7 })
      await expect(drawer.getByRole('progressbar')).toHaveCount(0)
      await expect(drawer.getByRole('status')).toContainText('运行中')
    }

    await applyFixture({ stage: 'no-denominator', [numeratorKey]: 3 })
    await expect(drawer.getByRole('progressbar')).toHaveCount(0)
    await expect(drawer.getByRole('status')).toContainText('运行中')
  }

  await applyFixture(
    { stage: 'cross-layer', processed_count: 4 },
    { progress: { stage: 'nested', total_count: 9 } },
  )
  await expect(drawer.getByRole('progressbar')).toHaveCount(0)
  await expect(drawer.getByRole('status')).toContainText('运行中')
})

test('completed elapsed uses measured detail values without ticking', async ({ page }) => {
  const state: Required<ProcessMockState> = {
    status: 'SUCCESS',
    progress: {},
    detailProgress: {},
    detailResult: {},
    detailTask: {},
  }
  await mockProcessPage(page, 'measured', state)
  await page.goto(`/#/admin/process?task_id=${runningTask.task_id}`)

  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer).toBeVisible()
  const elapsed = drawer
    .locator('.process-detail-summary > div')
    .filter({ hasText: '耗时' })
    .locator('strong')
  await expect(elapsed).toHaveText('未观测')

  await page.waitForTimeout(1100)
  await drawer.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(elapsed).toHaveText('未观测')

  state.detailTask = { duration_seconds: 0.1 }
  await drawer.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(elapsed).toHaveText('0.1s')
})

test('history detail preserves both history and task identities', async ({ page }) => {
  await mockProcessPage(page, 'measured')
  await page.goto('/#/admin/process?history_id=91')

  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer.getByRole('heading', { level: 2, name: '历史入库任务' })).toBeVisible()
  await expect(drawer.getByText('history#91')).toBeVisible()
  await expect(drawer.getByText('history-task-e2e')).toBeVisible()
  await expect(drawer.getByText('source timeout').first()).toBeVisible()
  await expect(drawer.locator('pre').first()).toBeHidden()
})

test('task readback failure is reported without marking the task failed', async ({ page }) => {
  await mockProcessPage(page, 'detail-error')
  await page.goto('/#/admin/process')

  await page
    .getByRole('cell', { name: runningTask.task_id, exact: true })
    .locator('..')
    .getByRole('button', { name: '详情', exact: true })
    .click()
  const drawer = page.getByTestId('process-detail-drawer')
  await expect(drawer.getByRole('alert')).toContainText('任务状态暂时不可读取')
  await expect(drawer.getByText('active')).toBeVisible()
  await expect(drawer.getByRole('button', { name: '重试读取' })).toBeVisible()
  await expect(drawer.getByText('failed')).toHaveCount(0)
})
