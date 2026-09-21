import { useCallback, useMemo, useState } from 'react'
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
  registerExternalProject,
  refreshSourceLibraryItem,
  recommendSiteEntriesBatch,
  recommendSiteEntry,
  simplifySiteEntries,
  syncSourceLibraryHandlerClusters,
  runSourceLibrary,
  upsertSourceLibraryItem,
  upsertSiteEntry,
} from '../lib/api'
import { patchSiteEntryLifecycle } from '../lib/api/domains/resource-source'
import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'
import { queryKeys } from '../lib/queryKeys'
import type {
  ResourcePoolRecommendationItem,
  ResourcePoolRecommendationResponse,
  ResourcePoolSiteEntryLifecycleState,
  SiteEntryItem,
  SourceLibraryItem,
  SourceLibraryScope,
} from '../lib/types'

type ResourcePageProps = {
  projectKey: string
  variant?: 'resource' | 'extract'
}

type ResourceMessageKey = MessageKey
type ResourceFactFormatter = (key: ResourceMessageKey, values: Record<string, string | number | boolean>) => string

const DEFAULT_EXTERNAL_HINTS_JSON = JSON.stringify({ query_terms: [] }, null, 2)

function formatResourceTemplate(template: string, values: Record<string, string | number | boolean>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
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

function asRecord(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function hasRecordFields(value: Record<string, unknown>) {
  return Object.keys(value).length > 0
}

function compactValue(value: unknown) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function summarizeCapabilityValue(value: unknown, formatFact?: ResourceFactFormatter) {
  const direct = compactValue(value)
  if (direct) return direct

  const payload = asRecord(value)
  const parts = [
    compactValue(payload.capability_id || payload.name || payload.summary),
    compactValue(payload.execution_mode || payload.source_mode),
    compactValue(payload.entry_type),
    compactValue(payload.status),
  ].filter(Boolean)
  if (typeof payload.enabled === 'boolean') {
    parts.push(formatFact ? formatFact('resourcePage.fact.enabled', { value: String(payload.enabled) }) : String(payload.enabled))
  }
  return parts.slice(0, 4).join(' | ')
}

function formatPlanDetailRows(rows: Array<[string, unknown]>) {
  return rows
    .map(([label, value]) => [label, compactValue(value)] as const)
    .filter(([, value]) => Boolean(value))
}

function renderPlanDetailGrid(rows: Array<readonly [string, string]>) {
  if (!rows.length) return null
  return (
    <dl className="resource-page__plan-detail-grid">
      {rows.flatMap(([label, value]) => [
        <dt key={`label:${label}:${value}`} style={{ color: 'var(--muted)', fontSize: 12 }}>
          {label}
        </dt>,
        <dd key={`value:${label}:${value}`} style={{ margin: 0, wordBreak: 'break-word' }}>
          {value}
        </dd>,
      ])}
    </dl>
  )
}

function getItemCapabilityValue(item: SourceLibraryItem) {
  const extra = asRecord(item.extra)
  return item.capability_summary ?? item.capability ?? extra.capability_summary ?? extra.capability ?? extra.capability_profile
}

function getItemExecutionPlanRows(item: SourceLibraryItem) {
  const extra = asRecord(item.extra)
  const params = asRecord(item.params)
  const executionPlan = asRecord(item.execution_plan)
  const planMeta = asRecord(executionPlan.plan_meta)
  const externalProject = asRecord(planMeta.external_project)
  const capability = asRecord(getItemCapabilityValue(item))
  const runner = asRecord(executionPlan.runner)
  return formatPlanDetailRows([
    ['contract_version', executionPlan.contract_version || capability.contract_version],
    ['execution_mode', executionPlan.execution_mode || externalProject.execution_mode || capability.execution_mode],
    ['runner', executionPlan.runner_key || runner.runner_key || runner.name || runner.type || capability.runner_ref || capability.runner],
    ['source_mode', executionPlan.source_mode || params.source_mode || capability.source_mode],
    ['entry_type', executionPlan.expected_entry_type || extra.expected_entry_type || capability.entry_type],
  ])
}

function getItemExecutabilityFacts(item: SourceLibraryItem, formatFact?: ResourceFactFormatter) {
  const extra = asRecord(item.extra)
  const params = asRecord(item.params)
  const executionPlan = asRecord(item.execution_plan)
  const planMeta = asRecord(executionPlan.plan_meta)
  const externalProject = asRecord(planMeta.external_project)
  const capability = getItemCapabilityValue(item)
  const capabilitySummary = summarizeCapabilityValue(capability, formatFact)
  const fact = (key: ResourceMessageKey, values: Record<string, string | number | boolean>) =>
    formatFact ? formatFact(key, values) : Object.values(values).join(':')
  const facts = [
    compactValue(item.managed_by || extra.managed_by) ? fact('resourcePage.fact.managedBy', { value: compactValue(item.managed_by || extra.managed_by) }) : '',
    compactValue(item.item_type || extra.item_type) ? fact('resourcePage.fact.itemType', { value: compactValue(item.item_type || extra.item_type) }) : '',
    capabilitySummary ? fact('resourcePage.fact.capability', { value: capabilitySummary }) : '',
    compactValue(externalProject.execution_mode) ? fact('resourcePage.fact.mode', { value: compactValue(externalProject.execution_mode) }) : '',
    compactValue(params.source_mode) ? fact('resourcePage.fact.sourceMode', { value: compactValue(params.source_mode) }) : '',
    compactValue(extra.expected_entry_type) ? fact('resourcePage.fact.entryType', { value: compactValue(extra.expected_entry_type) }) : '',
  ].filter(Boolean)
  return Array.from(new Set(facts)).slice(0, 5)
}

function renderItemExecutability(item: SourceLibraryItem, formatFact: ResourceFactFormatter) {
  const facts = getItemExecutabilityFacts(item, formatFact)
  const executionPlan = asRecord(item.execution_plan)
  const capability = getItemCapabilityValue(item)
  const capabilityRecord = asRecord(capability)
  const planRows = getItemExecutionPlanRows(item)
  const hasExecutionPlan = Object.keys(executionPlan).length > 0
  const hasCapability = Boolean(compactValue(capability)) || Object.keys(capabilityRecord).length > 0
  if (!facts.length && !planRows.length && !hasExecutionPlan && !hasCapability) return '-'
  return (
    <details>
      <summary style={{ cursor: 'pointer' }}>
        <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 6 }}>
          {(facts.length ? facts : planRows.map(([label, value]) => `${label}:${value}`).slice(0, 3)).map((fact) => (
            <span className="chip" key={fact} title={fact}>
              {fact.length > 56 ? `${fact.slice(0, 53)}...` : fact}
            </span>
          ))}
        </span>
      </summary>
      {renderPlanDetailGrid(planRows)}
      {hasCapability ? (
        <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {JSON.stringify({ capability_summary: capability }, null, 2)}
        </pre>
      ) : null}
      {hasExecutionPlan ? (
        <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {JSON.stringify({ execution_plan: item.execution_plan }, null, 2)}
        </pre>
      ) : null}
    </details>
  )
}

function getSiteEntryReviewState(item: SiteEntryItem) {
  const extra = asRecord(item.extra)
  const lifecycleReview = asRecord(extra.lifecycle_review)
  return compactValue(extra.review_state || lifecycleReview.review_state || lifecycleReview.state)
}

function getSiteEntryPlanFacts(item: SiteEntryItem, formatFact: ResourceFactFormatter) {
  const plan = asRecord(item.execution_plan_preview)
  const planMeta = asRecord(plan.plan_meta)
  const routeCounts = asRecord(plan.route_bucket_counts)
  const urls = Array.isArray(plan.site_entry_urls) ? plan.site_entry_urls : []
  return [
    compactValue(plan.expected_entry_type) ? formatFact('resourcePage.fact.expected', { value: compactValue(plan.expected_entry_type) }) : '',
    urls.length ? formatFact('resourcePage.fact.urls', { count: urls.length }) : '',
    compactValue(routeCounts.total) ? formatFact('resourcePage.fact.routes', { value: compactValue(routeCounts.total) }) : '',
    compactValue(planMeta.preview_source) ? formatFact('resourcePage.fact.preview', { value: compactValue(planMeta.preview_source) }) : '',
  ].filter(Boolean)
}

function getSiteEntryPlanRows(item: SiteEntryItem) {
  const plan = asRecord(item.execution_plan_preview)
  const planMeta = asRecord(plan.plan_meta)
  const routeCounts = asRecord(plan.route_bucket_counts)
  const routeBucketSummary = Object.entries(routeCounts)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}:${String(value)}`)
    .join(' | ')
  const urls = Array.isArray(plan.site_entry_urls) ? plan.site_entry_urls : []
  return formatPlanDetailRows([
    ['expected_entry_type', plan.expected_entry_type],
    ['preview_source', planMeta.preview_source],
    ['route_bucket', routeBucketSummary],
    ['site_entry_urls', urls.length ? urls.length : ''],
    ['contract_version', plan.contract_version],
  ])
}

function renderSiteEntryLifecycle(item: SiteEntryItem, formatFact: ResourceFactFormatter) {
  const summary = asRecord(item.lifecycle_summary)
  const transition = getSiteEntryLifecycleTransition(item)
  const closure = getSiteEntryReviewClosure(item)
  const state = compactValue(item.lifecycle_state || summary.state) || (item.enabled === false ? 'disabled' : 'active')
  const reviewState = getSiteEntryReviewState(item)
  const stateSource = compactValue(summary.state_source)
  const transitionState = compactValue(transition.to_state || transition.status)
  const transitionReason = compactValue(transition.reason_code || transition.reason)
  const closureStatus = compactValue(closure.status)
  const closureReason = compactValue(closure.reason_code || closure.block_reason)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span className="chip">{formatFact('resourcePage.fact.lifecycle', { value: state })}</span>
      {reviewState ? <span className="chip">{formatFact('resourcePage.fact.review', { value: reviewState })}</span> : null}
      {transitionState ? (
        <span className="chip">{formatFact('resourcePage.fact.lifecycleTransition', { value: transitionState })}</span>
      ) : null}
      {transitionReason ? (
        <span className="chip">{formatFact('resourcePage.fact.reason', { value: transitionReason })}</span>
      ) : null}
      {closureStatus ? (
        <span className="chip">{formatFact('resourcePage.fact.reviewClosure', { value: closureStatus })}</span>
      ) : null}
      {closureReason ? (
        <span className="chip">{formatFact('resourcePage.fact.reason', { value: closureReason })}</span>
      ) : null}
      {stateSource ? <small>{stateSource}</small> : null}
    </div>
  )
}

function renderSiteEntryPlanPreview(item: SiteEntryItem, formatFact: ResourceFactFormatter) {
  const facts = getSiteEntryPlanFacts(item, formatFact)
  const rows = getSiteEntryPlanRows(item)
  if (!facts.length && !rows.length) return '-'
  return (
    <details>
      <summary style={{ cursor: 'pointer' }}>
        <span className="chip">{facts.join(' | ')}</span>
      </summary>
      {renderPlanDetailGrid(rows)}
      <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {JSON.stringify(item.execution_plan_preview, null, 2)}
      </pre>
    </details>
  )
}

function getSiteEntryReviewClosure(item: SiteEntryItem) {
  const extra = asRecord(item.extra)
  return asRecord(item.review_closure || extra.review_closure)
}

function getSiteEntryLifecycleTransition(item: SiteEntryItem) {
  const extra = asRecord(item.extra)
  const summary = asRecord(item.lifecycle_summary)
  return asRecord(item.lifecycle_transition || summary.lifecycle_transition || extra.lifecycle_transition)
}

function getSiteEntryExecutionFact(item: SiteEntryItem) {
  const extra = asRecord(item.extra)
  return asRecord(item.execution_fact || extra.execution_fact)
}

function getSiteEntryEvidenceBinding(item: SiteEntryItem) {
  const closure = getSiteEntryReviewClosure(item)
  const extra = asRecord(item.extra)
  return asRecord(item.evidence_binding || closure.evidence_binding || extra.evidence_binding)
}

function getSiteEntryNextActions(item: SiteEntryItem) {
  const closure = getSiteEntryReviewClosure(item)
  const extra = asRecord(item.extra)
  const raw = Array.isArray(item.next_actions)
    ? item.next_actions
    : Array.isArray(closure.next_actions)
      ? closure.next_actions
      : Array.isArray(extra.next_actions)
        ? extra.next_actions
        : []
  return raw.filter((action) => action && typeof action === 'object') as Record<string, unknown>[]
}

function getSiteEntryCollectAction(item: SiteEntryItem) {
  return getSiteEntryNextActions(item).find((action) => compactValue(action.action) === 'collect_source_library_run') || {}
}

function getSiteEntryActionGuard(action: Record<string, unknown>) {
  const payload = asRecord(action.payload)
  const overrideParams = asRecord(payload.override_params)
  return asRecord(action.single_source_guard || action.strict_source || overrideParams.single_source_guard)
}

function getSiteEntrySingleSourceGuard(item: SiteEntryItem) {
  const collectAction = getSiteEntryCollectAction(item)
  const closure = getSiteEntryReviewClosure(item)
  const executionFact = getSiteEntryExecutionFact(item)
  const actionGuard = getSiteEntryActionGuard(collectAction)
  if (hasRecordFields(actionGuard)) return actionGuard
  const closureGuard = asRecord(closure.single_source_guard || closure.strict_source)
  if (hasRecordFields(closureGuard)) return closureGuard
  return asRecord(executionFact.single_source_guard)
}

function siteEntryAcceptedCollectEnabled(item: SiteEntryItem) {
  const action = getSiteEntryCollectAction(item)
  const closure = getSiteEntryReviewClosure(item)
  const executionFact = getSiteEntryExecutionFact(item)
  const guard = getSiteEntryActionGuard(action)
  const state = compactValue(item.lifecycle_state || closure.state)
  const guardStatus = compactValue(guard.status || executionFact.guard_status)
  return state === 'accepted' && action.enabled === true && !action.blocked && guardStatus === 'passed'
}

function appendEvidenceRows(
  rows: Array<[string, unknown]>,
  prefix: string,
  payload: Record<string, unknown>,
  fields: string[],
) {
  fields.forEach((field) => {
    rows.push([`${prefix}.${field}`, payload[field]])
  })
}

function getSiteEntryLifecycleEvidenceRows(item: SiteEntryItem) {
  const transition = getSiteEntryLifecycleTransition(item)
  const closure = getSiteEntryReviewClosure(item)
  const guard = getSiteEntrySingleSourceGuard(item)
  const executionFact = getSiteEntryExecutionFact(item)
  const rows: Array<[string, unknown]> = []
  appendEvidenceRows(rows, 'lifecycle_transition', transition, ['to_state', 'status', 'reason_code', 'reason'])
  appendEvidenceRows(rows, 'review_closure', closure, ['status', 'reason_code', 'block_reason', 'report_source_ref'])
  appendEvidenceRows(rows, 'single_source_guard', guard, [
    'status',
    'allowed_count',
    'reason_code',
    'blocked_reason',
    'report_source_ref',
  ])
  appendEvidenceRows(rows, 'execution_fact', executionFact, [
    'reason_code',
    'guard_status',
    'guard_reason_code',
    'fact_ref',
    'report_source_ref',
  ])
  return formatPlanDetailRows(rows)
}

function renderSiteEntryLifecycleEvidence(item: SiteEntryItem) {
  const rows = getSiteEntryLifecycleEvidenceRows(item)
  if (!rows.length) return null
  return (
    <details>
      <summary style={{ cursor: 'pointer' }}>lifecycle evidence</summary>
      {renderPlanDetailGrid(rows)}
    </details>
  )
}

function renderSiteEntryNextActions(item: SiteEntryItem, formatFact: ResourceFactFormatter) {
  const closure = getSiteEntryReviewClosure(item)
  const evidenceBinding = getSiteEntryEvidenceBinding(item)
  const reportSourceRef = compactValue(evidenceBinding.report_source_ref || closure.report_source_ref)
  const actions = getSiteEntryNextActions(item)
  const evidence = renderSiteEntryLifecycleEvidence(item)
  if (!actions.length && !reportSourceRef && !evidence) return '-'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {reportSourceRef ? (
        <span className="chip" title={reportSourceRef}>
          {formatFact('resourcePage.fact.sourceRef', { value: reportSourceRef.length > 44 ? `${reportSourceRef.slice(0, 41)}...` : reportSourceRef })}
        </span>
      ) : null}
      {actions.map((action, idx) => {
        const name = compactValue(action.action) || formatFact('resourcePage.fact.actionFallback', { index: idx })
        const blockReason = compactValue(action.block_reason)
        const guard = getSiteEntryActionGuard(action)
        const guardStatus = compactValue(guard.status)
        const allowedCount = compactValue(guard.allowed_count)
        const blocked = Boolean(action.blocked) || action.enabled === false
        return (
          <div key={`${name}-${idx}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            <span className="chip" title={blockReason || name}>
              {formatFact('resourcePage.fact.actionState', {
                name,
                state: blocked ? blockReason || 'blocked' : 'enabled',
              })}
            </span>
            {guardStatus ? (
              <span className="chip">{formatFact('resourcePage.fact.guardStatus', { value: guardStatus })}</span>
            ) : null}
            {allowedCount ? (
              <span className="chip">{formatFact('resourcePage.fact.allowedCount', { value: allowedCount })}</span>
            ) : null}
          </div>
        )
      })}
      {evidence}
    </div>
  )
}

function formatDate(value: string | null | undefined, locale: string) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString(locale)
}

function renderUrlFold(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw) return '-'
  if (raw.length <= 72) return raw
  const short = raw.slice(0, 48) + '...' + raw.slice(-16)
  return (
    <details>
      <summary title={raw} style={{ cursor: 'pointer' }}>
        {short}
      </summary>
      <div style={{ marginTop: 6, wordBreak: 'break-all' }}>{raw}</div>
    </details>
  )
}

function parseJsonObjectInput(raw: string, invalidObjectMessage: string) {
  const text = raw.trim()
  if (!text) return {}
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(invalidObjectMessage)
  }
  return parsed as Record<string, unknown>
}

function getExternalProjectPlan(item: SourceLibraryItem | null | undefined) {
  const executionPlan = item?.execution_plan
  if (!executionPlan || typeof executionPlan !== 'object') return {}
  const planMeta = (executionPlan as Record<string, unknown>).plan_meta
  if (!planMeta || typeof planMeta !== 'object') return {}
  const externalProject = (planMeta as Record<string, unknown>).external_project
  return externalProject && typeof externalProject === 'object' ? (externalProject as Record<string, unknown>) : {}
}

function getResultTraceId(payload: Record<string, unknown>) {
  const meta = asRecord(payload.meta)
  const traceChain = asRecord(payload.trace_chain)
  return compactValue(payload.trace_id || meta.trace_id || traceChain.trace_id)
}

export function ResourcePage({ projectKey, variant = 'resource' }: ResourcePageProps) {
  const locale = useAppLocale()
  const queryClient = useQueryClient()
  const t = (key: ResourceMessageKey, fallback?: string) => translate(locale, key, fallback)
  const tf = useCallback(
    (key: ResourceMessageKey, values: Record<string, string | number | boolean>) =>
      formatResourceTemplate(translate(locale, key), values),
    [locale],
  )
  const errorMessage = (error: unknown) => (error instanceof Error ? error.message : t('resourcePage.error.unknown'))

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
  const [externalProjectForm, setExternalProjectForm] = useState({
    project_link: '',
    item_key: '',
    name: '',
    description: '',
    tags: '',
    enabled: true,
    hints_json: DEFAULT_EXTERNAL_HINTS_JSON,
  })
  const [externalProjectPreview, setExternalProjectPreview] = useState<Record<string, unknown> | null>(null)

  const [domainFilter, setDomainFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [entryTypeFilter, setEntryTypeFilter] = useState('')

  const [resourceUrlPage, setResourceUrlPage] = useState(1)
  const [resourceSitePage, setResourceSitePage] = useState(1)

  const [newSiteUrl, setNewSiteUrl] = useState('')
  const [newSiteEntryType, setNewSiteEntryType] = useState('domain_root')

  const [actionPending, setActionPending] = useState(false)
  const [actionMessage, setActionMessage] = useState(() => t('resourcePage.status.ready'))
  const [actionError, setActionError] = useState('')

  const [discoverLimitDomains, setDiscoverLimitDomains] = useState('60')
  const [discoverDryRun, setDiscoverDryRun] = useState(false)

  const [recommendSiteUrl, setRecommendSiteUrl] = useState('')
  const [recommendEntryType, setRecommendEntryType] = useState('domain_root')
  const [recommendUseLlm, setRecommendUseLlm] = useState(true)
  const [singleRecommendation, setSingleRecommendation] = useState<ResourcePoolRecommendationResponse | null>(null)
  const [batchRecommendations, setBatchRecommendations] = useState<ResourcePoolRecommendationItem[]>([])
  const [bindingPending, setBindingPending] = useState(false)

  const handleDomainFilterChange = useCallback((value: string) => {
    setDomainFilter(value)
    setResourceUrlPage(1)
    setResourceSitePage(1)
  }, [])

  const handleSourceFilterChange = useCallback((value: string) => {
    setSourceFilter(value)
    setResourceUrlPage(1)
    setResourceSitePage(1)
  }, [])

  const handleEntryTypeFilterChange = useCallback((value: string) => {
    setEntryTypeFilter(value)
    setResourceUrlPage(1)
    setResourceSitePage(1)
  }, [])

  const sourceItems = useQuery({
    queryKey: queryKeys.sourceLibrary.items(projectKey, sourceScope),
    queryFn: () => listSourceLibraryItemsWithScope(sourceScope),
    enabled: Boolean(projectKey),
  })

  const sourceItemsGrouped = useQuery({
    queryKey: queryKeys.sourceLibrary.itemsGrouped(projectKey, sourceScope),
    queryFn: () => listSourceLibraryItemsGrouped(sourceScope),
    enabled: Boolean(projectKey),
  })

  const sourceChannels = useQuery({
    queryKey: queryKeys.sourceLibrary.channels(projectKey, sourceScope),
    queryFn: () => listSourceLibraryChannels(sourceScope),
    enabled: Boolean(projectKey),
  })

  const resourceUrls = useQuery({
    queryKey: queryKeys.resource.urls(projectKey, domainFilter, sourceFilter, resourceUrlPage),
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
    queryKey: queryKeys.resource.siteEntries(projectKey, domainFilter, entryTypeFilter, resourceSitePage),
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
      if (!newSiteUrl.trim()) throw new Error(t('resourcePage.error.missingSiteUrl'))
      return upsertSiteEntry({
        site_url: newSiteUrl.trim(),
        entry_type: newSiteEntryType,
        scope: 'project',
      })
    },
    onSuccess: async () => {
      setNewSiteUrl('')
      setActionMessage(t('resourcePage.message.siteEntryCreated'))
      await queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) })
    },
    onError: (error) => {
      setActionMessage(tf('resourcePage.message.siteEntryCreateFailed', { message: errorMessage(error) }))
    },
  })

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    setActionPending(true)
    setActionError('')
    setActionMessage(tf('resourcePage.status.running', { action: name }))
    try {
      const result = await fn()
      const payload = result && typeof result === 'object' ? (result as Record<string, unknown>) : {}
      const details = [
        'task_id',
        'trace_id',
        'item_key',
        'handler_key',
        'handler_count',
        'written',
        'inserted',
        'updated',
        'skipped',
        'added',
        'site_entries_after',
        'site_url',
        'lifecycle_state',
        'enabled',
        'handler_key',
        'report_source_ref',
        'guard_status',
        'allowed_count',
        'copied',
        'errors',
      ]
        .filter((key) => payload[key] !== undefined && payload[key] !== null && payload[key] !== '')
        .map((key) => `${key}=${String(payload[key])}`)
        .join(' | ')

      setActionMessage(
        payload.task_id && payload.async !== false
          ? tf('resourcePage.status.submittedWithDetails', { action: name, details })
          : details
          ? tf('resourcePage.status.completedWithDetails', { action: name, details })
          : tf('resourcePage.status.completed', { action: name }),
      )

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.resource.urlsBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) }),
      ])
    } catch (error) {
      const message = errorMessage(error)
      setActionMessage(tf('resourcePage.status.failed', { action: name }))
      setActionError(tf('resourcePage.status.failedWithMessage', { action: name, message }))
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
    if (!item.site_url) throw new Error(t('resourcePage.error.missingBindSiteUrl'))
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

  const runExternalProjectAction = async (persist: boolean) => {
    const projectLink = externalProjectForm.project_link.trim()
    if (!projectLink) throw new Error(t('resourcePage.error.missingProjectLink'))
    const response = await registerExternalProject({
      project_link: projectLink,
      item_key: externalProjectForm.item_key.trim() || undefined,
      name: externalProjectForm.name.trim() || undefined,
      description: externalProjectForm.description.trim() || undefined,
      tags: splitToList(externalProjectForm.tags),
      enabled: externalProjectForm.enabled,
      persist,
      hints: parseJsonObjectInput(externalProjectForm.hints_json, t('resourcePage.error.hintsJsonObject')),
    })
    const payload = response && typeof response === 'object' ? (response as Record<string, unknown>) : {}
    setExternalProjectPreview(payload)
    const item = payload.item
    if (item && typeof item === 'object') {
      fillItemForm(item as SourceLibraryItem)
    }
    if (persist) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.channelsBase(projectKey) }),
      ])
    }
    const itemPayload = item && typeof item === 'object' ? (item as SourceLibraryItem) : null
    const externalPlan = getExternalProjectPlan(itemPayload)
    const registrationContext =
      payload.registration_context && typeof payload.registration_context === 'object'
        ? (payload.registration_context as Record<string, unknown>)
        : {}
    const endpointCandidates = Array.isArray(registrationContext.endpoint_candidates)
      ? registrationContext.endpoint_candidates.length
      : 0
    return {
      item_key: itemPayload?.item_key || '-',
      persisted: String(Boolean(payload.persisted)),
      execution_mode: String(externalPlan.execution_mode || '-'),
      endpoint_candidates: endpointCandidates,
    }
  }

  const saveSourceItem = async () => {
    const itemKey = itemForm.item_key.trim()
    const name = itemForm.name.trim()
    const channelKey = itemForm.channel_key.trim()
    if (!itemKey || !name || !channelKey) {
      throw new Error(t('resourcePage.error.missingSourceItemRequired'))
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
    if (!item?.item_key) throw new Error(t('resourcePage.error.missingItemKey'))
    if (!handlerKey || handlerKey === 'url_routing') throw new Error(t('resourcePage.error.unsupportedHandler'))

    const rawParams = item.params && typeof item.params === 'object' ? { ...item.params } : {}
    rawParams.site_entries = getItemSiteEntries(item)
    delete (rawParams as Record<string, unknown>).site_entry_urls
    const rawExtra = item.extra && typeof item.extra === 'object' ? { ...item.extra } : {}
    rawExtra.creation_handler = ['handler', 'entry_type'].join('.')
    rawExtra.expected_entry_type = handlerKey
    if (rawExtra.auto_maintain == null) rawExtra.auto_maintain = true

    await upsertSourceLibraryItem({
      item_key: item.item_key,
      name: item.name || item.item_key,
      channel_key: item.channel_key || ['handler', 'cluster'].join('.'),
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
          const haystack = [
            handlerKey,
            item.item_key || '',
            item.name || '',
            item.channel_key || '',
            ...getItemExecutabilityFacts(item, tf),
          ]
            .join(' ')
            .toLowerCase()
          return haystack.includes(keyword)
        })
        if (String(handlerKey).toLowerCase().includes(keyword)) {
          return { handlerKey, total: list.length, items: list }
        }
        if (!filtered.length) return null
        return { handlerKey, total: list.length, items: filtered }
      })
      .filter(Boolean) as Array<{ handlerKey: string; total: number; items: SourceLibraryItem[] }>
  }, [sourceItemsGrouped.data, handlerSearch, tf])

  const bindAllRecommendations = async () => {
    if (!batchRecommendations.length && !singleRecommendation) {
      setActionError(t('resourcePage.error.noBindableRecommendation'))
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
      setActionMessage(tf('resourcePage.message.bindCompleted', { success, failed }))
      await queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) })
    } catch (error) {
      setActionError(tf('resourcePage.message.bindAllFailed', { message: errorMessage(error) }))
    } finally {
      setBindingPending(false)
    }
  }

  const reviewSiteEntryLifecycle = async (item: SiteEntryItem, lifecycleState: ResourcePoolSiteEntryLifecycleState) => {
    if (!item.site_url) throw new Error(t('resourcePage.error.missingSiteUrl'))
    const response = await patchSiteEntryLifecycle({
      project_key: projectKey,
      scope: item.scope === 'shared' ? 'shared' : 'project',
      site_url: item.site_url,
      lifecycle_state: lifecycleState,
      reviewer: 'resource_page_manual_review',
      review_reason: 'frontend_resource_pool_review_workbench',
    })
    return {
      site_url: response.site_url || item.site_url,
      lifecycle_state: response.lifecycle_state || lifecycleState,
      enabled: String(response.enabled ?? item.enabled ?? true),
      report_source_ref: compactValue(response.evidence_binding?.report_source_ref || response.review_closure?.report_source_ref),
    }
  }

  const runAcceptedSiteEntryCollect = async (item: SiteEntryItem) => {
    if (!item.site_url) throw new Error(t('resourcePage.error.missingSiteUrl'))
    const action = getSiteEntryCollectAction(item)
    if (!siteEntryAcceptedCollectEnabled(item)) {
      throw new Error(compactValue(action.block_reason) || t('resourcePage.error.reviewBlocked'))
    }
    const payload = asRecord(action.payload)
    const overrideParams = asRecord(payload.override_params)
    const evidenceBinding = getSiteEntryEvidenceBinding(item)
    const sourceRef = asRecord(evidenceBinding.source_ref)
    const singleSourceGuard = getSiteEntryActionGuard(action)
    const reportSourceRef = compactValue(evidenceBinding.report_source_ref || payload.report_source_ref)
    const handlerKey = compactValue(payload.handler_key || action.handler_key || item.entry_type) || 'domain_root'
    const result = await runSourceLibrary({
      item_key: null,
      handler_key: handlerKey,
      source_mode: compactValue(payload.source_mode) || null,
      async_mode: true,
      override_params: {
        ...overrideParams,
        site_entries: [item.site_url],
        source_ref: Object.keys(sourceRef).length ? sourceRef : { site_entry_url: item.site_url },
        report_source_ref: reportSourceRef,
        ...(hasRecordFields(singleSourceGuard) ? { single_source_guard: singleSourceGuard } : {}),
      },
    })
    const resultPayload = result && typeof result === 'object' ? (result as Record<string, unknown>) : {}
    const resultGuard = asRecord(resultPayload.single_source_guard || resultPayload.strict_source || singleSourceGuard)
    const resultExecutionFact = asRecord(resultPayload.execution_fact)
    return {
      ...resultPayload,
      handler_key: handlerKey,
      site_url: item.site_url,
      trace_id: getResultTraceId(resultPayload),
      report_source_ref: reportSourceRef || compactValue(resultExecutionFact.report_source_ref),
      guard_status: compactValue(resultGuard.status || resultExecutionFact.guard_status),
      allowed_count: compactValue(resultGuard.allowed_count),
    }
  }

  const copySiteEntrySourceRef = async (item: SiteEntryItem) => {
    const closure = getSiteEntryReviewClosure(item)
    const evidenceBinding = getSiteEntryEvidenceBinding(item)
    const reportSourceRef = compactValue(evidenceBinding.report_source_ref || closure.report_source_ref)
    const sourceRef = asRecord(evidenceBinding.source_ref || closure.source_ref || item.source_ref)
    if (!reportSourceRef && !Object.keys(sourceRef).length) throw new Error(t('resourcePage.error.missingSourceRef'))
    if (!navigator.clipboard?.writeText) throw new Error(t('resourcePage.error.clipboardUnavailable'))
    await navigator.clipboard.writeText(
      JSON.stringify(
        {
          report_source_ref: reportSourceRef || null,
          source_ref: sourceRef,
          site_entry_url: item.site_url || null,
        },
        null,
        2,
      ),
    )
    return {
      copied: 'true',
      report_source_ref: reportSourceRef || '-',
    }
  }

  return (
    <div className={`content-stack resource-page resource-page--${variant}`}>
      <section className="panel">
        <div className="panel-header">
          <h2>{t(variant === 'extract' ? 'resourcePage.title.extract' : 'resourcePage.title.resource')}</h2>
          <span className="chip">{variant === 'extract' ? 'extract' : 'resource'}</span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.title.resource')}</h2>
          <span className="chip">{tf('resourcePage.meta.project', { projectKey })}</span>
        </div>

        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.domain')}</span>
            <input
              value={domainFilter}
              onChange={(e) => handleDomainFilterChange(e.target.value)}
              placeholder={t('resourcePage.placeholder.domain')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.source')}</span>
            <input
              value={sourceFilter}
              onChange={(e) => handleSourceFilterChange(e.target.value)}
              placeholder={t('resourcePage.placeholder.source')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.entryType')}</span>
            <input
              value={entryTypeFilter}
              onChange={(e) => handleEntryTypeFilterChange(e.target.value)}
              placeholder={t('resourcePage.placeholder.entryType')}
            />
          </label>
          <div className="inline-actions">
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: queryKeys.resource.urlsBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.channelsBase(projectKey) })
              }}
            >
              <RefreshCw size={14} />{t('resourcePage.action.refreshList')}
            </button>
          </div>
        </div>

        <div className="action-grid">
          <button disabled={actionPending} onClick={() => runAction(t('resourcePage.actionName.extractUrls'), () => extractResourcePoolFromDocuments(true))}>
            <Play size={16} />{t('resourcePage.action.extractUrls')}
          </button>
          <button
            disabled={actionPending}
            onClick={() =>
              runAction(t('resourcePage.actionName.discoverEntries'), () =>
                discoverSiteEntriesAdvanced({
                  limit_domains: Math.max(1, Number.parseInt(discoverLimitDomains, 10) || 60),
                  dry_run: discoverDryRun,
                  write: !discoverDryRun,
                  async_mode: true,
                }),
              )
            }
          >
            <Radar size={16} />{t('resourcePage.action.discoverEntries')}
          </button>
          <button disabled={actionPending} onClick={() => runAction(t('resourcePage.actionName.simplifyEntries'), () => simplifySiteEntries(false))}>
            <RefreshCw size={16} />{t('resourcePage.action.simplifyEntries')}
          </button>
        </div>

        <div className="form-grid cols-4" style={{ marginTop: 12 }}>
          <label>
            <span>{t('resourcePage.field.limitDomains')}</span>
            <input
              value={discoverLimitDomains}
              onChange={(e) => setDiscoverLimitDomains(e.target.value)}
              placeholder={t('resourcePage.placeholder.limit')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.dryRun')}</span>
            <select value={discoverDryRun ? 'true' : 'false'} onChange={(e) => setDiscoverDryRun(e.target.value === 'true')}>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          </label>
        </div>

        <p className="status-line">{actionPending ? <LoaderCircle size={14} className="spinning" /> : <Play size={14} />}{actionMessage}</p>
        {actionError ? <p className="status-line">{tf('resourcePage.status.failureDetail', { message: actionError })}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.sourceItems')}</h2>
          <div className="inline-actions">
            <label>
              <span>{t('resourcePage.field.scope')}</span>
              <select value={sourceScope} onChange={(e) => setSourceScope(e.target.value as SourceLibraryScope)}>
                <option value="effective">effective</option>
                <option value="shared">shared</option>
                <option value="project">project</option>
              </select>
            </label>
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.channelsBase(projectKey) })
              }}
            >
              <RefreshCw size={14} />{t('resourcePage.action.refreshItems')}
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('resourcePage.field.itemKey')}</th>
                <th>{t('resourcePage.field.name')}</th>
                <th>{t('resourcePage.field.channelKey')}</th>
                <th>{t('resourcePage.field.scope')}</th>
                <th>{t('resourcePage.field.planCapability')}</th>
                <th>{t('resourcePage.field.urlCount')}</th>
                <th>{t('resourcePage.field.enabled')}</th>
                <th>{t('resourcePage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {(sourceItems.data || []).map((item) => (
                <tr key={item.item_key}>
                  <td>{item.item_key || '-'}</td>
                  <td>{item.name || '-'}</td>
                  <td>{item.channel_key || '-'}</td>
                  <td>{item.scope || '-'}</td>
                  <td>{renderItemExecutability(item, tf)}</td>
                  <td>{getItemUrlCount(item)}</td>
                  <td>{String(item.enabled !== false)}</td>
                  <td>
                    <button onClick={() => fillItemForm(item)}>{t('resourcePage.action.edit')}</button>
                  </td>
                </tr>
              ))}
              {!sourceItems.data?.length ? (
                <tr>
                  <td colSpan={8} className="empty-cell">
                    {t('resourcePage.empty.items')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.sourceItemEditor')}</h2>
          <div className="inline-actions">
            <button disabled={actionPending} onClick={() => void runAction(t('resourcePage.actionName.saveSourceItem'), saveSourceItem)}>
              <Save size={14} />{t('resourcePage.action.save')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.itemKey')}</span>
            <input value={itemForm.item_key} onChange={(e) => setItemForm((p) => ({ ...p, item_key: e.target.value }))} placeholder={t('resourcePage.placeholder.itemKey')} />
          </label>
          <label>
            <span>{t('resourcePage.field.name')}</span>
            <input value={itemForm.name} onChange={(e) => setItemForm((p) => ({ ...p, name: e.target.value }))} placeholder={t('resourcePage.placeholder.name')} />
          </label>
          <label>
            <span>{t('resourcePage.field.channelKey')}</span>
            <input
              list="source-channel-options"
              value={itemForm.channel_key}
              onChange={(e) => setItemForm((p) => ({ ...p, channel_key: e.target.value }))}
              placeholder={t('resourcePage.placeholder.channelKey')}
            />
            <datalist id="source-channel-options">
              {(sourceChannels.data || []).map((channel) => (
                <option key={channel.channel_key} value={channel.channel_key} />
              ))}
            </datalist>
          </label>
          <label>
            <span>{t('resourcePage.field.extendsItemKey')}</span>
            <input
              value={itemForm.extends_item_key}
              onChange={(e) => setItemForm((p) => ({ ...p, extends_item_key: e.target.value }))}
              placeholder={t('resourcePage.placeholder.extendsItemKey')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.enabled')}</span>
            <select
              value={itemForm.enabled ? 'true' : 'false'}
              onChange={(e) => setItemForm((p) => ({ ...p, enabled: e.target.value === 'true' }))}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label>
            <span>{t('resourcePage.field.tagsMultiline')}</span>
            <textarea
              rows={4}
              value={itemForm.tags}
              onChange={(e) => setItemForm((p) => ({ ...p, tags: e.target.value }))}
              placeholder={t('resourcePage.placeholder.tags')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.description')}</span>
            <textarea
              rows={4}
              value={itemForm.description}
              onChange={(e) => setItemForm((p) => ({ ...p, description: e.target.value }))}
              placeholder={t('resourcePage.placeholder.description')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.siteEntriesMultiline')}</span>
            <textarea
              rows={7}
              value={itemForm.site_entries}
              onChange={(e) => setItemForm((p) => ({ ...p, site_entries: e.target.value }))}
              placeholder={t('resourcePage.placeholder.oneUrlPerLine')}
            />
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.externalProject')}</h2>
          <div className="inline-actions">
            <button disabled={actionPending} onClick={() => void runAction(t('resourcePage.actionName.previewExternalProject'), () => runExternalProjectAction(false))}>
              <Search size={14} />{t('resourcePage.action.previewManifest')}
            </button>
            <button disabled={actionPending} onClick={() => void runAction(t('resourcePage.actionName.registerExternalProject'), () => runExternalProjectAction(true))}>
              <Save size={14} />{t('resourcePage.action.registerProject')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.projectLink')}</span>
            <input
              value={externalProjectForm.project_link}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, project_link: e.target.value }))}
              placeholder={t('resourcePage.placeholder.projectLink')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.itemKeyOptional')}</span>
            <input
              value={externalProjectForm.item_key}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, item_key: e.target.value }))}
              placeholder={t('resourcePage.placeholder.externalItemKey')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.nameOptional')}</span>
            <input
              value={externalProjectForm.name}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, name: e.target.value }))}
              placeholder={t('resourcePage.placeholder.displayName')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.enabled')}</span>
            <select
              value={externalProjectForm.enabled ? 'true' : 'false'}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, enabled: e.target.value === 'true' }))}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label>
            <span>{t('resourcePage.field.tagsMultiline')}</span>
            <textarea
              rows={4}
              value={externalProjectForm.tags}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, tags: e.target.value }))}
              placeholder={t('resourcePage.placeholder.tagsExternal')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.description')}</span>
            <textarea
              rows={4}
              value={externalProjectForm.description}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, description: e.target.value }))}
              placeholder={t('resourcePage.placeholder.optionalDescription')}
            />
          </label>
          <label style={{ gridColumn: ['span', 2].join(' ') }}>
            <span>{t('resourcePage.field.hintsJson')}</span>
            <textarea
              rows={8}
              value={externalProjectForm.hints_json}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, hints_json: e.target.value }))}
              placeholder={t('resourcePage.placeholder.hintsJson')}
            />
          </label>
        </div>
        {externalProjectPreview ? (
          <div style={{ marginTop: 16 }}>
            {(() => {
              const previewItem = externalProjectPreview.item && typeof externalProjectPreview.item === 'object'
                ? (externalProjectPreview.item as SourceLibraryItem)
                : null
              const externalPlan = getExternalProjectPlan(previewItem)
              const registrationContext =
                externalProjectPreview.registration_context && typeof externalProjectPreview.registration_context === 'object'
                  ? (externalProjectPreview.registration_context as Record<string, unknown>)
                  : {}
              const endpointCandidates = Array.isArray(registrationContext.endpoint_candidates)
                ? (registrationContext.endpoint_candidates as Array<Record<string, unknown>>)
                : []
              const preferredModes = Array.isArray(registrationContext.preferred_execution_modes)
                ? registrationContext.preferred_execution_modes.join(', ')
                : '-'
              return (
                <>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('resourcePage.field.itemKey')}</th>
                          <th>{t('resourcePage.field.name')}</th>
                          <th>{t('resourcePage.field.persisted')}</th>
                          <th>{t('resourcePage.field.executionMode')}</th>
                          <th>{t('resourcePage.field.runnerRef')}</th>
                          <th>{t('resourcePage.field.sourceKind')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>{previewItem?.item_key || '-'}</td>
                          <td>{previewItem?.name || '-'}</td>
                          <td>{String(Boolean(externalProjectPreview.persisted))}</td>
                          <td>{String(externalPlan.execution_mode || '-')}</td>
                          <td>{renderUrlFold(String(externalPlan.runner_ref || ''))}</td>
                          <td>{String(externalPlan.source_kind || '-')}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p className="status-line">{tf('resourcePage.status.preferredExecutionModes', { modes: preferredModes })}</p>
                  {endpointCandidates.length ? (
                    <div className="table-wrap" style={{ marginTop: 12 }}>
                      <table>
                        <thead>
                          <tr>
                            <th>{t('resourcePage.field.executionMode')}</th>
                            <th>{t('resourcePage.field.runnerRef')}</th>
                            <th>{t('resourcePage.field.confidence')}</th>
                            <th>{t('resourcePage.field.reason')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {endpointCandidates.map((candidate, idx) => (
                            <tr key={`${candidate.runner_ref || idx}`}>
                              <td>{String(candidate.execution_mode || '-')}</td>
                              <td>{renderUrlFold(String(candidate.runner_ref || ''))}</td>
                              <td>{String(candidate.confidence || '-')}</td>
                              <td>{String(candidate.reason || '-')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: 'pointer' }}>{t('resourcePage.detail.registrationContext')}</summary>
                    <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {JSON.stringify(externalProjectPreview, null, 2)}
                    </pre>
                  </details>
                </>
              )
            })()}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.handlerClusters')}</h2>
          <div className="inline-actions">
            <label>
              <span>{t('resourcePage.field.search')}</span>
              <input
                value={handlerSearch}
                onChange={(e) => setHandlerSearch(e.target.value)}
                placeholder={t('resourcePage.placeholder.handlerSearch')}
              />
            </label>
            <button
              disabled={actionPending}
              onClick={() =>
                void runAction(t('resourcePage.actionName.syncHandlerClusters'), () =>
                  syncSourceLibraryHandlerClusters({
                    incremental: true,
                    max_site_entries: 500,
                  }),
                )
              }
            >
              <Database size={14} />{t('resourcePage.action.syncHandlerClusters')}
            </button>
            <button onClick={() => void sourceItemsGrouped.refetch()}>
              <RefreshCw size={14} />{t('resourcePage.action.refreshClusters')}
            </button>
          </div>
        </div>
        {handlerBuckets.map((bucket) => (
          <div className="table-wrap" key={bucket.handlerKey} style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th colSpan={6}>
                    <code>{bucket.handlerKey}</code> ({bucket.items.length}/{bucket.total})
                  </th>
                </tr>
                <tr>
                  <th>{t('resourcePage.field.itemKey')}</th>
                  <th>{t('resourcePage.field.name')}</th>
                  <th>{t('resourcePage.field.channelKey')}</th>
                  <th>{t('resourcePage.field.planCapability')}</th>
                  <th>{t('resourcePage.field.enabled')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {bucket.items.map((item) => (
                  <tr key={`${bucket.handlerKey}-${item.item_key}`}>
                    <td>{item.item_key || '-'}</td>
                    <td>{item.name || '-'}</td>
                    <td>{item.channel_key || '-'}</td>
                    <td>{renderItemExecutability(item, tf)}</td>
                    <td>{String(item.enabled !== false)}</td>
                    <td>
                      <div className="inline-actions">
                        <button onClick={() => fillItemForm(item)}>{t('resourcePage.action.locate')}</button>
                        <button
                          disabled={actionPending}
                          onClick={() => void runAction(t('resourcePage.actionName.syncHandlerItem'), () => syncAndRefreshHandlerItem(item, bucket.handlerKey))}
                        >
                          {t('resourcePage.action.syncAndRefresh')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!bucket.items.length ? (
                  <tr>
                    <td colSpan={6} className="empty-cell">
                      {t('resourcePage.empty.noMatches')}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ))}
        {!handlerBuckets.length ? <p className="status-line"><Search size={14} />{t('resourcePage.empty.handlerClusters')}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.recommendationBinding')}</h2>
          <div className="inline-actions">
            <button disabled={actionPending || bindingPending} onClick={bindAllRecommendations}>
              <Database size={14} />{t('resourcePage.action.bindAll')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.siteUrl')}</span>
            <input
              value={recommendSiteUrl}
              onChange={(e) => setRecommendSiteUrl(e.target.value)}
              placeholder={t('resourcePage.placeholder.siteUrl')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.entryType')}</span>
            <select value={recommendEntryType} onChange={(e) => setRecommendEntryType(e.target.value)}>
              <option value="domain_root">domain_root</option>
              <option value="rss">rss</option>
              <option value="sitemap">sitemap</option>
              <option value="search_template">search_template</option>
              <option value="official_api">official_api</option>
            </select>
          </label>
          <label>
            <span>{t('resourcePage.field.useLlm')}</span>
            <select value={recommendUseLlm ? 'true' : 'false'} onChange={(e) => setRecommendUseLlm(e.target.value === 'true')}>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <div className="inline-actions">
            <button
              disabled={actionPending || !recommendSiteUrl.trim()}
              onClick={() =>
                runAction(t('resourcePage.actionName.singleRecommendation'), async () => {
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
              <Play size={14} />{t('resourcePage.action.singleRecommendation')}
            </button>
            <button
              disabled={actionPending || !(siteEntries.data || []).length}
              onClick={() =>
                runAction(t('resourcePage.actionName.batchRecommendation'), async () => {
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
              <Radar size={14} />{t('resourcePage.action.batchRecommendation')}
            </button>
          </div>
        </div>
        {singleRecommendation ? (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.mode')}</th>
                  <th>{t('resourcePage.field.entryType')}</th>
                  <th>{t('resourcePage.field.template')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.validated')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t('resourcePage.mode.single')}</td>
                  <td>{singleRecommendation.entry_type || '-'}</td>
                  <td>{singleRecommendation.template || '-'}</td>
                  <td>{singleRecommendation.source || '-'}</td>
                  <td>{String(singleRecommendation.validated ?? false)}</td>
                  <td>
                    <button
                      disabled={bindingPending || !recommendSiteUrl.trim()}
                      onClick={() =>
                        runAction(t('resourcePage.actionName.bindSingleRecommendation'), () =>
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
                      {t('resourcePage.action.bind')}
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
                  <th>{t('resourcePage.field.siteUrl')}</th>
                  <th>{t('resourcePage.field.entryType')}</th>
                  <th>{t('resourcePage.field.template')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.validated')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
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
                      <button disabled={bindingPending || !item.site_url} onClick={() => runAction(t('resourcePage.actionName.bindBatchRecommendation'), () => bindOne(item))}>
                        {t('resourcePage.action.bind')}
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
          <h2>{t('resourcePage.section.manualEntry')}</h2>
        </div>
        <div className="form-grid cols-3">
          <label>
            <span>{t('resourcePage.field.siteUrl')}</span>
            <input
              value={newSiteUrl}
              onChange={(e) => setNewSiteUrl(e.target.value)}
              placeholder={t('resourcePage.placeholder.siteUrl')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.entryType')}</span>
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
              <Database size={14} />{t('resourcePage.action.addEntry')}
            </button>
          </div>
        </div>
      </section>

      <section className="panel two-col">
        <div>
          <div className="panel-header">
            <h2>{t('resourcePage.section.urlPool')}</h2>
            <div className="inline-actions">
              <button disabled={resourceUrlPage <= 1} onClick={() => setResourceUrlPage((p) => Math.max(1, p - 1))}>
                {t('resourcePage.action.previousPage')}
              </button>
              <span className="chip">{tf('resourcePage.pagination.page', { page: resourceUrlPage })}</span>
              <button onClick={() => setResourceUrlPage((p) => p + 1)}>{t('resourcePage.action.nextPage')}</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.url')}</th>
                  <th>{t('resourcePage.field.domain')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.createdAt')}</th>
                </tr>
              </thead>
              <tbody>
                {(resourceUrls.data || []).map((item, idx) => (
                  <tr key={`${item.id || item.url || idx}`}>
                    <td>{renderUrlFold(item.url)}</td>
                    <td>{item.domain || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{formatDate(item.created_at, locale)}</td>
                  </tr>
                ))}
                {!resourceUrls.data?.length ? (
                  <tr>
                    <td colSpan={4} className="empty-cell">
                      {t('resourcePage.empty.urls')}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header">
            <h2>{t('resourcePage.section.siteEntries')}</h2>
            <div className="inline-actions">
              <button disabled={resourceSitePage <= 1} onClick={() => setResourceSitePage((p) => Math.max(1, p - 1))}>
                {t('resourcePage.action.previousPage')}
              </button>
              <span className="chip">{tf('resourcePage.pagination.page', { page: resourceSitePage })}</span>
              <button onClick={() => setResourceSitePage((p) => p + 1)}>{t('resourcePage.action.nextPage')}</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.siteUrl')}</th>
                  <th>{t('resourcePage.field.domain')}</th>
                  <th>{t('resourcePage.field.entryType')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.lifecycle')}</th>
                  <th>{t('resourcePage.field.executionPlanPreview')}</th>
                  <th>{t('resourcePage.field.nextActions')}</th>
                  <th>{t('resourcePage.field.enabled')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {(siteEntries.data || []).map((item, idx) => (
                  <tr key={`${item.id || item.site_url || idx}`}>
                    <td>{renderUrlFold(item.site_url)}</td>
                    <td>{item.domain || '-'}</td>
                    <td>{item.entry_type || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{renderSiteEntryLifecycle(item, tf)}</td>
                    <td>{renderSiteEntryPlanPreview(item, tf)}</td>
                    <td>{renderSiteEntryNextActions(item, tf)}</td>
                    <td>{String(item.enabled ?? true)}</td>
                    <td>
                      <div className="inline-actions">
                        <button
                          disabled={actionPending || !item.site_url}
                          onClick={() =>
                            void runAction(t('resourcePage.actionName.acceptSiteEntry'), () =>
                              reviewSiteEntryLifecycle(item, 'accepted'),
                            )
                          }
                        >
                          {t('resourcePage.action.acceptSiteEntry')}
                        </button>
                        <button
                          disabled={actionPending || !item.site_url}
                          onClick={() =>
                            void runAction(t('resourcePage.actionName.rejectSiteEntry'), () =>
                              reviewSiteEntryLifecycle(item, 'rejected'),
                            )
                          }
                        >
                          {t('resourcePage.action.rejectSiteEntry')}
                        </button>
                        <button
                          disabled={actionPending || !item.site_url}
                          onClick={() =>
                            void runAction(t('resourcePage.actionName.needsReviewSiteEntry'), () =>
                              reviewSiteEntryLifecycle(item, 'needs_review'),
                            )
                          }
                        >
                          {t('resourcePage.action.needsReviewSiteEntry')}
                        </button>
                        <button
                          disabled={actionPending || !item.site_url}
                          onClick={() =>
                            void runAction(t('resourcePage.actionName.disableSiteEntry'), () =>
                              reviewSiteEntryLifecycle(item, 'disabled'),
                            )
                          }
                        >
                          {t('resourcePage.action.disableSiteEntry')}
                        </button>
                        <button
                          disabled={actionPending || !siteEntryAcceptedCollectEnabled(item)}
                          onClick={() =>
                            void runAction(t('resourcePage.actionName.runAcceptedSiteEntryCollect'), () =>
                              runAcceptedSiteEntryCollect(item),
                            )
                          }
                        >
                          {t('resourcePage.action.runAcceptedSiteEntryCollect')}
                        </button>
                        <button
                          disabled={actionPending}
                          onClick={() =>
                            void runAction(t('resourcePage.actionName.copySiteEntrySourceRef'), () =>
                              copySiteEntrySourceRef(item),
                            )
                          }
                        >
                          {t('resourcePage.action.copySiteEntrySourceRef')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!siteEntries.data?.length ? (
                  <tr>
                    <td colSpan={9} className="empty-cell">
                      {t('resourcePage.empty.siteEntries')}
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
