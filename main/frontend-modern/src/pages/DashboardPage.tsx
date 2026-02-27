import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getDashboardStats } from '../lib/api'

type DashboardPageProps = {
  projectKey: string
  variant?: 'dashboard' | 'market' | 'social' | 'analysis' | 'board'
}

function asNumber(value: number | undefined) {
  return value ?? 0
}

function formatNumber(value: number | undefined) {
  return asNumber(value).toLocaleString('zh-CN')
}

export default function DashboardPage({ projectKey, variant = 'dashboard' }: DashboardPageProps) {
  const queryClient = useQueryClient()
  const dashboardStats = useQuery({
    queryKey: ['dashboard-stats', projectKey],
    queryFn: getDashboardStats,
    enabled: Boolean(projectKey),
  })

  const docTypeRows = Object.entries(dashboardStats.data?.documents?.type_distribution || {})
  const variantTitle: Record<NonNullable<DashboardPageProps['variant']>, string> = {
    dashboard: '综合数据概览',
    market: '市场视角概览',
    social: '舆情视角概览',
    analysis: '分析视角概览',
    board: '看板视角概览',
  }
  const variantHint: Record<NonNullable<DashboardPageProps['variant']>, string> = {
    dashboard: '跨域总览指标',
    market: '重点关注 market 数据和州覆盖',
    social: '重点关注 social 数据变化',
    analysis: '重点关注分析与提取质量',
    board: '重点关注运营看板关键指标',
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
          <span>文档总数</span>
          <strong>{formatNumber(dashboardStats.data?.documents?.total)}</strong>
          <small>7天新增 {formatNumber(dashboardStats.data?.documents?.recent_7d)}</small>
        </article>
        <article className="kpi-card">
          <span>数据源</span>
          <strong>{formatNumber(dashboardStats.data?.sources?.enabled)}</strong>
          <small>总计 {formatNumber(dashboardStats.data?.sources?.total)}</small>
        </article>
        <article className="kpi-card">
          <span>市场数据</span>
          <strong>{formatNumber(dashboardStats.data?.market_stats?.total)}</strong>
          <small>覆盖州 {formatNumber(dashboardStats.data?.market_stats?.states_count)}</small>
        </article>
        <article className="kpi-card">
          <span>任务运行</span>
          <strong>{formatNumber(dashboardStats.data?.tasks?.running)}</strong>
          <small>失败 {formatNumber(dashboardStats.data?.tasks?.failed)}</small>
        </article>
      </section>

      <section className="panel">
        <div className="inline-actions">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['dashboard-stats', projectKey] })}
            disabled={dashboardStats.isFetching}
          >
            {dashboardStats.isFetching ? '刷新中...' : '刷新'}
          </button>
        </div>

        <p className="status-line">今日文档新增: {formatNumber(dashboardStats.data?.documents?.recent_today)}</p>
        <p className="status-line">任务总量: {formatNumber(dashboardStats.data?.tasks?.total)}</p>
        <p className="status-line">任务完成: {formatNumber(dashboardStats.data?.tasks?.completed)}</p>
        <p className="status-line">结构化提取率: {asNumber(dashboardStats.data?.documents?.extraction_rate)}%</p>
        {dashboardStats.isError ? <p className="status-line">看板加载失败，请稍后重试</p> : null}
      </section>

      <section className="panel">
        <p className="status-line">文档类型分布</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>类型</th>
                <th>数量</th>
              </tr>
            </thead>
            <tbody>
              {docTypeRows.map(([type, count]) => (
                <tr key={type}>
                  <td>{type || '-'}</td>
                  <td>{formatNumber(count)}</td>
                </tr>
              ))}
              {!docTypeRows.length ? (
                <tr>
                  <td colSpan={2} className="empty-cell">
                    暂无分布数据
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
