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
import {
  deployCrawlerProject as deployCrawlerProjectByKey,
  fetchCrawlerDeployRunDetail,
  fetchCrawlerDeployRuns,
  fetchCrawlerProjectDetail,
  fetchCrawlerProjects,
  importCrawlerProject as createCrawlerProjectImport,
  rollbackCrawlerProject as rollbackCrawlerProjectByKey,
} from './api/services/crawlers'
import { fetchDeepHealth, fetchHealth } from './api/services/health'
import type {
  AutoCreateProjectPayload,
  AutoCreateProjectResult,
  CrawlerDeployRunItem,
  CrawlerProjectDeployPayload,
  CrawlerProjectImportPayload,
  CrawlerProjectRollbackPayload,
  InjectInitialProjectPayload,
  InjectInitialProjectResult,
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
  TopicItem,
} from './types'

export async function getHealth() {
  return fetchHealth()
}

export { getProjectKey, setProjectKey }

export async function getDeepHealth() {
  return fetchDeepHealth()
}

export {
  activateProject,
  archiveProject,
  createProject,
  deleteProject,
  getDashboardStats,
  listProjects,
  restoreProject,
  updateProject,
} from './api/domains/project-admin'
export {
  bindSiteEntry,
  discoverSiteEntries,
  discoverSiteEntriesAdvanced,
  extractResourcePoolFromDocuments,
  listResourcePoolUrls,
  listResourcePoolUrlsWithFilters,
  listSiteEntries,
  listSiteEntriesWithFilters,
  listSiteEntryGrouped,
  listSourceItems,
  listSourceLibraryChannels,
  listSourceLibraryItemsGrouped,
  listSourceLibraryItemsWithScope,
  recommendSiteEntriesBatch,
  recommendSiteEntry,
  refreshSourceLibraryItem,
  runSourceLibrary,
  simplifySiteEntries,
  syncSourceLibrary,
  syncSourceLibraryHandlerClusters,
  upsertSiteEntry,
  upsertSourceLibraryItem,
} from './api/domains/resource-source'
export {
  activateWorkflowGraphTemplateVersion,
  compileWorkflowGraph,
  createWorkflowGraphTemplate,
  createWorkflowGraphTemplateVersion,
  deleteWorkflowGraphTemplate,
  deleteWorkflowTemplate,
  exportGraph,
  getCompiledWorkflowGraph,
  getGraphConfig,
  getMarketGraph,
  getPolicyGraph,
  getSocialGraph,
  getWorkflowGraphTemplate,
  getWorkflowGraphTemplateVersion,
  normalizeGraphQueryParams,
  getWorkflowGraphRun,
  getWorkflowGraphRunEvents,
  listWorkflowGraphTemplates,
  listWorkflowGraphTemplateVersions,
  replayWorkflowGraphRun,
  getWorkflowTemplate,
  listWorkflows,
  runWorkflow,
  runWorkflowGraph,
  submitGraphStructuredSearchTasks,
  updateWorkflowGraphTemplate,
  upsertWorkflowTemplate,
} from './api/domains/graph-workflow'
export type {
  GraphKind,
  GraphQueryParams,
  NormalizedGraphQueryParams,
  WorkflowGraphCompilePayload,
  WorkflowGraphCompileResponse,
  WorkflowGraphRunDetailResponse,
  WorkflowGraphRunEventsResponse,
  WorkflowGraphRunPayload,
  WorkflowGraphRunResponse,
} from './api/domains/graph-workflow'
export type {
  WorkflowGraphTemplateItem,
  WorkflowGraphTemplateListResponse,
  WorkflowGraphTemplateMutationResponse,
  WorkflowGraphTemplatePayload,
  WorkflowGraphTemplateUpdatePayload,
  WorkflowGraphTemplateVersionItem,
  WorkflowGraphTemplateVersionListResponse,
  WorkflowGraphTemplateVersionMutationResponse,
  WorkflowGraphTemplateVersionPayload,
} from './types'
export {
  autosaveWritingDraft,
  createWritingDocument,
  exportWritingMarkdown,
  getWritingCardDetail,
  getWritingDocument,
  getWritingKeywordCards,
  getWritingLlmActionDetail,
  getWritingSuggest,
  listWritingCitations,
  listWritingDocuments,
  listWritingLlmActionHistory,
  listWritingTemplates,
  previewWritingKeywordCard,
  runWritingLlmAction,
  updateWritingDocument,
  upsertWritingCitations,
  validateWritingTemplate,
} from './api/domains/writing'
export type {
  AutosaveWritingDraftPayload,
  CreateWritingDocumentPayload,
  UpdateWritingDocumentPayload,
  ValidateWritingTemplatePayload,
  WritingCardDetailParams,
  WritingCitation,
  WritingDocument,
  WritingDraft,
  WritingKeywordCard,
  WritingKeywordCardDetail,
  WritingKeywordCardListResponse,
  WritingKeywordCardPreview,
  WritingKeywordCardPreviewRequest,
  WritingKeywordCardRequest,
  WritingKeywordCardSource,
  WritingLlmActionHistoryItem,
  WritingLlmActionId,
  WritingLlmActionPayload,
  WritingLlmActionResponse,
  WritingSuggestItem,
  WritingSuggestMode,
  WritingSuggestParams,
  WritingSuggestResponse,
  WritingTemplate,
  WritingTemplateValidation,
} from './api/domains/writing'

export async function autoCreateProject(payload: AutoCreateProjectPayload) {
  return post<AutoCreateProjectResult>(endpoints.projects.autoCreate, payload)
}

export async function injectInitialProject(payload: InjectInitialProjectPayload) {
  return post<InjectInitialProjectResult>(endpoints.projects.injectInitial, {
    source_project_key: payload.source_project_key || 'demo_proj',
    project_key: payload.project_key || null,
    name: payload.name || null,
    overwrite: payload.overwrite ?? true,
    activate: payload.activate ?? true,
  })
}

export async function listCrawlerProjects() {
  return fetchCrawlerProjects()
}

export async function getCrawlerProjectDetail(crawlerProjectKey: string) {
  return fetchCrawlerProjectDetail(crawlerProjectKey)
}

export async function importCrawlerProject(payload: CrawlerProjectImportPayload) {
  return createCrawlerProjectImport(payload)
}

export async function deployCrawlerProject(projectKey: string, payload: CrawlerProjectDeployPayload = {}) {
  return deployCrawlerProjectByKey(projectKey, payload)
}

export async function rollbackCrawlerProject(projectKey: string, payload: CrawlerProjectRollbackPayload = {}) {
  return rollbackCrawlerProjectByKey(projectKey, payload)
}

export async function listCrawlerDeployRuns(params?: { crawlerProjectKey?: string; limit?: number }) {
  return fetchCrawlerDeployRuns(params)
}

export async function getCrawlerDeployRunDetail(runId: string | number): Promise<CrawlerDeployRunItem> {
  return fetchCrawlerDeployRunDetail(runId)
}

export async function listIngestHistory(limit = 8) {
  const query = new URLSearchParams({ limit: String(limit) })
  const data = await get<IngestJobRow[] | { items?: IngestJobRow[] }>(`${endpoints.ingest.history}?${query.toString()}`)
  return asList<IngestJobRow>(data)
}

export async function listProcessTasks(limit = 50) {
  const query = new URLSearchParams({ limit: String(limit) })
  return get<ProcessTaskList>(`${endpoints.process.list}?${query.toString()}`)
}

export async function getProcessStats() {
  return get<ProcessTaskStats>(endpoints.process.stats)
}

export async function listProcessHistory(limit = 50) {
  const query = new URLSearchParams({ limit: String(limit) })
  return get<ProcessHistoryResponse>(`${endpoints.process.history}?${query.toString()}`)
}

export async function getProcessTaskDetail(taskId: string) {
  return get<ProcessTaskDetail>(endpoints.process.task(taskId))
}

export async function getProcessTaskLogs(taskId: string, tail = 200) {
  const query = new URLSearchParams({ tail: String(tail) })
  return get<ProcessTaskLogsResponse>(`${endpoints.process.logs(taskId)}?${query.toString()}`)
}

export async function cancelTask(taskId: string, terminate = false) {
  const query = new URLSearchParams({ terminate: terminate ? 'true' : 'false' })
  return post(`${endpoints.process.cancel(taskId)}?${query.toString()}`, null)
}

export async function generateKeywords(payload: {
  topic: string
  language: string
  platform?: string | null
  topic_focus?: string
  base_keywords?: string[]
}) {
  return post<{ search_keywords?: string[]; keywords?: string[] }>(endpoints.discovery.generateKeywords, payload)
}

export async function ingestPolicy(payload: {
  state: string
  source_hint?: string | null
  async_mode: boolean
}) {
  return post<Record<string, unknown>>(endpoints.ingest.policy, payload)
}

export async function ingestPolicyRegulation(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>(endpoints.ingest.policyRegulation, payload)
}

export async function ingestMarket(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>(endpoints.ingest.market, payload)
}

export type IngestSingleUrlPayload = {
  url: string
  query_terms?: string[] | null
  strict_mode?: boolean
  search_expand?: boolean
  search_expand_limit?: number
  search_provider?: 'auto' | 'google' | 'ddg_html' | string | null
  search_fallback_provider?: 'ddg_html' | string | null
  fallback_on_insufficient?: boolean
  allow_search_summary_write?: boolean
  min_results_required?: number | null
  target_candidates?: number | null
  decode_redirect_wrappers?: boolean
  filter_low_value_candidates?: boolean
  light_filter_enabled?: boolean
  light_filter_min_score?: number
  light_filter_reject_static_assets?: boolean
  light_filter_reject_search_noise_domain?: boolean
  project_key?: string | null
  async_mode?: boolean
}

export async function ingestSingleUrl(payload: IngestSingleUrlPayload) {
  return post<Record<string, unknown>>(endpoints.ingest.urlSingle, payload)
}

export async function ingestSocial(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>(endpoints.ingest.socialSentiment, payload)
}

export async function ingestCommodity(payload: { limit: number; async_mode: boolean }) {
  return post<Record<string, unknown>>(endpoints.ingest.commodityMetrics, payload)
}

export async function ingestEcom(payload: { limit: number; async_mode: boolean }) {
  return post<Record<string, unknown>>(endpoints.ingest.ecomPrices, payload)
}

export async function getEnvSettings() {
  return fetchEnvSettings()
}

export async function updateEnvSettings(payload: Record<string, string>) {
  return saveEnvSettings(payload)
}

export async function listTopics() {
  const data = await get<TopicItem[] | { items?: TopicItem[] }>(endpoints.topics.root)
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
  return post<{ id: number }>(endpoints.topics.root, payload)
}

export async function deleteTopic(topicId: number) {
  return del<{ deleted: number }>(endpoints.topics.byId(topicId))
}

export async function listProducts() {
  const data = await get<ProductItem[] | { items?: ProductItem[] }>(endpoints.products.root)
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
  return post<{ id: number }>(endpoints.products.root, payload)
}

export async function deleteProduct(productId: number) {
  return del<{ deleted: number }>(endpoints.products.byId(productId))
}

export async function getPolicyStats() {
  return get<PolicyStats>(endpoints.policies.stats)
}

export async function getPromptTimeDensity(params: {
  time_window?: string
  start?: string
  end?: string
  bucket?: 'day' | 'week' | 'month'
  prompt_group_ids?: string[]
  source_domains?: string[]
  normalize?: boolean
}) {
  const query = new URLSearchParams()
  if (params.time_window) query.set('time_window', params.time_window)
  if (params.start) query.set('start', params.start)
  if (params.end) query.set('end', params.end)
  if (params.bucket) query.set('bucket', params.bucket)
  if (typeof params.normalize === 'boolean') query.set('normalize', String(params.normalize))
  ;(params.prompt_group_ids || []).forEach((v) => v && query.append('prompt_group_ids', v))
  ;(params.source_domains || []).forEach((v) => v && query.append('source_domains', v))
  const url = query.toString() ? `${endpoints.stats.promptTimeDensity}?${query.toString()}` : endpoints.stats.promptTimeDensity
  return get<Record<string, unknown>>(url)
}

export async function getPromptTimeDensityPriority(params: {
  end?: string
  candidate_windows?: string[]
  prompt_group_ids?: string[]
  source_domains?: string[]
  prefer_low_density?: boolean
  exclude_high_dup?: boolean
}) {
  const query = new URLSearchParams()
  if (params.end) query.set('end', params.end)
  ;(params.candidate_windows || []).forEach((v) => v && query.append('candidate_windows', v))
  ;(params.prompt_group_ids || []).forEach((v) => v && query.append('prompt_group_ids', v))
  ;(params.source_domains || []).forEach((v) => v && query.append('source_domains', v))
  if (typeof params.prefer_low_density === 'boolean') query.set('prefer_low_density', String(params.prefer_low_density))
  if (typeof params.exclude_high_dup === 'boolean') query.set('exclude_high_dup', String(params.exclude_high_dup))
  const url = query.toString() ? `${endpoints.stats.promptTimeDensityPriority}?${query.toString()}` : endpoints.stats.promptTimeDensityPriority
  return get<Record<string, unknown>>(url)
}

export async function listPolicies(state = '', page = 1, pageSize = 20) {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (state.trim()) query.set('state', state.trim().toUpperCase())
  const data = await get<PolicyItem[] | { items?: PolicyItem[] }>(`${endpoints.policies.root}?${query.toString()}`)
  return asList<PolicyItem>(data)
}

export async function getPolicyDetail(policyId: number) {
  return get<PolicyDetail>(endpoints.policies.byId(policyId))
}

export async function listLlmConfigs() {
  const data = await get<LlmServiceConfigItem[] | { items?: LlmServiceConfigItem[] }>(endpoints.llm.root)
  return asList<LlmServiceConfigItem>(data)
}

export async function listProjectLlmTemplates(projectKey = getProjectKey()) {
  return get<LlmProjectTemplatesResponse>(endpoints.llm.project(projectKey))
}

export async function updateProjectLlmTemplate(
  serviceName: string,
  payload: LlmTemplateUpdatePayload,
  projectKey = getProjectKey(),
) {
  return put<LlmTemplateUpdateResponse>(endpoints.llm.projectService(projectKey, serviceName), payload)
}

export async function copyProjectLlmTemplates(payload: LlmTemplateCopyPayload, projectKey = getProjectKey()) {
  return post<LlmTemplateCopyResponse>(endpoints.llm.copyFrom(projectKey), payload)
}

export {
  bulkUpdateDocumentExtractedData,
  clearDocumentExtractedData,
  deleteAdminDocuments,
  getAdminDocument,
  getAdminStats,
  getSearchHistory,
  listAdminDocuments,
  rawImportDocuments,
  reExtractDocuments,
  topicExtractDocuments,
  updateDocumentExtractedData,
} from './api/domains/project-admin'

export async function cleanupGovernance(retentionDays: number) {
  return post<Record<string, unknown>>(endpoints.governance.cleanup, { retention_days: retentionDays })
}

export async function syncAggregator(asyncMode = true) {
  return post<Record<string, unknown>>(endpoints.governance.aggregatorSync, { async_mode: asyncMode })
}
