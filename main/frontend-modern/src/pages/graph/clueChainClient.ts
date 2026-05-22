import { httpPost as post } from '../../lib/api/client'

export type ClueChainSeedNode = {
  node_id: string
  node_type: string
  label: string
  entry_id?: string
}

export type ClueChainSelectedEdge = {
  source_entry_id?: string
  target_entry_id?: string
  relation?: string
  label?: string
}

export type ClueChainEvidence = {
  evidence_id: string
  title: string
  source_type?: string
  url?: string
  summary?: string
  snippet?: string
  created_at?: string
  node_ids?: string[]
  candidate_ids?: string[]
  raw_ref?: Record<string, unknown>
}

export type ClueChainCandidateStatus = 'pending' | 'promoted' | 'rejected' | string

export type ClueChainCandidate = {
  candidate_id: string
  label: string
  node_type?: string
  status?: ClueChainCandidateStatus
  confidence?: number
  reason?: string
  evidence_ids?: string[]
  proposed_node?: Record<string, unknown>
  proposed_edge?: Record<string, unknown>
}

export type ClueChainFrontierItem = {
  node_id: string
  label: string
  node_type?: string
  reason?: string
  source?: string
}

export type ClueChainHop = {
  hop_id: string
  mode: 'source_library' | 'external_search' | string
  query?: string
  status?: string
  started_at?: string
  finished_at?: string
  evidence_ids?: string[]
  candidate_ids?: string[]
  blockers?: ClueChainBlocker[]
}

export type ClueChainBlocker = {
  blocker_id?: string
  severity?: 'info' | 'warning' | 'error' | string
  message: string
  source?: string
}

export type ClueChainDetail = {
  chain_id: string
  title?: string
  status?: string
  graph_type?: string
  project_key?: string
  seed_nodes?: ClueChainSeedNode[]
  frontier?: ClueChainFrontierItem[]
  hops?: ClueChainHop[]
  candidates?: ClueChainCandidate[]
  evidence?: ClueChainEvidence[]
  blockers?: ClueChainBlocker[]
  created_at?: string
  updated_at?: string
}

export type CreateClueChainPayload = {
  project_key: string
  graph_type: string
  title?: string
  seed_nodes: ClueChainSeedNode[]
  selected_edges?: ClueChainSelectedEdge[]
  graph_context?: Record<string, unknown>
}

export type ExpandClueChainPayload = {
  mode: 'source_library' | 'external_search'
  project_key: string
  graph_type: string
  frontier_node_ids?: string[]
}

export type DecideClueChainCandidatePayload = {
  decision: 'promote' | 'reject'
  reason?: string
  actor_id?: string
}

const CLUE_CHAINS_BASE = '/api/v1/clue-chains'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
}

function pickChainPayload(value: unknown): unknown {
  const record = asRecord(value)
  if (!record) return value
  return record.chain || record.item || record.detail || record.result || value
}

export function coerceClueChainDetail(value: unknown): ClueChainDetail {
  const raw = pickChainPayload(value)
  const record = asRecord(raw)
  if (!record) throw new Error('invalid_clue_chain_response')
  const chainId = String(record.chain_id || record.id || '').trim()
  if (!chainId) throw new Error('missing_clue_chain_id')
  return {
    ...record,
    chain_id: chainId,
    title: String(record.title || record.name || `Chain ${chainId}`),
    status: String(record.status || 'open'),
    seed_nodes: Array.isArray(record.seed_nodes) ? record.seed_nodes as ClueChainSeedNode[] : [],
    frontier: Array.isArray(record.frontier) ? record.frontier as ClueChainFrontierItem[] : [],
    hops: Array.isArray(record.hops) ? record.hops as ClueChainHop[] : [],
    candidates: Array.isArray(record.candidates) ? record.candidates as ClueChainCandidate[] : [],
    evidence: Array.isArray(record.evidence) ? record.evidence as ClueChainEvidence[] : [],
    blockers: Array.isArray(record.blockers) ? record.blockers as ClueChainBlocker[] : [],
  }
}

export async function createClueChain(payload: CreateClueChainPayload) {
  return coerceClueChainDetail(await post<unknown>(CLUE_CHAINS_BASE, payload))
}

export async function expandClueChain(chainId: string, payload: ExpandClueChainPayload) {
  return coerceClueChainDetail(
    await post<unknown>(`${CLUE_CHAINS_BASE}/${encodeURIComponent(chainId)}/expand`, payload),
  )
}

export async function decideClueChainCandidate(
  chainId: string,
  candidateId: string,
  payload: DecideClueChainCandidatePayload,
) {
  return coerceClueChainDetail(
    await post<unknown>(
      `${CLUE_CHAINS_BASE}/${encodeURIComponent(chainId)}/candidates/${encodeURIComponent(candidateId)}/decision`,
      payload,
    ),
  )
}
