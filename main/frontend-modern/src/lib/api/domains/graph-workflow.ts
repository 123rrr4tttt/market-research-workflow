import { endpoints } from '../endpoints'
import {
  asList,
  getProjectKey,
  httpDelete as del,
  httpGet as get,
  httpPost as post,
} from '../client'
import type {
  GraphConfigResponse,
  GraphExportResponse,
  GraphResponse,
  GraphStructuredSearchRequest,
  GraphStructuredSearchResponse,
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
  dsl: Record<string, unknown>
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
  return get<GraphResponse>(`${endpoints.admin.policyGraph}?${query.toString()}`)
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
  const query = new URLSearchParams()
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  if (params.state) query.set('state', params.state)
  if (params.game) query.set('game', params.game)
  if (params.view) query.set('view', params.view)
  if (params.topic_scope) query.set('topic_scope', params.topic_scope)
  query.set('limit', String(params.limit || 100))
  return get<GraphResponse>(`${endpoints.admin.marketGraph}?${query.toString()}`)
}

export async function submitGraphStructuredSearchTasks(payload: GraphStructuredSearchRequest) {
  return post<GraphStructuredSearchResponse>(endpoints.ingest.graphStructuredSearch, payload)
}
