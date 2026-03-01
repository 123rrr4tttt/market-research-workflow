import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, RefreshCw } from 'lucide-react'
import { getPolicyDetail, getPolicyStats, listPolicies } from '../lib/api'

export type PolicyPageProps = {
  projectKey: string
  variant?: 'policy' | 'policyGraph'
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleDateString('zh-CN')
}

function statusClass(status?: string | null) {
  const key = String(status || '').toLowerCase()
  if (key.includes('active') || key.includes('effective') || key.includes('valid')) return 'chip chip-ok'
  if (key.includes('draft') || key.includes('pending') || key.includes('review')) return 'chip chip-warn'
  if (key.includes('expire') || key.includes('invalid') || key.includes('suspend')) return 'chip chip-danger'
  return 'chip'
}

export function PolicyPage({ projectKey, variant = 'policy' }: PolicyPageProps) {
  const queryClient = useQueryClient()

  const [policyStateFilter, setPolicyStateFilter] = useState('')
  const [policyPage, setPolicyPage] = useState(1)
  const [selectedPolicyIdState, setSelectedPolicyIdState] = useState<number | null>(null)

  const policyStats = useQuery({
    queryKey: ['policy-stats', projectKey],
    queryFn: getPolicyStats,
    enabled: Boolean(projectKey),
  })

  const policyList = useQuery({
    queryKey: ['policy-list', projectKey, policyStateFilter, policyPage],
    queryFn: () => listPolicies(policyStateFilter, policyPage, 12),
    enabled: Boolean(projectKey),
  })

  const selectedPolicyId = useMemo(() => {
    const items = policyList.data || []
    if (!items.length) return null
    if (selectedPolicyIdState != null && items.some((item) => item.id === selectedPolicyIdState)) {
      return selectedPolicyIdState
    }
    return items[0].id
  }, [policyList.data, selectedPolicyIdState])

  const policyDetail = useQuery({
    queryKey: ['policy-detail', projectKey, selectedPolicyId],
    queryFn: () => getPolicyDetail(Number(selectedPolicyId)),
    enabled: Boolean(projectKey) && selectedPolicyId != null,
  })

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

    return options.sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [policyStats.data?.state_distribution])

  const activePolicy = policyDetail.data

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['policy-stats', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['policy-list', projectKey] }),
      queryClient.invalidateQueries({ queryKey: ['policy-detail', projectKey] }),
    ])
  }

  const isRefreshing = policyStats.isFetching || policyList.isFetching || policyDetail.isFetching

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'policyGraph' ? '政策图谱视角' : '政策数据视角'}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card">
          <span>政策总数</span>
          <strong>{policyStats.data?.total_policies || 0}</strong>
          <small>当前项目</small>
        </article>
        <article className="kpi-card">
          <span>覆盖省份</span>
          <strong>{policyStats.data?.state_distribution?.length || 0}</strong>
          <small>state_distribution</small>
        </article>
        <article className="kpi-card">
          <span>政策类型</span>
          <strong>{policyStats.data?.type_distribution?.length || 0}</strong>
          <small>type_distribution</small>
        </article>
        <article className="kpi-card">
          <span>状态分类</span>
          <strong>{policyStats.data?.status_distribution?.length || 0}</strong>
          <small>status_distribution</small>
        </article>
      </section>

      <section className="panel two-col">
        <div>
          <div className="panel-header">
            <h2>
              <Database size={15} />
              政策列表
            </h2>
            <div className="inline-actions">
              <button onClick={() => void refreshAll()} disabled={isRefreshing}>
                <RefreshCw size={14} />
                {isRefreshing ? '刷新中...' : '刷新'}
              </button>
            </div>
          </div>

          <div className="form-grid cols-2" style={{ marginBottom: 12 }}>
            <label>
              <span>省份筛选</span>
              <select
                value={policyStateFilter}
                onChange={(e) => {
                  setPolicyStateFilter(e.target.value)
                  setPolicyPage(1)
                  setSelectedPolicyIdState(null)
                }}
              >
                <option value="">全部</option>
                {stateOptions.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>
            <div className="inline-actions" style={{ alignItems: 'end' }}>
              <button
                disabled={policyPage <= 1}
                onClick={() => {
                  setPolicyPage((p) => Math.max(1, p - 1))
                  setSelectedPolicyIdState(null)
                }}
              >
                上一页
              </button>
              <span className="chip">第 {policyPage} 页</span>
              <button
                onClick={() => {
                  setPolicyPage((p) => p + 1)
                  setSelectedPolicyIdState(null)
                }}
              >
                下一页
              </button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>标题</th>
                  <th>省份</th>
                  <th>状态</th>
                  <th>发布日期</th>
                </tr>
              </thead>
              <tbody>
                {(policyList.data || []).map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => setSelectedPolicyIdState(item.id)}
                    style={{ cursor: 'pointer', background: selectedPolicyId === item.id ? 'rgba(59, 130, 246, 0.1)' : undefined }}
                  >
                    <td>{item.id}</td>
                    <td>{item.title || '-'}</td>
                    <td>{item.state || '-'}</td>
                    <td>
                      <span className={statusClass(item.status)}>{item.status || '-'}</span>
                    </td>
                    <td>{formatDate(item.publish_date)}</td>
                  </tr>
                ))}
                {!policyList.data?.length ? (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      暂无政策数据
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header">
            <h2>政策详情</h2>
            <span className="chip">{activePolicy?.id ? `ID: ${activePolicy.id}` : '未选择'}</span>
          </div>

          {selectedPolicyId == null ? <p className="empty-cell">请先在左侧选择一条政策</p> : null}

          {selectedPolicyId != null ? (
            <div className="content-stack" style={{ gap: 10 }}>
              <article className="panel" style={{ padding: 12 }}>
                <div className="form-grid cols-2">
                  <div>
                    <strong>标题</strong>
                    <p>{activePolicy?.title || '-'}</p>
                  </div>
                  <div>
                    <strong>政策类型</strong>
                    <p>{activePolicy?.policy_type || '-'}</p>
                  </div>
                  <div>
                    <strong>省份</strong>
                    <p>{activePolicy?.state || '-'}</p>
                  </div>
                  <div>
                    <strong>状态</strong>
                    <p>
                      <span className={statusClass(activePolicy?.status)}>{activePolicy?.status || '-'}</span>
                    </p>
                  </div>
                  <div>
                    <strong>发布日期</strong>
                    <p>{formatDate(activePolicy?.publish_date)}</p>
                  </div>
                  <div>
                    <strong>生效日期</strong>
                    <p>{formatDate(activePolicy?.effective_date)}</p>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <strong>来源链接</strong>
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
                <h3>要点</h3>
                <ul>
                  {(activePolicy?.key_points || []).length ? (
                    (activePolicy?.key_points || []).map((point, idx) => <li key={`${idx}-${point}`}>{point}</li>)
                  ) : (
                    <li>-</li>
                  )}
                </ul>
              </article>

              <article className="panel" style={{ padding: 12 }}>
                <h3>摘要</h3>
                <p>{activePolicy?.summary || '-'}</p>
              </article>

              <article className="panel" style={{ padding: 12 }}>
                <h3>正文</h3>
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
