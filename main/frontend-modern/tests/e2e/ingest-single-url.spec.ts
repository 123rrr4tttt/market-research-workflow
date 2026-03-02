import { expect, test } from '@playwright/test'

test('single url ingest sends standardized payload and shows task feedback', async ({ page }) => {
  let capturedPayload: Record<string, unknown> | null = null

  await page.route('**/api/v1/ingest/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: [] }),
    })
  })

  await page.route('**/api/v1/ingest/url/single**', async (route) => {
    const request = route.request()
    try {
      capturedPayload = request.postDataJSON() as Record<string, unknown>
    } catch {
      capturedPayload = null
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          task_id: 'single-url-task-e2e-1',
          status: 'queued',
          async: true,
          params: {
            url: 'https://example.com/article',
            strict_mode: false,
          },
        },
      }),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: '采集', exact: true }).click()

  await page.getByPlaceholder('https://example.com/article').fill('https://example.com/article')
  await page.getByRole('button', { name: '执行单 URL 入库' }).click()

  await expect(page.getByText('单 URL 采集 已提交，任务 ID: single-url-task-e2e-1')).toBeVisible()

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

test('single url strict mode failure shows reason in action message', async ({ page }) => {
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
      }),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: '采集', exact: true }).click()

  await page.getByPlaceholder('https://example.com/article').fill('https://example.com/login')
  await page.getByLabel('严格模式').check()
  await page.getByRole('button', { name: '执行单 URL 入库' }).click()

  await expect(page.getByText('单 URL 采集 失败:')).toBeVisible()
  await expect(page.getByText('原因: url_policy_low_value_endpoint')).toBeVisible()
  await expect(page.getByText('降级: url_gate_rejected')).toBeVisible()
})
