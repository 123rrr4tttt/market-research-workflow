import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Circle,
  Clock3,
  FileText,
  LoaderCircle,
  MessageSquarePlus,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Search,
  SendHorizonal,
  ShieldCheck,
  Sparkles,
  Wrench,
  XCircle,
} from 'lucide-react'
import {
  cancelAgentSession,
  continueAgentChatApproval,
  getAgentSession,
  listAgentSessionArtifacts,
  listAgentChatCapabilities,
  listAgentSessionEvents,
  listAgentSessionTasks,
  openAgentSessionEventStream,
  retryAgentSessionTask,
  resolveAgentApproval,
  runAgentChatTurn,
  runAgentChatTurnStreaming,
  runAgentSessionCoordinatorPass,
} from '../lib/api'
import type {
  AgentApprovalItem,
  AgentArtifactItem,
  AgentChatCapabilityCall,
  AgentChatCapabilityItem,
  AgentChatTurnResult,
  AgentEventItem,
  AgentSessionEventStreamStatus,
  AgentTaskItem,
} from '../lib/types'
import { translate, useAppLocale, type AppLocale, type MessageKey } from '../app/platform/i18n'
import './agent-chat.css'

type AgentChatPageProps = {
  projectKey: string
}

type ChatRole = 'system' | 'user' | 'assistant'
type StageStatus = 'pending' | 'running' | 'done'
type WorkbenchView = 'overview' | 'tasks' | 'tools' | 'approvals' | 'artifacts'
type SourceHistoryFilter = 'all' | 'open' | 'approved' | 'deferred' | 'rejected'
type UnknownRecord = { [key: string]: unknown }
type StringMap = { [key: string]: string }
type CountMap = { [key: string]: number }
type CapabilityGroupMap = { [key: string]: AgentChatCapabilityItem[] | null | undefined }

type StageItem = {
  key: string
  label: string
  status: StageStatus
}

type WorkbenchTimelineItem = {
  key: string
  title: string
  meta: string
  summary: string
  status: string
}

type ProgressiveToolEventItem = {
  key: string
  type: string
  toolName: string
  summary: string
  status: string
  meta: string
}

type SourceQualityCard = {
  key: string
  title: string
  status: string
  score: string
  level: string
  reason: string
  url: string
  snippet: string
  provider: string
  nextGate: string
  rawCandidate: UnknownRecord
  reviewDecision?: 'approved' | 'deferred' | 'rejected'
  reviewReason?: string
  reviewNextGate?: string
  reviewTaskId?: string
  reviewedAt?: string
}

type WritingDiffCard = {
  key: string
  toolName: string
  operation: string
  added: number | null
  removed: number | null
  docId: string
  summary: string
}

type InvestigationTraceCard = {
  key: string
  focus: string
  nodeCount: string
  edgeCount: string
  summary: string
  pendingQuestion: string
}

type LongTaskStageCard = {
  key: string
  currentStage: string
  completed: string
  lastStage: string
  summary: string
  counts: string
  nextAction: string
}

type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  ts: string
  state?: 'error'
  stages?: StageItem[]
  meta?: string[]
  capabilityCalls?: AgentChatCapabilityCall[]
  agentTasks?: AgentTaskItem[]
  agentEvents?: AgentEventItem[]
  suggestedNextActions?: string[]
  agentMode?: string
  retryCommand?: string
  retrySessionId?: string
}

type ChatHistoryMap = { [sessionId: string]: ChatMessage[] }
type SessionStatsMap = { [sessionId: string]: { count: number; preview: string } }

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

type SessionRunState = {
  pending: boolean
  backendSessionId?: string | null
  streamStatus?: AgentSessionEventStreamStatus
  startedAt?: number
  lastEventAt?: number
}

type SessionRunStateMap = { [sessionId: string]: SessionRunState }

type StoredAgentChatState = {
  activeSessionId: string
  sessions: ChatSession[]
  sessionHistories: ChatHistoryMap
  draftBySession?: StringMap
}

function isTerminalAgentSessionStatus(status?: string | null) {
  return ['completed', 'failed', 'canceled', 'cancelled'].includes(String(status || '').toLowerCase())
}

const AGENT_CHAT_QUICK_COMMAND_KEYS = [
  'agentChat.composer.quickCommand.marketDrivers',
  'agentChat.composer.quickCommand.ingestBatch',
  'agentChat.composer.quickCommand.runtimeRisk',
] as const

const STAGE_LABELS = [
  { key: 'context', labelKey: 'agentChat.stage.context' },
  { key: 'tools', labelKey: 'agentChat.stage.tools' },
  { key: 'answer', labelKey: 'agentChat.stage.answer' },
] as const

const WORKBENCH_VIEW_LABEL_KEYS: Record<WorkbenchView, MessageKey> = {
  overview: 'agentChat.workbench.tab.overview',
  tasks: 'agentChat.workbench.tab.tasks',
  tools: 'agentChat.workbench.tab.tools',
  approvals: 'agentChat.workbench.tab.approvals',
  artifacts: 'agentChat.workbench.tab.artifacts',
}

const SOURCE_HISTORY_FILTERS: SourceHistoryFilter[] = ['all', 'open', 'approved', 'deferred', 'rejected']

const SOURCE_HISTORY_FILTER_LABEL_KEYS: Record<SourceHistoryFilter, MessageKey> = {
  all: 'agentChat.source.filter.all',
  open: 'agentChat.source.filter.open',
  approved: 'agentChat.source.filter.approved',
  deferred: 'agentChat.source.filter.deferred',
  rejected: 'agentChat.source.filter.rejected',
}
const AGENT_CHAT_STORAGE_PREFIX = 'agent-chat-state-v1'
const DEFAULT_SESSION_ID = 's-default'
const TECHNICAL_TEXT = {
  assistantDeltaEventFragment: { value: '.assistant_delta' },
  assistantMessageEventFragment: { value: '.assistant_message' },
  finalAnswerEventFragment: { value: '.final_answer' },
  objectObject: { value: '[object Object]' },
  unknownBackendError: { value: 'unknown backend error' },
  parsedDetailPrefix: { value: 'parsed:\n' },
  sourceCandidateReviewsArtifact: { value: 'source.candidate_reviews.json' },
  sourceCandidateReviewContract: { value: 'source.candidate.review.v1' },
  ingestUrlPoolSubmissionsArtifact: { value: 'ingest.url_pool_submissions.json' },
  ingestUrlPoolSubmitContract: { value: 'ingest.url_pool.submit.v1' },
  investigationTraceContract: { value: 'agent_investigation.trace.v1' },
  longTaskStageContract: { value: 'agent_long_task.stage.v1' },
  longTaskStateArtifact: { value: 'agent_long_task.state.json' },
  agentChatTurnBackend: { value: '/agent-chat/turn' },
  approvalContinueBackend: { value: '/agent-chat/approvals/continue' },
  approvalResolveBackend: { value: '/agent-approvals/resolve' },
  sourceCandidateReviewPayload: { value: 'source_candidate_review JSON' },
  sourceDecisionCollect: { value: '采集' },
  sourceDecisionPass: { value: '通过' },
  sourceDecisionUse: { value: '采用' },
  sourceDecisionDefer: { value: '暂缓' },
  sourceDecisionLater: { value: '稍后' },
  sourceDecisionReject: { value: '拒绝' },
  sourceDecisionDiscard: { value: '丢弃' },
  urlPoolGatePrefix: { value: 'URL-pool ' },
  readyState: { value: 'ready' },
  interactiveToolCallRequested: { value: 'interactive_agent.tool_call_requested' },
  interactiveToolCallStarted: { value: 'interactive_agent.tool_call_started' },
  interactiveToolCallResult: { value: 'interactive_agent.tool_call_result' },
  interactiveCapabilityExecuted: { value: 'interactive_agent.capability_executed' },
  agentCoreToolCallRequested: { value: 'agent_core.tool_call_requested' },
  agentCoreToolCallStarted: { value: 'agent_core.tool_call_started' },
  agentCoreToolResult: { value: 'agent_core.tool_result' },
  approvalOverrideExample: { value: '{"graph_id":"...","inputs":{}}' },
  enterKey: { value: 'Enter' },
} as const

function formatCatalogTemplate(template: string, values: { [key: string]: string | number }) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function compactText(value: unknown) {
  return String(value ?? '').trim()
}

function joinWithSeparator(values: Array<string | number | boolean | null | undefined>, separator: string) {
  return values
    .map((value) => compactText(value))
    .filter(Boolean)
    .join(separator)
}

function joinWithColon(values: Array<string | number | boolean | null | undefined>) {
  return joinWithSeparator(values, ':')
}

function joinWithHyphen(values: Array<string | number | boolean | null | undefined>) {
  return joinWithSeparator(values, '-')
}

function joinWithMiddleDot(values: Array<string | number | boolean | null | undefined>) {
  return joinWithSeparator(values, ' · ')
}

function debugMeta(label: string, value: string | number | boolean | null | undefined) {
  const content = compactText(value)
  return content ? label + ': ' + content : ''
}

function runtimeId(prefix: string) {
  return joinWithHyphen([prefix, Date.now()])
}

function refetchNoop() {
  return Promise.resolve()
}

function buildDefaultSessions(locale: AppLocale): ChatSession[] {
  return [
    {
      id: DEFAULT_SESSION_ID,
      title: translate(locale, 'agentChat.session.newTitle'),
      updatedAt: translate(locale, 'agentChat.session.updatedNow'),
    },
  ]
}

function buildBaseStages(locale: AppLocale): StageItem[] {
  return STAGE_LABELS.map((stage, idx) => ({
    key: stage.key,
    label: translate(locale, stage.labelKey),
    status: idx === 0 ? 'running' : 'pending',
  }))
}

function buildStreamingStages(locale: AppLocale): StageItem[] {
  return STAGE_LABELS.map((stage) => ({
    key: stage.key,
    label: translate(locale, stage.labelKey),
    status: stage.key === 'answer' ? 'running' : 'done',
  }))
}

function buildPendingStages(locale: AppLocale): StageItem[] {
  return STAGE_LABELS.map((stage) => ({
    key: stage.key,
    label: translate(locale, stage.labelKey),
    status: 'pending',
  }))
}

function buildCompletedStages(locale: AppLocale): StageItem[] {
  return STAGE_LABELS.map((stage) => ({
    key: stage.key,
    label: translate(locale, stage.labelKey),
    status: 'done',
  }))
}

function nowLabel() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function extractAssistantStreamChunk(event: AgentEventItem): { mode: 'append' | 'replace'; text: string } | null {
  const eventType = String(event.event_type || '').toLowerCase()
  const payloadRecord =
    event.payload && typeof event.payload === 'object'
      ? (event.payload as UnknownRecord)
      : {}
  const firstString = (...keys: string[]) => {
    for (const key of keys) {
      const value = payloadRecord[key]
      if (typeof value === 'string' && value.length) return value
    }
    return ''
  }
  if (eventType.endsWith('assistant_delta') || eventType.includes(TECHNICAL_TEXT.assistantDeltaEventFragment.value)) {
    const text = firstString('delta', 'text', 'content')
    return text ? { mode: 'append', text } : null
  }
  if (eventType.endsWith('assistant_message') || eventType.includes(TECHNICAL_TEXT.assistantMessageEventFragment.value)) {
    const text = firstString('content', 'text', 'message').trim()
    return text ? { mode: 'replace', text } : null
  }
  if (eventType.endsWith('final_answer') || eventType.includes(TECHNICAL_TEXT.finalAnswerEventFragment.value)) {
    const text = firstString('final_answer', 'answer', 'content', 'text').trim()
    return text ? { mode: 'replace', text } : null
  }
  return null
}

function extractProgressiveStreamText(locale: AppLocale, event: AgentEventItem): string {
  const eventType = String(event.event_type || '').toLowerCase()
  const payload =
    event.payload && typeof event.payload === 'object'
      ? (event.payload as UnknownRecord)
      : {}
  const toolCall =
    payload.tool_call && typeof payload.tool_call === 'object'
      ? (payload.tool_call as UnknownRecord)
      : {}
  const toolName = String(
    payload.tool_name
      || payload.capability_id
      || toolCall.tool_name
      || toolCall.capability_id
      || '',
  ).trim()
  const summary = String(payload.model_summary || payload.ui_summary || payload.summary || '').trim()
  const phase = String(payload.phase || '').trim()
  const transition = String(payload.transition_reason || '').trim()
  if (eventType.includes('tool_call_requested')) {
    return toolName
      ? formatCatalogTemplate(translate(locale, 'agentChat.stream.toolCallRequestedWithTool'), { tool: toolName })
      : translate(locale, 'agentChat.stream.toolCallRequested')
  }
  if (eventType.includes('tool_call_started')) {
    return toolName
      ? formatCatalogTemplate(translate(locale, 'agentChat.stream.toolCallStartedWithTool'), { tool: toolName })
      : translate(locale, 'agentChat.stream.toolCallStarted')
  }
  if (eventType.includes('tool_progress')) {
    return summary || (toolName
      ? formatCatalogTemplate(translate(locale, 'agentChat.stream.toolProgressWithTool'), { tool: toolName })
      : translate(locale, 'agentChat.stream.toolProgress'))
  }
  if (eventType.includes('tool_result')) {
    if (toolName && summary) {
      return formatCatalogTemplate(translate(locale, 'agentChat.stream.toolResultWithToolAndSummary'), { tool: toolName, summary })
    }
    return toolName
      ? formatCatalogTemplate(translate(locale, 'agentChat.stream.toolResultWithTool'), { tool: toolName })
      : translate(locale, 'agentChat.stream.toolResult')
  }
  if (eventType.includes('permission_requested')) {
    return toolName
      ? formatCatalogTemplate(translate(locale, 'agentChat.stream.permissionRequestedWithTool'), { tool: toolName })
      : translate(locale, 'agentChat.stream.permissionRequested')
  }
  if (eventType.includes('turn_state')) {
    if (phase === 'model_step') return translate(locale, 'agentChat.stream.turnModelStep')
    if (phase === 'tool_calls') return translate(locale, 'agentChat.stream.turnToolCalls')
    if (phase === 'final_answer') return translate(locale, 'agentChat.stream.turnFinalAnswer')
    if (transition) return formatCatalogTemplate(translate(locale, 'agentChat.stream.turnTransition'), { transition })
  }
  if (eventType.includes('run_resumed')) return translate(locale, 'agentChat.stream.runResumed')
  return ''
}

function buildSystemMessage(projectKey: string, locale: AppLocale, hint?: string): ChatMessage {
  return {
    id: runtimeId('sys'),
    role: 'system',
    ts: nowLabel(),
    content: hint || translate(locale, 'agentChat.system.ready'),
    meta: [debugMeta('project', projectKey)],
  }
}

function buildSeedHistories(projectKey: string, locale: AppLocale): ChatHistoryMap {
  return {
    [DEFAULT_SESSION_ID]: [buildSystemMessage(projectKey, locale)],
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
  locale: AppLocale,
  storedSessions?: ChatSession[] | null,
  sessionHistories?: ChatHistoryMap | null,
): ChatSession[] {
  const sessionsById = new Map<string, ChatSession>()
  const defaultSessions = buildDefaultSessions(locale)
  for (const session of storedSessions || []) {
    if (!session?.id) continue
    sessionsById.set(session.id, session)
  }
  for (const session of defaultSessions) {
    if (!sessionsById.has(session.id)) {
      sessionsById.set(session.id, session)
    }
  }
  for (const sessionId of Object.keys(sessionHistories || {})) {
    if (!sessionsById.has(sessionId)) {
      sessionsById.set(sessionId, {
        id: sessionId,
        title: translate(locale, 'agentChat.session.recoveredTitle'),
        updatedAt: translate(locale, 'agentChat.session.updatedNow'),
      })
    }
  }
  return Array.from(sessionsById.values())
}

function mergeHistoriesWithSeed(projectKey: string, locale: AppLocale, fromStorage?: ChatHistoryMap | null): ChatHistoryMap {
  const seed = buildSeedHistories(projectKey, locale)
  const baseSessions = Array.from(new Set([...buildDefaultSessions(locale).map((session) => session.id), ...Object.keys(fromStorage || {})]))
  const mergedEntries = baseSessions.map((sessionId) => {
    const cached = fromStorage?.[sessionId]
    if (Array.isArray(cached) && cached.length > 0) return [sessionId, cached] as const
    return [sessionId, seed[sessionId] || [buildSystemMessage(projectKey, locale)]] as const
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

function buildSessionId() {
  return joinWithHyphen(['s', Date.now().toString(36)])
}

function buildSessionTitle(command: string | undefined, locale: AppLocale) {
  const normalized = String(command || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return translate(locale, 'agentChat.session.newTitle')
  return normalized.slice(0, 28)
}

function safeDisplay(value?: string | number | boolean | null, fallback = '-') {
  if (value === null || value === undefined || value === '') return fallback
  return typeof value === 'boolean' ? (value ? 'yes' : 'no') : String(value)
}

function asRecord(value: unknown): UnknownRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as UnknownRecord) : null
}

function safeCount(value: unknown) {
  return Array.isArray(value) ? value.length : 0
}

function toTextList(value: unknown) {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => String(item || '').trim())
    .map((item, index) => {
      const raw = value[index]
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return item
      const record = raw as UnknownRecord
      const direct = record.text || record.title || record.summary || record.label || record.item_key || record.id || record.url
      if (direct) return String(direct).trim()
      return item === TECHNICAL_TEXT.objectObject.value ? toCompactJson(record) : item
    })
    .filter(Boolean)
}

function formatBackendError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || '')
  return message.trim() || TECHNICAL_TEXT.unknownBackendError.value
}

function normalizeStatusToken(value?: string | null) {
  return String(value || 'idle').toLowerCase().replace(/[^a-z0-9_-]+/g, '-') || 'idle'
}

function normalizeMaterialCategoryToken(value?: string | null) {
  return String(value || 'unknown').toLowerCase().replace(/[^a-z0-9_-]+/g, '-') || 'unknown'
}

function splitMessageContent(content: string) {
  const [summary, ...rest] = content.split('\n\n')
  const detail = rest.join('\n\n').trim()
  if (detail.startsWith(TECHNICAL_TEXT.parsedDetailPrefix.value)) {
    return {
      summary: summary.trim(),
      detailLabel: 'parsed',
      detailValue: detail.replace(TECHNICAL_TEXT.parsedDetailPrefix.value, '').trim(),
    }
  }
  return {
    summary: content.trim(),
    detailLabel: '',
    detailValue: '',
  }
}

function getAgentEventKey(event: AgentEventItem) {
  return String(event.event_id || joinWithColon([event.seq || 0, event.event_type || '', event.ts || '']))
}

function mergeAgentEvents(base: AgentEventItem[], incoming: AgentEventItem[]) {
  const byKey = new Map<string, AgentEventItem>()
  for (const event of [...base, ...incoming]) {
    byKey.set(getAgentEventKey(event), event)
  }
  return Array.from(byKey.values()).sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0))
}

function eventToCapabilityCall(event: AgentEventItem): AgentChatCapabilityCall | null {
  const payload = event.payload || {}
  const nestedToolCall = asRecord(payload.tool_call)
  const resultRecord = typeof payload.result === 'object' && payload.result
    ? (payload.result as UnknownRecord)
    : typeof payload.structured_content === 'object' && payload.structured_content
      ? (payload.structured_content as UnknownRecord)
      : null
  const materialCategory = asRecord(payload.material_category) || asRecord(resultRecord?.material_category)
  const capabilityId = String(payload.capability_id || payload.tool_name || nestedToolCall?.tool_name || '').trim()
  if (!capabilityId) return null
  return {
    call_id: String(payload.call_id || nestedToolCall?.call_id || event.call_id || '').trim() || null,
    capability_id: capabilityId,
    tool_name: String(payload.tool_name || nestedToolCall?.tool_name || capabilityId),
    protocol: typeof payload.protocol === 'string' ? payload.protocol : null,
    stream_state: typeof payload.stream_state === 'string' ? payload.stream_state : null,
    status: typeof payload.status === 'string' ? payload.status : String(payload.stream_state || event.event_type || ''),
    summary: typeof payload.summary === 'string'
      ? payload.summary
      : typeof payload.ui_summary === 'string'
        ? payload.ui_summary
        : typeof payload.model_summary === 'string'
          ? payload.model_summary
          : null,
    approval_id: typeof payload.approval_id === 'string' ? payload.approval_id : null,
    run_id: typeof payload.run_id === 'string' ? payload.run_id : null,
    result: resultRecord,
    error: typeof payload.error === 'object' && payload.error ? (payload.error as UnknownRecord) : null,
    material_category: materialCategory
      ? {
          category: typeof materialCategory.category === 'string' ? materialCategory.category : null,
          label: typeof materialCategory.label === 'string' ? materialCategory.label : null,
        }
      : null,
  }
}

function mergeCapabilityCalls(base: AgentChatCapabilityCall[], streamed: AgentChatCapabilityCall[]) {
  const byKey = new Map<string, AgentChatCapabilityCall>()
  for (const [index, call] of [...base, ...streamed].entries()) {
    const key = call.call_id
      ? joinWithColon([call.capability_id || call.tool_name || 'tool', call.call_id])
      : joinWithColon([call.capability_id || call.tool_name || 'tool', call.status || '', call.summary || '', index])
    byKey.set(key, call)
  }
  return Array.from(byKey.values())
}

function normalizeAgentEventType(event: AgentEventItem) {
  return String(event.event_type || '').replace(/^agent_core\./, '').replace(/^interactive_agent\./, '')
}

function getEventPayloadRecord(event: AgentEventItem) {
  return asRecord(event.payload) || {}
}

function getEventToolName(event: AgentEventItem) {
  const payload = getEventPayloadRecord(event)
  const toolCall = asRecord(payload.tool_call)
  return String(payload.capability_id || payload.tool_name || toolCall?.tool_name || '').trim()
}

function getEventStructuredContent(event: AgentEventItem) {
  const payload = getEventPayloadRecord(event)
  return asRecord(payload.structured_content) || asRecord(payload.result) || null
}

function formatAgentEventSummary(locale: AppLocale, event: AgentEventItem) {
  const payload = event.payload || {}
  const type = normalizeAgentEventType(event)
  if (type === 'turn_state') {
    const phase = safeDisplay(payload.phase as string | number | boolean | null)
    const iteration = safeDisplay(payload.iteration as string | number | boolean | null)
    const maxIterations = safeDisplay(payload.max_iterations as string | number | boolean | null)
    const toolCount = safeDisplay(payload.tool_call_count as string | number | boolean | null)
    const maxTools = safeDisplay(payload.max_tool_calls as string | number | boolean | null)
    return formatCatalogTemplate(translate(locale, 'agentChat.event.summary.turnState'), { phase, iteration, maxIterations, toolCount, maxTools })
  }
  const toolName = getEventToolName(event)
  const direct = [event.message, payload.summary, payload.ui_summary, payload.model_summary, payload.message, toolName, payload.capability_id, payload.tool_name].find(
    (value) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean',
  )
  return safeDisplay(direct || event.task_id)
}

function formatEventTitle(locale: AppLocale, event: AgentEventItem) {
  const type = normalizeAgentEventType(event) || 'event'
  if (type.includes('tool_call_requested')) return translate(locale, 'agentChat.event.title.toolRequested')
  if (type.includes('tool_call_started')) return translate(locale, 'agentChat.event.title.toolStarted')
  if (type.includes('tool_call_result')) return translate(locale, 'agentChat.event.title.toolResult')
  if (type.includes('tool_result')) return translate(locale, 'agentChat.event.title.toolResult')
  if (type.includes('turn_state')) return translate(locale, 'agentChat.event.title.turnState')
  if (type.includes('approval')) return translate(locale, 'agentChat.event.title.approvalUpdate')
  if (type.includes('task')) return translate(locale, 'agentChat.event.title.taskUpdate')
  return type.replace(/^interactive_agent\./, '').replace(/^agent_core\./, '').replace(/[._-]+/g, ' ')
}

function buildWorkbenchTimeline(locale: AppLocale, events: AgentEventItem[], tasks: AgentTaskItem[]): WorkbenchTimelineItem[] {
  const eventItems = events.slice(-7).map((event) => ({
    key: getAgentEventKey(event),
    title: formatEventTitle(locale, event),
    meta: formatCatalogTemplate(translate(locale, 'agentChat.event.meta.event'), {
      seq: safeDisplay(event.seq),
      severity: safeDisplay(event.severity || 'info'),
    }),
    summary: formatAgentEventSummary(locale, event),
    status: normalizeStatusToken(String(event.severity || event.event_type || 'event')),
  }))
  const taskItems = tasks.slice(-4).map((task) => ({
    key: joinWithHyphen(['task', task.task_id]),
    title: task.subject || task.task_type || task.task_id,
    meta: formatCatalogTemplate(translate(locale, 'agentChat.event.meta.task'), {
      status: safeDisplay(task.status),
      phase: safeDisplay(task.phase),
    }),
    summary: task.result_summary || task.progress?.summary_label || task.description || '-',
    status: normalizeStatusToken(task.status),
  }))
  return [...eventItems, ...taskItems].slice(-8).reverse()
}

function mergeAgentTasks(base: AgentTaskItem[], incoming: AgentTaskItem[]) {
  const byKey = new Map<string, AgentTaskItem>()
  for (const task of [...base, ...incoming]) {
    if (!task?.task_id) continue
    byKey.set(task.task_id, { ...(byKey.get(task.task_id) || {}), ...task })
  }
  return Array.from(byKey.values()).sort((a, b) => {
    const pa = typeof a.priority === 'number' ? a.priority : 999
    const pb = typeof b.priority === 'number' ? b.priority : 999
    return pa - pb || String(a.created_at || '').localeCompare(String(b.created_at || ''))
  })
}

function latestMessageTasks(messages: ChatMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const tasks = messages[index]?.agentTasks
    if (Array.isArray(tasks) && tasks.length) return tasks
  }
  return []
}

function latestMessageEvents(messages: ChatMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const events = messages[index]?.agentEvents
    if (Array.isArray(events) && events.length) return events
  }
  return []
}

function buildProgressiveToolEvents(locale: AppLocale, events: AgentEventItem[]): ProgressiveToolEventItem[] {
  return events
    .filter((event) => ['turn_state', 'tool_call_requested', 'tool_call_started', 'tool_result', 'tool_call_result'].includes(normalizeAgentEventType(event)))
    .slice(-14)
    .map((event) => {
      const type = normalizeAgentEventType(event)
      const toolName = getEventToolName(event) || (type === 'turn_state' ? translate(locale, 'agentChat.tool.genericAgentLoop') : translate(locale, 'agentChat.tool.genericTool'))
      const payload = getEventPayloadRecord(event)
      return {
        key: getAgentEventKey(event),
        type,
        toolName,
        summary: formatAgentEventSummary(locale, event),
        status: normalizeStatusToken(String(payload.status || payload.stream_state || event.severity || type)),
        meta: formatCatalogTemplate(translate(locale, 'agentChat.event.meta.sequence'), {
          seq: safeDisplay(event.seq),
          call: safeDisplay(event.call_id || payload.call_id as string | number | boolean | null),
        }),
      }
    })
    .reverse()
}

function buildSourceQualityCards(locale: AppLocale, events: AgentEventItem[], calls: AgentChatCapabilityCall[]): SourceQualityCard[] {
  const cardsByKey = new Map<string, SourceQualityCard>()
  const consume = (source: UnknownRecord | null, keyPrefix: string) => {
    const historySessions = Array.isArray(source?.sessions) ? source.sessions : []
    for (const [sessionIndex, rawSession] of historySessions.entries()) {
      const session = asRecord(rawSession)
      if (!session) continue
      const reviews = Array.isArray(session.reviews) ? session.reviews : []
      for (const [reviewIndex, rawReview] of reviews.entries()) {
        consume(asRecord(rawReview), joinWithHyphen([keyPrefix, 'history', 'review', sessionIndex, reviewIndex]))
      }
      const submissions = Array.isArray(session.submissions) ? session.submissions : []
      for (const [submissionIndex, rawSubmission] of submissions.entries()) {
        const submission = asRecord(rawSubmission)
        if (!submission) continue
        consume(
          { ingest_payload: submission, decision: 'approved', next_gate: 'inspect_ingest_status_or_source_artifacts' },
          joinWithHyphen([keyPrefix, 'history', 'submission', sessionIndex, submissionIndex]),
        )
      }
    }
    const review = asRecord(source?.review)
    const reviewCandidate = asRecord(review?.candidate) || asRecord(source?.candidate)
    const reviewIngestPayload = asRecord(source?.ingest_payload) || asRecord(review?.ingest_payload)
    if (reviewCandidate || reviewIngestPayload) {
      const candidate = reviewCandidate || reviewIngestPayload || {}
      const trust = asRecord(candidate.trust) || asRecord((asRecord(reviewIngestPayload?.metadata) || {}).trust) || {}
      const url = normalizeSourceCandidateKey(candidate) || normalizeSourceCandidateKey(reviewIngestPayload)
      const key = String(url || joinWithHyphen([keyPrefix, 'review']))
      cardsByKey.set(key, {
        key,
        title: safeDisplay((candidate.title || candidate.name || reviewIngestPayload?.source_name) as string | number | boolean | null, translate(locale, 'agentChat.source.fallback.candidate')),
        status: safeDisplay((trust.status || source?.decision || review?.decision) as string | number | boolean | null, 'candidate'),
        score: safeDisplay(trust.trust_score as string | number | boolean | null),
        level: safeDisplay(trust.trust_level as string | number | boolean | null),
        reason: safeDisplay((review?.reason || source?.reason || trust.blocked_reason) as string | number | boolean | null, ''),
        url,
        snippet: safeDisplay((candidate.snippet || (asRecord(reviewIngestPayload?.metadata) || {}).snippet) as string | number | boolean | null, ''),
        provider: safeDisplay((candidate.provider || candidate.source_provider || (asRecord(reviewIngestPayload?.metadata) || {}).provider) as string | number | boolean | null, ''),
        nextGate: safeDisplay((review?.next_gate || source?.next_gate) as string | number | boolean | null, ''),
        rawCandidate: candidate,
        reviewDecision: normalizeSourceCandidateDecision(source?.decision || review?.decision),
        reviewReason: safeDisplay((review?.reason || source?.reason) as string | number | boolean | null, ''),
        reviewNextGate: safeDisplay((review?.next_gate || source?.next_gate) as string | number | boolean | null, ''),
        reviewedAt: safeDisplay((review?.reviewed_at || source?.reviewed_at || source?.updated_at) as string | number | boolean | null, ''),
      })
    }
    const candidates = Array.isArray(source?.candidate_urls) ? source?.candidate_urls : []
    for (const [index, raw] of candidates.entries()) {
      const item = asRecord(raw)
      if (!item) continue
      const reasons = toTextList(item.trust_reasons)
      const key = String(item.normalized_url || item.original_url || item.domain || joinWithHyphen([keyPrefix, index]))
      cardsByKey.set(key, {
        key,
        title: String(item.domain || item.normalized_url || item.original_url || 'source'),
        status: String(item.status || 'candidate'),
        score: safeDisplay(item.trust_score as string | number | boolean | null),
        level: safeDisplay(item.trust_level as string | number | boolean | null),
        reason: reasons.slice(0, 3).join(', ') || safeDisplay(item.blocked_reason as string | number | boolean | null),
        url: safeDisplay(item.normalized_url as string | number | boolean | null) || safeDisplay(item.original_url as string | number | boolean | null),
        snippet: '',
        provider: '',
        nextGate: safeDisplay(source?.next_gate as string | number | boolean | null),
        rawCandidate: item,
      })
    }
    const searchCandidates = Array.isArray(source?.candidates) ? source?.candidates : []
    for (const [index, raw] of searchCandidates.entries()) {
      const item = asRecord(raw)
      if (!item) continue
      const trust = asRecord(item.trust) || {}
      const reasons = toTextList(trust.trust_reasons)
      const url = safeDisplay(item.url as string | number | boolean | null)
      const key = String(url || item.title || joinWithHyphen([keyPrefix, 'search', index]))
      cardsByKey.set(key, {
        key,
        title: safeDisplay(
          item.title as string | number | boolean | null,
          safeDisplay(trust.domain as string | number | boolean | null, translate(locale, 'agentChat.source.fallback.candidate')),
        ),
        status: safeDisplay(trust.status as string | number | boolean | null, 'candidate'),
        score: safeDisplay(trust.trust_score as string | number | boolean | null),
        level: safeDisplay(trust.trust_level as string | number | boolean | null),
        reason: reasons.slice(0, 3).join(', ') || safeDisplay(trust.blocked_reason as string | number | boolean | null),
        url,
        snippet: safeDisplay(item.snippet as string | number | boolean | null),
        provider: safeDisplay((item.provider || item.source_provider) as string | number | boolean | null),
        nextGate: safeDisplay(source?.next_gate as string | number | boolean | null, 'review_candidates_then_source_library_or_url_pool_ingest'),
        rawCandidate: item,
      })
    }
  }
  for (const event of events) consume(getEventStructuredContent(event), getAgentEventKey(event))
  for (const [index, call] of calls.entries()) consume(asRecord(call.result), joinWithHyphen(['call', call.call_id || index]))
  return Array.from(cardsByKey.values()).slice(-6).reverse()
}

function normalizeSourceCandidateKey(source?: UnknownRecord | null) {
  if (!source) return ''
  return String(
    source.url
      || source.normalized_url
      || source.original_url
      || source.link
      || source.item_key
      || source.source_library_item_key
      || source.title
      || '',
  ).trim()
}

function normalizeSourceCandidateDecision(value: unknown): SourceQualityCard['reviewDecision'] | undefined {
  const decision = String(value || '').trim().toLowerCase()
  if (['approved', 'approve', 'accepted', TECHNICAL_TEXT.sourceDecisionCollect.value, TECHNICAL_TEXT.sourceDecisionPass.value, TECHNICAL_TEXT.sourceDecisionUse.value].includes(decision)) return 'approved'
  if (['deferred', 'defer', 'pending', TECHNICAL_TEXT.sourceDecisionDefer.value, TECHNICAL_TEXT.sourceDecisionLater.value].includes(decision)) return 'deferred'
  if (['rejected', 'reject', 'refused', TECHNICAL_TEXT.sourceDecisionReject.value, TECHNICAL_TEXT.sourceDecisionDiscard.value].includes(decision)) return 'rejected'
  return undefined
}

function formatSourceCandidateDecision(locale: AppLocale, decision?: SourceQualityCard['reviewDecision']) {
  if (decision === 'approved') return translate(locale, 'agentChat.source.decision.approved')
  if (decision === 'deferred') return translate(locale, 'agentChat.source.decision.deferred')
  if (decision === 'rejected') return translate(locale, 'agentChat.source.decision.rejected')
  return ''
}

function buildSourceCandidateDecisionMap(
  locale: AppLocale,
  events: AgentEventItem[],
  calls: AgentChatCapabilityCall[],
  artifacts: AgentArtifactItem[],
) {
  type CandidateDecisionPatch = Pick<SourceQualityCard, 'reviewDecision' | 'reviewReason' | 'reviewNextGate' | 'reviewTaskId' | 'reviewedAt'>

  const decisions = new Map<string, CandidateDecisionPatch>()

  const upsertDecision = (key: string, patch: CandidateDecisionPatch) => {
    if (!key) return
    const existing = decisions.get(key) || {}
    const existingGate = String(existing.reviewNextGate || '')
    const incomingGate = String(patch.reviewNextGate || '')
    const normalizedPatch = {
      ...patch,
      reviewReason: patch.reviewReason || existing.reviewReason,
      reviewTaskId: patch.reviewTaskId || existing.reviewTaskId,
      reviewedAt: patch.reviewedAt || existing.reviewedAt,
    }
    if (existingGate.startsWith(TECHNICAL_TEXT.urlPoolGatePrefix.value) && !incomingGate.startsWith(TECHNICAL_TEXT.urlPoolGatePrefix.value)) {
      normalizedPatch.reviewNextGate = existing.reviewNextGate
    } else if (!incomingGate && existing.reviewNextGate) {
      normalizedPatch.reviewNextGate = existing.reviewNextGate
    }
    decisions.set(key, {
      ...existing,
      ...normalizedPatch,
    })
  }

  const consumeReview = (source: UnknownRecord | null) => {
    if (!source) return
    const historySessions = Array.isArray(source.sessions) ? source.sessions : []
    for (const rawSession of historySessions) {
      const session = asRecord(rawSession)
      if (!session) continue
      const reviews = Array.isArray(session.reviews) ? session.reviews : []
      for (const rawReview of reviews) consumeReview(asRecord(rawReview))
    }
    const reviews = Array.isArray(source.reviews) ? source.reviews : []
    for (const raw of reviews) consumeReview(asRecord(raw))
    const review = asRecord(source.review) || source
    const candidate = asRecord(review.candidate) || asRecord(source.candidate)
    const ingestPayload = asRecord(source.ingest_payload) || asRecord(review.ingest_payload)
    const decision = normalizeSourceCandidateDecision(source.decision || review.decision)
    const key = normalizeSourceCandidateKey(candidate) || normalizeSourceCandidateKey(ingestPayload)
    if (!decision || !key) return
    upsertDecision(key, {
      reviewDecision: decision,
      reviewReason: safeDisplay((review.reason || source.reason) as string | number | boolean | null, ''),
      reviewNextGate: safeDisplay((review.next_gate || source.next_gate) as string | number | boolean | null, ''),
      reviewedAt: safeDisplay((review.reviewed_at || source.reviewed_at || source.updated_at) as string | number | boolean | null, ''),
    })
  }

  const consumeTaskEvent = (source: UnknownRecord | null) => {
    if (!source) return
    const events = Array.isArray(source.task_events) ? source.task_events : [source]
    for (const rawEvent of events) {
      const taskEvent = asRecord(rawEvent)
      if (!taskEvent) continue
      const result = asRecord(taskEvent.result)
      const dispatchResult = asRecord(result?.dispatch_result) || asRecord(result)
      const effectivePayload = asRecord(dispatchResult?.effective_payload) || asRecord(result?.effective_payload)
      const key = normalizeSourceCandidateKey(taskEvent) || normalizeSourceCandidateKey(effectivePayload) || normalizeSourceCandidateKey(result)
      if (!key) continue
      const status = safeDisplay(taskEvent.status as string | number | boolean | null, '')
      upsertDecision(key, {
        reviewDecision: status.toLowerCase() === 'failed' ? 'deferred' : 'approved',
        reviewTaskId: safeDisplay((taskEvent.task_id || dispatchResult?.task_id || result?.task_id) as string | number | boolean | null, ''),
        reviewNextGate: status
          ? formatCatalogTemplate(translate(locale, 'agentChat.source.nextGate.urlPool'), { status })
          : 'inspect_ingest_status_or_source_artifacts',
        reviewedAt: safeDisplay((taskEvent.recorded_at || taskEvent.updated_at || result?.recorded_at) as string | number | boolean | null, ''),
      })
    }
  }

  const consumeSubmission = (source: UnknownRecord | null) => {
    if (!source) return
    const historySessions = Array.isArray(source.sessions) ? source.sessions : []
    for (const rawSession of historySessions) {
      const session = asRecord(rawSession)
      if (!session) continue
      consumeTaskEvent(session)
      const submissions = Array.isArray(session.submissions) ? session.submissions : []
      for (const rawSubmission of submissions) consumeSubmission(asRecord(rawSubmission))
    }
    const nestedSubmission = asRecord(source.submission)
    if (nestedSubmission) consumeSubmission(nestedSubmission)
    const submissions = Array.isArray(source.submissions) ? source.submissions : []
    for (const raw of submissions) consumeSubmission(asRecord(raw))
    consumeTaskEvent(source)
    const dispatchResult = asRecord(source.dispatch_result) || source
    const taskEvents = Array.isArray(source.task_events) ? source.task_events : []
    const latestTaskEvent = asRecord(taskEvents[taskEvents.length - 1]) || {}
    const latestTaskStatus = safeDisplay((source.latest_task_status || latestTaskEvent.status) as string | number | boolean | null, '')
    const key = normalizeSourceCandidateKey(source) || normalizeSourceCandidateKey(asRecord(dispatchResult?.effective_payload))
    if (!key) return
    upsertDecision(key, {
      reviewDecision: 'approved',
      reviewTaskId: safeDisplay((source.task_id || latestTaskEvent.task_id || dispatchResult?.task_id) as string | number | boolean | null, ''),
      reviewNextGate: latestTaskStatus
        ? formatCatalogTemplate(translate(locale, 'agentChat.source.nextGate.urlPool'), { status: latestTaskStatus })
        : safeDisplay(source.next_gate as string | number | boolean | null, 'inspect_ingest_status_or_source_artifacts'),
      reviewedAt: safeDisplay((latestTaskEvent.recorded_at || source.latest_task_event_at || source.submitted_at || source.updated_at) as string | number | boolean | null, ''),
    })
  }

  for (const event of events) {
    const structured = getEventStructuredContent(event)
    consumeReview(structured)
    consumeSubmission(structured)
  }
  for (const call of calls) {
    const result = asRecord(call.result)
    consumeReview(result)
    consumeSubmission(result)
  }
  for (const artifact of artifacts) {
    const rawArtifact = artifact as unknown as UnknownRecord
    const content = asRecord(rawArtifact.content_json)
      || parseJsonRecord(String(rawArtifact.content_text || artifact.content || ''))
      || asRecord(artifact.metadata)
    if (artifact.name === TECHNICAL_TEXT.sourceCandidateReviewsArtifact.value || content?.contract_version === TECHNICAL_TEXT.sourceCandidateReviewContract.value) consumeReview(content)
    if (artifact.name === TECHNICAL_TEXT.ingestUrlPoolSubmissionsArtifact.value || content?.contract_version === TECHNICAL_TEXT.ingestUrlPoolSubmitContract.value) consumeSubmission(content)
  }
  return decisions
}

function buildWritingDiffCards(locale: AppLocale, events: AgentEventItem[], calls: AgentChatCapabilityCall[]): WritingDiffCard[] {
  const cardsByKey = new Map<string, WritingDiffCard>()
  const consume = (source: UnknownRecord | null, keyPrefix: string, toolName = '') => {
    const diff = asRecord(source?.diff)
    if (!diff) return
    const key = joinWithColon([
      toolName || safeDisplay(source?.tool_name as string | number | boolean | null, 'writing'),
      safeDisplay(source?.doc_id as string | number | boolean | null),
      safeDisplay(source?.operation as string | number | boolean | null),
    ])
    cardsByKey.set(key, {
      key: key || keyPrefix,
      toolName: toolName || safeDisplay(source?.tool_name as string | number | boolean | null, translate(locale, 'agentChat.writing.fallback.toolName')),
      operation: safeDisplay(source?.operation as string | number | boolean | null),
      added: typeof diff.added_lines === 'number' ? diff.added_lines : null,
      removed: typeof diff.removed_lines === 'number' ? diff.removed_lines : null,
      docId: safeDisplay(source?.doc_id as string | number | boolean | null),
      summary: safeDisplay(source?.model_summary as string | number | boolean | null, translate(locale, 'agentChat.writing.fallback.summary')),
    })
  }
  for (const event of events) consume(getEventStructuredContent(event), getAgentEventKey(event), getEventToolName(event))
  for (const [index, call] of calls.entries()) consume(asRecord(call.result), joinWithHyphen(['call', call.call_id || index]), call.tool_name || call.capability_id || '')
  return Array.from(cardsByKey.values()).slice(-5).reverse()
}

function buildInvestigationTraceCards(locale: AppLocale, events: AgentEventItem[], calls: AgentChatCapabilityCall[]): InvestigationTraceCard[] {
  const cardsByKey = new Map<string, InvestigationTraceCard>()
  const consume = (source: UnknownRecord | null, keyPrefix: string) => {
    if (!source) return
    const contract = String(source.contract_version || '')
    const counts = asRecord(source.counts)
    if (contract !== TECHNICAL_TEXT.investigationTraceContract.value && !counts?.nodes && !source.focus_node_id) return
    const pending = Array.isArray(source.pending_questions) ? source.pending_questions.map((item) => asRecord(item)).filter(Boolean) : []
    const firstPending = pending[0] || null
    const focus = safeDisplay(source.focus_node_id as string | number | boolean | null, translate(locale, 'agentChat.investigation.fallback.focus'))
    const key = joinWithColon([focus, safeDisplay(source.artifact_name as string | number | boolean | null, keyPrefix)])
    cardsByKey.set(key, {
      key,
      focus,
      nodeCount: safeDisplay(counts?.nodes as string | number | boolean | null, '0'),
      edgeCount: safeDisplay(counts?.edges as string | number | boolean | null, '0'),
      summary: safeDisplay(source.trace_summary as string | number | boolean | null, translate(locale, 'agentChat.investigation.fallback.summary')),
      pendingQuestion: safeDisplay((firstPending?.text || firstPending?.question || firstPending?.title) as string | number | boolean | null, ''),
    })
  }
  for (const event of events) consume(getEventStructuredContent(event), getAgentEventKey(event))
  for (const [index, call] of calls.entries()) consume(asRecord(call.result), joinWithHyphen(['call', call.call_id || index]))
  return Array.from(cardsByKey.values()).slice(-4).reverse()
}

function parseJsonRecord(value: unknown): UnknownRecord | null {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    return asRecord(JSON.parse(value))
  } catch {
    return null
  }
}

function getLongTaskState(source: UnknownRecord | null): UnknownRecord | null {
  if (!source) return null
  const directContract = String(source.contract_version || '')
  if (directContract === TECHNICAL_TEXT.longTaskStageContract.value && asRecord(source.state)) return asRecord(source.state)
  if (directContract === TECHNICAL_TEXT.longTaskStageContract.value && source.current_stage) return source
  const state = asRecord(source.state)
  if (state && (state.current_stage || state.stage_summaries || state.completed_stages)) return state
  const resultPayload = asRecord(source.result_payload)
  const resultState = asRecord(resultPayload?.long_task_stage_state)
  if (resultState) return resultState
  const metadata = asRecord(source.metadata)
  const metadataState = asRecord(metadata?.long_task_stage_state)
  if (metadataState) return metadataState
  return null
}

function listLongTaskStages(state: UnknownRecord) {
  return Array.isArray(state.stage_summaries)
    ? state.stage_summaries.map((item) => asRecord(item)).filter((item): item is UnknownRecord => Boolean(item))
    : []
}

function buildLongTaskStageCards(
  locale: AppLocale,
  events: AgentEventItem[],
  calls: AgentChatCapabilityCall[],
  artifacts: AgentArtifactItem[],
  tasks: AgentTaskItem[],
): LongTaskStageCard[] {
  const cardsByKey = new Map<string, LongTaskStageCard>()
  const consume = (source: UnknownRecord | null, keyPrefix: string) => {
    const state = getLongTaskState(source)
    if (!state) return
    const stages = listLongTaskStages(state)
    const completed = toTextList(state.completed_stages)
    const lastCompleted = [...stages].reverse().find((stage) => String(stage.status || '').toLowerCase() === 'completed')
    const currentStage = safeDisplay(state.current_stage as string | number | boolean | null, 'plan')
    const lastStage = safeDisplay((lastCompleted?.stage || stages[0]?.stage) as string | number | boolean | null, currentStage)
    const counts = stages.reduce<CountMap>((acc, stage) => {
      const stageCounts = asRecord(stage.counts)
      for (const [key, value] of Object.entries(stageCounts || {})) {
        const numeric = typeof value === 'number' ? value : Number(value || 0)
        if (Number.isFinite(numeric) && numeric > 0) acc[key] = Math.max(acc[key] || 0, numeric)
      }
      return acc
    }, {})
    const countBits = [
      counts?.evidence_refs ? formatCatalogTemplate(translate(locale, 'agentChat.longTask.counter.evidenceRefs'), { count: counts.evidence_refs }) : '',
      counts?.gap_list ? formatCatalogTemplate(translate(locale, 'agentChat.longTask.counter.gapList'), { count: counts.gap_list }) : '',
      counts?.external_discovery_plan ? formatCatalogTemplate(translate(locale, 'agentChat.longTask.counter.externalDiscoveryPlan'), { count: counts.external_discovery_plan }) : '',
      counts?.source_intake ? formatCatalogTemplate(translate(locale, 'agentChat.longTask.counter.sourceIntake'), { count: counts.source_intake }) : '',
      counts?.clue_refs ? formatCatalogTemplate(translate(locale, 'agentChat.longTask.counter.clueRefs'), { count: counts.clue_refs }) : '',
      counts?.draft_refs ? formatCatalogTemplate(translate(locale, 'agentChat.longTask.counter.draftRefs'), { count: counts.draft_refs }) : '',
    ].filter(Boolean)
    const nextActions = toTextList(state.next_actions)
    const artifactName = safeDisplay(
      source?.artifact_name as string | number | boolean | null,
      safeDisplay(state.artifact_name as string | number | boolean | null, translate(locale, 'agentChat.longTask.fallback.artifactName')),
    )
    const key = joinWithColon([artifactName, currentStage, completed.join('|') || keyPrefix])
    cardsByKey.set(key, {
      key,
      currentStage,
      completed: completed.length ? completed.join(' -> ') : translate(locale, 'agentChat.longTask.none'),
      lastStage,
      summary: safeDisplay((lastCompleted?.summary || stages[0]?.summary || state.summary) as string | number | boolean | null, translate(locale, 'agentChat.longTask.fallback.summary')),
      counts: joinWithMiddleDot(countBits) || translate(locale, 'agentChat.longTask.noCounters'),
      nextAction: nextActions[nextActions.length - 1] || '',
    })
  }
  for (const event of events) consume(getEventStructuredContent(event), getAgentEventKey(event))
  for (const [index, call] of calls.entries()) consume(asRecord(call.result), joinWithHyphen(['call', call.call_id || index]))
  for (const artifact of artifacts) {
    if (String(artifact.artifact_type || '') !== 'agent_long_task_state') continue
    consume(parseJsonRecord(artifact.content) || asRecord(artifact.metadata), joinWithHyphen(['artifact', artifact.artifact_id]))
  }
  for (const task of tasks) consume(task as unknown as UnknownRecord, joinWithHyphen(['task', task.task_id]))
  return Array.from(cardsByKey.values()).slice(-4).reverse()
}

function getPrimaryArtifactText(artifact: AgentArtifactItem) {
  return artifact.summary || artifact.path || artifact.content || '-'
}

function formatArtifactPreview(artifact?: AgentArtifactItem | null) {
  if (!artifact) return ''
  const payload = artifact.content || artifact.summary || artifact.path || ''
  if (payload) return String(payload)
  return toCompactJson({
    artifact_id: artifact.artifact_id,
    type: artifact.artifact_type,
    name: artifact.name,
    status: artifact.status,
    metadata: artifact.metadata,
  })
}

function summarizeCapability(capability: AgentChatCapabilityItem) {
  const approval = safeDisplay(capability.approval_level)
  const concurrency = safeDisplay(capability.concurrency_class)
  const state = safeDisplay(capability.implementation_state || (capability.implemented === false ? 'unimplemented' : TECHNICAL_TEXT.readyState.value))
  return joinWithMiddleDot([state, approval, concurrency])
}

function summarizeCapabilityRuntime(capability: AgentChatCapabilityItem) {
  const bits = []
  if (capability.service_status) bits.push(joinWithColon(['status', capability.service_status]))
  if (typeof capability.configured === 'boolean') bits.push(joinWithColon(['configured', capability.configured ? 'yes' : 'no']))
  if (typeof capability.reachable === 'boolean') bits.push(joinWithColon(['reachable', capability.reachable ? 'yes' : 'no']))
  if (typeof capability.auth_ok === 'boolean') bits.push(joinWithColon(['auth', capability.auth_ok ? 'ok' : 'fail']))
  if (capability.server_error) bits.push(joinWithColon(['error', capability.server_error]))
  return joinWithMiddleDot(bits)
}

function capabilityImplementationState(capability: AgentChatCapabilityItem) {
  return String(capability.implementation_state || '').trim().toLowerCase()
}

function isCapabilityAvailable(capability: AgentChatCapabilityItem) {
  const state = capabilityImplementationState(capability)
  return capability.enabled !== false && capability.implemented !== false && !['disabled', 'not_configured', 'not_mounted', 'unimplemented', 'auth_failed', 'server_error', 'unreachable'].includes(state)
}

function flattenCapabilityGroups(groups: CapabilityGroupMap | null) {
  if (!groups) return []
  const items: AgentChatCapabilityItem[] = []
  for (const value of Object.values(groups)) {
    if (Array.isArray(value)) items.push(...value)
  }
  return items
}

function isAgentDebugMetaEnabled() {
  if (typeof window === 'undefined') return false
  try {
    const params = new URLSearchParams(window.location.search)
    const hashQuery = window.location.hash.includes('?') ? window.location.hash.split('?').slice(1).join('?') : ''
    const hashParams = new URLSearchParams(hashQuery)
    return params.get('agent_debug') === '1' || params.get('debug_agent') === '1' || hashParams.get('agent_debug') === '1' || hashParams.get('debug_agent') === '1'
  } catch {
    return false
  }
}

export default function AgentChatPage({ projectKey }: AgentChatPageProps) {
  const locale = useAppLocale()
  const t = useCallback((key: MessageKey) => translate(locale, key), [locale])
  const storageKey = joinWithColon([AGENT_CHAT_STORAGE_PREFIX, projectKey || 'default'])
  const stored = readStoredState(storageKey)
  const initialSessions = mergeSessionsWithSeed(locale, stored?.sessions, stored?.sessionHistories)
  const initialHistories = mergeHistoriesWithSeed(projectKey, locale, stored?.sessionHistories)

  const [sessionFilter, setSessionFilter] = useState('')
  const [activeSessionId, setActiveSessionId] = useState(stored?.activeSessionId || initialSessions[0]?.id || 's1')
  const [sessions, setSessions] = useState((): ChatSession[] => initialSessions)
  const [sessionHistories, setSessionHistories] = useState((): ChatHistoryMap => initialHistories)
  const [draftBySession, setDraftBySession] = useState((): StringMap => stored?.draftBySession || {})
  const [streamStatus, setStreamStatus] = useState((): AgentSessionEventStreamStatus => 'idle')
  const [streamEvents, setStreamEvents] = useState((): AgentEventItem[] => [])
  const [runStateBySession, setRunStateBySession] = useState((): SessionRunStateMap => ({}))
  const [selectedArtifactId, setSelectedArtifactId] = useState(null as string | null)
  const [workbenchView, setWorkbenchView] = useState((): WorkbenchView => 'overview')
  const [sourceHistoryFilter, setSourceHistoryFilter] = useState((): SourceHistoryFilter => 'all')
  const [approvalOverrideById, setApprovalOverrideById] = useState((): StringMap => ({}))
  const [approvalErrorById, setApprovalErrorById] = useState((): StringMap => ({}))
  const listRef = useRef(null as HTMLDivElement | null)
  const streamRefreshTimerRef = useRef(null as number | null)
  const turnStreamEventsRef = useRef([] as AgentEventItem[])
  const refetchBackendSessionRef = useRef(refetchNoop)
  const activeSessionIdRef = useRef(activeSessionId)
  const showDebugMeta = useMemo(() => isAgentDebugMetaEnabled(), [])

  const resolvedActiveSessionId = useMemo(
    () => (sessions.some((session) => session.id === activeSessionId) ? activeSessionId : sessions[0]?.id || activeSessionId),
    [activeSessionId, sessions],
  )
  useEffect(() => {
    activeSessionIdRef.current = resolvedActiveSessionId
  }, [resolvedActiveSessionId])
  const activeMessages = useMemo(() => sessionHistories[resolvedActiveSessionId] || [], [resolvedActiveSessionId, sessionHistories])
  const sessionStats = useMemo(() => {
    const entries = Object.entries(sessionHistories).map(([sessionId, msgs]) => {
      const last = msgs[msgs.length - 1]
      const preview = last?.content?.replace(/\s+/g, ' ').slice(0, 44) || t('agentChat.session.emptyPreview')
      return {
        sessionId,
        count: msgs.length,
        preview,
      }
    })
    return Object.fromEntries(entries.map((item) => [item.sessionId, item])) as SessionStatsMap
  }, [sessionHistories, t])
  const activeSession = useMemo(
    () => sessions.find((session) => session.id === resolvedActiveSessionId) || sessions[0],
    [sessions, resolvedActiveSessionId],
  )
  const activeBackendSessionId = activeSession?.backendSessionId || null
  const backendSessionQuery = useQuery({
    queryKey: ['agent-session', projectKey, activeBackendSessionId],
    queryFn: () => getAgentSession(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    refetchInterval: activeBackendSessionId ? 3000 : false,
    retry: false,
  })
  const backendTaskQuery = useQuery({
    queryKey: ['agent-session-tasks', projectKey, activeBackendSessionId],
    queryFn: () => listAgentSessionTasks(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    refetchInterval: activeBackendSessionId ? 3000 : false,
    retry: false,
  })
  const backendEventQuery = useQuery({
    queryKey: ['agent-session-events', projectKey, activeBackendSessionId],
    queryFn: () => listAgentSessionEvents(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    refetchInterval: activeBackendSessionId ? 3000 : false,
    retry: false,
  })
  const backendArtifactQuery = useQuery({
    queryKey: ['agent-session-artifacts', projectKey, activeBackendSessionId],
    queryFn: () => listAgentSessionArtifacts(activeBackendSessionId || ''),
    enabled: Boolean(activeBackendSessionId),
    refetchInterval: activeBackendSessionId ? 3000 : false,
    retry: false,
  })
  const agentCapabilityQuery = useQuery({
    queryKey: ['agent-chat-capabilities', projectKey],
    queryFn: () => listAgentChatCapabilities(projectKey || null),
    staleTime: 60_000,
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
  const messageCountLabel = useMemo(
    () => formatCatalogTemplate(t('agentChat.session.messageCount'), { count: activeMessages.length }),
    [activeMessages.length, t],
  )
  const quickCommands = useMemo(
    () => AGENT_CHAT_QUICK_COMMAND_KEYS.map((key) => t(key)),
    [t],
  )
  const currentDraft = draftBySession[resolvedActiveSessionId] || ''
  const activeRunState = runStateBySession[resolvedActiveSessionId]
  const isActiveSessionRunning = Boolean(activeRunState?.pending)
  const backendSessionStatus = String(
    ((backendSessionQuery.data as unknown as { session?: { status?: string } })?.session?.status || backendSessionQuery.data?.status || ''),
  )
  const shouldOpenSessionStream = Boolean(
    activeBackendSessionId && (isActiveSessionRunning || !backendSessionStatus || !isTerminalAgentSessionStatus(backendSessionStatus)),
  )
  const runningSessionCount = useMemo(
    () => Object.values(runStateBySession).filter((state) => state?.pending).length,
    [runStateBySession],
  )
  const refetchBackendSession = useCallback(async () => {
    await Promise.all([
      backendSessionQuery.refetch(),
      backendTaskQuery.refetch(),
      backendEventQuery.refetch(),
      backendArtifactQuery.refetch(),
    ])
  }, [backendArtifactQuery, backendEventQuery, backendSessionQuery, backendTaskQuery])
  useEffect(() => {
    refetchBackendSessionRef.current = refetchBackendSession
  }, [refetchBackendSession])
  const runAgentTurnForSession = useCallback(
    async (input: { command: string; sessionId: string; backendSessionId?: string | null }): Promise<{ result: AgentChatTurnResult; events: AgentEventItem[] }> => {
      const payload = {
        message: input.command,
        project_key: projectKey || null,
        session_id: input.backendSessionId || null,
        enable_model_tool_loop: true,
        require_high_risk_approval: false,
      }
      let sessionEvents: AgentEventItem[] = []
      let streamedAnswer = ''
      let lastProgressText = ''
      const updateStatus = (status: AgentSessionEventStreamStatus) => {
        setRunStateBySession((prev) => ({
          ...prev,
          [input.sessionId]: {
            ...(prev[input.sessionId] || { pending: true }),
            pending: true,
            backendSessionId: input.backendSessionId || null,
            streamStatus: status,
            lastEventAt: Date.now(),
          },
        }))
        if (activeSessionIdRef.current === input.sessionId) {
          setStreamStatus(status)
        }
      }
      const updateLoadingMessage = (content: string) => {
        setSessionHistories((prev) => {
          const sessionMessages = prev[input.sessionId] || []
          return {
            ...prev,
            [input.sessionId]: sessionMessages.map((message) =>
              message.id.startsWith('a-loading-')
                ? {
                    ...message,
                    content,
                    stages: buildStreamingStages(locale),
                  }
                : message,
            ),
          }
        })
      }
      const recordEvent = (event: AgentEventItem) => {
        sessionEvents = mergeAgentEvents(sessionEvents, [event]).slice(-120)
        if (activeSessionIdRef.current === input.sessionId) {
          turnStreamEventsRef.current = sessionEvents
          setStreamEvents(sessionEvents)
        }
        setRunStateBySession((prev) => ({
          ...prev,
          [input.sessionId]: {
            ...(prev[input.sessionId] || { pending: true }),
            pending: true,
            backendSessionId: input.backendSessionId || null,
            lastEventAt: Date.now(),
          },
        }))
        const chunk = extractAssistantStreamChunk(event)
        if (chunk) {
          streamedAnswer = chunk.mode === 'append' ? streamedAnswer + chunk.text : chunk.text
          updateLoadingMessage(streamedAnswer || translate(locale, 'agentChat.status.thinking'))
          return
        }
        if (streamedAnswer.trim()) return
        const progressText = extractProgressiveStreamText(locale, event)
        if (!progressText || progressText === lastProgressText) return
        lastProgressText = progressText
        updateLoadingMessage(progressText)
      }
      if (activeSessionIdRef.current === input.sessionId) {
        setStreamEvents([])
        turnStreamEventsRef.current = []
      }
      try {
        const result = await runAgentChatTurnStreaming(payload, {
          onStatus: updateStatus,
          onEvent: recordEvent,
          onFinalAnswer: (answer) => {
            const text = String(answer || '').trim()
            if (!text) return
            streamedAnswer = text
            updateLoadingMessage(text)
          },
        })
        return { result, events: sessionEvents }
      } catch {
        updateStatus('error')
        const result = await runAgentChatTurn(payload)
        return { result, events: sessionEvents }
      }
    },
    [locale, projectKey],
  )
  const coordinatorMutation = useMutation({
    mutationFn: (sessionId: string) => runAgentSessionCoordinatorPass(sessionId),
    onSuccess: () => {
      void refetchBackendSession()
    },
  })
  const retryTaskMutation = useMutation({
    mutationFn: (input: { sessionId: string; taskId: string }) =>
      retryAgentSessionTask(input.sessionId, { task_id: input.taskId }),
    onSuccess: () => {
      void refetchBackendSession()
    },
  })
  const cancelSessionMutation = useMutation({
    mutationFn: (sessionId: string) => cancelAgentSession(sessionId),
    onSuccess: () => {
      void refetchBackendSession()
    },
  })
  const continueApprovalMutation = useMutation({
    mutationFn: (input: { approvalId: string; bindingPayloadOverrides?: UnknownRecord }) =>
      continueAgentChatApproval(input.approvalId, {
        approved_by: 'user',
        binding_payload_overrides: input.bindingPayloadOverrides || {},
      }),
    onSuccess: (result) => {
      const finalAnswer = String(result?.final_answer || '').trim()
      const capabilityCall =
        result?.capability_call && typeof result.capability_call === 'object'
          ? (result.capability_call as AgentChatCapabilityCall)
          : null
      if (finalAnswer || capabilityCall) {
        setSessionHistories((prev) => ({
          ...prev,
          [resolvedActiveSessionId]: [
            ...(prev[resolvedActiveSessionId] || []),
            {
              id: runtimeId('a-approval'),
              role: 'assistant',
              content: finalAnswer || t('agentChat.approval.approvedContinue'),
              ts: nowLabel(),
              stages: buildCompletedStages(locale),
              meta: showDebugMeta ? [debugMeta('backend', TECHNICAL_TEXT.approvalContinueBackend.value)] : [],
              capabilityCalls: capabilityCall ? [capabilityCall] : [],
            },
          ],
        }))
      }
      void refetchBackendSession()
    },
  })
  const rejectApprovalMutation = useMutation({
    mutationFn: (approvalId: string) => resolveAgentApproval(approvalId, { approved: false }),
    onSuccess: (approval) => {
      setSessionHistories((prev) => ({
        ...prev,
        [resolvedActiveSessionId]: [
          ...(prev[resolvedActiveSessionId] || []),
          {
            id: runtimeId('a-reject'),
            role: 'assistant',
            content: approval?.approval_id
              ? formatCatalogTemplate(t('agentChat.approval.rejectedWithId'), { approvalId: approval.approval_id })
              : t('agentChat.approval.rejected'),
            ts: nowLabel(),
            stages: buildCompletedStages(locale),
            meta: showDebugMeta ? [debugMeta('backend', TECHNICAL_TEXT.approvalResolveBackend.value), debugMeta('approval', 'rejected')] : [],
          },
        ],
      }))
      void refetchBackendSession()
    },
  })

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [activeMessages, isActiveSessionRunning, resolvedActiveSessionId])

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

  useEffect(() => {
    setStreamEvents([])
    if (!activeBackendSessionId || !shouldOpenSessionStream) {
      setStreamStatus('idle')
      return undefined
    }
    const scheduleRefresh = () => {
      if (streamRefreshTimerRef.current != null) window.clearTimeout(streamRefreshTimerRef.current)
      streamRefreshTimerRef.current = window.setTimeout(() => {
        void refetchBackendSessionRef.current()
      }, 180)
    }
    const close = openAgentSessionEventStream(
      activeBackendSessionId,
      {
        onStatus: setStreamStatus,
        onEvent: (event) => {
          setStreamEvents((prev) => mergeAgentEvents(prev, [event]).slice(-120))
          scheduleRefresh()
        },
        onError: () => {
          scheduleRefresh()
        },
      },
      { sinceSeq: 0, pollSeconds: 1, maxSeconds: 180 },
    )
    return () => {
      if (streamRefreshTimerRef.current != null) {
        window.clearTimeout(streamRefreshTimerRef.current)
        streamRefreshTimerRef.current = null
      }
      close()
    }
  }, [activeBackendSessionId, shouldOpenSessionStream])

  const createSession = (seedCommand?: string) => {
    const nextId = buildSessionId()
    const title = buildSessionTitle(seedCommand, locale)
    const nextSession: ChatSession = {
      id: nextId,
      title,
      updatedAt: t('agentChat.session.updatedNow'),
    }
    setSessions((prev) => [nextSession, ...prev])
    setSessionHistories((prev) => ({
      ...prev,
      [nextId]: [
        buildSystemMessage(
          projectKey,
          locale,
          seedCommand
            ? formatCatalogTemplate(t('agentChat.system.newSessionCreated'), { command: seedCommand })
            : undefined,
        ),
      ],
    }))
    setDraftBySession((prev) => ({
      ...prev,
      [nextId]: seedCommand || '',
    }))
    setActiveSessionId(nextId)
  }

  const sendMessage = async (raw: string, options?: { sessionId?: string | null }) => {
    const command = raw.trim()
    const targetSessionId = options?.sessionId && sessions.some((session) => session.id === options.sessionId) ? options.sessionId : resolvedActiveSessionId
    if (!command || runStateBySession[targetSessionId]?.pending) return
    const targetSession = sessions.find((session) => session.id === targetSessionId) || activeSession
    if (targetSessionId !== resolvedActiveSessionId) setActiveSessionId(targetSessionId)
    const timestamp = Date.now()

    setSessionHistories((prev) => ({
      ...prev,
      [targetSessionId]: [
        ...(prev[targetSessionId] || []),
        {
          id: runtimeId('u'),
          role: 'user',
          content: command,
          ts: nowLabel(),
        },
        {
          id: joinWithHyphen(['a', 'loading', timestamp]),
          role: 'assistant',
          content: t('agentChat.status.thinking'),
          ts: nowLabel(),
          stages: buildBaseStages(locale),
        },
      ],
    }))
    setSessions((prev) => prev.map((session) => (session.id === targetSessionId ? { ...session, updatedAt: t('agentChat.session.updatedNow') } : session)))
    setDraftBySession((prev) => ({
      ...prev,
      [targetSessionId]: '',
    }))
    setRunStateBySession((prev) => ({
      ...prev,
      [targetSessionId]: {
        pending: true,
        backendSessionId: targetSession?.backendSessionId || null,
        streamStatus: 'connecting',
        startedAt: Date.now(),
        lastEventAt: Date.now(),
      },
    }))
    if (targetSessionId === activeSessionIdRef.current) {
      setStreamStatus('connecting')
      setStreamEvents([])
      turnStreamEventsRef.current = []
    }

    try {
      const { result, events } = await runAgentTurnForSession({
        command,
        sessionId: targetSessionId,
        backendSessionId: targetSession?.backendSessionId || null,
      })
      const loopResult = result?.loop_result && typeof result.loop_result === 'object' ? (result.loop_result as UnknownRecord) : {}
      const parsed = (loopResult?.parsed as UnknownRecord | undefined) || null
      const submit = (loopResult?.submit as UnknownRecord | undefined) || null
      const capabilityCalls = Array.isArray(result?.capability_calls) ? result.capability_calls : []
      const suggestedNextActions = Array.isArray(result?.suggested_next_actions) ? result.suggested_next_actions : []
      const agentMode = String(result?.agent_mode || '').trim()
      const backendSessionId = String(result?.session?.session_id || '')
      const backendRootTaskId = String(result?.session?.root_task_id || '')
      const backendCurrentPhase = String(result?.session?.current_phase || '')
      const backendCompatMode = typeof result?.session?.compat_mode === 'boolean' ? result.session.compat_mode : null
      const backendProjectionVersion = String(result?.contract_version || result?.session?.compat_projection_version || '')
      const meta: string[] = [debugMeta('backend', TECHNICAL_TEXT.agentChatTurnBackend.value)]
      if (agentMode) meta.push(debugMeta('mode', agentMode))
      if (submit?.job_id) meta.push(debugMeta('job_id', String(submit.job_id)))
      if (submit?.status) meta.push(debugMeta('status', String(submit.status)))
      if (backendSessionId) meta.push(debugMeta('session_id', backendSessionId))
      if (result?.stream?.url) meta.push(debugMeta('stream', TECHNICAL_TEXT.readyState.value))
      if (backendCurrentPhase) meta.push(debugMeta('phase', backendCurrentPhase))
      if (typeof submit?.accepted_count === 'number') meta.push(debugMeta('accepted', submit.accepted_count))
      if (typeof submit?.rejected_count === 'number') meta.push(debugMeta('rejected', submit.rejected_count))
      if (capabilityCalls.length) meta.push(debugMeta('capability', capabilityCalls.map((call) => call.capability_id).filter(Boolean).join(', ')))

      const parsedJson = toCompactJson(parsed)
      const finalAnswer = String(result?.final_answer || '').trim()
      const assistantContent = parsedJson
        ? joinWithSeparator([finalAnswer || t('agentChat.message.defaultAssistantComplete'), TECHNICAL_TEXT.parsedDetailPrefix.value + parsedJson], '\n\n').trim()
        : (finalAnswer || t('agentChat.message.defaultAssistantComplete'))
      const visibleMeta = showDebugMeta ? meta : []

      setSessionHistories((prev) => {
        const sessionMessages = prev[targetSessionId] || []
        const withoutLoading = sessionMessages.filter((msg) => !msg.id.startsWith('a-loading-'))
        return {
          ...prev,
          [targetSessionId]: [
            ...withoutLoading,
            {
              id: runtimeId('a'),
              role: 'assistant',
              content: assistantContent,
              ts: nowLabel(),
              stages: buildCompletedStages(locale),
              meta: visibleMeta,
              capabilityCalls,
              agentTasks: Array.isArray(result?.tasks) ? result.tasks : [],
              agentEvents: events,
              suggestedNextActions,
              agentMode,
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
                  updatedAt: t('agentChat.session.updatedNow'),
                }
              : session,
          ),
        )
      }
      setRunStateBySession((prev) => ({
        ...prev,
        [targetSessionId]: {
          ...(prev[targetSessionId] || { pending: true }),
          pending: false,
          streamStatus: 'closed',
          lastEventAt: Date.now(),
        },
      }))
      if (targetSessionId === activeSessionIdRef.current) {
        setStreamStatus('closed')
      }
    } catch (error) {
      if (targetSessionId === activeSessionIdRef.current) {
        setStreamStatus('error')
      }
      const errorText = formatBackendError(error)
      setSessionHistories((prev) => {
        const sessionMessages = prev[targetSessionId] || []
        const withoutLoading = sessionMessages.filter((msg) => !msg.id.startsWith('a-loading-'))
        return {
          ...prev,
          [targetSessionId]: [
            ...withoutLoading,
            {
              id: runtimeId('sys-error'),
              role: 'system',
              state: 'error',
              content: joinWithSeparator([t('agentChat.message.backendCallFailed'), debugMeta('error', errorText)], '\n\n'),
              ts: nowLabel(),
              stages: buildPendingStages(locale),
              meta: showDebugMeta ? [debugMeta('backend', TECHNICAL_TEXT.agentChatTurnBackend.value), debugMeta('status', 'failed')] : [],
              retryCommand: command,
              retrySessionId: targetSessionId,
            },
          ],
        }
      })
    } finally {
      setRunStateBySession((prev) => {
        const current = prev[targetSessionId]
        if (!current) return prev
        return {
          ...prev,
          [targetSessionId]: {
            ...current,
            pending: false,
            streamStatus: current.streamStatus === 'error' ? 'error' : 'closed',
            lastEventAt: Date.now(),
          },
        }
      })
    }
  }

  const clearCurrentSession = () => {
    const targetSessionId = resolvedActiveSessionId
    setSessionHistories((prev) => ({
      ...prev,
      [targetSessionId]: [buildSystemMessage(projectKey, locale)],
    }))
    setDraftBySession((prev) => ({
      ...prev,
      [targetSessionId]: '',
    }))
    setSessions((prev) =>
      prev.map((session) =>
        session.id === targetSessionId
          ? {
              ...session,
              updatedAt: t('agentChat.session.updatedNow'),
              backendSessionId: null,
              backendRootTaskId: null,
              backendCurrentPhase: null,
              backendCompatMode: null,
              backendProjectionVersion: null,
            }
          : session,
      ),
    )
    setStreamEvents([])
    setSelectedArtifactId(null)
    setStreamStatus('idle')
    setRunStateBySession((prev) => ({
      ...prev,
      [targetSessionId]: {
        ...(prev[targetSessionId] || {}),
        pending: false,
        streamStatus: 'idle',
      },
    }))
  }

  const refreshBackendSession = refetchBackendSession

  const sessionTasks = useMemo(
    () => mergeAgentTasks(Array.isArray(backendTaskQuery.data) ? backendTaskQuery.data : [], latestMessageTasks(activeMessages)),
    [activeMessages, backendTaskQuery.data],
  )
  const sessionEvents = useMemo(
    () => mergeAgentEvents(mergeAgentEvents(Array.isArray(backendEventQuery.data) ? backendEventQuery.data : [], latestMessageEvents(activeMessages)), streamEvents),
    [activeMessages, backendEventQuery.data, streamEvents],
  )
  const sessionArtifacts = useMemo(() => (Array.isArray(backendArtifactQuery.data) ? backendArtifactQuery.data : []), [backendArtifactQuery.data])
  const sessionApprovals = useMemo(() => {
    const data = backendSessionQuery.data as unknown as { approvals?: AgentApprovalItem[] | null }
    return Array.isArray(data?.approvals) ? data.approvals : []
  }, [backendSessionQuery.data])
  const pendingApprovals = useMemo(
    () => sessionApprovals.filter((approval) => String(approval.status || '').toLowerCase() === 'pending'),
    [sessionApprovals],
  )

  const sessionTelemetry = {
    sessionId:
      ((backendSessionQuery.data as unknown as { session?: { session_id?: string } })?.session?.session_id || backendSessionQuery.data?.session_id)
      || activeSession?.backendSessionId
      || null,
    currentPhase:
      ((backendSessionQuery.data as unknown as { session?: { current_phase?: string } })?.session?.current_phase || backendSessionQuery.data?.current_phase)
      || activeSession?.backendCurrentPhase
      || null,
    status: ((backendSessionQuery.data as unknown as { session?: { status?: string } })?.session?.status || backendSessionQuery.data?.status) || null,
    rootTaskId:
      ((backendSessionQuery.data as unknown as { session?: { root_task_id?: string } })?.session?.root_task_id || backendSessionQuery.data?.root_task_id)
      || activeSession?.backendRootTaskId
      || null,
    compatMode:
      typeof (backendSessionQuery.data as unknown as { session?: { compat_mode?: boolean } })?.session?.compat_mode === 'boolean'
        ? (backendSessionQuery.data as unknown as { session?: { compat_mode?: boolean } }).session?.compat_mode
        : typeof backendSessionQuery.data?.compat_mode === 'boolean'
          ? backendSessionQuery.data.compat_mode
        : activeSession?.backendCompatMode ?? null,
    projectionVersion:
      ((backendSessionQuery.data as unknown as { session?: { compat_projection_version?: string } })?.session?.compat_projection_version
        || backendSessionQuery.data?.compat_projection_version
        || activeSession?.backendProjectionVersion
        || null),
    goal: ((backendSessionQuery.data as unknown as { session?: { goal?: string } })?.session?.goal || backendSessionQuery.data?.goal) || null,
    tasks: safeCount(backendTaskQuery.data),
    events: sessionEvents.length,
    artifacts: safeCount(backendArtifactQuery.data),
    approvals: sessionApprovals.length,
  }
  const phaseIndex = useMemo(() => {
    const phase = String(sessionTelemetry.currentPhase || '').toLowerCase()
    if (phase === 'conversation' || phase === 'research' || phase === 'synthesis') return 0
    if (phase === 'implementation') return 1
    if (phase === 'verification') return 2
    if (String(sessionTelemetry.status || '').toLowerCase() === 'completed') return 2
    return activeBackendSessionId ? 0 : 0
  }, [activeBackendSessionId, sessionTelemetry.currentPhase, sessionTelemetry.status])
  const sessionStatusClass = normalizeStatusToken(sessionTelemetry.status)
  const streamedCapabilityCalls = useMemo(
    () =>
      sessionEvents
        .filter((event) =>
          [
            TECHNICAL_TEXT.interactiveToolCallRequested.value,
            TECHNICAL_TEXT.interactiveToolCallStarted.value,
            TECHNICAL_TEXT.interactiveToolCallResult.value,
            TECHNICAL_TEXT.interactiveCapabilityExecuted.value,
            TECHNICAL_TEXT.agentCoreToolCallRequested.value,
            TECHNICAL_TEXT.agentCoreToolCallStarted.value,
            TECHNICAL_TEXT.agentCoreToolResult.value,
            'tool_call_requested',
            'tool_call_started',
            'tool_call_result',
            'capability_executed',
            'tool_result',
          ].includes(String(event.event_type || '')),
        )
        .map(eventToCapabilityCall)
        .filter((call): call is AgentChatCapabilityCall => Boolean(call)),
    [sessionEvents],
  )
  const latestCapabilityCalls = useMemo(() => {
    let messageCalls: AgentChatCapabilityCall[] = []
    for (let index = activeMessages.length - 1; index >= 0; index -= 1) {
      const calls = activeMessages[index]?.capabilityCalls
      if (Array.isArray(calls) && calls.length) {
        messageCalls = calls
        break
      }
    }
    return mergeCapabilityCalls(messageCalls, streamedCapabilityCalls)
  }, [activeMessages, streamedCapabilityCalls])
  const progressiveToolEvents = useMemo(() => buildProgressiveToolEvents(locale, sessionEvents), [locale, sessionEvents])
  const sourceCandidateDecisions = useMemo(
    () => buildSourceCandidateDecisionMap(locale, sessionEvents, latestCapabilityCalls, sessionArtifacts),
    [latestCapabilityCalls, locale, sessionArtifacts, sessionEvents],
  )
  const sourceQualityCards = useMemo(
    () => buildSourceQualityCards(locale, sessionEvents, latestCapabilityCalls).map((card) => ({
      ...card,
      ...(sourceCandidateDecisions.get(card.key) || {}),
    })),
    [latestCapabilityCalls, locale, sessionEvents, sourceCandidateDecisions],
  )
  const sourceHistorySummary = useMemo(() => ({
    all: sourceQualityCards.length,
    open: sourceQualityCards.filter((card) => !card.reviewDecision).length,
    approved: sourceQualityCards.filter((card) => card.reviewDecision === 'approved').length,
    deferred: sourceQualityCards.filter((card) => card.reviewDecision === 'deferred').length,
    rejected: sourceQualityCards.filter((card) => card.reviewDecision === 'rejected').length,
  }), [sourceQualityCards])
  const visibleSourceQualityCards = useMemo(() => {
    if (sourceHistoryFilter === 'all') return sourceQualityCards
    if (sourceHistoryFilter === 'open') return sourceQualityCards.filter((card) => !card.reviewDecision)
    return sourceQualityCards.filter((card) => card.reviewDecision === sourceHistoryFilter)
  }, [sourceHistoryFilter, sourceQualityCards])
  const submitSourceCandidateDecision = (card: SourceQualityCard, decision: 'approved' | 'deferred' | 'rejected') => {
    const label = formatSourceCandidateDecision(locale, decision)
    const payload = {
      decision,
      preferred_ingest: decision === 'approved' ? 'url_pool' : 'manual',
      reason: formatCatalogTemplate(t('agentChat.source.decision.reason'), { decision: label }),
      idempotency_key: joinWithColon(['source-candidate', decision, card.key]),
      candidate: {
        ...card.rawCandidate,
        title: card.title,
        url: card.url,
        snippet: card.snippet,
        provider: card.provider,
      },
    }
    void sendMessage(formatCatalogTemplate(t('agentChat.source.decision.command'), {
      payload: TECHNICAL_TEXT.sourceCandidateReviewPayload.value + ': ' + JSON.stringify(payload),
    }))
  }
  const writingDiffCards = useMemo(
    () => buildWritingDiffCards(locale, sessionEvents, latestCapabilityCalls),
    [latestCapabilityCalls, locale, sessionEvents],
  )
  const investigationTraceCards = useMemo(
    () => buildInvestigationTraceCards(locale, sessionEvents, latestCapabilityCalls),
    [latestCapabilityCalls, locale, sessionEvents],
  )
  const longTaskStageCards = useMemo(
    () => buildLongTaskStageCards(locale, sessionEvents, latestCapabilityCalls, sessionArtifacts, sessionTasks),
    [latestCapabilityCalls, locale, sessionArtifacts, sessionEvents, sessionTasks],
  )
  const primaryPendingApproval = pendingApprovals[0] || null
  const latestArtifacts = sessionArtifacts.slice(-3).reverse()
  const selectedArtifact = useMemo(() => {
    if (!sessionArtifacts.length) return null
    return sessionArtifacts.find((artifact) => artifact.artifact_id === selectedArtifactId) || latestArtifacts[0] || sessionArtifacts[sessionArtifacts.length - 1]
  }, [latestArtifacts, selectedArtifactId, sessionArtifacts])
  const capabilityPool = agentCapabilityQuery.data?.tool_pool
  const capabilityGroups = capabilityPool?.groups || null
  const capabilityItems = useMemo(() => {
    if (Array.isArray(capabilityPool?.tools)) return capabilityPool.tools
    return Array.isArray(agentCapabilityQuery.data?.items) ? agentCapabilityQuery.data.items : []
  }, [agentCapabilityQuery.data?.items, capabilityPool?.tools])
  const coreCapabilities = useMemo(
    () => {
      const grouped = capabilityGroups && Array.isArray(capabilityGroups.core) ? capabilityGroups.core : null
      const source = grouped || capabilityItems.filter((item) => String(item.approval_level || '').toLowerCase() === 'none')
      return source.filter(isCapabilityAvailable).slice(0, 5)
    },
    [capabilityGroups, capabilityItems],
  )
  const governedCapabilities = useMemo(
    () => {
      const deferred = capabilityGroups && Array.isArray(capabilityGroups.deferred) ? capabilityGroups.deferred : []
      const governed = capabilityGroups && Array.isArray(capabilityGroups.governed) ? capabilityGroups.governed : []
      const source = deferred.length || governed.length
        ? [...deferred, ...governed]
        : capabilityItems.filter((item) => String(item.approval_level || '').toLowerCase() !== 'none')
      return source.filter(isCapabilityAvailable).slice(0, 4)
    },
    [capabilityGroups, capabilityItems],
  )
  const unavailableCapabilities = useMemo(
    () => {
      const source = capabilityGroups ? flattenCapabilityGroups(capabilityGroups) : capabilityItems
      return source
        .filter((item) => !isCapabilityAvailable(item))
        .slice(0, 6)
    },
    [capabilityGroups, capabilityItems],
  )
  const workbenchTimeline = useMemo(() => buildWorkbenchTimeline(locale, sessionEvents, sessionTasks), [locale, sessionEvents, sessionTasks])
  const sessionStatusToken = String(sessionTelemetry.status || '').toLowerCase()
  const isSessionTerminal = isTerminalAgentSessionStatus(sessionStatusToken)
  const isStreamLive = !isSessionTerminal && (streamStatus === 'open' || streamStatus === 'connecting')
  const runSignal = pendingApprovals.length
    ? {
        className: 'needs-approval',
        label: t('agentChat.status.approvalNeeded'),
        detail: formatCatalogTemplate(t('agentChat.status.approvalNeededDetail'), { count: pendingApprovals.length }),
      }
    : isActiveSessionRunning || isStreamLive
      ? {
          className: 'live',
          label: t('agentChat.status.live'),
          detail: formatCatalogTemplate(t('agentChat.status.streamDetail'), { status: activeRunState?.streamStatus || streamStatus }),
      }
      : sessionTelemetry.status
        ? { className: sessionStatusClass, label: safeDisplay(sessionTelemetry.status), detail: safeDisplay(sessionTelemetry.currentPhase) }
        : { className: 'idle', label: t('agentChat.status.idle'), detail: t('agentChat.status.idleDetail') }
  const runSignalIcon = pendingApprovals.length
    ? createElement(ShieldCheck, { size: 14 })
    : isStreamLive
      ? createElement(Radio, { size: 14 })
      : String(sessionTelemetry.status || '').toLowerCase() === 'completed'
        ? createElement(CheckCircle2, { size: 14 })
        : createElement(Bot, { size: 14 })
  const retryableTask = sessionTasks.find((task) => ['failed', 'blocked', 'expired'].includes(String(task.status || '').toLowerCase()))
  const actionBusy =
    coordinatorMutation.isPending
    || retryTaskMutation.isPending
    || cancelSessionMutation.isPending
    || continueApprovalMutation.isPending
    || rejectApprovalMutation.isPending
  const backendErrorText = backendSessionQuery.isError
    ? t('agentChat.error.backendSessionLoadFailed')
    : backendTaskQuery.isError
      ? t('agentChat.error.taskListLoadFailed')
      : backendEventQuery.isError
        ? t('agentChat.error.eventStreamLoadFailed')
        : backendArtifactQuery.isError
          ? t('agentChat.error.artifactLoadFailed')
          : agentCapabilityQuery.isError
            ? t('agentChat.error.capabilityCatalogLoadFailed')
            : ''
  const isConversationIdle = activeMessages.length <= 1 && !activeBackendSessionId && !isActiveSessionRunning
  const hasStreamingPlaceholder = activeMessages.some((message) => message.role === 'assistant' && message.id.startsWith('a-loading-'))
  const isThinking = isActiveSessionRunning && !hasStreamingPlaceholder
  const shouldShowWorkbenchSection = (view: WorkbenchView) => workbenchView === 'overview' || workbenchView === view

  const continueApproval = (approvalId: string) => {
    const rawOverride = String(approvalOverrideById[approvalId] || '').trim()
    if (!rawOverride) {
      setApprovalErrorById((prev) => ({ ...prev, [approvalId]: '' }))
      continueApprovalMutation.mutate({ approvalId })
      return
    }
    try {
      const parsed = JSON.parse(rawOverride) as UnknownRecord
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(t('agentChat.approval.invalidOverrideObject'))
      }
      setApprovalErrorById((prev) => ({ ...prev, [approvalId]: '' }))
      continueApprovalMutation.mutate({ approvalId, bindingPayloadOverrides: parsed })
    } catch {
      setApprovalErrorById((prev) => ({ ...prev, [approvalId]: t('agentChat.error.invalidApprovalJson') }))
    }
  }

  return (
    <div className="agent-chat-page" data-testid="agent-chat-page">
      <section className="agent-chat-layout">
        <aside className="agent-chat-rail">
          <div className="agent-chat-section-head">
            <small>{t('agentChat.brand.agent')}</small>
            <button type="button" className="agent-chat-rail__new" onClick={() => createSession()}>
              <MessageSquarePlus size={15} />
              <span>{t('agentChat.action.newConversation')}</span>
            </button>
          </div>
          <label className="agent-chat-session-filter">
            <div className="agent-chat-session-filter__control">
              <Search size={14} />
              <input
                value={sessionFilter}
                onChange={(event) => setSessionFilter(event.target.value)}
                placeholder={t('agentChat.session.searchPlaceholder')}
              />
            </div>
          </label>
          <details className="agent-chat-session-dropdown" open={Boolean(sessionFilter.trim()) || undefined}>
            <summary>
              <span>{t('agentChat.session.label')}</span>
              <em>{activeSession?.title || t('agentChat.session.current')} · {filteredSessions.length}</em>
            </summary>
            <div className="agent-chat-session-list">
              {filteredSessions.length ? (
                filteredSessions.map((session) => {
                  const sessionRunning = Boolean(runStateBySession[session.id]?.pending)
                  return (
                    <button
                      key={session.id}
                      type="button"
                      className={`agent-chat-session-item ${activeSessionId === session.id ? 'is-active' : ''} ${sessionRunning ? 'is-running' : ''}`.trim()}
                      onClick={() => setActiveSessionId(session.id)}
                    >
                      <strong>{session.title}</strong>
                      <small>{sessionRunning ? t('agentChat.session.running') : session.backendCurrentPhase || session.updatedAt}</small>
                      <p>{sessionStats[session.id]?.preview || t('agentChat.session.emptyPreview')}</p>
                      <em>{sessionStats[session.id]?.count || 0}</em>
                    </button>
                  )
                })
              ) : (
                <div className="agent-chat-session-empty">
                  <strong>{t('agentChat.session.noMatchesTitle')}</strong>
                  <span>{t('agentChat.session.noMatchesHint')}</span>
                </div>
              )}
            </div>
          </details>
          <div className="agent-chat-rail-footer">
            <span>{projectKey}</span>
            <span>
              {runningSessionCount
                ? formatCatalogTemplate(t('agentChat.session.runningTasksCount'), { count: runningSessionCount })
                : streamStatus}
            </span>
          </div>
        </aside>

        <div className="agent-chat-conversation" data-running={isActiveSessionRunning ? 'true' : 'false'} data-testid="agent-chat-conversation">
          <div className="agent-chat-conversation-head">
            <div className="agent-chat-conversation-head__copy">
              <strong data-testid="agent-chat-active-session-title">{activeSession?.title || t('agentChat.session.current')}</strong>
              <div className="agent-chat-conversation-head__stages">
                {STAGE_LABELS.map((stage, index) => (
                  <span
                    key={stage.key}
                    className={`agent-chat-head-stage ${index < phaseIndex ? 'is-done' : index === phaseIndex ? 'is-active' : ''}`.trim()}
                  >
                    {index < phaseIndex ? <CheckCircle2 size={13} /> : <Circle size={12} />}
                    {t(stage.labelKey)}
                  </span>
                ))}
              </div>
            </div>
            <div className="agent-chat-conversation-head__meta">
              <span>{messageCountLabel}</span>
              <span className={`agent-chat-run-signal is-${runSignal.className}`} title={runSignal.detail}>
                {runSignalIcon}
                {runSignal.label}
              </span>
              <button
                type="button"
                className="agent-chat-icon-button"
                onClick={() => activeBackendSessionId && coordinatorMutation.mutate(activeBackendSessionId)}
                disabled={!activeBackendSessionId || actionBusy}
                title={t('agentChat.action.continueCurrentSession')}
              >
                <Play size={15} />
              </button>
              <button
                type="button"
                className="agent-chat-icon-button"
                onClick={() =>
                  activeBackendSessionId && retryableTask?.task_id
                    ? retryTaskMutation.mutate({ sessionId: activeBackendSessionId, taskId: retryableTask.task_id })
                    : undefined
                }
                disabled={!activeBackendSessionId || !retryableTask?.task_id || actionBusy}
                title={t('agentChat.action.retryFailedTask')}
              >
                <RotateCcw size={15} />
              </button>
              <button
                type="button"
                className="agent-chat-icon-button"
                onClick={() => activeBackendSessionId && cancelSessionMutation.mutate(activeBackendSessionId)}
                disabled={!activeBackendSessionId || actionBusy}
                title={t('agentChat.action.stopCurrentSession')}
              >
                <XCircle size={15} />
              </button>
            </div>
          </div>

          <div className="agent-chat-workspace">
            <section className="agent-chat-thread">
              <div ref={listRef} className="agent-chat-message-list">
                {backendErrorText ? (
                  <div className="agent-chat-state-banner is-error">
                    <AlertTriangle size={15} />
                    <span>{backendErrorText}</span>
                  </div>
                ) : null}
                {isConversationIdle ? (
                  <div className="agent-chat-state-banner">
                    <Bot size={15} />
                    <span>{t('agentChat.composer.idleHint')}</span>
                  </div>
                ) : null}
                {activeMessages.map((message) => {
                  const contentParts = splitMessageContent(message.content)
                  const isStreamingMessage = message.role === 'assistant' && message.id.startsWith('a-loading-') && message.state !== 'error'
                  const retrySessionId = message.retrySessionId || resolvedActiveSessionId
                  return (
                    <article
                      key={message.id}
                      className={`agent-chat-message role-${message.role} ${message.state === 'error' ? 'is-error' : ''} ${isStreamingMessage ? 'is-streaming' : ''}`.trim()}
                    >
                      <div className="agent-chat-message-body">
                        <span className="agent-chat-message-role">
                          {message.role === 'user'
                            ? t('agentChat.message.role.user')
                            : message.role === 'system'
                              ? t('agentChat.message.role.system')
                              : t('agentChat.message.role.assistant')}
                        </span>
                        <p className="agent-chat-message-summary">{contentParts.summary}</p>
                        {message.state === 'error' && message.retryCommand ? (
                          <div className="agent-chat-error-actions">
                            <button
                              type="button"
                              data-testid="agent-chat-retry-last"
                              onClick={() => void sendMessage(message.retryCommand || '', { sessionId: message.retrySessionId || resolvedActiveSessionId })}
                              disabled={Boolean(runStateBySession[retrySessionId]?.pending)}
                            >
                              <RotateCcw size={13} />
                              {t('agentChat.action.retry')}
                            </button>
                          </div>
                        ) : null}
                        {message.capabilityCalls?.length ? (
                          <details className="agent-chat-run-details">
                            <summary>
                              <Wrench size={14} />
                              {formatCatalogTemplate(t('agentChat.message.runToolsCount'), { count: message.capabilityCalls.length })}
                            </summary>
                            {message.capabilityCalls.map((call, index) => (
                              <div key={`${call.capability_id || 'tool'}-${index}`} className={`agent-chat-run-row status-${normalizeStatusToken(call.status)}`}>
                                <span>{call.capability_id || call.tool_name || 'tool'}</span>
                                <em>{call.status || '-'}</em>
                                {call.material_category?.label ? (
                                  <small className={`agent-chat-material-chip material-${normalizeMaterialCategoryToken(call.material_category.category)}`}>
                                    {call.material_category.label}
                                  </small>
                                ) : null}
                                <p>{call.summary || call.protocol || '-'}</p>
                              </div>
                            ))}
                          </details>
                        ) : null}
                        {showDebugMeta && message.meta?.length && message.role !== 'system' ? (
                          <details className="agent-chat-debug-details">
                            <summary>{t('agentChat.message.runtimeMeta')}</summary>
                            <div className="agent-chat-message-meta">
                              {message.meta.map((item, index) => (
                                <span key={`${item}-${index}`}>{item}</span>
                              ))}
                            </div>
                          </details>
                        ) : null}
                        {message.suggestedNextActions?.length ? (
                          <div className="agent-chat-next-actions">
                            {message.suggestedNextActions.slice(0, 3).map((item, index) => (
                              <button
                                key={`${item}-${index}`}
                                type="button"
                                onClick={() =>
                                  setDraftBySession((prev) => ({
                                    ...prev,
                                    [resolvedActiveSessionId]: item,
                                  }))
                                }
                              >
                                {item}
                              </button>
                            ))}
                          </div>
                        ) : null}
                        {contentParts.detailValue ? (
                          <details className="agent-chat-message-detail">
                            <summary>{contentParts.detailLabel || t('agentChat.message.details')}</summary>
                            <pre>{contentParts.detailValue}</pre>
                          </details>
                        ) : null}
                      </div>
                    </article>
                  )
                })}
                {isThinking ? (
                  <article className="agent-chat-message role-assistant is-thinking">
                    <div className="agent-chat-message-body">
                      <span className="agent-chat-message-role">{t('agentChat.message.role.assistant')}</span>
                      <p className="agent-chat-message-summary">
                        <LoaderCircle size={14} className="spin" />
                        <span>{t('agentChat.status.thinking')}</span>
                      </p>
                    </div>
                  </article>
                ) : null}
                <details className="agent-chat-runtime-panel" open={pendingApprovals.length > 0 || undefined}>
                  <summary>
                    <Clock3 size={14} />
                    {t('agentChat.runtime.title')}
                    <span>
                      {formatCatalogTemplate(t('agentChat.runtime.summary'), {
                        events: sessionTelemetry.events,
                        tools: latestCapabilityCalls.length,
                        artifacts: sessionTelemetry.artifacts,
                      })}
                    </span>
                  </summary>
                  <div className="agent-chat-workbench-tabs" aria-label={t('agentChat.workbench.ariaLabel')}>
                    {(['overview', 'tasks', 'tools', 'approvals', 'artifacts'] as const).map((view) => (
                      <button
                        key={view}
                        type="button"
                        className={workbenchView === view ? 'is-active' : undefined}
                        onClick={() => setWorkbenchView(view)}
                      >
                        {t(WORKBENCH_VIEW_LABEL_KEYS[view])}
                      </button>
                    ))}
                  </div>

                  <div className={`agent-chat-inspector-section agent-chat-overview-section ${workbenchView === 'overview' ? '' : 'is-hidden'}`.trim()}>
                    <div className="agent-chat-workbench-metrics">
                      <div>
                        <span>{t('agentChat.metric.phase')}</span>
                        <strong>{safeDisplay(sessionTelemetry.currentPhase)}</strong>
                      </div>
                      <div>
                        <span>{t('agentChat.metric.status')}</span>
                        <strong>{safeDisplay(sessionTelemetry.status)}</strong>
                      </div>
                      <div>
                        <span>{t('agentChat.metric.root')}</span>
                        <strong>{safeDisplay(sessionTelemetry.rootTaskId)}</strong>
                      </div>
                      <div>
                        <span>{t('agentChat.metric.stream')}</span>
                        <strong>{streamStatus}</strong>
                      </div>
                    </div>
                    <div className="agent-chat-timeline-section">
                      {workbenchTimeline.length ? (
                        workbenchTimeline.map((item) => (
                          <article key={item.key} className={`timeline-item status-${item.status}`}>
                            <i aria-hidden="true" />
                            <div>
                              <strong>{item.title}</strong>
                              <small>{item.meta}</small>
                              <p>{item.summary}</p>
                            </div>
                          </article>
                        ))
                      ) : (
                        <p>{t('agentChat.empty.events')}</p>
                      )}
                    </div>
                  </div>

                  <div className={`agent-chat-inspector-section agent-chat-task-plan-section ${shouldShowWorkbenchSection('tasks') ? '' : 'is-hidden'}`.trim()}>
                    <span><Play size={13} /> {t('agentChat.section.taskPlan')}</span>
                    {sessionTasks.length ? (
                      <div className="agent-chat-task-plan-list">
                        {sessionTasks.map((task, index) => {
                          const status = normalizeStatusToken(task.status)
                          const canRetry = ['failed', 'blocked', 'expired'].includes(status)
                          return (
                            <article
                              key={task.task_id}
                              className={`agent-chat-task-plan-card status-${status}`}
                              data-testid="agent-chat-task-plan-card"
                            >
                              <div className="agent-chat-task-plan-card__head">
                                <span>{index + 1}</span>
                                <strong>{task.subject || task.task_type || task.task_id}</strong>
                                <em>{safeDisplay(task.status)} · {safeDisplay(task.phase)}</em>
                              </div>
                              <p>{task.result_summary || task.progress?.summary_label || task.description || t('agentChat.task.pendingModel')}</p>
                              <div className="agent-chat-task-plan-card__meta">
                                {task.blocked_by?.length ? <span>{formatCatalogTemplate(t('agentChat.task.blockedByCount'), { count: task.blocked_by.length })}</span> : null}
                                {task.blocks?.length ? <span>{formatCatalogTemplate(t('agentChat.task.blocksCount'), { count: task.blocks.length })}</span> : null}
                                {task.read_set?.length ? <span>{formatCatalogTemplate(t('agentChat.task.readCount'), { count: task.read_set.length })}</span> : null}
                                {task.write_set?.length ? <span>{formatCatalogTemplate(t('agentChat.task.writeCount'), { count: task.write_set.length })}</span> : null}
                              </div>
                              <div className="agent-chat-task-plan-card__actions">
                                {canRetry ? (
                                  <button
                                    type="button"
                                    data-testid="agent-chat-task-retry"
                                    onClick={() =>
                                      activeBackendSessionId
                                        ? retryTaskMutation.mutate({ sessionId: activeBackendSessionId, taskId: task.task_id })
                                        : undefined
                                    }
                                    disabled={!activeBackendSessionId || actionBusy}
                                  >
                                    <RotateCcw size={13} />
                                    {t('agentChat.action.retry')}
                                  </button>
                                ) : null}
                                <button
                                  type="button"
                                  data-testid="agent-chat-task-continue"
                                  onClick={() => activeBackendSessionId && coordinatorMutation.mutate(activeBackendSessionId)}
                                  disabled={!activeBackendSessionId || actionBusy}
                                >
                                  <Play size={13} />
                                  {t('agentChat.action.continue')}
                                </button>
                              </div>
                            </article>
                          )
                        })}
                      </div>
                    ) : (
                      <p>{t('agentChat.empty.tasks')}</p>
                    )}
                    {longTaskStageCards.length ? (
                      <>
                        <span><Clock3 size={13} /> {t('agentChat.section.longTaskStages')}</span>
                        <div className="agent-chat-long-task-stage-list">
                          {longTaskStageCards.map((stage) => (
                            <article key={stage.key} className="agent-chat-long-task-stage-card" data-testid="agent-chat-long-task-stage-card">
                              <strong>{stage.currentStage}</strong>
                              <small>{formatCatalogTemplate(t('agentChat.longTask.completed'), { value: stage.completed })}</small>
                              <p>{stage.summary}</p>
                              <em>{stage.lastStage} · {stage.counts}</em>
                              {stage.nextAction ? <em>{formatCatalogTemplate(t('agentChat.longTask.next'), { value: stage.nextAction })}</em> : null}
                            </article>
                          ))}
                        </div>
                      </>
                    ) : null}
                  </div>

                  <div className={`agent-chat-inspector-section agent-chat-capability-section ${shouldShowWorkbenchSection('tools') ? '' : 'is-hidden'}`.trim()}>
                    <span><Wrench size={13} /> {t('agentChat.section.capabilities')}</span>
                    <div className="agent-chat-capability-groups">
                      <div>
                        <small>{t('agentChat.capability.group.core')}</small>
                        {coreCapabilities.length ? (
                          coreCapabilities.map((capability) => (
                            <article
                              key={capability.capability_id || capability.name}
                              className="agent-chat-capability-card"
                              data-testid="agent-chat-capability-item"
                              title={t('agentChat.capability.readOnlyTitle')}
                            >
                              <strong>{capability.capability_id || capability.name}</strong>
                              <em>{summarizeCapability(capability)}</em>
                            </article>
                          ))
                        ) : (
                          <p>{agentCapabilityQuery.isFetching ? t('agentChat.status.loading') : t('agentChat.empty.capabilityCatalog')}</p>
                        )}
                      </div>
                      <div>
                        <small>{t('agentChat.capability.group.governed')}</small>
                        {governedCapabilities.length ? (
                          governedCapabilities.map((capability) => (
                            <article
                              key={capability.capability_id || capability.name}
                              className="agent-chat-capability-card"
                              data-testid="agent-chat-capability-item"
                              title={t('agentChat.capability.readOnlyTitle')}
                            >
                              <strong>{capability.capability_id || capability.name}</strong>
                              <em>{summarizeCapability(capability)}</em>
                            </article>
                          ))
                        ) : (
                          <p>{t('agentChat.empty.governedCapabilities')}</p>
                        )}
                      </div>
                      <div>
                        <small>{t('agentChat.capability.group.externalBoundary')}</small>
                        {unavailableCapabilities.length ? (
                          unavailableCapabilities.map((capability) => (
                            <article
                              key={capability.capability_id || capability.name}
                              className="agent-chat-boundary-card"
                              data-testid="agent-chat-external-boundary-item"
                              title={t('agentChat.capability.externalBoundaryTitle')}
                            >
                              <strong>{capability.capability_id || capability.name}</strong>
                              <em>{capability.implementation_state || (capability.implemented === false ? 'unimplemented' : 'disabled')}</em>
                              {summarizeCapabilityRuntime(capability) ? <small>{summarizeCapabilityRuntime(capability)}</small> : null}
                              <p>{capability.disabled_reason || capability.description || t('agentChat.capability.notAvailableBoundary')}</p>
                            </article>
                          ))
                        ) : (
                          <p>{t('agentChat.empty.externalBoundary')}</p>
                        )}
                      </div>
                    </div>
                    <span><Wrench size={13} /> {t('agentChat.section.toolCalls')}</span>
                    {latestCapabilityCalls.length ? (
                      latestCapabilityCalls.slice(0, 8).map((call, index) => (
                        <article key={`${call.capability_id || 'call'}-${index}`} className={`agent-chat-run-row status-${normalizeStatusToken(call.status)}`}>
                          <span>{call.capability_id || call.tool_name || 'tool'}</span>
                          <em>
                            {joinWithMiddleDot([call.status || '-', call.protocol, call.stream_state])}
                          </em>
                          {call.material_category?.label ? (
                            <small className={`agent-chat-material-chip material-${normalizeMaterialCategoryToken(call.material_category.category)}`}>
                              {call.material_category.label}
                            </small>
                          ) : null}
                          <p>{call.summary || (call.run_id ? formatCatalogTemplate(t('agentChat.toolCall.runLabel'), { runId: call.run_id }) : '-')}</p>
                        </article>
                      ))
                    ) : (
                      <p>{t('agentChat.empty.toolCalls')}</p>
                    )}
                    <span><Radio size={13} /> {t('agentChat.section.progressiveEvents')}</span>
                    {progressiveToolEvents.length ? (
                      <div className="agent-chat-progressive-list">
                        {progressiveToolEvents.map((event) => (
                          <article
                            key={event.key}
                            className={`agent-chat-progressive-event status-${event.status}`}
                            data-testid="agent-chat-progressive-tool-event"
                          >
                            <strong>{event.toolName}</strong>
                            <small>{event.type} · {event.meta}</small>
                            <p>{event.summary}</p>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <p>{t('agentChat.empty.progressiveEvents')}</p>
                    )}
                    {investigationTraceCards.length ? (
                      <>
                        <span><Search size={13} /> {t('agentChat.section.investigationTrace')}</span>
                        <div className="agent-chat-trace-list">
                          {investigationTraceCards.map((trace) => (
                            <article key={trace.key} className="agent-chat-trace-card" data-testid="agent-chat-investigation-trace-card">
                              <strong>{trace.focus}</strong>
                              <small>{formatCatalogTemplate(t('agentChat.investigation.counts'), { nodes: trace.nodeCount, edges: trace.edgeCount })}</small>
                              <p>{trace.summary}</p>
                              {trace.pendingQuestion ? <em>{trace.pendingQuestion}</em> : null}
                            </article>
                          ))}
                        </div>
                      </>
                    ) : null}
                    {writingDiffCards.length ? (
                      <>
                        <span><FileText size={13} /> {t('agentChat.section.writingDiff')}</span>
                        <div className="agent-chat-diff-list">
                          {writingDiffCards.map((diff) => (
                            <article key={diff.key} className="agent-chat-diff-card" data-testid="agent-chat-diff-event">
                              <strong>{diff.toolName}</strong>
                              <small>{joinWithMiddleDot([diff.operation, formatCatalogTemplate(t('agentChat.diff.docLabel'), { docId: diff.docId })])}</small>
                              <p>{diff.summary}</p>
                              <em>+{diff.added ?? '-'} / -{diff.removed ?? '-'}</em>
                            </article>
                          ))}
                        </div>
                      </>
                    ) : null}
                    {sourceQualityCards.length ? (
                      <>
                        <span><ShieldCheck size={13} /> {t('agentChat.section.sourceQuality')}</span>
                        <div className="agent-chat-source-history-toolbar" data-testid="agent-chat-source-history-toolbar">
                          {SOURCE_HISTORY_FILTERS.map((filter) => (
                            <button
                              key={filter}
                              type="button"
                              className={sourceHistoryFilter === filter ? 'is-selected' : ''}
                              onClick={() => setSourceHistoryFilter(filter as typeof sourceHistoryFilter)}
                            >
                              {formatCatalogTemplate(t(SOURCE_HISTORY_FILTER_LABEL_KEYS[filter]), { count: sourceHistorySummary[filter] })}
                            </button>
                          ))}
                        </div>
                        <div className="agent-chat-source-quality-list">
                          {visibleSourceQualityCards.length ? visibleSourceQualityCards.map((card) => (
                            <article key={card.key} className={`agent-chat-source-quality-card status-${normalizeStatusToken(card.status)}`} data-testid="agent-chat-source-quality-card">
                              <strong>{card.title}</strong>
                              <small>{formatCatalogTemplate(t('agentChat.source.scoreMeta'), { status: card.status, score: card.score, level: card.level })}</small>
                              {card.url ? <em>{card.url}</em> : null}
                              <p>{card.reason}</p>
                              {card.snippet ? <p>{card.snippet}</p> : null}
                              {(card.provider || card.nextGate) ? (
                                <div className="agent-chat-source-quality-card__meta">
                                  {card.provider ? <span>{card.provider}</span> : null}
                                  {card.nextGate ? <span>{card.nextGate}</span> : null}
                                </div>
                              ) : null}
                              {card.reviewDecision ? (
                                <div className={`agent-chat-source-quality-card__decision decision-${card.reviewDecision}`} data-testid="agent-chat-source-candidate-decision">
                                  <span>{formatSourceCandidateDecision(locale, card.reviewDecision)}</span>
                                  {card.reviewTaskId ? <em>{formatCatalogTemplate(t('agentChat.source.taskLabel'), { taskId: card.reviewTaskId })}</em> : null}
                                  {card.reviewNextGate ? <em>{card.reviewNextGate}</em> : null}
                                  {card.reviewReason ? <p>{card.reviewReason}</p> : null}
                                </div>
                              ) : null}
                              <div className="agent-chat-source-quality-card__actions">
                                <button
                                  type="button"
                                  data-testid="agent-chat-source-candidate-approve"
                                  className={card.reviewDecision === 'approved' ? 'is-selected' : ''}
                                  disabled={isActiveSessionRunning}
                                  onClick={() => submitSourceCandidateDecision(card, 'approved')}
                                >
                                  <Play size={13} /> {t('agentChat.source.action.collect')}
                                </button>
                                <button
                                  type="button"
                                  data-testid="agent-chat-source-candidate-defer"
                                  className={card.reviewDecision === 'deferred' ? 'is-selected' : ''}
                                  disabled={isActiveSessionRunning}
                                  onClick={() => submitSourceCandidateDecision(card, 'deferred')}
                                >
                                  <Clock3 size={13} /> {t('agentChat.source.action.defer')}
                                </button>
                                <button
                                  type="button"
                                  data-testid="agent-chat-source-candidate-reject"
                                  className={card.reviewDecision === 'rejected' ? 'is-selected' : ''}
                                  disabled={isActiveSessionRunning}
                                  onClick={() => submitSourceCandidateDecision(card, 'rejected')}
                                >
                                  <XCircle size={13} /> {t('agentChat.source.action.reject')}
                                </button>
                              </div>
                            </article>
                          )) : (
                            <p className="agent-chat-source-history-empty">{t('agentChat.empty.sourceHistory')}</p>
                          )}
                        </div>
                      </>
                    ) : null}
                  </div>

                  <div className={`agent-chat-inspector-section agent-chat-approval-section ${shouldShowWorkbenchSection('approvals') ? '' : 'is-hidden'}`.trim()}>
                    <span><ShieldCheck size={13} /> {t('agentChat.section.approvals')}</span>
                    {primaryPendingApproval ? (
                      <div className="agent-chat-approval-callout">
                        <div>
                          <small>{t('agentChat.approval.pending')}</small>
                          <strong>
                            {(() => {
                              const binding = primaryPendingApproval.binding_payload || {}
                              const toolCall = asRecord(binding.tool_call)
                              const toolSpec = asRecord(binding.tool_spec)
                              return String(binding.capability_id || toolCall?.tool_name || toolSpec?.name || primaryPendingApproval.metadata?.capability_id || t('agentChat.approval.highRiskCapability'))
                            })()}
                          </strong>
                          <p>{String(primaryPendingApproval.binding_payload?.command || primaryPendingApproval.binding_payload?.user_message || primaryPendingApproval.binding_payload?.resume_token || '-')}</p>
                          <textarea
                            value={approvalOverrideById[primaryPendingApproval.approval_id] || ''}
                            placeholder={t('agentChat.approval.overridePlaceholder')}
                            aria-label={t('agentChat.approval.overrideAriaLabel')}
                            onChange={(event) => {
                              const value = event.target.value
                              setApprovalOverrideById((prev) => ({ ...prev, [primaryPendingApproval.approval_id]: value }))
                              if (approvalErrorById[primaryPendingApproval.approval_id]) {
                                setApprovalErrorById((prev) => ({ ...prev, [primaryPendingApproval.approval_id]: '' }))
                              }
                            }}
                          />
                          {approvalErrorById[primaryPendingApproval.approval_id] ? (
                            <em>{approvalErrorById[primaryPendingApproval.approval_id]}</em>
                          ) : null}
                        </div>
                        <div className="agent-chat-approval-actions">
                          <button
                            type="button"
                            data-testid="agent-chat-approval-approve"
                            onClick={() => continueApproval(primaryPendingApproval.approval_id)}
                            disabled={actionBusy}
                          >
                            <Play size={13} />
                            {t('agentChat.action.approveAndContinue')}
                          </button>
                          <button
                            type="button"
                            data-testid="agent-chat-approval-reject"
                            className="is-danger"
                            onClick={() => rejectApprovalMutation.mutate(primaryPendingApproval.approval_id)}
                            disabled={actionBusy}
                          >
                            {t('agentChat.action.reject')}
                          </button>
                        </div>
                      </div>
                    ) : null}
                    {sessionApprovals.length ? (
                      sessionApprovals.slice(0, 6).map((approval) => {
                        const binding = approval.binding_payload || {}
                        const toolCall = asRecord(binding.tool_call)
                        const toolSpec = asRecord(binding.tool_spec)
                        const capabilityId = String(
                          binding.capability_id
                          || toolCall?.tool_name
                          || toolSpec?.name
                          || approval.metadata?.capability_id
                          || 'approval',
                        )
                        return (
                          <article key={approval.approval_id}>
                            <strong>{capabilityId}</strong>
                            <small>{approval.status || '-'} · {approval.approval_id}</small>
                            <p>{String(binding.command || binding.resume_token || '-')}</p>
                          </article>
                        )
                      })
                    ) : (
                      <p>{t('agentChat.empty.approvals')}</p>
                    )}
                  </div>

                  <div className={`agent-chat-inspector-section agent-chat-artifact-section ${shouldShowWorkbenchSection('artifacts') ? '' : 'is-hidden'}`.trim()}>
                    <span><FileText size={13} /> {t('agentChat.section.artifacts')}</span>
                    {latestArtifacts.length ? (
                      latestArtifacts.map((artifact) => (
                        <button
                          key={artifact.artifact_id}
                          type="button"
                          className={selectedArtifact?.artifact_id === artifact.artifact_id ? 'is-selected' : undefined}
                          onClick={() => setSelectedArtifactId(artifact.artifact_id)}
                        >
                          <strong>{artifact.name || artifact.artifact_type || 'artifact'}</strong>
                          <small>{artifact.status || 'artifact'} · {artifact.artifact_type || '-'}</small>
                          <p>{getPrimaryArtifactText(artifact)}</p>
                        </button>
                      ))
                    ) : (
                      <p>{t('agentChat.empty.artifacts')}</p>
                    )}
                    {selectedArtifact ? (
                      <div className="agent-chat-artifact-preview">
                        <div>
                          <strong>{selectedArtifact.name || selectedArtifact.artifact_type || selectedArtifact.artifact_id}</strong>
                          <small>{selectedArtifact.artifact_type || '-'} · {selectedArtifact.status || 'artifact'}</small>
                        </div>
                        <pre>{formatArtifactPreview(selectedArtifact)}</pre>
                      </div>
                    ) : null}
                  </div>
                  <div className="agent-chat-session-panel__footer">
                    <span>{formatCatalogTemplate(t('agentChat.runtime.compatLabel'), { value: safeDisplay(sessionTelemetry.compatMode) })}</span>
                    <span>
                      {sessionTelemetry.projectionVersion
                        ? formatCatalogTemplate(t('agentChat.runtime.projectionLabel'), { value: sessionTelemetry.projectionVersion })
                        : t('agentChat.runtime.projectionEmpty')}
                    </span>
                    <button type="button" onClick={() => void refreshBackendSession()} disabled={!activeBackendSessionId}>
                      <RefreshCw size={13} className={backendSessionQuery.isFetching ? 'spin' : undefined} />
                      {t('agentChat.action.refresh')}
                    </button>
                  </div>
                </details>
              </div>

              <footer className="agent-chat-composer">
                {isConversationIdle ? (
                  <div className="agent-chat-composer-prompts">
                    <div className="agent-chat-prompt-row">
                      {quickCommands.map((command) => (
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
                        <MessageSquarePlus size={14} />
                        <span>{t('agentChat.action.newFromDraft')}</span>
                      </button>
                    </div>
                  </div>
                ) : null}
                <textarea
                  aria-label={t('agentChat.composer.inputAriaLabel')}
                  data-testid="agent-chat-input"
                  value={currentDraft}
                  placeholder={t('agentChat.composer.inputPlaceholder')}
                  onChange={(event) =>
                    setDraftBySession((prev) => ({
                      ...prev,
                      [resolvedActiveSessionId]: event.target.value,
                    }))
                  }
                  onKeyDown={(event) => {
                    if (event.key !== TECHNICAL_TEXT.enterKey.value || event.shiftKey || event.nativeEvent.isComposing) return
                    event.preventDefault()
                    void sendMessage(currentDraft)
                  }}
                />
                <div className="agent-chat-composer-actions">
                  <button
                    type="button"
                    className="agent-chat-icon-button"
                    data-testid="agent-chat-clear-session"
                    onClick={clearCurrentSession}
                    disabled={isActiveSessionRunning}
                    title={t('agentChat.action.clearSession')}
                  >
                    <XCircle size={15} />
                  </button>
                  <button
                    type="button"
                    className="agent-chat-send-button"
                    data-testid="agent-chat-send-button"
                    onClick={() => void sendMessage(currentDraft)}
                    disabled={isActiveSessionRunning || !currentDraft.trim()}
                    title={t('agentChat.action.send')}
                  >
                    {isActiveSessionRunning ? <LoaderCircle size={14} className="spin" /> : <SendHorizonal size={14} />}
                  </button>
                </div>
              </footer>
            </section>
          </div>
        </div>
      </section>
    </div>
  )
}
