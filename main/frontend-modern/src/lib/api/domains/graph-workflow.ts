import { endpoints } from '../endpoints'
import {
  asList,
  getProjectKey,
  httpDelete as del,
  httpGet as get,
  httpPatch as patch,
  httpPost as post,
} from '../client'
import type {
  GraphConfigResponse,
  GraphExportResponse,
  GraphResponse,
  GraphStructuredSearchRequest,
  GraphStructuredSearchResponse,
  WorkflowGraphTemplateItem,
  WorkflowGraphTemplateListResponse,
  WorkflowGraphTemplateMutationResponse,
  WorkflowGraphTemplatePayload,
  WorkflowGraphTemplateUpdatePayload,
  WorkflowGraphTemplateVersionItem,
  WorkflowGraphTemplateVersionListResponse,
  WorkflowGraphTemplateVersionMutationResponse,
  WorkflowGraphTemplateVersionPayload,
  WorkflowTemplate,
  WorkflowTemplateMutationResponse,
  WorkflowTemplatePayload,
} from '../../types'

export async function listWorkflows() {
  const data = await get<string[] | { items?: string[] }>(endpoints.workflow.root)
  return asList<string>(data)
}

export async function getWorkflowTemplate(workflowName: string) {
  return get<WorkflowTemplate>(endpoints.workflow.template(workflowName))
}

export async function upsertWorkflowTemplate(workflowName: string, payload: WorkflowTemplatePayload) {
  return post<WorkflowTemplateMutationResponse>(endpoints.workflow.template(workflowName), payload)
}

export async function deleteWorkflowTemplate(workflowName: string, projectKey?: string) {
  const query = projectKey ? `?project_key=${encodeURIComponent(projectKey)}` : ''
  return del<WorkflowTemplateMutationResponse>(`${endpoints.workflow.template(workflowName)}${query}`)
}

export async function runWorkflow(workflowName: string, params: Record<string, unknown>) {
  return post<Record<string, unknown>>(endpoints.workflow.run(workflowName), {
    project_key: getProjectKey(),
    params,
  })
}

export type WorkflowGraphCompilePayload = {
  graph_id?: string
  dsl?: Record<string, unknown>
  template_id?: string
  version_id?: string
  base_version?: number
}

export type WorkflowGraphCompileResponse = {
  graph_id?: string
  version?: string
  checksum?: string
  topo_order?: string[]
  warnings?: unknown[]
}

export type WorkflowGraphRunPayload = {
  graph_id: string
  run_id?: string
  input?: Record<string, unknown>
  inputs?: Record<string, unknown>
}

export type WorkflowGraphRunResponse = {
  run_id?: string
  status?: string
  node_statuses?: Record<string, unknown>
  nodes?: Record<string, unknown>
  contract_version?: string
}

export type WorkflowGraphRunDetailResponse = {
  run_id?: string
  status?: string
  node_statuses?: Record<string, unknown>
  nodes?: Record<string, unknown>
  contract_version?: string
  [key: string]: unknown
}

export type WorkflowGraphRunEventsResponse = {
  items?: unknown[]
  total?: number
  contract_version?: string
  [key: string]: unknown
}

export async function compileWorkflowGraph(payload: WorkflowGraphCompilePayload) {
  return post<WorkflowGraphCompileResponse>(endpoints.workflowGraph.compile, payload)
}

export async function listWorkflowGraphTemplates() {
  const data = await get<WorkflowGraphTemplateItem[] | WorkflowGraphTemplateListResponse>(endpoints.workflowGraph.templates)
  if (Array.isArray(data)) return { items: data, total: data.length } satisfies WorkflowGraphTemplateListResponse
  return data || { items: [] }
}

export async function createWorkflowGraphTemplate(payload: WorkflowGraphTemplatePayload) {
  return post<WorkflowGraphTemplateMutationResponse>(endpoints.workflowGraph.templates, payload)
}

export async function getWorkflowGraphTemplate(templateId: string) {
  return get<WorkflowGraphTemplateMutationResponse>(endpoints.workflowGraph.templateById(templateId))
}

export async function updateWorkflowGraphTemplate(templateId: string, payload: WorkflowGraphTemplateUpdatePayload) {
  return patch<WorkflowGraphTemplateMutationResponse>(endpoints.workflowGraph.templateById(templateId), payload)
}

export async function deleteWorkflowGraphTemplate(templateId: string) {
  return del<WorkflowGraphTemplateMutationResponse>(endpoints.workflowGraph.templateById(templateId))
}

export async function listWorkflowGraphTemplateVersions(templateId: string) {
  const data = await get<WorkflowGraphTemplateVersionItem[] | WorkflowGraphTemplateVersionListResponse>(
    endpoints.workflowGraph.templateVersions(templateId),
  )
  if (Array.isArray(data)) return { items: data, total: data.length } satisfies WorkflowGraphTemplateVersionListResponse
  return data || { items: [] }
}

export async function createWorkflowGraphTemplateVersion(templateId: string, payload: WorkflowGraphTemplateVersionPayload) {
  return post<WorkflowGraphTemplateVersionMutationResponse>(endpoints.workflowGraph.templateVersions(templateId), payload)
}

export async function getWorkflowGraphTemplateVersion(templateId: string, versionId: string) {
  return get<WorkflowGraphTemplateVersionMutationResponse>(endpoints.workflowGraph.templateVersionById(templateId, versionId))
}

export async function activateWorkflowGraphTemplateVersion(templateId: string, versionId: string) {
  return post<WorkflowGraphTemplateVersionMutationResponse>(
    endpoints.workflowGraph.templateVersionActivate(templateId, versionId),
    null,
  )
}

export async function runWorkflowGraph(payload: WorkflowGraphRunPayload) {
  return post<WorkflowGraphRunResponse>(endpoints.workflowGraph.run, payload)
}

export async function getWorkflowGraphRun(runId: string) {
  return get<WorkflowGraphRunDetailResponse>(endpoints.workflowGraph.runById(runId))
}

export async function getWorkflowGraphRunEvents(runId: string) {
  return get<WorkflowGraphRunEventsResponse>(endpoints.workflowGraph.runEvents(runId))
}

export async function replayWorkflowGraphRun(runId: string) {
  return get<WorkflowGraphRunDetailResponse>(endpoints.workflowGraph.runReplay(runId))
}

export async function getCompiledWorkflowGraph(graphId: string) {
  return get<Record<string, unknown>>(endpoints.workflowGraph.compiledById(graphId))
}

export async function exportGraph(docIds: number[] | string) {
  const value = Array.isArray(docIds) ? docIds.join(',') : String(docIds || '')
  return get<GraphExportResponse>(`${endpoints.admin.exportGraph}?doc_ids=${encodeURIComponent(value)}`)
}

export type GraphKind = 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'

export async function getGraphConfig() {
  return get<GraphConfigResponse>(endpoints.graph.config)
}

const GRAPH_QUERY_LIMIT_MIN = 1
const GRAPH_QUERY_LIMIT_MAX = 2000
const GRAPH_QUERY_LIMIT_DEFAULT = 100
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export type GraphQueryParams = {
  start_date?: string
  end_date?: string
  state?: string
  policy_type?: string
  platform?: string
  topic?: string
  game?: string
  limit?: number
}

export type NormalizedGraphQueryParams = {
  start_date: string
  end_date: string
  state: string
  policy_type: string
  platform: string
  topic: string
  game: string
  limit: number
}

function normalizeGraphDate(value?: string) {
  const trimmed = String(value || '').trim()
  return ISO_DATE_RE.test(trimmed) ? trimmed : ''
}

function normalizeGraphFilter(value?: string) {
  return String(value || '').trim()
}

function clampGraphQueryLimit(value?: number) {
  if (!Number.isFinite(value)) return GRAPH_QUERY_LIMIT_DEFAULT
  const n = Math.trunc(Number(value))
  return Math.max(GRAPH_QUERY_LIMIT_MIN, Math.min(GRAPH_QUERY_LIMIT_MAX, n))
}

export function normalizeGraphQueryParams(params: GraphQueryParams = {}): NormalizedGraphQueryParams {
  return {
    start_date: normalizeGraphDate(params.start_date),
    end_date: normalizeGraphDate(params.end_date),
    state: normalizeGraphFilter(params.state),
    policy_type: normalizeGraphFilter(params.policy_type),
    platform: normalizeGraphFilter(params.platform),
    topic: normalizeGraphFilter(params.topic),
    game: normalizeGraphFilter(params.game),
    limit: clampGraphQueryLimit(params.limit),
  }
}

export async function getPolicyGraph(params: {
  start_date?: string
  end_date?: string
  state?: string
  policy_type?: string
  limit?: number
}) {
  const normalized = normalizeGraphQueryParams(params)
  const query = new URLSearchParams()
  if (normalized.start_date) query.set('start_date', normalized.start_date)
  if (normalized.end_date) query.set('end_date', normalized.end_date)
  if (normalized.state) query.set('state', normalized.state)
  if (normalized.policy_type) query.set('policy_type', normalized.policy_type)
  query.set('limit', String(normalized.limit))
  return get<GraphResponse>(`${endpoints.admin.policyGraph}?${query.toString()}`)
}

export async function getSocialGraph(params: {
  start_date?: string
  end_date?: string
  platform?: string
  topic?: string
  limit?: number
}) {
  const normalized = normalizeGraphQueryParams(params)
  const query = new URLSearchParams()
  if (normalized.start_date) query.set('start_date', normalized.start_date)
  if (normalized.end_date) query.set('end_date', normalized.end_date)
  if (normalized.platform) query.set('platform', normalized.platform)
  if (normalized.topic) query.set('topic', normalized.topic)
  query.set('limit', String(normalized.limit))
  return get<GraphResponse>(`${endpoints.admin.contentGraph}?${query.toString()}`)
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
  const normalized = normalizeGraphQueryParams(params)
  const query = new URLSearchParams()
  if (normalized.start_date) query.set('start_date', normalized.start_date)
  if (normalized.end_date) query.set('end_date', normalized.end_date)
  if (normalized.state) query.set('state', normalized.state)
  if (normalized.game) query.set('game', normalized.game)
  if (params.view) query.set('view', params.view)
  if (params.topic_scope) query.set('topic_scope', params.topic_scope)
  query.set('limit', String(normalized.limit))
  return get<GraphResponse>(`${endpoints.admin.marketGraph}?${query.toString()}`)
}

export async function submitGraphStructuredSearchTasks(payload: GraphStructuredSearchRequest) {
  return post<GraphStructuredSearchResponse>(endpoints.ingest.graphStructuredSearch, payload)
}
