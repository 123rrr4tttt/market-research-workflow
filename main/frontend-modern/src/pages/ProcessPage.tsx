import { Database, RefreshCw, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useProcessData } from '../hooks/useProcessData'
import type { ProcessTaskItem } from '../lib/types'

export type ProcessPageProps = {
  projectKey: string
  variant?: 'process' | 'processing'
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
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
}) {
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
  if (inserted != null) parts.push(`新增 ${inserted}`)
  if (updated != null) parts.push(`更新 ${updated}`)
  if (skipped != null) parts.push(`跳过 ${skipped}`)
  if (errors != null && errors > 0) parts.push(`错误 ${errors}`)
  if (urls != null) parts.push(`URL ${urls}`)
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
  return `${reason} (${count})`
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
}) {
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
  const keep = typeof keepRaw === 'boolean' ? (keepRaw ? 'yes' : 'no') : '-'
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
      })
    : buildResultSummary({
        display_meta: (selectedHistoryTask?.display_meta || null) as Record<string, unknown> | null,
        params: (selectedHistoryTask?.params || null) as Record<string, unknown> | null,
      })
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
      })
    : buildLightFilterView({
        display_meta: (selectedHistoryTask?.display_meta || null) as Record<string, unknown> | null,
        params: (selectedHistoryTask?.params || null) as Record<string, unknown> | null,
      })
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

  const detailPreStyle = {
    marginTop: 8,
    maxHeight: 280,
    overflow: 'auto' as const,
    whiteSpace: 'pre-wrap' as const,
    overflowWrap: 'anywhere' as const,
  }

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'processing' ? '数据处理任务视图' : '任务调度视图'}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card">
          <span>运行任务</span>
          <strong>{processStats.data?.total_running || 0}</strong>
          <small>active {processStats.data?.active_tasks || 0}</small>
        </article>
        <article className="kpi-card">
          <span>scheduled</span>
          <strong>{processStats.data?.scheduled_tasks || 0}</strong>
          <small>reserved {processStats.data?.reserved_tasks || 0}</small>
        </article>
        <article className="kpi-card">
          <span>workers</span>
          <strong>{processStats.data?.workers || 0}</strong>
          <small>{(processStats.data?.worker_names || []).slice(0, 2).join(', ') || '-'}</small>
        </article>
        <article className="kpi-card">
          <span>总任务</span>
          <strong>{processList.data?.stats?.total_tasks || 0}</strong>
          <small>pending {processList.data?.stats?.pending_tasks || 0}</small>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Database size={15} />
            当前队列
          </h2>
          <div className="inline-actions">
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input
                type="checkbox"
                checked={autoRefreshEnabled}
                onChange={(e) => setAutoRefreshEnabled(e.target.checked)}
              />
              自动刷新
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              间隔
              <select
                value={refreshIntervalSec}
                disabled={!autoRefreshEnabled}
                onChange={(e) => setRefreshIntervalSec(Number(e.target.value) || 8)}
              >
                {[5, 8, 10, 15, 30, 60].map((sec) => (
                  <option key={sec} value={sec}>
                    {sec}s
                  </option>
                ))}
              </select>
            </label>
            <button onClick={() => void refreshAll()} disabled={isRefreshing}>
              <RefreshCw size={14} />
              {isRefreshing ? '刷新中...' : '刷新'}
            </button>
            <button onClick={selectAllCancellable} disabled={!(processList.data?.tasks || []).length}>
              选择可取消
            </button>
            <button onClick={clearSelectedTasks} disabled={!selectedTaskIds.length}>
              清空选择
            </button>
            <button onClick={() => void cancelSelectedTasks()} disabled={!cancellableSelectedTaskIds.length || cancelMutation.isPending}>
              批量取消({cancellableSelectedTaskIds.length})
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Task ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Worker</th>
                <th>来源</th>
                <th>Started</th>
                <th>选中</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {(processList.data?.tasks || []).map((task) => (
                <tr key={task.task_id}>
                  <td>{task.task_id}</td>
                  <td>{task.name || '-'}</td>
                  <td>
                    <span className={statusClass(task.status)}>{task.status || '-'}</span>
                  </td>
                  <td>{task.worker || '-'}</td>
                  <td>
                    <div>{getTaskSourceKind(task)}</div>
                    {task.display_meta?.item_key || task.display_meta?.channel || task.display_meta?.provider ? (
                      <small>
                        {task.display_meta?.item_key ? `item:${task.display_meta.item_key}` : ''}
                        {task.display_meta?.channel ? `${task.display_meta?.item_key ? ' | ' : ''}channel:${task.display_meta.channel}` : ''}
                        {task.display_meta?.provider
                          ? `${task.display_meta?.item_key || task.display_meta?.channel ? ' | ' : ''}provider:${task.display_meta.provider}`
                          : ''}
                      </small>
                    ) : null}
                  </td>
                  <td>{formatDate(task.started_at)}</td>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedTaskIds.includes(task.task_id)}
                      onChange={() => toggleTaskSelect(task.task_id)}
                      disabled={!canCancelTask(task)}
                    />
                  </td>
                  <td>
                    <button
                      onClick={() => {
                        setSelectedHistoryId(null)
                        setSelectedTaskId((prev) => (prev === task.task_id ? null : task.task_id))
                      }}
                    >
                      {selectedTaskId === task.task_id ? '收起' : '详情'}
                    </button>
                    <button
                      disabled={!canCancelTask(task) || cancelMutation.isPending}
                      onClick={() => cancelMutation.mutate(task.task_id)}
                    >
                      <XCircle size={14} />
                      取消
                    </button>
                  </td>
                </tr>
              ))}
              {!processList.data?.tasks?.length ? (
                <tr>
                  <td colSpan={8} className="empty-cell">
                    暂无运行中任务
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {selectedTaskId || selectedHistoryId ? (
        <div
          className="process-detail-backdrop"
          onClick={() => {
            setSelectedTaskId(null)
            setSelectedHistoryId(null)
          }}
        >
          <section className="panel process-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
            <h2>
              任务详情 {selectedCurrent ? selectedTaskId : `history#${selectedHistoryId}`}
            </h2>
            <div className="inline-actions">
              <button
                onClick={() => {
                  void refreshSelectedTask(selectedTaskId)
                }}
                disabled={!selectedCurrent || taskDetail.isFetching || taskLogs.isFetching}
              >
                <RefreshCw size={14} />
                {selectedCurrent && (taskDetail.isFetching || taskLogs.isFetching) ? '刷新中...' : '刷新'}
              </button>
              <button
                onClick={() => {
                  setSelectedTaskId(null)
                  setSelectedHistoryId(null)
                }}
              >
                关闭
              </button>
            </div>
            </div>
            <div className="content-stack">
            <div>
              <strong>状态：</strong>
              <span className={statusClass(selectedCurrent ? (taskDetail.data?.status || selectedTask?.status) : selectedHistoryTask?.status)}>
                {selectedCurrent ? (taskDetail.data?.status || selectedTask?.status || '-') : (selectedHistoryTask?.status || '-')}
              </span>
            </div>
            <div>
              <strong>来源：</strong>
              {selectedSourceKind}
              {selectedMeta?.item_key ? ` | item_key=${selectedMeta.item_key}` : ''}
              {selectedMeta?.channel ? ` | channel=${selectedMeta.channel}` : ''}
              {selectedMeta?.provider ? ` | provider=${selectedMeta.provider}` : ''}
            </div>
            <div>
              <strong>结果摘要：</strong>
              {selectedResultSummary}
            </div>
            <div>
              <strong>有效入库：</strong>
              {selectedRejectionView.insertedValid ?? '-'}
              {' | '}
              <strong>剔除：</strong>
              {selectedRejectionView.rejectedCount ?? '-'}
            </div>
            <div>
              <strong>主要剔除原因：</strong>
              {selectedRejectionView.topReason}
            </div>
            <div>
              <strong>轻过滤：</strong>
              {selectedLightFilterView.decision}
              {' | '}
              <strong>原因：</strong>
              {selectedLightFilterView.reason}
              {' | '}
              <strong>分数：</strong>
              {selectedLightFilterView.score ?? '-'}
              {' | '}
              <strong>向量化保留：</strong>
              {selectedLightFilterView.keep}
            </div>
            <div>
              <strong>剔除明细</strong>
              <pre style={detailPreStyle}>
                {Object.keys(selectedRejectionView.rejectionBreakdown).length
                  ? stringifyBlock(selectedRejectionView.rejectionBreakdown)
                  : '-'}
              </pre>
            </div>
            <div>
              <strong>Worker：</strong>
              {selectedCurrent ? (taskDetail.data?.worker || selectedTask?.worker || '-') : (selectedHistoryTask?.worker || '-')}
            </div>
            <div>
              <strong>Started：</strong>
              {formatDate(selectedCurrent ? (taskDetail.data?.started_at || selectedTask?.started_at) : selectedHistoryTask?.started_at)}
            </div>
            {!selectedCurrent ? (
              <>
                <div>
                  <strong>Finished：</strong>
                  {formatDate(selectedHistoryTask?.finished_at)}
                </div>
                <div>
                  <strong>Duration(s)：</strong>
                  {selectedHistoryTask?.duration_seconds != null ? selectedHistoryTask.duration_seconds.toFixed(1) : '-'}
                </div>
                <div>
                  <strong>job_type：</strong>
                  {selectedHistoryTask?.job_type || '-'}
                </div>
              </>
            ) : null}
            <div>
              <strong>display_meta</strong>
              <pre style={detailPreStyle}>{stringifyBlock(selectedMeta)}</pre>
            </div>
            {selectedCurrent ? (
              <>
                <div>
                  <strong>args</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(taskDetail.data?.args || selectedTask?.args)}
                  </pre>
                </div>
                <div>
                  <strong>kwargs</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(taskDetail.data?.kwargs || selectedTask?.kwargs)}
                  </pre>
                </div>
                <div>
                  <strong>progress</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(taskDetail.data?.progress || selectedTask?.progress)}
                  </pre>
                </div>
                <div>
                  <strong>result</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(taskDetail.data?.result)}
                  </pre>
                </div>
                <div>
                  <strong>traceback</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(taskDetail.data?.traceback || selectedTask?.traceback)}
                  </pre>
                </div>
                <div>
                  <strong>logs (tail 200)</strong>
                  <pre style={detailPreStyle}>
                    {taskLogs.isError ? '日志加载失败' : stringifyBlock(taskLogs.data?.text)}
                  </pre>
                </div>
              </>
            ) : (
              <>
                <div>
                  <strong>params</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(selectedHistoryTask?.params)}
                  </pre>
                </div>
                <div>
                  <strong>error</strong>
                  <pre style={detailPreStyle}>
                    {stringifyBlock(selectedHistoryTask?.error)}
                  </pre>
                </div>
              </>
            )}
            </div>
          </section>
        </div>
      ) : null}

      <section className="panel">
        <div className="panel-header">
          <h2>任务历史</h2>
          <div className="inline-actions">
            <button onClick={() => void refreshHistory()} disabled={processHistory.isFetching}>
              <RefreshCw size={14} />
              {processHistory.isFetching ? '刷新中...' : '刷新'}
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>类型</th>
                <th>状态</th>
                <th>开始</th>
                <th>结束</th>
                <th>耗时(秒)</th>
                <th>结果</th>
                <th>有效入库</th>
                <th>剔除</th>
                <th>主要剔除原因</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {(processHistory.data?.history || []).map((row) => {
                const rowRejectionView = buildRejectionView({
                  display_meta: row.display_meta as Record<string, unknown> | null,
                  params: row.params || null,
                })
                return (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{row.job_type || '-'}</td>
                    <td>
                      <span className={statusClass(row.status)}>{row.status || '-'}</span>
                    </td>
                    <td>{formatDate(row.started_at)}</td>
                    <td>{formatDate(row.finished_at)}</td>
                    <td>{row.duration_seconds != null ? row.duration_seconds.toFixed(1) : '-'}</td>
                    <td>{buildResultSummary({ display_meta: row.display_meta as Record<string, unknown> | null, params: row.params || null })}</td>
                    <td>{rowRejectionView.insertedValid ?? '-'}</td>
                    <td>{rowRejectionView.rejectedCount ?? '-'}</td>
                    <td>{rowRejectionView.topReason}</td>
                    <td>
                      <button
                        onClick={() => {
                          setSelectedTaskId(null)
                          setSelectedHistoryId((prev) => (prev === Number(row.id) ? null : Number(row.id)))
                        }}
                      >
                        {selectedHistoryId === Number(row.id) ? '收起' : '详情'}
                      </button>
                    </td>
                  </tr>
                )
              })}
              {!processHistory.data?.history?.length ? (
                <tr>
                  <td colSpan={11} className="empty-cell">
                    暂无历史数据
                  </td>
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
