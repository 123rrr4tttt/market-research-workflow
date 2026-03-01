import { endpoints } from './api/endpoints'
import {
  asList,
  getProjectKey,
  httpDelete as del,
  httpGet as get,
  httpPost as post,
  httpPut as put,
  setProjectKey,
} from './api/client'
import { fetchEnvSettings, saveEnvSettings } from './api/services/config'
import { fetchDeepHealth, fetchHealth } from './api/services/health'
import {
  activateProjectByKey,
  archiveProjectRecord,
  createProjectRecord,
  deleteProjectRecord,
  fetchProjects,
  restoreProjectRecord,
  updateProjectRecord,
} from './api/services/projects'
import type {
  AdminActionResponse,
  AdminDeleteDocumentsPayload,
  AdminDocumentListPayload,
  AdminDocumentListResponse,
  AdminReExtractPayload,
  AdminStats,
  AutoCreateProjectPayload,
  AutoCreateProjectResult,
  AdminTopicExtractPayload,
  AdminTopicExtractResponse,
  DashboardStats,
  DocumentBulkExtractedPayload,
  DocumentExtractedPayload,
  DocumentItem,
  GraphExportResponse,
  GraphConfigResponse,
  GraphStructuredSearchRequest,
  GraphStructuredSearchResponse,
  GraphResponse,
  IngestJobRow,
  LlmProjectTemplatesResponse,
  LlmServiceConfigItem,
  LlmTemplateCopyPayload,
  LlmTemplateCopyResponse,
  LlmTemplateUpdatePayload,
  LlmTemplateUpdateResponse,
  PolicyDetail,
  PolicyItem,
  PolicyStats,
  ProcessHistoryResponse,
  ProcessTaskDetail,
  ProcessTaskList,
  ProcessTaskLogsResponse,
  ProcessTaskStats,
  ProductItem,
  RawImportPayload,
  RawImportResult,
  ResourcePoolBatchRecommendationPayload,
  ResourcePoolBatchRecommendationResponse,
  ResourcePoolDiscoverPayload,
  ResourcePoolDiscoverResponse,
  ResourcePoolRecommendationPayload,
  ResourcePoolRecommendationResponse,
  ResourcePoolUpsertSiteEntryPayload,
  ResourcePoolUrlItem,
  SearchHistoryItem,
  SiteEntryGroupedResponse,
  SiteEntryItem,
  SourceLibraryItem,
  TopicItem,
  WorkflowTemplate,
  WorkflowTemplateMutationResponse,
  WorkflowTemplatePayload,
} from './types'

export async function getHealth() {
  return fetchHealth()
}

export { getProjectKey, setProjectKey }

export async function getDeepHealth() {
  return fetchDeepHealth()
}

export async function getDashboardStats() {
  return get<DashboardStats>(endpoints.dashboard.stats)
}

export async function listProjects() {
  return fetchProjects()
}

export async function activateProject(projectKey: string) {
  return activateProjectByKey(projectKey)
}

export async function createProject(payload: { project_key: string; name: string; enabled?: boolean }) {
  return createProjectRecord(payload)
}

export async function autoCreateProject(payload: AutoCreateProjectPayload) {
  return post<AutoCreateProjectResult>('/api/v1/projects/auto-create', payload)
}

export async function updateProject(projectKey: string, payload: { name?: string; enabled?: boolean }) {
  return updateProjectRecord(projectKey, payload)
}

export async function archiveProject(projectKey: string) {
  return archiveProjectRecord(projectKey)
}

export async function restoreProject(projectKey: string) {
  return restoreProjectRecord(projectKey)
}

export async function deleteProject(projectKey: string, hard = false) {
  return deleteProjectRecord(projectKey, hard)
}

export async function listSourceItems() {
  const data = await get<SourceLibraryItem[] | { items?: SourceLibraryItem[] }>('/api/v1/source_library/items?scope=effective')
  return asList<SourceLibraryItem>(data)
}

export async function listResourcePoolUrls(page = 1, pageSize = 20) {
  const data = await get<ResourcePoolUrlItem[] | { items?: ResourcePoolUrlItem[] }>(
    `/api/v1/resource_pool/urls?scope=effective&page=${page}&page_size=${pageSize}`,
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
    page_size: String(params?.pageSize || 20),
  })
  if (params?.domain?.trim()) query.set('domain', params.domain.trim())
  if (params?.source?.trim()) query.set('source', params.source.trim())
  const data = await get<ResourcePoolUrlItem[] | { items?: ResourcePoolUrlItem[] }>(
    `/api/v1/resource_pool/urls?${query.toString()}`,
  )
  return asList<ResourcePoolUrlItem>(data)
}

export async function listSiteEntries(page = 1, pageSize = 20) {
  const data = await get<SiteEntryItem[] | { items?: SiteEntryItem[] }>(
    `/api/v1/resource_pool/site_entries?scope=effective&page=${page}&page_size=${pageSize}`,
  )
  return asList<SiteEntryItem>(data)
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
    `/api/v1/resource_pool/site_entries?${query.toString()}`,
  )
  return asList<SiteEntryItem>(data)
}

export async function upsertSiteEntry(payload: {
  site_url: string
  entry_type?: string
  scope?: 'project' | 'shared'
  name?: string
  enabled?: boolean
}) {
  return post<Record<string, unknown>>('/api/v1/resource_pool/site_entries', {
    scope: payload.scope || 'project',
    site_url: payload.site_url,
    entry_type: payload.entry_type || 'domain_root',
    name: payload.name || null,
    enabled: payload.enabled ?? true,
    source: 'manual',
  })
}

export async function recommendSiteEntry(payload: ResourcePoolRecommendationPayload) {
  return post<ResourcePoolRecommendationResponse>('/api/v1/resource_pool/site_entries/recommend', {
    project_key: payload.project_key || getProjectKey(),
    site_url: payload.site_url,
    entry_type: payload.entry_type ?? null,
    template: payload.template ?? null,
    use_llm: payload.use_llm ?? false,
  })
}

export async function recommendSiteEntriesBatch(payload: ResourcePoolBatchRecommendationPayload) {
  return post<ResourcePoolBatchRecommendationResponse>('/api/v1/resource_pool/site_entries/recommend-batch', {
    project_key: payload.project_key || getProjectKey(),
    entries: payload.entries || [],
    use_llm: payload.use_llm ?? true,
    llm_batch_size: payload.llm_batch_size ?? 20,
  })
}

export async function bindSiteEntry(payload: ResourcePoolUpsertSiteEntryPayload) {
  return post<Record<string, unknown>>('/api/v1/resource_pool/site_entries', {
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

export async function extractResourcePoolFromDocuments(asyncMode = true) {
  return post<Record<string, unknown>>('/api/v1/resource_pool/extract/from-documents', {
    scope: 'project',
    filters: { limit: 500 },
    async_mode: asyncMode,
  })
}

export async function discoverSiteEntries(asyncMode = true) {
  return post<Record<string, unknown>>('/api/v1/resource_pool/discover/site-entries', {
    url_scope: 'effective',
    target_scope: 'project',
    limit_domains: 60,
    dry_run: false,
    write: true,
    async_mode: asyncMode,
  })
}

export async function discoverSiteEntriesAdvanced(payload: ResourcePoolDiscoverPayload = {}) {
  return post<ResourcePoolDiscoverResponse>('/api/v1/resource_pool/discover/site-entries', {
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
  return post<Record<string, unknown>>('/api/v1/resource_pool/site_entries/simplify', {
    scope: 'project',
    dry_run: dryRun,
  })
}

export async function listSiteEntryGrouped() {
  return get<SiteEntryGroupedResponse>('/api/v1/resource_pool/site_entries/grouped?scope=effective')
}

export async function listIngestHistory(limit = 8) {
  const data = await get<IngestJobRow[] | { items?: IngestJobRow[] }>(`/api/v1/ingest/history?limit=${limit}`)
  return asList<IngestJobRow>(data)
}

export async function listProcessTasks(limit = 50) {
  return get<ProcessTaskList>(`/api/v1/process/list?limit=${limit}`)
}

export async function getProcessStats() {
  return get<ProcessTaskStats>('/api/v1/process/stats')
}

export async function listProcessHistory(limit = 50) {
  return get<ProcessHistoryResponse>(`/api/v1/process/history?limit=${limit}`)
}

export async function getProcessTaskDetail(taskId: string) {
  return get<ProcessTaskDetail>(`/api/v1/process/${encodeURIComponent(taskId)}`)
}

export async function getProcessTaskLogs(taskId: string, tail = 200) {
  return get<ProcessTaskLogsResponse>(`/api/v1/process/${encodeURIComponent(taskId)}/logs?tail=${tail}`)
}

export async function cancelTask(taskId: string, terminate = false) {
  return post(`/api/v1/process/${encodeURIComponent(taskId)}/cancel?terminate=${terminate ? 'true' : 'false'}`, null)
}

export async function generateKeywords(payload: {
  topic: string
  language: string
  platform?: string | null
  topic_focus?: string
  base_keywords?: string[]
}) {
  return post<{ search_keywords?: string[]; keywords?: string[] }>('/api/v1/discovery/generate-keywords', payload)
}

export async function ingestPolicy(payload: {
  state: string
  source_hint?: string | null
  async_mode: boolean
}) {
  return post<Record<string, unknown>>('/api/v1/ingest/policy', payload)
}

export async function ingestPolicyRegulation(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>('/api/v1/ingest/policy/regulation', payload)
}

export async function ingestMarket(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>('/api/v1/ingest/market', payload)
}

export async function ingestSocial(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>('/api/v1/ingest/social/sentiment', payload)
}

export async function ingestCommodity(payload: { limit: number; async_mode: boolean }) {
  return post<Record<string, unknown>>('/api/v1/ingest/commodity/metrics', payload)
}

export async function ingestEcom(payload: { limit: number; async_mode: boolean }) {
  return post<Record<string, unknown>>('/api/v1/ingest/ecom/prices', payload)
}

export async function syncSourceLibrary() {
  return post<Record<string, unknown>>('/api/v1/ingest/source-library/sync', {})
}

export async function runSourceLibrary(payload: {
  item_key?: string | null
  handler_key?: string | null
  async_mode: boolean
  override_params: Record<string, unknown>
}) {
  return post<Record<string, unknown>>('/api/v1/ingest/source-library/run', payload)
}

export async function getEnvSettings() {
  return fetchEnvSettings()
}

export async function updateEnvSettings(payload: Record<string, string>) {
  return saveEnvSettings(payload)
}

export async function listTopics() {
  const data = await get<TopicItem[] | { items?: TopicItem[] }>('/api/v1/topics')
  return asList<TopicItem>(data)
}

export async function createTopic(payload: {
  topic_name: string
  domains: string[]
  languages: string[]
  keywords_seed: string[]
  subreddits: string[]
  enabled: boolean
  description?: string | null
}) {
  return post<{ id: number }>('/api/v1/topics', payload)
}

export async function deleteTopic(topicId: number) {
  return del<{ deleted: number }>(`/api/v1/topics/${topicId}`)
}

export async function listProducts() {
  const data = await get<ProductItem[] | { items?: ProductItem[] }>('/api/v1/products')
  return asList<ProductItem>(data)
}

export async function createProduct(payload: {
  name: string
  category?: string | null
  source_name?: string | null
  source_uri?: string | null
  selector_hint?: string | null
  currency?: string | null
  enabled: boolean
}) {
  return post<{ id: number }>('/api/v1/products', payload)
}

export async function deleteProduct(productId: number) {
  return del<{ deleted: number }>(`/api/v1/products/${productId}`)
}

export async function getPolicyStats() {
  return get<PolicyStats>('/api/v1/policies/stats')
}

export async function listPolicies(state = '', page = 1, pageSize = 20) {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (state.trim()) query.set('state', state.trim().toUpperCase())
  const data = await get<PolicyItem[] | { items?: PolicyItem[] }>(`/api/v1/policies?${query.toString()}`)
  return asList<PolicyItem>(data)
}

export async function getPolicyDetail(policyId: number) {
  return get<PolicyDetail>(`/api/v1/policies/${policyId}`)
}

export async function listWorkflows() {
  const data = await get<string[] | { items?: string[] }>('/api/v1/project-customization/workflows')
  return asList<string>(data)
}

export async function getWorkflowTemplate(workflowName: string) {
  return get<WorkflowTemplate>(`/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/template`)
}

export async function upsertWorkflowTemplate(workflowName: string, payload: WorkflowTemplatePayload) {
  return post<WorkflowTemplateMutationResponse>(
    `/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/template`,
    payload,
  )
}

export async function deleteWorkflowTemplate(workflowName: string, projectKey?: string) {
  const query = projectKey ? `?project_key=${encodeURIComponent(projectKey)}` : ''
  return del<WorkflowTemplateMutationResponse>(
    `/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/template${query}`,
  )
}

export async function runWorkflow(workflowName: string, params: Record<string, unknown>) {
  return post<Record<string, unknown>>(`/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/run`, {
    project_key: getProjectKey(),
    params,
  })
}

export async function listLlmConfigs() {
  const data = await get<LlmServiceConfigItem[] | { items?: LlmServiceConfigItem[] }>('/api/v1/llm-config')
  return asList<LlmServiceConfigItem>(data)
}

export async function listProjectLlmTemplates(projectKey = getProjectKey()) {
  return get<LlmProjectTemplatesResponse>(`/api/v1/llm-config/projects/${encodeURIComponent(projectKey)}`)
}

export async function updateProjectLlmTemplate(
  serviceName: string,
  payload: LlmTemplateUpdatePayload,
  projectKey = getProjectKey(),
) {
  return put<LlmTemplateUpdateResponse>(
    `/api/v1/llm-config/projects/${encodeURIComponent(projectKey)}/${encodeURIComponent(serviceName)}`,
    payload,
  )
}

export async function copyProjectLlmTemplates(payload: LlmTemplateCopyPayload, projectKey = getProjectKey()) {
  return post<LlmTemplateCopyResponse>(
    `/api/v1/llm-config/projects/${encodeURIComponent(projectKey)}/copy-from`,
    payload,
  )
}

export async function getAdminStats() {
  return get<AdminStats>('/api/v1/admin/stats')
}

export async function getSearchHistory(page = 1, pageSize = 50) {
  const data = await get<SearchHistoryItem[] | { items?: SearchHistoryItem[] }>(
    `/api/v1/admin/search-history?page=${page}&page_size=${pageSize}`,
  )
  return asList<SearchHistoryItem>(data)
}

export async function listAdminDocuments(payload: AdminDocumentListPayload = {}) {
  return post<AdminDocumentListResponse>('/api/v1/admin/documents/list', {
    page: payload.page ?? 1,
    page_size: payload.page_size ?? 20,
    state: payload.state ?? null,
    doc_type: payload.doc_type ?? null,
    has_extracted_data: payload.has_extracted_data ?? null,
    search: payload.search ?? null,
    sort_by: payload.sort_by ?? 'created_at',
    sort_order: payload.sort_order ?? 'desc',
  })
}

export async function getAdminDocument(docId: number) {
  return get<DocumentItem>(`/api/v1/admin/documents/${docId}`)
}

export async function updateDocumentExtractedData(docId: number, payload: DocumentExtractedPayload) {
  return post<{ id?: number; extracted_data?: unknown }>(
    `/api/v1/admin/documents/${docId}/extracted-data`,
    payload,
  )
}

export async function bulkUpdateDocumentExtractedData(payload: DocumentBulkExtractedPayload) {
  return post<AdminActionResponse>('/api/v1/admin/documents/bulk/extracted-data', payload)
}

export async function clearDocumentExtractedData(docIds: number[]) {
  return bulkUpdateDocumentExtractedData({
    doc_ids: docIds,
    mode: 'replace',
    extracted_data: null,
  })
}

export async function deleteAdminDocuments(payload: AdminDeleteDocumentsPayload | number[]) {
  const ids = Array.isArray(payload) ? payload : payload.ids
  return post<{ deleted?: number }>('/api/v1/admin/documents/delete', { ids })
}

export async function reExtractDocuments(payload: AdminReExtractPayload = {}) {
  return post<AdminActionResponse>('/api/v1/admin/documents/re-extract', payload)
}

export async function topicExtractDocuments(payload: AdminTopicExtractPayload = {}) {
  return post<AdminTopicExtractResponse>('/api/v1/admin/documents/topic-extract', payload)
}

export async function rawImportDocuments(payload: RawImportPayload) {
  return post<RawImportResult>('/api/v1/admin/documents/raw-import', payload)
}

export async function exportGraph(docIds: number[] | string) {
  const value = Array.isArray(docIds) ? docIds.join(',') : String(docIds || '')
  return get<GraphExportResponse>(`/api/v1/admin/export-graph?doc_ids=${encodeURIComponent(value)}`)
}

export async function cleanupGovernance(retentionDays: number) {
  return post<Record<string, unknown>>('/api/v1/governance/cleanup', { retention_days: retentionDays })
}

export async function syncAggregator(asyncMode = true) {
  return post<Record<string, unknown>>('/api/v1/governance/aggregator/sync', { async_mode: asyncMode })
}

export type GraphKind = 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'

export async function getGraphConfig() {
  return get<GraphConfigResponse>('/api/v1/project-customization/graph-config')
}

export async function getPolicyGraph(params: {
  start_date?: string
  end_date?: string
  state?: string
  policy_type?: string
  limit?: number
}) {
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.state) query.set('state', params.state)
  if (params.policy_type) query.set('policy_type', params.policy_type)
  query.set('limit', String(params.limit || 100))
  return get<GraphResponse>(`/api/v1/admin/policy-graph?${query.toString()}`)
}

export async function getSocialGraph(params: {
  start_date?: string
  end_date?: string
  platform?: string
  topic?: string
  limit?: number
}) {
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.platform) query.set('platform', params.platform)
  if (params.topic) query.set('topic', params.topic)
  query.set('limit', String(params.limit || 100))
  return get<GraphResponse>(`/api/v1/admin/content-graph?${query.toString()}`)
}

export async function getMarketGraph(params: {
  start_date?: string
  end_date?: string
  state?: string
  game?: string
  view?: 'market_deep_entities'
  topic_scope?: 'company' | 'product' | 'operation'
  limit?: number
}) {
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.state) query.set('state', params.state)
  if (params.game) query.set('game', params.game)
  if (params.view) query.set('view', params.view)
  if (params.topic_scope) query.set('topic_scope', params.topic_scope)
  query.set('limit', String(params.limit || 100))
  return get<GraphResponse>(`/api/v1/admin/market-graph?${query.toString()}`)
}

export async function submitGraphStructuredSearchTasks(payload: GraphStructuredSearchRequest) {
  return post<GraphStructuredSearchResponse>('/api/v1/ingest/graph/structured-search', payload)
}
