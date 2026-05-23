import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, RefreshCw } from 'lucide-react'
import { translate, useAppLocale, type AppLocale } from '../app/platform/i18n'
import { getPolicyDetail, getPolicyStats, getPromptTimeDensityPriority, listPolicies } from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

export type PolicyPageProps = {
  projectKey: string
  variant?: 'policy' | 'policyGraph'
}

type PromptDensityRow = {
  rank?: number | string | null
  source_domain?: string | null
  prompt_group_id?: string | null
  window?: string | null
  norm_density?: number | string | null
  dup_ratio?: number | string | null
}

type PolicyMessageKey = Parameters<typeof translate>[1]

function formatDate(value: string | null | undefined, locale: AppLocale) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleDateString(locale)
}

function formatPolicyTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function statusClass(status?: string | null) {
  const key = String(status || '').toLowerCase()
  if (key.includes('active') || key.includes('effective') || key.includes('valid')) return 'chip chip-ok'
  if (key.includes('draft') || key.includes('pending') || key.includes('review')) return 'chip chip-warn'
  if (key.includes('expire') || key.includes('invalid') || key.includes('suspend')) return 'chip chip-danger'
  return 'chip'
}

export function PolicyPage({ projectKey, variant = 'policy' }: PolicyPageProps) {
  const locale = useAppLocale()
  const t = (key: PolicyMessageKey, fallback?: string) => translate(locale, key, fallback)
  const formatTemplate = (key: PolicyMessageKey, values: Record<string, string | number>) =>
    formatPolicyTemplate(t(key), values)
  const queryClient = useQueryClient()

  const [policyStateFilter, setPolicyStateFilter] = useState('')
  const [policyPage, setPolicyPage] = useState(1)
  const [selectedPolicyId, setSelectedPolicyId] = useState<number | null>(null)
  const [densityPromptGroupId, setDensityPromptGroupId] = useState('')
  const [densityTimeWindow, setDensityTimeWindow] = useState('30d')

  const policyStats = useQuery({
    queryKey: queryKeys.policy.stats(projectKey),
    queryFn: getPolicyStats,
    enabled: Boolean(projectKey),
  })

  const policyList = useQuery({
    queryKey: queryKeys.policy.list(projectKey, policyStateFilter, policyPage),
    queryFn: () => listPolicies(policyStateFilter, policyPage, 12),
    enabled: Boolean(projectKey),
  })

  const effectiveSelectedPolicyId = useMemo(() => {
    const items = policyList.data || []
    if (!items.length) return null
    if (selectedPolicyId != null && items.some((item) => item.id === selectedPolicyId)) return selectedPolicyId
    return items[0].id
  }, [policyList.data, selectedPolicyId])

  const policyDetail = useQuery({
    queryKey: queryKeys.policy.detail(projectKey, effectiveSelectedPolicyId),
    queryFn: () => getPolicyDetail(Number(effectiveSelectedPolicyId)),
    enabled: Boolean(projectKey) && effectiveSelectedPolicyId != null,
  })

  const normalizedDensityTimeWindow = useMemo(() => {
    const raw = String(densityTimeWindow || '').trim().toLowerCase()
    return /^\d+d$/.test(raw) ? raw : '30d'
  }, [densityTimeWindow])

  const promptDensityPriority = useQuery({
    queryKey: queryKeys.stats.promptTimeDensityPriority(
      projectKey,
      normalizedDensityTimeWindow,
      densityPromptGroupId.trim(),
      true,
    ),
    queryFn: () =>
      getPromptTimeDensityPriority({
        candidate_windows: [normalizedDensityTimeWindow],
        prompt_group_ids: densityPromptGroupId.trim() ? [densityPromptGroupId.trim()] : [],
        prefer_low_density: true,
        exclude_high_dup: true,
      }),
    enabled: Boolean(projectKey),
  })
  const promptDensityRows = useMemo(
    () => (((promptDensityPriority.data as { items?: PromptDensityRow[] } | undefined)?.items) || []).slice(0, 5),
    [promptDensityPriority.data],
  )

  const stateOptions = useMemo(() => {
    const items = policyStats.data?.state_distribution || []
    const unique = new Set<string>()
    const options: string[] = []

    items.forEach((row) => {
      const state = String(row.state || '').trim()
      if (!state || unique.has(state)) return
      unique.add(state)
      options.push(state)
    })

    return options.sort((a, b) => a.localeCompare(b, locale))
  }, [locale, policyStats.data?.state_distribution])

  const activePolicy = policyDetail.data

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.policy.stats(projectKey) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.policy.listBase(projectKey) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.policy.detailBase(projectKey) }),
    ])
  }

  const isRefreshing = policyStats.isFetching || policyList.isFetching || policyDetail.isFetching

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{t(variant === 'policyGraph' ? 'policyPage.title.policyGraph' : 'policyPage.title.policy')}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card">
          <span>{t('policyPage.kpi.totalPolicies')}</span>
          <strong>{policyStats.data?.total_policies || 0}</strong>
          <small>{t('policyPage.kpi.currentProject')}</small>
        </article>
        <article className="kpi-card">
          <span>{t('policyPage.kpi.coveredStates')}</span>
          <strong>{policyStats.data?.state_distribution?.length || 0}</strong>
          <small>state_distribution</small>
        </article>
        <article className="kpi-card">
          <span>{t('policyPage.kpi.policyTypes')}</span>
          <strong>{policyStats.data?.type_distribution?.length || 0}</strong>
          <small>type_distribution</small>
        </article>
        <article className="kpi-card">
          <span>{t('policyPage.kpi.statusCategories')}</span>
          <strong>{policyStats.data?.status_distribution?.length || 0}</strong>
          <small>status_distribution</small>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('policyPage.section.promptDensity')}</h2>
        </div>
        <div className="form-grid cols-2" style={{ marginBottom: 12 }}>
          <label>
            <span>{t('policyPage.field.promptGroupId')}</span>
            <input
              value={densityPromptGroupId}
              placeholder={t('policyPage.placeholder.promptGroupId')}
              onChange={(e) => setDensityPromptGroupId(e.target.value)}
            />
          </label>
          <label>
            <span>{t('policyPage.field.timeWindow')}</span>
            <input
              value={densityTimeWindow}
              placeholder={t('policyPage.placeholder.timeWindow')}
              onChange={(e) => setDensityTimeWindow(e.target.value)}
            />
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('policyPage.field.rank')}</th>
                <th>{t('policyPage.field.domain')}</th>
                <th>{t('policyPage.field.promptGroup')}</th>
                <th>{t('policyPage.field.window')}</th>
                <th>{t('policyPage.field.normDensity')}</th>
                <th>{t('policyPage.field.dupRatio')}</th>
              </tr>
            </thead>
            <tbody>
              {promptDensityRows.map((item) => (
                <tr key={`${item.rank}-${item.source_domain}-${item.prompt_group_id}-${item.window}`}>
                  <td>{item.rank}</td>
                  <td>{item.source_domain}</td>
                  <td>{item.prompt_group_id}</td>
                  <td>{item.window}</td>
                  <td>{Number(item.norm_density || 0).toFixed(4)}</td>
                  <td>{Number(item.dup_ratio || 0).toFixed(4)}</td>
                </tr>
              ))}
              {!promptDensityRows.length ? (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    {t('policyPage.empty.promptDensity')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel two-col">
        <div>
          <div className="panel-header">
            <h2>
              <Database size={15} />
              {t('policyPage.section.policyList')}
            </h2>
            <div className="inline-actions">
              <button onClick={() => void refreshAll()} disabled={isRefreshing}>
                <RefreshCw size={14} />
                {isRefreshing ? t('policyPage.action.refreshing') : t('policyPage.action.refresh')}
              </button>
            </div>
          </div>

          <div className="form-grid cols-2" style={{ marginBottom: 12 }}>
            <label>
              <span>{t('policyPage.field.stateFilter')}</span>
              <select
                value={policyStateFilter}
                onChange={(e) => {
                  setPolicyStateFilter(e.target.value)
                  setPolicyPage(1)
                }}
              >
                <option value="">{t('policyPage.option.all')}</option>
                {stateOptions.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>
            <div className="inline-actions" style={{ alignItems: 'end' }}>
              <button disabled={policyPage <= 1} onClick={() => setPolicyPage((p) => Math.max(1, p - 1))}>
                {t('policyPage.action.previousPage')}
              </button>
              <span className="chip">{formatTemplate('policyPage.status.page', { page: policyPage })}</span>
              <button onClick={() => setPolicyPage((p) => p + 1)}>{t('policyPage.action.nextPage')}</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
              <tr>
                  <th>{t('policyPage.field.id')}</th>
                  <th>{t('policyPage.field.title')}</th>
                  <th>{t('policyPage.field.state')}</th>
                  <th>{t('policyPage.field.status')}</th>
                  <th>{t('policyPage.field.publishDate')}</th>
              </tr>
              </thead>
              <tbody>
                {(policyList.data || []).map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => setSelectedPolicyId(item.id)}
                    style={{ cursor: 'pointer', background: effectiveSelectedPolicyId === item.id ? '#eff6ff' : undefined }}
                  >
                    <td>{item.id}</td>
                    <td>{item.title || '-'}</td>
                    <td>{item.state || '-'}</td>
                    <td>
                      <span className={statusClass(item.status)}>{item.status || '-'}</span>
                    </td>
                    <td>{formatDate(item.publish_date, locale)}</td>
                  </tr>
                ))}
                {!policyList.data?.length ? (
                  <tr>
                  <td colSpan={5} className="empty-cell">
                      {t('policyPage.empty.policies')}
                  </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header">
            <h2>{t('policyPage.section.policyDetail')}</h2>
            <span className="chip">
              {activePolicy?.id ? formatTemplate('policyPage.status.selectedId', { id: activePolicy.id }) : t('policyPage.status.unselected')}
            </span>
          </div>

          {effectiveSelectedPolicyId == null ? <p className="empty-cell">{t('policyPage.empty.selectPolicy')}</p> : null}

          {effectiveSelectedPolicyId != null ? (
            <div className="content-stack" style={{ gap: 10 }}>
              <article className="panel" style={{ padding: 12 }}>
                <div className="form-grid cols-2">
                  <div>
                    <strong>{t('policyPage.field.title')}</strong>
                    <p>{activePolicy?.title || '-'}</p>
                  </div>
                  <div>
                    <strong>{t('policyPage.field.policyType')}</strong>
                    <p>{activePolicy?.policy_type || '-'}</p>
                  </div>
                  <div>
                    <strong>{t('policyPage.field.state')}</strong>
                    <p>{activePolicy?.state || '-'}</p>
                  </div>
                  <div>
                    <strong>{t('policyPage.field.status')}</strong>
                    <p>
                      <span className={statusClass(activePolicy?.status)}>{activePolicy?.status || '-'}</span>
                    </p>
                  </div>
                  <div>
                    <strong>{t('policyPage.field.publishDate')}</strong>
                    <p>{formatDate(activePolicy?.publish_date, locale)}</p>
                  </div>
                  <div>
                    <strong>{t('policyPage.field.effectiveDate')}</strong>
                    <p>{formatDate(activePolicy?.effective_date, locale)}</p>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <strong>{t('policyPage.field.sourceUri')}</strong>
                    <p>
                      {activePolicy?.uri ? (
                        <a href={activePolicy.uri} target="_blank" rel="noreferrer">
                          {activePolicy.uri}
                        </a>
                      ) : (
                        '-'
                      )}
                    </p>
                  </div>
                </div>
              </article>

              <article className="panel" style={{ padding: 12 }}>
                <h3>{t('policyPage.field.keyPoints')}</h3>
                <ul>
                  {(activePolicy?.key_points || []).length ? (
                    (activePolicy?.key_points || []).map((point, idx) => <li key={`${idx}-${point}`}>{point}</li>)
                  ) : (
                    <li>-</li>
                  )}
                </ul>
              </article>

              <article className="panel" style={{ padding: 12 }}>
                <h3>{t('policyPage.field.summary')}</h3>
                <p>{activePolicy?.summary || '-'}</p>
              </article>

              <article className="panel" style={{ padding: 12 }}>
                <h3>{t('policyPage.field.content')}</h3>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>{activePolicy?.content || '-'}</pre>
              </article>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  )
}

export default PolicyPage
