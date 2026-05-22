import { endpoints } from '../endpoints'
import { asList, httpGet as get, httpPost as post } from '../client'

export type ClueChainStatus = 'draft' | 'running' | 'paused' | 'blocked' | 'closed' | string

export type ChainHopStatus =
  | 'planned'
  | 'running'
  | 'search_started'
  | 'evidence_collected'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'closed'
  | string

export type ChainEvidenceStatus = 'lead' | 'finding' | 'corroborated' | 'rejected' | string

export type ChainCandidateDecisionStatus =
  | 'pending'
  | 'promoted'
  | 'rejected'
  | 'merged'
  | 'paused'
  | 'blocked'
  | string

export type ChainDecisionAction = 'promote' | 'reject' | 'merge' | 'pause' | 'close' | string

export type ChainExpansionMode = 'graph_neighbors' | 'external_search' | 'source_library_search' | 'agent_subtask' | string

export type ChainCreatedBy = 'user' | 'agent' | 'workflow_graph' | string

export type ChainEvidenceSourceKind =
  | 'graph'
  | 'source_library'
  | 'local_index'
  | 'external_search'
  | 'url'
  | 'document'
  | 'agent'
  | string

export type ChainSourceRef = {
  source_item_key?: string | null
  channel_key?: string | null
  source_scope?: 'project' | 'shared' | 'effective' | string | null
  document_id?: string | number | null
  chunk_id?: string | number | null
  row_id?: string | number | null
  url?: string | null
  title?: string | null
  provider?: string | null
  rank?: number | null
  [key: string]: unknown
}

export type ChainBudget = {
  depth_remaining?: number
  max_results?: number
  max_hops?: number
  max_retries?: number
  timeout_ms?: number
  [key: string]: unknown
}

export type ChainOperatorPolicy = {
  require_approval_for_sensitive?: boolean
  public_sources_only?: boolean
  archive_before_pivot?: boolean
  allow_graph_mutation?: boolean
  [key: string]: unknown
}

export type ClueChain = {
  chain_id: string
  project_key?: string | null
  title: string
  status: ClueChainStatus
  objective?: string | null
  seed_node_ids?: string[]
  frontier_node_ids?: string[]
  max_depth?: number | null
  max_hops?: number | null
  confidence_threshold?: number | null
  created_by?: ChainCreatedBy | null
  provenance_policy?: string | null
  privacy_policy?: string | null
  policy_json?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
  closed_at?: string | null
  [key: string]: unknown
}

export type ChainHop = {
  hop_id: string
  chain_id: string
  depth?: number | null
  input_node_id?: string | null
  mode: ChainExpansionMode
  tool_name?: 'chain.expand' | string | null
  query_json?: Record<string, unknown> | null
  status: ChainHopStatus
  started_at?: string | null
  finished_at?: string | null
  evidence_ids?: string[]
  candidate_ids?: string[]
  budget?: ChainBudget | null
  provider_trace?: Record<string, unknown> | null
  blockers?: string[]
  [key: string]: unknown
}

export type ChainEvidence = {
  evidence_id: string
  chain_id: string
  hop_id?: string | null
  source_kind: ChainEvidenceSourceKind
  source_ref?: ChainSourceRef | null
  url?: string | null
  archive_url?: string | null
  hash?: string | null
  captured_at?: string | null
  status: ChainEvidenceStatus
  title?: string | null
  snippet?: string | null
  provider?: string | null
  query?: string | null
  rank?: number | null
  confidence?: number | null
  metadata?: Record<string, unknown> | null
  [key: string]: unknown
}

export type ChainCandidate = {
  candidate_id: string
  chain_id: string
  hop_id?: string | null
  entity_type: string
  value: string
  aliases?: string[]
  score?: number | null
  decision_status: ChainCandidateDecisionStatus
  confidence?: number | null
  novelty_score?: number | null
  evidence_ids?: string[]
  source_refs?: ChainSourceRef[]
  proposed_node?: Record<string, unknown> | null
  proposed_edges?: ChainEdge[]
  duplicate_of?: string | null
  blocker?: string | null
  [key: string]: unknown
}

export type ChainDecision = {
  decision_id: string
  chain_id: string
  candidate_id?: string | null
  actor?: 'user' | 'agent' | 'workflow' | string | null
  decision: ChainDecisionAction
  reason?: string | null
  created_at?: string | null
  target_node_id?: string | null
  target_edge_ids?: string[]
  merge_target_id?: string | null
  evidence_ids?: string[]
  metadata?: Record<string, unknown> | null
  [key: string]: unknown
}

export type ChainEdge = {
  edge_id?: string | null
  chain_id: string
  hop_id?: string | null
  from_node_id: string
  to_node_id: string
  relation: string
  evidence_ids?: string[]
  confidence?: number | null
  created_at?: string | null
  [key: string]: unknown
}

export type ChainFrontierItem = {
  node_id: string
  depth?: number | null
  priority?: number | null
  reason?: string | null
  source_candidate_id?: string | null
  evidence_gap?: number | null
  [key: string]: unknown
}

export type ClueChainCreatePayload = {
  title: string
  objective?: string | null
  seed_node_ids: string[]
  seed_nodes?: Array<Record<string, unknown>>
  max_depth?: number | null
  max_hops?: number | null
  confidence_threshold?: number | null
  created_by?: ChainCreatedBy
  provenance_policy?: string | null
  privacy_policy?: string | null
  policy_json?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
}

export type ClueChainListParams = {
  status?: ClueChainStatus | ClueChainStatus[]
  project_key?: string | null
  q?: string
  limit?: number
  offset?: number
}

export type ClueChainExpandPayload = {
  input_node_id?: string | null
  expansion_mode: ChainExpansionMode
  budget?: ChainBudget
  operator_policy?: ChainOperatorPolicy
  query?: string | null
  aliases?: string[]
  provider?: string | null
  source_item_keys?: string[]
  local_index_mode?: 'keyword' | 'vector' | 'hybrid' | string | null
  fixture_key?: string | null
  dry_run?: boolean
  replay?: boolean
  metadata?: Record<string, unknown> | null
}

export type ClueChainCandidateDecisionPayload = {
  decision: ChainDecisionAction
  actor?: 'user' | 'agent' | 'workflow' | string | null
  reason?: string | null
  merge_target_id?: string | null
  target_node_id?: string | null
  evidence_ids?: string[]
  metadata?: Record<string, unknown> | null
}

export type ClueChainClosePayload = {
  actor?: 'user' | 'agent' | 'workflow' | string | null
  reason?: string | null
  final_status?: 'closed' | 'blocked'
  blockers?: string[]
  summary?: string | null
  metadata?: Record<string, unknown> | null
}

export type ClueChainListResponse = {
  items: ClueChain[]
  total?: number
  status_counts?: Record<string, number>
  [key: string]: unknown
}

export type ClueChainDetailResponse = {
  chain: ClueChain
  hops?: ChainHop[]
  evidence?: ChainEvidence[]
  candidates?: ChainCandidate[]
  decisions?: ChainDecision[]
  edges?: ChainEdge[]
  frontier?: ChainFrontierItem[]
  blockers?: string[]
  [key: string]: unknown
}

export type ClueChainMutationResponse = ClueChainDetailResponse & {
  ok?: boolean
}

export type ClueChainExpandResponse = {
  chain: ClueChain
  hop?: ChainHop | null
  evidence?: ChainEvidence[]
  candidates?: ChainCandidate[]
  decisions?: ChainDecision[]
  edges?: ChainEdge[]
  events?: Array<Record<string, unknown>>
  blocked?: boolean
  blockers?: string[]
  [key: string]: unknown
}

export type ClueChainCandidateDecisionResponse = {
  chain?: ClueChain
  candidate?: ChainCandidate | null
  decision: ChainDecision
  promoted_node_id?: string | null
  promoted_edge_ids?: string[]
  merged_into?: string | null
  [key: string]: unknown
}

export type ClueChainCloseResponse = {
  chain: ClueChain
  final_status?: ClueChainStatus
  blockers?: string[]
  summary?: string | null
  [key: string]: unknown
}

function buildClueChainListQuery(params: ClueChainListParams = {}) {
  const query = new URLSearchParams()
  if (params.project_key) query.set('project_key', params.project_key)
  if (params.q?.trim()) query.set('q', params.q.trim())
  if (typeof params.limit === 'number') query.set('limit', String(params.limit))
  if (typeof params.offset === 'number') query.set('offset', String(params.offset))
  if (Array.isArray(params.status) && params.status.length) {
    query.set('status', params.status.join(','))
  } else if (typeof params.status === 'string' && params.status.trim()) {
    query.set('status', params.status.trim())
  }
  return query
}

export async function createClueChain(payload: ClueChainCreatePayload) {
  return post<ClueChainMutationResponse>(endpoints.clueChains.root, payload)
}

export async function listClueChains(params: ClueChainListParams = {}) {
  const query = buildClueChainListQuery(params)
  const data = await get<ClueChain[] | ClueChainListResponse>(
    query.toString() ? endpoints.clueChains.query(query) : endpoints.clueChains.root,
  )
  if (Array.isArray(data)) return { items: data, total: data.length } satisfies ClueChainListResponse
  return {
    ...data,
    items: asList<ClueChain>(data),
  } satisfies ClueChainListResponse
}

export async function getClueChain(chainId: string) {
  return get<ClueChainDetailResponse>(endpoints.clueChains.byId(chainId))
}

export async function expandClueChain(chainId: string, payload: ClueChainExpandPayload) {
  return post<ClueChainExpandResponse>(endpoints.clueChains.expand(chainId), payload)
}

export async function decideClueChainCandidate(
  chainId: string,
  candidateId: string,
  payload: ClueChainCandidateDecisionPayload,
) {
  return post<ClueChainCandidateDecisionResponse>(endpoints.clueChains.candidateDecision(chainId, candidateId), payload)
}

export async function closeClueChain(chainId: string, payload: ClueChainClosePayload = {}) {
  return post<ClueChainCloseResponse>(endpoints.clueChains.close(chainId), payload)
}
