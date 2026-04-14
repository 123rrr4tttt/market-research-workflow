import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle, RefreshCw, SendHorizonal, Sparkles } from 'lucide-react'
import {
  getAgentSession,
  listAgentSessionArtifacts,
  listAgentSessionEvents,
  listAgentSessionTasks,
  runAgentBatchNlCommand,
} from '../lib/api'
import './agent-chat.css'

type AgentChatPageProps = {
  projectKey: string
}

type ChatRole = 'system' | 'user' | 'assistant'
type StageStatus = 'pending' | 'running' | 'done'

type StageItem = {
  key: string
  label: string
  status: StageStatus
}

type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  ts: string
  stages?: StageItem[]
  meta?: string[]
}

type ChatSession = {
  id: string
  title: string
  updatedAt: string
  backendSessionId?: string | null
  backendRootTaskId?: string | null
  backendCurrentPhase?: string | null
  backendCompatMode?: boolean | null
  backendProjectionVersion?: string | null
}

type StoredAgentChatState = {
  activeSessionId: string
  sessions: ChatSession[]
  sessionHistories: Record<string, ChatMessage[]>
  draftBySession?: Record<string, string>
}

const DEFAULT_QUICK_COMMANDS = [
  '分析最近 14 天 California gas price 的主驱动因素，并给出证据链',
  '针对 New York power market，生成一个可执行的采集批处理命令',
  '总结当前项目 agent runtime 的风险点，并列出最小回归验证步骤',
]

const STAGE_LABELS = [
  { key: 'plan', label: 'Plan' },
  { key: 'dispatch', label: 'Dispatch' },
  { key: 'execute', label: 'Execute' },
  { key: 'observe_adjust', label: 'Observe/Adjust' },
  { key: 'report', label: 'Report' },
]
const AGENT_CHAT_STORAGE_PREFIX = 'agent-chat-state-v1'
const DEFAULT_SESSIONS: ChatSession[] = [
  { id: 's1', title: 'Agent Runtime 讨论', updatedAt: '今天' },
  { id: 's2', title: 'Market Batch Search', updatedAt: '昨天' },
  { id: 's3', title: '风险审查与回放', updatedAt: '3 天前' },
]

function buildBaseStages(): StageItem[] {
  return STAGE_LABELS.map((stage, idx) => ({
    key: stage.key,
    label: stage.label,
    status: idx === 0 ? 'running' : 'pending',
  }))
}

function nowLabel() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function buildSystemMessage(projectKey: string, hint?: string): ChatMessage {
  return {
    id: `sys-${Date.now()}`,
    role: 'system',
    ts: nowLabel(),
    content: hint || 'Agent 对话已就绪。建议先输入目标和约束，例如时间窗口、地区、输出格式。',
    meta: [`project: ${projectKey}`],
  }
}

function buildSeedHistories(projectKey: string): Record<string, ChatMessage[]> {
  return {
    s1: [buildSystemMessage(projectKey)],
    s2: [
      buildSystemMessage(projectKey, '这是一个市场批量检索会话。可直接输入地区 + 品类 + 时间窗。'),
      {
        id: 's2-u1',
        role: 'user',
        ts: '19:08:12',
        content: '给我一个 Texas power market 的 7 天批量检索命令',
      },
      {
        id: 's2-a1',
        role: 'assistant',
        ts: '19:08:15',
        content: '建议命令: 收集 Texas 电力市场近 7 天价格、负荷、政策变更，并输出可重放任务批次。',
        stages: STAGE_LABELS.map((stage) => ({ ...stage, status: 'done' })),
        meta: ['backend: /agent-batch/nl-command/direct', 'status: accepted'],
      },
    ],
    s3: [
      buildSystemMessage(projectKey, '这是一个风险审查会话。可要求输出风险级别和最小回归验证步骤。'),
      {
        id: 's3-u1',
        role: 'user',
        ts: '19:09:04',
        content: '检查 agent loop 的高风险点，并给最小验证步骤',
      },
      {
        id: 's3-a1',
        role: 'assistant',
        ts: '19:09:07',
        content: '高风险点: approval binding 漏检、loop 检测缺失、fallback 不可观测。建议先跑 schema + replay + rollback drill 三个最小门禁。',
        stages: STAGE_LABELS.map((stage) => ({ ...stage, status: 'done' })),
        meta: ['risk: high', 'validation: schema/replay/rollback'],
      },
    ],
  }
}

function readStoredState(storageKey: string): StoredAgentChatState | null {
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredAgentChatState
    if (!parsed || typeof parsed !== 'object') return null
    if (!Array.isArray(parsed.sessions) || !parsed.sessionHistories || typeof parsed.sessionHistories !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

function mergeSessionsWithSeed(
  storedSessions?: ChatSession[] | null,
  sessionHistories?: Record<string, ChatMessage[]> | null,
): ChatSession[] {
  const sessionsById = new Map<string, ChatSession>()
  for (const session of storedSessions || []) {
    if (!session?.id) continue
    sessionsById.set(session.id, session)
  }
  for (const session of DEFAULT_SESSIONS) {
    if (!sessionsById.has(session.id)) {
      sessionsById.set(session.id, session)
    }
  }
  for (const sessionId of Object.keys(sessionHistories || {})) {
    if (!sessionsById.has(sessionId)) {
      sessionsById.set(sessionId, {
        id: sessionId,
        title: 'Recovered Session',
        updatedAt: '刚刚',
      })
    }
  }
  return Array.from(sessionsById.values())
}

function mergeHistoriesWithSeed(projectKey: string, fromStorage?: Record<string, ChatMessage[]> | null): Record<string, ChatMessage[]> {
  const seed = buildSeedHistories(projectKey)
  const baseSessions = Array.from(new Set([...DEFAULT_SESSIONS.map((session) => session.id), ...Object.keys(fromStorage || {})]))
  const mergedEntries = baseSessions.map((sessionId) => {
    const cached = fromStorage?.[sessionId]
    if (Array.isArray(cached) && cached.length > 0) return [sessionId, cached] as const
    return [sessionId, seed[sessionId] || [buildSystemMessage(projectKey)]] as const
  })
  return Object.fromEntries(mergedEntries)
}

function toCompactJson(value: unknown) {
  if (!value || typeof value !== 'object') return ''
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return ''
  }
}

function buildFallbackAssistant(command: string): { content: string; stages: StageItem[]; meta: string[] } {
  const normalized = command.toLowerCase()
  const focus =
    normalized.includes('采集') || normalized.includes('ingest')
      ? '采集链路'
      : normalized.includes('风险') || normalized.includes('risk')
        ? '治理与风险'
        : normalized.includes('graph') || normalized.includes('图谱')
          ? '图谱检索'
          : '通用分析'
  return {
    content: `已接收你的指令。我会按「Plan -> Dispatch -> Execute -> Observe/Adjust -> Report」执行，并优先使用 skill-first 路径。当前判定焦点: ${focus}。`,
    stages: STAGE_LABELS.map((stage) => ({ ...stage, status: 'done' })),
    meta: ['backend: fallback-local', 'reason: nl-command unavailable'],
  }
}

function buildSessionId() {
  return `s-${Date.now().toString(36)}`
}

function buildSessionTitle(command?: string) {
  const normalized = String(command || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return 'New Agent Session'
  return normalized.slice(0, 28)
}

function safeDisplay(value?: string | number | boolean | null) {
  if (value === null || value === undefined || value === '') return '-'
  return typeof value === 'boolean' ? (value ? 'yes' : 'no') : String(value)
}

function safeCount(value: unknown) {
  return Array.isArray(value) ? value.length : 0
}

function splitMessageContent(content: string) {
  const [summary, ...rest] = content.split('\n\n')
  const detail = rest.join('\n\n').trim()
  if (detail.startsWith('parsed:\n')) {
    return {
      summary: summary.trim(),
      detailLabel: 'parsed',
      detailValue: detail.replace(/^parsed:\n/, '').trim(),
    }
  }
  return {
    summary: content.trim(),
    detailLabel: '',
    detailValue: '',
  }
}

export default function AgentChatPage({ projectKey }: AgentChatPageProps) {
  const storageKey = `${AGENT_CHAT_STORAGE_PREFIX}:${projectKey || 'default'}`
  const stored = readStoredState(storageKey)
  const initialSessions = mergeSessionsWithSeed(stored?.sessions, stored?.sessionHistories)
  const initialHistories = mergeHistoriesWithSeed(projectKey, stored?.sessionHistories)

  const [sessionFilter, setSessionFilter] = useState('')
  const [activeSessionId, setActiveSessionId] = useState(stored?.activeSessionId || initialSessions[0]?.id || 's1')
  const [sessions, setSessions] = useState<ChatSession[]>(initialSessions)
  const [sessionHistories, setSessionHistories] = useState<Record<string, ChatMessage[]>>(initialHistories)
  const [draftBySession, setDraftBySession] = useState<Record<string, string>>(stored?.draftBySession || {})
  const listRef = useRef<HTMLDivElement | null>(null)

  const resolvedActiveSessionId = useMemo(
    () => (sessions.some((session) => session.id === activeSessionId) ? activeSessionId : sessions[0]?.id || activeSessionId),
    [activeSessionId, sessions],
  )
  const activeMessages = useMemo(() => sessionHistories[resolvedActiveSessionId] || [], [resolvedActiveSessionId, sessionHistories])
  const sessionStats = useMemo(() => {
    const entries = Object.entries(sessionHistories).map(([sessionId, msgs]) => {
      const last = msgs[msgs.length - 1]
      const preview = last?.content?.replace(/\s+/g, ' ').slice(0, 44) || '暂无消息'
      return {
        sessionId,
        count: msgs.length,
        preview,
      }
    })
    return Object.fromEntries(entries.map((item) => [item.sessionId, item])) as Record<string, { count: number; preview: string }>
  }, [sessionHistories])
  const activeSession = useMemo(
    () => sessions.find((session) => session.id === resolvedActiveSessionId) || sessions[0],
    [sessions, resolvedActiveSessionId],
  )
  const activeBackendSessionId = activeSession?.backendSessionId || null
  const backendSessionQuery = useQuery({
    queryKey: ['agent-session', projectKey, activeBackendSessionId],
    queryFn: () => getAgentSession(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    retry: false,
  })
  const backendTaskQuery = useQuery({
    queryKey: ['agent-session-tasks', projectKey, activeBackendSessionId],
    queryFn: () => listAgentSessionTasks(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    retry: false,
  })
  const backendEventQuery = useQuery({
    queryKey: ['agent-session-events', projectKey, activeBackendSessionId],
    queryFn: () => listAgentSessionEvents(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    retry: false,
  })
  const backendArtifactQuery = useQuery({
    queryKey: ['agent-session-artifacts', projectKey, activeBackendSessionId],
    queryFn: () => listAgentSessionArtifacts(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    retry: false,
  })
  const filteredSessions = useMemo(() => {
    const query = sessionFilter.trim().toLowerCase()
    if (!query) return sessions
    return sessions.filter((session) => {
      const stats = sessionStats[session.id]
      return (
        session.title.toLowerCase().includes(query)
        || String(stats?.preview || '').toLowerCase().includes(query)
      )
    })
  }, [sessionFilter, sessions, sessionStats])
  const messageCountLabel = useMemo(() => `${activeMessages.length} 条消息`, [activeMessages.length])
  const currentDraft = draftBySession[resolvedActiveSessionId] || ''
  const nlCommandMutation = useMutation({
    mutationFn: (command: string) =>
      runAgentBatchNlCommand({
        command,
        project_key: projectKey || null,
      }),
  })

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [activeMessages, nlCommandMutation.isPending, resolvedActiveSessionId])

  useEffect(() => {
    const payload: StoredAgentChatState = {
      activeSessionId,
      sessions,
      sessionHistories,
      draftBySession,
    }
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(payload))
    } catch {
      // Ignore storage failures so the chat surface remains usable in restricted environments.
    }
  }, [activeSessionId, sessions, sessionHistories, draftBySession, storageKey])

  const createSession = (seedCommand?: string) => {
    const nextId = buildSessionId()
    const title = buildSessionTitle(seedCommand)
    const nextSession: ChatSession = {
      id: nextId,
      title,
      updatedAt: '刚刚',
    }
    setSessions((prev) => [nextSession, ...prev])
    setSessionHistories((prev) => ({
      ...prev,
      [nextId]: [buildSystemMessage(projectKey, seedCommand ? `新会话已创建。可继续围绕这条任务展开：${seedCommand}` : undefined)],
    }))
    setDraftBySession((prev) => ({
      ...prev,
      [nextId]: seedCommand || '',
    }))
    setActiveSessionId(nextId)
  }

  const sendMessage = async (raw: string) => {
    const command = raw.trim()
    if (!command || nlCommandMutation.isPending) return
    const targetSessionId = resolvedActiveSessionId

    setSessionHistories((prev) => ({
      ...prev,
      [targetSessionId]: [
        ...(prev[targetSessionId] || []),
        {
          id: `u-${Date.now()}`,
          role: 'user',
          content: command,
          ts: nowLabel(),
        },
        {
          id: `a-loading-${Date.now()}`,
          role: 'assistant',
          content: '正在解析指令并构建执行计划...',
          ts: nowLabel(),
          stages: buildBaseStages(),
        },
      ],
    }))
    setSessions((prev) => prev.map((session) => (session.id === targetSessionId ? { ...session, updatedAt: '刚刚' } : session)))
    setDraftBySession((prev) => ({
      ...prev,
      [targetSessionId]: '',
    }))

    try {
      const result = await nlCommandMutation.mutateAsync(command)
      const parsed = result?.parsed || null
      const submit = result?.submit || null
      const backendSessionId = String(result?.session_id || result?.session?.session_id || '')
      const backendRootTaskId = String(result?.root_task_id || result?.session?.root_task_id || '')
      const backendCurrentPhase = String(result?.current_phase || result?.session?.current_phase || '')
      const backendCompatMode = typeof result?.compat_mode === 'boolean' ? result.compat_mode : result?.session?.compat_mode
      const backendProjectionVersion = String(result?.compat_projection_version || result?.session?.compat_projection_version || '')
      const meta: string[] = ['backend: /agent-batch/nl-command/direct']
      if (submit?.job_id) meta.push(`job_id: ${submit.job_id}`)
      if (submit?.status) meta.push(`status: ${submit.status}`)
      if (backendSessionId) meta.push(`session_id: ${backendSessionId}`)
      if (backendCurrentPhase) meta.push(`phase: ${backendCurrentPhase}`)
      if (typeof submit?.accepted_count === 'number') meta.push(`accepted: ${submit.accepted_count}`)
      if (typeof submit?.rejected_count === 'number') meta.push(`rejected: ${submit.rejected_count}`)

      const parsedJson = toCompactJson(parsed)
      const assistantContent = submit
        ? `指令已解析并提交批处理任务。\n\n${parsedJson ? `parsed:\n${parsedJson}` : 'parsed: (empty)'}`.trim()
        : `指令已解析，当前未触发提交动作。\n\n${parsedJson ? `parsed:\n${parsedJson}` : 'parsed: (empty)'}`.trim()

      setSessionHistories((prev) => {
        const sessionMessages = prev[targetSessionId] || []
        const withoutLoading = sessionMessages.filter((msg) => !msg.id.startsWith('a-loading-'))
        return {
          ...prev,
          [targetSessionId]: [
            ...withoutLoading,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              content: assistantContent,
              ts: nowLabel(),
              stages: STAGE_LABELS.map((stage) => ({ ...stage, status: 'done' })),
              meta,
            },
          ],
        }
      })
      if (backendSessionId || backendRootTaskId || backendCurrentPhase || backendProjectionVersion || typeof backendCompatMode === 'boolean') {
        setSessions((prev) =>
          prev.map((session) =>
            session.id === targetSessionId
              ? {
                  ...session,
                  backendSessionId: backendSessionId || session.backendSessionId,
                  backendRootTaskId: backendRootTaskId || session.backendRootTaskId,
                  backendCurrentPhase: backendCurrentPhase || session.backendCurrentPhase,
                  backendCompatMode: typeof backendCompatMode === 'boolean' ? backendCompatMode : session.backendCompatMode,
                  backendProjectionVersion: backendProjectionVersion || session.backendProjectionVersion,
                  updatedAt: '刚刚',
                }
              : session,
          ),
        )
      }
    } catch {
      const fallback = buildFallbackAssistant(command)
      setSessionHistories((prev) => {
        const sessionMessages = prev[targetSessionId] || []
        const withoutLoading = sessionMessages.filter((msg) => !msg.id.startsWith('a-loading-'))
        return {
          ...prev,
          [targetSessionId]: [
            ...withoutLoading,
            {
              id: `a-fallback-${Date.now()}`,
              role: 'assistant',
              content: fallback.content,
              ts: nowLabel(),
              stages: fallback.stages,
              meta: fallback.meta,
            },
          ],
        }
      })
    }
  }

  const refreshBackendSession = async () => {
    await Promise.all([
      backendSessionQuery.refetch(),
      backendTaskQuery.refetch(),
      backendEventQuery.refetch(),
      backendArtifactQuery.refetch(),
    ])
  }

  const sessionTelemetry = {
    sessionId: backendSessionQuery.data?.session_id || activeSession?.backendSessionId || null,
    currentPhase: backendSessionQuery.data?.current_phase || activeSession?.backendCurrentPhase || null,
    status: backendSessionQuery.data?.status || null,
    rootTaskId: backendSessionQuery.data?.root_task_id || activeSession?.backendRootTaskId || null,
    compatMode:
      typeof backendSessionQuery.data?.compat_mode === 'boolean'
        ? backendSessionQuery.data.compat_mode
        : activeSession?.backendCompatMode ?? null,
    projectionVersion:
      backendSessionQuery.data?.compat_projection_version || activeSession?.backendProjectionVersion || null,
    goal: backendSessionQuery.data?.goal || null,
    tasks: safeCount(backendTaskQuery.data),
    events: safeCount(backendEventQuery.data),
    artifacts: safeCount(backendArtifactQuery.data),
  }

  return (
    <div className="agent-chat-page">
      <section className="agent-chat-layout">
        <aside className="agent-chat-rail">
          <div className="agent-chat-section-head">
            <small>sessions</small>
            <button type="button" className="agent-chat-rail__new" onClick={() => createSession()}>
              + New
            </button>
          </div>
          <label className="agent-chat-session-filter">
            <span>search</span>
            <input
              value={sessionFilter}
              onChange={(event) => setSessionFilter(event.target.value)}
              placeholder="Search sessions"
            />
          </label>
          <div className="agent-chat-session-list">
            {filteredSessions.length ? (
              filteredSessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  className={`agent-chat-session-item ${activeSessionId === session.id ? 'is-active' : ''}`.trim()}
                  onClick={() => setActiveSessionId(session.id)}
                >
                  <strong>{session.title}</strong>
                  <small>{session.backendCurrentPhase ? `phase: ${session.backendCurrentPhase}` : session.updatedAt}</small>
                  <p>{sessionStats[session.id]?.preview || '暂无消息'}</p>
                  <em>{sessionStats[session.id]?.count || 0} 条</em>
                </button>
              ))
            ) : (
              <div className="agent-chat-session-empty">
                <strong>没有匹配会话</strong>
                <span>换个关键词，或者直接新建一个 agent 会话。</span>
              </div>
            )}
          </div>
        </aside>

        <div className="agent-chat-conversation">
          <div className="agent-chat-conversation-head">
            <div className="agent-chat-conversation-head__copy">
              <small>active session</small>
              <strong>{activeSession?.title || '当前会话'}</strong>
              <div className="agent-chat-conversation-head__stages">
                {STAGE_LABELS.map((stage) => (
                  <span key={stage.key} className="agent-chat-head-stage">
                    {stage.label}
                  </span>
                ))}
              </div>
            </div>
            <div className="agent-chat-conversation-head__meta">
              <span>{messageCountLabel}</span>
              <span>{projectKey}</span>
            </div>
          </div>
          <section className="agent-chat-session-panel">
            <div className="agent-chat-session-panel__head">
              <div>
                <small>agent session metadata</small>
                <strong>{sessionTelemetry.sessionId || '等待 compat session'}</strong>
              </div>
              <button
                type="button"
                className="agent-chat-session-panel__refresh"
                onClick={() => void refreshBackendSession()}
                disabled={!activeBackendSessionId}
              >
                <RefreshCw size={14} className={backendSessionQuery.isFetching ? 'spin' : undefined} />
                <span>Refresh</span>
              </button>
            </div>
            <div className="agent-chat-session-panel__grid">
              <div>
                <span>phase</span>
                <strong>{safeDisplay(sessionTelemetry.currentPhase)}</strong>
              </div>
              <div>
                <span>status</span>
                <strong>{safeDisplay(sessionTelemetry.status)}</strong>
              </div>
              <div>
                <span>compat</span>
                <strong>{safeDisplay(sessionTelemetry.compatMode)}</strong>
              </div>
              <div>
                <span>root task</span>
                <strong>{safeDisplay(sessionTelemetry.rootTaskId)}</strong>
              </div>
              <div>
                <span>tasks</span>
                <strong>{sessionTelemetry.tasks}</strong>
              </div>
              <div>
                <span>events / artifacts</span>
                <strong>
                  {sessionTelemetry.events} / {sessionTelemetry.artifacts}
                </strong>
              </div>
            </div>
            <div className="agent-chat-session-panel__footer">
              <span>{sessionTelemetry.projectionVersion ? `projection ${sessionTelemetry.projectionVersion}` : 'projection -'}</span>
              <span>{sessionTelemetry.goal || 'goal -'}</span>
            </div>
          </section>
          <div ref={listRef} className="agent-chat-message-list">
            {activeMessages.map((message) => {
              const contentParts = splitMessageContent(message.content)
              return (
                <article key={message.id} className={`agent-chat-message role-${message.role}`}>
                  <div className="agent-chat-message-body">
                    <p className="agent-chat-message-summary">{contentParts.summary}</p>
                    {contentParts.detailValue ? (
                      <details className="agent-chat-message-detail">
                        <summary>{contentParts.detailLabel || 'details'}</summary>
                        <pre>{contentParts.detailValue}</pre>
                      </details>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>

          <footer className="agent-chat-composer">
            <div className="agent-chat-composer-prompts">
              <small>starter commands</small>
              <div className="agent-chat-prompt-row">
                {DEFAULT_QUICK_COMMANDS.map((command) => (
                  <button
                    key={command}
                    type="button"
                    className="agent-chat-prompt-chip"
                    onClick={() =>
                      setDraftBySession((prev) => ({
                        ...prev,
                        [resolvedActiveSessionId]: command,
                      }))
                    }
                  >
                    <Sparkles size={14} />
                    <span>{command}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className="agent-chat-prompt-chip is-ghost"
                  onClick={() => createSession(currentDraft)}
                >
                  <Sparkles size={14} />
                  <span>基于当前草稿新建会话</span>
                </button>
              </div>
            </div>
              <textarea
              value={currentDraft}
              placeholder="输入自然语言指令，例如：为德州电力市场生成可执行采集计划，并附上回放策略。"
              onChange={(event) =>
                setDraftBySession((prev) => ({
                  ...prev,
                  [resolvedActiveSessionId]: event.target.value,
                }))
              }
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void sendMessage(currentDraft)
                  return
                }
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                  event.preventDefault()
                  void sendMessage(currentDraft)
                }
              }}
            />
            <div className="agent-chat-composer-hint">
              <span>Enter 发送</span>
              <span>Shift + Enter 换行</span>
              <span>Cmd/Ctrl + Enter 立即提交</span>
            </div>
            <div className="agent-chat-composer-actions">
              <button
                type="button"
                className="button-secondary"
                onClick={() =>
                  setSessionHistories((prev) => ({
                    ...prev,
                    [resolvedActiveSessionId]: [buildSystemMessage(projectKey)],
                  }))
                }
              >
                清空消息
              </button>
              <button
                type="button"
                className="button-primary"
                onClick={() => void sendMessage(currentDraft)}
                disabled={nlCommandMutation.isPending || !currentDraft.trim()}
              >
                {nlCommandMutation.isPending ? <LoaderCircle size={14} className="spin" /> : <SendHorizonal size={14} />}
                <span>{nlCommandMutation.isPending ? '处理中...' : '发送'}</span>
              </button>
            </div>
          </footer>
        </div>
      </section>
    </div>
  )
}
