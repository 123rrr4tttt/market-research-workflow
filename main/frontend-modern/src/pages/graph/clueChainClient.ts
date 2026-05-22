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

export type ClueChainCandidateStatus = 'pending' | 'accepted' | 'promoted' | 'rejected' | 'merged' | string

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
  mode: 'source_library' | 'source_library_search' | 'external_search' | string
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

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : []
}

function normalizeMode(mode: unknown) {
  const text = String(mode || '')
  if (text === 'source_library_search') return 'source_library'
  return text
}

function normalizeCandidateStatus(status: unknown) {
  const text = String(status || 'pending')
  if (text === 'accepted') return 'promoted'
  return text
}

function chainRecordFrom(value: unknown) {
  const record = asRecord(value)
  if (!record) throw new Error('invalid_clue_chain_response')
  const chain = asRecord(record.chain) || record
  const chainId = String(chain.chain_id || chain.id || '').trim()
  if (!chainId) throw new Error('missing_clue_chain_id')
  return { record, chain, chainId }
}

function seedNodesFrom(chain: Record<string, unknown>) {
  const seedNodes = asArray<ClueChainSeedNode>(chain.seed_nodes)
  if (seedNodes.length) return seedNodes
  return asArray<string>(chain.root_node_ids).map((nodeId) => ({
    node_id: String(nodeId),
    node_type: 'node',
    label: String(nodeId),
    entry_id: String(nodeId),
  }))
}

function frontierFrom(chain: Record<string, unknown>) {
  const frontier = asArray<ClueChainFrontierItem>(chain.frontier)
  if (frontier.length) return frontier
  return asArray<string>(chain.frontier_node_ids).map((nodeId) => ({
    node_id: String(nodeId),
    node_type: 'node',
    label: String(nodeId),
    reason: 'frontier',
  }))
}

function hopsFrom(record: Record<string, unknown>) {
  const items = asArray<ClueChainHop>(record.hops)
  const single = asRecord(record.hop)
  const raw = items.length ? items : single ? [single as ClueChainHop] : []
  return raw.map((hop) => ({
    ...hop,
    mode: normalizeMode(hop.mode),
    started_at: hop.started_at || (hop as Record<string, unknown>).created_at as string | undefined,
    finished_at: hop.finished_at || (hop as Record<string, unknown>).completed_at as string | undefined,
  }))
}

function evidenceFrom(record: Record<string, unknown>) {
  const items = asArray<ClueChainEvidence>(record.evidence)
  const single = asRecord(record.evidence)
  const raw = items.length ? items : single ? [single as ClueChainEvidence] : []
  return raw.map((item) => ({
    ...item,
    title: String(item.title || item.evidence_id),
    summary: item.summary || item.snippet,
  }))
}

function candidatesFrom(record: Record<string, unknown>) {
  const items = asArray<ClueChainCandidate>(record.candidates)
  const single = asRecord(record.candidate)
  const raw = items.length ? items : single ? [single as ClueChainCandidate] : []
  return raw.map((item) => ({
    ...item,
    status: normalizeCandidateStatus(item.status),
    node_type: item.node_type || String((item as Record<string, unknown>).candidate_type || ''),
    reason: item.reason || String(asRecord((item as Record<string, unknown>).metadata)?.canonical_key || ''),
  }))
}

export function coerceClueChainDetail(value: unknown): ClueChainDetail {
  const { record, chain, chainId } = chainRecordFrom(value)
  const detailRecord = asRecord(record.chain) ? { ...chain, ...record } : { ...record, chain }
  const graphType = String(chain.graph_type || chain.graph_id || 'graph')
  return {
    chain_id: chainId,
    title: String(chain.title || chain.name || `Chain ${chainId}`),
    status: String(chain.status || 'open'),
    graph_type: graphType,
    project_key: String(chain.project_key || ''),
    seed_nodes: seedNodesFrom(chain),
    frontier: frontierFrom(chain),
    hops: hopsFrom(detailRecord),
    candidates: candidatesFrom(detailRecord),
    evidence: evidenceFrom(detailRecord),
    blockers: asArray<ClueChainBlocker>(record.blockers).length
      ? asArray<ClueChainBlocker>(record.blockers)
      : asArray<ClueChainBlocker>(chain.blockers),
    created_at: String(chain.created_at || ''),
    updated_at: String(chain.updated_at || ''),
  }
}

export async function createClueChain(payload: CreateClueChainPayload) {
  return coerceClueChainDetail(
    await post<unknown>(CLUE_CHAINS_BASE, {
      project_key: payload.project_key,
      graph_id: payload.graph_type,
      title: payload.title || `Clue Chain ${payload.seed_nodes[0]?.label || ''}`.trim(),
      question: payload.graph_context?.question || payload.title || null,
      root_node_ids: payload.seed_nodes.map((node) => node.node_id).filter(Boolean),
      metadata: {
        graph_type: payload.graph_type,
        seed_nodes: payload.seed_nodes,
        selected_edges: payload.selected_edges || [],
        graph_context: payload.graph_context || {},
        created_by: 'graphpage.clue-chain-ui',
      },
    }),
  )
}

export async function expandClueChain(chainId: string, payload: ExpandClueChainPayload) {
  return coerceClueChainDetail(
    await post<unknown>(`${CLUE_CHAINS_BASE}/${encodeURIComponent(chainId)}/expand`, {
      mode: payload.mode === 'source_library' ? 'source_library_search' : 'external_search',
      frontier_node_ids: payload.frontier_node_ids || [],
      limit: 5,
      provider_options: {
        graph_type: payload.graph_type,
        project_key: payload.project_key,
        requested_by: 'graphpage.clue-chain-ui',
      },
    }),
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
      {
        action: payload.decision,
        reason: payload.reason,
        decided_by: payload.actor_id || 'graphpage.clue-chain-ui',
      },
    ),
  )
}
