import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { translate, useAppLocale } from '../app/platform/i18n'
import {
  createDashboardReportFromFilter,
  exportLlmReportFile,
  exportWritingMarkdown,
  getBusinessLineEvidenceMatrix,
  getDashboardLlmReportDetail,
  getDashboardStats,
  type LlmReportExportFormat,
  type LlmReportFileExportPayload,
} from '../lib/api'
import {
  buildProcessHistoryHash,
  buildQualityRepairContext,
  dashboardQualityGateForExport,
  dashboardQualityGateModeForExport,
  dashboardReportArtifact,
  dashboardReportDetailProjectKey,
  dashboardReportDetailTraceId,
  dashboardReportDocumentId,
  dashboardReportExportArtifact,
  dashboardReportExportEventsSummary,
  dashboardReportQualityGate,
  fetchDashboardDrilldown,
  formatCountMap,
  formatPercent,
  isDashboardReportExportTokenError,
  requireDashboardDrilldownSelection,
  requireDashboardReportDetailSelection,
  stringifyJson,
  triggerBlobDownload,
  triggerMarkdownDownload,
  type DashboardDrilldownSelection,
  type DashboardLlmReportDetailSelection,
} from '../lib/dashboardDiagnostics'
import { queryKeys } from '../lib/queryKeys'
import type {
  BusinessLineEvidenceMatrix,
  DashboardLlmReportQualityRecord,
  DashboardPendingAction,
  DashboardReportFromFilterPayload,
  DashboardStatsSourceRef,
} from '../lib/types'
import { DashboardSearchRetrievalRunPanel } from './dashboard/DashboardSearchRetrievalRunPanel'

type DashboardPageProps = {
  projectKey: string
  variant?: 'dashboard' | 'market' | 'social' | 'analysis' | 'board'
}

type FrontdoorTriStateStatus = 'success' | 'degraded_success' | 'failed'

const EMPTY_SAMPLE_ROWS: Array<Record<string, unknown>> = []

function asNumber(value: number | undefined) {
  return value ?? 0
}

function formatNumber(value: number | undefined, locale: string) {
  return asNumber(value).toLocaleString(locale)
}

function formatDashboardTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function frontdoorTriStateChipClass(status: FrontdoorTriStateStatus) {
  if (status === 'success') return 'chip chip-ok'
  if (status === 'failed') return 'chip chip-danger'
  return 'chip chip-warn'
}

function severityChipClass(severity: string | undefined) {
  if (severity === 'high') return 'chip chip-danger'
  if (severity === 'medium') return 'chip chip-warn'
  return 'chip'
}

function formatUnknownValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return stringifyJson(value)
  return String(value)
}

function sourceRefId(ref: DashboardStatsSourceRef | string | undefined) {
  if (!ref) return ''
  if (typeof ref === 'string') return ref
  return ref.id || ref.detail || ''
}

function sourceRefLabel(ref: DashboardStatsSourceRef | string | undefined) {
  if (!ref) return '-'
  if (typeof ref === 'string') return ref
  return ref.id || ref.table || ref.detail || '-'
}

function sampleRowColumns(rows: Array<Record<string, unknown>>) {
  const columns: string[] = []
  rows.slice(0, 5).forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!columns.includes(key)) columns.push(key)
    })
  })
  return columns.slice(0, 8)
}

function asRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function textValue(value: unknown) {
  return typeof value === 'string' && value ? value : ''
}

function dashboardResetTelemetryBoundaryLines(matrix: BusinessLineEvidenceMatrix | undefined) {
  const batchOrchestration = asRecord(matrix?.batch_orchestration)
  const asyncTaskReadback = asRecord(batchOrchestration?.async_task_readback_extension)
  const metadata = asRecord(asyncTaskReadback?.scheduled_artifact_warning_empty_reset_telemetry_ui_extension)
  const uiEventContract = asRecord(metadata?.ui_event_contract)
  const apiContract = asRecord(metadata?.api_contract)

  const eventName = textValue(uiEventContract?.event_name)
  const eventScope = textValue(uiEventContract?.event_scope)
  const scheduledEvidenceWrite = textValue(uiEventContract?.scheduled_evidence_write)
  const scheduledCompletionProofChanged = apiContract?.scheduled_completion_proof_changed
  const scheduledEvidenceController = textValue(apiContract?.scheduled_evidence_controller)

  if (
    eventName !== 'reset_empty_warning_view'
    || eventScope !== 'ui_event_log_only'
    || scheduledEvidenceWrite !== 'none'
    || scheduledCompletionProofChanged !== false
    || scheduledEvidenceController !== 'scheduled_run_evidence'
  ) {
    return [
      'reset telemetry metadata unavailable',
      'fallback boundary: not scheduled_run_evidence proof',
      'fallback boundary: scheduled_evidence_write=none',
      'fallback boundary: scheduled_completion_proof unchanged',
    ]
  }

  return [
    eventName,
    eventScope,
    `scheduled_evidence_write=${scheduledEvidenceWrite}`,
    'scheduled_completion_proof unchanged',
    'not scheduled_run_evidence proof',
  ]
}

type ResetTelemetryBoundaryContext = {
  scope: 'ui_read_only_evidence_context'
  source: 'business_lines.evidence_matrix.async_task_readback_extension'
  lines: string[]
  not_report_proof: true
  not_scheduled_run_evidence_proof: true
  scheduled_evidence_write: 'none'
  scheduled_completion_proof: 'unchanged'
}

type DashboardReportDashboardPayload = DashboardReportFromFilterPayload['dashboard'] & {
  reset_telemetry_boundary_context: ResetTelemetryBoundaryContext
}

type DashboardLlmReportFileExportPayload = LlmReportFileExportPayload & {
  reset_telemetry_boundary_context: ResetTelemetryBoundaryContext
}

type DashboardLlmReportExportAuditRecord = DashboardLlmReportQualityRecord & {
  ui_read_only_context_included?: boolean | null
  ui_read_only_context_scope?: string | null
}

type DashboardLlmReportExportEventsSummary = {
  total?: number
  success?: number
  blocked?: number
  token_invalid?: number
  failed?: number
  legacy?: number
  trusted?: number
  ui_read_only_context_included_count?: number
  by_format?: Record<string, number>
  by_integrity_mode?: Record<string, number>
}

function formatExportAuditReadOnlyContext(record: DashboardLlmReportExportAuditRecord) {
  const included = record.ui_read_only_context_included
  const includedText = included == null ? '-' : String(included)
  const scope = record.ui_read_only_context_scope || '-'
  return `ui_read_only_context_included=${includedText} / scope=${scope}`
}

export default function DashboardPage({ projectKey, variant = 'dashboard' }: DashboardPageProps) {
  const locale = useAppLocale()
  const queryClient = useQueryClient()
  const [drilldownSelection, setDrilldownSelection] = useState<DashboardDrilldownSelection | null>(null)
  const [copyMessage, setCopyMessage] = useState('')
  const [reportMessage, setReportMessage] = useState('')
  const [exportMessage, setExportMessage] = useState('')
  const [qualityActionMessage, setQualityActionMessage] = useState('')
  const [reportDetailMessage, setReportDetailMessage] = useState('')
  const [reportDetailSelection, setReportDetailSelection] = useState<DashboardLlmReportDetailSelection | null>(null)
  const dashboardStats = useQuery({
    queryKey: queryKeys.dashboard.stats(projectKey),
    queryFn: getDashboardStats,
    enabled: Boolean(projectKey),
  })
  const businessLineEvidenceMatrix = useQuery({
    queryKey: ['dashboard-business-line-evidence-matrix', projectKey],
    queryFn: getBusinessLineEvidenceMatrix,
    enabled: Boolean(projectKey),
  })
  const dashboardDrilldown = useQuery({
    queryKey: [
      'dashboard-drilldown',
      projectKey,
      drilldownSelection?.metric || '',
      drilldownSelection?.sourceRef || '',
    ],
    queryFn: () => {
      return fetchDashboardDrilldown(requireDashboardDrilldownSelection(drilldownSelection))
    },
    enabled: Boolean(projectKey && drilldownSelection),
  })
  const llmReportDetail = useQuery({
    queryKey: [
      'dashboard-llm-report-detail',
      projectKey,
      reportDetailSelection?.traceId || '',
      reportDetailSelection?.projectKey || '',
    ],
    queryFn: () => {
      const selection = requireDashboardReportDetailSelection(reportDetailSelection)
      return getDashboardLlmReportDetail({
        traceId: selection.traceId,
        projectKey: selection.projectKey || projectKey,
      })
    },
    enabled: Boolean(projectKey && reportDetailSelection?.traceId),
  })
  const docTypeRows = Object.entries(dashboardStats.data?.documents?.type_distribution || {})
  const pendingActions = dashboardStats.data?.pending_actions || []
  type DashboardMessageKey = Parameters<typeof translate>[1]
  const t = (key: DashboardMessageKey, fallback?: string) => translate(locale, key, fallback)
  const triStateLabelKeys: Record<FrontdoorTriStateStatus, DashboardMessageKey> = {
    success: 'dashboardPage.triState.success',
    degraded_success: 'dashboardPage.triState.degraded_success',
    failed: 'dashboardPage.triState.failed',
  }
  const formattedNumber = (value: number | undefined) => formatNumber(value, locale)
  const formatTemplate = (key: DashboardMessageKey, values: Record<string, string | number>) =>
    formatDashboardTemplate(t(key), values)
  const triStateRows: FrontdoorTriStateStatus[] = dashboardStats.data?.tasks?.frontdoor_tri_state?.states?.length
    ? dashboardStats.data.tasks.frontdoor_tri_state.states
    : ['success', 'degraded_success', 'failed']
  const triStateCounts = dashboardStats.data?.tasks?.frontdoor_tri_state?.counts || {}
  const variantTitle: Record<NonNullable<DashboardPageProps['variant']>, string> = {
    dashboard: t('dashboardPage.title.dashboard'),
    market: t('dashboardPage.title.market'),
    social: t('dashboardPage.title.social'),
    analysis: t('dashboardPage.title.analysis'),
    board: t('dashboardPage.title.board'),
  }
  const variantHint: Record<NonNullable<DashboardPageProps['variant']>, string> = {
    dashboard: t('dashboardPage.hint.dashboard'),
    market: t('dashboardPage.hint.market'),
    social: t('dashboardPage.hint.social'),
    analysis: t('dashboardPage.hint.analysis'),
    board: t('dashboardPage.hint.board'),
  }
  const metricDrilldowns = [
    {
      key: 'documents.total',
      label: t('dashboardPage.kpi.documents'),
      refs: dashboardStats.data?.documents?.source_refs || [],
    },
    {
      key: 'sources.total',
      label: t('dashboardPage.kpi.sources'),
      refs: dashboardStats.data?.sources?.source_refs || [],
    },
    {
      key: 'market_stats.total',
      label: t('dashboardPage.kpi.marketStats'),
      refs: dashboardStats.data?.market_stats?.source_refs || [],
    },
    {
      key: 'tasks.total',
      label: t('dashboardPage.kpi.runningTasks'),
      refs: dashboardStats.data?.tasks?.source_refs || [],
    },
    {
      key: 'tasks.frontdoor_tri_state',
      label: t('dashboardPage.section.frontdoorTriState'),
      refs: dashboardStats.data?.tasks?.frontdoor_tri_state?.source_refs || [],
    },
  ]
  const sampleRows = dashboardDrilldown.data?.sample_rows || EMPTY_SAMPLE_ROWS
  const sampleColumns = useMemo(() => sampleRowColumns(sampleRows), [sampleRows])
  const resetTelemetryBoundaryLines = useMemo(
    () => dashboardResetTelemetryBoundaryLines(businessLineEvidenceMatrix.data),
    [businessLineEvidenceMatrix.data],
  )
  const resetTelemetryBoundaryContext = useMemo<ResetTelemetryBoundaryContext>(() => ({
    scope: 'ui_read_only_evidence_context',
    source: 'business_lines.evidence_matrix.async_task_readback_extension',
    lines: resetTelemetryBoundaryLines,
    not_report_proof: true,
    not_scheduled_run_evidence_proof: true,
    scheduled_evidence_write: 'none',
    scheduled_completion_proof: 'unchanged',
  }), [resetTelemetryBoundaryLines])
  const reportPayload = useMemo<DashboardReportFromFilterPayload>(() => {
    const drilldownFilters = dashboardDrilldown.data?.filters || {}
    const actionFilters = drilldownSelection?.filters || {}
    const sourceRefs = dashboardDrilldown.data?.source_refs?.length
      ? dashboardDrilldown.data.source_refs
      : drilldownSelection?.sourceRef
        ? [{ id: drilldownSelection.sourceRef }]
        : []
    const dashboardPayload: DashboardReportDashboardPayload = {
      variant,
      selected_label: drilldownSelection?.label || null,
      selected_metric: dashboardDrilldown.data?.metric || drilldownSelection?.metric || null,
      selected_source_ref: dashboardDrilldown.data?.source_ref || drilldownSelection?.sourceRef || null,
      pending_action_id: drilldownSelection?.pendingActionId || null,
      filters: {
        ...actionFilters,
        ...drilldownFilters,
      },
      action_filters: actionFilters,
      drilldown_filters: drilldownFilters,
      source_query: dashboardDrilldown.data?.source_query || null,
      source_refs: sourceRefs,
      sample_rows: sampleRows,
      sample_row_count: dashboardDrilldown.data?.row_count || 0,
      reset_telemetry_boundary_context: resetTelemetryBoundaryContext,
    }
    return {
      request_type: 'report_from_dashboard_filter',
      project_key: projectKey,
      dashboard: dashboardPayload,
      report_options: {
        include_dashboard_sample_rows: true,
        include_reset_telemetry_boundary_context: true,
        preserve_source_refs: true,
      },
    }
  }, [dashboardDrilldown.data, drilldownSelection, projectKey, resetTelemetryBoundaryContext, sampleRows, variant])
  const reportPayloadText = stringifyJson(reportPayload)
  const reportSourceRefs = reportPayload.dashboard.source_refs || []
  const llmReportQuality = dashboardStats.data?.llm_report_quality
  const llmReportQualitySummary = llmReportQuality?.summary || {}
  const llmReportQualityDecisions = llmReportQualitySummary.by_decision || llmReportQualitySummary.decisions || {}
  const llmReportQualityReadiness = llmReportQualitySummary.readiness || {}
  const llmReportExportEvents = (llmReportQualitySummary.export_events || {}) as DashboardLlmReportExportEventsSummary
  const llmReportQualityRecords = llmReportQuality?.recent_records || []
  const llmReportExportRecords = (llmReportQuality?.recent_export_events || []) as DashboardLlmReportExportAuditRecord[]
  const reportFromFilter = useMutation({
    mutationFn: () => createDashboardReportFromFilter(reportPayload),
    onSuccess: (data) => {
      setExportMessage('')
      setReportMessage(formatTemplate('dashboardPage.message.reportCreated', {
        id: data.draft_id || data.document_id || data.report_id || '-',
      }))
    },
    onError: () => {
      setReportMessage(t('dashboardPage.error.reportCreateFailed'))
    },
  })
  const exportReportDraft = useMutation({
    mutationFn: async () => {
      const docId = dashboardReportDocumentId(reportFromFilter.data)
      return exportWritingMarkdown(docId, projectKey)
    },
    onSuccess: (data) => {
      triggerMarkdownDownload(data.filename, data.markdown)
      setExportMessage(formatTemplate('dashboardPage.message.markdownExported', { filename: data.filename }))
    },
    onError: () => {
      setExportMessage(t('dashboardPage.error.markdownExportFailed'))
    },
  })
  const exportReportFile = useMutation({
    mutationFn: async (format: LlmReportExportFormat) => {
      const docId = dashboardReportDocumentId(reportFromFilter.data)
      const artifact = dashboardReportExportArtifact(reportFromFilter.data)
      const exported = await exportWritingMarkdown(docId, projectKey)
      const exportPayload: DashboardLlmReportFileExportPayload = {
        markdown: exported.markdown,
        quality_gate: dashboardQualityGateForExport(reportFromFilter.data),
        quality_gate_mode: dashboardQualityGateModeForExport(reportFromFilter.data),
        filename: exported.filename,
        project_key: projectKey,
        artifact_token: artifact.artifact_token,
        artifact_sha256: artifact.artifact_sha256 || null,
        reset_telemetry_boundary_context: resetTelemetryBoundaryContext,
      }
      return exportLlmReportFile(format, exportPayload)
    },
    onSuccess: (data) => {
      triggerBlobDownload(data.filename, data.blob)
      setExportMessage(formatTemplate('dashboardPage.message.fileExported', { filename: data.filename }))
    },
    onError: (error) => {
      setExportMessage(
        isDashboardReportExportTokenError(error)
          ? t('dashboardPage.error.fileExportTokenRequired')
          : t('dashboardPage.error.fileExportFailed'),
      )
    },
  })

  const selectDrilldown = (selection: DashboardDrilldownSelection) => {
    setCopyMessage('')
    setReportMessage('')
    setExportMessage('')
    setQualityActionMessage('')
    reportFromFilter.reset()
    exportReportDraft.reset()
    exportReportFile.reset()
    setDrilldownSelection(selection)
  }
  const openQualityRecordTask = (record: DashboardLlmReportQualityRecord) => {
    window.location.assign(buildProcessHistoryHash(record))
  }
  const openLlmReportDetail = (record: DashboardLlmReportQualityRecord) => {
    const traceId = dashboardReportDetailTraceId(record)
    if (!traceId) return
    setReportDetailMessage('')
    setReportDetailSelection({
      traceId,
      projectKey: dashboardReportDetailProjectKey(record, projectKey),
    })
  }
  const copyQualityRepairContext = async (record: DashboardLlmReportQualityRecord) => {
    const context = buildQualityRepairContext(record, projectKey)
    try {
      await navigator.clipboard.writeText(stringifyJson(context))
      setQualityActionMessage(t('dashboardPage.message.qualityRepairContextCopied'))
    } catch {
      setQualityActionMessage(t('dashboardPage.message.qualityRepairContextCopyFailed'))
    }
  }
  const copyReportDetailRepairContext = async () => {
    if (!llmReportDetail.data?.repair_context) return
    try {
      await navigator.clipboard.writeText(stringifyJson(llmReportDetail.data.repair_context))
      setReportDetailMessage(t('dashboardPage.message.reportDetailRepairContextCopied'))
    } catch {
      setReportDetailMessage(t('dashboardPage.message.reportDetailRepairContextCopyFailed'))
    }
  }
  const copyReportPayload = async () => {
    try {
      await navigator.clipboard.writeText(reportPayloadText)
      setCopyMessage(t('dashboardPage.message.copyDone'))
    } catch {
      setCopyMessage(t('dashboardPage.message.copyFailed'))
    }
  }
  const createReportDraft = () => {
    if (!drilldownSelection) {
      setReportMessage(t('dashboardPage.empty.drilldown'))
      return
    }
    if (!reportSourceRefs.length) {
      setReportMessage(t('dashboardPage.error.reportSourceRefsRequired'))
      return
    }
    setReportMessage('')
    setExportMessage('')
    reportFromFilter.mutate()
  }
  const renderSourceRefButtons = (refs: Array<DashboardStatsSourceRef | string> | undefined, label: string) => {
    const validRefs = (refs || []).map((ref) => ({ ref, id: sourceRefId(ref) })).filter((item) => item.id)
    if (!validRefs.length) return <span className="status-line">{t('dashboardPage.empty.sourceRefs')}</span>
    return validRefs.map(({ ref, id }) => (
      <button
        key={id}
        type="button"
        data-testid={`dashboard-source-ref-${id}`}
        onClick={() => selectDrilldown({ sourceRef: id, label })}
      >
        {sourceRefLabel(ref)}
      </button>
    ))
  }
  const renderPendingActionSourceRefs = (action: DashboardPendingAction) => {
    const refs = action.source_refs || []
    if (!refs.length) return '-'
    return (
      <div className="inline-actions">
        {refs.map((ref) => (
          <button
            key={ref}
            type="button"
            onClick={() => selectDrilldown({
              sourceRef: ref,
              label: action.title || action.type || ref,
              filters: action.filters,
              pendingActionId: action.id,
            })}
          >
            {ref}
          </button>
        ))}
      </div>
    )
  }

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <h2>{variantTitle[variant]}</h2>
        </div>
        <p className="status-line">{variantHint[variant]}</p>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card">
          <span>{t('dashboardPage.kpi.documents')}</span>
          <strong>{formattedNumber(dashboardStats.data?.documents?.total)}</strong>
          <small>{formatTemplate('dashboardPage.kpi.documentsRecent', { count: formattedNumber(dashboardStats.data?.documents?.recent_7d) })}</small>
        </article>
        <article className="kpi-card">
          <span>{t('dashboardPage.kpi.sources')}</span>
          <strong>{formattedNumber(dashboardStats.data?.sources?.enabled)}</strong>
          <small>{formatTemplate('dashboardPage.kpi.sourcesTotal', { count: formattedNumber(dashboardStats.data?.sources?.total) })}</small>
        </article>
        <article className="kpi-card">
          <span>{t('dashboardPage.kpi.marketStats')}</span>
          <strong>{formattedNumber(dashboardStats.data?.market_stats?.total)}</strong>
          <small>{formatTemplate('dashboardPage.kpi.marketStates', { count: formattedNumber(dashboardStats.data?.market_stats?.states_count) })}</small>
        </article>
        <article className="kpi-card">
          <span>{t('dashboardPage.kpi.runningTasks')}</span>
          <strong>{formattedNumber(dashboardStats.data?.tasks?.running)}</strong>
          <small>{formatTemplate('dashboardPage.kpi.tasksFailed', { count: formattedNumber(dashboardStats.data?.tasks?.failed) })}</small>
        </article>
      </section>

      <section className="panel">
        <div className="inline-actions">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.stats(projectKey) })}
            disabled={dashboardStats.isFetching}
          >
            {dashboardStats.isFetching ? t('dashboardPage.action.refreshing') : t('dashboardPage.action.refresh')}
          </button>
        </div>

        <p className="status-line">{formatTemplate('dashboardPage.metric.documentsToday', { count: formattedNumber(dashboardStats.data?.documents?.recent_today) })}</p>
        <p className="status-line">{formatTemplate('dashboardPage.metric.tasksTotal', { count: formattedNumber(dashboardStats.data?.tasks?.total) })}</p>
        <p className="status-line">{formatTemplate('dashboardPage.metric.tasksCompleted', { count: formattedNumber(dashboardStats.data?.tasks?.completed) })}</p>
        <p className="status-line">{formatTemplate('dashboardPage.metric.extractionRate', { value: asNumber(dashboardStats.data?.documents?.extraction_rate) })}</p>
        <p className="status-line">{t('dashboardPage.section.frontdoorTriState')}</p>
        <div className="inline-actions">
          {triStateRows.map((status) => (
            <span key={status} className={frontdoorTriStateChipClass(status)}>
              {t(triStateLabelKeys[status])}: {formattedNumber(triStateCounts[status])}
            </span>
          ))}
        </div>
        {dashboardStats.isError ? <p className="status-line">{t('dashboardPage.error.loadFailed')}</p> : null}
      </section>

      <section className="kpi-grid">
        <article
          className="kpi-card"
          data-testid="dashboard-scheduled-artifact-reset-telemetry-boundary"
        >
          <span>{t('dashboardPage.section.scheduledArtifactResetTelemetryBoundary')}</span>
          <ul className="compact-list">
            {resetTelemetryBoundaryLines.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>{t('dashboardPage.section.llmReportQuality')}</h3>
        </div>
        <div className="inline-actions">
          {renderSourceRefButtons(llmReportQuality?.source_refs, t('dashboardPage.section.llmReportQuality'))}
          {qualityActionMessage ? <span className="status-line">{qualityActionMessage}</span> : null}
        </div>
        <section className="kpi-grid">
          <article className="kpi-card">
            <span>{t('dashboardPage.kpi.llmReportQualityTotal')}</span>
            <strong>{formattedNumber(llmReportQualitySummary.total)}</strong>
            <small>
              {formatTemplate('dashboardPage.kpi.llmReportQualityBlocked', {
                count: formattedNumber(llmReportQualityDecisions.fail),
              })}
            </small>
          </article>
          <article className="kpi-card">
            <span>{t('dashboardPage.kpi.llmReportQualityAvgCitation')}</span>
            <strong>{formatPercent(llmReportQualitySummary.avg_citation_coverage, locale)}</strong>
            <small>
              {formatTemplate('dashboardPage.kpi.llmReportQualityReviewRequired', {
                count: formattedNumber(llmReportQualityReadiness.review_required),
              })}
            </small>
          </article>
          <article className="kpi-card">
            <span>{t('dashboardPage.kpi.llmReportQualityAvgEvidence')}</span>
            <strong>{formatPercent(llmReportQualitySummary.avg_evidence_coverage, locale)}</strong>
            <small>{llmReportQuality?.actionability?.next_action || t('dashboardPage.empty.llmReportQualityNoData')}</small>
          </article>
          <article className="kpi-card">
            <span>{t('dashboardPage.kpi.llmReportExportEventsTotal')}</span>
            <strong>{formattedNumber(llmReportExportEvents.total)}</strong>
            <small>
              {formatTemplate('dashboardPage.kpi.llmReportExportEventsTrusted', {
                count: formattedNumber(llmReportExportEvents.trusted),
              })}
            </small>
            <small data-testid="dashboard-export-events-read-only-context-included">
              {formatTemplate('dashboardPage.kpi.llmReportExportEventsReadOnlyContextIncluded', {
                count: formattedNumber(llmReportExportEvents.ui_read_only_context_included_count),
              })}
            </small>
          </article>
          <article className="kpi-card">
            <span>{t('dashboardPage.kpi.llmReportExportEventsLegacy')}</span>
            <strong>{formattedNumber(llmReportExportEvents.legacy)}</strong>
            <small>
              {formatTemplate('dashboardPage.kpi.llmReportExportEventsTokenInvalid', {
                count: formattedNumber(llmReportExportEvents.token_invalid),
              })}
            </small>
          </article>
          <article className="kpi-card">
            <span>{t('dashboardPage.kpi.llmReportExportEventsBlocked')}</span>
            <strong>{formattedNumber(llmReportExportEvents.blocked)}</strong>
            <small>
              {formatTemplate('dashboardPage.metric.llmReportExportFormatBreakdown', {
                formats: formatCountMap(llmReportExportEvents.by_format, locale),
              })}
            </small>
          </article>
        </section>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('dashboardPage.field.decision')}</th>
                <th>{t('dashboardPage.field.traceId')}</th>
                <th>{t('dashboardPage.field.jobId')}</th>
                <th>{t('dashboardPage.field.readiness')}</th>
                <th>{t('dashboardPage.field.coverage')}</th>
                <th>{t('dashboardPage.field.jobStatus')}</th>
                <th>{t('dashboardPage.field.recordedAt')}</th>
                <th>{t('dashboardPage.field.nextAction')}</th>
                <th>{t('dashboardPage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {llmReportQualityRecords.map((record, index) => (
                <tr key={record.trace_id || record.job_id || index}>
                  <td>{record.decision || '-'}</td>
                  <td>{record.trace_id || '-'}</td>
                  <td>{record.job_id || '-'}</td>
                  <td>{record.readiness || '-'}</td>
                  <td>
                    {formatTemplate('dashboardPage.metric.llmReportQualityCoverage', {
                      citation: formatPercent(record.citation_coverage, locale),
                      evidence: formatPercent(record.evidence_coverage, locale),
                    })}
                  </td>
                  <td>{record.job_status || '-'}</td>
                  <td>{record.recorded_at || '-'}</td>
                  <td>{record.next_action || '-'}</td>
                  <td>
                    <div className="inline-actions">
                      <button
                        type="button"
                        disabled={!record.job_id && !record.trace_id}
                        onClick={() => openQualityRecordTask(record)}
                      >
                        {t('dashboardPage.action.openJobDetail')}
                      </button>
                      <button
                        type="button"
                        data-testid="dashboard-open-quality-report-detail"
                        disabled={!dashboardReportDetailTraceId(record)}
                        onClick={() => openLlmReportDetail(record)}
                      >
                        {t('dashboardPage.action.openReportDetail')}
                      </button>
                      <button type="button" onClick={() => void copyQualityRepairContext(record)}>
                        {t('dashboardPage.action.copyQualityRepairContext')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!llmReportQualityRecords.length ? (
                <tr>
                  <td colSpan={9} className="empty-cell">
                    {t('dashboardPage.empty.llmReportQualityRecentRecords')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="panel-header">
          <h4>{t('dashboardPage.section.llmReportExportEvents')}</h4>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('dashboardPage.field.exportFormat')}</th>
                <th>{t('dashboardPage.field.exportOutcome')}</th>
                <th>{t('dashboardPage.field.exportIntegrity')}</th>
                <th>{t('dashboardPage.field.exportReadOnlyContextTrace')}</th>
                <th>{t('dashboardPage.field.artifactId')}</th>
                <th>{t('dashboardPage.field.traceId')}</th>
                <th>{t('dashboardPage.field.contentSize')}</th>
                <th>{t('dashboardPage.field.errorCode')}</th>
                <th>{t('dashboardPage.field.recordedAt')}</th>
                <th>{t('dashboardPage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {llmReportExportRecords.map((record, index) => (
                <tr key={record.trace_id || record.artifact_id || index}>
                  <td>{record.export_format || '-'}</td>
                  <td>{record.export_outcome || '-'}</td>
                  <td>
                    {formatTemplate('dashboardPage.metric.llmReportExportIntegrity', {
                      mode: record.export_integrity_mode || '-',
                      trusted: record.export_integrity_trusted ? 'true' : 'false',
                    })}
                  </td>
                  <td data-testid="dashboard-export-audit-read-only-context-trace">
                    {formatExportAuditReadOnlyContext(record)}
                  </td>
                  <td>{record.artifact_id || '-'}</td>
                  <td>{record.source_trace_id || record.trace_id || '-'}</td>
                  <td>{record.content_size_bytes == null ? '-' : formattedNumber(record.content_size_bytes)}</td>
                  <td>{record.error_code || '-'}</td>
                  <td>{record.recorded_at || '-'}</td>
                  <td>
                    <button
                      type="button"
                      data-testid="dashboard-open-export-report-detail"
                      disabled={!dashboardReportDetailTraceId(record)}
                      onClick={() => openLlmReportDetail(record)}
                    >
                      {t('dashboardPage.action.openReportDetail')}
                    </button>
                  </td>
                </tr>
              ))}
              {!llmReportExportRecords.length ? (
                <tr>
                  <td colSpan={10} className="empty-cell">
                    {t('dashboardPage.empty.llmReportExportEvents')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="panel-header">
          <h4>{t('dashboardPage.section.llmReportDetail')}</h4>
        </div>
        <p className="status-line">
          {reportDetailSelection
            ? formatTemplate('dashboardPage.status.currentReportDetail', { traceId: reportDetailSelection.traceId })
            : t('dashboardPage.empty.llmReportDetail')}
        </p>
        <div className="inline-actions">
          <button
            type="button"
            disabled={!llmReportDetail.data?.repair_context}
            onClick={() => void copyReportDetailRepairContext()}
          >
            {t('dashboardPage.action.copyReportDetailRepairContext')}
          </button>
          {llmReportDetail.isFetching ? <span className="status-line">{t('dashboardPage.status.reportDetailLoading')}</span> : null}
          {llmReportDetail.isError ? <span className="status-line">{t('dashboardPage.error.reportDetailLoadFailed')}</span> : null}
          {reportDetailMessage ? <span className="status-line">{reportDetailMessage}</span> : null}
        </div>
        {llmReportDetail.data ? (
          <div className="status-line" data-testid="dashboard-report-detail-panel">
            <article
              className="kpi-card"
              data-testid="dashboard-report-detail-reset-telemetry-boundary"
            >
              <span>{t('dashboardPage.section.reportDetailResetTelemetryBoundary')}</span>
              <ul className="compact-list">
                {resetTelemetryBoundaryLines.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
            <p>
              <strong>{t('dashboardPage.field.found')}</strong>: {llmReportDetail.data.found == null ? '-' : String(llmReportDetail.data.found)}
            </p>
            <p>
              <strong>{t('dashboardPage.field.traceId')}</strong>: {llmReportDetail.data.trace_id || reportDetailSelection?.traceId || '-'}
            </p>
            <p>{t('dashboardPage.field.sourceRefs')}</p>
            <pre data-testid="dashboard-report-detail-source-refs">
              {stringifyJson(llmReportDetail.data.source_refs || [])}
            </pre>
            <p>{t('dashboardPage.field.sourceQuery')}</p>
            <pre data-testid="dashboard-report-detail-source-query">
              {stringifyJson(llmReportDetail.data.source_query || {})}
            </pre>
            <p>{t('dashboardPage.field.reportArtifact')}</p>
            <pre data-testid="dashboard-report-detail-artifact">
              {stringifyJson(dashboardReportArtifact(llmReportDetail.data) || {})}
            </pre>
            <p>{t('dashboardPage.field.qualityGate')}</p>
            <pre data-testid="dashboard-report-detail-quality-gate">
              {stringifyJson(dashboardReportQualityGate(llmReportDetail.data) || {})}
            </pre>
            <p>{t('dashboardPage.field.repairContext')}</p>
            <pre data-testid="dashboard-report-detail-repair-context">
              {stringifyJson(llmReportDetail.data.repair_context || {})}
            </pre>
            <p>{t('dashboardPage.field.exportEvents')}</p>
            <pre data-testid="dashboard-report-detail-export-events-summary">
              {stringifyJson(dashboardReportExportEventsSummary(llmReportDetail.data))}
            </pre>
          </div>
        ) : null}
      </section>

      <DashboardSearchRetrievalRunPanel projectKey={projectKey} />

      <section className="panel">
        <div className="panel-header">
          <h3>{t('dashboardPage.section.metricDrilldown')}</h3>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('dashboardPage.field.metric')}</th>
                <th>{t('dashboardPage.field.sourceRefs')}</th>
                <th>{t('dashboardPage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {metricDrilldowns.map((item) => (
                <tr key={item.key}>
                  <td>{item.key}</td>
                  <td>
                    <div className="inline-actions">
                      {renderSourceRefButtons(item.refs, item.label)}
                    </div>
                  </td>
                  <td>
                    <button type="button" onClick={() => selectDrilldown({ metric: item.key, label: item.label })}>
                      {t('dashboardPage.action.drilldown')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>{t('dashboardPage.section.pendingActions')}</h3>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('dashboardPage.field.severity')}</th>
                <th>{t('dashboardPage.field.type')}</th>
                <th>{t('dashboardPage.field.status')}</th>
                <th>{t('dashboardPage.field.sourceMetric')}</th>
                <th>{t('dashboardPage.field.sourceRefs')}</th>
              </tr>
            </thead>
            <tbody>
              {pendingActions.map((action) => (
                <tr key={action.id || `${action.type}-${action.source_metric}`}>
                  <td><span className={severityChipClass(action.severity)}>{action.severity || '-'}</span></td>
                  <td>
                    <strong>{action.type || '-'}</strong>
                    {action.title ? <p className="status-line">{action.title}</p> : null}
                    {action.detail ? <p className="status-line">{action.detail}</p> : null}
                  </td>
                  <td>{action.status || '-'}</td>
                  <td>
                    {action.source_metric ? (
                      <button
                        type="button"
                        onClick={() => selectDrilldown({
                          metric: action.source_metric,
                          label: action.title || action.source_metric || '-',
                          filters: action.filters,
                          pendingActionId: action.id,
                        })}
                      >
                        {action.source_metric}
                      </button>
                    ) : '-'}
                  </td>
                  <td>{renderPendingActionSourceRefs(action)}</td>
                </tr>
              ))}
              {!pendingActions.length ? (
                <tr>
                  <td colSpan={5} className="empty-cell">
                    {t('dashboardPage.empty.pendingActions')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>{t('dashboardPage.section.drilldown')}</h3>
        </div>
        <p className="status-line">
          {drilldownSelection
            ? formatDashboardTemplate(t('dashboardPage.status.currentDrilldown'), { label: drilldownSelection.label })
            : t('dashboardPage.empty.drilldown')}
        </p>
        {dashboardDrilldown.isFetching ? <p className="status-line">{t('dashboardPage.status.drilldownLoading')}</p> : null}
        {dashboardDrilldown.isError ? <p className="status-line">{t('dashboardPage.error.drilldownFailed')}</p> : null}
        <p className="status-line">{t('dashboardPage.field.filters')}</p>
        <pre>{stringifyJson(dashboardDrilldown.data?.filters || drilldownSelection?.filters || {})}</pre>
        <p className="status-line">{t('dashboardPage.field.sampleRows')}</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {sampleColumns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
                {!sampleColumns.length ? <th>{t('dashboardPage.field.sampleRows')}</th> : null}
              </tr>
            </thead>
            <tbody>
              {sampleRows.map((row, index) => (
                <tr key={String(row.id || index)}>
                  {sampleColumns.map((column) => (
                    <td key={column}>{formatUnknownValue(row[column])}</td>
                  ))}
                </tr>
              ))}
              {!sampleRows.length ? (
                <tr>
                  <td colSpan={Math.max(1, sampleColumns.length)} className="empty-cell">
                    {t('dashboardPage.empty.sampleRows')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>{t('dashboardPage.section.reportFromFilter')}</h3>
        </div>
        <p className="status-line">{t('dashboardPage.hint.reportFromFilter')}</p>
        <textarea data-testid="dashboard-report-payload" readOnly rows={12} value={reportPayloadText} />
        <div className="inline-actions">
          <button
            type="button"
            data-testid="dashboard-generate-report-draft"
            disabled={!drilldownSelection || dashboardDrilldown.isFetching || reportFromFilter.isPending}
            onClick={() => createReportDraft()}
          >
            {reportFromFilter.isPending
              ? t('dashboardPage.action.generatingReportDraft')
              : t('dashboardPage.action.generateReportDraft')}
          </button>
          <button type="button" disabled={!drilldownSelection} onClick={() => void copyReportPayload()}>
            {t('dashboardPage.action.copyReportPayload')}
          </button>
          <button
            type="button"
            data-testid="dashboard-export-markdown"
            disabled={!reportFromFilter.data || exportReportDraft.isPending}
            onClick={() => exportReportDraft.mutate()}
          >
            {exportReportDraft.isPending
              ? t('dashboardPage.action.exportingMarkdown')
              : t('dashboardPage.action.exportMarkdown')}
          </button>
          <button
            type="button"
            data-testid="dashboard-export-pdf"
            disabled={!reportFromFilter.data || exportReportFile.isPending}
            onClick={() => exportReportFile.mutate('pdf')}
          >
            {exportReportFile.isPending && exportReportFile.variables === 'pdf'
              ? t('dashboardPage.action.exportingPdf')
              : t('dashboardPage.action.exportPdf')}
          </button>
          <button
            type="button"
            data-testid="dashboard-export-docx"
            disabled={!reportFromFilter.data || exportReportFile.isPending}
            onClick={() => exportReportFile.mutate('docx')}
          >
            {exportReportFile.isPending && exportReportFile.variables === 'docx'
              ? t('dashboardPage.action.exportingDocx')
              : t('dashboardPage.action.exportDocx')}
          </button>
          {copyMessage ? <span className="status-line">{copyMessage}</span> : null}
          {reportMessage ? <span className="status-line">{reportMessage}</span> : null}
          {exportMessage ? <span className="status-line">{exportMessage}</span> : null}
        </div>
        {reportFromFilter.data ? (
          <div className="status-line">
            <strong>{t('dashboardPage.field.reportDraft')}</strong>: {reportFromFilter.data.title || reportFromFilter.data.report_id}
            <ul>
              {(reportFromFilter.data.quality?.checklist || []).map((item) => (
                <li key={item.id || item.detail}>
                  {item.status || '-'} - {item.detail || item.id || '-'}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <p className="status-line">{t('dashboardPage.section.documentTypeDistribution')}</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('dashboardPage.field.type')}</th>
                <th>{t('dashboardPage.field.count')}</th>
              </tr>
            </thead>
            <tbody>
              {docTypeRows.map(([type, count]) => (
                <tr key={type}>
                  <td>{type || '-'}</td>
                  <td>{formattedNumber(count)}</td>
                </tr>
              ))}
              {!docTypeRows.length ? (
                <tr>
                  <td colSpan={2} className="empty-cell">
                    {t('dashboardPage.empty.distribution')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
