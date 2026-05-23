import { useMemo, useState, type Dispatch, type SetStateAction } from 'react'
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
import { DEFAULT_APP_LOCALE, translate, useAppLocale, type AppLocale, type MessageKey } from '../app/platform/i18n'
import type { IngestSingleUrlPayload } from '../lib/api'
import { useIngestActions } from '../hooks/useIngestActions'
import { queryKeys } from '../lib/queryKeys'
import type { AgentBatchEventRow, AgentBatchItemRow, AgentBatchJobDetail, IngestFormState, IngestJobRow, SourceLibraryItem } from '../lib/types'

type IngestMessageKey = MessageKey
type TemplateValues = {
  [key: string]: string | number
}
type HandlerGroupedByEntryType = {
  [entryType: string]: { count?: number }
}

function formatIngestTemplate(template: string, values: TemplateValues) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

const defaultBaseSubreddits = translate(DEFAULT_APP_LOCALE, 'ingestPage.default.baseSubreddits')

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
  baseSubreddits: defaultBaseSubreddits,
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

function formatDate(value?: string | null, locale: AppLocale = DEFAULT_APP_LOCALE) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString(locale)
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

function toDisplayInt(value: number | string | null | undefined, fallback: number) {
  const parsed = Number.parseInt(String(value ?? ''), 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

type SliderFieldProps = {
  label: string
  value: number
  min: number
  max: number
  step?: number
  unit?: string
  onChange: (nextValue: number) => void
}

function SliderField({ label, value, min, max, step = 1, unit = '', onChange }: SliderFieldProps) {
  return (
    <label className="ingest-slider-field">
      <span>{label}</span>
      <div className="ingest-slider-field__body">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => onChange(Number.parseInt(event.target.value, 10) || min)}
        />
        <strong>{unit ? `${value}${unit}` : value}</strong>
      </div>
    </label>
  )
}

type IngestPageProps = {
  projectKey: string
  variant?: 'ingest' | 'specialized'
}

export type IngestPageViewProps = {
  variant: 'ingest' | 'specialized'
  pageTitle: string
  pageScopeLabel: string
  form: IngestFormState
  setForm: Dispatch<SetStateAction<IngestFormState>>
  actionPending: boolean
  actionMessage: string
  sourceItemList: SourceLibraryItem[]
  selectedSourceItem: SourceLibraryItem | null
  handlerGroupedByEntryType: HandlerGroupedByEntryType
  handlerKeys: string[]
  historyRows: IngestJobRow[]
  agentBatchJobId: string
  agentBatchJob: AgentBatchJobDetail | undefined
  agentBatchItems: AgentBatchItemRow[]
  agentBatchEvents: AgentBatchEventRow[]
  agentBatchRejectedReasonCodes: string[]
  onSourceItemChange: (itemKey: string) => void
  onSuggestKeywords: () => void
  onSyncSourceLibrary: () => void
  onRunSourceLibrary: () => void
  onIngestSingleUrl: () => void
  onIngestPolicyRegulation: () => void
  onIngestMarket: () => void
  onIngestDataApi: () => void
  onIngestCommodity: () => void
  onIngestEcom: () => void
  onSubmitAgentBatch: () => void
  onSubmitNlAgentBatch: () => void
  onRefreshBatchStatus: () => void
  onRetryBatchItem: (item: AgentBatchItemRow) => void
  onRefreshHistory: () => void
}

export default function IngestPage({ projectKey, variant = 'ingest' }: IngestPageProps) {
  const locale = useAppLocale()
  const t = (key: IngestMessageKey) => translate(locale, key)
  const isSpecialized = variant === 'specialized'
  const pageTitle = t(isSpecialized ? 'ingestPage.title.specialized' : 'ingestPage.title.ingest')
  const pageScopeLabel = t(isSpecialized ? 'ingestPage.scope.specialized' : 'ingestPage.scope.ingest')
  const [form, setForm] = useState(defaultForm)
  const [agentBatchJobId, setAgentBatchJobId] = useState('')
  const [agentBatchRejectedReasonCodes, setAgentBatchRejectedReasonCodes] = useState([] as string[])
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
    if (!queryTerms.length) throw new Error(t('ingestPage.error.queryTermsComma'))

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
    if (!url) throw new Error(t('ingestPage.error.urlRequired'))
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
    runAction(t('ingestPage.action.suggestKeywords'), async () => {
      const base = splitTerms(form.queryTerms)
      if (!base.length) throw new Error(t('ingestPage.error.queryTerms'))

      const response = await generateKeywords({
        topic: base.join(' '),
        language: getLanguageValue() || 'zh',
        platform: form.topicFocus ? null : form.socialPlatform,
        topic_focus: form.topicFocus || undefined,
        base_keywords: base,
      })

      const suggested = response.search_keywords?.length ? response.search_keywords : response.keywords || []
      const merged = Array.from(new Set([...base, ...suggested.map((v) => String(v || '').trim()).filter(Boolean)]))
      if (!merged.length) throw new Error(t('ingestPage.error.noSuggestedKeywords'))

      setForm((prev) => ({ ...prev, queryTerms: merged.join(', ') }))
      return { ok: true }
    })

  const onSubmitAgentBatch = async () => {
    const terms = splitTerms(form.queryTerms)
    if (!terms.length) throw new Error(t('ingestPage.error.queryTermsComma'))
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
    if (!command) throw new Error(t('ingestPage.error.queryTerms'))
    const requestCommand = formatIngestTemplate(translate(DEFAULT_APP_LOCALE, 'ingestPage.agentBatch.nlCommand'), {
      days: toNullableInt(form.daysBack, 1, 365) ?? 7,
      command,
    })
    const result = await runAgentBatchNlCommand({
      command: requestCommand,
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

  return (
    <IngestPageView
      variant={variant}
      pageTitle={pageTitle}
      pageScopeLabel={pageScopeLabel}
      form={form}
      setForm={setForm}
      actionPending={actionPending}
      actionMessage={actionMessage}
      sourceItemList={sourceItemList}
      selectedSourceItem={selectedSourceItem}
      handlerGroupedByEntryType={handlerGrouped.data?.by_entry_type || {}}
      handlerKeys={handlerKeys}
      historyRows={history.data || []}
      agentBatchJobId={agentBatchJobId}
      agentBatchJob={agentBatchJob.data}
      agentBatchItems={agentBatchItems.data || []}
      agentBatchEvents={agentBatchEvents.data || []}
      agentBatchRejectedReasonCodes={agentBatchRejectedReasonCodes}
      onSourceItemChange={onSourceItemChange}
      onSuggestKeywords={() => {
        void onSuggestKeywords()
      }}
      onSyncSourceLibrary={() => {
        void syncSourceLibrary()
      }}
      onRunSourceLibrary={() => {
        void runSourceLibrary({
          item_key: form.sourceItemKey || null,
          handler_key: form.sourceHandlerKey || null,
          async_mode: form.asyncMode,
          override_params: buildOverrideParams(),
        })
      }}
      onIngestSingleUrl={() => {
        void ingestSingleUrl(buildSingleUrlPayload())
      }}
      onIngestPolicyRegulation={() => {
        void ingestPolicyRegulation(buildCommonPayload())
      }}
      onIngestMarket={() => {
        void ingestMarket(buildCommonPayload())
      }}
      onIngestDataApi={() => {
        void ingestDataApi({
          ...buildCommonPayload(),
          platforms: [form.socialPlatform],
          base_subreddits: splitTerms(form.baseSubreddits),
          enable_subreddit_discovery: form.enableSubredditDiscovery,
        })
      }}
      onIngestCommodity={() => {
        void ingestCommodity({ limit: form.commodityLimit, async_mode: form.asyncMode })
      }}
      onIngestEcom={() => {
        void ingestEcom({ limit: form.ecomLimit, async_mode: form.asyncMode })
      }}
      onSubmitAgentBatch={() => {
        void onSubmitAgentBatch()
      }}
      onSubmitNlAgentBatch={() => {
        void onSubmitNlAgentBatch()
      }}
      onRefreshBatchStatus={() => {
        void Promise.all([agentBatchJob.refetch(), agentBatchItems.refetch(), agentBatchEvents.refetch()])
      }}
      onRetryBatchItem={(item) => {
        void onRetryBatchItem(item)
      }}
      onRefreshHistory={() => {
        void history.refetch()
      }}
    />
  )
}

export function IngestPageView({
  variant,
  pageTitle,
  pageScopeLabel,
  form,
  setForm,
  actionPending,
  actionMessage,
  sourceItemList,
  selectedSourceItem,
  handlerGroupedByEntryType,
  handlerKeys,
  historyRows,
  agentBatchJobId,
  agentBatchJob,
  agentBatchItems,
  agentBatchEvents,
  agentBatchRejectedReasonCodes,
  onSourceItemChange,
  onSuggestKeywords,
  onSyncSourceLibrary,
  onRunSourceLibrary,
  onIngestSingleUrl,
  onIngestPolicyRegulation,
  onIngestMarket,
  onIngestDataApi,
  onIngestCommodity,
  onIngestEcom,
  onSubmitAgentBatch,
  onSubmitNlAgentBatch,
  onRefreshBatchStatus,
  onRetryBatchItem,
  onRefreshHistory,
}: IngestPageViewProps) {
  const locale = useAppLocale()
  const t = (key: IngestMessageKey) => translate(locale, key)
  const tf = (key: IngestMessageKey, values: Record<string, string | number>) => formatIngestTemplate(t(key), values)
  const isSpecialized = variant === 'specialized'
  const progress = agentBatchJob?.progress
  const failedBatchItems = agentBatchItems.filter((item) => isFailedStatus(item.status))
  const hasBatch = Boolean(agentBatchJobId)
  const batchSummaryParts = [
    hasBatch ? tf('ingestPage.summary.status', { status: agentBatchJob?.status || '-' }) : '',
    hasBatch ? tf('ingestPage.summary.progress', { succeeded: progress?.succeeded || 0, total: progress?.total || 0 }) : '',
    hasBatch && (progress?.failed || 0) ? tf('ingestPage.summary.failed', { count: progress?.failed || 0 }) : '',
    agentBatchRejectedReasonCodes.length ? tf('ingestPage.summary.rejected', { reasons: agentBatchRejectedReasonCodes.join(', ') }) : '',
    hasBatch && failedBatchItems.length ? tf('ingestPage.summary.retryPending', { count: failedBatchItems.length }) : '',
  ].filter(Boolean)

  return (
    <div className={`content-stack ingest-page ingest-page--${variant} ingest-page--quiet`}>
      <section className="panel ingest-page__section ingest-page__section--query">
        <div className="panel-header">
          <h2>
            <Search size={15} />{t('ingestPage.section.searchSettings')}
          </h2>
          <span className="chip">
            {pageTitle} / {pageScopeLabel}
          </span>
        </div>

        <div className="ingest-query-layout">
          <div className="ingest-query-primary">
            <label className="ingest-query-prompt">
              <span>{t('ingestPage.field.queryTerms')}</span>
              <textarea
                rows={4}
                value={form.queryTerms}
                onChange={(e) => setForm((p) => ({ ...p, queryTerms: e.target.value }))}
                placeholder={t('ingestPage.placeholder.queryTerms')}
              />
            </label>

            <div className="ingest-query-footer">
              <div className="ingest-query-modes toggles">
                <label>
                  <input type="checkbox" checked={form.enableExtraction} onChange={(e) => setForm((p) => ({ ...p, enableExtraction: e.target.checked }))} />
                  {t('ingestPage.toggle.enableExtraction')}
                </label>
                <label>
                  <input type="checkbox" checked={form.asyncMode} onChange={(e) => setForm((p) => ({ ...p, asyncMode: e.target.checked }))} />
                  {t('ingestPage.toggle.asyncMode')}
                </label>
              </div>

              <div className="inline-actions">
                <button disabled={actionPending} onClick={onSuggestKeywords}>
                  <Sparkles size={15} />{t('ingestPage.action.suggestKeywords')}
                </button>
              </div>
            </div>
          </div>

          <div className="ingest-query-sidebar">
            <div className="ingest-query-cluster">
              <small>{t('ingestPage.group.searchStrategy')}</small>
              <div className="form-grid cols-3 ingest-query-cluster__fields">
                <label>
                  <span>{t('ingestPage.field.topicFocus')}</span>
                  <select value={form.topicFocus} onChange={(e) => setForm((p) => ({ ...p, topicFocus: e.target.value as IngestFormState['topicFocus'] }))}>
                    <option value="">{t('ingestPage.option.default')}</option>
                    <option value="company">{t('ingestPage.option.company')}</option>
                    <option value="product">{t('ingestPage.option.product')}</option>
                    <option value="operation">{t('ingestPage.option.operation')}</option>
                  </select>
                </label>
                <label>
                  <span>{t('ingestPage.field.provider')}</span>
                  <select value={form.provider} onChange={(e) => setForm((p) => ({ ...p, provider: e.target.value as IngestFormState['provider'] }))}>
                    <option value="">{t('ingestPage.option.default')}</option>
                    <option value="serper">serper</option>
                    <option value="google">google</option>
                    <option value="ddg">ddg</option>
                    <option value="serpstack">serpstack</option>
                    <option value="serpapi">serpapi</option>
                    <option value="auto">auto</option>
                  </select>
                </label>
                <SliderField label={t('ingestPage.field.maxItems')} min={1} max={100} value={form.maxItems} onChange={(nextValue) => setForm((p) => ({ ...p, maxItems: nextValue }))} />
              </div>
            </div>

            <div className="ingest-query-cluster">
              <small>{t('ingestPage.group.windowLanguage')}</small>
              <div className="form-grid cols-3 ingest-query-cluster__fields">
                <SliderField label={t('ingestPage.field.startOffset')} min={1} max={91} value={toDisplayInt(form.startOffset, 1)} onChange={(nextValue) => setForm((p) => ({ ...p, startOffset: String(nextValue) }))} />
                <SliderField label={t('ingestPage.field.daysBack')} min={1} max={90} unit="d" value={toDisplayInt(form.daysBack, 7)} onChange={(nextValue) => setForm((p) => ({ ...p, daysBack: String(nextValue) }))} />
                <label>
                  <span>{t('ingestPage.field.language')}</span>
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
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className={`ingest-workspace ingest-workspace--${variant}`}>
        <div className={`ingest-workspace__primary ingest-workspace__primary--${variant}`}>
          {isSpecialized ? (
            <>
              <section className="ingest-flow-block ingest-page__section ingest-page__section--library">
                <div className="panel-header">
                  <h2>
                    <Database size={15} />{t('ingestPage.section.sourceLibraryRun')}
                  </h2>
                </div>

                <p className="status-line">
                  <Database size={14} />
                  {selectedSourceItem
                    ? tf('ingestPage.status.selectedSourceItem', { name: selectedSourceItem.name || selectedSourceItem.item_key })
                    : t('ingestPage.status.noSourceItem')}
                </p>

                <div className="form-grid cols-2">
                  <label>
                    <span>{t('ingestPage.field.sourceItem')}</span>
                    <select value={form.sourceItemKey} onChange={(e) => onSourceItemChange(e.target.value)}>
                      <option value="">{t('ingestPage.option.sourceItemOptional')}</option>
                      {sourceItemList.map((item) => (
                        <option key={item.item_key} value={item.item_key}>
                          {item.name || item.item_key} ({item.item_key})
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    <span>{t('ingestPage.field.handlerCluster')}</span>
                    <select value={form.sourceHandlerKey} onChange={(e) => setForm((p) => ({ ...p, sourceHandlerKey: e.target.value, sourceItemKey: '' }))}>
                      <option value="">{t('ingestPage.option.handlerOptional')}</option>
                      {handlerKeys.map((key) => (
                        <option key={key} value={key}>
                          {key} ({handlerGroupedByEntryType[key]?.count || 0})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="form-grid cols-2">
                  <label>
                    <span>{t('ingestPage.field.platform')}</span>
                    <input value={form.socialPlatform} onChange={(e) => setForm((p) => ({ ...p, socialPlatform: e.target.value || 'reddit' }))} />
                  </label>
                  <label>
                    <span>{t('ingestPage.field.baseSubreddits')}</span>
                    <input value={form.baseSubreddits} onChange={(e) => setForm((p) => ({ ...p, baseSubreddits: e.target.value }))} />
                  </label>
                </div>

                <label className="single-check">
                  <input type="checkbox" checked={form.enableSubredditDiscovery} onChange={(e) => setForm((p) => ({ ...p, enableSubredditDiscovery: e.target.checked }))} />
                  {t('ingestPage.toggle.subredditDiscovery')}
                </label>

                <div className="inline-actions ingest-flow-actions">
                  <button disabled={actionPending} onClick={onSyncSourceLibrary}>
                    <RefreshCw size={15} />{t('ingestPage.action.syncSourceLibrary')}
                  </button>
                  <button disabled={actionPending || (!form.sourceItemKey && !form.sourceHandlerKey)} onClick={onRunSourceLibrary}>
                    <Play size={15} />{t('ingestPage.action.run')}
                  </button>
                </div>
              </section>

              <section className="ingest-flow-block ingest-page__section ingest-page__section--single-url">
                <div className="panel-header">
                  <h2>
                    <Link2 size={15} />{t('ingestPage.section.singleUrlIngest')}
                  </h2>
                  <span className="chip">single_url</span>
                </div>

                <div className="form-grid cols-2 ingest-single-url-intro">
                  <label>
                    <span>{t('ingestPage.field.targetUrl')}</span>
                    <input value={form.singleUrl} onChange={(e) => setForm((p) => ({ ...p, singleUrl: e.target.value }))} placeholder="https://example.com/article" />
                  </label>
                  <SliderField label={t('ingestPage.field.singleUrlSearchLimit')} min={1} max={20} value={form.singleUrlSearchExpandLimit} onChange={(nextValue) => setForm((p) => ({ ...p, singleUrlSearchExpandLimit: Math.max(1, Math.min(20, nextValue)) }))} />
                </div>

                <div className="form-grid cols-4 ingest-single-url-settings">
                  <label>
                    <span>{t('ingestPage.field.searchProvider')}</span>
                    <select value={form.singleUrlSearchProvider} onChange={(e) => setForm((p) => ({ ...p, singleUrlSearchProvider: e.target.value as IngestFormState['singleUrlSearchProvider'] }))}>
                      <option value="auto">auto</option>
                      <option value="google">google</option>
                      <option value="ddg_html">ddg_html</option>
                    </select>
                  </label>
                  <label>
                    <span>{t('ingestPage.field.fallbackProvider')}</span>
                    <select value={form.singleUrlSearchFallbackProvider} onChange={(e) => setForm((p) => ({ ...p, singleUrlSearchFallbackProvider: e.target.value as IngestFormState['singleUrlSearchFallbackProvider'] }))}>
                      <option value="ddg_html">ddg_html</option>
                    </select>
                  </label>
                  <SliderField label={t('ingestPage.field.minResultsRequired')} min={1} max={20} value={form.singleUrlMinResultsRequired} onChange={(nextValue) => setForm((p) => ({ ...p, singleUrlMinResultsRequired: Math.max(1, Math.min(20, nextValue)) }))} />
                  <SliderField label={t('ingestPage.field.targetCandidates')} min={1} max={20} value={form.singleUrlTargetCandidates} onChange={(nextValue) => setForm((p) => ({ ...p, singleUrlTargetCandidates: Math.max(1, Math.min(20, nextValue)) }))} />
                  <SliderField label={t('ingestPage.field.lightFilterMinScore')} min={0} max={100} value={form.singleUrlLightFilterMinScore} onChange={(nextValue) => setForm((p) => ({ ...p, singleUrlLightFilterMinScore: Math.max(0, Math.min(100, nextValue)) }))} />
                </div>

                <div className="toggles">
                  <label><input type="checkbox" checked={form.singleUrlStrictMode} onChange={(e) => setForm((p) => ({ ...p, singleUrlStrictMode: e.target.checked }))} />{t('ingestPage.toggle.strictMode')}</label>
                  <label><input type="checkbox" checked={form.singleUrlSearchExpand} onChange={(e) => setForm((p) => ({ ...p, singleUrlSearchExpand: e.target.checked }))} />{t('ingestPage.toggle.searchExpand')}</label>
                  <label><input type="checkbox" checked={form.singleUrlFallbackOnInsufficient} onChange={(e) => setForm((p) => ({ ...p, singleUrlFallbackOnInsufficient: e.target.checked }))} />{t('ingestPage.toggle.fallbackOnInsufficient')}</label>
                  <label><input type="checkbox" checked={form.singleUrlAllowSearchSummaryWrite} onChange={(e) => setForm((p) => ({ ...p, singleUrlAllowSearchSummaryWrite: e.target.checked }))} />{t('ingestPage.toggle.allowSearchSummaryWrite')}</label>
                  <label><input type="checkbox" checked={form.singleUrlDecodeRedirectWrappers} onChange={(e) => setForm((p) => ({ ...p, singleUrlDecodeRedirectWrappers: e.target.checked }))} />{t('ingestPage.toggle.decodeRedirectWrappers')}</label>
                  <label><input type="checkbox" checked={form.singleUrlFilterLowValueCandidates} onChange={(e) => setForm((p) => ({ ...p, singleUrlFilterLowValueCandidates: e.target.checked }))} />{t('ingestPage.toggle.filterLowValueCandidates')}</label>
                  <label><input type="checkbox" checked={form.singleUrlLightFilterEnabled} onChange={(e) => setForm((p) => ({ ...p, singleUrlLightFilterEnabled: e.target.checked }))} />{t('ingestPage.toggle.lightFilterEnabled')}</label>
                  <label><input type="checkbox" checked={form.singleUrlLightFilterRejectStaticAssets} onChange={(e) => setForm((p) => ({ ...p, singleUrlLightFilterRejectStaticAssets: e.target.checked }))} />{t('ingestPage.toggle.lightFilterRejectStaticAssets')}</label>
                  <label><input type="checkbox" checked={form.singleUrlLightFilterRejectSearchNoiseDomain} onChange={(e) => setForm((p) => ({ ...p, singleUrlLightFilterRejectSearchNoiseDomain: e.target.checked }))} />{t('ingestPage.toggle.lightFilterRejectSearchNoiseDomain')}</label>
                </div>

                <div className="inline-actions ingest-flow-actions">
                  <button disabled={actionPending || !form.singleUrl.trim()} onClick={onIngestSingleUrl}>
                    <Play size={15} />{t('ingestPage.action.ingestSingleUrl')}
                  </button>
                </div>
              </section>
            </>
          ) : (
            <>
              <section className="ingest-flow-block ingest-page__section ingest-page__section--execution">
                <div className="panel-header">
                  <h2>
                    <Cable size={15} />{t('ingestPage.section.ingestExecution')}
                  </h2>
                </div>

                <div className="form-grid cols-3 ingest-task-controls">
                  <SliderField label={t('ingestPage.field.commodityDays')} min={1} max={365} unit="d" value={form.commodityLimit} onChange={(nextValue) => setForm((p) => ({ ...p, commodityLimit: nextValue }))} />
                  <SliderField label={t('ingestPage.field.ecomLimit')} min={1} max={500} value={form.ecomLimit} onChange={(nextValue) => setForm((p) => ({ ...p, ecomLimit: nextValue }))} />
                </div>

                <div className="action-grid ingest-task-actions">
                  <button disabled={actionPending} onClick={onIngestPolicyRegulation}><Radar size={16} />{t('ingestPage.action.ingestPolicy')}</button>
                  <button disabled={actionPending} onClick={onIngestMarket}><Activity size={16} />{t('ingestPage.action.ingestMarket')}</button>
                  <button disabled={actionPending} onClick={onIngestDataApi}><Globe size={16} />{t('ingestPage.action.ingestDataApi')}</button>
                  <button disabled={actionPending} onClick={onIngestCommodity}><Boxes size={16} />{t('ingestPage.action.ingestCommodity')}</button>
                  <button disabled={actionPending} onClick={onIngestEcom}><Database size={16} />{t('ingestPage.action.ingestEcom')}</button>
                </div>

                <p className="status-line">
                  {actionPending ? <LoaderCircle size={14} className="spinning" /> : <Play size={14} />}
                  {actionMessage}
                </p>
              </section>

              <section className="ingest-flow-block ingest-page__section ingest-page__section--batch">
                <div className="panel-header">
                  <h2>
                    <History size={15} />
                    {t('ingestPage.section.agentBatch')}
                  </h2>
                  <span className="chip">{hasBatch ? tf('ingestPage.status.batchJob', { jobId: agentBatchJobId }) : t('ingestPage.status.batchNotSubmitted')}</span>
                </div>

                <div className="inline-actions ingest-task-toolbar">
                  <button disabled={actionPending} onClick={onSubmitAgentBatch}><Play size={15} />{t('ingestPage.action.submitBatch')}</button>
                  <button disabled={actionPending} onClick={onSubmitNlAgentBatch}><Sparkles size={15} />{t('ingestPage.action.startNlCommand')}</button>
                  {hasBatch ? (
                    <button disabled={actionPending} onClick={onRefreshBatchStatus}>
                      <RefreshCw size={15} />{t('ingestPage.action.refreshBatchStatus')}
                    </button>
                  ) : null}
                </div>

                {batchSummaryParts.length > 0 ? (
                  <div className="ingest-task-summary">
                    {batchSummaryParts.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                ) : null}

                {hasBatch ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('ingestPage.table.item')}</th>
                          <th>{t('ingestPage.table.task')}</th>
                          <th>{t('ingestPage.table.status')}</th>
                          <th>{t('ingestPage.table.error')}</th>
                          <th>{t('ingestPage.table.action')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {agentBatchItems.map((item, idx) => (
                          <tr key={`${item.item_id || 'item'}-${idx}`}>
                            <td>{item.item_id || '-'}</td>
                            <td>{item.task_id || '-'}</td>
                            <td><span className={statusClass(item.status)}>{item.status || '-'}</span></td>
                            <td>{toErrorText(item.error) || '-'}</td>
                            <td>
                              <button disabled={actionPending || !isFailedStatus(item.status)} onClick={() => onRetryBatchItem(item)}>
                                <RotateCcw size={14} />{t('ingestPage.action.retry')}
                              </button>
                            </td>
                          </tr>
                        ))}
                        {!agentBatchItems.length ? (
                          <tr>
                            <td colSpan={5} className="empty-cell">{t('ingestPage.empty.batchItems')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                ) : null}

                {hasBatch ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('ingestPage.table.time')}</th>
                          <th>{t('ingestPage.table.event')}</th>
                          <th>{t('ingestPage.table.item')}</th>
                          <th>{t('ingestPage.table.message')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {agentBatchEvents.slice(0, 20).map((event, idx) => (
                          <tr key={`${event.id || 'evt'}-${idx}`}>
                            <td>{formatDate(event.ts, locale)}</td>
                            <td>{event.event_type || '-'}</td>
                            <td>{event.item_id || '-'}</td>
                            <td>{event.message || '-'}</td>
                          </tr>
                        ))}
                        {!agentBatchEvents.length ? (
                          <tr>
                            <td colSpan={4} className="empty-cell">{t('ingestPage.empty.batchEvents')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </section>
            </>
          )}
        </div>

        <aside className="ingest-workspace__secondary">
          <section className="ingest-flow-block ingest-flow-block--history ingest-page__section ingest-page__section--history">
            <div className="panel-header">
              <h2>{t('ingestPage.section.recentTaskStatus')}</h2>
              <button onClick={onRefreshHistory}>
                <RefreshCw size={14} />{t('ingestPage.action.refresh')}
              </button>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t('ingestPage.table.task')}</th>
                    <th>{t('ingestPage.table.status')}</th>
                    <th>{t('ingestPage.table.rejectionCount')}</th>
                    <th>{t('ingestPage.table.degradationFlags')}</th>
                    <th>{t('ingestPage.table.startedAt')}</th>
                    <th>{t('ingestPage.table.finishedAt')}</th>
                  </tr>
                </thead>
                <tbody>
                  {historyRows.map((row, idx) => (
                    <tr key={`${row.id || row.task_id || idx}`}>
                      <td>{rowTaskName(row)}</td>
                      <td><span className={statusClass(row.status)}>{row.status || '-'}</span></td>
                      <td>{rowRejectionCount(row)}</td>
                      <td>{rowDegradationFlags(row).slice(0, 2).join(', ') || '-'}</td>
                      <td>{formatDate(rowStartAt(row), locale)}</td>
                      <td>{formatDate(rowEndAt(row), locale)}</td>
                    </tr>
                  ))}
                  {!historyRows.length ? (
                    <tr>
                      <td colSpan={6} className="empty-cell">{t('ingestPage.empty.history')}</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
