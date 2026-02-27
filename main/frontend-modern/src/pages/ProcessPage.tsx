import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, RefreshCw, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { cancelTask, getProcessStats, getProcessTaskDetail, getProcessTaskLogs, listProcessHistory, listProcessTasks } from '../lib/api'
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

function getTaskSourceKind(task?: ProcessTaskItem, fallback?: string | null) {
  if (task?.source) return task.source
  if (fallback) return fallback
  if (String(task?.task_id || '').startsWith('db-job-')) return 'db-running'
  if (task?.worker) return 'worker'
  return 'unknown'
}

export function ProcessPage({ projectKey, variant = 'process' }: ProcessPageProps) {
  const queryClient = useQueryClient()
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true)
  const [refreshIntervalSec, setRefreshIntervalSec] = useState(8)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([])

  const refreshIntervalMs = autoRefreshEnabled ? Math.max(3, refreshIntervalSec) * 1000 : false

  const processStats = useQuery({
    queryKey: ['process-stats', projectKey],
    queryFn: getProcessStats,
    enabled: Boolean(projectKey),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const processList = useQuery({
    queryKey: ['process-list', projectKey],
    queryFn: () => listProcessTasks(40),
    enabled: Boolean(projectKey),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const processHistory = useQuery({
    queryKey: ['process-history', projectKey],
    queryFn: () => listProcessHistory(50),
    enabled: Boolean(projectKey),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const taskDetail = useQuery({
    queryKey: ['process-task-detail', projectKey, selectedTaskId],
    queryFn: () => getProcessTaskDetail(String(selectedTaskId)),
    enabled: Boolean(projectKey && selectedTaskId),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const taskLogs = useQuery({
    queryKey: ['process-task-logs', projectKey, selectedTaskId],
    queryFn: () => getProcessTaskLogs(String(selectedTaskId), 200),
    enabled: Boolean(projectKey && selectedTaskId),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => cancelTask(taskId, false),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['process-stats', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['process-list', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['process-history', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['process-task-detail', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['process-task-logs', projectKey] }),
      ])
    },
  })

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['process-stats', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['process-list', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['process-history', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['process-task-detail', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['process-task-logs', projectKey] }),
    ])
  }

  const isRefreshing = processStats.isFetching || processList.isFetching || processHistory.isFetching || taskDetail.isFetching || taskLogs.isFetching
  const selectedTask = useMemo(
    () => (processList.data?.tasks || []).find((task) => task.task_id === selectedTaskId),
    [processList.data?.tasks, selectedTaskId],
  )
  const selectedMeta = taskDetail.data?.display_meta || selectedTask?.display_meta || null
  const selectedSourceKind = getTaskSourceKind(selectedTask, taskDetail.data?.worker ? 'worker' : null)
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
    for (const taskId of cancellableSelectedTaskIds) {
      try {
        await cancelTask(taskId, false)
      } catch {
        // continue cancelling remaining tasks
      }
    }
    clearSelectedTasks()
    await refreshAll()
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
                    <button onClick={() => setSelectedTaskId((prev) => (prev === task.task_id ? null : task.task_id))}>
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

      {selectedTaskId ? (
        <section className="panel">
          <div className="panel-header">
            <h2>任务详情 {selectedTaskId}</h2>
            <div className="inline-actions">
              <button
                onClick={() => {
                  void queryClient.invalidateQueries({ queryKey: ['process-task-detail', projectKey, selectedTaskId] })
                  void queryClient.invalidateQueries({ queryKey: ['process-task-logs', projectKey, selectedTaskId] })
                }}
                disabled={taskDetail.isFetching || taskLogs.isFetching}
              >
                <RefreshCw size={14} />
                {taskDetail.isFetching || taskLogs.isFetching ? '刷新中...' : '刷新'}
              </button>
              <button onClick={() => setSelectedTaskId(null)}>关闭</button>
            </div>
          </div>
          <div className="content-stack">
            <div>
              <strong>状态：</strong>
              <span className={statusClass(taskDetail.data?.status || selectedTask?.status)}>{taskDetail.data?.status || selectedTask?.status || '-'}</span>
            </div>
            <div>
              <strong>来源：</strong>
              {selectedSourceKind}
              {selectedMeta?.item_key ? ` | item_key=${selectedMeta.item_key}` : ''}
              {selectedMeta?.channel ? ` | channel=${selectedMeta.channel}` : ''}
              {selectedMeta?.provider ? ` | provider=${selectedMeta.provider}` : ''}
            </div>
            <div>
              <strong>Worker：</strong>
              {taskDetail.data?.worker || selectedTask?.worker || '-'}
            </div>
            <div>
              <strong>Started：</strong>
              {formatDate(taskDetail.data?.started_at || selectedTask?.started_at)}
            </div>
            <div>
              <strong>display_meta</strong>
              <pre style={{ marginTop: 8, maxHeight: 220, overflow: 'auto' }}>{stringifyBlock(selectedMeta)}</pre>
            </div>
            <div>
              <strong>args</strong>
              <pre style={{ marginTop: 8, maxHeight: 220, overflow: 'auto' }}>
                {stringifyBlock(taskDetail.data?.args || selectedTask?.args)}
              </pre>
            </div>
            <div>
              <strong>kwargs</strong>
              <pre style={{ marginTop: 8, maxHeight: 220, overflow: 'auto' }}>
                {stringifyBlock(taskDetail.data?.kwargs || selectedTask?.kwargs)}
              </pre>
            </div>
            <div>
              <strong>progress</strong>
              <pre style={{ marginTop: 8, maxHeight: 220, overflow: 'auto' }}>
                {stringifyBlock(taskDetail.data?.progress || selectedTask?.progress)}
              </pre>
            </div>
            <div>
              <strong>traceback</strong>
              <pre style={{ marginTop: 8, maxHeight: 220, overflow: 'auto' }}>
                {stringifyBlock(taskDetail.data?.traceback || selectedTask?.traceback)}
              </pre>
            </div>
            <div>
              <strong>logs (tail 200)</strong>
              <pre style={{ marginTop: 8, maxHeight: 280, overflow: 'auto' }}>
                {taskLogs.isError ? '日志加载失败' : stringifyBlock(taskLogs.data?.text)}
              </pre>
            </div>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="panel-header">
          <h2>任务历史</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ['process-history', projectKey] })} disabled={processHistory.isFetching}>
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
              </tr>
            </thead>
            <tbody>
              {(processHistory.data?.history || []).map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.job_type || '-'}</td>
                  <td>
                    <span className={statusClass(row.status)}>{row.status || '-'}</span>
                  </td>
                  <td>{formatDate(row.started_at)}</td>
                  <td>{formatDate(row.finished_at)}</td>
                  <td>{row.duration_seconds != null ? row.duration_seconds.toFixed(1) : '-'}</td>
                </tr>
              ))}
              {!processHistory.data?.history?.length ? (
                <tr>
                  <td colSpan={6} className="empty-cell">
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
