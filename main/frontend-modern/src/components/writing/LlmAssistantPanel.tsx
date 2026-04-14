import type { WritingLlmActionHistoryItem, WritingLlmActionId } from '../../lib/api'

const defaultActions: Array<{ id: WritingLlmActionId; label: string }> = [
  { id: 'outline_generate', label: '生成提纲' },
  { id: 'section_expand', label: '扩写章节' },
  { id: 'selection_rewrite', label: '改写选区' },
  { id: 'evidence_summary', label: '证据总结' },
]

export type LlmAssistantPanelProps = {
  history: WritingLlmActionHistoryItem[]
  selectedJobId?: number | null
  detail?: WritingLlmActionHistoryItem | null
  busy?: boolean
  generatedContent?: string
  onRunAction?: (actionId: WritingLlmActionId) => void
  onSelectHistory?: (jobId: number) => void
}

export default function LlmAssistantPanel({
  history,
  selectedJobId,
  detail,
  busy = false,
  generatedContent,
  onRunAction,
  onSelectHistory,
}: LlmAssistantPanelProps) {
  return (
    <section className="panel writing-side-panel">
      <div className="panel-header">
        <div>
          <h2>LLM 助手</h2>
          <p className="text-muted writing-panel-subtitle">动作面板只暴露高频写作动作，不做泛聊天堆砌。</p>
        </div>
        {busy ? <span className="chip chip-warn">running</span> : <span className="chip chip-ok">ready</span>}
      </div>

      <div className="writing-action-grid">
        {defaultActions.map((action) => (
          <button key={action.id} type="button" className="button-secondary" onClick={() => onRunAction?.(action.id)}>
            {action.label}
          </button>
        ))}
      </div>

      {generatedContent ? <pre className="writing-llm-output">{generatedContent}</pre> : null}

      <div className="writing-list">
        {history.map((item) => (
          <button
            key={item.job_id}
            type="button"
            className={`writing-list-card${selectedJobId === item.job_id ? ' is-active' : ''}`}
            onClick={() => onSelectHistory?.(item.job_id)}
          >
            <div className="writing-list-card__header">
              <strong>{item.action_id || item.job_type}</strong>
              <span className={`chip ${item.status === 'completed' ? 'chip-ok' : 'chip-warn'}`}>{item.status}</span>
            </div>
            <p>{item.template_key || 'no-template'}</p>
            <div className="writing-list-card__footer">
              <span className="text-muted">{item.created_at || 'pending'}</span>
              <span className="writing-score">{item.duration_ms != null ? `${item.duration_ms}ms` : 'n/a'}</span>
            </div>
          </button>
        ))}
        {!history.length ? <div className="empty-cell">暂无动作历史</div> : null}
      </div>

      {detail ? (
        <article className="writing-preview-card">
          <div className="writing-preview-card__meta">
            <span className="chip chip-ok">job #{detail.job_id}</span>
            <span className={`chip ${detail.status === 'completed' ? 'chip-ok' : 'chip-warn'}`}>{detail.status}</span>
          </div>
          <strong>{detail.action_id || detail.job_type}</strong>
          <p>{detail.template_key || detail.template_version || 'no-template'}</p>
          <div className="writing-chip-wrap">
            {detail.trace_id ? <span className="chip">{detail.trace_id}</span> : null}
            {detail.created_at ? <span className="chip">{detail.created_at}</span> : null}
            {detail.duration_ms != null ? <span className="chip">{detail.duration_ms}ms</span> : null}
          </div>
        </article>
      ) : null}
    </section>
  )
}
