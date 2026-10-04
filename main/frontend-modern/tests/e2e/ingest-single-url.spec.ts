import { expect, test, type Page } from '@playwright/test'

async function mockShellApis(page: Page) {
  await page.route('**/api/v1/health**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { ok: true } }),
    })
  })
  await page.route('**/api/v1/config/env**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { variables: {} } }),
    })
  })
  await page.route('**/api/v1/projects**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    })
  })
  await page.route('**/api/v1/codex-auth/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { authenticated: true } }),
    })
  })
  await page.route('**/api/v1/source_library/items**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    })
  })
  await page.route('**/api/v1/resource_pool/site_entries/grouped**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { by_entry_type: {} } }),
    })
  })
}

test('specialized ingest exposes direct URL collection without an NL command control', async ({ page }) => {
  const nlCommandRequests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/agent-batch/nl-command')) {
      nlCommandRequests.push(request.url())
    }
  })
  await mockShellApis(page)
  await page.goto('/#/workbench/ingest/specialized')

  await expect(page.getByRole('button', { name: '执行单 URL 入库' })).toBeVisible()
  await expect(page.getByRole('button', { name: '自然语言触发批量采集' })).toHaveCount(0)
  expect(nlCommandRequests).toEqual([])
})

test('single url ingest sends standardized payload and shows task feedback', async ({ page }) => {
  let capturedPayload: Record<string, unknown> | null = null
  let submitted = false
  await mockShellApis(page)

  await page.route('**/api/v1/ingest/history**', async (route) => {
    const rows = submitted
      ? [
          {
            submission_id: 'submission-e2e-1',
            idempotency_key: 'single-url-e2e-key-1',
            task_id: 'single-url-task-e2e-1',
            submission_status: 'queued',
            submission_source: 'single_url',
            created_at: '2026-05-24T10:00:00Z',
            trace_id: 'trace-single-url-e2e-1',
            trace_chain: {
              submission_id: 'submission-e2e-1',
              task_id: 'single-url-task-e2e-1',
              trace_id: 'trace-single-url-e2e-1',
              retrieval_run_id: 'retrieval-run-e2e-1',
            },
            feedback_state: {
              status: 'history_readback_ready',
            },
            degradation_flags: ['fallback_used'],
          },
        ]
      : []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: rows }),
    })
  })

  await page.route('**/api/v1/search/runs/retrieval-run-e2e-1**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          retrieval_run_id: 'retrieval-run-e2e-1',
          source_refs: ['source-ref-1', 'source-ref-2'],
          provider_trace: { status: 'ok', provider: 'ddg_html' },
          index_freshness: { status: 'fresh', backend: 'memory' },
          retrieval_run_readback: { status: 'available' },
          source_query: { query_terms: ['example'] },
          known_limitations: ['sample_only'],
        },
      }),
    })
  })

  await page.route('**/api/v1/ingest/url/single**', async (route) => {
    const request = route.request()
    try {
      capturedPayload = request.postDataJSON() as Record<string, unknown>
    } catch {
      capturedPayload = null
    }
    submitted = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          submission_id: 'submission-e2e-1',
          task_id: 'single-url-task-e2e-1',
          status: 'queued',
          async: true,
          degradation_flags: ['fallback_used'],
          trace_id: 'trace-single-url-e2e-1',
          trace_chain: {
            contract_version: 'ingest.feedback.v1',
            submission_id: 'submission-e2e-1',
            task_id: 'single-url-task-e2e-1',
            trace_id: 'trace-single-url-e2e-1',
            retrieval_run_id: 'retrieval-run-e2e-1',
            provider_trace: { provider: 'ddg_html' },
            fallback: { used: true },
            index_freshness: { backend: 'memory' },
            known_limitations: ['sample_only'],
          },
          params: {
            url: 'https://example.com/article',
            strict_mode: false,
          },
        },
      }),
    })
  })

  await page.goto('/#/workbench/ingest/specialized')
  await expect(page.getByRole('button', { name: '执行单 URL 入库' })).toBeVisible()

  await page.getByPlaceholder('https://example.com/article').fill('https://example.com/article')
  await page.getByRole('button', { name: '执行单 URL 入库' }).click()

  await expect(page.getByText('单 URL 采集 已提交，任务 ID: single-url-task-e2e-1')).toBeVisible()
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('最近一次提交：当前页面动作')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('history 已读回同一 submission')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('提交来源: 单 URL 采集')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('submission_id: submission-e2e-1')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('single-url-task-e2e-1')
  await expect(page.getByTestId('ingest-action-status')).toContainText('追踪: trace-single-url-e2e-1')
  await expect(page.getByTestId('ingest-action-status')).toContainText('fallback: true')

  await page.getByRole('button', { name: '加载检索运行详情' }).click()
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('来源引用: 2')
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('回读状态: available')

  expect(capturedPayload).toBeTruthy()
  expect(capturedPayload).toMatchObject({
    url: 'https://example.com/article',
    strict_mode: false,
    search_expand: true,
    search_expand_limit: 3,
    search_provider: 'auto',
    search_fallback_provider: 'ddg_html',
    fallback_on_insufficient: true,
    allow_search_summary_write: false,
    min_results_required: 6,
    target_candidates: 6,
    decode_redirect_wrappers: true,
    filter_low_value_candidates: true,
    async_mode: true,
  })
})

test('single url history feedback row remains visible without legacy job fields', async ({ page }) => {
  let capturedPayload: Record<string, unknown> | null = null
  await mockShellApis(page)

  await page.route('**/api/v1/ingest/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: [
          {
            submission_id: 'history-submission-1',
            idempotency_key: 'history-key-1',
            task_id: 'history-single-url-task',
            submission_source: 'single_url',
            submission_status: 'completed',
            created_at: '2026-05-24T10:00:00Z',
            degradation_flags: ['fallback_used'],
            trace_chain: {
              submission_id: 'history-submission-1',
              task_id: 'history-single-url-task',
              trace_id: 'trace-history-1',
              retrieval_run_id: 'retrieval-history-1',
            },
            feedback_state: {
              status: 'history_readback_ready',
            },
          },
        ],
      }),
    })
  })

  await page.route('**/api/v1/ingest/url/single**', async (route) => {
    const request = route.request()
    capturedPayload = request.postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          task_id: 'single-url-task-strict',
          status: 'queued',
          async: true,
        },
      }),
    })
  })

  await page.goto('/#/workbench/ingest/specialized')

  await expect(page.getByTestId('ingest-recent-submission')).toContainText('最近一次提交：历史记录')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('submission_id: history-submission-1')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('history-single-url-task')
  await expect(page.getByTestId('ingest-recent-submission')).toContainText('trace-history-1')

  await page.getByPlaceholder('https://example.com/article').fill('https://example.com/strict-review')
  await page.getByTestId('single-url-preset-strict').click()
  await page.getByRole('button', { name: '执行单 URL 入库' }).click()

  await expect(page.getByTestId('ingest-recent-submission')).toContainText('single-url-task-strict')
  expect(capturedPayload).toMatchObject({
    url: 'https://example.com/strict-review',
    strict_mode: true,
    search_expand_limit: 6,
    min_results_required: 8,
    target_candidates: 8,
    light_filter_min_score: 60,
    filter_low_value_candidates: true,
  })
})

test('single url strict mode failure shows reason in action message', async ({ page }) => {
  await mockShellApis(page)

  await page.route('**/api/v1/ingest/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    })
  })

  await page.route('**/api/v1/ingest/url/single**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'error',
        data: null,
        error: {
          code: 'URL_POLICY_LOW_VALUE',
          message: 'single_url blocked by policy',
          details: {
            reason: 'url_policy_low_value_endpoint',
            degradation_flags: ['url_gate_rejected'],
          },
        },
        meta: {
          trace_id: 'trace-error-e2e-1',
        },
      }),
    })
  })

  await page.goto('/#/workbench/ingest/specialized')
  await expect(page.getByRole('button', { name: '执行单 URL 入库' })).toBeVisible()

  await page.getByPlaceholder('https://example.com/article').fill('https://example.com/login')
  await page.getByLabel('严格模式').check()
  await page.getByRole('button', { name: '执行单 URL 入库' }).click()

  await expect(page.getByText('单 URL 采集 失败:')).toBeVisible()
  await expect(page.getByTestId('ingest-action-status').getByText('提交来源: 单 URL 采集', { exact: true })).toBeVisible()
  await expect(page.getByTestId('ingest-action-status').getByText('代码: URL_POLICY_LOW_VALUE', { exact: true })).toBeVisible()
  await expect(page.getByTestId('ingest-action-status').getByText('原因: url_policy_low_value_endpoint', { exact: true })).toBeVisible()
  await expect(page.getByTestId('ingest-action-status').getByText('降级: url_gate_rejected', { exact: true })).toBeVisible()
  await expect(page.getByTestId('ingest-action-status').getByText('追踪: trace-error-e2e-1', { exact: true })).toBeVisible()
})
