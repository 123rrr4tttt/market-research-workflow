import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, RefreshCw, XCircle } from 'lucide-react'
import { cancelTask, getProcessStats, listProcessHistory, listProcessTasks } from '../lib/api'
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

export function ProcessPage({ projectKey, variant = 'process' }: ProcessPageProps) {
  const queryClient = useQueryClient()

  const processStats = useQuery({
    queryKey: ['process-stats', projectKey],
    queryFn: getProcessStats,
    enabled: Boolean(projectKey),
  })

  const processList = useQuery({
    queryKey: ['process-list', projectKey],
    queryFn: () => listProcessTasks(40),
    enabled: Boolean(projectKey),
  })

  const processHistory = useQuery({
    queryKey: ['process-history', projectKey],
    queryFn: () => listProcessHistory(50),
    enabled: Boolean(projectKey),
  })

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => cancelTask(taskId, false),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['process-stats', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['process-list', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['process-history', projectKey] }),
      ])
    },
  })

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['process-stats', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['process-list', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['process-history', projectKey] }),
    ])
  }

  const isRefreshing = processStats.isFetching || processList.isFetching || processHistory.isFetching

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
            <button onClick={() => void refreshAll()} disabled={isRefreshing}>
              <RefreshCw size={14} />
              {isRefreshing ? '刷新中...' : '刷新'}
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
                <th>Started</th>
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
                  <td>{formatDate(task.started_at)}</td>
                  <td>
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
                  <td colSpan={6} className="empty-cell">
                    暂无运行中任务
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

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
