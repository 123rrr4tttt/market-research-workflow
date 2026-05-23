import { Database, RefreshCw, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { translate, useAppLocale, type AppLocale } from '../app/platform/i18n'
import { useProcessData } from '../hooks/useProcessData'
import type { ProcessHistoryResponse, ProcessTaskDetail, ProcessTaskItem, ProcessTaskList, ProcessTaskStats } from '../lib/types'

export type ProcessPageProps = {
  projectKey: string
  variant?: 'process' | 'processing'
}

type ProcessHistoryItem = NonNullable<ProcessHistoryResponse['history']>[number]
type ProcessMessageKey = Parameters<typeof translate>[1]

type ProcessSummaryLabels = {
  inserted: string
  updated: string
  skipped: string
  errors: string
  urls: string
}

type ProcessBooleanLabels = {
  yes: string
  no: string
}

const detailPreStyle = {
  marginTop: 8,
  maxHeight: 280,
  overflow: 'auto' as const,
  whiteSpace: 'pre-wrap' as const,
  overflowWrap: 'anywhere' as const,
}

export type ProcessPageViewProps = {
  variant: 'process' | 'processing'
  autoRefreshEnabled: boolean
  refreshIntervalSec: number
  processStats: ProcessTaskStats | undefined
  processList: ProcessTaskList | undefined
  processHistory: ProcessHistoryResponse | undefined
  taskDetail: ProcessTaskDetail | undefined
  taskLogsText: string | undefined
  taskLogsError: boolean
  cancelPending: boolean
  isRefreshing: boolean
  selectedTask: ProcessTaskItem | undefined
  selectedHistoryTask: ProcessHistoryItem | undefined
  selectedCurrent: boolean
  selectedTaskId: string | null
  selectedHistoryId: number | null
  selectedTaskIds: string[]
  selectedMeta: Record<string, unknown> | null
  selectedSourceKind: string
  selectedResultSummary: string
  selectedRejectionView: {
    insertedValid: number | null
    rejectedCount: number | null
    rejectionBreakdown: Record<string, number>
    topReason: string
  }
  selectedLightFilterView: {
    decision: string
    reason: string
    score: number | null
    keep: string
  }
  cancellableSelectedTaskIds: string[]
  onAutoRefreshEnabledChange: (value: boolean) => void
  onRefreshIntervalChange: (value: number) => void
  onRefreshAll: () => void
  onSelectAllCancellable: () => void
  onClearSelectedTasks: () => void
  onCancelSelectedTasks: () => void
  onToggleTaskSelect: (taskId: string) => void
  onToggleCurrentTaskDetail: (taskId: string) => void
  onToggleHistoryDetail: (historyId: number) => void
  onCancelTask: (taskId: string) => void
  onCloseDetail: () => void
  onRefreshSelectedTask: () => void
  onRefreshHistory: () => void
}

function formatDate(value: string | null | undefined, locale: AppLocale) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString(locale)
}

function formatProcessTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function getProcessSummaryLabels(locale: AppLocale): ProcessSummaryLabels {
  return {
    inserted: translate(locale, 'processPage.summary.inserted'),
    updated: translate(locale, 'processPage.summary.updated'),
    skipped: translate(locale, 'processPage.summary.skipped'),
    errors: translate(locale, 'processPage.summary.errors'),
    urls: translate(locale, 'processPage.summary.urls'),
  }
}

function getProcessBooleanLabels(locale: AppLocale): ProcessBooleanLabels {
  return {
    yes: translate(locale, 'processPage.status.yes'),
    no: translate(locale, 'processPage.status.no'),
  }
}

function statusClass(status?: string) {
  const key = String(status || '').toLowerCase()
  if (key.includes('fail') || key.includes('error')) return 'chip chip-danger'
  if (key.includes('done') || key.includes('success') || key.includes('completed')) return 'chip chip-ok'
  return 'chip chip-warn'
}

function canCancelTask(task: ProcessTaskItem) {
  const id = String(task.task_id || '')
  if (!id || id.startsWith('db-job-')) return false
  return ['active', 'pending', 'reserved'].includes(String(task.status || '').toLowerCase())
}

function stringifyBlock(value: unknown) {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function firstDefined<T>(...values: T[]): T | null {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== '') return value
  }
  return null
}

function toFiniteNumber(value: unknown) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function buildResultSummary(input: {
  display_meta?: Record<string, unknown> | null
  params?: Record<string, unknown> | null
  result?: unknown
  progress?: Record<string, unknown> | null
}, labels: ProcessSummaryLabels) {
  const dm = (input.display_meta || {}) as Record<string, unknown>
  const params = (input.params || {}) as Record<string, unknown>
  const progress = (input.progress || {}) as Record<string, unknown>
  const result = (input.result && typeof input.result === 'object' ? input.result : {}) as Record<string, unknown>

  const inserted = toFiniteNumber(firstDefined(dm.inserted, params.inserted, result.inserted, progress.inserted))
  const updated = toFiniteNumber(firstDefined(dm.updated, params.updated, result.updated, progress.updated))
  const skipped = toFiniteNumber(firstDefined(dm.skipped, params.skipped, result.skipped, progress.skipped))
  const errors = toFiniteNumber(firstDefined(dm.errors_count, params.errors_count, result.errors_count, progress.errors_count))
  const urls = toFiniteNumber(firstDefined(dm.url_count, params.url_count, params.urls, result.url_count, result.urls))

  const parts: string[] = []
  if (inserted != null) parts.push([labels.inserted, inserted].join(' '))
  if (updated != null) parts.push([labels.updated, updated].join(' '))
  if (skipped != null) parts.push([labels.skipped, skipped].join(' '))
  if (errors != null && errors > 0) parts.push([labels.errors, errors].join(' '))
  if (urls != null) parts.push([labels.urls, urls].join(' '))
  return parts.length ? parts.join(' | ') : '-'
}

function normalizeBreakdown(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const out: Record<string, number> = {}
  Object.entries(value as Record<string, unknown>).forEach(([key, raw]) => {
    const n = Number(raw)
    if (key && Number.isFinite(n) && n > 0) out[key] = n
  })
  return out
}

function topRejectionReason(breakdown: Record<string, number>): string {
  const entries = Object.entries(breakdown)
  if (!entries.length) return '-'
  const [reason, count] = entries.sort((a, b) => b[1] - a[1])[0]
  return String(reason) + ' (' + String(count) + ')'
}

function buildRejectionView(input: {
  display_meta?: Record<string, unknown> | null
  params?: Record<string, unknown> | null
  result?: unknown
  progress?: Record<string, unknown> | null
}) {
  const dm = (input.display_meta || {}) as Record<string, unknown>
  const params = (input.params || {}) as Record<string, unknown>
  const progress = (input.progress || {}) as Record<string, unknown>
  const result = (input.result && typeof input.result === 'object' ? input.result : {}) as Record<string, unknown>
  const insertedValid = toFiniteNumber(firstDefined(dm.inserted_valid, params.inserted_valid, result.inserted_valid, progress.inserted_valid))
  const rejectedCount = toFiniteNumber(firstDefined(dm.rejected_count, params.rejected_count, result.rejected_count, progress.rejected_count))
  const breakdown = normalizeBreakdown(
    firstDefined(dm.rejection_breakdown, params.rejection_breakdown, result.rejection_breakdown, progress.rejection_breakdown),
  )
  return {
    insertedValid,
    rejectedCount,
    rejectionBreakdown: breakdown,
    topReason: topRejectionReason(breakdown),
  }
}

function buildLightFilterView(input: {
  display_meta?: Record<string, unknown> | null
  params?: Record<string, unknown> | null
  result?: unknown
  progress?: Record<string, unknown> | null
}, labels: ProcessBooleanLabels) {
  const dm = (input.display_meta || {}) as Record<string, unknown>
  const params = (input.params || {}) as Record<string, unknown>
  const progress = (input.progress || {}) as Record<string, unknown>
  const result = (input.result && typeof input.result === 'object' ? input.result : {}) as Record<string, unknown>
  const nested = (result.light_filter && typeof result.light_filter === 'object' ? result.light_filter : {}) as Record<string, unknown>
  const decision = String(
    firstDefined(
      nested.filter_decision,
      result.filter_decision,
      dm.filter_decision,
      params.filter_decision,
      progress.filter_decision,
      '-',
    ) || '-',
  )
  const reason = String(
    firstDefined(
      nested.filter_reason_code,
      result.filter_reason_code,
      dm.filter_reason_code,
      params.filter_reason_code,
      progress.filter_reason_code,
      '-',
    ) || '-',
  )
  const score = toFiniteNumber(
    firstDefined(nested.filter_score, result.filter_score, dm.filter_score, params.filter_score, progress.filter_score),
  )
  const keepRaw = firstDefined(
    nested.keep_for_vectorization,
    result.keep_for_vectorization,
    dm.keep_for_vectorization,
    params.keep_for_vectorization,
    progress.keep_for_vectorization,
  )
  const keep = typeof keepRaw === 'boolean' ? (keepRaw ? labels.yes : labels.no) : '-'
  return { decision, reason, score, keep }
}

function getTaskSourceKind(task?: ProcessTaskItem, fallback?: string | null) {
  if (task?.source) return task.source
  if (fallback) return fallback
  if (String(task?.task_id || '').startsWith('db-job-')) return 'db-running'
  if (task?.worker) return 'worker'
  return 'unknown'
}

export function ProcessPage({ projectKey, variant = 'process' }: ProcessPageProps) {
  const locale = useAppLocale()
  const summaryLabels = useMemo(() => getProcessSummaryLabels(locale), [locale])
  const booleanLabels = useMemo(() => getProcessBooleanLabels(locale), [locale])
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true)
  const [refreshIntervalSec, setRefreshIntervalSec] = useState(8)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null)
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([])

  const {
    processStats,
    processList,
    processHistory,
    taskDetail,
    taskLogs,
    cancelMutation,
    cancelTasks,
    refreshAll,
    refreshSelectedTask,
    refreshHistory,
    isRefreshing,
  } = useProcessData({
    projectKey,
    selectedTaskId,
    autoRefreshEnabled,
    refreshIntervalSec,
  })
  const selectedTask = useMemo(
    () => (processList.data?.tasks || []).find((task) => task.task_id === selectedTaskId),
    [processList.data?.tasks, selectedTaskId],
  )
  const selectedHistoryTask = useMemo(
    () => (processHistory.data?.history || []).find((row) => Number(row.id) === Number(selectedHistoryId)),
    [processHistory.data?.history, selectedHistoryId],
  )
  const selectedCurrent = Boolean(selectedTaskId)
  const selectedMeta = selectedCurrent
    ? taskDetail.data?.display_meta || selectedTask?.display_meta || null
    : selectedHistoryTask?.display_meta || null
  const selectedSourceKind = selectedCurrent
    ? getTaskSourceKind(selectedTask, taskDetail.data?.worker ? 'worker' : null)
    : selectedHistoryTask?.source || 'history'
  const selectedResultSummary = selectedCurrent
    ? buildResultSummary({
        display_meta: (taskDetail.data?.display_meta || selectedTask?.display_meta || null) as Record<string, unknown> | null,
        params: (taskDetail.data?.kwargs || selectedTask?.kwargs || null) as Record<string, unknown> | null,
        progress: (taskDetail.data?.progress || selectedTask?.progress || null) as Record<string, unknown> | null,
        result: taskDetail.data?.result,
      }, summaryLabels)
    : buildResultSummary({
        display_meta: (selectedHistoryTask?.display_meta || null) as Record<string, unknown> | null,
        params: (selectedHistoryTask?.params || null) as Record<string, unknown> | null,
      }, summaryLabels)
  const selectedRejectionView = selectedCurrent
    ? buildRejectionView({
        display_meta: (taskDetail.data?.display_meta || selectedTask?.display_meta || null) as Record<string, unknown> | null,
        params: (taskDetail.data?.kwargs || selectedTask?.kwargs || null) as Record<string, unknown> | null,
        progress: (taskDetail.data?.progress || selectedTask?.progress || null) as Record<string, unknown> | null,
        result: taskDetail.data?.result,
      })
    : buildRejectionView({
        display_meta: (selectedHistoryTask?.display_meta || null) as Record<string, unknown> | null,
        params: (selectedHistoryTask?.params || null) as Record<string, unknown> | null,
      })
  const selectedLightFilterView = selectedCurrent
    ? buildLightFilterView({
        display_meta: (taskDetail.data?.display_meta || selectedTask?.display_meta || null) as Record<string, unknown> | null,
        params: (taskDetail.data?.kwargs || selectedTask?.kwargs || null) as Record<string, unknown> | null,
        progress: (taskDetail.data?.progress || selectedTask?.progress || null) as Record<string, unknown> | null,
        result: taskDetail.data?.result,
      }, booleanLabels)
    : buildLightFilterView({
        display_meta: (selectedHistoryTask?.display_meta || null) as Record<string, unknown> | null,
        params: (selectedHistoryTask?.params || null) as Record<string, unknown> | null,
      }, booleanLabels)
  const cancellableSelectedTaskIds = selectedTaskIds.filter((taskId) => {
    const task = (processList.data?.tasks || []).find((item) => item.task_id === taskId)
    return task ? canCancelTask(task) : false
  })

  const toggleTaskSelect = (taskId: string) => {
    setSelectedTaskIds((prev) => (prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]))
  }

  const selectAllCancellable = () => {
    const ids = (processList.data?.tasks || []).filter((task) => canCancelTask(task)).map((task) => task.task_id)
    setSelectedTaskIds(ids)
  }

  const clearSelectedTasks = () => setSelectedTaskIds([])

  const cancelSelectedTasks = async () => {
    if (!cancellableSelectedTaskIds.length) return
    await cancelTasks(cancellableSelectedTaskIds)
    clearSelectedTasks()
  }

  return (
    <ProcessPageView
      variant={variant}
      autoRefreshEnabled={autoRefreshEnabled}
      refreshIntervalSec={refreshIntervalSec}
      processStats={processStats.data}
      processList={processList.data}
      processHistory={processHistory.data}
      taskDetail={taskDetail.data}
      taskLogsText={taskLogs.data?.text}
      taskLogsError={taskLogs.isError}
      cancelPending={cancelMutation.isPending}
      isRefreshing={isRefreshing}
      selectedTask={selectedTask}
      selectedHistoryTask={selectedHistoryTask}
      selectedCurrent={selectedCurrent}
      selectedTaskId={selectedTaskId}
      selectedHistoryId={selectedHistoryId}
      selectedTaskIds={selectedTaskIds}
      selectedMeta={selectedMeta as Record<string, unknown> | null}
      selectedSourceKind={selectedSourceKind}
      selectedResultSummary={selectedResultSummary}
      selectedRejectionView={selectedRejectionView}
      selectedLightFilterView={selectedLightFilterView}
      cancellableSelectedTaskIds={cancellableSelectedTaskIds}
      onAutoRefreshEnabledChange={setAutoRefreshEnabled}
      onRefreshIntervalChange={setRefreshIntervalSec}
      onRefreshAll={() => {
        void refreshAll()
      }}
      onSelectAllCancellable={selectAllCancellable}
      onClearSelectedTasks={clearSelectedTasks}
      onCancelSelectedTasks={() => {
        void cancelSelectedTasks()
      }}
      onToggleTaskSelect={toggleTaskSelect}
      onToggleCurrentTaskDetail={(taskId) => {
        setSelectedHistoryId(null)
        setSelectedTaskId((prev) => (prev === taskId ? null : taskId))
      }}
      onToggleHistoryDetail={(historyId) => {
        setSelectedTaskId(null)
        setSelectedHistoryId((prev) => (prev === historyId ? null : historyId))
      }}
      onCancelTask={(taskId) => cancelMutation.mutate(taskId)}
      onCloseDetail={() => {
        setSelectedTaskId(null)
        setSelectedHistoryId(null)
      }}
      onRefreshSelectedTask={() => {
        void refreshSelectedTask(selectedTaskId)
      }}
      onRefreshHistory={() => {
        void refreshHistory()
      }}
    />
  )
}

export function ProcessPageView({
  variant,
  autoRefreshEnabled,
  refreshIntervalSec,
  processStats,
  processList,
  processHistory,
  taskDetail,
  taskLogsText,
  taskLogsError,
  cancelPending,
  isRefreshing,
  selectedTask,
  selectedHistoryTask,
  selectedCurrent,
  selectedTaskId,
  selectedHistoryId,
  selectedTaskIds,
  selectedMeta,
  selectedSourceKind,
  selectedResultSummary,
  selectedRejectionView,
  selectedLightFilterView,
  cancellableSelectedTaskIds,
  onAutoRefreshEnabledChange,
  onRefreshIntervalChange,
  onRefreshAll,
  onSelectAllCancellable,
  onClearSelectedTasks,
  onCancelSelectedTasks,
  onToggleTaskSelect,
  onToggleCurrentTaskDetail,
  onToggleHistoryDetail,
  onCancelTask,
  onCloseDetail,
  onRefreshSelectedTask,
  onRefreshHistory,
}: ProcessPageViewProps) {
  const locale = useAppLocale()
  const summaryLabels = useMemo(() => getProcessSummaryLabels(locale), [locale])
  const t = (key: ProcessMessageKey, fallback?: string) => translate(locale, key, fallback)
  const formatTemplate = (key: ProcessMessageKey, values: Record<string, string | number>) =>
    formatProcessTemplate(t(key), values)
  const formatMetaValue = (key: ProcessMessageKey, value: unknown) =>
    value === null || value === undefined || value === '' ? '' : formatTemplate(key, { value: String(value) })
  const selectedMetaSegments = [
    formatMetaValue('processPage.meta.itemKey', selectedMeta?.item_key),
    formatMetaValue('processPage.meta.channel', selectedMeta?.channel),
    formatMetaValue('processPage.meta.provider', selectedMeta?.provider),
  ].filter(Boolean)

  return (
    <div className={`content-stack process-page process-page--${variant}`}>
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'processing' ? t('processPage.title.processing') : t('processPage.title.process')}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card">
          <span>{t('processPage.kpi.runningTasks')}</span>
          <strong>{processStats?.total_running || 0}</strong>
          <small>{formatTemplate('processPage.kpi.activeTasks', { count: processStats?.active_tasks || 0 })}</small>
        </article>
        <article className="kpi-card">
          <span>{t('processPage.kpi.scheduledTasks')}</span>
          <strong>{processStats?.scheduled_tasks || 0}</strong>
          <small>{formatTemplate('processPage.kpi.reservedTasks', { count: processStats?.reserved_tasks || 0 })}</small>
        </article>
        <article className="kpi-card">
          <span>{t('processPage.kpi.workers')}</span>
          <strong>{processStats?.workers || 0}</strong>
          <small>{(processStats?.worker_names || []).slice(0, 2).join(', ') || '-'}</small>
        </article>
        <article className="kpi-card">
          <span>{t('processPage.kpi.totalTasks')}</span>
          <strong>{processList?.stats?.total_tasks || 0}</strong>
          <small>{formatTemplate('processPage.kpi.pendingTasks', { count: processList?.stats?.pending_tasks || 0 })}</small>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Database size={15} />
            {t('processPage.section.currentQueue')}
          </h2>
          <div className="inline-actions">
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={autoRefreshEnabled} onChange={(e) => onAutoRefreshEnabledChange(e.target.checked)} />
              {t('processPage.control.autoRefresh')}
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {t('processPage.control.interval')}
              <select value={refreshIntervalSec} disabled={!autoRefreshEnabled} onChange={(e) => onRefreshIntervalChange(Number(e.target.value) || 8)}>
                {[5, 8, 10, 15, 30, 60].map((sec) => (
                  <option key={sec} value={sec}>
                    {sec}s
                  </option>
                ))}
              </select>
            </label>
            <button onClick={onRefreshAll} disabled={isRefreshing}>
              <RefreshCw size={14} />
              {isRefreshing ? t('processPage.action.refreshing') : t('processPage.action.refresh')}
            </button>
            <button onClick={onSelectAllCancellable} disabled={!(processList?.tasks || []).length}>
              {t('processPage.action.selectCancellable')}
            </button>
            <button onClick={onClearSelectedTasks} disabled={!selectedTaskIds.length}>
              {t('processPage.action.clearSelection')}
            </button>
            <button onClick={onCancelSelectedTasks} disabled={!cancellableSelectedTaskIds.length || cancelPending}>
              {formatTemplate('processPage.action.cancelSelected', { count: cancellableSelectedTaskIds.length })}
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('processPage.field.taskId')}</th>
                <th>{t('processPage.field.name')}</th>
                <th>{t('processPage.field.status')}</th>
                <th>{t('processPage.field.worker')}</th>
                <th>{t('processPage.field.source')}</th>
                <th>{t('processPage.field.started')}</th>
                <th>{t('processPage.field.selected')}</th>
                <th>{t('processPage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {(processList?.tasks || []).map((task) => (
                <tr key={task.task_id}>
                  <td>{task.task_id}</td>
                  <td>{task.name || '-'}</td>
                  <td><span className={statusClass(task.status)}>{task.status || '-'}</span></td>
                  <td>{task.worker || '-'}</td>
                  <td>
                    <div>{getTaskSourceKind(task)}</div>
                    {task.display_meta?.item_key || task.display_meta?.channel || task.display_meta?.provider ? (
                      <small>
                        {[
                          formatMetaValue('processPage.meta.item', task.display_meta?.item_key),
                          formatMetaValue('processPage.meta.channel', task.display_meta?.channel),
                          formatMetaValue('processPage.meta.provider', task.display_meta?.provider),
                        ].filter(Boolean).join(' | ')}
                      </small>
                    ) : null}
                  </td>
                  <td>{formatDate(task.started_at, locale)}</td>
                  <td>
                    <input type="checkbox" checked={selectedTaskIds.includes(task.task_id)} onChange={() => onToggleTaskSelect(task.task_id)} disabled={!canCancelTask(task)} />
                  </td>
                  <td>
                    <button onClick={() => onToggleCurrentTaskDetail(task.task_id)}>
                      {selectedTaskId === task.task_id ? t('processPage.action.collapse') : t('processPage.action.details')}
                    </button>
                    <button disabled={!canCancelTask(task) || cancelPending} onClick={() => onCancelTask(task.task_id)}>
                      <XCircle size={14} />
                      {t('processPage.action.cancel')}
                    </button>
                  </td>
                </tr>
              ))}
              {!processList?.tasks?.length ? (
                <tr>
                  <td colSpan={8} className="empty-cell">{t('processPage.empty.runningTasks')}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {selectedTaskId || selectedHistoryId ? (
        <div className="process-detail-backdrop" onClick={onCloseDetail}>
          <section className="panel process-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h2>
                {t('processPage.section.taskDetail')}{' '}
                {selectedCurrent ? selectedTaskId : formatTemplate('processPage.detail.historyId', { id: selectedHistoryId ?? '-' })}
              </h2>
              <div className="inline-actions">
                <button onClick={onRefreshSelectedTask} disabled={!selectedCurrent || isRefreshing}>
                  <RefreshCw size={14} />
                  {selectedCurrent && isRefreshing ? t('processPage.action.refreshing') : t('processPage.action.refresh')}
                </button>
                <button onClick={onCloseDetail}>{t('processPage.action.close')}</button>
              </div>
            </div>
            <div className="content-stack">
              <div>
                <strong>{t('processPage.field.status')}：</strong>
                <span className={statusClass(selectedCurrent ? (taskDetail?.status || selectedTask?.status) : selectedHistoryTask?.status)}>
                  {selectedCurrent ? (taskDetail?.status || selectedTask?.status || '-') : (selectedHistoryTask?.status || '-')}
                </span>
              </div>
              <div>
                <strong>{t('processPage.field.source')}：</strong>
                {selectedSourceKind}
                {selectedMetaSegments.length ? ' | ' : ''}
                {selectedMetaSegments.join(' | ')}
              </div>
              <div><strong>{t('processPage.field.resultSummary')}：</strong>{selectedResultSummary}</div>
              <div><strong>{t('processPage.field.insertedValid')}：</strong>{selectedRejectionView.insertedValid ?? '-'} {' | '}<strong>{t('processPage.field.rejected')}：</strong>{selectedRejectionView.rejectedCount ?? '-'}</div>
              <div><strong>{t('processPage.field.topRejectionReason')}：</strong>{selectedRejectionView.topReason}</div>
              <div><strong>{t('processPage.field.lightFilter')}：</strong>{selectedLightFilterView.decision} {' | '}<strong>{t('processPage.field.reason')}：</strong>{selectedLightFilterView.reason} {' | '}<strong>{t('processPage.field.score')}：</strong>{selectedLightFilterView.score ?? '-'} {' | '}<strong>{t('processPage.field.keepForVectorization')}：</strong>{selectedLightFilterView.keep}</div>
              <div>
                <strong>{t('processPage.section.rejectionBreakdown')}</strong>
                <pre style={detailPreStyle}>{Object.keys(selectedRejectionView.rejectionBreakdown).length ? stringifyBlock(selectedRejectionView.rejectionBreakdown) : '-'}</pre>
              </div>
              <div><strong>{t('processPage.field.worker')}：</strong>{selectedCurrent ? (taskDetail?.worker || selectedTask?.worker || '-') : (selectedHistoryTask?.worker || '-')}</div>
              <div><strong>{t('processPage.field.started')}：</strong>{formatDate(selectedCurrent ? (taskDetail?.started_at || selectedTask?.started_at) : selectedHistoryTask?.started_at, locale)}</div>
              {!selectedCurrent ? (
                <>
                  <div><strong>{t('processPage.field.finished')}：</strong>{formatDate(selectedHistoryTask?.finished_at, locale)}</div>
                  <div><strong>{t('processPage.field.durationSeconds')}：</strong>{selectedHistoryTask?.duration_seconds != null ? selectedHistoryTask.duration_seconds.toFixed(1) : '-'}</div>
                  <div><strong>{t('processPage.field.jobType')}：</strong>{selectedHistoryTask?.job_type || '-'}</div>
                </>
              ) : null}
              <div><strong>{t('processPage.field.displayMeta')}</strong><pre style={detailPreStyle}>{stringifyBlock(selectedMeta)}</pre></div>
              {selectedCurrent ? (
                <>
                  <div><strong>{t('processPage.field.args')}</strong><pre style={detailPreStyle}>{stringifyBlock(taskDetail?.args || selectedTask?.args)}</pre></div>
                  <div><strong>{t('processPage.field.kwargs')}</strong><pre style={detailPreStyle}>{stringifyBlock(taskDetail?.kwargs || selectedTask?.kwargs)}</pre></div>
                  <div><strong>{t('processPage.field.progress')}</strong><pre style={detailPreStyle}>{stringifyBlock(taskDetail?.progress || selectedTask?.progress)}</pre></div>
                  <div><strong>{t('processPage.field.resultRaw')}</strong><pre style={detailPreStyle}>{stringifyBlock(taskDetail?.result)}</pre></div>
                  <div><strong>{t('processPage.field.traceback')}</strong><pre style={detailPreStyle}>{stringifyBlock(taskDetail?.traceback || selectedTask?.traceback)}</pre></div>
                  <div><strong>{t('processPage.field.logsTail')}</strong><pre style={detailPreStyle}>{taskLogsError ? t('processPage.error.logsFailed') : stringifyBlock(taskLogsText)}</pre></div>
                </>
              ) : (
                <>
                  <div><strong>{t('processPage.field.params')}</strong><pre style={detailPreStyle}>{stringifyBlock(selectedHistoryTask?.params)}</pre></div>
                  <div><strong>{t('processPage.field.error')}</strong><pre style={detailPreStyle}>{stringifyBlock(selectedHistoryTask?.error)}</pre></div>
                </>
              )}
            </div>
          </section>
        </div>
      ) : null}

      <section className="panel">
        <div className="panel-header">
          <h2>{t('processPage.section.taskHistory')}</h2>
          <div className="inline-actions">
            <button onClick={onRefreshHistory} disabled={isRefreshing}>
              <RefreshCw size={14} />
              {isRefreshing ? t('processPage.action.refreshing') : t('processPage.action.refresh')}
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('processPage.field.id')}</th>
                <th>{t('processPage.field.type')}</th>
                <th>{t('processPage.field.status')}</th>
                <th>{t('processPage.field.start')}</th>
                <th>{t('processPage.field.end')}</th>
                <th>{t('processPage.field.durationSeconds')}</th>
                <th>{t('processPage.field.result')}</th>
                <th>{t('processPage.field.insertedValid')}</th>
                <th>{t('processPage.field.rejected')}</th>
                <th>{t('processPage.field.topRejectionReason')}</th>
                <th>{t('processPage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {(processHistory?.history || []).map((row) => {
                const rowRejectionView = buildRejectionView({
                  display_meta: row.display_meta as Record<string, unknown> | null,
                  params: row.params || null,
                })
                return (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{row.job_type || '-'}</td>
                    <td><span className={statusClass(row.status)}>{row.status || '-'}</span></td>
                    <td>{formatDate(row.started_at, locale)}</td>
                    <td>{formatDate(row.finished_at, locale)}</td>
                    <td>{row.duration_seconds != null ? row.duration_seconds.toFixed(1) : '-'}</td>
                    <td>{buildResultSummary({ display_meta: row.display_meta as Record<string, unknown> | null, params: row.params || null }, summaryLabels)}</td>
                    <td>{rowRejectionView.insertedValid ?? '-'}</td>
                    <td>{rowRejectionView.rejectedCount ?? '-'}</td>
                    <td>{rowRejectionView.topReason}</td>
                    <td>
                      <button onClick={() => onToggleHistoryDetail(Number(row.id))}>
                        {selectedHistoryId === Number(row.id) ? t('processPage.action.collapse') : t('processPage.action.details')}
                      </button>
                    </td>
                  </tr>
                )
              })}
              {!processHistory?.history?.length ? (
                <tr>
                  <td colSpan={11} className="empty-cell">{t('processPage.empty.history')}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

export default ProcessPage
