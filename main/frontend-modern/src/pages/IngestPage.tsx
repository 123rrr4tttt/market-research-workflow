import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  Boxes,
  Cable,
  Database,
  Globe,
  LoaderCircle,
  Play,
  Radar,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import {
  generateKeywords,
  ingestCommodity,
  ingestEcom,
  ingestMarket,
  ingestPolicy,
  ingestPolicyRegulation,
  ingestSocial,
  listIngestHistory,
  listSiteEntryGrouped,
  listSourceItems,
  runSourceLibrary,
  syncSourceLibrary,
} from '../lib/api'
import type { IngestFormState, IngestJobRow, SourceLibraryItem } from '../lib/types'

const defaultForm: IngestFormState = {
  queryTerms: '',
  topicFocus: '',
  languages: [],
  provider: '',
  maxItems: 20,
  startOffset: '',
  daysBack: '',
  enableExtraction: true,
  asyncMode: true,
  socialPlatform: 'reddit',
  baseSubreddits: 'MachineLearning, robotics, ArtificialInteligence, singularity',
  enableSubredditDiscovery: true,
  commodityLimit: 30,
  ecomLimit: 100,
  sourceItemKey: '',
  sourceHandlerKey: '',
  policyState: '',
}

function splitTerms(raw: string) {
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function toNullableInt(raw: string, min: number, max: number) {
  if (!raw.trim()) return null
  const value = Number.parseInt(raw, 10)
  if (!Number.isFinite(value)) return null
  return Math.min(max, Math.max(min, value))
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
}

function rowTaskName(row: IngestJobRow) {
  return row.task_name || row.job_type || row.task_id || String(row.id || '-')
}

function rowStartAt(row: IngestJobRow) {
  return row.started_at || row.created_at
}

function rowEndAt(row: IngestJobRow) {
  return row.finished_at || row.updated_at
}

function statusClass(status?: string) {
  const key = String(status || '').toLowerCase()
  if (key.includes('fail') || key.includes('error')) return 'chip chip-danger'
  if (key.includes('done') || key.includes('success') || key.includes('completed')) return 'chip chip-ok'
  return 'chip chip-warn'
}

function getSourceParams(item: SourceLibraryItem | null) {
  return item?.params && typeof item.params === 'object' ? item.params : {}
}

function listFromUnknown(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((v) => String(v || '').trim()).filter(Boolean)
  }
  if (typeof value === 'string') {
    return splitTerms(value)
  }
  return []
}

type IngestPageProps = {
  projectKey: string
  variant?: 'ingest' | 'specialized'
}

export default function IngestPage({ projectKey, variant = 'ingest' }: IngestPageProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<IngestFormState>(defaultForm)
  const [actionPending, setActionPending] = useState(false)
  const [actionMessage, setActionMessage] = useState('等待操作')

  const sourceItems = useQuery({ queryKey: ['source-items', projectKey], queryFn: listSourceItems })
  const handlerGrouped = useQuery({ queryKey: ['site-entry-grouped', projectKey], queryFn: listSiteEntryGrouped })
  const history = useQuery({ queryKey: ['ingest-history', projectKey], queryFn: () => listIngestHistory(12) })

  const sourceItemList = sourceItems.data || []
  const selectedSourceItem = useMemo(
    () => sourceItemList.find((item) => item.item_key === form.sourceItemKey) || null,
    [sourceItemList, form.sourceItemKey],
  )

  const handlerKeys = useMemo(
    () => Object.keys(handlerGrouped.data?.by_entry_type || {}).sort(),
    [handlerGrouped.data],
  )

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
        queryClient.invalidateQueries({ queryKey: ['source-items', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['site-entry-grouped', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['ingest-history', projectKey] }),
      ])
    } catch (error) {
      setActionMessage(`${name} 失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setActionPending(false)
    }
  }

  const getLanguageValue = () => {
    const langs = Array.from(new Set(form.languages))
    if (!langs.length) return null
    if (langs.includes('zh') && langs.includes('en')) return 'zh-en'
    return langs[0]
  }

  const buildCommonPayload = () => {
    const queryTerms = splitTerms(form.queryTerms)
    if (!queryTerms.length) throw new Error('请先输入查询词（逗号分隔）')

    const payload: Record<string, unknown> = {
      query_terms: queryTerms,
      keywords: queryTerms,
      max_items: form.maxItems,
      limit: form.maxItems,
      async_mode: form.asyncMode,
      enable_extraction: form.enableExtraction,
    }

    const startOffset = toNullableInt(form.startOffset, 1, 91)
    const daysBack = toNullableInt(form.daysBack, 1, 365)
    const language = getLanguageValue()

    if (startOffset != null) payload.start_offset = startOffset
    if (daysBack != null) payload.days_back = daysBack
    if (language) payload.language = language
    if (form.provider) payload.provider = form.provider
    if (form.topicFocus) payload.topic_focus = form.topicFocus

    return payload
  }

  const buildOverrideParams = () => {
    const payload: Record<string, unknown> = {
      limit: form.maxItems,
      max_items: form.maxItems,
      enable_extraction: form.enableExtraction,
      platforms: [form.socialPlatform],
      enable_subreddit_discovery: form.enableSubredditDiscovery,
    }

    const queryTerms = splitTerms(form.queryTerms)
    if (queryTerms.length) {
      payload.query_terms = queryTerms
      payload.keywords = queryTerms
      payload.search_keywords = queryTerms
      payload.base_keywords = queryTerms
      payload.topic_keywords = queryTerms
    }

    const startOffset = toNullableInt(form.startOffset, 1, 91)
    const daysBack = toNullableInt(form.daysBack, 1, 365)
    const language = getLanguageValue()

    if (startOffset != null) payload.start_offset = startOffset
    if (daysBack != null) payload.days_back = daysBack
    if (language) payload.language = language
    if (form.provider) payload.provider = form.provider

    const subreddits = splitTerms(form.baseSubreddits)
    if (subreddits.length) payload.base_subreddits = subreddits

    return payload
  }

  const onSourceItemChange = (itemKey: string) => {
    const item = sourceItemList.find((it) => it.item_key === itemKey) || null
    const params = getSourceParams(item)

    const preferredState = String(params.state || '').trim()
    const preferredPlatform = listFromUnknown(params.platforms || params.platform)[0] || 'reddit'
    const preferredSubreddits = listFromUnknown(params.base_subreddits || params.subreddits)
    const keywords = [
      ...listFromUnknown(params.query_terms),
      ...listFromUnknown(params.keywords),
      ...listFromUnknown(params.search_keywords),
      ...listFromUnknown(params.base_keywords),
      ...listFromUnknown(params.topic_keywords),
    ]

    setForm((prev) => ({
      ...prev,
      sourceItemKey: itemKey,
      sourceHandlerKey: '',
      policyState: preferredState || prev.policyState,
      socialPlatform: preferredPlatform,
      baseSubreddits: preferredSubreddits.length ? preferredSubreddits.join(', ') : prev.baseSubreddits,
      queryTerms: prev.queryTerms.trim() ? prev.queryTerms : Array.from(new Set(keywords)).join(', '),
    }))
  }

  const onSuggestKeywords = () =>
    runAction('获取联想词', async () => {
      const base = splitTerms(form.queryTerms)
      if (!base.length) throw new Error('请先输入查询词')

      const response = await generateKeywords({
        topic: base.join(' '),
        language: getLanguageValue() || 'zh',
        platform: form.topicFocus ? null : form.socialPlatform,
        topic_focus: form.topicFocus || undefined,
        base_keywords: base,
      })

      const suggested = response.search_keywords?.length ? response.search_keywords : response.keywords || []
      const merged = Array.from(new Set([...base, ...suggested.map((v) => String(v || '').trim()).filter(Boolean)]))
      if (!merged.length) throw new Error('未获得联想词')

      setForm((prev) => ({ ...prev, queryTerms: merged.join(', ') }))
      return { ok: true }
    })

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'specialized' ? '特化采集配置' : '通用采集配置'}</h2>
          <span className="chip">{variant === 'specialized' ? 'specialized' : 'general'}</span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>
            <Search size={15} />检索设置
          </h2>
          <span className="chip">项目: {projectKey}</span>
        </div>

        <div className="form-grid cols-4">
          <label>
            <span>查询词</span>
            <textarea
              rows={3}
              value={form.queryTerms}
              onChange={(e) => setForm((p) => ({ ...p, queryTerms: e.target.value }))}
              placeholder="词A, 词B"
            />
          </label>
          <label>
            <span>专题联想</span>
            <select
              value={form.topicFocus}
              onChange={(e) => setForm((p) => ({ ...p, topicFocus: e.target.value as IngestFormState['topicFocus'] }))}
            >
              <option value="">默认</option>
              <option value="company">公司</option>
              <option value="product">商品</option>
              <option value="operation">电商/经营</option>
            </select>
          </label>
          <label>
            <span>搜索服务</span>
            <select
              value={form.provider}
              onChange={(e) => setForm((p) => ({ ...p, provider: e.target.value as IngestFormState['provider'] }))}
            >
              <option value="">默认</option>
              <option value="serper">serper</option>
              <option value="google">google</option>
              <option value="ddg">ddg</option>
              <option value="serpstack">serpstack</option>
              <option value="serpapi">serpapi</option>
              <option value="auto">auto</option>
            </select>
          </label>
          <label>
            <span>每词结果数</span>
            <input
              type="number"
              min={1}
              max={100}
              value={form.maxItems}
              onChange={(e) => setForm((p) => ({ ...p, maxItems: Number.parseInt(e.target.value || '20', 10) || 20 }))}
            />
          </label>
          <label>
            <span>起始偏移</span>
            <input value={form.startOffset} onChange={(e) => setForm((p) => ({ ...p, startOffset: e.target.value }))} placeholder="1 / 11 / 21" />
          </label>
          <label>
            <span>时间范围(天)</span>
            <input value={form.daysBack} onChange={(e) => setForm((p) => ({ ...p, daysBack: e.target.value }))} placeholder="7" />
          </label>
          <label>
            <span>语言</span>
            <div className="inline-checks">
              <label>
                <input
                  type="checkbox"
                  checked={form.languages.includes('zh')}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      languages: e.target.checked ? Array.from(new Set([...p.languages, 'zh'])) : p.languages.filter((x) => x !== 'zh'),
                    }))
                  }
                />
                zh
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={form.languages.includes('en')}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      languages: e.target.checked ? Array.from(new Set([...p.languages, 'en'])) : p.languages.filter((x) => x !== 'en'),
                    }))
                  }
                />
                en
              </label>
            </div>
          </label>
          <div className="toggles">
            <label>
              <input
                type="checkbox"
                checked={form.enableExtraction}
                onChange={(e) => setForm((p) => ({ ...p, enableExtraction: e.target.checked }))}
              />
              结构化提取
            </label>
            <label>
              <input type="checkbox" checked={form.asyncMode} onChange={(e) => setForm((p) => ({ ...p, asyncMode: e.target.checked }))} />
              异步模式
            </label>
          </div>
        </div>

        <div className="inline-actions">
          <button disabled={actionPending} onClick={onSuggestKeywords}>
            <Sparkles size={15} />获取联想词
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Database size={15} />来源库运行
          </h2>
        </div>

        <p className="status-line">
          <Database size={14} />
          {selectedSourceItem ? `已选来源项: ${selectedSourceItem.name || selectedSourceItem.item_key}` : '未选择来源项，可直接选 Handler 聚类运行'}
        </p>

        <div className="form-grid cols-2">
          <label>
            <span>来源库项</span>
            <select value={form.sourceItemKey} onChange={(e) => onSourceItemChange(e.target.value)}>
              <option value="">(可选) 选择 item_key</option>
              {sourceItemList.map((item) => (
                <option key={item.item_key} value={item.item_key}>
                  {item.name || item.item_key} ({item.item_key})
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Handler 聚类(entry_type)</span>
            <select value={form.sourceHandlerKey} onChange={(e) => setForm((p) => ({ ...p, sourceHandlerKey: e.target.value, sourceItemKey: '' }))}>
              <option value="">(可选) 选择 handler_key</option>
              {handlerKeys.map((key) => (
                <option key={key} value={key}>
                  {key} ({handlerGrouped.data?.by_entry_type?.[key]?.count || 0})
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="form-grid cols-2">
          <label>
            <span>平台</span>
            <input value={form.socialPlatform} onChange={(e) => setForm((p) => ({ ...p, socialPlatform: e.target.value || 'reddit' }))} />
          </label>
          <label>
            <span>基础子论坛(逗号分隔)</span>
            <input value={form.baseSubreddits} onChange={(e) => setForm((p) => ({ ...p, baseSubreddits: e.target.value }))} />
          </label>
        </div>

        <label className="single-check">
          <input
            type="checkbox"
            checked={form.enableSubredditDiscovery}
            onChange={(e) => setForm((p) => ({ ...p, enableSubredditDiscovery: e.target.checked }))}
          />
          子论坛发现
        </label>

        <div className="inline-actions">
          <button disabled={actionPending} onClick={() => runAction('同步来源库', syncSourceLibrary)}>
            <RefreshCw size={15} />同步来源库
          </button>
          <button
            disabled={actionPending || (!form.sourceItemKey && !form.sourceHandlerKey)}
            onClick={() =>
              runAction('运行来源库', () =>
                runSourceLibrary({
                  item_key: form.sourceItemKey || null,
                  handler_key: form.sourceHandlerKey || null,
                  async_mode: form.asyncMode,
                  override_params: buildOverrideParams(),
                }),
              )
            }
          >
            <Play size={15} />运行
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Cable size={15} />采集执行
          </h2>
        </div>

        <div className="form-grid cols-3">
          <label>
            <span>政策 State</span>
            <input value={form.policyState} onChange={(e) => setForm((p) => ({ ...p, policyState: e.target.value }))} placeholder="如 CA" />
          </label>
          <label>
            <span>商品天数</span>
            <input
              type="number"
              min={1}
              max={365}
              value={form.commodityLimit}
              onChange={(e) => setForm((p) => ({ ...p, commodityLimit: Number.parseInt(e.target.value || '30', 10) || 30 }))}
            />
          </label>
          <label>
            <span>电商条数</span>
            <input
              type="number"
              min={1}
              max={500}
              value={form.ecomLimit}
              onChange={(e) => setForm((p) => ({ ...p, ecomLimit: Number.parseInt(e.target.value || '100', 10) || 100 }))}
            />
          </label>
        </div>

        <div className="action-grid">
          <button
            disabled={actionPending || !form.policyState.trim()}
            onClick={() => runAction('政策采集', () => ingestPolicy({ state: form.policyState.trim(), async_mode: form.asyncMode, source_hint: null }))}
          >
            <Bot size={16} />政策采集
          </button>
          <button disabled={actionPending} onClick={() => runAction('政策法规采集', () => ingestPolicyRegulation(buildCommonPayload()))}>
            <Radar size={16} />政策法规
          </button>
          <button disabled={actionPending} onClick={() => runAction('市场采集', () => ingestMarket(buildCommonPayload()))}>
            <Activity size={16} />市场采集
          </button>
          <button
            disabled={actionPending}
            onClick={() =>
              runAction('舆情采集', () =>
                ingestSocial({
                  ...buildCommonPayload(),
                  platforms: [form.socialPlatform],
                  base_subreddits: splitTerms(form.baseSubreddits),
                  enable_subreddit_discovery: form.enableSubredditDiscovery,
                }),
              )
            }
          >
            <Globe size={16} />舆情采集
          </button>
          <button disabled={actionPending} onClick={() => runAction('商品采集', () => ingestCommodity({ limit: form.commodityLimit, async_mode: form.asyncMode }))}>
            <Boxes size={16} />商品采集
          </button>
          <button disabled={actionPending} onClick={() => runAction('电商采集', () => ingestEcom({ limit: form.ecomLimit, async_mode: form.asyncMode }))}>
            <Database size={16} />电商采集
          </button>
        </div>

        <p className="status-line">
          {actionPending ? <LoaderCircle size={14} className="spinning" /> : <Play size={14} />}
          {actionMessage}
        </p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>最近任务状态</h2>
          <button onClick={() => queryClient.invalidateQueries({ queryKey: ['ingest-history', projectKey] })}>
            <RefreshCw size={14} />刷新
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>结束时间</th>
              </tr>
            </thead>
            <tbody>
              {(history.data || []).map((row, idx) => (
                <tr key={`${row.id || row.task_id || idx}`}>
                  <td>{rowTaskName(row)}</td>
                  <td>
                    <span className={statusClass(row.status)}>{row.status || '-'}</span>
                  </td>
                  <td>{formatDate(rowStartAt(row))}</td>
                  <td>{formatDate(rowEndAt(row))}</td>
                </tr>
              ))}
              {!history.data?.length && (
                <tr>
                  <td colSpan={4} className="empty-cell">
                    暂无任务记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
