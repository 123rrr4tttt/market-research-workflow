import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, LoaderCircle, Play, Radar, RefreshCw } from 'lucide-react'
import {
  bindSiteEntry,
  discoverSiteEntriesAdvanced,
  extractResourcePoolFromDocuments,
  listResourcePoolUrlsWithFilters,
  listSiteEntriesWithFilters,
  recommendSiteEntriesBatch,
  recommendSiteEntry,
  simplifySiteEntries,
  upsertSiteEntry,
} from '../lib/api'
import type { ResourcePoolRecommendationItem, ResourcePoolRecommendationResponse } from '../lib/types'

type ResourcePageProps = {
  projectKey: string
  variant?: 'resource' | 'extract'
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
}

export function ResourcePage({ projectKey, variant = 'resource' }: ResourcePageProps) {
  const queryClient = useQueryClient()

  const [domainFilter, setDomainFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [entryTypeFilter, setEntryTypeFilter] = useState('')

  const [resourceUrlPage, setResourceUrlPage] = useState(1)
  const [resourceSitePage, setResourceSitePage] = useState(1)

  const [newSiteUrl, setNewSiteUrl] = useState('')
  const [newSiteEntryType, setNewSiteEntryType] = useState('domain_root')

  const [actionPending, setActionPending] = useState(false)
  const [actionMessage, setActionMessage] = useState('等待操作')
  const [actionError, setActionError] = useState('')

  const [discoverLimitDomains, setDiscoverLimitDomains] = useState('60')
  const [discoverDryRun, setDiscoverDryRun] = useState(false)

  const [recommendSiteUrl, setRecommendSiteUrl] = useState('')
  const [recommendEntryType, setRecommendEntryType] = useState('domain_root')
  const [recommendUseLlm, setRecommendUseLlm] = useState(true)
  const [singleRecommendation, setSingleRecommendation] = useState<ResourcePoolRecommendationResponse | null>(null)
  const [batchRecommendations, setBatchRecommendations] = useState<ResourcePoolRecommendationItem[]>([])
  const [bindingPending, setBindingPending] = useState(false)

  useEffect(() => {
    setResourceUrlPage(1)
    setResourceSitePage(1)
  }, [domainFilter, sourceFilter, entryTypeFilter])

  const resourceUrls = useQuery({
    queryKey: ['resource-urls', projectKey, domainFilter, sourceFilter, resourceUrlPage],
    queryFn: () =>
      listResourcePoolUrlsWithFilters({
        page: resourceUrlPage,
        pageSize: 24,
        domain: domainFilter,
        source: sourceFilter,
      }),
    enabled: Boolean(projectKey),
  })

  const siteEntries = useQuery({
    queryKey: ['site-entries', projectKey, domainFilter, entryTypeFilter, resourceSitePage],
    queryFn: () =>
      listSiteEntriesWithFilters({
        page: resourceSitePage,
        pageSize: 24,
        domain: domainFilter,
        entryType: entryTypeFilter,
      }),
    enabled: Boolean(projectKey),
  })

  const siteEntryMutation = useMutation({
    mutationFn: async () => {
      if (!newSiteUrl.trim()) throw new Error('请输入 site_url')
      return upsertSiteEntry({
        site_url: newSiteUrl.trim(),
        entry_type: newSiteEntryType,
        scope: 'project',
      })
    },
    onSuccess: async () => {
      setNewSiteUrl('')
      setActionMessage('新增入口成功')
      await queryClient.invalidateQueries({ queryKey: ['site-entries', projectKey] })
    },
    onError: (error) => {
      setActionMessage(`新增入口失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    setActionPending(true)
    setActionError('')
    setActionMessage(`${name} 执行中...`)
    try {
      const result = await fn()
      const payload = result && typeof result === 'object' ? (result as Record<string, unknown>) : {}
      const details = ['task_id', 'written', 'inserted', 'updated', 'skipped', 'errors']
        .filter((key) => payload[key] !== undefined && payload[key] !== null && payload[key] !== '')
        .map((key) => `${key}=${String(payload[key])}`)
        .join(' | ')

      setActionMessage(details ? `${name} 完成: ${details}` : `${name} 执行完成`)

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['resource-urls', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['site-entries', projectKey] }),
      ])
    } catch (error) {
      const message = error instanceof Error ? error.message : '未知错误'
      setActionMessage(`${name} 失败`)
      setActionError(`${name} 失败: ${message}`)
    } finally {
      setActionPending(false)
    }
  }

  const bindOne = async (item: {
    site_url?: string
    entry_type?: string | null
    template?: string | null
    capabilities?: Record<string, unknown>
    source?: string
  }) => {
    if (!item.site_url) throw new Error('缺少 site_url，无法绑定')
    return bindSiteEntry({
      site_url: item.site_url,
      entry_type: item.entry_type || 'domain_root',
      template: item.template || null,
      capabilities: item.capabilities || {},
      source: item.source || 'recommended',
      source_ref: { action: 'recommend_bind' },
      scope: 'project',
    })
  }

  const bindAllRecommendations = async () => {
    if (!batchRecommendations.length && !singleRecommendation) {
      setActionError('没有可绑定的推荐结果')
      return
    }
    setBindingPending(true)
    setActionError('')
    try {
      const list = batchRecommendations.length
        ? batchRecommendations
        : [
            {
              site_url: recommendSiteUrl.trim(),
              entry_type: singleRecommendation?.entry_type || recommendEntryType,
              template: singleRecommendation?.template || null,
              capabilities: singleRecommendation?.capabilities || {},
              source: singleRecommendation?.source || 'recommended',
            },
          ]
      let success = 0
      let failed = 0
      for (const item of list) {
        try {
          await bindOne(item)
          success += 1
        } catch {
          failed += 1
        }
      }
      setActionMessage(`绑定完成: inserted/updated=${success} | errors=${failed}`)
      await queryClient.invalidateQueries({ queryKey: ['site-entries', projectKey] })
    } catch (error) {
      setActionError(`一键绑定失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setBindingPending(false)
    }
  }

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'extract' ? '提取与资源沉淀' : '信息资源库管理'}</h2>
          <span className="chip">{variant === 'extract' ? 'extract' : 'resource'}</span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>信息资源库管理</h2>
          <span className="chip">项目: {projectKey}</span>
        </div>

        <div className="form-grid cols-4">
          <label>
            <span>domain</span>
            <input
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              placeholder="按域名筛选"
            />
          </label>
          <label>
            <span>source</span>
            <input
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              placeholder="manual/discovered/..."
            />
          </label>
          <label>
            <span>entry_type</span>
            <input
              value={entryTypeFilter}
              onChange={(e) => setEntryTypeFilter(e.target.value)}
              placeholder="domain_root/rss/..."
            />
          </label>
          <div className="inline-actions">
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: ['resource-urls', projectKey] })
                queryClient.invalidateQueries({ queryKey: ['site-entries', projectKey] })
              }}
            >
              <RefreshCw size={14} />刷新列表
            </button>
          </div>
        </div>

        <div className="action-grid">
          <button disabled={actionPending} onClick={() => runAction('从文档提取 URL', () => extractResourcePoolFromDocuments(true))}>
            <Play size={16} />提取 URL
          </button>
          <button
            disabled={actionPending}
            onClick={() =>
              runAction('发现站点入口', () =>
                discoverSiteEntriesAdvanced({
                  limit_domains: Math.max(1, Number.parseInt(discoverLimitDomains, 10) || 60),
                  dry_run: discoverDryRun,
                  write: !discoverDryRun,
                  async_mode: true,
                }),
              )
            }
          >
            <Radar size={16} />发现入口
          </button>
          <button disabled={actionPending} onClick={() => runAction('去重合并站点入口', () => simplifySiteEntries(false))}>
            <RefreshCw size={16} />简化去重
          </button>
        </div>

        <div className="form-grid cols-4" style={{ marginTop: 12 }}>
          <label>
            <span>limit_domains</span>
            <input
              value={discoverLimitDomains}
              onChange={(e) => setDiscoverLimitDomains(e.target.value)}
              placeholder="60"
            />
          </label>
          <label>
            <span>dry_run</span>
            <select value={discoverDryRun ? 'true' : 'false'} onChange={(e) => setDiscoverDryRun(e.target.value === 'true')}>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          </label>
        </div>

        <p className="status-line">{actionPending ? <LoaderCircle size={14} className="spinning" /> : <Play size={14} />}{actionMessage}</p>
        {actionError ? <p className="status-line">失败详情: {actionError}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>站点入口推荐与绑定</h2>
          <div className="inline-actions">
            <button disabled={actionPending || bindingPending} onClick={bindAllRecommendations}>
              <Database size={14} />一键绑定
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>site_url</span>
            <input
              value={recommendSiteUrl}
              onChange={(e) => setRecommendSiteUrl(e.target.value)}
              placeholder="https://example.com"
            />
          </label>
          <label>
            <span>entry_type</span>
            <select value={recommendEntryType} onChange={(e) => setRecommendEntryType(e.target.value)}>
              <option value="domain_root">domain_root</option>
              <option value="rss">rss</option>
              <option value="sitemap">sitemap</option>
              <option value="search_template">search_template</option>
              <option value="official_api">official_api</option>
            </select>
          </label>
          <label>
            <span>use_llm</span>
            <select value={recommendUseLlm ? 'true' : 'false'} onChange={(e) => setRecommendUseLlm(e.target.value === 'true')}>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <div className="inline-actions">
            <button
              disabled={actionPending || !recommendSiteUrl.trim()}
              onClick={() =>
                runAction('单条推荐', async () => {
                  const response = await recommendSiteEntry({
                    site_url: recommendSiteUrl.trim(),
                    entry_type: recommendEntryType,
                    use_llm: recommendUseLlm,
                  })
                  setSingleRecommendation(response)
                  return response
                })
              }
            >
              <Play size={14} />单条推荐
            </button>
            <button
              disabled={actionPending || !(siteEntries.data || []).length}
              onClick={() =>
                runAction('当前页批量推荐', async () => {
                  const response = await recommendSiteEntriesBatch({
                    entries: (siteEntries.data || [])
                      .filter((item) => Boolean(item.site_url))
                      .map((item) => ({
                        site_url: String(item.site_url),
                        entry_type: item.entry_type || null,
                        template: null,
                      })),
                    use_llm: recommendUseLlm,
                  })
                  setBatchRecommendations(response.items || [])
                  return { ...response, written: response.count ?? response.items?.length ?? 0 }
                })
              }
            >
              <Radar size={14} />当前页批量推荐
            </button>
          </div>
        </div>
        {singleRecommendation ? (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>mode</th>
                  <th>entry_type</th>
                  <th>template</th>
                  <th>source</th>
                  <th>validated</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>single</td>
                  <td>{singleRecommendation.entry_type || '-'}</td>
                  <td>{singleRecommendation.template || '-'}</td>
                  <td>{singleRecommendation.source || '-'}</td>
                  <td>{String(singleRecommendation.validated ?? false)}</td>
                  <td>
                    <button
                      disabled={bindingPending || !recommendSiteUrl.trim()}
                      onClick={() =>
                        runAction('绑定单条推荐', () =>
                          bindOne({
                            site_url: recommendSiteUrl.trim(),
                            entry_type: singleRecommendation.entry_type || recommendEntryType,
                            template: singleRecommendation.template || null,
                            capabilities: singleRecommendation.capabilities || {},
                            source: singleRecommendation.source || 'recommended',
                          }),
                        )
                      }
                    >
                      绑定
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : null}
        {batchRecommendations.length ? (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>site_url</th>
                  <th>entry_type</th>
                  <th>template</th>
                  <th>source</th>
                  <th>validated</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {batchRecommendations.map((item, idx) => (
                  <tr key={`${item.site_url || idx}`}>
                    <td>{item.site_url || '-'}</td>
                    <td>{item.entry_type || '-'}</td>
                    <td>{item.template || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{String(item.validated ?? false)}</td>
                    <td>
                      <button disabled={bindingPending || !item.site_url} onClick={() => runAction('绑定批量推荐项', () => bindOne(item))}>
                        绑定
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>手动新增入口</h2>
        </div>
        <div className="form-grid cols-3">
          <label>
            <span>site_url</span>
            <input
              value={newSiteUrl}
              onChange={(e) => setNewSiteUrl(e.target.value)}
              placeholder="https://example.com"
            />
          </label>
          <label>
            <span>entry_type</span>
            <select value={newSiteEntryType} onChange={(e) => setNewSiteEntryType(e.target.value)}>
              <option value="domain_root">domain_root</option>
              <option value="rss">rss</option>
              <option value="sitemap">sitemap</option>
              <option value="search_template">search_template</option>
              <option value="official_api">official_api</option>
            </select>
          </label>
          <div className="inline-actions">
            <button disabled={siteEntryMutation.isPending} onClick={() => siteEntryMutation.mutate()}>
              <Database size={14} />新增入口
            </button>
          </div>
        </div>
      </section>

      <section className="panel two-col">
        <div>
          <div className="panel-header">
            <h2>URL 池</h2>
            <div className="inline-actions">
              <button disabled={resourceUrlPage <= 1} onClick={() => setResourceUrlPage((p) => Math.max(1, p - 1))}>
                上一页
              </button>
              <span className="chip">第 {resourceUrlPage} 页</span>
              <button onClick={() => setResourceUrlPage((p) => p + 1)}>下一页</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>URL</th>
                  <th>domain</th>
                  <th>source</th>
                  <th>created_at</th>
                </tr>
              </thead>
              <tbody>
                {(resourceUrls.data || []).map((item, idx) => (
                  <tr key={`${item.id || item.url || idx}`}>
                    <td>{item.url || '-'}</td>
                    <td>{item.domain || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
                {!resourceUrls.data?.length ? (
                  <tr>
                    <td colSpan={4} className="empty-cell">
                      暂无 URL 数据
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header">
            <h2>Site Entries</h2>
            <div className="inline-actions">
              <button disabled={resourceSitePage <= 1} onClick={() => setResourceSitePage((p) => Math.max(1, p - 1))}>
                上一页
              </button>
              <span className="chip">第 {resourceSitePage} 页</span>
              <button onClick={() => setResourceSitePage((p) => p + 1)}>下一页</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>site_url</th>
                  <th>domain</th>
                  <th>entry_type</th>
                  <th>source</th>
                  <th>enabled</th>
                </tr>
              </thead>
              <tbody>
                {(siteEntries.data || []).map((item, idx) => (
                  <tr key={`${item.id || item.site_url || idx}`}>
                    <td>{item.site_url || '-'}</td>
                    <td>{item.domain || '-'}</td>
                    <td>{item.entry_type || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{String(item.enabled ?? true)}</td>
                  </tr>
                ))}
                {!siteEntries.data?.length ? (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      暂无 Site Entry
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}

export default ResourcePage
