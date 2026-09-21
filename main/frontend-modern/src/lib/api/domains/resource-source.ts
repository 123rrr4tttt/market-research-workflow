import { endpoints } from '../endpoints'
import { asList, getProjectKey, httpGet as get, httpPatch as patch, httpPost as post } from '../client'
import type {
  ResourcePoolBatchRecommendationPayload,
  ResourcePoolBatchRecommendationResponse,
  ExternalProjectRegistrationPayload,
  ExternalProjectRegistrationResponse,
  ResourcePoolDiscoverPayload,
  ResourcePoolDiscoverResponse,
  ResourcePoolRecommendationPayload,
  ResourcePoolRecommendationResponse,
  ResourcePoolSiteEntryLifecyclePatchPayload,
  ResourcePoolUpsertSiteEntryPayload,
  ResourcePoolUrlItem,
  SiteEntryGroupedResponse,
  SiteEntryItem,
  SourceLibraryChannel,
  SourceLibraryHandlerSyncPayload,
  SourceLibraryHandlerSyncResponse,
  SourceLibraryItem,
  SourceLibraryItemRefreshPayload,
  SourceLibraryRunResult,
  SourceLibraryItemUpsertPayload,
  SourceLibraryItemsGroupedResponse,
  SourceLibraryScope,
} from '../../types'

function asRecord(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function firstDefined<T>(...values: Array<T | null | undefined>) {
  return values.find((value) => value !== undefined && value !== null)
}

function normalizeSourceLibraryItem(item: SourceLibraryItem): SourceLibraryItem {
  const extra = asRecord(item.extra)
  return {
    ...item,
    item_type: String(firstDefined(item.item_type, extra.item_type, '') || '') || undefined,
    managed_by: String(firstDefined(item.managed_by, extra.managed_by, '') || '') || undefined,
    capability: firstDefined(item.capability, extra.capability, extra.capability_profile) as SourceLibraryItem['capability'],
    capability_summary: firstDefined(
      item.capability_summary,
      extra.capability_summary,
      extra.capability,
      extra.capability_profile,
    ) as SourceLibraryItem['capability_summary'],
  }
}

function normalizeSourceLibraryItems(items: SourceLibraryItem[]) {
  return items.map(normalizeSourceLibraryItem)
}

function normalizeSiteEntry(item: SiteEntryItem): SiteEntryItem {
  const extra = asRecord(item.extra)
  const reviewClosure = asRecord(firstDefined(item.review_closure, extra.review_closure))
  const evidenceBinding = asRecord(firstDefined(item.evidence_binding, reviewClosure.evidence_binding, extra.evidence_binding))
  const executionFact = asRecord(firstDefined(item.execution_fact, extra.execution_fact))
  const lifecycleSummary = asRecord(item.lifecycle_summary)
  return {
    ...item,
    lifecycle_transition: firstDefined(
      item.lifecycle_transition,
      lifecycleSummary.lifecycle_transition,
      extra.lifecycle_transition,
    ) as SiteEntryItem['lifecycle_transition'],
    review_closure: reviewClosure as SiteEntryItem['review_closure'],
    next_actions: firstDefined(item.next_actions, reviewClosure.next_actions, extra.next_actions) as SiteEntryItem['next_actions'],
    evidence_binding: evidenceBinding as SiteEntryItem['evidence_binding'],
    single_source_guard: firstDefined(
      item.single_source_guard,
      reviewClosure.single_source_guard,
      reviewClosure.strict_source,
      executionFact.single_source_guard,
      extra.single_source_guard,
    ) as SiteEntryItem['single_source_guard'],
    execution_fact: executionFact as SiteEntryItem['execution_fact'],
  }
}

function normalizeSiteEntries(items: SiteEntryItem[]) {
  return items.map(normalizeSiteEntry)
}

export async function listSourceItems() {
  return listSourceLibraryItemsWithScope('effective')
}

export async function listSourceLibraryItemsWithScope(scope: SourceLibraryScope = 'effective') {
  const query = new URLSearchParams({ scope })
  const data = await get<SourceLibraryItem[] | { items?: SourceLibraryItem[] }>(endpoints.sourceLibrary.itemsQuery(query))
  return normalizeSourceLibraryItems(asList<SourceLibraryItem>(data))
}

export async function listSourceLibraryChannels(scope: SourceLibraryScope = 'effective') {
  const query = new URLSearchParams({ scope })
  const data = await get<SourceLibraryChannel[] | { items?: SourceLibraryChannel[] }>(
    endpoints.sourceLibrary.channelsQuery(query),
  )
  return asList<SourceLibraryChannel>(data)
}

export async function listSourceLibraryItemsGrouped(scope: SourceLibraryScope = 'effective') {
  const query = new URLSearchParams({ scope })
  const data = await get<SourceLibraryItemsGroupedResponse>(endpoints.sourceLibrary.itemsGroupedQuery(query))
  const byHandler = asRecord(data?.by_handler)
  return {
    ...data,
    by_handler: Object.fromEntries(
      Object.entries(byHandler).map(([handlerKey, items]) => [
        handlerKey,
        normalizeSourceLibraryItems(Array.isArray(items) ? (items as SourceLibraryItem[]) : []),
      ]),
    ),
  }
}

export async function upsertSourceLibraryItem(payload: SourceLibraryItemUpsertPayload) {
  return post<{ item_key?: string; project_key?: string; ok?: boolean }>(endpoints.sourceLibrary.items, {
    item_key: payload.item_key,
    name: payload.name,
    channel_key: payload.channel_key,
    description: payload.description ?? null,
    params: payload.params ?? {},
    tags: payload.tags ?? [],
    schedule: payload.schedule ?? null,
    extends_item_key: payload.extends_item_key ?? null,
    enabled: payload.enabled ?? true,
    extra: payload.extra ?? {},
  })
}

export async function refreshSourceLibraryItem(itemKey: string, payload: SourceLibraryItemRefreshPayload = {}) {
  return post<Record<string, unknown>>(endpoints.sourceLibrary.itemRefresh(itemKey), {
    project_key: getProjectKey(),
    incremental: payload.incremental ?? true,
    max_site_entries: payload.max_site_entries ?? 500,
  })
}

export async function registerExternalProject(payload: ExternalProjectRegistrationPayload) {
  return post<ExternalProjectRegistrationResponse>(endpoints.sourceLibrary.externalProjectRegister, {
    project_link: payload.project_link,
    item_key: payload.item_key ?? null,
    name: payload.name ?? null,
    description: payload.description ?? null,
    tags: payload.tags ?? [],
    enabled: payload.enabled ?? true,
    persist: payload.persist ?? false,
    hints: payload.hints ?? {},
  })
}

export async function syncSourceLibraryHandlerClusters(payload: SourceLibraryHandlerSyncPayload = {}) {
  return post<SourceLibraryHandlerSyncResponse>(endpoints.sourceLibrary.handlerClustersSync, {
    project_key: getProjectKey(),
    handlers: payload.handlers ?? [],
    incremental: payload.incremental ?? true,
    max_site_entries: payload.max_site_entries ?? 500,
  })
}

export async function listResourcePoolUrls(page = 1, pageSize = 20) {
  const query = new URLSearchParams({
    scope: 'effective',
    page: String(page),
    page_size: String(pageSize),
  })
  const data = await get<ResourcePoolUrlItem[] | { items?: ResourcePoolUrlItem[] }>(
    endpoints.resourcePool.urlsQuery(query),
  )
  return asList<ResourcePoolUrlItem>(data)
}

export async function listResourcePoolUrlsWithFilters(params?: {
  page?: number
  pageSize?: number
  domain?: string
  source?: string
}) {
  const query = new URLSearchParams({
    scope: 'effective',
    page: String(params?.page || 1),
  })
  // Guard against duplicated page_size in query strings assembled across layers.
  query.delete('page_size')
  query.set('page_size', String(params?.pageSize || 20))

  if (params?.domain?.trim()) query.set('domain', params.domain.trim())
  if (params?.source?.trim()) query.set('source', params.source.trim())

  const data = await get<ResourcePoolUrlItem[] | { items?: ResourcePoolUrlItem[] }>(
    endpoints.resourcePool.urlsQuery(query),
  )
  return asList<ResourcePoolUrlItem>(data)
}

export async function listSiteEntries(page = 1, pageSize = 20) {
  const query = new URLSearchParams({
    scope: 'effective',
    page: String(page),
    page_size: String(pageSize),
  })
  const data = await get<SiteEntryItem[] | { items?: SiteEntryItem[] }>(
    endpoints.resourcePool.siteEntriesQuery(query),
  )
  return normalizeSiteEntries(asList<SiteEntryItem>(data))
}

export async function listSiteEntriesWithFilters(params?: {
  page?: number
  pageSize?: number
  domain?: string
  entryType?: string
}) {
  const query = new URLSearchParams({
    scope: 'effective',
    page: String(params?.page || 1),
    page_size: String(params?.pageSize || 20),
  })
  if (params?.domain?.trim()) query.set('domain', params.domain.trim())
  if (params?.entryType?.trim()) query.set('entry_type', params.entryType.trim())
  const data = await get<SiteEntryItem[] | { items?: SiteEntryItem[] }>(
    endpoints.resourcePool.siteEntriesQuery(query),
  )
  return normalizeSiteEntries(asList<SiteEntryItem>(data))
}

export async function upsertSiteEntry(payload: {
  site_url: string
  entry_type?: string
  scope?: 'project' | 'shared'
  name?: string
  enabled?: boolean
}) {
  return post<Record<string, unknown>>(endpoints.resourcePool.siteEntries, {
    scope: payload.scope || 'project',
    site_url: payload.site_url,
    entry_type: payload.entry_type || 'domain_root',
    name: payload.name || null,
    enabled: payload.enabled ?? true,
    source: 'manual',
  })
}

export async function recommendSiteEntry(payload: ResourcePoolRecommendationPayload) {
  return post<ResourcePoolRecommendationResponse>(endpoints.resourcePool.siteEntriesRecommend, {
    project_key: payload.project_key || getProjectKey(),
    site_url: payload.site_url,
    entry_type: payload.entry_type ?? null,
    template: payload.template ?? null,
    use_llm: payload.use_llm ?? false,
  })
}

export async function recommendSiteEntriesBatch(payload: ResourcePoolBatchRecommendationPayload) {
  return post<ResourcePoolBatchRecommendationResponse>(endpoints.resourcePool.siteEntriesRecommendBatch, {
    project_key: payload.project_key || getProjectKey(),
    entries: payload.entries || [],
    use_llm: payload.use_llm ?? true,
    llm_batch_size: payload.llm_batch_size ?? 20,
  })
}

export async function bindSiteEntry(payload: ResourcePoolUpsertSiteEntryPayload) {
  return post<Record<string, unknown>>(endpoints.resourcePool.siteEntries, {
    project_key: payload.project_key || getProjectKey(),
    scope: payload.scope || 'project',
    site_url: payload.site_url,
    entry_type: payload.entry_type || 'domain_root',
    template: payload.template ?? null,
    name: payload.name ?? null,
    domain: payload.domain ?? null,
    tags: payload.tags || [],
    enabled: payload.enabled ?? true,
    capabilities: payload.capabilities || {},
    source: payload.source || 'manual',
    source_ref: payload.source_ref || {},
    extra: payload.extra || {},
  })
}

export async function patchSiteEntryLifecycle(payload: ResourcePoolSiteEntryLifecyclePatchPayload) {
  return patch<SiteEntryItem>(`${endpoints.resourcePool.siteEntries}/lifecycle`, {
    project_key: payload.project_key || getProjectKey(),
    scope: payload.scope || 'project',
    site_url: payload.site_url,
    lifecycle_state: payload.lifecycle_state,
    reviewer: payload.reviewer ?? null,
    review_note: payload.review_note ?? null,
    review_reason: payload.review_reason ?? null,
    enabled: payload.enabled ?? null,
    extra_patch: payload.extra_patch ?? null,
  })
}

export async function extractResourcePoolFromDocuments(asyncMode = true) {
  return post<Record<string, unknown>>(endpoints.resourcePool.extractFromDocuments, {
    scope: 'project',
    filters: { limit: 500 },
    async_mode: asyncMode,
  })
}

export async function discoverSiteEntries(asyncMode = true) {
  return post<Record<string, unknown>>(endpoints.resourcePool.discoverSiteEntries, {
    url_scope: 'effective',
    target_scope: 'project',
    limit_domains: 60,
    dry_run: false,
    write: true,
    async_mode: asyncMode,
  })
}

export async function discoverSiteEntriesAdvanced(payload: ResourcePoolDiscoverPayload = {}) {
  return post<ResourcePoolDiscoverResponse>(endpoints.resourcePool.discoverSiteEntries, {
    project_key: payload.project_key || getProjectKey(),
    url_scope: payload.url_scope || 'effective',
    target_scope: payload.target_scope || 'project',
    limit_domains: payload.limit_domains ?? 60,
    probe_timeout: payload.probe_timeout ?? 6,
    dry_run: payload.dry_run ?? false,
    write: payload.write ?? true,
    async_mode: payload.async_mode ?? true,
  })
}

export async function simplifySiteEntries(dryRun = false) {
  return post<Record<string, unknown>>(endpoints.resourcePool.siteEntriesSimplify, {
    scope: 'project',
    dry_run: dryRun,
  })
}

export async function listSiteEntryGrouped() {
  const query = new URLSearchParams({ scope: 'effective' })
  return get<SiteEntryGroupedResponse>(endpoints.resourcePool.siteEntriesGroupedQuery(query))
}

export async function syncSourceLibrary() {
  return post<Record<string, unknown>>(endpoints.ingest.sourceLibrarySync, {})
}

export async function runSourceLibrary(payload: {
  item_key?: string | null
  handler_key?: string | null
  source_mode?: string | null
  async_mode: boolean
  override_params: Record<string, unknown>
}) {
  return post<SourceLibraryRunResult>(endpoints.ingest.sourceLibraryRun, payload)
}
