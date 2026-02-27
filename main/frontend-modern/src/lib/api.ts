import axios from 'axios'
import type {
  AdminStats,
  ApiEnvelope,
  DashboardStats,
  LlmServiceConfigItem,
  GraphConfigResponse,
  GraphResponse,
  HealthResponse,
  IngestJobRow,
  PolicyItem,
  PolicyDetail,
  PolicyStats,
  ProcessHistoryResponse,
  ProcessTaskList,
  ProcessTaskStats,
  ProductItem,
  ProjectItem,
  ResourcePoolUrlItem,
  SearchHistoryItem,
  SiteEntryGroupedResponse,
  SiteEntryItem,
  SourceLibraryItem,
  TopicItem,
  WorkflowTemplate,
  EnvSettings,
} from './types'

const STORAGE_KEY = 'market_project_key'

function normalizeProjectKey(raw: string) {
  return (
    String(raw || 'default')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_+|_+$/g, '') || 'default'
  )
}

export function getProjectKey() {
  return normalizeProjectKey(window.localStorage.getItem(STORAGE_KEY) || 'default')
}

export function setProjectKey(projectKey: string) {
  const next = normalizeProjectKey(projectKey)
  window.localStorage.setItem(STORAGE_KEY, next)
  return next
}

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
})

client.interceptors.request.use((config) => {
  const projectKey = getProjectKey()
  config.headers['X-Project-Key'] = projectKey

  const original = String(config.url || '')
  const isAbsolute = /^https?:\/\//i.test(original)
  const url = new URL(original || '/', isAbsolute ? undefined : window.location.origin)

  if (url.pathname.startsWith('/api/')) {
    url.searchParams.set('project_key', projectKey)
  }

  config.url = isAbsolute ? url.toString() : `${url.pathname}${url.search}${url.hash}`
  return config
})

function unwrap<T>(payload: ApiEnvelope<T> | T): T {
  if (payload && typeof payload === 'object' && 'status' in payload && 'data' in payload) {
    const envelope = payload as ApiEnvelope<T>
    if (envelope.status === 'error') {
      throw new Error(envelope.error?.message || 'Request failed')
    }
    return envelope.data as T
  }
  return payload as T
}

async function get<T>(url: string) {
  const { data } = await client.get<ApiEnvelope<T> | T>(url)
  return unwrap<T>(data)
}

async function post<T>(url: string, body: unknown) {
  const { data } = await client.post<ApiEnvelope<T> | T>(url, body)
  return unwrap<T>(data)
}

async function patch<T>(url: string, body: unknown) {
  const { data } = await client.patch<ApiEnvelope<T> | T>(url, body)
  return unwrap<T>(data)
}

async function del<T>(url: string) {
  const { data } = await client.delete<ApiEnvelope<T> | T>(url)
  return unwrap<T>(data)
}

function asList<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object' && 'items' in value) {
    const items = (value as { items?: unknown }).items
    return Array.isArray(items) ? (items as T[]) : []
  }
  return []
}

export async function getHealth() {
  return get<HealthResponse>('/api/v1/health')
}

export async function getDashboardStats() {
  return get<DashboardStats>('/api/v1/dashboard/stats')
}

export async function listProjects() {
  const data = await get<ProjectItem[] | { items?: ProjectItem[] }>('/api/v1/projects')
  return asList<ProjectItem>(data)
}

export async function activateProject(projectKey: string) {
  const key = normalizeProjectKey(projectKey)
  await post(`/api/v1/projects/${encodeURIComponent(key)}/activate`, null)
  setProjectKey(key)
  return key
}

export async function createProject(payload: { project_key: string; name: string; enabled?: boolean }) {
  return post<{ id?: number; schema_name?: string }>('/api/v1/projects', {
    ...payload,
    enabled: payload.enabled ?? true,
  })
}

export async function updateProject(projectKey: string, payload: { name?: string; enabled?: boolean }) {
  return patch<{ project_key: string }>(`/api/v1/projects/${encodeURIComponent(projectKey)}`, payload)
}

export async function archiveProject(projectKey: string) {
  return post<{ archived: boolean }>(`/api/v1/projects/${encodeURIComponent(projectKey)}/archive`, null)
}

export async function restoreProject(projectKey: string) {
  return post<{ archived: boolean }>(`/api/v1/projects/${encodeURIComponent(projectKey)}/restore`, null)
}

export async function deleteProject(projectKey: string, hard = false) {
  return del<{ deleted: boolean }>(`/api/v1/projects/${encodeURIComponent(projectKey)}?hard=${hard ? 'true' : 'false'}`)
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
  return get<EnvSettings>('/api/v1/config/env')
}

export async function updateEnvSettings(payload: Record<string, string>) {
  return post<{ updated?: string[] }>('/api/v1/config/env', payload)
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

export async function getAdminStats() {
  return get<AdminStats>('/api/v1/admin/stats')
}

export async function getSearchHistory(page = 1, pageSize = 50) {
  const data = await get<SearchHistoryItem[] | { items?: SearchHistoryItem[] }>(
    `/api/v1/admin/search-history?page=${page}&page_size=${pageSize}`,
  )
  return asList<SearchHistoryItem>(data)
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
  limit?: number
}) {
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.state) query.set('state', params.state)
  if (params.game) query.set('game', params.game)
  if (params.view) query.set('view', params.view)
  query.set('limit', String(params.limit || 100))
  return get<GraphResponse>(`/api/v1/admin/market-graph?${query.toString()}`)
}
