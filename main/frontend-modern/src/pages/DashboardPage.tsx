import { useQuery, useQueryClient } from '@tanstack/react-query'
import { translate, useAppLocale } from '../app/platform/i18n'
import { getDashboardStats } from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

type DashboardPageProps = {
  projectKey: string
  variant?: 'dashboard' | 'market' | 'social' | 'analysis' | 'board'
}

type FrontdoorTriStateStatus = 'success' | 'degraded_success' | 'failed'

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

export default function DashboardPage({ projectKey, variant = 'dashboard' }: DashboardPageProps) {
  const locale = useAppLocale()
  const queryClient = useQueryClient()
  const dashboardStats = useQuery({
    queryKey: queryKeys.dashboard.stats(projectKey),
    queryFn: getDashboardStats,
    enabled: Boolean(projectKey),
  })

  const docTypeRows = Object.entries(dashboardStats.data?.documents?.type_distribution || {})
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
