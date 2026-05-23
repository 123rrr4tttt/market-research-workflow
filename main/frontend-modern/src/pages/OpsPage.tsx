import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Eye, RefreshCw, Trash2, XCircle } from 'lucide-react'
import GraphNodeCard from '../components/graph-kit/GraphNodeCard'
import GraphBusinessCardSections from '../components/GraphBusinessCardSections'
import GraphExtensionsSections from '../components/GraphExtensionsSections'
import { DEFAULT_APP_LOCALE, translate, useAppLocale, type AppLocale, type MessageKey } from '../app/platform/i18n'
import { endpoints } from '../lib/api/endpoints'
import { queryKeys } from '../lib/queryKeys'
import type { AgentArtifactItem, AgentEventItem, AgentMessageItem, AgentSessionDetail, AgentSessionItem, AgentTaskItem, DocumentItem } from '../lib/types'
import {
  cancelAgentSession,
  bulkUpdateDocumentExtractedData,
  clearDocumentExtractedData,
  cleanupGovernance,
  createAgentSession,
  getAdminDocument,
  deleteAdminDocuments,
  exportGraph,
  getAdminStats,
  getAgentSession,
  getSearchHistory,
  listAdminDocuments,
  listAgentSessions,
  reclaimExpiredAgentSessionTasks,
  reExtractDocuments,
  resolveAgentApproval,
  runAgentSessionCoordinatorPass,
  retryAgentSessionTask,
  syncAggregator,
  topicExtractDocuments,
} from '../lib/api'

type OpsPageProps = {
  projectKey: string
  variant?: 'ops' | 'backend'
}

type OpsCardTab = 'business' | 'graph_ext'
type OpsActionKey =
  | 'cleanup'
  | 'reExtract'
  | 'topicExtract'
  | 'graphExport'
  | 'syncAggregator'
  | 'bulkStructuredWrite'
  | 'clearStructured'
  | 'deleteDocuments'

const OPS_ACTION_NAME_KEYS: Record<OpsActionKey, MessageKey> = {
  cleanup: 'opsPage.actionName.cleanup',
  reExtract: 'opsPage.actionName.reExtract',
  topicExtract: 'opsPage.actionName.topicExtract',
  graphExport: 'opsPage.actionName.graphExport',
  syncAggregator: 'opsPage.actionName.syncAggregator',
  bulkStructuredWrite: 'opsPage.actionName.bulkStructuredWrite',
  clearStructured: 'opsPage.actionName.clearStructured',
  deleteDocuments: 'opsPage.actionName.deleteDocuments',
}

type OpsGraphExtensionLabels = {
  documentType: string
  entityType: string
  objectValue: string
  relationTargetType: string
}

const OPS_CARD_PALETTE = [
  '#7dd3fc', // brand cyan
  '#93c5fd', // blue-300
  '#67e8f9', // cyan-300
  '#a5b4fc', // indigo-300
  '#86efac', // green-300
  '#c4b5fd', // violet-300
  '#5eead4', // teal-300
  '#bae6fd', // sky-200
]

const AGENT_ENFORCEMENT_EVENT_TYPES = new Set([
  'skill.write_conflict',
  'approval.requested',
  'approval.waiting',
  'approval.approved',
  'approval.failed',
  'coordinator.dispatch_planned',
  'coordinator.synthesis_completed',
])

function formatDate(value?: string | null, locale: AppLocale = DEFAULT_APP_LOCALE) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString(locale)
}

function formatOpsTemplate(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value)),
    template,
  )
}

function toGraphBusinessNode(
  doc: DocumentItem | undefined,
  activeDocId: number | null,
  labels: Pick<OpsGraphExtensionLabels, 'documentType'>,
): Record<string, unknown> {
  const extracted = (doc?.extracted_data && typeof doc.extracted_data === 'object' && !Array.isArray(doc.extracted_data))
    ? doc.extracted_data
    : {}
  return {
    ...extracted,
    id: doc?.id ?? activeDocId ?? '-',
    type: doc?.doc_type || String((extracted as Record<string, unknown>).type || labels.documentType),
    title: doc?.title || String((extracted as Record<string, unknown>).title || ''),
    name: String(
      (extracted as Record<string, unknown>).name
      || (extracted as Record<string, unknown>).canonical_name
      || '',
    ),
    state: doc?.state || String((extracted as Record<string, unknown>).state || ''),
    status: doc?.status || String((extracted as Record<string, unknown>).status || ''),
    publish_date: doc?.publish_date || String((extracted as Record<string, unknown>).publish_date || ''),
    platform: String((extracted as Record<string, unknown>).platform || ''),
    game: String((extracted as Record<string, unknown>).game || ''),
    policy_type: String((extracted as Record<string, unknown>).policy_type || ''),
    summary: doc?.summary || '',
    content: doc?.content || '',
    extracted_data: extracted,
    text: doc?.summary || doc?.content || '',
  }
}

function normalizeScalar(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function normalizeObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function hashText(value: string) {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

function opsChipColorForIndex(index: number) {
  return OPS_CARD_PALETTE[index % OPS_CARD_PALETTE.length]
}

function opsElementColorForLabel(label: string) {
  return OPS_CARD_PALETTE[hashText(label || 'element') % OPS_CARD_PALETTE.length]
}

function buildOpsGraphExtension(
  doc: DocumentItem | undefined,
  activeDocId: number | null,
  labels: OpsGraphExtensionLabels,
) {
  const node = toGraphBusinessNode(doc, activeDocId, labels)
  const elementGroups = new Map<string, string[]>()
  Object.entries(node).forEach(([key, value]) => {
    if (value == null) return
    if (Array.isArray(value)) {
      const values = value.map((item) => normalizeScalar(item).trim()).filter(Boolean)
      if (!values.length) return
      const bucket = elementGroups.get(key) || []
      elementGroups.set(key, [...bucket, ...values])
      return
    }
    if (typeof value === 'object') {
      const obj = normalizeObject(value)
      const values = Object.entries(obj).map(([k, v]) => `${k}: ${normalizeScalar(v) || labels.objectValue}`)
      if (!values.length) return
      const bucket = elementGroups.get(key) || []
      elementGroups.set(key, [...bucket, ...values])
      return
    }
    const text = normalizeScalar(value).trim()
    if (!text) return
    const bucket = elementGroups.get(key) || []
    elementGroups.set(key, [...bucket, text])
  })

  const extracted = normalizeObject(doc?.extracted_data)
  const er = normalizeObject(extracted.entities_relations)
  const entities = Array.isArray(er.entities) ? er.entities : []
  const relations = Array.isArray(er.relations) ? er.relations : []

  const entityTypeCount = new Map<string, number>()
  const entityItemsByType = new Map<string, string[]>()
  entities.forEach((item) => {
    const entity = normalizeObject(item)
    const type = String(entity.type || entity.entity_type || entity.category || entity.label || labels.entityType)
    const name = String(entity.name || entity.text || entity.value || entity.id || type)
    entityTypeCount.set(type, (entityTypeCount.get(type) || 0) + 1)
    const bucket = entityItemsByType.get(type) || []
    bucket.push(name)
    entityItemsByType.set(type, bucket)
  })

  const relationTypeCount = new Map<string, number>()
  const relationItemsByType = new Map<string, string[]>()
  const relationExamples: string[] = []
  relations.forEach((item) => {
    const relation = normalizeObject(item)
    const relType = String(relation.relation || relation.predicate || relation.type || relation.relation_type || relation.label || 'related_to')
    relationTypeCount.set(relType, (relationTypeCount.get(relType) || 0) + 1)
    const from = String(relation.subject || relation.source || relation.from || relation.head || 'source')
    const to = String(relation.object || relation.target || relation.to || relation.tail || 'target')
    const line = `${from} -${relType}-> ${to}`
    relationExamples.push(line)
    const bucket = relationItemsByType.get(relType) || []
    bucket.push(line)
    relationItemsByType.set(relType, bucket)
  })

  return {
    elementGroups: Array.from(elementGroups.entries())
      .map(([label, values]) => ({
        label,
        items: Array.from(new Set(values)).slice(0, 40).map((value, index) => ({ id: `${label}-${index}-${value}`, value, label })),
      }))
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 20),
    entityTypeItems: Array.from(entityTypeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
      .slice(0, 20),
    relationTypeItems: Array.from(relationTypeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
      .slice(0, 20),
    entityItemsByType: Object.fromEntries(
      Array.from(entityItemsByType.entries()).map(([type, list]) => [type, Array.from(new Set(list)).slice(0, 40)]),
    ) as Record<string, string[]>,
    relationItemsByType: Object.fromEntries(
      Array.from(relationItemsByType.entries()).map(([type, list]) => [type, Array.from(new Set(list)).slice(0, 40)]),
    ) as Record<string, string[]>,
    relationExamples: relationExamples.slice(0, 24),
  }
}

function normalizeSessionList(items: AgentSessionItem[] | undefined) {
  return [...(items || [])].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
}

function getArtifactPreview(artifact: AgentArtifactItem | undefined) {
  if (!artifact) return '-'
  const content = String(artifact.content || artifact.summary || '').trim()
  if (!content) return '-'
  return content.length > 1800 ? `${content.slice(0, 1800)}...` : content
}

function getEventLabel(event: AgentEventItem) {
  return [event.event_type, event.severity].filter(Boolean).join(' · ') || '-'
}

function getTaskProgressLabel(task: AgentTaskItem, labels: { tools: string; tokens: string }) {
  const progress = task.progress || {}
  const toolUseCount = Number(progress.tool_use_count || 0)
  const tokenUsage = Number(progress.token_usage || 0)
  return `${labels.tools} ${toolUseCount} | ${labels.tokens} ${tokenUsage}`
}

function getMessageLabel(message: AgentMessageItem) {
  return [message.actor, message.role].filter(Boolean).join(' · ') || '-'
}

function getAgentEventKey(event: AgentEventItem) {
  return `${event.seq || '-'}-${event.event_type || '-'}-${event.ts || '-'}-${event.task_id || event.session_id || '-'}`
}

function getEnforcementPolicyLabel(event: AgentEventItem, labels: { writeConflict: string; approvalFlow: string }) {
  const payload = event.payload || {}
  const concurrencyClass = typeof payload.concurrency_class === 'string' ? payload.concurrency_class : ''
  if (concurrencyClass) return concurrencyClass
  const eventType = String(event.event_type || '')
  if (eventType === 'skill.write_conflict') return labels.writeConflict
  if (eventType.startsWith('approval.')) return labels.approvalFlow
  return '-'
}

function getPayloadSummary(payload?: Record<string, unknown> | null) {
  const text = JSON.stringify(payload || {})
  return text.length > 160 ? `${text.slice(0, 160)}...` : text
}

const detailPreStyle = {
  marginTop: 8,
  maxHeight: 280,
  overflow: 'auto' as const,
  whiteSpace: 'pre-wrap' as const,
  overflowWrap: 'anywhere' as const,
}

function statusClass(status?: string | null) {
  const key = String(status || '').toLowerCase()
  if (key.includes('fail') || key.includes('error')) return 'chip chip-danger'
  if (key.includes('done') || key.includes('success') || key.includes('completed') || key.includes('approved')) return 'chip chip-ok'
  return 'chip chip-warn'
}

export default function OpsPage({ projectKey, variant = 'ops' }: OpsPageProps) {
  const queryClient = useQueryClient()
  const locale = useAppLocale()
  const t = (key: MessageKey, fallback?: string) => translate(locale, key, fallback)
  const actionName = (key: OpsActionKey) => t(OPS_ACTION_NAME_KEYS[key])
  const [retentionDays, setRetentionDays] = useState(90)
  const [pending, setPending] = useState(false)
  const [activeAction, setActiveAction] = useState<OpsActionKey | ''>('')
  const [statusText, setStatusText] = useState(() => t('opsPage.status.ready'))
  const [errorText, setErrorText] = useState('')
  const [docIdsText, setDocIdsText] = useState('')
  const [topicScope, setTopicScope] = useState<'all' | 'company' | 'product' | 'operation'>('all')
  const [docPage, setDocPage] = useState(1)
  const [docTypeFilter, setDocTypeFilter] = useState('')
  const [docStateFilter, setDocStateFilter] = useState('')
  const [docSearch, setDocSearch] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<number[]>([])
  const [activeDocCardId, setActiveDocCardId] = useState<number | null>(null)
  const [opsCardTab, setOpsCardTab] = useState<OpsCardTab>('business')
  const [extractMode, setExtractMode] = useState<'replace' | 'merge'>('merge')
  const [extractJsonText, setExtractJsonText] = useState('{}')
  const [sessionGoal, setSessionGoal] = useState(() => t('opsPage.default.sessionGoal'))
  const [sessionSource, setSessionSource] = useState<'user' | 'agent_batch' | 'workflow_graph'>('user')
  const [sessionCompatMode, setSessionCompatMode] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [selectedArtifactName, setSelectedArtifactName] = useState<string | null>(null)
  const [selectedEnforcementEventKey, setSelectedEnforcementEventKey] = useState<string | null>(null)
  const opsGraphExtensionLabels = useMemo(
    () => ({
      documentType: translate(locale, 'opsPage.fallback.documentType'),
      entityType: translate(locale, 'opsPage.fallback.entityType'),
      objectValue: translate(locale, 'opsPage.fallback.objectValue'),
      relationTargetType: translate(locale, 'opsPage.fallback.relationTargetType'),
    }),
    [locale],
  )

  const adminStats = useQuery({ queryKey: queryKeys.admin.stats(projectKey), queryFn: getAdminStats, enabled: Boolean(projectKey) })
  const searchHistory = useQuery({ queryKey: queryKeys.admin.searchHistory(projectKey), queryFn: () => getSearchHistory(1, 30), enabled: Boolean(projectKey) })
  const agentSessionsQuery = useQuery({
    queryKey: queryKeys.agentSessions.list(),
    queryFn: listAgentSessions,
  })
  const adminDocuments = useQuery({
    queryKey: queryKeys.admin.documents(projectKey, docPage, docTypeFilter, docStateFilter, docSearch),
    queryFn: () =>
      listAdminDocuments({
        page: docPage,
        page_size: 20,
        doc_type: docTypeFilter.trim() || null,
        state: docStateFilter.trim() || null,
        search: docSearch.trim() || null,
      }),
    enabled: Boolean(projectKey),
  })
  const activeDocDetail = useQuery({
    queryKey: queryKeys.admin.documentDetail(projectKey, activeDocCardId),
    queryFn: () => getAdminDocument(Number(activeDocCardId)),
    enabled: Boolean(projectKey && activeDocCardId),
  })
  const selectedSessionQuery = useQuery({
    queryKey: queryKeys.agentSessions.detail(selectedSessionId || 'none'),
    queryFn: () => getAgentSession(selectedSessionId || ''),
    enabled: Boolean(selectedSessionId),
  })
  const createSessionMutation = useMutation({
    mutationFn: async () =>
      createAgentSession({
        project_key: projectKey,
        source: sessionSource,
        goal: sessionGoal.trim(),
        entrypoint_type: 'ops_panel',
        compat_mode: sessionCompatMode,
        initial_context: {
          project_key: projectKey,
          surface: 'ops',
        },
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      const sessionId = String((result as AgentSessionDetail | null)?.session_id || '').trim()
      if (sessionId) {
        setSelectedSessionId(sessionId)
        setSelectedTaskId(null)
        setSelectedArtifactName('memory.md')
      }
    },
  })
  const cancelSessionMutation = useMutation({
    mutationFn: (sessionId: string) => cancelAgentSession(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
    },
  })
  const retryTaskMutation = useMutation({
    mutationFn: ({ sessionId, taskId }: { sessionId: string; taskId: string }) =>
      retryAgentSessionTask(sessionId, { task_id: taskId }),
    onSuccess: async (_result, variables) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(variables.sessionId) })
    },
  })
  const resolveApprovalMutation = useMutation({
    mutationFn: ({ approvalId, approved }: { approvalId: string; approved: boolean }) =>
      resolveAgentApproval(approvalId, { approved, reason: approved ? 'approved_from_ops_panel' : 'rejected_from_ops_panel' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      if (selectedSessionId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
      }
    },
  })
  const reclaimExpiredMutation = useMutation({
    mutationFn: (sessionId: string) => reclaimExpiredAgentSessionTasks(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      if (selectedSessionId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
      }
    },
  })
  const coordinatorPassMutation = useMutation({
    mutationFn: (sessionId: string) => runAgentSessionCoordinatorPass(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      if (selectedSessionId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
      }
    },
  })
  const normalizedSessions = useMemo(
    () => normalizeSessionList(agentSessionsQuery.data || undefined),
    [agentSessionsQuery.data],
  )
  useEffect(() => {
    if (!selectedSessionId && normalizedSessions.length) {
      setSelectedSessionId(normalizedSessions[0].session_id)
      setSelectedTaskId(null)
      setSelectedArtifactName('memory.md')
    }
  }, [normalizedSessions, selectedSessionId])
  const selectedSession = selectedSessionQuery.data
  const selectedSessionTasks = selectedSession?.tasks || []
  const selectedSessionEvents = useMemo(
    () => selectedSession?.events || [],
    [selectedSession?.events],
  )
  const selectedSessionArtifacts = useMemo(
    () => selectedSession?.artifacts || [],
    [selectedSession?.artifacts],
  )
  const selectedSessionApprovals = selectedSession?.approvals || []
  const selectedSessionMessages = selectedSession?.messages || []
  const selectedEnforcementEvents = useMemo(
    () => selectedSessionEvents.filter((event) => AGENT_ENFORCEMENT_EVENT_TYPES.has(String(event.event_type || ''))),
    [selectedSessionEvents],
  )
  const selectedEnforcementEvent = useMemo(
    () =>
      selectedEnforcementEvents.find((event) => getAgentEventKey(event) === selectedEnforcementEventKey)
      || selectedEnforcementEvents[0],
    [selectedEnforcementEventKey, selectedEnforcementEvents],
  )
  const selectedArtifact = useMemo(
    () => selectedSessionArtifacts.find((artifact) => artifact.name === selectedArtifactName) || selectedSessionArtifacts[0],
    [selectedArtifactName, selectedSessionArtifacts],
  )
  const selectedAgentTask = selectedSessionTasks.find((task) => task.task_id === selectedTaskId) || selectedSessionTasks[0]

  useEffect(() => {
    if (!selectedSessionId || typeof window === 'undefined' || typeof EventSource === 'undefined') return undefined
    const streamUrl = `${endpoints.agentSessions.streamBySession(selectedSessionId)}?since_seq=0&poll_seconds=1&max_seconds=60`
    const source = new EventSource(streamUrl, { withCredentials: false })
    let refreshTimer: number | null = null
    const scheduleRefresh = () => {
      if (refreshTimer != null) window.clearTimeout(refreshTimer)
      refreshTimer = window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.list() })
      }, 150)
    }
    source.onmessage = () => {
      scheduleRefresh()
    }
    source.onerror = () => {
      source.close()
    }
    return () => {
      if (refreshTimer != null) window.clearTimeout(refreshTimer)
      source.close()
    }
  }, [queryClient, selectedSessionId])

  const selectedCount = selectedDocIds.length
  const selectedCsv = useMemo(() => selectedDocIds.join(','), [selectedDocIds])
  const parsedDocIds = useMemo(() => {
    const tokens = docIdsText
      .split(/[,\s]+/)
      .map((item) => Number.parseInt(item.trim(), 10))
      .filter((item) => Number.isFinite(item) && item > 0)
    return Array.from(new Set(tokens))
  }, [docIdsText])
  const docTotalPages = Math.max(1, Math.ceil((adminDocuments.data?.total || 0) / Math.max(1, adminDocuments.data?.page_size || 20)))
  const graphExtension = useMemo(
    () => buildOpsGraphExtension(activeDocDetail.data, activeDocCardId, opsGraphExtensionLabels),
    [activeDocDetail.data, activeDocCardId, opsGraphExtensionLabels],
  )

  const toggleDocSelection = (docId: number) => {
    setSelectedDocIds((prev) => (prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]))
  }

  const selectCurrentPage = () => {
    const pageIds = (adminDocuments.data?.items || []).map((item) => item.id)
    setSelectedDocIds(pageIds)
  }

  const runAction = async (
    actionKey: OpsActionKey,
    fn: () => Promise<unknown>,
    options?: { refreshStats?: boolean; refreshSearchHistory?: boolean; refreshDocuments?: boolean },
  ) => {
    const name = actionName(actionKey)
    setPending(true)
    setActiveAction(actionKey)
    setErrorText('')
    setStatusText(formatOpsTemplate(t('opsPage.status.running'), { action: name }))
    try {
      const result = await fn()
      const taskId = typeof (result as { task_id?: unknown })?.task_id === 'string' ? String((result as { task_id?: string }).task_id) : ''
      setStatusText(
        taskId
          ? formatOpsTemplate(t('opsPage.status.submittedWithTask'), { action: name, taskId })
          : formatOpsTemplate(t('opsPage.status.completed'), { action: name }),
      )
      if (options?.refreshStats !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.stats(projectKey) })
      }
      if (options?.refreshSearchHistory !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.searchHistory(projectKey) })
      }
      if (options?.refreshDocuments !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.documentsBase(projectKey) })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t('opsPage.error.unknown')
      setStatusText(formatOpsTemplate(t('opsPage.status.failed'), { action: name }))
      setErrorText(message)
    } finally {
      setPending(false)
      setActiveAction('')
    }
  }

  return (
    <div className={`content-stack gv2-root ops-page ops-page--${variant}`}>
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'backend' ? t('opsPage.title.backend') : t('opsPage.title.ops')}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card"><span>{t('opsPage.kpi.documents')}</span><strong>{adminStats.data?.documents?.total || 0}</strong><small>{formatOpsTemplate(t('opsPage.kpi.todayCount'), { count: adminStats.data?.documents?.recent_today || 0 })}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.socialDocuments')}</span><strong>{adminStats.data?.social_data?.total || 0}</strong><small>{formatOpsTemplate(t('opsPage.kpi.todayCount'), { count: adminStats.data?.social_data?.recent_today || 0 })}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.sources')}</span><strong>{adminStats.data?.sources?.total || 0}</strong><small>{t('opsPage.kpi.resourcePool')}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.searchHistory')}</span><strong>{adminStats.data?.search_history?.total || 0}</strong><small>{t('opsPage.kpi.history')}</small></article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Eye size={15} />
            {t('opsPage.section.agentSessions')}
          </h2>
          <div className="inline-actions">
            <button
              type="button"
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
                if (selectedSessionId) {
                  void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
                }
              }}
            >
              <RefreshCw size={14} />
              {t('opsPage.action.refresh')}
            </button>
            <button
              type="button"
              onClick={() => {
                void createSessionMutation.mutateAsync()
              }}
              disabled={!sessionGoal.trim() || createSessionMutation.isPending}
            >
              {t('opsPage.action.createSession')}
            </button>
          </div>
        </div>

        <div className="grid-2" style={{ alignItems: 'start' }}>
          <div className="panel" style={{ margin: 0 }}>
            <div className="panel-header">
              <h3>{t('opsPage.section.newSession')}</h3>
            </div>
            <div className="stack" style={{ gap: 12 }}>
              <label className="stack" style={{ gap: 6 }}>
                <span>{t('opsPage.field.goal')}</span>
                <textarea value={sessionGoal} onChange={(e) => setSessionGoal(e.target.value)} rows={4} />
              </label>
              <div className="grid-2">
                <label className="stack" style={{ gap: 6 }}>
                  <span>{t('opsPage.field.source')}</span>
                  <select value={sessionSource} onChange={(e) => setSessionSource(e.target.value as 'user' | 'agent_batch' | 'workflow_graph')}>
                    <option value="user">user</option>
                    <option value="agent_batch">agent_batch</option>
                    <option value="workflow_graph">workflow_graph</option>
                  </select>
                </label>
                <label className="stack" style={{ gap: 6 }}>
                  <span>{t('opsPage.field.compatMode')}</span>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={sessionCompatMode}
                      onChange={(e) => setSessionCompatMode(e.target.checked)}
                    />
                    {t('opsPage.control.projectCompatProjection')}
                  </label>
                </label>
              </div>
              <div className="inline-actions">
                <button
                  type="button"
                  onClick={() => {
                    void createSessionMutation.mutateAsync()
                  }}
                  disabled={!sessionGoal.trim() || createSessionMutation.isPending}
                >
                  {createSessionMutation.isPending ? t('opsPage.action.creating') : t('opsPage.action.create')}
                </button>
                {selectedSessionId ? <span className="chip">{formatOpsTemplate(t('opsPage.status.currentSession'), { sessionId: selectedSessionId })}</span> : null}
              </div>
            </div>
          </div>

          <div className="panel" style={{ margin: 0 }}>
            <div className="panel-header">
              <h3>{t('opsPage.section.sessionList')}</h3>
              <span className="chip">{formatOpsTemplate(t('opsPage.metric.itemsCount'), { count: normalizedSessions.length })}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t('opsPage.field.session')}</th>
                    <th>{t('opsPage.field.status')}</th>
                    <th>{t('opsPage.field.phase')}</th>
                    <th>{t('opsPage.field.tasks')}</th>
                    <th>{t('opsPage.field.updated')}</th>
                    <th>{t('opsPage.field.open')}</th>
                  </tr>
                </thead>
                <tbody>
                  {normalizedSessions.map((session) => (
                    <tr key={session.session_id} className={session.session_id === selectedSessionId ? 'row-selected' : undefined}>
                      <td>
                        <div>{session.session_id}</div>
                        <small>{session.source || '-'} · {session.project_key || 'n/a'}</small>
                      </td>
                      <td><span className={statusClass(session.status)}>{session.status || '-'}</span></td>
                      <td>{session.current_phase || '-'}</td>
                      <td>{session.task_count ?? '-'}</td>
                      <td>{formatDate(session.updated_at, locale)}</td>
                      <td>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedSessionId(session.session_id)
                            setSelectedTaskId(null)
                            setSelectedArtifactName('memory.md')
                          }}
                        >
                          {t('opsPage.action.open')}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!normalizedSessions.length ? (
                    <tr>
                      <td colSpan={6} className="empty-cell">
                        {t('opsPage.empty.sessions')}
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {selectedSession ? (
          <div className="grid-2" style={{ marginTop: 16, alignItems: 'start' }}>
            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-header">
                <h3>{t('opsPage.section.sessionDetail')}</h3>
                <div className="inline-actions">
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void cancelSessionMutation.mutateAsync(selectedSessionId)
                    }}
                    disabled={!selectedSessionId || cancelSessionMutation.isPending}
                  >
                    <XCircle size={14} />
                    {t('opsPage.action.cancelSession')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
                    }}
                  >
                    <RefreshCw size={14} />
                    {t('opsPage.action.refreshDetails')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void coordinatorPassMutation.mutateAsync(selectedSessionId)
                    }}
                    disabled={!selectedSessionId || coordinatorPassMutation.isPending}
                  >
                    <RefreshCw size={14} />
                    {t('opsPage.action.coordinatorPass')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void reclaimExpiredMutation.mutateAsync(selectedSessionId)
                    }}
                    disabled={!selectedSessionId || reclaimExpiredMutation.isPending}
                  >
                    <Trash2 size={14} />
                    {t('opsPage.action.reclaimExpiredLease')}
                  </button>
                </div>
              </div>
              <div className="kpi-grid" style={{ marginTop: 0 }}>
                <article className="kpi-card">
                  <span>{t('opsPage.field.status')}</span>
                  <strong>{selectedSession.status || '-'}</strong>
                  <small>{selectedSession.current_phase || '-'}</small>
                </article>
                <article className="kpi-card">
                  <span>{t('opsPage.field.tasks')}</span>
                  <strong>{selectedSessionTasks.length}</strong>
                  <small>{formatOpsTemplate(t('opsPage.metric.eventsMessages'), { events: selectedSessionEvents.length, messages: selectedSessionMessages.length })}</small>
                </article>
                <article className="kpi-card">
                  <span>{t('opsPage.field.artifacts')}</span>
                  <strong>{selectedSessionArtifacts.length}</strong>
                  <small>{formatOpsTemplate(t('opsPage.metric.approvalsCount'), { count: selectedSessionApprovals.length })}</small>
                </article>
                <article className="kpi-card">
                  <span>{t('opsPage.field.compat')}</span>
                  <strong>{selectedSession.compat_mode ? t('opsPage.status.yes') : t('opsPage.status.no')}</strong>
                  <small>{selectedSession.compat_projection_version || '-'}</small>
                </article>
              </div>
              <div className="stack" style={{ gap: 12 }}>
                <div>
                  <strong>{t('opsPage.field.goal')}</strong>
                  <div>{selectedSession.goal || '-'}</div>
                </div>
                <div>
                  <strong>{t('opsPage.field.artifacts')}</strong>
                  <div className="inline-actions" style={{ marginTop: 8, flexWrap: 'wrap' }}>
                    {selectedSessionArtifacts.map((artifact) => (
                      <button
                        key={artifact.artifact_id}
                        type="button"
                        className={artifact.name === selectedArtifactName ? 'chip chip-ok' : 'chip'}
                        onClick={() => setSelectedArtifactName(artifact.name || artifact.artifact_id)}
                      >
                        {artifact.name || artifact.artifact_id}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <strong>{t('opsPage.field.selectedArtifact')}</strong>
                  <pre style={{ ...detailPreStyle, maxHeight: 220 }}>{getArtifactPreview(selectedArtifact)}</pre>
                </div>
              </div>
            </div>

            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-header">
                <h3>{t('opsPage.section.tasksApprovalsEvents')}</h3>
              </div>
              <div className="stack" style={{ gap: 16 }}>
                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>{t('opsPage.section.taskTree')}</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('opsPage.field.task')}</th>
                          <th>{t('opsPage.field.status')}</th>
                          <th>{t('opsPage.field.phase')}</th>
                          <th>{t('opsPage.field.progress')}</th>
                          <th>{t('opsPage.field.action')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionTasks.map((task) => (
                          <tr key={task.task_id} className={task.task_id === selectedTaskId ? 'row-selected' : undefined}>
                            <td>
                              <div>{task.subject || task.task_id}</div>
                              <small>{task.task_type || '-'} · {task.owner || '-'}</small>
                            </td>
                            <td><span className={statusClass(task.status)}>{task.status || '-'}</span></td>
                            <td>{task.phase || '-'}</td>
                            <td>{getTaskProgressLabel(task, { tools: t('opsPage.taskProgress.tools'), tokens: t('opsPage.taskProgress.tokens') })}</td>
                            <td>
                              <div className="inline-actions">
                                <button type="button" onClick={() => setSelectedTaskId(task.task_id)}>{t('opsPage.action.open')}</button>
                                {String(task.status || '') === 'failed' ? (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (!selectedSessionId) return
                                      void retryTaskMutation.mutateAsync({ sessionId: selectedSessionId, taskId: task.task_id })
                                    }}
                                  disabled={!selectedSessionId || retryTaskMutation.isPending}
                                >
                                    {t('opsPage.action.retry')}
                                  </button>
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        ))}
                        {!selectedSessionTasks.length ? (
                          <tr>
                            <td colSpan={5} className="empty-cell">{t('opsPage.empty.tasks')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                  {selectedAgentTask ? (
                    <div style={{ marginTop: 12 }}>
                      <strong>{t('opsPage.field.selectedTaskDetail')}</strong>
                      <pre style={{ ...detailPreStyle, maxHeight: 200 }}>{JSON.stringify(selectedAgentTask, null, 2)}</pre>
                    </div>
                  ) : null}
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>{t('opsPage.section.approvals')}</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('opsPage.field.approval')}</th>
                          <th>{t('opsPage.field.status')}</th>
                          <th>{t('opsPage.field.requester')}</th>
                          <th>{t('opsPage.field.expires')}</th>
                          <th>{t('opsPage.field.action')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionApprovals.map((approval) => (
                          <tr key={approval.approval_id}>
                            <td>
                              <div>{approval.approval_id}</div>
                              <small>{approval.binding_hash || '-'}</small>
                            </td>
                            <td><span className={statusClass(approval.status)}>{approval.status || '-'}</span></td>
                            <td>
                              <div>{approval.requester_session_id || approval.session_id || approval.requested_by || '-'}</div>
                              <small>{approval.requester_task_id || approval.task_id || '-'}</small>
                            </td>
                            <td>{formatDate(approval.expires_at, locale)}</td>
                            <td>
                              <div className="inline-actions">
                                <button
                                  type="button"
                                  onClick={() => {
                                    void resolveApprovalMutation.mutateAsync({ approvalId: approval.approval_id, approved: true })
                                  }}
                                  disabled={resolveApprovalMutation.isPending}
                                >
                                  <CheckCircle2 size={14} />
                                  {t('opsPage.action.approve')}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    void resolveApprovalMutation.mutateAsync({ approvalId: approval.approval_id, approved: false })
                                  }}
                                  disabled={resolveApprovalMutation.isPending}
                                >
                                  <XCircle size={14} />
                                  {t('opsPage.action.reject')}
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                        {!selectedSessionApprovals.length ? (
                          <tr>
                            <td colSpan={5} className="empty-cell">{t('opsPage.empty.approvals')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <strong>{t('opsPage.field.approvalPayload')}</strong>
                    <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                      {selectedSessionApprovals[0] ? JSON.stringify(selectedSessionApprovals[0].binding_payload || {}, null, 2) : '-'}
                    </pre>
                  </div>
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>{t('opsPage.section.skillEnforcementTimeline')}</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('opsPage.field.time')}</th>
                          <th>{t('opsPage.field.type')}</th>
                          <th>{t('opsPage.field.task')}</th>
                          <th>{t('opsPage.field.policy')}</th>
                          <th>{t('opsPage.field.payload')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedEnforcementEvents.slice().reverse().slice(0, 12).map((event) => {
                          const eventKey = getAgentEventKey(event)
                          return (
                            <tr
                              key={eventKey}
                              className={eventKey === selectedEnforcementEventKey ? 'row-selected' : undefined}
                              onClick={() => setSelectedEnforcementEventKey(eventKey)}
                              style={{ cursor: 'pointer' }}
                            >
                              <td>{formatDate(event.ts, locale)}</td>
                              <td>{event.event_type || '-'}</td>
                              <td>{event.task_id || '-'}</td>
                              <td>{getEnforcementPolicyLabel(event, { writeConflict: t('opsPage.policy.writeSharedConflict'), approvalFlow: t('opsPage.policy.approvalFlow') })}</td>
                              <td>{getPayloadSummary(event.payload)}</td>
                            </tr>
                          )
                        })}
                        {!selectedEnforcementEvents.length ? (
                          <tr>
                            <td colSpan={5} className="empty-cell">{t('opsPage.empty.enforcementEvents')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <strong>{t('opsPage.field.enforcementPayload')}</strong>
                    <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                      {selectedEnforcementEvent ? JSON.stringify(selectedEnforcementEvent.payload || {}, null, 2) : '-'}
                    </pre>
                  </div>
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>{t('opsPage.section.events')}</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('opsPage.field.seq')}</th>
                          <th>{t('opsPage.field.type')}</th>
                          <th>{t('opsPage.field.task')}</th>
                          <th>{t('opsPage.field.message')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionEvents.slice().reverse().slice(0, 12).map((event) => (
                          <tr key={`${event.event_type}-${event.ts}-${event.task_id || event.session_id}`}>
                            <td>{(event as { seq?: number }).seq || '-'}</td>
                            <td>{getEventLabel(event)}</td>
                            <td>{event.task_id || '-'}</td>
                            <td>{event.message || JSON.stringify(event.payload || {})}</td>
                          </tr>
                        ))}
                        {!selectedSessionEvents.length ? (
                          <tr>
                            <td colSpan={4} className="empty-cell">{t('opsPage.empty.events')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>{t('opsPage.section.coordinatorMessages')}</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('opsPage.field.when')}</th>
                          <th>{t('opsPage.field.actor')}</th>
                          <th>{t('opsPage.field.task')}</th>
                          <th>{t('opsPage.field.content')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionMessages.slice().reverse().slice(0, 12).map((message) => (
                          <tr key={`${message.created_at}-${message.actor}-${message.task_id || 'session'}`}>
                            <td>{formatDate(message.created_at, locale)}</td>
                            <td>{getMessageLabel(message)}</td>
                            <td>{message.task_id || '-'}</td>
                            <td>{message.content || '-'}</td>
                          </tr>
                        ))}
                        {!selectedSessionMessages.length ? (
                          <tr>
                            <td colSpan={4} className="empty-cell">{t('opsPage.empty.messages')}</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header"><h2>{t('opsPage.section.governanceActions')}</h2></div>
        <div className="inline-actions">
          <label><span>retention_days</span><input type="number" min={1} max={3650} value={retentionDays} onChange={(e) => setRetentionDays(Number.parseInt(e.target.value || '90', 10) || 90)} /></label>
          <label>
            <span>doc_ids</span>
            <input type="text" value={docIdsText} onChange={(e) => setDocIdsText(e.target.value)} placeholder="101,102,103" />
          </label>
          <button
            disabled={!selectedCount}
            onClick={() => setDocIdsText(selectedCsv)}
          >
            {formatOpsTemplate(t('opsPage.action.useSelected'), { count: selectedCount })}
          </button>
          <label>
            <span>topic_scope</span>
            <select value={topicScope} onChange={(e) => setTopicScope(e.target.value as 'all' | 'company' | 'product' | 'operation')}>
              <option value="all">all</option>
              <option value="company">company</option>
              <option value="product">product</option>
              <option value="operation">operation</option>
            </select>
          </label>
          <button disabled={pending} onClick={() => runAction('cleanup', () => cleanupGovernance(retentionDays))}><Trash2 size={14} />{activeAction === 'cleanup' ? t('opsPage.action.running') : t('opsPage.action.cleanup')}</button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              runAction('reExtract', () => reExtractDocuments(docIds.length ? { doc_ids: docIds } : {}))
            }}
          >
            <RefreshCw size={14} />{activeAction === 'reExtract' ? t('opsPage.action.running') : t('opsPage.action.reExtract')}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              const topics: Array<'company' | 'product' | 'operation'> = topicScope === 'all' ? ['company', 'product', 'operation'] : [topicScope]
              const payload = {
                topics,
                ...(docIds.length ? { doc_ids: docIds } : {}),
              }
              runAction('topicExtract', () => topicExtractDocuments(payload))
            }}
          >
            <RefreshCw size={14} />{activeAction === 'topicExtract' ? t('opsPage.action.running') : t('opsPage.action.topicExtract')}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              if (!docIds.length) {
                setStatusText(formatOpsTemplate(t('opsPage.status.failed'), { action: actionName('graphExport') }))
                setErrorText(t('opsPage.error.missingDocIds'))
                return
              }
              runAction(
                'graphExport',
                async () => {
                  const result = await exportGraph(docIds)
                  const nodes = Array.isArray(result?.nodes) ? result.nodes.length : 0
                  const edges = Array.isArray(result?.edges) ? result.edges.length : 0
                  setStatusText(formatOpsTemplate(t('opsPage.status.graphExportCompleted'), { nodes, edges }))
                  return result
                },
                { refreshStats: false, refreshSearchHistory: false },
              )
            }}
          >
            <RefreshCw size={14} />{activeAction === 'graphExport' ? t('opsPage.action.running') : t('opsPage.action.graphExport')}
          </button>
          <button disabled={pending} onClick={() => runAction('syncAggregator', () => syncAggregator(true))}><RefreshCw size={14} />{activeAction === 'syncAggregator' ? t('opsPage.action.running') : t('opsPage.action.syncAggregator')}</button>
          <button onClick={() => { queryClient.invalidateQueries({ queryKey: queryKeys.admin.stats(projectKey) }); queryClient.invalidateQueries({ queryKey: queryKeys.admin.searchHistory(projectKey) }); }}><RefreshCw size={14} />{t('opsPage.action.refresh')}</button>
        </div>
        <p className="status-line">{statusText}</p>
        {!!errorText && <p className="status-line">{errorText}</p>}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('opsPage.section.documentGovernance')}</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.admin.documentsBase(projectKey) })} disabled={adminDocuments.isFetching}>
              <RefreshCw size={14} />
              {adminDocuments.isFetching ? t('opsPage.action.refreshing') : t('opsPage.action.refreshDocuments')}
            </button>
            <button onClick={selectCurrentPage} disabled={!(adminDocuments.data?.items || []).length}>{t('opsPage.action.selectCurrentPage')}</button>
            <button onClick={() => setSelectedDocIds([])} disabled={!selectedCount}>{t('opsPage.action.clearSelection')}</button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>doc_type</span>
            <input value={docTypeFilter} onChange={(e) => { setDocTypeFilter(e.target.value); setDocPage(1) }} placeholder={t('opsPage.placeholder.docType')} />
          </label>
          <label>
            <span>state</span>
            <input value={docStateFilter} onChange={(e) => { setDocStateFilter(e.target.value); setDocPage(1) }} placeholder="state" />
          </label>
          <label>
            <span>search</span>
            <input value={docSearch} onChange={(e) => { setDocSearch(e.target.value); setDocPage(1) }} placeholder={t('opsPage.placeholder.titleKeyword')} />
          </label>
          <label>
            <span>extract_mode</span>
            <select value={extractMode} onChange={(e) => setExtractMode(e.target.value as 'replace' | 'merge')}>
              <option value="merge">merge</option>
              <option value="replace">replace</option>
            </select>
          </label>
        </div>
        <div className="form-grid cols-2">
          <label>
            <span>extracted_data(JSON)</span>
            <textarea rows={6} value={extractJsonText} onChange={(e) => setExtractJsonText(e.target.value)} />
          </label>
          <div className="inline-actions">
            <button
              disabled={pending || !selectedCount}
              onClick={() => {
                runAction('bulkStructuredWrite', async () => {
                  let parsed: unknown
                  try {
                    parsed = JSON.parse(extractJsonText || '{}')
                  } catch {
                    throw new Error(t('opsPage.error.invalidJson'))
                  }
                  return bulkUpdateDocumentExtractedData({
                    doc_ids: selectedDocIds,
                    mode: extractMode,
                    extracted_data: parsed,
                  })
                })
              }}
            >
              {t('opsPage.action.bulkWriteStructured')}
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('clearStructured', () => clearDocumentExtractedData(selectedDocIds))}
            >
              {t('opsPage.action.clearStructured')}
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('deleteDocuments', () => deleteAdminDocuments({ ids: selectedDocIds }))}
            >
              {t('opsPage.action.deleteDocuments')}
            </button>
          </div>
        </div>
        <p className="status-line">{formatOpsTemplate(t('opsPage.metric.selectedDocuments'), { count: selectedCount })}</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('opsPage.field.selected')}</th>
                <th>ID</th>
                <th>{t('opsPage.field.title')}</th>
                <th>{t('opsPage.field.type')}</th>
                <th>{t('opsPage.field.state')}</th>
                <th>{t('opsPage.field.extraction')}</th>
                <th>{t('opsPage.field.updated')}</th>
              </tr>
            </thead>
            <tbody>
              {(adminDocuments.data?.items || []).map((row) => (
                <tr
                  key={row.id}
                  onClick={() => {
                    let nextId: number | null = row.id
                    setActiveDocCardId((prev) => {
                      nextId = prev === row.id ? null : row.id
                      return nextId
                    })
                    if (nextId === null) {
                      return
                    }
                    setOpsCardTab('business')
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedDocIds.includes(row.id)}
                      onChange={() => toggleDocSelection(row.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td>{row.id}</td>
                  <td>{row.title || '-'}</td>
                  <td>{row.doc_type || '-'}</td>
                  <td>{row.state || '-'}</td>
                  <td>{String(row.has_extracted_data ?? false)}</td>
                  <td>{formatDate(row.updated_at, locale)}</td>
                </tr>
              ))}
              {!adminDocuments.data?.items?.length ? (
                <tr>
                  <td colSpan={7} className="empty-cell">{t('opsPage.empty.documents')}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="inline-actions">
          <button disabled={docPage <= 1} onClick={() => setDocPage((p) => Math.max(1, p - 1))}>{t('opsPage.action.previousPage')}</button>
          <span className="chip">{formatOpsTemplate(t('opsPage.metric.pageOf'), { page: docPage, total: docTotalPages })}</span>
          <button disabled={docPage >= docTotalPages} onClick={() => setDocPage((p) => Math.min(docTotalPages, p + 1))}>{t('opsPage.action.nextPage')}</button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><h2>{t('opsPage.section.searchHistory')}</h2></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>{t('opsPage.field.topic')}</th><th>{t('opsPage.field.lastSearchTime')}</th></tr></thead>
            <tbody>
              {(searchHistory.data || []).map((row) => (
                <tr key={row.id}><td>{row.id}</td><td>{row.topic || '-'}</td><td>{formatDate(row.last_search_time, locale)}</td></tr>
              ))}
              {!searchHistory.data?.length && <tr><td colSpan={3} className="empty-cell">{t('opsPage.empty.searchHistory')}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {activeDocCardId ? (
        <GraphNodeCard
          title={activeDocDetail.data?.title || formatOpsTemplate(t('opsPage.fallback.documentTitle'), { docId: activeDocCardId })}
          subtitle={activeDocDetail.data?.doc_type || '-'}
          style={{
            position: 'fixed',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            width: 'min(720px, calc(100vw - 40px))',
            maxHeight: 'calc(100vh - 80px)',
            overflow: 'auto',
            zIndex: 80,
          }}
          actions={
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <div className="gv2-card-tabs" role="tablist" aria-label={t('opsPage.aria.cardTabs')}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={opsCardTab === 'business'}
                  className={`gv2-card-tab ${opsCardTab === 'business' ? 'is-active' : ''}`.trim()}
                  onClick={() => {
                    setOpsCardTab('business')
                  }}
                  title={t('opsPage.tab.businessData')}
                >
                  {t('opsPage.tab.businessData')}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={opsCardTab === 'graph_ext'}
                  className={`gv2-card-tab ${opsCardTab === 'graph_ext' ? 'is-active' : ''}`.trim()}
                  onClick={() => setOpsCardTab('graph_ext')}
                  title={t('opsPage.tab.graphExtension')}
                >
                  {t('opsPage.tab.graphExtension')}
                </button>
              </div>
              <button
                type="button"
                onClick={() => {
                  void queryClient.invalidateQueries({ queryKey: queryKeys.admin.documentDetail(projectKey, activeDocCardId) })
                }}
                title={t('opsPage.action.refresh')}
              >
                ↻
              </button>
            </div>
          }
          onClose={() => {
            setActiveDocCardId(null)
            setOpsCardTab('business')
          }}
        >
          {activeDocDetail.isFetching ? (
            <div className="gv2-node-grid">
              <div className="gv2-node-grid-item">
                <label>{t('opsPage.field.status')}</label>
                <strong>{t('opsPage.status.loading')}</strong>
              </div>
            </div>
          ) : (
            <>
              {opsCardTab === 'business' ? <GraphBusinessCardSections node={toGraphBusinessNode(activeDocDetail.data, activeDocCardId, opsGraphExtensionLabels)} /> : null}
              {opsCardTab === 'graph_ext' ? (
                <GraphExtensionsSections
                  key={`ops-graph-ext-${activeDocCardId || 'none'}`}
                  graphInfo={{
                    degree: graphExtension.relationExamples.length,
                    neighborTypeCount: graphExtension.entityTypeItems.length,
                    marketDocCount: graphExtension.relationTypeItems.length,
                    neighborTypeItems: graphExtension.entityTypeItems,
                    predicateItems: graphExtension.relationTypeItems.map((item) => ({ predicate: item.type, count: item.count })),
                    neighborNodesByType: Object.fromEntries(
                      Object.entries(graphExtension.entityItemsByType).map(([type, names]) => [
                        type,
                        names.map((name, idx) => ({ id: `${type}-${idx}`, name, type })),
                      ]),
                    ),
                    relationsByPredicate: Object.fromEntries(
                      Object.entries(graphExtension.relationItemsByType).map(([type, lines]) => [
                        type,
                        lines.map((line, idx) => ({ id: `${type}-${idx}`, direction: 'OUT' as const, targetName: line, targetType: opsGraphExtensionLabels.relationTargetType })),
                      ]),
                    ),
                  }}
                  nodeElementGroups={graphExtension.elementGroups}
                  relationGroups={graphExtension.relationTypeItems.map((item) => ({
                    relation: item.type,
                    items: (graphExtension.relationItemsByType[item.type] || []).map((line, idx) => ({
                      id: `${item.type}-${idx}`,
                      direction: 'OUT' as const,
                      relation: item.type,
                      targetName: line,
                      targetType: opsGraphExtensionLabels.relationTargetType,
                    })),
                  }))}
                  nodeTypeColor={{ [opsGraphExtensionLabels.relationTargetType]: '#c4b5fd' }}
                  chipColorForIndex={opsChipColorForIndex}
                  elementColorForLabel={opsElementColorForLabel}
                />
              ) : null}
            </>
          )}
        </GraphNodeCard>
      ) : null}
    </div>
  )
}
