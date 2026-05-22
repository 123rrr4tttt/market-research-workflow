import { endpoints } from './api/endpoints'
import {
  asList,
  CODEX_AUTH_REQUIRED_EVENT,
  getProjectKey,
  httpDelete as del,
  httpGet as get,
  httpPost as post,
  httpPut as put,
  resolveApiUrl,
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
  AgentApprovalResolvePayload,
  AgentApprovalItem,
  AgentArtifactItem,
  AgentArtifactListResult,
  AgentCoordinatorPassResult,
  AgentEventItem,
  AgentEventListResult,
  AgentMessageItem,
  AgentMessageListResult,
  AgentSessionMessageCreatePayload,
  AgentSessionCancelPayload,
  AgentSessionCreatePayload,
  AgentSessionDetail,
  AgentSessionItem,
  AgentSessionListResult,
  AgentApprovalRequestPayload,
  AgentChatApprovalContinuePayload,
  AgentChatApprovalContinueResult,
  AgentChatCapabilitiesResult,
  AgentSessionTaskRetryPayload,
  AgentChatTurnPayload,
  AgentChatTurnResult,
  AgentSessionEventStreamStatus,
  AgentTaskItem,
  AgentTaskListResult,
  AgentBatchEventsResult,
  AgentBatchJobDetail,
  AgentBatchItemsResult,
  AgentBatchNlCommandPayload,
  AgentBatchNlCommandResult,
  AgentBatchRetryPayload,
  AgentBatchRetryResult,
  AgentBatchRuleSetValidatePayload,
  AgentBatchRuleSetValidateResult,
  AgentBatchSubmitPayload,
  AgentBatchSubmitResult,
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

function extractSectionList<T>(value: unknown, keys: string[] = ['items']): T[] {
  if (Array.isArray(value)) return value as T[]
  if (!value || typeof value !== 'object') return []
  const record = value as Record<string, unknown>
  for (const key of keys) {
    const candidate = record[key]
    if (Array.isArray(candidate)) return candidate as T[]
  }
  return []
}

export async function getHealth() {
  return fetchHealth()
}

export { CODEX_AUTH_REQUIRED_EVENT, getProjectKey, setProjectKey }

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
  bootstrapCodexCliLogin,
  getCodexAuthStatus,
  logoutCodexAuth,
  openCodexAuthLoginPopup,
} from './api/domains/codex-auth'
export type CodexAuthStatusResponse = import('./api/domains/codex-auth').CodexAuthStatusResponse
export type CodexCliBootstrapResponse = import('./api/domains/codex-auth').CodexCliBootstrapResponse
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
  registerExternalProject,
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
  closeClueChain,
  createClueChain,
  decideClueChainCandidate,
  expandClueChain,
  getClueChain,
  listClueChains,
} from './api/domains/clue-chains'
export type ChainBudget = import('./api/domains/clue-chains').ChainBudget
export type ChainCandidate = import('./api/domains/clue-chains').ChainCandidate
export type ChainCandidateDecisionStatus = import('./api/domains/clue-chains').ChainCandidateDecisionStatus
export type ChainCreatedBy = import('./api/domains/clue-chains').ChainCreatedBy
export type ChainDecision = import('./api/domains/clue-chains').ChainDecision
export type ChainDecisionAction = import('./api/domains/clue-chains').ChainDecisionAction
export type ChainEdge = import('./api/domains/clue-chains').ChainEdge
export type ChainEvidence = import('./api/domains/clue-chains').ChainEvidence
export type ChainEvidenceSourceKind = import('./api/domains/clue-chains').ChainEvidenceSourceKind
export type ChainEvidenceStatus = import('./api/domains/clue-chains').ChainEvidenceStatus
export type ChainExpansionMode = import('./api/domains/clue-chains').ChainExpansionMode
export type ChainFrontierItem = import('./api/domains/clue-chains').ChainFrontierItem
export type ChainHop = import('./api/domains/clue-chains').ChainHop
export type ChainHopStatus = import('./api/domains/clue-chains').ChainHopStatus
export type ChainOperatorPolicy = import('./api/domains/clue-chains').ChainOperatorPolicy
export type ChainSourceRef = import('./api/domains/clue-chains').ChainSourceRef
export type ClueChain = import('./api/domains/clue-chains').ClueChain
export type ClueChainCandidateDecisionPayload = import('./api/domains/clue-chains').ClueChainCandidateDecisionPayload
export type ClueChainCandidateDecisionResponse =
  import('./api/domains/clue-chains').ClueChainCandidateDecisionResponse
export type ClueChainClosePayload = import('./api/domains/clue-chains').ClueChainClosePayload
export type ClueChainCloseResponse = import('./api/domains/clue-chains').ClueChainCloseResponse
export type ClueChainCreatePayload = import('./api/domains/clue-chains').ClueChainCreatePayload
export type ClueChainDetailResponse = import('./api/domains/clue-chains').ClueChainDetailResponse
export type ClueChainExpandPayload = import('./api/domains/clue-chains').ClueChainExpandPayload
export type ClueChainExpandResponse = import('./api/domains/clue-chains').ClueChainExpandResponse
export type ClueChainListParams = import('./api/domains/clue-chains').ClueChainListParams
export type ClueChainListResponse = import('./api/domains/clue-chains').ClueChainListResponse
export type ClueChainMutationResponse = import('./api/domains/clue-chains').ClueChainMutationResponse
export type ClueChainStatus = import('./api/domains/clue-chains').ClueChainStatus
export {
  activateWorkflowGraphTemplateVersion,
  buildWorkflowGraphEvidencePack,
  buildWorkflowGraphReportingHandoff,
  buildWorkflowGraphWritingHandoff,
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
  getWorkflowGraphCuratedState,
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
  saveWorkflowGraphCuratedDraft,
  submitGraphStructuredSearchTasks,
  submitWorkflowGraphCuratedDraft,
  syncWorkflowGraphCuratedState,
  updateWorkflowGraphTemplate,
  upsertWorkflowTemplate,
} from './api/domains/graph-workflow'
export type GraphKind = import('./api/domains/graph-workflow').GraphKind
export type GraphQueryParams = import('./api/domains/graph-workflow').GraphQueryParams
export type NormalizedGraphQueryParams = import('./api/domains/graph-workflow').NormalizedGraphQueryParams
export type WorkflowGraphCompilePayload = import('./api/domains/graph-workflow').WorkflowGraphCompilePayload
export type WorkflowGraphCompileResponse = import('./api/domains/graph-workflow').WorkflowGraphCompileResponse
export type WorkflowGraphCuratedDraftPayload = import('./api/domains/graph-workflow').WorkflowGraphCuratedDraftPayload
export type WorkflowGraphCuratedDsl = import('./api/domains/graph-workflow').WorkflowGraphCuratedDsl
export type WorkflowGraphCuratedStateResponse = import('./api/domains/graph-workflow').WorkflowGraphCuratedStateResponse
export type WorkflowGraphCuratedSubmitPayload = import('./api/domains/graph-workflow').WorkflowGraphCuratedSubmitPayload
export type WorkflowGraphCuratedSyncPayload = import('./api/domains/graph-workflow').WorkflowGraphCuratedSyncPayload
export type WorkflowGraphEvidencePackPayload = import('./api/domains/graph-workflow').WorkflowGraphEvidencePackPayload
export type WorkflowGraphEvidencePackResponse = import('./api/domains/graph-workflow').WorkflowGraphEvidencePackResponse
export type WorkflowGraphHandoffResponse = import('./api/domains/graph-workflow').WorkflowGraphHandoffResponse
export type WorkflowGraphReportingHandoffPayload = import('./api/domains/graph-workflow').WorkflowGraphReportingHandoffPayload
export type WorkflowGraphRunDetailResponse = import('./api/domains/graph-workflow').WorkflowGraphRunDetailResponse
export type WorkflowGraphRunEventsResponse = import('./api/domains/graph-workflow').WorkflowGraphRunEventsResponse
export type WorkflowGraphRunPayload = import('./api/domains/graph-workflow').WorkflowGraphRunPayload
export type WorkflowGraphRunResponse = import('./api/domains/graph-workflow').WorkflowGraphRunResponse
export type WorkflowGraphWritingHandoffPayload = import('./api/domains/graph-workflow').WorkflowGraphWritingHandoffPayload
export type WorkflowGraphTemplateItem = import('./types').WorkflowGraphTemplateItem
export type WorkflowGraphTemplateListResponse = import('./types').WorkflowGraphTemplateListResponse
export type WorkflowGraphTemplateMutationResponse = import('./types').WorkflowGraphTemplateMutationResponse
export type WorkflowGraphTemplatePayload = import('./types').WorkflowGraphTemplatePayload
export type WorkflowGraphTemplateUpdatePayload = import('./types').WorkflowGraphTemplateUpdatePayload
export type WorkflowGraphTemplateVersionItem = import('./types').WorkflowGraphTemplateVersionItem
export type WorkflowGraphTemplateVersionListResponse = import('./types').WorkflowGraphTemplateVersionListResponse
export type WorkflowGraphTemplateVersionMutationResponse = import('./types').WorkflowGraphTemplateVersionMutationResponse
export type WorkflowGraphTemplateVersionPayload = import('./types').WorkflowGraphTemplateVersionPayload
export {
  autosaveWritingDraft,
  createWritingDocument,
  deleteWritingDocument,
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
export type AutosaveWritingDraftPayload = import('./api/domains/writing').AutosaveWritingDraftPayload
export type CreateWritingDocumentPayload = import('./api/domains/writing').CreateWritingDocumentPayload
export type UpdateWritingDocumentPayload = import('./api/domains/writing').UpdateWritingDocumentPayload
export type ValidateWritingTemplatePayload = import('./api/domains/writing').ValidateWritingTemplatePayload
export type WritingCardDetailParams = import('./api/domains/writing').WritingCardDetailParams
export type WritingCitation = import('./api/domains/writing').WritingCitation
export type WritingContextEnvelope = import('./api/domains/writing').WritingContextEnvelope
export type WritingDocument = import('./api/domains/writing').WritingDocument
export type WritingDraft = import('./api/domains/writing').WritingDraft
export type WritingKeywordCard = import('./api/domains/writing').WritingKeywordCard
export type WritingKeywordCardDetail = import('./api/domains/writing').WritingKeywordCardDetail
export type WritingKeywordCardListResponse = import('./api/domains/writing').WritingKeywordCardListResponse
export type WritingKeywordCardPreview = import('./api/domains/writing').WritingKeywordCardPreview
export type WritingKeywordCardPreviewRequest = import('./api/domains/writing').WritingKeywordCardPreviewRequest
export type WritingKeywordCardRequest = import('./api/domains/writing').WritingKeywordCardRequest
export type WritingKeywordCardSource = import('./api/domains/writing').WritingKeywordCardSource
export type WritingLlmActionHistoryItem = import('./api/domains/writing').WritingLlmActionHistoryItem
export type WritingLlmActionId = import('./api/domains/writing').WritingLlmActionId
export type WritingLlmActionPayload = import('./api/domains/writing').WritingLlmActionPayload
export type WritingLlmActionResponse = import('./api/domains/writing').WritingLlmActionResponse
export type WritingSuggestItem = import('./api/domains/writing').WritingSuggestItem
export type WritingSuggestMode = import('./api/domains/writing').WritingSuggestMode
export type WritingSuggestParams = import('./api/domains/writing').WritingSuggestParams
export type WritingSuggestResponse = import('./api/domains/writing').WritingSuggestResponse
export type WritingTemplate = import('./api/domains/writing').WritingTemplate
export type WritingTemplateValidation = import('./api/domains/writing').WritingTemplateValidation

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

export async function ingestDataApi(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>(endpoints.ingest.dataApi, payload)
}

export async function ingestCommodity(payload: { limit: number; async_mode: boolean }) {
  return post<Record<string, unknown>>(endpoints.ingest.commodityMetrics, payload)
}

export async function ingestEcom(payload: { limit: number; async_mode: boolean }) {
  return post<Record<string, unknown>>(endpoints.ingest.ecomPrices, payload)
}

export async function submitAgentBatchJob(payload: AgentBatchSubmitPayload) {
  return post<AgentBatchSubmitResult>(endpoints.agentBatch.jobs, payload)
}

export async function getAgentBatchJob(jobId: string) {
  return get<AgentBatchJobDetail>(endpoints.agentBatch.jobById(jobId))
}

export async function listAgentBatchItems(jobId: string) {
  return get<AgentBatchItemsResult>(endpoints.agentBatch.itemsByJob(jobId))
}

export async function retryAgentBatchJob(jobId: string, payload: AgentBatchRetryPayload = {}) {
  return post<AgentBatchRetryResult>(endpoints.agentBatch.retryByJob(jobId), payload)
}

export async function getAgentBatchEvents(jobId: string) {
  return get<AgentBatchEventsResult>(endpoints.agentBatch.eventsByJob(jobId))
}

export async function validateAgentBatchRuleSet(payload: AgentBatchRuleSetValidatePayload) {
  return post<AgentBatchRuleSetValidateResult>(endpoints.agentBatch.ruleSetValidate, payload)
}

export async function runAgentBatchNlCommand(payload: AgentBatchNlCommandPayload) {
  return post<AgentBatchNlCommandResult>(endpoints.agentBatch.nlCommandDirect, payload)
}

export async function runAgentChatTurn(payload: AgentChatTurnPayload) {
  return post<AgentChatTurnResult>(endpoints.agentChat.turn, payload)
}

export async function runAgentChatTurnStream(payload: AgentChatTurnPayload) {
  return fetch(resolveApiUrl(endpoints.agentChat.turnStream), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export type AgentChatTurnStreamHandlers = {
  onEvent?: (event: AgentEventItem) => void
  onStatus?: (status: AgentSessionEventStreamStatus) => void
  onFinalAnswer?: (answer: string, result?: AgentChatTurnResult | null) => void
}

function parseAgentChatTurnSseBlock(block: string) {
  let eventType = 'message'
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      eventType = line.replace(/^event:\s*/, '').trim() || eventType
    } else if (line.startsWith('data:')) {
      dataLines.push(line.replace(/^data:\s?/, ''))
    }
  }
  if (!dataLines.length) return null
  try {
    return { eventType, data: JSON.parse(dataLines.join('\n')) as Record<string, unknown> }
  } catch {
    return null
  }
}

function isAgentEventPayload(value: unknown): value is AgentEventItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return typeof item.event_type === 'string' || typeof item.event_id === 'string' || typeof item.seq === 'number'
}

export async function runAgentChatTurnStreaming(
  payload: AgentChatTurnPayload,
  handlers: AgentChatTurnStreamHandlers = {},
): Promise<AgentChatTurnResult> {
  handlers.onStatus?.('connecting')
  const response = await runAgentChatTurnStream(payload)
  if (!response.ok) {
    handlers.onStatus?.('error')
    throw new Error(`agent chat stream failed: ${response.status}`)
  }
  if (!response.body) {
    handlers.onStatus?.('error')
    throw new Error('agent chat stream did not return a readable body')
  }

  handlers.onStatus?.('open')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult: AgentChatTurnResult | null = null

  const processBlock = (block: string) => {
    const parsed = parseAgentChatTurnSseBlock(block)
    if (!parsed) return
    const { eventType, data } = parsed
    if (eventType === 'interactive_agent.error' || eventType === 'agent_core.error') {
      handlers.onStatus?.('error')
      throw new Error(String((data.error as Record<string, unknown> | undefined)?.message || 'agent chat stream error'))
    }
    if (isAgentEventPayload(data)) {
      handlers.onEvent?.(data)
    }
    if (eventType === 'interactive_agent.final_answer' || eventType === 'agent_core.final_answer') {
      const dataRecord = data as Record<string, unknown>
      const result = dataRecord.result
      if (result && typeof result === 'object') {
        finalResult = result as AgentChatTurnResult
        handlers.onFinalAnswer?.(String((finalResult as AgentChatTurnResult).final_answer || ''), finalResult)
      } else if (typeof dataRecord.final_answer === 'string' || typeof dataRecord.contract_version === 'string') {
        finalResult = dataRecord as AgentChatTurnResult
        handlers.onFinalAnswer?.(String(dataRecord.final_answer || ''), finalResult)
      }
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\n\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      processBlock(block)
    }
    if (done) break
  }
  if (buffer.trim()) {
    processBlock(buffer)
  }
  handlers.onStatus?.('closed')
  if (!finalResult) {
    throw new Error('agent chat stream closed before final answer')
  }
  return finalResult
}

export async function listAgentChatCapabilities(projectKey?: string | null) {
  const query = new URLSearchParams()
  if (projectKey) query.set('project_key', projectKey)
  const suffix = query.toString()
  return get<AgentChatCapabilitiesResult>(suffix ? `${endpoints.agentChat.capabilities}?${suffix}` : endpoints.agentChat.capabilities)
}

export async function continueAgentChatApproval(approvalId: string, payload: AgentChatApprovalContinuePayload = {}) {
  return post<AgentChatApprovalContinueResult>(endpoints.agentChat.approvalContinue(approvalId), payload)
}

export async function createAgentSession(payload: AgentSessionCreatePayload) {
  return post<AgentSessionDetail>(endpoints.agentSessions.root, payload)
}

export async function listAgentSessions() {
  const data = await get<AgentSessionItem[] | AgentSessionListResult | { sessions?: AgentSessionItem[]; items?: AgentSessionItem[] }>(
    endpoints.agentSessions.root,
  )
  return extractSectionList<AgentSessionItem>(data, ['sessions', 'items'])
}

export async function getAgentSession(sessionId: string) {
  return get<AgentSessionDetail>(endpoints.agentSessions.byId(sessionId))
}

export async function listAgentSessionTasks(sessionId: string) {
  const data = await get<AgentTaskItem[] | AgentTaskListResult | { tasks?: AgentTaskItem[]; items?: AgentTaskItem[] }>(
    endpoints.agentSessions.tasksBySession(sessionId),
  )
  return extractSectionList<AgentTaskItem>(data, ['tasks', 'items'])
}

export async function listAgentSessionMessages(sessionId: string) {
  const data = await get<AgentMessageItem[] | AgentMessageListResult | { messages?: AgentMessageItem[]; items?: AgentMessageItem[] }>(
    endpoints.agentSessions.messagesBySession(sessionId),
  )
  return extractSectionList<AgentMessageItem>(data, ['messages', 'items'])
}

export async function createAgentSessionMessage(sessionId: string, payload: AgentSessionMessageCreatePayload) {
  return post<AgentMessageItem>(endpoints.agentSessions.messagesBySession(sessionId), payload)
}

export async function listAgentSessionEvents(sessionId: string) {
  const data = await get<AgentEventItem[] | AgentEventListResult | { events?: AgentEventItem[]; items?: AgentEventItem[] }>(
    endpoints.agentSessions.eventsBySession(sessionId),
  )
  return extractSectionList<AgentEventItem>(data, ['events', 'items'])
}

const AGENT_SESSION_STREAM_EVENT_TYPES = [
  'session.created',
  'session.canceled',
  'task.created',
  'task.claimed',
  'task.heartbeat',
  'task.released',
  'task.retried',
  'task.expired',
  'task.unblocked',
  'message.created',
  'artifact.upserted',
  'approval.requested',
  'approval.waiting',
  'approval.resolved',
  'approval.approved',
  'approval.failed',
  'memory.updated',
  'compat.projected',
  'compat.job_projected',
  'compat.job_state_projected',
  'workflow_graph.run_projected',
  'coordinator.dispatch_planned',
  'coordinator.noop',
  'coordinator.synthesis_completed',
  'interactive_agent.model_delta',
  'interactive_agent.turn_started',
  'interactive_agent.capability_planned',
  'interactive_agent.tool_call_requested',
  'interactive_agent.tool_call_started',
  'interactive_agent.tool_call_result',
  'interactive_agent.capability_executed',
  'interactive_agent.approval_continued',
  'interactive_agent.final_answer',
  'interactive_agent.failed',
  'agent_core.session_started',
  'agent_core.user_message',
  'agent_core.assistant_delta',
  'agent_core.assistant_message',
  'agent_core.tool_call_requested',
  'agent_core.permission_requested',
  'agent_core.tool_call_started',
  'agent_core.tool_progress',
  'agent_core.tool_result',
  'agent_core.approval_resolved',
  'agent_core.run_resumed',
  'agent_core.final_answer',
  'agent_core.error',
]

export type AgentSessionEventStreamOptions = {
  sinceSeq?: number
  pollSeconds?: number
  maxSeconds?: number
}

export type AgentSessionEventStreamHandlers = {
  onEvent?: (event: AgentEventItem) => void
  onStatus?: (status: AgentSessionEventStreamStatus) => void
  onError?: (error: Event) => void
}

function parseAgentSessionStreamEvent(message: MessageEvent): AgentEventItem | null {
  try {
    const parsed = JSON.parse(String(message.data || '')) as AgentEventItem
    if (!parsed || typeof parsed !== 'object') return null
    if (!parsed.event_id && !parsed.event_type && !parsed.seq) return null
    return parsed
  } catch {
    return null
  }
}

export function openAgentSessionEventStream(
  sessionId: string,
  handlers: AgentSessionEventStreamHandlers = {},
  options: AgentSessionEventStreamOptions = {},
) {
  if (!sessionId || typeof window === 'undefined' || typeof EventSource === 'undefined') {
    handlers.onStatus?.('idle')
    return () => undefined
  }
  const params = new URLSearchParams({
    since_seq: String(Math.max(0, Math.trunc(options.sinceSeq || 0))),
    poll_seconds: String(options.pollSeconds ?? 1),
    max_seconds: String(options.maxSeconds ?? 120),
  })
  const streamUrl = resolveApiUrl(`${endpoints.agentSessions.streamBySession(sessionId)}?${params.toString()}`)
  const source = new EventSource(streamUrl, { withCredentials: true })
  let closed = false
  const emitStatus = (status: AgentSessionEventStreamStatus) => {
    if (!closed) handlers.onStatus?.(status)
  }
  const handleMessage = (event: Event) => {
    const parsed = parseAgentSessionStreamEvent(event as MessageEvent)
    if (parsed) handlers.onEvent?.(parsed)
  }

  emitStatus('connecting')
  source.onopen = () => emitStatus('open')
  source.onmessage = handleMessage
  for (const eventType of AGENT_SESSION_STREAM_EVENT_TYPES) {
    source.addEventListener(eventType, handleMessage)
  }
  source.onerror = (event) => {
    handlers.onError?.(event)
    emitStatus('error')
    source.close()
  }
  return () => {
    closed = true
    source.close()
    handlers.onStatus?.('closed')
  }
}

export async function listAgentSessionArtifacts(sessionId: string) {
  const data = await get<
    AgentArtifactItem[] | AgentArtifactListResult | { artifacts?: AgentArtifactItem[]; items?: AgentArtifactItem[] }
  >(endpoints.agentSessions.artifactsBySession(sessionId))
  return extractSectionList<AgentArtifactItem>(data, ['artifacts', 'items'])
}

export async function retryAgentSessionTask(sessionId: string, payload: AgentSessionTaskRetryPayload) {
  return post<AgentSessionDetail>(endpoints.agentSessions.retryTaskBySession(sessionId), payload)
}

export async function cancelAgentSession(sessionId: string, payload: AgentSessionCancelPayload = {}) {
  return post<AgentSessionDetail>(endpoints.agentSessions.cancelBySession(sessionId), payload)
}

export async function reclaimExpiredAgentSessionTasks(sessionId: string) {
  return post<{ items?: AgentTaskItem[] }>(endpoints.agentSessions.reclaimExpiredBySession(sessionId), {})
}

export async function runAgentSessionCoordinatorPass(sessionId: string) {
  return post<AgentCoordinatorPassResult>(endpoints.agentSessions.coordinatorPassBySession(sessionId), {})
}

export async function requestAgentSessionApproval(sessionId: string, payload: AgentApprovalRequestPayload) {
  return post(endpoints.agentSessions.requestApprovalBySession(sessionId), payload)
}

export async function resolveAgentApproval(approvalId: string, payload: AgentApprovalResolvePayload) {
  return post<AgentApprovalItem>(endpoints.agentSessions.resolveApprovalById(approvalId), payload)
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
