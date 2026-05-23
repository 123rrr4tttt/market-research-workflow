import {
  AlertTriangle,
  Check,
  Database,
  Eye,
  GitBranchPlus,
  LoaderCircle,
  Search,
  X,
} from 'lucide-react'
import type {
  ClueChainBlocker,
  ClueChainCandidate,
  ClueChainDetail,
  ClueChainEvidence,
  ClueChainHop,
} from './clueChainClient'
import './clue-chain.css'

type Props = {
  chain: ClueChainDetail
  busy: boolean
  status: string
  selectedEvidenceId: string | null
  onClose: () => void
  onRunExpand: (mode: 'source_library' | 'external_search') => void
  onReviewCandidate: (candidateId: string, decision: 'promote' | 'reject') => void
  onOpenEvidence: (evidenceId: string) => void
}

function compactDate(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function evidenceById(chain: ClueChainDetail) {
  const map = new Map<string, ClueChainEvidence>()
  ;(chain.evidence || []).forEach((item) => {
    map.set(item.evidence_id, item)
  })
  return map
}

function candidateStatusLabel(candidate: ClueChainCandidate) {
  const status = String(candidate.status || 'pending')
  if (status === 'promoted') return '已提升'
  if (status === 'rejected') return '已拒绝'
  return '待审核'
}

function modeLabel(mode: string) {
  if (mode === 'source_library') return 'Source Library'
  if (mode === 'external_search') return 'External Search'
  return mode || 'unknown'
}

function EvidenceButtons({
  evidenceIds,
  evidenceMap,
  onOpenEvidence,
}: {
  evidenceIds: string[]
  evidenceMap: Map<string, ClueChainEvidence>
  onOpenEvidence: (evidenceId: string) => void
}) {
  if (!evidenceIds.length) return <span className="clue-chain-muted">无证据</span>
  return (
    <div className="clue-chain-evidence-links">
      {evidenceIds.map((evidenceId) => {
        const evidence = evidenceMap.get(evidenceId)
        return (
          <button
            key={evidenceId}
            type="button"
            className="clue-chain-icon-btn"
            onClick={() => onOpenEvidence(evidenceId)}
            title={evidence?.title || evidenceId}
            data-testid={`clue-chain-evidence-${evidenceId}`}
          >
            <Eye size={13} />
            <span>{evidence?.title || evidenceId}</span>
          </button>
        )
      })}
    </div>
  )
}

function HopRow({
  hop,
  evidenceMap,
  onOpenEvidence,
}: {
  hop: ClueChainHop
  evidenceMap: Map<string, ClueChainEvidence>
  onOpenEvidence: (evidenceId: string) => void
}) {
  const blockerCount = (hop.blockers || []).length
  return (
    <article className="clue-chain-hop">
      <div className="clue-chain-row-head">
        <strong>{modeLabel(hop.mode)}</strong>
        <span>{hop.status || 'queued'}</span>
      </div>
      <p>{hop.query || '未记录 query'}</p>
      <div className="clue-chain-meta">
        <span>{hop.candidate_ids?.length || 0} candidates</span>
        <span>{hop.evidence_ids?.length || 0} evidence</span>
        {blockerCount ? <span>{blockerCount} blockers</span> : null}
        {hop.finished_at ? <span>{compactDate(hop.finished_at)}</span> : null}
      </div>
      <EvidenceButtons
        evidenceIds={hop.evidence_ids || []}
        evidenceMap={evidenceMap}
        onOpenEvidence={onOpenEvidence}
      />
    </article>
  )
}

function BlockerList({ blockers }: { blockers: ClueChainBlocker[] }) {
  if (!blockers.length) {
    return <div className="clue-chain-empty">当前没有 blocker</div>
  }
  return (
    <div className="clue-chain-blockers">
      {blockers.map((blocker, index) => (
        <div key={blocker.blocker_id || `${blocker.message}-${index}`} className="clue-chain-blocker">
          <AlertTriangle size={14} />
          <div>
            <strong>{blocker.severity || 'warning'}</strong>
            <span>{blocker.message}</span>
            {blocker.source ? <small>{blocker.source}</small> : null}
          </div>
        </div>
      ))}
    </div>
  )
}

export function ClueChainInspector({
  chain,
  busy,
  status,
  selectedEvidenceId,
  onClose,
  onRunExpand,
  onReviewCandidate,
  onOpenEvidence,
}: Props) {
  const evidenceMap = evidenceById(chain)
  const selectedEvidence = selectedEvidenceId ? evidenceMap.get(selectedEvidenceId) || null : null
  const pendingCandidates = (chain.candidates || []).filter((candidate) => String(candidate.status || 'pending') === 'pending')
  const chainTitle = chain.title || chain.chain_id

  return (
    <aside className="clue-chain-panel" data-testid="clue-chain-inspector">
      <div className="clue-chain-head">
        <div>
          <span>Clue Chain</span>
          <strong>{chainTitle}</strong>
          <small>{chain.chain_id}</small>
        </div>
        <button type="button" className="clue-chain-close" onClick={onClose} aria-label="关闭 Clue Chain">
          <X size={16} />
        </button>
      </div>

      <div className="clue-chain-summary">
        <div><span>Frontier</span><strong>{chain.frontier?.length || 0}</strong></div>
        <div><span>Hops</span><strong>{chain.hops?.length || 0}</strong></div>
        <div><span>Queue</span><strong>{pendingCandidates.length}</strong></div>
        <div><span>Blockers</span><strong>{chain.blockers?.length || 0}</strong></div>
      </div>

      <div className="clue-chain-actions">
        <button type="button" onClick={() => onRunExpand('source_library')} disabled={busy}>
          {busy ? <LoaderCircle size={14} className="spinning" /> : <Database size={14} />}
          <span>Source Hop</span>
        </button>
        <button type="button" onClick={() => onRunExpand('external_search')} disabled={busy}>
          {busy ? <LoaderCircle size={14} className="spinning" /> : <Search size={14} />}
          <span>Search Hop</span>
        </button>
      </div>

      <div className="clue-chain-status" data-testid="clue-chain-status">
        {busy ? 'Clue Chain API 调用中...' : (status || `状态：${chain.status || 'open'}`)}
      </div>

      <section className="clue-chain-section">
        <div className="clue-chain-section-title">
          <GitBranchPlus size={14} />
          <strong>Frontier</strong>
        </div>
        {chain.frontier?.length ? (
          <div className="clue-chain-frontier">
            {chain.frontier.map((item) => (
              <div key={`${item.node_type || 'node'}-${item.node_id}`} className="clue-chain-frontier-item">
                <strong>{item.label || item.node_id}</strong>
                <span>{item.node_type || 'node'} · {item.reason || item.source || 'ready'}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="clue-chain-empty">没有待展开 frontier</div>
        )}
      </section>

      <section className="clue-chain-section">
        <div className="clue-chain-section-title">
          <Database size={14} />
          <strong>Hops</strong>
        </div>
        {chain.hops?.length ? (
          <div className="clue-chain-hop-list" data-testid="clue-chain-hop-list">
            {chain.hops.map((hop) => (
              <HopRow key={hop.hop_id} hop={hop} evidenceMap={evidenceMap} onOpenEvidence={onOpenEvidence} />
            ))}
          </div>
        ) : (
          <div className="clue-chain-empty">尚未运行 hop</div>
        )}
      </section>

      <section className="clue-chain-section">
        <div className="clue-chain-section-title">
          <Check size={14} />
          <strong>Candidate Review</strong>
        </div>
        {chain.candidates?.length ? (
          <div className="clue-chain-candidates" data-testid="clue-chain-candidate-queue">
            {chain.candidates.map((candidate) => {
              const isPending = String(candidate.status || 'pending') === 'pending'
              return (
                <article key={candidate.candidate_id} className="clue-chain-candidate">
                  <div className="clue-chain-row-head">
                    <strong>{candidate.label}</strong>
                    <span>{candidateStatusLabel(candidate)}</span>
                  </div>
                  <p>{candidate.reason || candidate.node_type || '未记录说明'}</p>
                  <div className="clue-chain-meta">
                    <span>{candidate.node_type || 'node'}</span>
                    {typeof candidate.confidence === 'number' ? <span>{Math.round(candidate.confidence * 100)}%</span> : null}
                  </div>
                  <EvidenceButtons
                    evidenceIds={candidate.evidence_ids || []}
                    evidenceMap={evidenceMap}
                    onOpenEvidence={onOpenEvidence}
                  />
                  <div className="clue-chain-candidate-actions">
                    <button
                      type="button"
                      onClick={() => onReviewCandidate(candidate.candidate_id, 'promote')}
                      disabled={busy || !isPending}
                      data-testid={`clue-chain-promote-${candidate.candidate_id}`}
                    >
                      <Check size={13} />
                      <span>Promote</span>
                    </button>
                    <button
                      type="button"
                      className="is-danger"
                      onClick={() => onReviewCandidate(candidate.candidate_id, 'reject')}
                      disabled={busy || !isPending}
                      data-testid={`clue-chain-reject-${candidate.candidate_id}`}
                    >
                      <X size={13} />
                      <span>Reject</span>
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <div className="clue-chain-empty">没有候选项</div>
        )}
      </section>

      <section className="clue-chain-section">
        <div className="clue-chain-section-title">
          <AlertTriangle size={14} />
          <strong>Blockers</strong>
        </div>
        <BlockerList blockers={chain.blockers || []} />
      </section>

      {selectedEvidence ? (
        <section className="clue-chain-evidence-drawer" data-testid="clue-chain-evidence-drawer">
          <div className="clue-chain-row-head">
            <strong>{selectedEvidence.title}</strong>
            <span>{selectedEvidence.source_type || 'evidence'}</span>
          </div>
          {selectedEvidence.url ? (
            <a href={selectedEvidence.url} target="_blank" rel="noreferrer">
              {selectedEvidence.url}
            </a>
          ) : null}
          <p>{selectedEvidence.summary || selectedEvidence.snippet || '未记录摘要'}</p>
          <div className="clue-chain-meta">
            {selectedEvidence.created_at ? <span>{compactDate(selectedEvidence.created_at)}</span> : null}
            {selectedEvidence.node_ids?.length ? <span>{selectedEvidence.node_ids.length} nodes</span> : null}
            {selectedEvidence.candidate_ids?.length ? <span>{selectedEvidence.candidate_ids.length} candidates</span> : null}
          </div>
        </section>
      ) : null}
    </aside>
  )
}
