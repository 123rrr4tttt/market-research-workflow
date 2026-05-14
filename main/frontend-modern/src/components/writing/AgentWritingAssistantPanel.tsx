export type WritingAgentPanelMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  pending?: boolean
}

export type WritingAgentToolAction = {
  id: string
  label: string
  description: string
  prompt: string
  disabled?: boolean
}

export type WritingAgentWorkbenchTool = {
  id: string
  label: string
  active?: boolean
  disabled?: boolean
  onClick: () => void
}

export type AgentWritingAssistantPanelProps = {
  messages: WritingAgentPanelMessage[]
  draft: string
  busy?: boolean
  streamStatus?: string
  sessionId?: string | null
  documentLabel: string
  selectionText?: string
  selectionLine?: number | null
  actions: WritingAgentToolAction[]
  workbenchTools: WritingAgentWorkbenchTool[]
  onDraftChange: (value: string) => void
  onSend: (message: string) => void
  onRunAction: (action: WritingAgentToolAction) => void
}

export default function AgentWritingAssistantPanel({
  messages,
  draft,
  busy = false,
  streamStatus = 'idle',
  sessionId,
  documentLabel,
  selectionText,
  selectionLine,
  actions,
  workbenchTools,
  onDraftChange,
  onSend,
  onRunAction,
}: AgentWritingAssistantPanelProps) {
  const canSend = draft.trim().length > 0 && !busy
  const sessionLabel = sessionId ? `session ${sessionId.slice(0, 8)}` : 'new session'

  return (
    <section className="panel writing-side-panel writing-agent-panel" data-testid="writing-agent-panel">
      <div className="panel-header">
        <div>
          <h2>Agent 写作协作</h2>
          <p className="text-muted writing-panel-subtitle">划词、定位、资料、引用和写回都从同一条 Agent 会话进入。</p>
        </div>
        {busy ? <span className="chip chip-warn">running</span> : <span className="chip chip-ok">ready</span>}
      </div>

      <div className="writing-agent-context-strip" data-testid="writing-agent-context-strip">
        <span className="chip chip-warn">{documentLabel}</span>
        {selectionText ? <span className="chip chip-ok">选区 {selectionText.length} 字</span> : <span className="chip">无选区</span>}
        {selectionLine ? <span className="chip">L{selectionLine}</span> : null}
        <span className="chip">{streamStatus}</span>
      </div>

      <div className="writing-agent-workbench-tools" data-testid="writing-agent-workbench-tools">
        {workbenchTools.map((tool) => (
          <button
            key={tool.id}
            type="button"
            className={tool.active ? 'button-primary' : 'button-secondary'}
            disabled={tool.disabled}
            onClick={tool.onClick}
          >
            {tool.label}
          </button>
        ))}
      </div>

      <details className="writing-agent-session-dropdown" data-testid="writing-agent-session-dropdown">
        <summary>
          <span>会话记录</span>
          <em>{sessionLabel} · {messages.length} 条</em>
        </summary>
        <div className="writing-agent-message-list">
          {messages.map((message) => (
            <article key={message.id} className={`writing-agent-message role-${message.role}${message.pending ? ' is-streaming' : ''}`}>
              <strong>{message.role === 'user' ? 'YOU' : message.role === 'system' ? 'SYSTEM' : 'AGENT'}</strong>
              <p>{message.content}</p>
            </article>
          ))}
          {!messages.length ? <div className="empty-cell">当前写作会话还没有消息。</div> : null}
        </div>
      </details>

      <div className="writing-agent-action-grid" data-testid="writing-agent-action-grid">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            className="button-secondary"
            disabled={busy || action.disabled}
            title={action.description}
            onClick={() => onRunAction(action)}
          >
            {action.label}
          </button>
        ))}
      </div>

      <div className="writing-agent-composer">
        <textarea
          data-testid="writing-agent-input"
          value={draft}
          placeholder="直接告诉 Agent 要如何改这段、补资料、续写或写回文档"
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
            event.preventDefault()
            if (canSend) onSend(draft)
          }}
        />
        <button
          type="button"
          className="button-primary"
          data-testid="writing-agent-send"
          disabled={!canSend}
          onClick={() => onSend(draft)}
        >
          发送
        </button>
      </div>
    </section>
  )
}
