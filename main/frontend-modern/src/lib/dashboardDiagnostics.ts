import { httpGet } from './api/client'
import type {
  DashboardDrilldownResponse,
  DashboardLlmReportDetailResponse,
  DashboardLlmReportQualityRecord,
  DashboardReportFromFilterResponse,
} from './types'

export type DashboardDrilldownSelection = {
  metric?: string
  sourceRef?: string
  label: string
  filters?: Record<string, unknown>
  pendingActionId?: string
}

export type DashboardLlmReportDetailSelection = {
  traceId: string
  projectKey?: string | null
}

const DASHBOARD_DRILLDOWN_LIMIT = 10
const PROCESS_HISTORY_SOURCE = 'llm_report_quality'
const QUALITY_REPAIR_CONTEXT_CONTRACT = 'dashboard.llm_report_quality.repair_context.v1'
const QUALITY_REPAIR_CONTEXT_SOURCE = 'dashboard.llm_report_quality'
const REPORT_DRAFT_DOCUMENT_ID_REQUIRED = 'report draft document id is required'
const REPORT_EXPORT_TOKEN_REQUIRED = 'llm_report_export_token_required'
const READY_GATE_STATUS = 'ready'

function asNumber(value: number | undefined) {
  return value ?? 0
}

export function stringifyJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function formatPercent(value: number | undefined, locale: string) {
  return `${(asNumber(value) * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}%`
}

export function formatCountMap(value: Record<string, number> | undefined, locale: string) {
  const entries = Object.entries(value || {})
    .filter(([, count]) => asNumber(count) > 0)
    .sort(([left], [right]) => left.localeCompare(right))
  if (!entries.length) return '-'
  return entries.map(([key, count]) => `${key}: ${asNumber(count).toLocaleString(locale)}`).join(' / ')
}

export function triggerMarkdownDownload(filename: string, markdown: string) {
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  triggerBlobDownload(filename, blob)
}

export function triggerBlobDownload(filename: string, blob: Blob) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export function dashboardQualityGateForExport(data: DashboardReportFromFilterResponse | undefined) {
  const rawGate = data?.report_quality_gate || data?.quality?.report_quality_gate || {}
  const status = String(rawGate.status || data?.quality?.status || '').trim().toLowerCase()
  const decision = status === 'pass' ? 'pass' : status === 'warn' || status === READY_GATE_STATUS ? 'warn' : 'fail'
  return {
    ...rawGate,
    decision,
    hard_failures: Array.isArray(rawGate.blocking_reasons) ? rawGate.blocking_reasons : [],
    soft_failures: Array.isArray(rawGate.warnings) ? rawGate.warnings : [],
    missing_items: Array.isArray(rawGate.missing_items) ? rawGate.missing_items : [],
  }
}

export function dashboardQualityGateModeForExport(data: DashboardReportFromFilterResponse | undefined) {
  const mode = String(data?.quality?.quality_gate_mode || '').trim().toLowerCase()
  return mode === 'strict' ? 'strict' : 'warn'
}

export function dashboardArtifactForExport(data: DashboardReportFromFilterResponse | undefined) {
  return data?.export_artifact || data?.artifact || null
}

export function dashboardReportDocumentId(data: DashboardReportFromFilterResponse | undefined) {
  const docId = data?.document_id || data?.draft_id
  if (!docId) throw new Error(REPORT_DRAFT_DOCUMENT_ID_REQUIRED)
  return docId
}

export function dashboardReportExportArtifact(data: DashboardReportFromFilterResponse | undefined) {
  const artifact = dashboardArtifactForExport(data)
  if (!artifact?.artifact_token) throw new Error(REPORT_EXPORT_TOKEN_REQUIRED)
  return artifact
}

export function isDashboardReportExportTokenError(error: unknown) {
  return error instanceof Error && error.message === REPORT_EXPORT_TOKEN_REQUIRED
}

export function buildProcessHistoryHash(record: DashboardLlmReportQualityRecord) {
  const params = new URLSearchParams()
  const jobId = record.job_id == null ? '' : String(record.job_id)
  const traceId = record.trace_id || ''
  if (jobId) {
    params.set('history_id', jobId)
    params.set('job_id', jobId)
  }
  if (traceId) params.set('trace_id', traceId)
  if (record.project_key) params.set('project_key', record.project_key)
  params.set('source', PROCESS_HISTORY_SOURCE)
  const query = params.toString()
  return `#/admin/process${query ? `?${query}` : ''}`
}

export function dashboardReportDetailTraceId(record: DashboardLlmReportQualityRecord) {
  return record.source_trace_id || record.trace_id || ''
}

export function dashboardReportDetailProjectKey(record: DashboardLlmReportQualityRecord, fallbackProjectKey: string) {
  return record.project_key || fallbackProjectKey || null
}

export function dashboardReportArtifact(detail: DashboardLlmReportDetailResponse | undefined) {
  return detail?.report_artifact || detail?.artifact || null
}

export function dashboardReportQualityGate(detail: DashboardLlmReportDetailResponse | undefined) {
  return detail?.quality_gate || detail?.report_quality_gate || null
}

export function dashboardReportExportEventsSummary(detail: DashboardLlmReportDetailResponse | undefined) {
  const events = detail?.export_events || []
  const apiSummary = detail?.export_events_summary || detail?.export_audit?.summary || null
  const recent = events.slice(0, 5).map((event) => ({
    export_format: event.export_format ?? event.format ?? null,
    export_outcome: event.export_outcome ?? event.outcome ?? null,
    artifact_id: event.artifact_id ?? null,
    recorded_at: event.recorded_at ?? event.created_at ?? null,
    error_code: event.error_code ?? null,
    ui_read_only_context_included: event.ui_read_only_context_included ?? null,
    ui_read_only_context_scope: event.ui_read_only_context_scope ?? null,
  }))
  if (apiSummary && typeof apiSummary === 'object') {
    return {
      ...apiSummary,
      recent: Array.isArray(apiSummary.recent) ? apiSummary.recent : recent,
    }
  }
  return {
    total: events.length,
    ui_read_only_context_included_count: events.filter(
      (event) => event.ui_read_only_context_included === true,
    ).length,
    recent,
  }
}

export function requireDashboardDrilldownSelection(
  selection: DashboardDrilldownSelection | null,
): DashboardDrilldownSelection {
  if (!selection) throw new Error('Dashboard drilldown selection is required')
  return selection
}

export function requireDashboardReportDetailSelection(
  selection: DashboardLlmReportDetailSelection | null,
): DashboardLlmReportDetailSelection {
  if (!selection?.traceId) throw new Error('Dashboard LLM report trace_id is required')
  return selection
}

export async function fetchDashboardDrilldown(selection: DashboardDrilldownSelection) {
  const params = new URLSearchParams()
  params.set('limit', String(DASHBOARD_DRILLDOWN_LIMIT))
  if (selection.sourceRef) {
    params.set('source_ref', selection.sourceRef)
  } else if (selection.metric) {
    params.set('metric', selection.metric)
  }
  return httpGet<DashboardDrilldownResponse>(`/api/v1/dashboard/drilldown?${params.toString()}`)
}

export function buildQualityRepairContext(record: DashboardLlmReportQualityRecord, projectKey: string) {
  return {
    contract_version: QUALITY_REPAIR_CONTEXT_CONTRACT,
    source: QUALITY_REPAIR_CONTEXT_SOURCE,
    trace_id: record.trace_id || null,
    request_id: record.request_id || null,
    job_id: record.job_id || null,
    project_key: record.project_key || projectKey,
    decision: record.decision || null,
    readiness: record.readiness || null,
    job_status: record.job_status || null,
    next_action: record.next_action || null,
    coverage: {
      citation: record.citation_coverage ?? null,
      evidence: record.evidence_coverage ?? null,
    },
    failure_counts: {
      missing_items: record.missing_items_count ?? null,
      hard_failures: record.hard_failure_count ?? null,
      soft_failures: record.soft_failure_count ?? null,
    },
    process_detail_hash: buildProcessHistoryHash(record),
  }
}
