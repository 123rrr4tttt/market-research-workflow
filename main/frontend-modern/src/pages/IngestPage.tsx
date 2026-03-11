import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Boxes,
  Cable,
  Database,
  Globe,
  History,
  LoaderCircle,
  Link2,
  Play,
  Radar,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
} from 'lucide-react'
import {
  generateKeywords,
  listIngestHistory,
  listSiteEntryGrouped,
  listSourceItems,
} from '../lib/api'
import type { IngestSingleUrlPayload } from '../lib/api'
import { useIngestActions } from '../hooks/useIngestActions'
import { queryKeys } from '../lib/queryKeys'
import type { AgentBatchEventRow, AgentBatchItemRow, IngestFormState, IngestJobRow, SourceLibraryItem } from '../lib/types'

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
  singleUrl: '',
  singleUrlStrictMode: false,
  singleUrlSearchExpand: true,
  singleUrlSearchExpandLimit: 3,
  singleUrlSearchProvider: 'auto',
  singleUrlSearchFallbackProvider: 'ddg_html',
  singleUrlFallbackOnInsufficient: true,
  singleUrlAllowSearchSummaryWrite: false,
  singleUrlMinResultsRequired: 6,
  singleUrlTargetCandidates: 6,
  singleUrlDecodeRedirectWrappers: true,
  singleUrlFilterLowValueCandidates: true,
  singleUrlLightFilterEnabled: true,
  singleUrlLightFilterMinScore: 30,
  singleUrlLightFilterRejectStaticAssets: true,
  singleUrlLightFilterRejectSearchNoiseDomain: true,
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

function rowRejectionCount(row: IngestJobRow) {
  if (typeof row.rejected_count === 'number') return row.rejected_count
  const params = row.params && typeof row.params === 'object' ? row.params : null
  const value = params && 'rejected_count' in params ? Number((params as Record<string, unknown>).rejected_count) : Number.NaN
  return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0
}

function rowDegradationFlags(row: IngestJobRow) {
  if (Array.isArray(row.degradation_flags)) {
    return row.degradation_flags.map((v) => String(v || '').trim()).filter(Boolean)
  }
  const params = row.params && typeof row.params === 'object' ? row.params : null
  const value = params && 'degradation_flags' in params ? (params as Record<string, unknown>).degradation_flags : null
  if (!Array.isArray(value)) return []
  return value.map((v) => String(v || '').trim()).filter(Boolean)
}

function statusClass(status?: string) {
  const key = String(status || '').toLowerCase()
  if (key.includes('fail') || key.includes('error')) return 'chip chip-danger'
  if (key.includes('done') || key.includes('success') || key.includes('completed')) return 'chip chip-ok'
  return 'chip chip-warn'
}

function isFailedStatus(status?: string) {
  const key = String(status || '').toLowerCase()
  return key.includes('fail') || key.includes('error') || key.includes('revoked')
}

function toErrorText(value: unknown) {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object') return ''
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
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
  const [form, setForm] = useState<IngestFormState>(defaultForm)
  const [agentBatchJobId, setAgentBatchJobId] = useState('')
  const [agentBatchRejectedReasonCodes, setAgentBatchRejectedReasonCodes] = useState<string[]>([])
  const {
    actionPending,
    actionMessage,
    runAction,
    syncSourceLibrary,
    runSourceLibrary,
    ingestPolicyRegulation,
    ingestMarket,
    ingestSingleUrl,
    ingestDataApi,
    ingestCommodity,
    ingestEcom,
    submitAgentBatchJob,
    getAgentBatchJob,
    listAgentBatchItems,
    getAgentBatchEvents,
    retryAgentBatchJob,
    runAgentBatchNlCommand,
  } = useIngestActions(projectKey)

  const sourceItems = useQuery({ queryKey: queryKeys.sourceLibrary.items(projectKey), queryFn: listSourceItems })
  const handlerGrouped = useQuery({ queryKey: queryKeys.sourceLibrary.siteEntryGrouped(projectKey), queryFn: listSiteEntryGrouped })
  const history = useQuery({ queryKey: queryKeys.ingest.historyByProject(projectKey, 12), queryFn: () => listIngestHistory(12) })
  const agentBatchJob = useQuery({
    queryKey: ['agent-batch', projectKey, 'job', agentBatchJobId],
    queryFn: () => getAgentBatchJob(agentBatchJobId),
    enabled: Boolean(agentBatchJobId),
    refetchInterval: 5000,
  })
  const agentBatchItems = useQuery({
    queryKey: ['agent-batch', projectKey, 'items', agentBatchJobId],
    queryFn: async () => (await listAgentBatchItems(agentBatchJobId)).items || [],
    enabled: Boolean(agentBatchJobId),
    refetchInterval: 5000,
  })
  const agentBatchEvents = useQuery({
    queryKey: ['agent-batch', projectKey, 'events', agentBatchJobId],
    queryFn: async () => (await getAgentBatchEvents(agentBatchJobId)).events || [],
    enabled: Boolean(agentBatchJobId),
    refetchInterval: 5000,
  })

  const sourceItemList = useMemo(() => sourceItems.data || [], [sourceItems.data])
  const selectedSourceItem = useMemo(
    () => sourceItemList.find((item) => item.item_key === form.sourceItemKey) || null,
    [sourceItemList, form.sourceItemKey],
  )

  const handlerKeys = useMemo(
    () => Object.keys(handlerGrouped.data?.by_entry_type || {}).sort(),
    [handlerGrouped.data],
  )

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

  const buildSingleUrlPayload = (): IngestSingleUrlPayload => {
    const url = String(form.singleUrl || '').trim()
    if (!url) throw new Error('请先输入 URL')
    const queryTerms = splitTerms(form.queryTerms)
    return {
      url,
      query_terms: queryTerms.length ? queryTerms : null,
      strict_mode: form.singleUrlStrictMode,
      search_expand: form.singleUrlSearchExpand,
      search_expand_limit: form.singleUrlSearchExpandLimit,
      search_provider: form.singleUrlSearchProvider,
      search_fallback_provider: form.singleUrlSearchFallbackProvider,
      fallback_on_insufficient: form.singleUrlFallbackOnInsufficient,
      allow_search_summary_write: form.singleUrlAllowSearchSummaryWrite,
      min_results_required: form.singleUrlMinResultsRequired,
      target_candidates: form.singleUrlTargetCandidates,
      decode_redirect_wrappers: form.singleUrlDecodeRedirectWrappers,
      filter_low_value_candidates: form.singleUrlFilterLowValueCandidates,
      light_filter_enabled: form.singleUrlLightFilterEnabled,
      light_filter_min_score: form.singleUrlLightFilterMinScore,
      light_filter_reject_static_assets: form.singleUrlLightFilterRejectStaticAssets,
      light_filter_reject_search_noise_domain: form.singleUrlLightFilterRejectSearchNoiseDomain,
      async_mode: form.asyncMode,
    }
  }

  const onSourceItemChange = (itemKey: string) => {
    const item = sourceItemList.find((it) => it.item_key === itemKey) || null
    const params = getSourceParams(item)

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

  const onSubmitAgentBatch = async () => {
    const terms = splitTerms(form.queryTerms)
    if (!terms.length) throw new Error('请先输入查询词（逗号分隔）')
    const language = getLanguageValue() || 'zh'
    const daysBack = toNullableInt(form.daysBack, 1, 365) ?? undefined
    const jobs = terms.map((term, idx) => ({
      item_id: `market-${idx + 1}`,
      channel: 'search.market',
      query_terms: [term],
      max_items: form.maxItems,
      provider: form.provider || 'auto',
      language,
      days_back: daysBack,
      contract_version: 'collect.request.v2',
    }))

    const result = await submitAgentBatchJob({
      project_key: projectKey,
      idempotency_key: `ingest-ui-${Date.now()}`,
      batch: { jobs },
    })
    if (!result) return
    const jobId = typeof result.job_id === 'string' ? result.job_id : ''
    if (jobId) setAgentBatchJobId(jobId)
    const rejected = Array.isArray(result.rejected_job_items) ? result.rejected_job_items : []
    const reasonCodes = rejected.map((item) => String(item.reason_code || '').trim()).filter(Boolean)
    setAgentBatchRejectedReasonCodes(Array.from(new Set(reasonCodes)))
  }

  const onSubmitNlAgentBatch = async () => {
    const command = splitTerms(form.queryTerms).join('，')
    if (!command) throw new Error('请先输入查询词')
    const result = await runAgentBatchNlCommand({
      command: `请在最近${toNullableInt(form.daysBack, 1, 365) ?? 7}天采集：${command}`,
      project_key: projectKey,
      idempotency_key: `ingest-ui-nl-${Date.now()}`,
    })
    if (!result?.submit?.job_id) return
    setAgentBatchJobId(String(result.submit.job_id))
    const rejected = Array.isArray(result.submit.rejected_job_items) ? result.submit.rejected_job_items : []
    const reasonCodes = rejected.map((item) => String(item.reason_code || '').trim()).filter(Boolean)
    setAgentBatchRejectedReasonCodes(Array.from(new Set(reasonCodes)))
  }

  const onRetryBatchItem = async (item: AgentBatchItemRow) => {
    if (!agentBatchJobId || !item.item_id) return
    const result = await retryAgentBatchJob(agentBatchJobId, {
      scope: 'items',
      item_ids: [item.item_id],
      reason: 'ui_retry_failed_item',
      max_retries: 1,
    })
    if (!result) return
    await Promise.all([agentBatchJob.refetch(), agentBatchItems.refetch(), agentBatchEvents.refetch(), history.refetch()])
  }

  const progress = agentBatchJob.data?.progress
  const failedBatchItems = (agentBatchItems.data || []).filter((item) => isFailedStatus(item.status))
  const hasBatch = Boolean(agentBatchJobId)

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
          <button disabled={actionPending} onClick={() => void syncSourceLibrary()}>
            <RefreshCw size={15} />同步来源库
          </button>
          <button
            disabled={actionPending || (!form.sourceItemKey && !form.sourceHandlerKey)}
            onClick={() =>
              void runSourceLibrary({
                item_key: form.sourceItemKey || null,
                handler_key: form.sourceHandlerKey || null,
                async_mode: form.asyncMode,
                override_params: buildOverrideParams(),
              })
            }
          >
            <Play size={15} />运行
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Link2 size={15} />单 URL 入库
          </h2>
          <span className="chip">single_url</span>
        </div>

        <div className="form-grid cols-2">
          <label>
            <span>目标 URL</span>
            <input
              value={form.singleUrl}
              onChange={(e) => setForm((p) => ({ ...p, singleUrl: e.target.value }))}
              placeholder="https://example.com/article"
            />
          </label>
          <label>
            <span>搜索展开上限</span>
            <input
              type="number"
              min={1}
              max={20}
              value={form.singleUrlSearchExpandLimit}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  singleUrlSearchExpandLimit: Math.max(1, Math.min(20, Number.parseInt(e.target.value || '3', 10) || 3)),
                }))
              }
            />
          </label>
        </div>

        <div className="form-grid cols-4">
          <label>
            <span>搜索提供方</span>
            <select
              value={form.singleUrlSearchProvider}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  singleUrlSearchProvider: e.target.value as IngestFormState['singleUrlSearchProvider'],
                }))
              }
            >
              <option value="auto">auto</option>
              <option value="google">google</option>
              <option value="ddg_html">ddg_html</option>
            </select>
          </label>
          <label>
            <span>兜底提供方</span>
            <select
              value={form.singleUrlSearchFallbackProvider}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  singleUrlSearchFallbackProvider: e.target.value as IngestFormState['singleUrlSearchFallbackProvider'],
                }))
              }
            >
              <option value="ddg_html">ddg_html</option>
            </select>
          </label>
          <label>
            <span>最少结果数</span>
            <input
              type="number"
              min={1}
              max={20}
              value={form.singleUrlMinResultsRequired}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  singleUrlMinResultsRequired: Math.max(1, Math.min(20, Number.parseInt(e.target.value || '6', 10) || 6)),
                }))
              }
            />
          </label>
          <label>
            <span>目标候选数</span>
            <input
              type="number"
              min={1}
              max={20}
              value={form.singleUrlTargetCandidates}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  singleUrlTargetCandidates: Math.max(1, Math.min(20, Number.parseInt(e.target.value || '6', 10) || 6)),
                }))
              }
            />
          </label>
          <label>
            <span>轻过滤阈值(0-100)</span>
            <input
              type="number"
              min={0}
              max={100}
              value={form.singleUrlLightFilterMinScore}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  singleUrlLightFilterMinScore: Math.max(0, Math.min(100, Number.parseInt(e.target.value || '30', 10) || 30)),
                }))
              }
            />
          </label>
        </div>

        <div className="toggles">
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlStrictMode}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlStrictMode: e.target.checked }))}
            />
            严格模式
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlSearchExpand}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlSearchExpand: e.target.checked }))}
            />
            搜索展开
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlFallbackOnInsufficient}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlFallbackOnInsufficient: e.target.checked }))}
            />
            结果不足兜底
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlAllowSearchSummaryWrite}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlAllowSearchSummaryWrite: e.target.checked }))}
            />
            允许写入搜索摘要
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlDecodeRedirectWrappers}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlDecodeRedirectWrappers: e.target.checked }))}
            />
            解包重定向链接
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlFilterLowValueCandidates}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlFilterLowValueCandidates: e.target.checked }))}
            />
            过滤低价值候选
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlLightFilterEnabled}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlLightFilterEnabled: e.target.checked }))}
            />
            启用轻过滤
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlLightFilterRejectStaticAssets}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlLightFilterRejectStaticAssets: e.target.checked }))}
            />
            轻过滤拒绝静态资源
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.singleUrlLightFilterRejectSearchNoiseDomain}
              onChange={(e) => setForm((p) => ({ ...p, singleUrlLightFilterRejectSearchNoiseDomain: e.target.checked }))}
            />
            轻过滤拒绝噪音域
          </label>
        </div>

        <div className="inline-actions">
          <button disabled={actionPending || !form.singleUrl.trim()} onClick={() => void ingestSingleUrl(buildSingleUrlPayload())}>
            <Play size={15} />执行单 URL 入库
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
          <button disabled={actionPending} onClick={() => void ingestPolicyRegulation(buildCommonPayload())}>
            <Radar size={16} />政策法规
          </button>
          <button disabled={actionPending} onClick={() => void ingestMarket(buildCommonPayload())}>
            <Activity size={16} />市场采集
          </button>
          <button
            disabled={actionPending}
            onClick={() =>
              void ingestDataApi({
                ...buildCommonPayload(),
                platforms: [form.socialPlatform],
                base_subreddits: splitTerms(form.baseSubreddits),
                enable_subreddit_discovery: form.enableSubredditDiscovery,
              })
            }
          >
            <Globe size={16} />数据 API 采集
          </button>
          <button disabled={actionPending} onClick={() => void ingestCommodity({ limit: form.commodityLimit, async_mode: form.asyncMode })}>
            <Boxes size={16} />商品采集
          </button>
          <button disabled={actionPending} onClick={() => void ingestEcom({ limit: form.ecomLimit, async_mode: form.asyncMode })}>
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
          <h2>
            <History size={15} />
            Agent 批量采集（P1）
          </h2>
          <span className="chip">{hasBatch ? `job: ${agentBatchJobId}` : '未提交'}</span>
        </div>

        <div className="inline-actions">
          <button disabled={actionPending} onClick={() => void onSubmitAgentBatch()}>
            <Play size={15} />提交批量任务
          </button>
          <button disabled={actionPending} onClick={() => void onSubmitNlAgentBatch()}>
            <Sparkles size={15} />NL 指令启动
          </button>
          {hasBatch && (
            <button
              disabled={actionPending}
              onClick={() => {
                void Promise.all([agentBatchJob.refetch(), agentBatchItems.refetch(), agentBatchEvents.refetch()])
              }}
            >
              <RefreshCw size={15} />刷新批量状态
            </button>
          )}
        </div>

        {hasBatch && (
          <p className="status-line">
            状态: {agentBatchJob.data?.status || '-'} · 进度: {progress?.succeeded || 0}/{progress?.total || 0}（失败 {progress?.failed || 0}
            ，运行中 {progress?.running || 0}）
          </p>
        )}
        {!!agentBatchRejectedReasonCodes.length && (
          <p className="status-line">拒绝原因码: {agentBatchRejectedReasonCodes.join(', ')}</p>
        )}
        {hasBatch && !!failedBatchItems.length && <p className="status-line">失败项: {failedBatchItems.length}（可一键重试）</p>}

        {hasBatch && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>任务</th>
                  <th>状态</th>
                  <th>错误</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {(agentBatchItems.data || []).map((item, idx) => (
                  <tr key={`${item.item_id || 'item'}-${idx}`}>
                    <td>{item.item_id || '-'}</td>
                    <td>{item.task_id || '-'}</td>
                    <td>
                      <span className={statusClass(item.status)}>{item.status || '-'}</span>
                    </td>
                    <td>{toErrorText(item.error) || '-'}</td>
                    <td>
                      <button
                        disabled={actionPending || !isFailedStatus(item.status)}
                        onClick={() => {
                          void onRetryBatchItem(item)
                        }}
                      >
                        <RotateCcw size={14} />重试
                      </button>
                    </td>
                  </tr>
                ))}
                {!agentBatchItems.data?.length && (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      暂无批量项
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {hasBatch && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>事件</th>
                  <th>Item</th>
                  <th>消息</th>
                </tr>
              </thead>
              <tbody>
                {(agentBatchEvents.data || []).slice(0, 20).map((event: AgentBatchEventRow, idx) => (
                  <tr key={`${event.id || 'evt'}-${idx}`}>
                    <td>{formatDate(event.ts)}</td>
                    <td>{event.event_type || '-'}</td>
                    <td>{event.item_id || '-'}</td>
                    <td>{event.message || '-'}</td>
                  </tr>
                ))}
                {!agentBatchEvents.data?.length && (
                  <tr>
                    <td colSpan={4} className="empty-cell">
                      暂无时间线事件
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>最近任务状态</h2>
          <button onClick={() => void history.refetch()}>
            <RefreshCw size={14} />刷新
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>拒绝数</th>
                <th>降级标记</th>
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
                  <td>{rowRejectionCount(row)}</td>
                  <td>{rowDegradationFlags(row).slice(0, 2).join(', ') || '-'}</td>
                  <td>{formatDate(rowStartAt(row))}</td>
                  <td>{formatDate(rowEndAt(row))}</td>
                </tr>
              ))}
              {!history.data?.length && (
                <tr>
                  <td colSpan={6} className="empty-cell">
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
