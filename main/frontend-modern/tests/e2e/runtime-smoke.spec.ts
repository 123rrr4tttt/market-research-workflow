import { expect, test, type Page, type Route } from '@playwright/test'
import { requireRealBackendReadiness, SKIP_BACKEND_CHECK, type RealBackendReadinessResult } from './helpers/backend-readiness'

function skipWhenBackendCheckBypassed(backendReadiness: RealBackendReadinessResult) {
  test.skip(
    backendReadiness?.skipped === true,
    `${SKIP_BACKEND_CHECK}=1 bypasses live-backend readiness; this real-backend proof was not run.`,
  )
}

function apiEnvelope(data: unknown) {
  return {
    status: 'success',
    data,
    error: null,
    meta: { trace_id: 'dashboard-runtime-smoke-mock' },
  }
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(apiEnvelope(data)),
  })
}

async function fulfillTextDownload(route: Route, filename: string, text: string) {
  await route.fulfill({
    status: 200,
    contentType: 'text/markdown;charset=utf-8',
    headers: { 'content-disposition': `attachment; filename="${filename}"` },
    body: text,
  })
}

async function fulfillBinaryDownload(route: Route, filename: string, contentType: string, body: string) {
  await route.fulfill({
    status: 200,
    contentType,
    headers: {
      'content-disposition': `attachment; filename="${filename}"`,
      'x-llm-report-export-readiness': 'ready',
    },
    body,
  })
}

type CapturedApiCall = {
  method: string
  pathname: string
}

async function mockDashboardReportApi(
  page: Page,
  captured: {
    apiCalls: CapturedApiCall[]
    reportPayloads: Array<Record<string, unknown>>
    fileExportPayloads: Array<{
      format: 'pdf' | 'docx'
      payload: Record<string, unknown>
    }>
  },
) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    captured.apiCalls.push({ method: request.method(), pathname })

    if (pathname === '/api/v1/health' || pathname === '/api/v1/health/deep') {
      await fulfillJson(route, { status: 'ok', provider: 'mocked-dashboard-runtime-smoke' })
      return
    }

    if (pathname === '/api/v1/projects') {
      await fulfillJson(route, {
        items: [
          { project_key: 'dashboard_e2e', name: 'Dashboard E2E', enabled: true },
          { project_key: 'default', name: 'Default', enabled: true },
        ],
      })
      return
    }

    if (/^\/api\/v1\/projects\/[^/]+\/activate$/.test(pathname)) {
      await fulfillJson(route, { project_key: pathname.split('/').at(-2) || 'dashboard_e2e' })
      return
    }

    if (pathname === '/api/v1/business-lines/evidence-matrix') {
      await fulfillJson(route, {
        contract_version: 'business_line.evidence_matrix.v2',
        vocabulary_version: 'business_line.vocabulary.current.v1',
        coverage: { covered_line_count: 0, covered_line_keys: [], not_admin_only: true },
        worker_readback: {
          contract_version: 'business_line.worker_readback_contract.v2',
          covered_line_keys: [],
          completion_claim: 'not_observed_without_live_worker_readback',
        },
        scheduled_observation: {
          observation_status: 'not_observed',
          scheduled_run_evidence: 'not_observed',
          install_status: 'unknown',
          completion_claim: 'not_observed',
        },
        ui_boundary: {
          reset_telemetry: {
            event_name: 'reset_empty_warning_view',
            event_scope: 'ui_event_log_only',
            filter_transition: { from: 'warning_only', to: 'all' },
            sort_behavior: 'unchanged',
            api_payload_behavior: 'unchanged',
            scheduled_evidence_write: 'none',
            scheduled_completion_proof: false,
            scheduled_evidence_controller: 'scheduled_run_evidence',
          },
          read_only_context: {
            not_report_proof: true,
            not_quality_gate_input: true,
            not_scheduled_run_evidence_proof: true,
            scheduled_evidence_write: 'none',
            scheduled_completion_proof_behavior: 'unchanged',
            audit_outcome_behavior: 'unchanged',
            observation_status: 'not_applicable_ui_boundary',
          },
        },
      })
      return
    }

    if (pathname === '/api/v1/dashboard/stats') {
      await fulfillJson(route, {
        documents: {
          total: 42,
          recent_today: 3,
          recent_7d: 9,
          extraction_rate: 0.88,
          type_distribution: { report: 7, memo: 2 },
          source_refs: [
            {
              id: 'dashboard-documents-source',
              kind: 'table',
              table: 'documents',
              detail: 'dashboard documents source',
            },
          ],
        },
        sources: {
          total: 5,
          enabled: 4,
          source_refs: [{ id: 'dashboard-sources-source', table: 'source_library' }],
        },
        market_stats: {
          total: 11,
          states_count: 3,
          source_refs: [{ id: 'dashboard-market-source', table: 'market_stats' }],
        },
        tasks: {
          total: 6,
          running: 1,
          completed: 4,
          failed: 1,
          source_refs: [{ id: 'dashboard-tasks-source', table: 'process_tasks' }],
          frontdoor_tri_state: {
            states: ['success', 'degraded_success', 'failed'],
            counts: { success: 4, degraded_success: 1, failed: 1 },
            source_refs: [{ id: 'dashboard-frontdoor-source', table: 'ingest_registry' }],
          },
        },
        llm_report_quality: {
          summary: {
            total: 2,
            by_decision: { pass: 1, fail: 1 },
            readiness: { ready: 1, review_required: 1 },
            avg_citation_coverage: 0.92,
            avg_evidence_coverage: 0.81,
            export_events: {
              total: 2,
              trusted: 1,
              legacy: 1,
              blocked: 1,
              token_invalid: 1,
              by_format: { pdf: 1, docx: 1 },
            },
          },
          actionability: { next_action: 'Inspect blocked export token lineage' },
          source_refs: [{ id: 'llm-report-quality-source', table: 'llm_report_quality' }],
          recent_records: [
            {
              trace_id: 'trace-dashboard-57',
              request_id: 'req-dashboard-57',
              project_key: 'dashboard_e2e',
              decision: 'pass',
              readiness: 'ready',
              citation_coverage: 0.94,
              evidence_coverage: 0.83,
              job_id: 5701,
              job_status: 'completed',
              recorded_at: '2026-05-24T12:00:00Z',
              next_action: 'Export with trusted artifact token',
            },
          ],
          recent_export_events: [
            {
              source_trace_id: 'trace-dashboard-57',
              trace_id: 'export-dashboard-57-pdf',
              project_key: 'dashboard_e2e',
              export_format: 'pdf',
              export_outcome: 'success',
              export_integrity_mode: 'trusted',
              export_integrity_trusted: true,
              artifact_id: 'artifact-dashboard-57',
              content_size_bytes: 1024,
              recorded_at: '2026-05-24T12:05:00Z',
            },
          ],
        },
        pending_actions: [
          {
            id: 'pending-dashboard-57',
            type: 'report_export_review',
            status: 'open',
            severity: 'medium',
            title: 'Review report export evidence',
            source_metric: 'documents.total',
            source_refs: ['dashboard-documents-source'],
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/dashboard/drilldown') {
      await fulfillJson(route, {
        metric: url.searchParams.get('metric') || 'documents.total',
        source_ref: url.searchParams.get('source_ref') || 'dashboard-documents-source',
        filters: { source_ref: url.searchParams.get('source_ref') || 'dashboard-documents-source' },
        row_count: 1,
        source_query: {
          scope: 'dashboard.stats',
          table: 'documents',
          metrics: ['documents.total'],
          filters: { project_key: 'dashboard_e2e' },
        },
        source_refs: [
          {
            id: 'dashboard-documents-source',
            kind: 'table',
            table: 'documents',
            columns: ['id', 'title', 'source_ref'],
          },
        ],
        sample_rows: [
          {
            id: 57,
            title: 'Boundary D dashboard evidence row',
            source_ref: 'dashboard-documents-source',
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/dashboard/report-from-filter') {
      captured.reportPayloads.push((request.postDataJSON() as Record<string, unknown>) || {})
      await fulfillJson(route, {
        contract_version: 'dashboard.report_from_filter.v1',
        report_id: 'report-dashboard-57',
        draft_id: 5702,
        document_id: 5702,
        title: 'Boundary D Dashboard Report',
        status: 'draft',
        source_refs: [{ id: 'dashboard-documents-source', table: 'documents' }],
        quality: {
          status: 'ready',
          quality_gate_mode: 'strict',
          report_quality_gate: {
            status: 'ready',
            warnings: [],
            blocking_reasons: [],
            missing_items: [],
          },
          checklist: [{ id: 'source_refs', status: 'pass', detail: 'source_refs preserved' }],
        },
        export_artifact: {
          artifact_id: 'artifact-dashboard-57',
          artifact_token: 'trusted-token-dashboard-57',
          artifact_sha256: 'sha256-dashboard-57',
          markdown_sha256: 'markdown-sha256-dashboard-57',
        },
      })
      return
    }

    if (pathname === '/api/v1/dashboard/llm-report-detail') {
      await fulfillJson(route, {
        contract_version: 'dashboard.llm_report_detail.v1',
        found: true,
        trace_id: url.searchParams.get('trace_id') || 'trace-dashboard-57',
        request_id: 'req-dashboard-57',
        project_key: 'dashboard_e2e',
        source_refs: [{ id: 'dashboard-documents-source', table: 'documents' }],
        source_query: { scope: 'dashboard.stats', table: 'documents' },
        report_artifact: {
          artifact_id: 'artifact-dashboard-57',
          artifact_sha256: 'sha256-dashboard-57',
        },
        quality_gate: { decision: 'pass', status: 'ready' },
        repair_context: {
          trace_id: 'trace-dashboard-57',
          project_key: 'dashboard_e2e',
          action: 'replay_export_with_trusted_token',
        },
        export_events: [
          {
            export_format: 'pdf',
            export_outcome: 'success',
            artifact_id: 'artifact-dashboard-57',
            recorded_at: '2026-05-24T12:05:00Z',
          },
        ],
      })
      return
    }

    if (pathname.startsWith('/api/v1/search/runs/')) {
      const retrievalRunId = decodeURIComponent(pathname.split('/').pop() || 'retrieval_run_dashboard_57')
      await fulfillJson(route, {
        retrieval_run_id: retrievalRunId,
        run_id: retrievalRunId,
        source_query: {
          scope: 'search.retrieval_run',
          query: 'dashboard market signal',
          project_key: 'dashboard_e2e',
        },
        source_refs: [
          {
            id: `search.retrieval_run:${retrievalRunId}`,
            type: 'search_retrieval_run',
            retrieval_run_id: retrievalRunId,
          },
          {
            id: `search.evidence_hit:${retrievalRunId}:eh_1`,
            type: 'search_evidence_hit',
            source_id: 'dashboard-search-source',
          },
        ],
        provider_trace: {
          contract_version: 'search.provider_trace.compat.v1',
          retrieval_run_id: retrievalRunId,
          providers_used: ['opensearch_lexical', 'qdrant_vector'],
          fallback_order: ['opensearch_lexical', 'qdrant_vector', 'pgvector_fallback'],
          index_backend: 'opensearch_lexical',
          fallback_used: true,
          index_freshness: {
            freshness_state: 'fallback_available',
            readback_available: true,
            fallback_used: true,
          },
        },
        index_freshness: {
          contract_version: 'search.index_freshness.v1',
          retrieval_run_id: retrievalRunId,
          index_backend: 'opensearch_lexical',
          freshness_state: 'fallback_available',
          readback_available: true,
          fallback_used: true,
          freshness_basis: 'retrieval_run_readback',
        },
        retrieval_run_readback: {
          status: 'passed',
          readback_available: true,
          branch_count: 2,
          hit_count: 1,
        },
      })
      return
    }

    if (pathname === '/api/v1/writing/export/markdown') {
      await fulfillTextDownload(route, 'boundary-d-dashboard-report.md', '# Boundary D Dashboard Report\n')
      return
    }

    if (pathname === '/api/v1/llm-report/export/pdf') {
      captured.fileExportPayloads.push({
        format: 'pdf',
        payload: (request.postDataJSON() as Record<string, unknown>) || {},
      })
      await fulfillBinaryDownload(route, 'boundary-d-dashboard-report.pdf', 'application/pdf', '%PDF-1.4\n')
      return
    }

    if (pathname === '/api/v1/llm-report/export/docx') {
      captured.fileExportPayloads.push({
        format: 'docx',
        payload: (request.postDataJSON() as Record<string, unknown>) || {},
      })
      await fulfillBinaryDownload(
        route,
        'boundary-d-dashboard-report.docx',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'PK\u0003\u0004',
      )
      return
    }

    await route.fulfill({
      status: request.method() === 'GET' ? 404 : 500,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'error',
        data: null,
        error: {
          code: 'UNMOCKED_API_REQUEST',
          message: `Unmocked ${request.method()} ${pathname}`,
        },
        meta: { trace_id: 'dashboard-runtime-smoke-unmocked' },
      }),
    })
  })
}

async function bootstrapMockedDashboard(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'dashboard_e2e')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], {
    origin: `http://127.0.0.1:${process.env.FRONTEND_E2E_PORT || '4173'}`,
  })
}

test('homepage runtime smoke uses live backend', async ({ page, request }) => {
  const backendReadiness = await requireRealBackendReadiness(request)
  skipWhenBackendCheckBypassed(backendReadiness)
  await page.addInitScript(() => {
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  const projectsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/projects') && response.status() === 200
  })

  const response = await page.goto('/')
  expect(response?.ok()).toBeTruthy()
  await projectsResponse

  await expect(page.getByRole('heading', { level: 1, name: '运行记录', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: '目标项目', exact: true })).toBeVisible()
})

test('graph runtime smoke loads against live graph endpoints', async ({ page, request }) => {
  const backendReadiness = await requireRealBackendReadiness(request)
  skipWhenBackendCheckBypassed(backendReadiness)
  const graphConfigResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/project-customization/graph-config') && response.status() === 200
  })
  const marketGraphResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/market-graph') && response.status() === 200
  })

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await graphConfigResponse
  await marketGraphResponse

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  await expect(page.getByText('节点总数', { exact: true })).toBeVisible()
  await expect(page.getByText('边总数', { exact: true })).toBeVisible()
})

test('dashboard report browser behavior uses mocked backend only (not real-backend proof)', async ({ page }) => {
  const captured = {
    apiCalls: [] as CapturedApiCall[],
    reportPayloads: [] as Array<Record<string, unknown>>,
    fileExportPayloads: [] as Array<{
      format: 'pdf' | 'docx'
      payload: Record<string, unknown>
    }>,
  }
  await mockDashboardReportApi(page, captured)
  await bootstrapMockedDashboard(page)

  const statsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/dashboard/stats') && response.status() === 200
  })
  const response = await page.goto('/#dashboard.html')
  expect(response?.ok()).toBeTruthy()
  await statsResponse

  await expect(page.getByRole('heading', { level: 1, name: '数据仪表盘' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 3, name: '从当前过滤器生成报告' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 3, name: '检索运行详情' })).toBeVisible()

  await page.getByTestId('dashboard-search-run-id-input').fill('retrieval_run_dashboard_57')
  await page.getByTestId('dashboard-load-search-run').click()
  await expect(page.getByText('当前 run: retrieval_run_dashboard_57')).toBeVisible()
  await expect(page.getByTestId('dashboard-search-run-provider-trace')).toContainText('opensearch_lexical')
  await expect(page.getByTestId('dashboard-search-run-provider-trace')).toContainText('"fallback_used": true')
  await expect(page.getByTestId('dashboard-search-run-index-freshness')).toContainText('fallback_available')
  await expect(page.getByTestId('dashboard-search-run-index-freshness')).toContainText('"readback_available": true')
  await expect(page.getByTestId('dashboard-search-run-source-refs')).toContainText('dashboard-search-source')

  await page.getByTestId('dashboard-source-ref-dashboard-documents-source').first().click()
  await expect(page.getByText('当前下钻: 文档总数')).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Boundary D dashboard evidence row' })).toBeVisible()

  await page.getByTestId('dashboard-generate-report-draft').click()
  await expect(page.getByText('报告草稿已生成: 5702')).toBeVisible()
  expect(captured.reportPayloads).toHaveLength(1)
  expect(captured.reportPayloads[0]).toMatchObject({
    request_type: 'report_from_dashboard_filter',
    project_key: 'dashboard_e2e',
  })
  expect(captured.reportPayloads[0].dashboard).toMatchObject({
    selected_label: '文档总数',
    selected_source_ref: 'dashboard-documents-source',
    sample_row_count: 1,
    reset_telemetry_boundary_context: {
      scope: 'ui_read_only_evidence_context',
      not_report_proof: true,
      not_scheduled_run_evidence_proof: true,
      scheduled_evidence_write: 'none',
      scheduled_completion_proof: 'unchanged',
    },
  })
  expect(captured.reportPayloads[0].report_options).toMatchObject({
    include_reset_telemetry_boundary_context: true,
  })

  await page.getByTestId('dashboard-open-quality-report-detail').click()
  await expect(page.getByText('当前报告详情 trace: trace-dashboard-57')).toBeVisible()
  await expect(page.getByTestId('dashboard-report-detail-source-refs')).toContainText('dashboard-documents-source')
  await expect(page.getByTestId('dashboard-report-detail-artifact')).toContainText('"artifact_id": "artifact-dashboard-57"')
  await expect(page.getByTestId('dashboard-report-detail-quality-gate')).toContainText('"decision": "pass"')
  await expect(page.getByTestId('dashboard-report-detail-export-events-summary')).toContainText('"export_format": "pdf"')
  await expect(page.getByTestId('dashboard-report-detail-export-events-summary')).toContainText('"export_outcome": "success"')

  await page.getByRole('button', { name: '复制详情修复上下文' }).click()
  await expect(page.getByText('报告详情修复上下文已复制')).toBeVisible()
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(JSON.parse(clipboard)).toMatchObject({
    trace_id: 'trace-dashboard-57',
    project_key: 'dashboard_e2e',
    action: 'replay_export_with_trusted_token',
  })

  const markdownDownload = page.waitForEvent('download')
  await page.getByTestId('dashboard-export-markdown').click()
  await expect((await markdownDownload).suggestedFilename()).toBe('boundary-d-dashboard-report.md')
  await expect(page.getByText('Markdown 已导出: boundary-d-dashboard-report.md')).toBeVisible()

  const pdfDownload = page.waitForEvent('download')
  await page.getByTestId('dashboard-export-pdf').click()
  await expect((await pdfDownload).suggestedFilename()).toBe('boundary-d-dashboard-report.pdf')
  await expect(page.getByText('文件已导出: boundary-d-dashboard-report.pdf')).toBeVisible()

  const docxDownload = page.waitForEvent('download')
  await page.getByTestId('dashboard-export-docx').click()
  await expect((await docxDownload).suggestedFilename()).toBe('boundary-d-dashboard-report.docx')
  await expect(page.getByText('文件已导出: boundary-d-dashboard-report.docx')).toBeVisible()
  expect(captured.fileExportPayloads).toHaveLength(2)
  expect(captured.fileExportPayloads.map((item) => item.format)).toEqual(['pdf', 'docx'])
  captured.fileExportPayloads.forEach(({ payload }) => {
    expect(payload).toMatchObject({
      artifact_token: 'trusted-token-dashboard-57',
      artifact_sha256: 'sha256-dashboard-57',
      project_key: 'dashboard_e2e',
      quality_gate_mode: 'strict',
      reset_telemetry_boundary_context: {
        scope: 'ui_read_only_evidence_context',
        not_report_proof: true,
        not_scheduled_run_evidence_proof: true,
        scheduled_evidence_write: 'none',
        scheduled_completion_proof: 'unchanged',
      },
    })
  })
  await page.getByTestId('dashboard-open-export-report-detail').click()
  await expect(page.getByText('当前报告详情 trace: trace-dashboard-57')).toBeVisible()

  expect(captured.apiCalls).toEqual(expect.arrayContaining([
    expect.objectContaining({ method: 'GET', pathname: '/api/v1/dashboard/stats' }),
    expect.objectContaining({ method: 'GET', pathname: '/api/v1/dashboard/drilldown' }),
    expect.objectContaining({ method: 'GET', pathname: '/api/v1/dashboard/llm-report-detail' }),
    expect.objectContaining({ method: 'GET', pathname: '/api/v1/search/runs/retrieval_run_dashboard_57' }),
  ]))
})
