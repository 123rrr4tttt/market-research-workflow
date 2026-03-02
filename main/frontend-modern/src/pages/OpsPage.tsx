import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Trash2 } from 'lucide-react'
import Gv2NodeCard from '../components/Gv2NodeCard'
import GraphBusinessCardSections from '../components/GraphBusinessCardSections'
import GraphExtensionsSections from '../components/GraphExtensionsSections'
import type { DocumentItem } from '../lib/types'
import {
  bulkUpdateDocumentExtractedData,
  clearDocumentExtractedData,
  cleanupGovernance,
  getAdminDocument,
  deleteAdminDocuments,
  exportGraph,
  getAdminStats,
  getSearchHistory,
  listAdminDocuments,
  reExtractDocuments,
  syncAggregator,
  topicExtractDocuments,
} from '../lib/api'

type OpsPageProps = {
  projectKey: string
  variant?: 'ops' | 'backend'
}

type OpsCardTab = 'business' | 'graph_ext'

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
}

function toGraphBusinessNode(doc: DocumentItem | undefined, activeDocId: number | null): Record<string, unknown> {
  const extracted = (doc?.extracted_data && typeof doc.extracted_data === 'object' && !Array.isArray(doc.extracted_data))
    ? doc.extracted_data
    : {}
  return {
    ...extracted,
    id: doc?.id ?? activeDocId ?? '-',
    type: doc?.doc_type || String((extracted as Record<string, unknown>).type || 'Document'),
    title: doc?.title || String((extracted as Record<string, unknown>).title || ''),
    name: String(
      (extracted as Record<string, unknown>).name
      || (extracted as Record<string, unknown>).canonical_name
      || '',
    ),
    state: doc?.state || String((extracted as Record<string, unknown>).state || ''),
    status: doc?.status || String((extracted as Record<string, unknown>).status || ''),
    publish_date: doc?.publish_date || String((extracted as Record<string, unknown>).publish_date || ''),
    platform: String((extracted as Record<string, unknown>).platform || ''),
    game: String((extracted as Record<string, unknown>).game || ''),
    policy_type: String((extracted as Record<string, unknown>).policy_type || ''),
    summary: doc?.summary || '',
    content: doc?.content || '',
    extracted_data: extracted,
    text: doc?.summary || doc?.content || '',
  }
}

function normalizeScalar(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function normalizeObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function buildOpsGraphExtension(doc: DocumentItem | undefined, activeDocId: number | null) {
  const node = toGraphBusinessNode(doc, activeDocId)
  const elementGroups = new Map<string, string[]>()
  Object.entries(node).forEach(([key, value]) => {
    if (value == null) return
    if (Array.isArray(value)) {
      const values = value.map((item) => normalizeScalar(item).trim()).filter(Boolean)
      if (!values.length) return
      const bucket = elementGroups.get(key) || []
      elementGroups.set(key, [...bucket, ...values])
      return
    }
    if (typeof value === 'object') {
      const obj = normalizeObject(value)
      const values = Object.entries(obj).map(([k, v]) => `${k}: ${normalizeScalar(v) || '[object]'}`)
      if (!values.length) return
      const bucket = elementGroups.get(key) || []
      elementGroups.set(key, [...bucket, ...values])
      return
    }
    const text = normalizeScalar(value).trim()
    if (!text) return
    const bucket = elementGroups.get(key) || []
    elementGroups.set(key, [...bucket, text])
  })

  const extracted = normalizeObject(doc?.extracted_data)
  const er = normalizeObject(extracted.entities_relations)
  const entities = Array.isArray(er.entities) ? er.entities : []
  const relations = Array.isArray(er.relations) ? er.relations : []

  const entityTypeCount = new Map<string, number>()
  const entityItemsByType = new Map<string, string[]>()
  entities.forEach((item) => {
    const entity = normalizeObject(item)
    const type = String(entity.type || entity.entity_type || entity.category || entity.label || 'Entity')
    const name = String(entity.name || entity.text || entity.value || entity.id || type)
    entityTypeCount.set(type, (entityTypeCount.get(type) || 0) + 1)
    const bucket = entityItemsByType.get(type) || []
    bucket.push(name)
    entityItemsByType.set(type, bucket)
  })

  const relationTypeCount = new Map<string, number>()
  const relationItemsByType = new Map<string, string[]>()
  const relationExamples: string[] = []
  relations.forEach((item) => {
    const relation = normalizeObject(item)
    const relType = String(relation.relation || relation.predicate || relation.type || relation.relation_type || relation.label || 'related_to')
    relationTypeCount.set(relType, (relationTypeCount.get(relType) || 0) + 1)
    const from = String(relation.subject || relation.source || relation.from || relation.head || 'source')
    const to = String(relation.object || relation.target || relation.to || relation.tail || 'target')
    const line = `${from} -${relType}-> ${to}`
    relationExamples.push(line)
    const bucket = relationItemsByType.get(relType) || []
    bucket.push(line)
    relationItemsByType.set(relType, bucket)
  })

  return {
    elementGroups: Array.from(elementGroups.entries())
      .map(([label, values]) => ({
        label,
        items: Array.from(new Set(values)).slice(0, 40).map((value, index) => ({ id: `${label}-${index}-${value}`, value, label })),
      }))
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 20),
    entityTypeItems: Array.from(entityTypeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
      .slice(0, 20),
    relationTypeItems: Array.from(relationTypeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
      .slice(0, 20),
    entityItemsByType: Object.fromEntries(
      Array.from(entityItemsByType.entries()).map(([type, list]) => [type, Array.from(new Set(list)).slice(0, 40)]),
    ) as Record<string, string[]>,
    relationItemsByType: Object.fromEntries(
      Array.from(relationItemsByType.entries()).map(([type, list]) => [type, Array.from(new Set(list)).slice(0, 40)]),
    ) as Record<string, string[]>,
    relationExamples: relationExamples.slice(0, 24),
  }
}

export default function OpsPage({ projectKey, variant = 'ops' }: OpsPageProps) {
  const queryClient = useQueryClient()
  const [retentionDays, setRetentionDays] = useState(90)
  const [pending, setPending] = useState(false)
  const [activeAction, setActiveAction] = useState('')
  const [statusText, setStatusText] = useState('等待操作')
  const [errorText, setErrorText] = useState('')
  const [docIdsText, setDocIdsText] = useState('')
  const [topicScope, setTopicScope] = useState<'all' | 'company' | 'product' | 'operation'>('all')
  const [docPage, setDocPage] = useState(1)
  const [docTypeFilter, setDocTypeFilter] = useState('')
  const [docStateFilter, setDocStateFilter] = useState('')
  const [docSearch, setDocSearch] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<number[]>([])
  const [activeDocCardId, setActiveDocCardId] = useState<number | null>(null)
  const [opsCardTab, setOpsCardTab] = useState<OpsCardTab>('business')
  const [extractMode, setExtractMode] = useState<'replace' | 'merge'>('merge')
  const [extractJsonText, setExtractJsonText] = useState('{}')

  const adminStats = useQuery({ queryKey: ['admin-stats', projectKey], queryFn: getAdminStats, enabled: Boolean(projectKey) })
  const searchHistory = useQuery({ queryKey: ['search-history', projectKey], queryFn: () => getSearchHistory(1, 30), enabled: Boolean(projectKey) })
  const adminDocuments = useQuery({
    queryKey: ['admin-documents', projectKey, docPage, docTypeFilter, docStateFilter, docSearch],
    queryFn: () =>
      listAdminDocuments({
        page: docPage,
        page_size: 20,
        doc_type: docTypeFilter.trim() || null,
        state: docStateFilter.trim() || null,
        search: docSearch.trim() || null,
      }),
    enabled: Boolean(projectKey),
  })
  const activeDocDetail = useQuery({
    queryKey: ['admin-document-detail', projectKey, activeDocCardId],
    queryFn: () => getAdminDocument(Number(activeDocCardId)),
    enabled: Boolean(projectKey && activeDocCardId),
  })

  const selectedCount = selectedDocIds.length
  const selectedCsv = useMemo(() => selectedDocIds.join(','), [selectedDocIds])
  const parsedDocIds = useMemo(() => {
    const tokens = docIdsText
      .split(/[,\s]+/)
      .map((item) => Number.parseInt(item.trim(), 10))
      .filter((item) => Number.isFinite(item) && item > 0)
    return Array.from(new Set(tokens))
  }, [docIdsText])
  const docTotalPages = Math.max(1, Math.ceil((adminDocuments.data?.total || 0) / Math.max(1, adminDocuments.data?.page_size || 20)))
  const graphExtension = useMemo(
    () => buildOpsGraphExtension(activeDocDetail.data, activeDocCardId),
    [activeDocDetail.data, activeDocCardId],
  )

  const toggleDocSelection = (docId: number) => {
    setSelectedDocIds((prev) => (prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]))
  }

  const selectCurrentPage = () => {
    const pageIds = (adminDocuments.data?.items || []).map((item) => item.id)
    setSelectedDocIds(pageIds)
  }

  const runAction = async (
    name: string,
    fn: () => Promise<unknown>,
    options?: { refreshStats?: boolean; refreshSearchHistory?: boolean; refreshDocuments?: boolean },
  ) => {
    setPending(true)
    setActiveAction(name)
    setErrorText('')
    setStatusText(`${name} 执行中...`)
    try {
      const result = await fn()
      const taskId = typeof (result as { task_id?: unknown })?.task_id === 'string' ? String((result as { task_id?: string }).task_id) : ''
      setStatusText(taskId ? `${name} 已提交，任务 ID: ${taskId}` : `${name} 完成`)
      if (options?.refreshStats !== false) {
        await queryClient.invalidateQueries({ queryKey: ['admin-stats', projectKey] })
      }
      if (options?.refreshSearchHistory !== false) {
        await queryClient.invalidateQueries({ queryKey: ['search-history', projectKey] })
      }
      if (options?.refreshDocuments !== false) {
        await queryClient.invalidateQueries({ queryKey: ['admin-documents', projectKey] })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '未知错误'
      setStatusText(`${name} 失败`)
      setErrorText(message)
    } finally {
      setPending(false)
      setActiveAction('')
    }
  }

  return (
    <div className="content-stack gv2-root">
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
          <label>
            <span>doc_ids</span>
            <input type="text" value={docIdsText} onChange={(e) => setDocIdsText(e.target.value)} placeholder="示例: 101,102 103" />
          </label>
          <button
            disabled={!selectedCount}
            onClick={() => setDocIdsText(selectedCsv)}
          >
            使用所选({selectedCount})
          </button>
          <label>
            <span>topic_scope</span>
            <select value={topicScope} onChange={(e) => setTopicScope(e.target.value as 'all' | 'company' | 'product' | 'operation')}>
              <option value="all">all</option>
              <option value="company">company</option>
              <option value="product">product</option>
              <option value="operation">operation</option>
            </select>
          </label>
          <button disabled={pending} onClick={() => runAction('数据清理', () => cleanupGovernance(retentionDays))}><Trash2 size={14} />{activeAction === '数据清理' ? '执行中...' : '清理旧数据'}</button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              runAction('文档重提取', () => reExtractDocuments(docIds.length ? { doc_ids: docIds } : {}))
            }}
          >
            <RefreshCw size={14} />{activeAction === '文档重提取' ? '执行中...' : '文档重提取'}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              const topics: Array<'company' | 'product' | 'operation'> = topicScope === 'all' ? ['company', 'product', 'operation'] : [topicScope]
              const payload = {
                topics,
                ...(docIds.length ? { doc_ids: docIds } : {}),
              }
              runAction('专题提取', () => topicExtractDocuments(payload))
            }}
          >
            <RefreshCw size={14} />{activeAction === '专题提取' ? '执行中...' : '专题提取'}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              if (!docIds.length) {
                setStatusText('图谱导出 失败')
                setErrorText('请先输入 doc_ids（逗号或空格分隔）')
                return
              }
              runAction(
                '图谱导出',
                async () => {
                  const result = await exportGraph(docIds)
                  const nodes = Array.isArray(result?.nodes) ? result.nodes.length : 0
                  const edges = Array.isArray(result?.edges) ? result.edges.length : 0
                  setStatusText(`图谱导出完成，nodes=${nodes}, edges=${edges}`)
                  return result
                },
                { refreshStats: false, refreshSearchHistory: false },
              )
            }}
          >
            <RefreshCw size={14} />{activeAction === '图谱导出' ? '执行中...' : '图谱导出'}
          </button>
          <button disabled={pending} onClick={() => runAction('聚合库同步', () => syncAggregator(true))}><RefreshCw size={14} />{activeAction === '聚合库同步' ? '执行中...' : '同步 Aggregator'}</button>
          <button onClick={() => { queryClient.invalidateQueries({ queryKey: ['admin-stats', projectKey] }); queryClient.invalidateQueries({ queryKey: ['search-history', projectKey] }); }}><RefreshCw size={14} />刷新</button>
        </div>
        <p className="status-line">{statusText}</p>
        {!!errorText && <p className="status-line">{errorText}</p>}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>文档治理</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ['admin-documents', projectKey] })} disabled={adminDocuments.isFetching}>
              <RefreshCw size={14} />
              {adminDocuments.isFetching ? '刷新中...' : '刷新文档'}
            </button>
            <button onClick={selectCurrentPage} disabled={!(adminDocuments.data?.items || []).length}>选择当前页</button>
            <button onClick={() => setSelectedDocIds([])} disabled={!selectedCount}>清空选择</button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>doc_type</span>
            <input value={docTypeFilter} onChange={(e) => { setDocTypeFilter(e.target.value); setDocPage(1) }} placeholder="policy/market_info/..." />
          </label>
          <label>
            <span>state</span>
            <input value={docStateFilter} onChange={(e) => { setDocStateFilter(e.target.value); setDocPage(1) }} placeholder="CA/TX/..." />
          </label>
          <label>
            <span>search</span>
            <input value={docSearch} onChange={(e) => { setDocSearch(e.target.value); setDocPage(1) }} placeholder="标题关键词" />
          </label>
          <label>
            <span>extract_mode</span>
            <select value={extractMode} onChange={(e) => setExtractMode(e.target.value as 'replace' | 'merge')}>
              <option value="merge">merge</option>
              <option value="replace">replace</option>
            </select>
          </label>
        </div>
        <div className="form-grid cols-2">
          <label>
            <span>extracted_data(JSON)</span>
            <textarea rows={6} value={extractJsonText} onChange={(e) => setExtractJsonText(e.target.value)} />
          </label>
          <div className="inline-actions">
            <button
              disabled={pending || !selectedCount}
              onClick={() => {
                runAction('批量写入结构化', async () => {
                  let parsed: unknown
                  try {
                    parsed = JSON.parse(extractJsonText || '{}')
                  } catch {
                    throw new Error('extracted_data 不是合法 JSON')
                  }
                  return bulkUpdateDocumentExtractedData({
                    doc_ids: selectedDocIds,
                    mode: extractMode,
                    extracted_data: parsed,
                  })
                })
              }}
            >
              批量写入结构化
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('清空结构化', () => clearDocumentExtractedData(selectedDocIds))}
            >
              清空结构化
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('删除文档', () => deleteAdminDocuments({ ids: selectedDocIds }))}
            >
              删除文档
            </button>
          </div>
        </div>
        <p className="status-line">已选择文档: {selectedCount}</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>选中</th>
                <th>ID</th>
                <th>标题</th>
                <th>类型</th>
                <th>州</th>
                <th>提取</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {(adminDocuments.data?.items || []).map((row) => (
                <tr
                  key={row.id}
                  onClick={() => {
                    let nextId: number | null = row.id
                    setActiveDocCardId((prev) => {
                      nextId = prev === row.id ? null : row.id
                      return nextId
                    })
                    if (nextId === null) {
                      return
                    }
                    setOpsCardTab('business')
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedDocIds.includes(row.id)}
                      onChange={() => toggleDocSelection(row.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td>{row.id}</td>
                  <td>{row.title || '-'}</td>
                  <td>{row.doc_type || '-'}</td>
                  <td>{row.state || '-'}</td>
                  <td>{String(row.has_extracted_data ?? false)}</td>
                  <td>{formatDate(row.updated_at)}</td>
                </tr>
              ))}
              {!adminDocuments.data?.items?.length ? (
                <tr>
                  <td colSpan={7} className="empty-cell">暂无文档</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="inline-actions">
          <button disabled={docPage <= 1} onClick={() => setDocPage((p) => Math.max(1, p - 1))}>上一页</button>
          <span className="chip">第 {docPage}/{docTotalPages} 页</span>
          <button disabled={docPage >= docTotalPages} onClick={() => setDocPage((p) => Math.min(docTotalPages, p + 1))}>下一页</button>
        </div>
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

      {activeDocCardId ? (
        <Gv2NodeCard
          title={activeDocDetail.data?.title || `文档 ${activeDocCardId}`}
          subtitle={activeDocDetail.data?.doc_type || '-'}
          style={{
            position: 'fixed',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            width: 'min(720px, calc(100vw - 40px))',
            maxHeight: 'calc(100vh - 80px)',
            overflow: 'auto',
            zIndex: 80,
          }}
          actions={
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <div className="gv2-card-tabs" role="tablist" aria-label="卡片标签">
                <button
                  type="button"
                  role="tab"
                  aria-selected={opsCardTab === 'business'}
                  className={`gv2-card-tab ${opsCardTab === 'business' ? 'is-active' : ''}`.trim()}
                  onClick={() => {
                    setOpsCardTab('business')
                  }}
                  title="业务数据"
                >
                  业务数据
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={opsCardTab === 'graph_ext'}
                  className={`gv2-card-tab ${opsCardTab === 'graph_ext' ? 'is-active' : ''}`.trim()}
                  onClick={() => setOpsCardTab('graph_ext')}
                  title="图谱扩展"
                >
                  图谱扩展
                </button>
              </div>
              <button
                type="button"
                onClick={() => {
                  void queryClient.invalidateQueries({ queryKey: ['admin-document-detail', projectKey, activeDocCardId] })
                }}
                title="刷新"
              >
                ↻
              </button>
            </div>
          }
          onClose={() => {
            setActiveDocCardId(null)
            setOpsCardTab('business')
          }}
        >
          {activeDocDetail.isFetching ? (
            <div className="gv2-node-grid">
              <div className="gv2-node-grid-item">
                <label>状态</label>
                <strong>加载中...</strong>
              </div>
            </div>
          ) : (
            <>
              {opsCardTab === 'business' ? <GraphBusinessCardSections node={toGraphBusinessNode(activeDocDetail.data, activeDocCardId)} /> : null}
              {opsCardTab === 'graph_ext' ? (
                <GraphExtensionsSections
                  key={`ops-graph-ext-${activeDocCardId || 'none'}`}
                  graphInfo={{
                    degree: graphExtension.relationExamples.length,
                    neighborTypeCount: graphExtension.entityTypeItems.length,
                    marketDocCount: graphExtension.relationTypeItems.length,
                    neighborTypeItems: graphExtension.entityTypeItems,
                    predicateItems: graphExtension.relationTypeItems.map((item) => ({ predicate: item.type, count: item.count })),
                    neighborNodesByType: Object.fromEntries(
                      Object.entries(graphExtension.entityItemsByType).map(([type, names]) => [
                        type,
                        names.map((name, idx) => ({ id: `${type}-${idx}`, name, type })),
                      ]),
                    ),
                    relationsByPredicate: Object.fromEntries(
                      Object.entries(graphExtension.relationItemsByType).map(([type, lines]) => [
                        type,
                        lines.map((line, idx) => ({ id: `${type}-${idx}`, direction: 'OUT' as const, targetName: line, targetType: 'Relation' })),
                      ]),
                    ),
                  }}
                  nodeElementGroups={graphExtension.elementGroups}
                  relationGroups={graphExtension.relationTypeItems.map((item) => ({
                    relation: item.type,
                    items: (graphExtension.relationItemsByType[item.type] || []).map((line, idx) => ({
                      id: `${item.type}-${idx}`,
                      direction: 'OUT' as const,
                      relation: item.type,
                      targetName: line,
                      targetType: 'Relation',
                    })),
                  }))}
                  nodeTypeColor={{ Relation: '#c4b5fd' }}
                />
              ) : null}
            </>
          )}
        </Gv2NodeCard>
      ) : null}
    </div>
  )
}
