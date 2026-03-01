import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, LoaderCircle, Play, Radar, RefreshCw, Save, Search } from 'lucide-react'
import {
  bindSiteEntry,
  discoverSiteEntriesAdvanced,
  extractResourcePoolFromDocuments,
  listResourcePoolUrlsWithFilters,
  listSourceLibraryChannels,
  listSourceLibraryItemsGrouped,
  listSourceLibraryItemsWithScope,
  listSiteEntriesWithFilters,
  refreshSourceLibraryItem,
  recommendSiteEntriesBatch,
  recommendSiteEntry,
  simplifySiteEntries,
  syncSourceLibraryHandlerClusters,
  upsertSourceLibraryItem,
  upsertSiteEntry,
} from '../lib/api'
import type {
  ResourcePoolRecommendationItem,
  ResourcePoolRecommendationResponse,
  SourceLibraryItem,
  SourceLibraryScope,
} from '../lib/types'

type ResourcePageProps = {
  projectKey: string
  variant?: 'resource' | 'extract'
}

function splitToList(raw: string) {
  return raw
    .split(/\r?\n|,/)
    .map((v) => v.trim())
    .filter(Boolean)
}

function getItemSiteEntries(item: SourceLibraryItem) {
  const params = item.params && typeof item.params === 'object' ? item.params : {}
  const raw = (params.site_entries ?? params.site_entry_urls) as unknown
  if (Array.isArray(raw)) {
    return raw
      .map((entry) => {
        if (typeof entry === 'string') return entry.trim()
        if (entry && typeof entry === 'object') {
          const row = entry as Record<string, unknown>
          return String(row.site_url || row.url || '').trim()
        }
        return ''
      })
      .filter(Boolean)
  }
  if (typeof raw === 'string' && raw.trim()) return [raw.trim()]
  return []
}

function getItemUrlCount(item: SourceLibraryItem) {
  const maybe = (item as unknown as Record<string, unknown>).url_count
  if (typeof maybe === 'number' && Number.isFinite(maybe)) return maybe
  return getItemSiteEntries(item).length
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
}

function renderUrlFold(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw) return '-'
  if (raw.length <= 72) return raw
  const short = `${raw.slice(0, 48)}...${raw.slice(-16)}`
  return (
    <details>
      <summary title={raw} style={{ cursor: 'pointer' }}>
        {short}
      </summary>
      <div style={{ marginTop: 6, wordBreak: 'break-all' }}>{raw}</div>
    </details>
  )
}

export function ResourcePage({ projectKey, variant = 'resource' }: ResourcePageProps) {
  const queryClient = useQueryClient()

  const [sourceScope, setSourceScope] = useState<SourceLibraryScope>('effective')
  const [handlerSearch, setHandlerSearch] = useState('')
  const [itemForm, setItemForm] = useState({
    item_key: '',
    name: '',
    channel_key: '',
    extends_item_key: '',
    tags: '',
    description: '',
    enabled: true,
    site_entries: '',
  })
  const [itemParamsSnapshot, setItemParamsSnapshot] = useState<Record<string, unknown>>({})
  const [itemExtraSnapshot, setItemExtraSnapshot] = useState<Record<string, unknown>>({})

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

  const sourceItems = useQuery({
    queryKey: ['source-items', projectKey, sourceScope],
    queryFn: () => listSourceLibraryItemsWithScope(sourceScope),
    enabled: Boolean(projectKey),
  })

  const sourceItemsGrouped = useQuery({
    queryKey: ['source-items-grouped', projectKey, sourceScope],
    queryFn: () => listSourceLibraryItemsGrouped(sourceScope),
    enabled: Boolean(projectKey),
  })

  const sourceChannels = useQuery({
    queryKey: ['source-channels', projectKey, sourceScope],
    queryFn: () => listSourceLibraryChannels(sourceScope),
    enabled: Boolean(projectKey),
  })

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
      const details = [
        'task_id',
        'item_key',
        'handler_key',
        'handler_count',
        'written',
        'inserted',
        'updated',
        'skipped',
        'added',
        'site_entries_after',
        'errors',
      ]
        .filter((key) => payload[key] !== undefined && payload[key] !== null && payload[key] !== '')
        .map((key) => `${key}=${String(payload[key])}`)
        .join(' | ')

      setActionMessage(details ? `${name} 完成: ${details}` : `${name} 执行完成`)

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['resource-urls', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['site-entries', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['source-items', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['source-items-grouped', projectKey] }),
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

  const fillItemForm = (item: SourceLibraryItem) => {
    const tags = Array.isArray(item.tags) ? item.tags.filter(Boolean) : []
    const params = item.params && typeof item.params === 'object' ? item.params : {}
    const extra = item.extra && typeof item.extra === 'object' ? item.extra : {}
    const siteEntries = getItemSiteEntries(item)
    setItemForm({
      item_key: item.item_key || '',
      name: item.name || item.item_key || '',
      channel_key: item.channel_key || '',
      extends_item_key: item.extends_item_key || '',
      tags: tags.join('\n'),
      description: item.description || '',
      enabled: item.enabled !== false,
      site_entries: siteEntries.join('\n'),
    })
    setItemParamsSnapshot(params)
    setItemExtraSnapshot(extra)
  }

  const saveSourceItem = async () => {
    const itemKey = itemForm.item_key.trim()
    const name = itemForm.name.trim()
    const channelKey = itemForm.channel_key.trim()
    if (!itemKey || !name || !channelKey) {
      throw new Error('item_key / name / channel_key 不能为空')
    }
    const nextParams = { ...itemParamsSnapshot }
    nextParams.site_entries = itemForm.site_entries
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
    delete (nextParams as Record<string, unknown>).site_entry_urls

    return upsertSourceLibraryItem({
      item_key: itemKey,
      name,
      channel_key: channelKey,
      description: itemForm.description.trim() || undefined,
      params: nextParams,
      tags: splitToList(itemForm.tags),
      extends_item_key: itemForm.extends_item_key.trim() || undefined,
      enabled: itemForm.enabled,
      extra: itemExtraSnapshot || {},
    })
  }

  const syncAndRefreshHandlerItem = async (item: SourceLibraryItem, handlerKey: string) => {
    if (!item?.item_key) throw new Error('item_key 不能为空')
    if (!handlerKey || handlerKey === 'url_routing') throw new Error('仅支持 entry_type handler（不支持 url_routing）')

    const rawParams = item.params && typeof item.params === 'object' ? { ...item.params } : {}
    rawParams.site_entries = getItemSiteEntries(item)
    delete (rawParams as Record<string, unknown>).site_entry_urls
    const rawExtra = item.extra && typeof item.extra === 'object' ? { ...item.extra } : {}
    rawExtra.creation_handler = 'handler.entry_type'
    rawExtra.expected_entry_type = handlerKey
    if (rawExtra.auto_maintain == null) rawExtra.auto_maintain = true

    await upsertSourceLibraryItem({
      item_key: item.item_key,
      name: item.name || item.item_key,
      channel_key: item.channel_key || 'handler.cluster',
      description: item.description || undefined,
      params: rawParams,
      tags: Array.isArray(item.tags) ? item.tags : [],
      schedule: item.schedule || undefined,
      extends_item_key: item.extends_item_key || undefined,
      enabled: item.enabled !== false,
      extra: rawExtra,
    })

    const refreshed = await refreshSourceLibraryItem(item.item_key, {
      incremental: true,
      max_site_entries: 500,
    })
    return {
      ...refreshed,
      item_key: item.item_key,
      handler_key: handlerKey,
    }
  }

  const handlerBuckets = useMemo(() => {
    const byHandler = sourceItemsGrouped.data?.by_handler || {}
    const keyword = handlerSearch.trim().toLowerCase()
    return Object.keys(byHandler)
      .sort()
      .map((handlerKey) => {
        const list = Array.isArray(byHandler[handlerKey]) ? byHandler[handlerKey] : []
        if (!keyword) return { handlerKey, total: list.length, items: list }
        const filtered = list.filter((item) => {
          const haystack = `${handlerKey} ${item.item_key || ''} ${item.name || ''} ${item.channel_key || ''}`.toLowerCase()
          return haystack.includes(keyword)
        })
        if (String(handlerKey).toLowerCase().includes(keyword)) {
          return { handlerKey, total: list.length, items: list }
        }
        if (!filtered.length) return null
        return { handlerKey, total: list.length, items: filtered }
      })
      .filter(Boolean) as Array<{ handlerKey: string; total: number; items: SourceLibraryItem[] }>
  }, [sourceItemsGrouped.data, handlerSearch])

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
                queryClient.invalidateQueries({ queryKey: ['source-items', projectKey] })
                queryClient.invalidateQueries({ queryKey: ['source-items-grouped', projectKey] })
                queryClient.invalidateQueries({ queryKey: ['source-channels', projectKey] })
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
          <h2>信息源库 Items 列表</h2>
          <div className="inline-actions">
            <label>
              <span>scope</span>
              <select value={sourceScope} onChange={(e) => setSourceScope(e.target.value as SourceLibraryScope)}>
                <option value="effective">effective</option>
                <option value="shared">shared</option>
                <option value="project">project</option>
              </select>
            </label>
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: ['source-items', projectKey] })
                queryClient.invalidateQueries({ queryKey: ['source-items-grouped', projectKey] })
                queryClient.invalidateQueries({ queryKey: ['source-channels', projectKey] })
              }}
            >
              <RefreshCw size={14} />刷新 items
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>item_key</th>
                <th>name</th>
                <th>channel_key</th>
                <th>scope</th>
                <th>url_count</th>
                <th>enabled</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {(sourceItems.data || []).map((item) => (
                <tr key={item.item_key}>
                  <td>{item.item_key || '-'}</td>
                  <td>{item.name || '-'}</td>
                  <td>{item.channel_key || '-'}</td>
                  <td>{item.scope || '-'}</td>
                  <td>{getItemUrlCount(item)}</td>
                  <td>{String(item.enabled !== false)}</td>
                  <td>
                    <button onClick={() => fillItemForm(item)}>编辑</button>
                  </td>
                </tr>
              ))}
              {!sourceItems.data?.length ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    暂无 items
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>来源项编辑</h2>
          <div className="inline-actions">
            <button disabled={actionPending} onClick={() => void runAction('保存来源项', saveSourceItem)}>
              <Save size={14} />保存
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>item_key</span>
            <input value={itemForm.item_key} onChange={(e) => setItemForm((p) => ({ ...p, item_key: e.target.value }))} placeholder="handler.cluster.rss" />
          </label>
          <label>
            <span>name</span>
            <input value={itemForm.name} onChange={(e) => setItemForm((p) => ({ ...p, name: e.target.value }))} placeholder="Handler Cluster rss" />
          </label>
          <label>
            <span>channel_key</span>
            <input
              list="source-channel-options"
              value={itemForm.channel_key}
              onChange={(e) => setItemForm((p) => ({ ...p, channel_key: e.target.value }))}
              placeholder="handler.cluster / url_pool"
            />
            <datalist id="source-channel-options">
              {(sourceChannels.data || []).map((channel) => (
                <option key={channel.channel_key} value={channel.channel_key} />
              ))}
            </datalist>
          </label>
          <label>
            <span>extends_item_key</span>
            <input
              value={itemForm.extends_item_key}
              onChange={(e) => setItemForm((p) => ({ ...p, extends_item_key: e.target.value }))}
              placeholder="可选"
            />
          </label>
          <label>
            <span>enabled</span>
            <select
              value={itemForm.enabled ? 'true' : 'false'}
              onChange={(e) => setItemForm((p) => ({ ...p, enabled: e.target.value === 'true' }))}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label>
            <span>tags（多行或逗号）</span>
            <textarea
              rows={4}
              value={itemForm.tags}
              onChange={(e) => setItemForm((p) => ({ ...p, tags: e.target.value }))}
              placeholder="tag1&#10;tag2"
            />
          </label>
          <label>
            <span>description</span>
            <textarea
              rows={4}
              value={itemForm.description}
              onChange={(e) => setItemForm((p) => ({ ...p, description: e.target.value }))}
              placeholder="描述"
            />
          </label>
          <label>
            <span>site_entries（每行一个 URL）</span>
            <textarea
              rows={7}
              value={itemForm.site_entries}
              onChange={(e) => setItemForm((p) => ({ ...p, site_entries: e.target.value }))}
              placeholder="https://example.com&#10;https://example.org/rss"
            />
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Handler 聚类（by_handler）</h2>
          <div className="inline-actions">
            <label>
              <span>搜索</span>
              <input
                value={handlerSearch}
                onChange={(e) => setHandlerSearch(e.target.value)}
                placeholder="handler / item_key / name / channel"
              />
            </label>
            <button
              disabled={actionPending}
              onClick={() =>
                void runAction('生成/更新全部 handler 聚类', () =>
                  syncSourceLibraryHandlerClusters({
                    incremental: true,
                    max_site_entries: 500,
                  }),
                )
              }
            >
              <Database size={14} />一键生成/更新
            </button>
            <button onClick={() => void sourceItemsGrouped.refetch()}>
              <RefreshCw size={14} />刷新聚类
            </button>
          </div>
        </div>
        {handlerBuckets.map((bucket) => (
          <div className="table-wrap" key={bucket.handlerKey} style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th colSpan={5}>
                    <code>{bucket.handlerKey}</code> ({bucket.items.length}/{bucket.total})
                  </th>
                </tr>
                <tr>
                  <th>item_key</th>
                  <th>name</th>
                  <th>channel_key</th>
                  <th>enabled</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {bucket.items.map((item) => (
                  <tr key={`${bucket.handlerKey}-${item.item_key}`}>
                    <td>{item.item_key || '-'}</td>
                    <td>{item.name || '-'}</td>
                    <td>{item.channel_key || '-'}</td>
                    <td>{String(item.enabled !== false)}</td>
                    <td>
                      <div className="inline-actions">
                        <button onClick={() => fillItemForm(item)}>定位</button>
                        <button
                          disabled={actionPending}
                          onClick={() => void runAction('同步并刷新 handler item', () => syncAndRefreshHandlerItem(item, bucket.handlerKey))}
                        >
                          同步并刷新
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!bucket.items.length ? (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      无匹配结果
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ))}
        {!handlerBuckets.length ? <p className="status-line"><Search size={14} />暂无 handler 聚类数据</p> : null}
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
                    <td>{renderUrlFold(item.site_url)}</td>
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
                    <td>{renderUrlFold(item.url)}</td>
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
                    <td>{renderUrlFold(item.site_url)}</td>
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
