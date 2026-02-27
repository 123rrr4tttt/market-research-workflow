import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, LoaderCircle, Play, Radar, RefreshCw } from 'lucide-react'
import {
  discoverSiteEntries,
  extractResourcePoolFromDocuments,
  listResourcePoolUrlsWithFilters,
  listSiteEntriesWithFilters,
  simplifySiteEntries,
  upsertSiteEntry,
} from '../lib/api'

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
    setActionMessage(`${name} 执行中...`)
    try {
      const result = await fn()
      const taskId =
        result &&
        typeof result === 'object' &&
        'task_id' in result &&
        typeof (result as { task_id?: unknown }).task_id === 'string'
          ? (result as { task_id?: string }).task_id
          : null

      setActionMessage(taskId ? `${name} 已提交，任务 ID: ${taskId}` : `${name} 执行完成`)

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['resource-urls', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['site-entries', projectKey] }),
      ])
    } catch (error) {
      setActionMessage(`${name} 失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setActionPending(false)
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
          <button disabled={actionPending} onClick={() => runAction('发现站点入口', () => discoverSiteEntries(true))}>
            <Radar size={16} />发现入口
          </button>
          <button disabled={actionPending} onClick={() => runAction('去重合并站点入口', () => simplifySiteEntries(false))}>
            <RefreshCw size={16} />简化去重
          </button>
        </div>

        <p className="status-line">{actionPending ? <LoaderCircle size={14} className="spinning" /> : <Play size={14} />}{actionMessage}</p>
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
