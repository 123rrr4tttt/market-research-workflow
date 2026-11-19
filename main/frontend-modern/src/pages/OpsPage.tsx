import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CheckCircle2, ChevronDown, ChevronUp, Eye, RefreshCw, Trash2, XCircle } from 'lucide-react'
import GraphNodeCard from '../components/graph-kit/GraphNodeCard'
import GraphBusinessCardSections from '../components/GraphBusinessCardSections'
import GraphExtensionsSections from '../components/GraphExtensionsSections'
import ProjectRetrievalPanel from './ProjectRetrievalPanel'
import { TaskSubmissionNotice } from '../components/TaskSubmissionNotice'
import { useTaskSubmission } from '../hooks/useTaskSubmission'
import './ops-page-management.css'
import { DEFAULT_APP_LOCALE, translate, useAppLocale, type AppLocale, type MessageKey } from '../app/platform/i18n'
import { endpoints } from '../lib/api/endpoints'
import { queryKeys } from '../lib/queryKeys'
import type {
  AdminActionResponse,
  AgentArtifactItem,
  AgentEventItem,
  AgentMessageItem,
  AgentSessionDetail,
  AgentSessionItem,
  AgentTaskItem,
  MaterialItem,
} from '../lib/types'
import {
  cancelAgentSession,
  bulkUpdateMaterialExtractedData,
  clearMaterialExtractedData,
  cleanupGovernance,
  createAgentSession,
  deleteAdminMaterials,
  exportGraph,
  getAdminMaterial,
  getAdminStats,
  getDeepHealth,
  getAgentSession,
  getSearchHistory,
  listAdminMaterials,
  listAgentSessions,
  reExtractMaterials,
  resolveAgentApproval,
  topicExtractMaterials,
} from '../lib/api'

type OpsPageProps = {
  projectKey: string
  variant?: 'ops' | 'backend'
}

type OpsCardTab = 'business' | 'graph_ext'
type OpsManagementTab = 'materials' | 'governance' | 'insights' | 'runtime' | 'agentSessions'
const OPS_MANAGEMENT_TAB_KEYS: Record<OpsManagementTab, MessageKey> = {
  materials: 'opsPage.tab.documents',
  governance: 'opsPage.tab.governance',
  insights: 'opsPage.tab.insights',
  runtime: 'opsPage.tab.runtime',
  agentSessions: 'opsPage.tab.agentSessions',
}
type OpsActionKey =
  | 'cleanup'
  | 'reExtract'
  | 'topicExtract'
  | 'graphExport'
  | 'bulkStructuredWrite'
  | 'clearStructured'
  | 'deleteMaterials'

const OPS_ACTION_NAME_KEYS: Record<OpsActionKey, MessageKey> = {
  cleanup: 'opsPage.actionName.cleanup',
  reExtract: 'opsPage.actionName.reExtract',
  topicExtract: 'opsPage.actionName.topicExtract',
  graphExport: 'opsPage.actionName.graphExport',
  bulkStructuredWrite: 'opsPage.actionName.bulkStructuredWrite',
  clearStructured: 'opsPage.actionName.clearStructured',
  deleteMaterials: 'opsPage.actionName.deleteMaterials',
}

type OpsGraphExtensionLabels = {
  documentType: string
  entityType: string
  objectValue: string
  relationTargetType: string
}

type OpsAdminPreviewPackage = {
  schema_version: string
  project_key: string
  action_kind: string
  risk_labels: string[]
  source_refs: AdminActionResponse['source_refs']
  trace_chain: AdminActionResponse['trace_chain']
  evidence_preview: AdminActionResponse['evidence_preview']
  audit_event: AdminActionResponse['audit_event']
  audit_trail: AdminActionResponse['audit_trail']
  execution_result: AdminActionResponse['execution_result']
  rollback_hint: AdminActionResponse['rollback_hint']
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
  material: MaterialItem | undefined,
  activeMaterialId: number | string | null,
  labels: Pick<OpsGraphExtensionLabels, 'documentType'>,
): Record<string, unknown> {
  const extracted = (material?.extracted_data && typeof material.extracted_data === 'object' && !Array.isArray(material.extracted_data))
    ? material.extracted_data
    : {}
  return {
    ...extracted,
    id: material?.material_id ?? activeMaterialId ?? '-',
    type: material?.material_type || String((extracted as Record<string, unknown>).type || labels.documentType),
    name: String(
      (extracted as Record<string, unknown>).name
      || (extracted as Record<string, unknown>).canonical_name
      || '',
    ),
    state: material?.state || String((extracted as Record<string, unknown>).state || ''),
    status: material?.status || String((extracted as Record<string, unknown>).status || ''),
    publish_date: material?.publish_date || String((extracted as Record<string, unknown>).publish_date || ''),
    platform: String((extracted as Record<string, unknown>).platform || ''),
    game: String((extracted as Record<string, unknown>).game || ''),
    policy_type: String((extracted as Record<string, unknown>).policy_type || ''),
    summary: material?.summary || '',
    content: material?.content || '',
    extracted_data: extracted,
    text: material?.summary || material?.content || '',
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
  material: MaterialItem | undefined,
  activeMaterialId: number | string | null,
  labels: OpsGraphExtensionLabels,
) {
  const node = toGraphBusinessNode(material, activeMaterialId, labels)
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

  const extracted = normalizeObject(material?.extracted_data)
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

function getAdminPreviewActionKind(preview: AdminActionResponse | null | undefined, fallback: string) {
  return String(preview?.action_kind || preview?.action || fallback)
}

function getAdminPreviewRiskLabels(preview: AdminActionResponse | null | undefined) {
  return [...(preview?.risk_labels || preview?.risk_tags || [])]
}

function getAdminPreviewSourceRefCount(preview: AdminActionResponse | null | undefined) {
  return Array.isArray(preview?.source_refs) ? preview.source_refs.length : 0
}

function getAdminPreviewTraceLabel(preview: AdminActionResponse | null | undefined) {
  const trace = preview?.trace_chain || {}
  const contract = typeof trace.contract_version === 'string' ? trace.contract_version : ''
  const traceId = typeof trace.trace_id === 'string' ? trace.trace_id : ''
  const action = getAdminPreviewActionKind(preview, '')
  return [contract, traceId, action].filter(Boolean).join(' · ') || '-'
}

function buildOpsAdminPreviewPackage(projectKey: string, preview: AdminActionResponse | null): OpsAdminPreviewPackage {
  return {
    schema_version: preview?.schema_version || ['ops', 'admin', 'governance_evidence_package', 'v1'].join('.'),
    project_key: projectKey,
    action_kind: getAdminPreviewActionKind(preview, 'unknown'),
    risk_labels: getAdminPreviewRiskLabels(preview),
    source_refs: preview?.source_refs || [],
    trace_chain: preview?.trace_chain || null,
    evidence_preview: preview?.evidence_preview || null,
    audit_event: preview?.audit_event || null,
    audit_trail: preview?.audit_trail || null,
    execution_result: preview?.execution_result || null,
    rollback_hint: preview?.rollback_hint || preview?.rollback_recommendation || null,
  }
}

function hasAdminGovernanceEvidence(value: unknown): value is AdminActionResponse {
  if (!value || typeof value !== 'object') return false
  const record = value as AdminActionResponse
  return Boolean(
    record.source_query
    || record.source_refs?.length
    || record.trace_chain
    || record.evidence_preview
    || record.audit_event
    || record.audit_trail
    || record.execution_result
    || record.rollback_hint
    || record.rollback_recommendation,
  )
}

function getExecutionResultAvailable(value: AdminActionResponse | null | undefined) {
  if (!value) return false
  const execution = value.execution_result
  if (execution && typeof execution === 'object') {
    const available = execution.execution_result_available
    if (typeof available === 'boolean') return available
    return Object.keys(execution).length > 0
  }
  return Boolean(value.evidence_preview?.execution_result_available)
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
  return <OpsPageView key={`${projectKey}/${variant}`} projectKey={projectKey} variant={variant} />
}

function OpsPageView({ projectKey, variant = 'ops' }: OpsPageProps) {
  const queryClient = useQueryClient()
  const locale = useAppLocale()
  const t = (key: MessageKey, fallback?: string) => translate(locale, key, fallback)
  const isZhLocale = locale.toLowerCase().startsWith('zh')
  const actionName = (key: OpsActionKey) => t(OPS_ACTION_NAME_KEYS[key])
  const [retentionDays, setRetentionDays] = useState(90)
  const [pending, setPending] = useState(false)
  const [activeAction, setActiveAction] = useState<OpsActionKey | ''>('')
  const [statusText, setStatusText] = useState(() => t('opsPage.status.ready'))
  const [errorText, setErrorText] = useState('')
  const [materialIdsText, setMaterialIdsText] = useState('')
  const [topicScope, setTopicScope] = useState<'all' | 'company' | 'product' | 'operation'>('all')
  const [materialPage, setMaterialPage] = useState(1)
  const [materialTypeFilter, setMaterialTypeFilter] = useState('')
  const [materialStateFilter, setMaterialStateFilter] = useState('')
  const [materialSearch, setMaterialSearch] = useState('')
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<number[]>([])
  const [activeMaterialCardId, setActiveMaterialCardId] = useState<number | null>(null)
  const [opsCardTab, setOpsCardTab] = useState<OpsCardTab>('business')
  const [extractMode, setExtractMode] = useState<'replace' | 'merge'>('merge')
  const [extractJsonText, setExtractJsonText] = useState('{}')
  const [adminPreview, setAdminPreview] = useState<AdminActionResponse | null>(null)
  const [adminPreviewAction, setAdminPreviewAction] = useState<OpsActionKey | ''>('')
  const [sessionGoal, setSessionGoal] = useState(() => t('opsPage.default.sessionGoal'))
  const [sessionSource, setSessionSource] = useState<'user' | 'agent_batch' | 'workflow_graph'>('user')
  const [sessionCompatMode, setSessionCompatMode] = useState(false)
  const [explicitSelectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [explicitSelectedArtifactName, setSelectedArtifactName] = useState<string | null>(null)
  const [selectedEnforcementEventKey, setSelectedEnforcementEventKey] = useState<string | null>(null)
  const [requestedTab, setRequestedTab] = useState<OpsManagementTab>(variant === 'backend' ? 'runtime' : 'materials')
  const [showMaterialTools, setShowMaterialTools] = useState(false)
  const managementTabs: OpsManagementTab[] = variant === 'backend'
    ? ['runtime', 'agentSessions']
    : ['materials', 'governance', 'insights']
  const activeTab = managementTabs.includes(requestedTab) ? requestedTab : managementTabs[0]
  const taskSubmission = useTaskSubmission({
    projectKey,
    invalidateOnSettled: [
      queryKeys.admin.stats(projectKey),
      queryKeys.admin.materialsBase(projectKey),
      queryKeys.admin.searchHistory(projectKey),
      queryKeys.health.deep(),
    ],
  })
  const opsGraphExtensionLabels = useMemo(
    () => ({
      documentType: translate(locale, 'opsPage.fallback.documentType'),
      entityType: translate(locale, 'opsPage.fallback.entityType'),
      objectValue: translate(locale, 'opsPage.fallback.objectValue'),
      relationTargetType: translate(locale, 'opsPage.fallback.relationTargetType'),
    }),
    [locale],
  )

  const adminStats = useQuery({ queryKey: queryKeys.admin.stats(projectKey), queryFn: getAdminStats, enabled: Boolean(projectKey) && variant === 'ops' })
  const runtimeStatus = useQuery({ queryKey: queryKeys.health.deep(), queryFn: getDeepHealth, enabled: variant === 'backend' })
  const searchHistory = useQuery({ queryKey: queryKeys.admin.searchHistory(projectKey), queryFn: () => getSearchHistory(1, 30), enabled: Boolean(projectKey) && variant === 'ops' && activeTab === 'insights' })
  const agentSessionsQuery = useQuery({
    queryKey: queryKeys.agentSessions.list(),
    queryFn: listAgentSessions,
    enabled: variant === 'backend' && activeTab === 'agentSessions',
  })
  const normalizedSessions = useMemo(
    () => normalizeSessionList(agentSessionsQuery.data || undefined),
    [agentSessionsQuery.data],
  )
  const selectedSessionId = explicitSelectedSessionId ?? normalizedSessions[0]?.session_id ?? null
  const adminMaterials = useQuery({
    queryKey: queryKeys.admin.materials(projectKey, materialPage, materialTypeFilter, materialStateFilter, materialSearch),
    queryFn: () =>
      listAdminMaterials({
        page: materialPage,
        page_size: 20,
        material_type: materialTypeFilter.trim() || null,
        state: materialStateFilter.trim() || null,
        search: materialSearch.trim() || null,
      }),
    enabled: Boolean(projectKey) && variant === 'ops',
  })
  const activeMaterialDetail = useQuery({
    queryKey: queryKeys.admin.materialDetail(projectKey, activeMaterialCardId),
    queryFn: () => getAdminMaterial(Number(activeMaterialCardId)),
    enabled: Boolean(projectKey && typeof activeMaterialCardId === 'number') && variant === 'ops',
  })
  const selectedSessionQuery = useQuery({
    queryKey: queryKeys.agentSessions.detail(selectedSessionId || 'none'),
    queryFn: () => getAgentSession(selectedSessionId || ''),
    enabled: Boolean(selectedSessionId) && variant === 'backend' && activeTab === 'agentSessions',
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
        setSelectedArtifactName(null)
      }
    },
  })
  const cancelSessionMutation = useMutation({
    mutationFn: (sessionId: string) => cancelAgentSession(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
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
  const selectedArtifactName = useMemo(() => {
    const explicitArtifact = selectedSessionArtifacts.find((artifact) => artifact.name === explicitSelectedArtifactName)
    if (explicitArtifact?.name) return explicitArtifact.name
    const firstArtifact = selectedSessionArtifacts[0]
    return firstArtifact ? (firstArtifact.name || firstArtifact.artifact_id) : null
  }, [explicitSelectedArtifactName, selectedSessionArtifacts])
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
    () =>
      selectedSessionArtifacts.find((artifact) => artifact.name === selectedArtifactName)
      || selectedSessionArtifacts[0],
    [selectedArtifactName, selectedSessionArtifacts],
  )
  const selectedAgentTask = selectedSessionTasks.find((task) => task.task_id === selectedTaskId) || selectedSessionTasks[0]

  useEffect(() => {
    if (variant !== 'backend' || activeTab !== 'agentSessions' || !selectedSessionId || typeof window === 'undefined' || typeof EventSource === 'undefined') return undefined
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
  }, [queryClient, selectedSessionId, variant, activeTab])

  const selectedCount = selectedMaterialIds.length
  const selectedCsv = useMemo(() => selectedMaterialIds.join(','), [selectedMaterialIds])
  const parsedMaterialIds = useMemo(() => {
    const tokens = materialIdsText
      .split(/[,\s]+/)
      .map((item) => Number.parseInt(item.trim(), 10))
      .filter((item) => Number.isFinite(item) && item > 0)
    return Array.from(new Set(tokens))
  }, [materialIdsText])
  const materialTotalPages = Math.max(1, Math.ceil((adminMaterials.data?.total || 0) / Math.max(1, adminMaterials.data?.page_size || 20)))
  const graphExtension = useMemo(
    () => buildOpsGraphExtension(activeMaterialDetail.data, activeMaterialCardId, opsGraphExtensionLabels),
    [activeMaterialDetail.data, activeMaterialCardId, opsGraphExtensionLabels],
  )
  const health = runtimeStatus.data
  const runtimeChecks = health ? [
    ['database', health.database],
    ['database_pool', health.database_pool],
    ['elasticsearch', health.elasticsearch],
  ].filter((entry): entry is [string, string] => typeof entry[1] === 'string') : []
  const copyRuntimeDiagnosticPackage = async () => {
    if (!health) return
    const packageText = JSON.stringify(health, null, 2)
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
        throw new Error(t('opsPage.error.clipboardUnavailable'))
      }
      await navigator.clipboard.writeText(packageText)
      setErrorText('')
      setStatusText(t('opsPage.message.runtimeDiagnosticCopied'))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('opsPage.error.unknown')
      setStatusText(t('opsPage.message.runtimeDiagnosticCopyFailed'))
      setErrorText(message)
    }
  }

  const copyAdminPreviewEvidencePackage = async () => {
    const packageText = JSON.stringify(buildOpsAdminPreviewPackage(projectKey, adminPreview), null, 2)
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
        throw new Error(t('opsPage.error.clipboardUnavailable'))
      }
      await navigator.clipboard.writeText(packageText)
      setErrorText('')
      setStatusText(t('opsPage.message.adminPreviewEvidenceCopied'))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('opsPage.error.unknown')
      setStatusText(t('opsPage.message.adminPreviewEvidenceCopyFailed'))
      setErrorText(message)
    }
  }

  const toggleMaterialSelection = (materialId: number) => {
    setSelectedMaterialIds((prev) => (prev.includes(materialId) ? prev.filter((id) => id !== materialId) : [...prev, materialId]))
  }

  const selectCurrentPage = () => {
    const pageIds = (adminMaterials.data?.items || []).flatMap((item) => (
      !item.readonly ? [item.material_id] : []
    ))
    setSelectedMaterialIds(pageIds)
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
    setAdminPreview(null)
    setAdminPreviewAction('')
    setStatusText(formatOpsTemplate(t('opsPage.status.running'), { action: name }))
    try {
      const result = await fn()
      const previewOnly = Boolean(result && typeof result === 'object' && (result as { preview?: unknown }).preview === true)
      const submitted = !previewOnly && taskSubmission.track(result, name)
      if (hasAdminGovernanceEvidence(result)) {
        setAdminPreview(result)
        setAdminPreviewAction(actionKey)
      }
      setStatusText(
        previewOnly
          ? t('opsPage.status.previewModeNoExecution')
          : submitted
            ? formatOpsTemplate(t('opsPage.status.submittedWithTask'), { action: name, taskId: String((result as { task_id: string }).task_id) })
            : hasAdminGovernanceEvidence(result)
              ? t(getExecutionResultAvailable(result) ? 'opsPage.status.executionResultReadback' : 'opsPage.status.executionNotObserved')
              : formatOpsTemplate(t('opsPage.status.completed'), { action: name }),
      )
      if (options?.refreshStats !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.stats(projectKey) })
      }
      if (options?.refreshSearchHistory !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.searchHistory(projectKey) })
      }
      if (options?.refreshDocuments !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.materialsBase(projectKey) })
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

  const runAdminPreview = async (actionKey: OpsActionKey, fn: () => Promise<AdminActionResponse>) => {
    const name = actionName(actionKey)
    setPending(true)
    setActiveAction(actionKey)
    setErrorText('')
    setStatusText(formatOpsTemplate(t('opsPage.status.previewRunning'), { action: name }))
    try {
      const result = await fn()
      setAdminPreview(result)
      setAdminPreviewAction(actionKey)
      setStatusText(formatOpsTemplate(t('opsPage.status.previewReady'), {
        action: name,
        sourceRefs: getAdminPreviewSourceRefCount(result),
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('opsPage.error.unknown')
      setStatusText(formatOpsTemplate(t('opsPage.status.previewFailed'), { action: name }))
      setErrorText(message)
    } finally {
      setPending(false)
      setActiveAction('')
    }
  }

  const parseExtractedJson = () => {
    try {
      return JSON.parse(extractJsonText || '{}') as unknown
    } catch {
      throw new Error(t('opsPage.error.invalidJson'))
    }
  }

  return (
    <div className={`content-stack gv2-root ops-page ops-page--${variant}`}>
      <header className="ops-management-header">
        <div className="panel-header">
          <h2>{variant === 'backend' ? t('opsPage.title.backend') : t('opsPage.title.ops')}</h2>
          <a className="ops-management-link" href={variant === 'backend' ? '#/admin/ops' : '#/admin/backend'}>
            {t(variant === 'backend' ? 'opsPage.status.opsLink' : 'opsPage.status.backendLink')}
            <ArrowUpRight size={15} aria-hidden="true" />
          </a>
        </div>
        <p className="status-line" data-testid="ops-scope-label">
          {variant === 'backend'
            ? (isZhLocale
              ? '系统运行：全局后端服务、worker、队列与健康观测。当前项目仅作为查询上下文。'
              : 'System runtime: global backend services, workers, queues, and health observations. The current project is query context only.')
            : (isZhLocale
              ? '资料与质量：当前项目绑定的资料、质量结果与已授权操作。全局资源会单独标注。'
              : 'Materials and quality: materials, quality results, and authorized operations bound to this project. Global resources are labeled separately.')}
        </p>
      </header>
      <nav className="ops-management-tabs" role="tablist" aria-label={variant === 'backend' ? t('opsPage.title.backend') : t('opsPage.title.ops')}>
        {managementTabs.map((tab) => (
          <button key={tab} id={`ops-tab-${tab}`} type="button" role="tab" tabIndex={activeTab === tab ? 0 : -1} aria-selected={activeTab === tab} aria-controls={`ops-view-${tab}`} onClick={() => setRequestedTab(tab)} onKeyDown={(event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
            event.preventDefault()
            const index = managementTabs.indexOf(tab)
            const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? managementTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + managementTabs.length) % managementTabs.length
            const nextTab = managementTabs[nextIndex]
            setRequestedTab(nextTab)
            document.getElementById(`ops-tab-${nextTab}`)?.focus()
          }}>
            {t(OPS_MANAGEMENT_TAB_KEYS[tab])}
          </button>
        ))}
      </nav>
      <TaskSubmissionNotice submission={taskSubmission} />
      {statusText !== t('opsPage.status.ready') && <p className="status-line ops-action-status" role="status">{statusText}</p>}
      {!!errorText && <p className="status-line ops-action-status" role="alert">{errorText}</p>}
      {variant === 'ops' && <section className="kpi-grid ops-management-metrics">
        <article className="kpi-card"><span>{t('opsPage.kpi.documents')}</span><strong>{adminStats.data?.materials?.total ?? '-'}</strong><small>{formatOpsTemplate(t('opsPage.kpi.todayCount'), { count: adminStats.data?.materials?.recent_today ?? '-' })}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.socialDocuments')}</span><strong>{adminStats.data?.social_data?.total ?? '-'}</strong><small>{formatOpsTemplate(t('opsPage.kpi.todayCount'), { count: adminStats.data?.social_data?.recent_today ?? '-' })}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.sources')}</span><strong>{adminStats.data?.sources?.total ?? '-'}</strong><small>{t('opsPage.kpi.resourcePool')}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.searchHistory')}</span><strong>{adminStats.data?.search_history?.total ?? '-'}</strong><small>{t('opsPage.kpi.history')}</small></article>
      </section>}
      {variant === 'ops' && adminStats.isError && <p className="status-line" role="alert">{adminStats.error.message}</p>}

      {variant === 'ops' && activeTab === 'insights' ? <ProjectRetrievalPanel key={projectKey} projectKey={projectKey} /> : null}

      {variant === 'backend' && activeTab === 'runtime' && <section id="ops-view-runtime" role="tabpanel" aria-labelledby="ops-tab-runtime" className={`panel ops-runtime-panel ops-runtime-panel--${variant}`}>
        <div className="panel-header">
          <div>
            <h2>{t('opsPage.section.runtimeStatus')}</h2>
            <p className="muted">{isZhLocale ? '全局后端观测 / 当前项目运行上下文' : 'Global backend observation / current project runtime context'}</p>
          </div>
          <div className="inline-actions">
            {health ? <span className={health.status === 'ok' ? 'chip chip-ok' : 'chip chip-warn'}>{health.status}</span> : null}
            <button type="button" disabled={!health || runtimeStatus.isError} onClick={() => void copyRuntimeDiagnosticPackage()}>
              {t('opsPage.action.copyRuntimeDiagnosticPackage')}
            </button>
            <button type="button" onClick={() => { void runtimeStatus.refetch() }}>
              <RefreshCw size={14} />
              {t('opsPage.action.refresh')}
            </button>
          </div>
        </div>
        {runtimeStatus.isError && <p className="status-line" role="alert">{runtimeStatus.error.message}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('opsPage.field.service')}</th>
                <th>{t('opsPage.field.status')}</th>
              </tr>
            </thead>
            <tbody>
              {runtimeChecks.map(([name, status]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td><span className={status === 'ok' ? 'chip chip-ok' : statusClass(status)}>{status}</span></td>
                </tr>
              ))}
              {!runtimeChecks.length ? (
                <tr>
                  <td colSpan={2} className="empty-cell">
                    {runtimeStatus.isLoading ? t('opsPage.status.loading') : t('opsPage.empty.runtimeStatus')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>}

      {variant === 'backend' && activeTab === 'agentSessions' && <section id="ops-view-agentSessions" role="tabpanel" aria-labelledby="ops-tab-agentSessions" className="panel ops-agent-session-panel">
        {[agentSessionsQuery.error, selectedSessionQuery.error, createSessionMutation.error, cancelSessionMutation.error, resolveApprovalMutation.error].filter(Boolean).map((error, index) => (
          <p className="status-line" role="alert" key={index}>{error?.message}</p>
        ))}
        <div className="panel-header">
          <h2>
            <Eye size={15} />
            {t('opsPage.section.agentSessions')}
          </h2>
          <p className="muted">{isZhLocale ? 'Agent session 是操作记录，不代表项目状态。' : 'Agent sessions are operation records, not project state.'}</p>
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
                createSessionMutation.mutate()
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
                    createSessionMutation.mutate()
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
                            setSelectedArtifactName(null)
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
                      cancelSessionMutation.mutate(selectedSessionId)
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
                  {selectedArtifact ? (
                    <pre style={{ ...detailPreStyle, maxHeight: 220 }}>{getArtifactPreview(selectedArtifact)}</pre>
                  ) : (
                    <div className="empty-cell">{t('opsPage.empty.selectedArtifact')}</div>
                  )}
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
                                    resolveApprovalMutation.mutate({ approvalId: approval.approval_id, approved: true })
                                  }}
                                  disabled={resolveApprovalMutation.isPending}
                                >
                                  <CheckCircle2 size={14} />
                                  {t('opsPage.action.approve')}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    resolveApprovalMutation.mutate({ approvalId: approval.approval_id, approved: false })
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
                    <h4>{t('opsPage.section.sessionMessages')}</h4>
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
      </section>}

      {variant === 'ops' && activeTab === 'governance' && <section id="ops-view-governance" role="tabpanel" aria-labelledby="ops-tab-governance" className="panel ops-governance-panel">
        <div className="panel-header"><h2>{t('opsPage.section.governanceActions')}</h2></div>
        <div className="inline-actions">
          <label><span>retention_days</span><input type="number" min={1} max={3650} value={retentionDays} onChange={(e) => setRetentionDays(Number.parseInt(e.target.value || '90', 10) || 90)} /></label>
          <label>
            <span>material_ids</span>
            <input type="text" value={materialIdsText} onChange={(e) => setMaterialIdsText(e.target.value)} placeholder="101,102,103" />
          </label>
          <button
            disabled={!selectedCount}
            onClick={() => setMaterialIdsText(selectedCsv)}
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
              const materialIds = parsedMaterialIds
              runAction('reExtract', () => reExtractMaterials(materialIds.length ? { material_ids: materialIds } : {}))
            }}
          >
            <RefreshCw size={14} />{activeAction === 'reExtract' ? t('opsPage.action.running') : t('opsPage.action.reExtract')}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const materialIds = parsedMaterialIds
              const topics: Array<'company' | 'product' | 'operation'> = topicScope === 'all' ? ['company', 'product', 'operation'] : [topicScope]
              const payload = {
                topics,
                ...(materialIds.length ? { material_ids: materialIds } : {}),
              }
              runAction('topicExtract', () => topicExtractMaterials(payload))
            }}
          >
            <RefreshCw size={14} />{activeAction === 'topicExtract' ? t('opsPage.action.running') : t('opsPage.action.topicExtract')}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const materialIds = parsedMaterialIds
              if (!materialIds.length) {
                setStatusText(formatOpsTemplate(t('opsPage.status.failed'), { action: actionName('graphExport') }))
                setErrorText(t('opsPage.error.missingMaterialIds'))
                return
              }
              runAction(
                'graphExport',
                async () => {
                  const result = await exportGraph(materialIds)
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
          <button onClick={() => { queryClient.invalidateQueries({ queryKey: queryKeys.admin.stats(projectKey) }); queryClient.invalidateQueries({ queryKey: queryKeys.admin.searchHistory(projectKey) }); }}><RefreshCw size={14} />{t('opsPage.action.refresh')}</button>
        </div>
      </section>}

      {variant === 'ops' && activeTab === 'materials' && <section id="ops-view-materials" role="tabpanel" aria-labelledby="ops-tab-materials" className="panel ops-materials-panel">
        <div className="panel-header">
          <h2>{t('opsPage.section.documentGovernance')}</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.admin.materialsBase(projectKey) })} disabled={adminMaterials.isFetching}>
              <RefreshCw size={14} />
              {adminMaterials.isFetching ? t('opsPage.action.refreshing') : t('opsPage.action.refreshMaterials')}
            </button>
            <button onClick={selectCurrentPage} disabled={!(adminMaterials.data?.items || []).length}>{t('opsPage.action.selectCurrentPage')}</button>
            <button onClick={() => setSelectedMaterialIds([])} disabled={!selectedCount}>{t('opsPage.action.clearSelection')}</button>
            <button type="button" aria-expanded={showMaterialTools} aria-controls="ops-material-tools" onClick={() => setShowMaterialTools((visible) => !visible)}>
              {showMaterialTools ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              {t(showMaterialTools ? 'opsPage.action.hideAdvancedDetails' : 'opsPage.action.showAdvancedDetails')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>material_type</span>
            <input value={materialTypeFilter} onChange={(e) => { setMaterialTypeFilter(e.target.value); setMaterialPage(1) }} placeholder={t('opsPage.placeholder.materialType')} />
          </label>
          <label>
            <span>state</span>
            <input value={materialStateFilter} onChange={(e) => { setMaterialStateFilter(e.target.value); setMaterialPage(1) }} placeholder="state" />
          </label>
          <label>
            <span>search</span>
            <input value={materialSearch} onChange={(e) => { setMaterialSearch(e.target.value); setMaterialPage(1) }} placeholder={t('opsPage.placeholder.titleKeyword')} />
          </label>
          {showMaterialTools && <label>
            <span>extract_mode</span>
            <select value={extractMode} onChange={(e) => setExtractMode(e.target.value as 'replace' | 'merge')}>
              <option value="merge">merge</option>
              <option value="replace">replace</option>
            </select>
          </label>}
        </div>
        {showMaterialTools && <div id="ops-material-tools" className="form-grid cols-2 ops-material-tools">
          <label>
            <span>extracted_data(JSON)</span>
            <textarea rows={6} value={extractJsonText} onChange={(e) => setExtractJsonText(e.target.value)} />
          </label>
          <div className="inline-actions">
            <button
              disabled={pending || !selectedCount}
              onClick={() => {
                void runAdminPreview('bulkStructuredWrite', () =>
                  bulkUpdateMaterialExtractedData({
                    material_ids: selectedMaterialIds,
                    mode: extractMode,
                    extracted_data: parseExtractedJson(),
                    preview: true,
                  }),
                )
              }}
            >
              {t('opsPage.action.previewBulkWriteStructured')}
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => {
                void runAction('bulkStructuredWrite', async () =>
                  bulkUpdateMaterialExtractedData({
                    material_ids: selectedMaterialIds,
                    mode: extractMode,
                    extracted_data: parseExtractedJson(),
                  }),
                )
              }}
            >
              {t('opsPage.action.bulkWriteStructured')}
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() =>
                void runAdminPreview('deleteMaterials', () =>
                  deleteAdminMaterials({ material_ids: selectedMaterialIds, preview: true }),
                )
              }
            >
              {t('opsPage.action.previewDeleteDocuments')}
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('clearStructured', () => clearMaterialExtractedData(selectedMaterialIds))}
            >
              {t('opsPage.action.clearStructured')}
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('deleteMaterials', () => deleteAdminMaterials({ material_ids: selectedMaterialIds }))}
            >
              {t('opsPage.action.deleteDocuments')}
            </button>
          </div>
        </div>}
        {adminPreview ? (
          <section className="ops-governance-evidence" data-testid="ops-material-governance-preview" style={{ marginTop: 16 }}>
            <div className="panel-header">
              <h3>{t('opsPage.section.adminGovernanceEvidence')}</h3>
              <div className="inline-actions">
                <span className="chip">{actionName(adminPreviewAction || 'deleteMaterials')}</span>
                <span className="chip">
                  {adminPreview.preview ? t('opsPage.status.previewEvidence') : t('opsPage.status.executionEvidence')}
                </span>
                <button
                  type="button"
                  data-testid="ops-copy-preview-evidence-package"
                  onClick={() => void copyAdminPreviewEvidencePackage()}
                >
                  {t('opsPage.action.copyPreviewEvidencePackage')}
                </button>
              </div>
            </div>
            <div className="kpi-grid" style={{ marginTop: 0 }}>
              <article className="kpi-card">
                <span>{t('opsPage.field.actionKind')}</span>
                <strong>{getAdminPreviewActionKind(adminPreview, adminPreviewAction || '-')}</strong>
                <small>{formatOpsTemplate(t('opsPage.metric.wouldAffectCount'), { count: adminPreview.would_affect_count ?? adminPreview.requested ?? 0 })}</small>
              </article>
              <article className="kpi-card">
                <span>{t('opsPage.field.riskLabels')}</span>
                <strong>{getAdminPreviewRiskLabels(adminPreview).join(', ') || '-'}</strong>
                <small>{formatOpsTemplate(t('opsPage.metric.riskLabelCount'), { count: getAdminPreviewRiskLabels(adminPreview).length })}</small>
              </article>
              <article className="kpi-card">
                <span>{t('opsPage.field.sourceRefs')}</span>
                <strong>{getAdminPreviewSourceRefCount(adminPreview)}</strong>
                <small>{adminPreview.source_query ? t('opsPage.status.sourceQueryAvailable') : t('opsPage.status.sourceQueryMissing')}</small>
              </article>
              <article className="kpi-card">
                <span>{t('opsPage.field.executionResultAvailable')}</span>
                <strong>{String(getExecutionResultAvailable(adminPreview))}</strong>
                <small>{adminPreview.preview ? t('opsPage.status.previewModeNoExecution') : t(getExecutionResultAvailable(adminPreview) ? 'opsPage.status.executionResultReadback' : 'opsPage.status.executionNotObserved')}</small>
              </article>
            </div>
            <div className="grid-2" style={{ alignItems: 'start' }}>
              <div>
                <strong>{t('opsPage.field.traceAction')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 160 }}>
                  {getAdminPreviewTraceLabel(adminPreview)}
                </pre>
              </div>
              <div>
                <strong>{t('opsPage.field.sourceQuery')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 160 }}>
                  {adminPreview.source_query ? JSON.stringify(adminPreview.source_query, null, 2) : '-'}
                </pre>
              </div>
              <div>
                <strong>{t('opsPage.field.sourceRefs')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                  {JSON.stringify(adminPreview.source_refs || [], null, 2)}
                </pre>
              </div>
              <div>
                <strong>{t('opsPage.field.evidencePreview')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                  {JSON.stringify(adminPreview.evidence_preview || {}, null, 2)}
                </pre>
              </div>
              <div>
                <strong>{t('opsPage.field.executionResult')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                  {JSON.stringify(adminPreview.execution_result || {}, null, 2)}
                </pre>
              </div>
              <div>
                <strong>{t('opsPage.field.auditTrail')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                  {JSON.stringify(adminPreview.audit_event || adminPreview.audit_trail || {}, null, 2)}
                </pre>
              </div>
              <div>
                <strong>{t('opsPage.field.rollbackHint')}</strong>
                <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                  {JSON.stringify(adminPreview.rollback_hint || adminPreview.rollback_recommendation || {}, null, 2)}
                </pre>
              </div>
            </div>
          </section>
        ) : null}
        <p className="status-line">{formatOpsTemplate(t('opsPage.metric.selectedMaterials'), { count: selectedCount })}</p>
        {adminMaterials.isError && <p className="status-line" role="alert">{adminMaterials.error.message}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('opsPage.field.selected')}</th>
                <th>ID</th>
                <th>{t('opsPage.field.title')}</th>
                <th>{t('opsPage.field.sourceUrl')}</th>
                <th>{t('opsPage.field.type')}</th>
                <th>{t('opsPage.field.state')}</th>
                <th>{t('opsPage.field.extraction')}</th>
                <th>{t('opsPage.field.updated')}</th>
              </tr>
            </thead>
            <tbody>
              {(adminMaterials.data?.items || []).map((row) => (
                <tr
                  key={row.material_id}
                  onClick={() => {
                    if (row.readonly) return
                    const candidateId = row.material_id
                    const nextId: number | null = activeMaterialCardId === candidateId ? null : candidateId
                    setActiveMaterialCardId((prev) => {
                      return prev === candidateId ? null : candidateId
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
                      aria-label={`${t('opsPage.field.selected')} ${row.material_id}`}
                      checked={selectedMaterialIds.includes(row.material_id)}
                      onChange={() => toggleMaterialSelection(row.material_id)}
                      disabled={row.readonly}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td>{row.material_id}</td>
                  <td>{row.title || '-'}</td>
                  <td>
                    {row.uri ? (
                      <a href={row.uri} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                        {row.uri}
                      </a>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td>{row.material_type || '-'}</td>
                  <td>{row.state || '-'}</td>
                  <td>{String(row.has_extracted_data ?? false)}</td>
                  <td>{formatDate(row.updated_at, locale)}</td>
                </tr>
              ))}
              {!adminMaterials.data?.items?.length ? (
                <tr>
                  <td colSpan={8} className="empty-cell">{adminMaterials.isLoading ? t('opsPage.status.loading') : adminMaterials.isError ? t('opsPage.error.unknown') : t('opsPage.empty.materials')}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="inline-actions">
          <button disabled={materialPage <= 1} onClick={() => setMaterialPage((p) => Math.max(1, p - 1))}>{t('opsPage.action.previousPage')}</button>
          <span className="chip">{formatOpsTemplate(t('opsPage.metric.pageOf'), { page: materialPage, total: materialTotalPages })}</span>
          <button disabled={materialPage >= materialTotalPages} onClick={() => setMaterialPage((p) => Math.min(materialTotalPages, p + 1))}>{t('opsPage.action.nextPage')}</button>
        </div>
      </section>}

      {variant === 'ops' && activeTab === 'insights' && <section id="ops-view-insights" role="tabpanel" aria-labelledby="ops-tab-insights" className="panel ops-search-history-panel">
        <div className="panel-header"><h2>{t('opsPage.section.searchHistory')}</h2></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>{t('opsPage.field.topic')}</th><th>{t('opsPage.field.lastSearchTime')}</th></tr></thead>
            <tbody>
              {(searchHistory.data || []).map((row) => (
                <tr key={row.id}><td>{row.id}</td><td>{row.topic || '-'}</td><td>{formatDate(row.last_search_time, locale)}</td></tr>
              ))}
              {!searchHistory.data?.length && <tr><td colSpan={3} className="empty-cell">{searchHistory.isLoading ? t('opsPage.status.loading') : t('opsPage.empty.searchHistory')}</td></tr>}
            </tbody>
          </table>
        </div>
        {searchHistory.isError && <p className="status-line" role="alert">{searchHistory.error.message}</p>}
      </section>}

      {variant === 'ops' && activeTab === 'materials' && activeMaterialCardId ? (
        <GraphNodeCard
          title={activeMaterialDetail.data?.title || formatOpsTemplate(t('opsPage.fallback.materialTitle'), { materialId: activeMaterialCardId })}
          subtitle={activeMaterialDetail.data?.material_type || '-'}
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
                  void queryClient.invalidateQueries({ queryKey: queryKeys.admin.materialDetail(projectKey, activeMaterialCardId) })
                }}
                title={t('opsPage.action.refresh')}
              >
                <RefreshCw size={14} aria-hidden="true" />
              </button>
            </div>
          }
          onClose={() => {
            setActiveMaterialCardId(null)
            setOpsCardTab('business')
          }}
        >
          {activeMaterialDetail.isFetching ? (
            <div className="gv2-node-grid">
              <div className="gv2-node-grid-item">
                <label>{t('opsPage.field.status')}</label>
                <strong>{t('opsPage.status.loading')}</strong>
              </div>
            </div>
          ) : (
            <>
              {opsCardTab === 'business' ? <GraphBusinessCardSections node={toGraphBusinessNode(activeMaterialDetail.data, activeMaterialCardId, opsGraphExtensionLabels)} /> : null}
              {opsCardTab === 'graph_ext' ? (
                <GraphExtensionsSections
                  key={`ops-graph-ext-${activeMaterialCardId || 'none'}`}
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
