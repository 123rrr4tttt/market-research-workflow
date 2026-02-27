import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Trash2 } from 'lucide-react'
import { cleanupGovernance, getAdminStats, getSearchHistory, syncAggregator } from '../lib/api'

type OpsPageProps = {
  projectKey: string
  variant?: 'ops' | 'backend'
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
}

export default function OpsPage({ projectKey, variant = 'ops' }: OpsPageProps) {
  const queryClient = useQueryClient()
  const [retentionDays, setRetentionDays] = useState(90)
  const [pending, setPending] = useState(false)
  const [statusText, setStatusText] = useState('等待操作')

  const adminStats = useQuery({ queryKey: ['admin-stats', projectKey], queryFn: getAdminStats, enabled: Boolean(projectKey) })
  const searchHistory = useQuery({ queryKey: ['search-history', projectKey], queryFn: () => getSearchHistory(1, 30), enabled: Boolean(projectKey) })

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    setPending(true)
    setStatusText(`${name} 执行中...`)
    try {
      const result = await fn()
      const taskId = typeof (result as { task_id?: unknown })?.task_id === 'string' ? String((result as { task_id?: string }).task_id) : ''
      setStatusText(taskId ? `${name} 已提交，任务 ID: ${taskId}` : `${name} 完成`)
      await queryClient.invalidateQueries({ queryKey: ['admin-stats', projectKey] })
      await queryClient.invalidateQueries({ queryKey: ['search-history', projectKey] })
    } catch (error) {
      setStatusText(`${name} 失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'backend' ? '后端监控视图' : '数据运维视图'}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card"><span>文档</span><strong>{adminStats.data?.documents?.total || 0}</strong><small>今日 {adminStats.data?.documents?.recent_today || 0}</small></article>
        <article className="kpi-card"><span>社媒文档</span><strong>{adminStats.data?.social_data?.total || 0}</strong><small>今日 {adminStats.data?.social_data?.recent_today || 0}</small></article>
        <article className="kpi-card"><span>来源数</span><strong>{adminStats.data?.sources?.total || 0}</strong><small>source table</small></article>
        <article className="kpi-card"><span>搜索历史</span><strong>{adminStats.data?.search_history?.total || 0}</strong><small>admin/search-history</small></article>
      </section>

      <section className="panel">
        <div className="panel-header"><h2>治理动作</h2></div>
        <div className="inline-actions">
          <label><span>retention_days</span><input type="number" min={1} max={3650} value={retentionDays} onChange={(e) => setRetentionDays(Number.parseInt(e.target.value || '90', 10) || 90)} /></label>
          <button disabled={pending} onClick={() => runAction('数据清理', () => cleanupGovernance(retentionDays))}><Trash2 size={14} />清理旧数据</button>
          <button disabled={pending} onClick={() => runAction('聚合库同步', () => syncAggregator(true))}><RefreshCw size={14} />同步 Aggregator</button>
          <button onClick={() => { queryClient.invalidateQueries({ queryKey: ['admin-stats', projectKey] }); queryClient.invalidateQueries({ queryKey: ['search-history', projectKey] }); }}><RefreshCw size={14} />刷新</button>
        </div>
        <p className="status-line">{statusText}</p>
      </section>

      <section className="panel">
        <div className="panel-header"><h2>搜索历史</h2></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>topic</th><th>last_search_time</th></tr></thead>
            <tbody>
              {(searchHistory.data || []).map((row) => (
                <tr key={row.id}><td>{row.id}</td><td>{row.topic || '-'}</td><td>{formatDate(row.last_search_time)}</td></tr>
              ))}
              {!searchHistory.data?.length && <tr><td colSpan={3} className="empty-cell">暂无搜索历史</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
