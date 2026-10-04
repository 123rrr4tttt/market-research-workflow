import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Eye, RefreshCw, Trash2, XCircle } from 'lucide-react'
import GraphNodeCard from '../components/graph-kit/GraphNodeCard'
import GraphBusinessCardSections from '../components/GraphBusinessCardSections'
import GraphExtensionsSections from '../components/GraphExtensionsSections'
import ProjectRetrievalPanel from './ProjectRetrievalPanel'
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
  BusinessLineEvidenceMatrix,
  BusinessLineEvidenceMatrixLine,
  BusinessLineScheduledArtifactDrilldown,
  BusinessLineScheduledArtifactDrilldownArtifact,
  BusinessLineScheduledArtifactDrilldownLane,
  BusinessLineScheduledArtifactLaneSummary,
  BusinessLineScheduledArtifactSummaries,
  BusinessLineScheduledMatrixArtifactSummary,
  DocumentItem,
} from '../lib/types'
import { buildRuntimeDiagnosticPackage, collectRuntimeMissingDependencies, runtimeHealthTarget } from '../lib/runtimeDiagnostic'
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
  getBusinessLineEvidenceMatrix,
  getBusinessLineScheduledArtifactDrilldown,
  getBusinessLineScheduledArtifactSummaries,
  getBusinessLineScheduledMatrixArtifactSummary,
  getHealth,
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
type ScheduledArtifactDrilldownLaneFilter = 'all' | 'warning_only'
type ScheduledArtifactDrilldownLaneSort = 'source_order' | 'warning_priority' | 'warning_count' | 'artifact_count'

const SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_TITLE = 'empty warning view: no lanes match the current warning-only filter and lane sort'
const SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_LINES = [
  'empty warning view is not scheduled evidence passed',
  'scheduled_completion_proof unchanged',
  'only scheduled_run_evidence can close scheduled evidence',
]
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
  activeDocId: number | string | null,
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
  activeDocId: number | string | null,
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
    return true
  }
  return Boolean(value.evidence_preview?.execution_result_available)
}

function matrixFieldCount(value: unknown) {
  if (Array.isArray(value)) return value.length
  if (value && typeof value === 'object') return Object.keys(value).length
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim()) return 1
  return 0
}

function matrixTextValue(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value && typeof value === 'object') return JSON.stringify(value)
  return ''
}

function matrixTextList(value: unknown) {
  if (Array.isArray(value)) {
    return value.map(matrixTextValue).filter(Boolean)
  }
  if (typeof value === 'string') {
    return value.trim() ? [value.trim()] : []
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).map(([key, item]) => `${key}: ${matrixTextValue(item)}`).filter(Boolean)
  }
  return []
}

function matrixCoverageStatement(value: BusinessLineEvidenceMatrix | null | undefined) {
  const coverage = value?.coverage
  if (!coverage || typeof coverage !== 'object' || Array.isArray(coverage)) return ''
  const record = coverage as Record<string, unknown>
  const coveredCount = Number(record.covered_line_count)
  const keys = Array.isArray(record.covered_line_keys) ? record.covered_line_keys : []
  if (!Number.isFinite(coveredCount) || coveredCount <= 0 || keys.length !== coveredCount) return ''
  const notAdminOnly = record.not_admin_only === true
  return `覆盖所有条线（covered_line_count=${coveredCount}）；not_admin_only=${notAdminOnly}`
}

function matrixLineTestId(line: BusinessLineEvidenceMatrixLine) {
  return ['ops', 'business', 'line', 'evidence', 'matrix', 'line', line.line_key].join('-')
}

function matrixClassificationBoundaryList(value: unknown) {
  return matrixTextList(value)
}

function scheduledMatrixArtifactLabel(value: unknown, fallback = '-') {
  const label = matrixTextValue(value)
  return label || fallback
}

function scheduledMatrixArtifactPath(
  value: BusinessLineScheduledMatrixArtifactSummary | BusinessLineScheduledArtifactLaneSummary | null | undefined,
) {
  const artifactPath = typeof value?.artifact_path === 'string' ? value.artifact_path.trim() : ''
  return artifactPath || '<missing>'
}

function scheduledMatrixArtifactClass(
  value: (
    BusinessLineScheduledMatrixArtifactSummary
    | BusinessLineScheduledArtifactLaneSummary
    | BusinessLineScheduledArtifactSummaries
    | null
    | undefined
  ),
) {
  const key = String(value?.lane_classification || value?.status || '').toLowerCase()
  if (key === 'scheduled_run_evidence' || key === 'evidence' || key === 'passed' || key === 'ready') return 'chip chip-ok'
  if (key === 'scheduled_run_blocked' || key === 'blocked' || key === 'failed' || key === 'error') return 'chip chip-danger'
  return 'chip chip-warn'
}

function scheduledArtifactLaneRows(value: BusinessLineScheduledArtifactSummaries | null | undefined) {
  return Array.isArray(value?.lanes) ? value.lanes : []
}

function scheduledArtifactDrilldownLaneRows(value: BusinessLineScheduledArtifactDrilldown | null | undefined) {
  return Array.isArray(value?.lanes) ? value.lanes : []
}

function scheduledArtifactDrilldownLaneHasWarning(lane: BusinessLineScheduledArtifactDrilldownLane) {
  const warningCount = typeof lane.identity_warning_count === 'number' && Number.isFinite(lane.identity_warning_count)
    ? lane.identity_warning_count
    : 0
  const highestSeverityRank = typeof lane.identity_warning_highest_severity_rank === 'number' && Number.isFinite(lane.identity_warning_highest_severity_rank)
    ? lane.identity_warning_highest_severity_rank
    : 0
  return warningCount > 0 || highestSeverityRank > 0
}

function scheduledArtifactDrilldownLaneMetric(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function scheduledArtifactDrilldownLaneName(lane: BusinessLineScheduledArtifactDrilldownLane) {
  return String(lane.lane || '')
}

function scheduledArtifactDrilldownLaneArtifactCount(lane: BusinessLineScheduledArtifactDrilldownLane) {
  return scheduledArtifactDrilldownLaneMetric(lane.artifact_count) || scheduledArtifactDrilldownArtifacts(lane).length
}

function scheduledArtifactDrilldownLaneWarningCount(lane: BusinessLineScheduledArtifactDrilldownLane) {
  return scheduledArtifactDrilldownLaneMetric(lane.identity_warning_count)
}

function scheduledArtifactDrilldownLaneSeverityRank(lane: BusinessLineScheduledArtifactDrilldownLane) {
  return scheduledArtifactDrilldownLaneMetric(lane.identity_warning_highest_severity_rank)
}

function compareScheduledArtifactDrilldownLanes(
  left: BusinessLineScheduledArtifactDrilldownLane,
  right: BusinessLineScheduledArtifactDrilldownLane,
  metrics: Array<(lane: BusinessLineScheduledArtifactDrilldownLane) => number>,
) {
  for (const metric of metrics) {
    const diff = metric(right) - metric(left)
    if (diff !== 0) return diff
  }
  return scheduledArtifactDrilldownLaneName(left).localeCompare(scheduledArtifactDrilldownLaneName(right))
}

function sortScheduledArtifactDrilldownLanes(
  lanes: BusinessLineScheduledArtifactDrilldownLane[],
  sortMode: ScheduledArtifactDrilldownLaneSort,
) {
  if (sortMode === 'source_order') return lanes
  const sorted = [...lanes]
  if (sortMode === 'warning_priority') {
    return sorted.sort((left, right) => compareScheduledArtifactDrilldownLanes(left, right, [
      scheduledArtifactDrilldownLaneSeverityRank,
      scheduledArtifactDrilldownLaneWarningCount,
      scheduledArtifactDrilldownLaneArtifactCount,
    ]))
  }
  if (sortMode === 'warning_count') {
    return sorted.sort((left, right) => compareScheduledArtifactDrilldownLanes(left, right, [
      scheduledArtifactDrilldownLaneWarningCount,
      scheduledArtifactDrilldownLaneSeverityRank,
      scheduledArtifactDrilldownLaneArtifactCount,
    ]))
  }
  return sorted.sort((left, right) => compareScheduledArtifactDrilldownLanes(left, right, [
    scheduledArtifactDrilldownLaneArtifactCount,
    scheduledArtifactDrilldownLaneWarningCount,
    scheduledArtifactDrilldownLaneSeverityRank,
  ]))
}

function scheduledArtifactDrilldownLaneSortExplanation(sortMode: ScheduledArtifactDrilldownLaneSort) {
  if (sortMode === 'source_order') {
    return 'source order from API payload; display order only; scheduled_completion_proof unchanged; not proof'
  }
  if (sortMode === 'warning_priority') {
    return 'sorted by highest severity rank desc, warning count desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof'
  }
  if (sortMode === 'warning_count') {
    return 'sorted by warning count desc, severity rank desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof'
  }
  return 'sorted by artifact count desc, warning count desc, severity rank desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof'
}

function isScheduledArtifactDrilldownEmptyWarningView(
  filter: ScheduledArtifactDrilldownLaneFilter,
  visibleLanes: BusinessLineScheduledArtifactDrilldownLane[],
  lanes: BusinessLineScheduledArtifactDrilldownLane[],
) {
  return filter === 'warning_only' && visibleLanes.length === 0 && lanes.length > 0
}

function scheduledArtifactDrilldownArtifacts(lane: BusinessLineScheduledArtifactDrilldownLane) {
  return Array.isArray(lane.artifacts) ? lane.artifacts : []
}

function scheduledArtifactSizeLabel(sizeBytes: unknown) {
  if (typeof sizeBytes !== 'number' || !Number.isFinite(sizeBytes) || sizeBytes < 0) return '-'
  if (sizeBytes < 1024) return `${sizeBytes} B`
  const units = ['KiB', 'MiB', 'GiB', 'TiB']
  let value = sizeBytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`
}

function scheduledArtifactSha256Label(sha256: unknown) {
  if (typeof sha256 !== 'string') return '-'
  const hash = sha256.trim()
  if (!hash) return '-'
  return `sha256: ${hash.length > 20 ? `${hash.slice(0, 12)}...${hash.slice(-8)}` : hash}`
}

function scheduledArtifactFreshnessRows(artifact: BusinessLineScheduledArtifactDrilldownArtifact) {
  const windowSize = typeof artifact.freshness_window_size === 'number' && Number.isFinite(artifact.freshness_window_size)
    ? artifact.freshness_window_size
    : null
  const rank = typeof artifact.freshness_rank === 'number' && Number.isFinite(artifact.freshness_rank)
    ? `rank ${artifact.freshness_rank}${windowSize ? `/${windowSize}` : ''}`
    : 'rank -'
  const latest = artifact.is_latest_for_lane == null
    ? 'latest unknown'
    : artifact.is_latest_for_lane
      ? 'latest'
      : 'stale'
  const identity = artifact.identity_matches_latest == null
    ? 'identity unknown'
    : artifact.identity_matches_latest
      ? 'identity match'
      : 'identity mismatch'
  const identityStatus = scheduledMatrixArtifactLabel(artifact.identity_status, '')
  const identityWarning = scheduledMatrixArtifactLabel(artifact.identity_warning, '')
  const identityWarningSeverity = scheduledMatrixArtifactLabel(artifact.identity_warning_severity, '')
  const identityWarningMessage = scheduledMatrixArtifactLabel(artifact.identity_warning_message, '')
  const latestPath = scheduledMatrixArtifactLabel(artifact.latest_artifact_path, '')
  const rows = [rank, latest, identity]
  if (identityStatus) rows.push(`identity status: ${identityStatus}`)
  if (identityWarning) rows.push(`identity warning: ${identityWarning}`)
  if (identityWarningSeverity) rows.push(`identity warning severity: ${identityWarningSeverity}`)
  if (identityWarningMessage) rows.push(`identity warning message: ${identityWarningMessage}`)
  if (latestPath) rows.push(`latest path: ${latestPath}`)
  return rows
}

function scheduledArtifactDiagnosticsRows(value: unknown) {
  const diagnostics = normalizeObject(value)
  const preferred = ['runtime_preflight_status', 'matrix_exit_code', 'first_blocked_reason', 'artifact_count']
  const keys = [
    ...preferred.filter((key) => Object.prototype.hasOwnProperty.call(diagnostics, key)),
    ...Object.keys(diagnostics).filter((key) => !preferred.includes(key) && key !== 'absolute_path').slice(0, 6),
  ]
  return keys.map((key) => [key, scheduledMatrixArtifactLabel(diagnostics[key])] as const)
}

function scheduledMatrixArtifactError(error: unknown) {
  if (!error) return ''
  return error instanceof Error ? error.message : String(error)
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

function runtimeModeClass(mode?: string | null) {
  const key = String(mode || '').toLowerCase()
  if (key === 'mixed') return 'chip chip-danger'
  if (key === 'docker' || key === 'local') return 'chip chip-ok'
  return 'chip chip-warn'
}

export default function OpsPage({ projectKey, variant = 'ops' }: OpsPageProps) {
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
  const [adminPreview, setAdminPreview] = useState<AdminActionResponse | null>(null)
  const [adminPreviewAction, setAdminPreviewAction] = useState<OpsActionKey | ''>('')
  const [sessionGoal, setSessionGoal] = useState(() => t('opsPage.default.sessionGoal'))
  const [sessionSource, setSessionSource] = useState<'user' | 'agent_batch' | 'workflow_graph'>('user')
  const [sessionCompatMode, setSessionCompatMode] = useState(false)
  const [explicitSelectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [explicitSelectedArtifactName, setSelectedArtifactName] = useState<string | null>(null)
  const [selectedEnforcementEventKey, setSelectedEnforcementEventKey] = useState<string | null>(null)
  const [scheduledArtifactDrilldownLaneFilter, setScheduledArtifactDrilldownLaneFilter] = useState<ScheduledArtifactDrilldownLaneFilter>('all')
  const [scheduledArtifactDrilldownLaneSort, setScheduledArtifactDrilldownLaneSort] = useState<ScheduledArtifactDrilldownLaneSort>('source_order')
  const [scheduledArtifactDrilldownUiEventLog, setScheduledArtifactDrilldownUiEventLog] = useState<string[]>([])
  const [showTechnicalDiagnostics, setShowTechnicalDiagnostics] = useState(variant === 'backend')
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
  const runtimeStatus = useQuery({ queryKey: queryKeys.health.all, queryFn: getHealth })
  const businessLineEvidenceMatrix = useQuery({
    queryKey: ['business-line-evidence-matrix', projectKey],
    queryFn: getBusinessLineEvidenceMatrix,
    enabled: Boolean(projectKey),
  })
  const scheduledMatrixArtifactSummary = useQuery({
    queryKey: ['business-line-scheduled-matrix-artifact-summary', projectKey],
    queryFn: getBusinessLineScheduledMatrixArtifactSummary,
    enabled: Boolean(projectKey),
  })
  const scheduledArtifactSummaries = useQuery({
    queryKey: ['business-line-scheduled-artifact-summaries', projectKey],
    queryFn: getBusinessLineScheduledArtifactSummaries,
    enabled: Boolean(projectKey),
  })
  const scheduledArtifactDrilldown = useQuery({
    queryKey: ['business-line-scheduled-artifact-drilldown', projectKey],
    queryFn: getBusinessLineScheduledArtifactDrilldown,
    enabled: Boolean(projectKey),
  })
  const searchHistory = useQuery({ queryKey: queryKeys.admin.searchHistory(projectKey), queryFn: () => getSearchHistory(1, 30), enabled: Boolean(projectKey) })
  const agentSessionsQuery = useQuery({
    queryKey: queryKeys.agentSessions.list(),
    queryFn: listAgentSessions,
  })
  const normalizedSessions = useMemo(
    () => normalizeSessionList(agentSessionsQuery.data || undefined),
    [agentSessionsQuery.data],
  )
  const selectedSessionId = explicitSelectedSessionId ?? normalizedSessions[0]?.session_id ?? null
  const adminDocuments = useQuery({
    queryKey: queryKeys.admin.documents(projectKey, docPage, docTypeFilter, docStateFilter, docSearch),
    queryFn: () =>
      listAdminDocuments({
        page: docPage,
        page_size: 20,
        doc_type: docTypeFilter.trim() || null,
        state: docStateFilter.trim() || null,
        search: docSearch.trim() || null,
        include_topology_materials: true,
      }),
    enabled: Boolean(projectKey),
  })
  const activeDocDetail = useQuery({
    queryKey: queryKeys.admin.documentDetail(projectKey, activeDocCardId),
    queryFn: () => getAdminDocument(Number(activeDocCardId)),
    enabled: Boolean(projectKey && typeof activeDocCardId === 'number'),
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
  const selectedArtifactName = explicitSelectedArtifactName ?? 'memory.md'
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
    () =>
      selectedSessionArtifacts.find((artifact) => artifact.name === selectedArtifactName)
      || selectedSessionArtifacts[0],
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
  const runtimeServiceEntries = Object.entries(runtimeStatus.data?.services || {})
  const runtimeMissingDependencies = collectRuntimeMissingDependencies(runtimeStatus.data)
  const runtimeMode = runtimeStatus.data?.runtime_mode || 'unknown'
  const businessLineEvidenceLines = businessLineEvidenceMatrix.data?.lines || []
  const businessLineEvidenceStatement = matrixCoverageStatement(businessLineEvidenceMatrix.data)
  const businessLineCoverage = (
    businessLineEvidenceMatrix.data?.coverage && typeof businessLineEvidenceMatrix.data.coverage === 'object'
      ? businessLineEvidenceMatrix.data.coverage as Record<string, unknown>
      : null
  )
  const businessLineScheduledObservation = (
    businessLineEvidenceMatrix.data?.scheduled_observation && typeof businessLineEvidenceMatrix.data.scheduled_observation === 'object'
      ? businessLineEvidenceMatrix.data.scheduled_observation as Record<string, unknown>
      : null
  )
  const businessLineWorkerReadback = (
    businessLineEvidenceMatrix.data?.worker_readback && typeof businessLineEvidenceMatrix.data.worker_readback === 'object'
      ? businessLineEvidenceMatrix.data.worker_readback as Record<string, unknown>
      : null
  )
  const scheduledMatrixDiagnostics = (
    businessLineEvidenceMatrix.data?.matrix_diagnostics_guidance
  )
  const scheduledMatrixArtifact = scheduledMatrixArtifactSummary.data
  const scheduledMatrixArtifactDiagnostics = normalizeObject(scheduledMatrixArtifact?.diagnostics)
  const scheduledMatrixArtifactBoundary = matrixTextList(scheduledMatrixArtifact?.completion_boundary)
  const scheduledMatrixArtifactSummaryRows = matrixTextList(scheduledMatrixArtifact?.summary)
  const scheduledArtifactSummary = scheduledArtifactSummaries.data
  const scheduledArtifactLanes = scheduledArtifactLaneRows(scheduledArtifactSummary)
  const scheduledArtifactSummaryRows = matrixTextList(scheduledArtifactSummary?.summary)
  const scheduledArtifactBoundary = matrixTextList(scheduledArtifactSummary?.completion_boundary)
  const scheduledArtifactWhitelistedLanes = matrixTextList(scheduledArtifactSummary?.whitelisted_lanes)
  const scheduledArtifactDrilldownData = scheduledArtifactDrilldown.data
  const scheduledArtifactDrilldownLanes = scheduledArtifactDrilldownLaneRows(scheduledArtifactDrilldownData)
  const scheduledArtifactDrilldownWarningLanes = useMemo(
    () => scheduledArtifactDrilldownLanes.filter(scheduledArtifactDrilldownLaneHasWarning),
    [scheduledArtifactDrilldownLanes],
  )
  const scheduledArtifactDrilldownFilteredLanes = scheduledArtifactDrilldownLaneFilter === 'warning_only'
    ? scheduledArtifactDrilldownWarningLanes
    : scheduledArtifactDrilldownLanes
  const scheduledArtifactDrilldownVisibleLanes = useMemo(
    () => sortScheduledArtifactDrilldownLanes(
      scheduledArtifactDrilldownFilteredLanes,
      scheduledArtifactDrilldownLaneSort,
    ),
    [scheduledArtifactDrilldownFilteredLanes, scheduledArtifactDrilldownLaneSort],
  )
  const scheduledArtifactDrilldownEmptyWarningView = isScheduledArtifactDrilldownEmptyWarningView(
    scheduledArtifactDrilldownLaneFilter,
    scheduledArtifactDrilldownVisibleLanes,
    scheduledArtifactDrilldownLanes,
  )
  const scheduledArtifactDrilldownEmptyWarningDiagnostics = [
    `empty warning diagnostics: filter=${scheduledArtifactDrilldownLaneFilter}`,
    `empty warning diagnostics: sort=${scheduledArtifactDrilldownLaneSort}`,
    `empty warning diagnostics: total_lanes=${scheduledArtifactDrilldownLanes.length}`,
    `empty warning diagnostics: visible_lanes=${scheduledArtifactDrilldownVisibleLanes.length}`,
    `empty warning diagnostics: warning_lanes=${scheduledArtifactDrilldownWarningLanes.length}`,
  ]
  const recordScheduledArtifactDrilldownEmptyReset = () => {
    setScheduledArtifactDrilldownUiEventLog([
      'ui telemetry event: reset_empty_warning_view',
      `ui telemetry event: from=${scheduledArtifactDrilldownLaneFilter}`,
      'ui telemetry event: to=all',
      `ui telemetry event: sort=${scheduledArtifactDrilldownLaneSort}`,
      'ui telemetry event: api_payload=unchanged',
      'ui telemetry event: scheduled_evidence_write=none',
      'ui telemetry event: scheduled_completion_proof=unchanged',
    ])
    setScheduledArtifactDrilldownLaneFilter('all')
  }
  const scheduledArtifactDrilldownSummaryRows = matrixTextList(scheduledArtifactDrilldownData?.summary)
  const scheduledArtifactDrilldownBoundary = matrixTextList(scheduledArtifactDrilldownData?.completion_boundary)

  const copyRuntimeDiagnosticPackage = async () => {
    const packageText = JSON.stringify(buildRuntimeDiagnosticPackage(projectKey, runtimeStatus.data), null, 2)
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

  const toggleDocSelection = (docId: number) => {
    setSelectedDocIds((prev) => (prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]))
  }

  const selectCurrentPage = () => {
    const pageIds = (adminDocuments.data?.items || []).flatMap((item) => (
      !item.readonly && typeof item.id === 'number' ? [item.id] : []
    ))
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
    setAdminPreview(null)
    setAdminPreviewAction('')
    setStatusText(formatOpsTemplate(t('opsPage.status.running'), { action: name }))
    try {
      const result = await fn()
      const taskId = typeof (result as { task_id?: unknown })?.task_id === 'string' ? String((result as { task_id?: string }).task_id) : ''
      if (hasAdminGovernanceEvidence(result)) {
        setAdminPreview(result)
        setAdminPreviewAction(actionKey)
      }
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
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'backend' ? t('opsPage.title.backend') : t('opsPage.title.ops')}</h2>
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
      </section>
      <section className="kpi-grid">
        <article className="kpi-card"><span>{t('opsPage.kpi.documents')}</span><strong>{adminStats.data?.documents?.total || 0}</strong><small>{formatOpsTemplate(t('opsPage.kpi.todayCount'), { count: adminStats.data?.documents?.recent_today || 0 })}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.socialDocuments')}</span><strong>{adminStats.data?.social_data?.total || 0}</strong><small>{formatOpsTemplate(t('opsPage.kpi.todayCount'), { count: adminStats.data?.social_data?.recent_today || 0 })}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.sources')}</span><strong>{adminStats.data?.sources?.total || 0}</strong><small>{t('opsPage.kpi.resourcePool')}</small></article>
        <article className="kpi-card"><span>{t('opsPage.kpi.searchHistory')}</span><strong>{adminStats.data?.search_history?.total || 0}</strong><small>{t('opsPage.kpi.history')}</small></article>
      </section>

      {variant === 'ops' ? <ProjectRetrievalPanel key={projectKey} projectKey={projectKey} /> : null}

      <section className={`panel ops-runtime-panel ops-runtime-panel--${variant}`}>
        <div className="panel-header">
          <div>
            <h2>{t('opsPage.section.runtimeStatus')}</h2>
            <p className="muted">{isZhLocale ? '全局后端观测 / 当前项目运行上下文' : 'Global backend observation / current project runtime context'}</p>
          </div>
          <div className="inline-actions">
            <span className={runtimeModeClass(runtimeMode)}>
              {formatOpsTemplate(t('opsPage.status.runtimeMode'), { mode: runtimeMode })}
            </span>
            <button type="button" onClick={() => void copyRuntimeDiagnosticPackage()}>
              {t('opsPage.action.copyRuntimeDiagnosticPackage')}
            </button>
            <button type="button" onClick={() => { void runtimeStatus.refetch() }}>
              <RefreshCw size={14} />
              {t('opsPage.action.refresh')}
            </button>
          </div>
        </div>
        {runtimeMode === 'mixed' ? (
          <p className="status-line">
            {t('opsPage.status.mixedRuntimeRisk')}
          </p>
        ) : null}
        {runtimeMissingDependencies.length ? (
          <p className="status-line">
            {formatOpsTemplate(t('opsPage.status.missingDependencies'), { dependencies: runtimeMissingDependencies.join(', ') })}
          </p>
        ) : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('opsPage.field.service')}</th>
                <th>{t('opsPage.field.status')}</th>
                <th>{t('opsPage.field.mode')}</th>
                <th>{t('opsPage.field.healthPortHint')}</th>
                <th>{t('opsPage.field.missing')}</th>
              </tr>
            </thead>
            <tbody>
              {runtimeServiceEntries.map(([name, service]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td><span className={statusClass(service.status)}>{service.status || '-'}</span></td>
                  <td><span className={runtimeModeClass(service.mode)}>{service.mode || t('opsPage.status.unknown')}</span></td>
                  <td>{runtimeHealthTarget(service) || service.host || '-'}</td>
                  <td>{service.missing_dependencies?.length ? service.missing_dependencies.join(', ') : '-'}</td>
                </tr>
              ))}
              {!runtimeServiceEntries.length ? (
                <tr>
                  <td colSpan={5} className="empty-cell">
                    {runtimeStatus.isLoading ? t('opsPage.status.loading') : t('opsPage.empty.runtimeStatus')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <div className="ops-technical-toggle" data-testid="ops-technical-toggle">
        <button type="button" className="chip" onClick={() => setShowTechnicalDiagnostics((visible) => !visible)}>
          {showTechnicalDiagnostics
            ? (isZhLocale ? '收起技术日志与证据矩阵' : 'Collapse technical logs and evidence matrix')
            : (isZhLocale ? '展开技术日志与证据矩阵' : 'Expand technical logs and evidence matrix')}
        </button>
        <span className="muted">{isZhLocale ? '资料质量结论不会由此观测面板推导。' : 'This observation panel does not derive materials or quality conclusions.'}</span>
      </div>
      {showTechnicalDiagnostics ? <section className="panel ops-technical-diagnostics" data-testid="ops-business-line-evidence-matrix">
        <div className="panel-header">
          <div>
            <h2>{t('opsPage.section.businessLineEvidenceMatrix')}</h2>
            <p className="muted">{isZhLocale ? '技术诊断与证据矩阵（按需展开；不改变项目资料质量结论）' : 'Technical diagnostics and evidence matrix (expand on demand; does not change project materials or quality conclusions)'}</p>
            <p className="muted">
              {formatOpsTemplate(t('opsPage.status.businessLineEvidenceContract'), {
                contract: businessLineEvidenceMatrix.data?.contract_version || '-',
              })}
            </p>
            {businessLineEvidenceStatement ? (
              <p className="status-line">{businessLineEvidenceStatement}</p>
            ) : null}
          </div>
          <div className="inline-actions">
            <span className="chip">
              {formatOpsTemplate(t('opsPage.metric.businessLineCount'), { count: businessLineEvidenceLines.length })}
            </span>
            <button type="button" onClick={() => { void businessLineEvidenceMatrix.refetch() }}>
              <RefreshCw size={14} />
              {t('opsPage.action.refresh')}
            </button>
          </div>
        </div>
        <div className="grid-3" data-testid="ops-business-line-matrix-contract" style={{ alignItems: 'start', marginBottom: 16 }}>
          <article className="kpi-card">
            <span>vocabulary</span>
            <strong>{scheduledMatrixArtifactLabel(businessLineEvidenceMatrix.data?.vocabulary_version, 'unknown/fallback')}</strong>
            <small>
              coverage: {scheduledMatrixArtifactLabel(businessLineCoverage?.covered_line_count, 'unknown')} / {businessLineCoverage ? matrixTextList(businessLineCoverage.covered_line_keys).length : 0} keys
              {' '}| not_admin_only: {scheduledMatrixArtifactLabel(businessLineCoverage?.not_admin_only, 'unknown')}
            </small>
          </article>
          <article className="kpi-card">
            <span>scheduled observation</span>
            <strong>{scheduledMatrixArtifactLabel(businessLineScheduledObservation?.observation_status, 'unknown/fallback')}</strong>
            <small>
              scheduled_run_evidence: {scheduledMatrixArtifactLabel(businessLineScheduledObservation?.scheduled_run_evidence, 'unknown')}
              {' '}| install_status: {scheduledMatrixArtifactLabel(businessLineScheduledObservation?.install_status, 'unknown')}
              {' '}| completion_claim: {scheduledMatrixArtifactLabel(businessLineScheduledObservation?.completion_claim, 'unknown')}
            </small>
          </article>
          <article className="kpi-card">
            <span>worker readback</span>
            <strong>{scheduledMatrixArtifactLabel(businessLineWorkerReadback?.contract_version, 'unknown/fallback')}</strong>
            <small>
              completion_claim: {scheduledMatrixArtifactLabel(businessLineWorkerReadback?.completion_claim, 'unknown')}
              {' '}| covered_line_keys: {matrixTextList(businessLineWorkerReadback?.covered_line_keys).length}
            </small>
          </article>
        </div>
        <div
          className="grid-2"
          data-testid="ops-business-line-scheduled-matrix-artifact-summary"
          style={{ alignItems: 'start', marginBottom: 16 }}
        >
          <article className="kpi-card">
            <span>scheduled matrix lane</span>
            <strong>{scheduledMatrixArtifact?.lane || '-'}</strong>
            <small>
              <span className={scheduledMatrixArtifactClass(scheduledMatrixArtifact)}>
                {[
                  scheduledMatrixArtifact?.lane_classification || '-',
                  scheduledMatrixArtifact?.status || '-',
                ].join(' / ')}
              </span>
            </small>
          </article>
          <article className="kpi-card">
            <span>reason</span>
            <strong>{scheduledMatrixArtifactLabel(scheduledMatrixArtifact?.reason)}</strong>
            <small>source checker: {scheduledMatrixArtifact?.source_checker || '-'}</small>
          </article>
          <article className="kpi-card">
            <span>artifact path</span>
            <strong>{scheduledMatrixArtifactPath(scheduledMatrixArtifact)}</strong>
            <small>observed at: {formatDate(scheduledMatrixArtifact?.observed_at, locale)}</small>
          </article>
          <article className="kpi-card">
            <span>recommended command</span>
            <strong>{scheduledMatrixArtifactLabel(scheduledMatrixArtifact?.recommended_command)}</strong>
            <small>contract: {scheduledMatrixArtifact?.contract_version || '-'}</small>
          </article>
          <div>
            <strong>diagnostics</strong>
            <ul className="compact-list">
              <li><code>runtime_preflight_status</code>: {scheduledMatrixArtifactLabel(scheduledMatrixArtifactDiagnostics.runtime_preflight_status)}</li>
              <li><code>matrix_exit_code</code>: {scheduledMatrixArtifactLabel(scheduledMatrixArtifactDiagnostics.matrix_exit_code)}</li>
              <li><code>first_blocked_reason</code>: {scheduledMatrixArtifactLabel(scheduledMatrixArtifactDiagnostics.first_blocked_reason)}</li>
            </ul>
          </div>
          <div>
            <strong>completion boundary</strong>
            <ul className="compact-list">
              {scheduledMatrixArtifactBoundary.length
                ? scheduledMatrixArtifactBoundary.map((item) => <li key={item}>{item}</li>)
                : <li>-</li>}
            </ul>
          </div>
          {scheduledMatrixArtifactSummaryRows.length ? (
            <div>
              <strong>summary</strong>
              <ul className="compact-list">
                {scheduledMatrixArtifactSummaryRows.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
          {scheduledMatrixArtifactSummary.isError ? (
            <p className="status-line">
              scheduled matrix artifact summary unavailable: {scheduledMatrixArtifactError(scheduledMatrixArtifactSummary.error)}
            </p>
          ) : null}
        </div>
        <div
          className="grid-2"
          data-testid="ops-business-line-scheduled-artifact-summaries"
          style={{ alignItems: 'start', marginBottom: 16 }}
        >
          <article className="kpi-card">
            <span>all scheduled lanes status</span>
            <strong>
              <span className={scheduledMatrixArtifactClass(scheduledArtifactSummary)}>
                {scheduledMatrixArtifactLabel(scheduledArtifactSummary?.status)}
              </span>
            </strong>
            <small>source checker: {scheduledArtifactSummary?.source_checker || '-'}</small>
          </article>
          <article className="kpi-card">
            <span>observed at</span>
            <strong>{formatDate(scheduledArtifactSummary?.observed_at, locale)}</strong>
            <small>contract: {scheduledArtifactSummary?.contract_version || '-'}</small>
          </article>
          <article className="kpi-card">
            <span>recommended command</span>
            <strong>{scheduledMatrixArtifactLabel(scheduledArtifactSummary?.recommended_command)}</strong>
            <small>
              lanes: {scheduledArtifactWhitelistedLanes.length ? scheduledArtifactWhitelistedLanes.join(', ') : '-'}
            </small>
          </article>
          <div>
            <strong>summary</strong>
            <ul className="compact-list">
              {scheduledArtifactSummaryRows.length
                ? scheduledArtifactSummaryRows.map((item) => <li key={item}>{item}</li>)
                : <li>-</li>}
            </ul>
          </div>
          <div className="table-wrap" style={{ gridColumn: '1 / -1' }}>
            <table>
              <thead>
                <tr>
                  <th>lane</th>
                  <th>classification/status</th>
                  <th>reason</th>
                  <th>artifact path</th>
                  <th>observed at</th>
                </tr>
              </thead>
              <tbody>
                {scheduledArtifactLanes.map((lane, index) => (
                  <tr key={`${lane.lane || 'lane'}-${index}`}>
                    <td><code>{lane.lane || '-'}</code></td>
                    <td>
                      <span className={scheduledMatrixArtifactClass(lane)}>
                        {[
                          scheduledMatrixArtifactLabel(lane.lane_classification),
                          scheduledMatrixArtifactLabel(lane.status),
                        ].join(' / ')}
                      </span>
                    </td>
                    <td>{scheduledMatrixArtifactLabel(lane.reason)}</td>
                    <td><code>{scheduledMatrixArtifactPath(lane)}</code></td>
                    <td>{formatDate(lane.observed_at, locale)}</td>
                  </tr>
                ))}
                {!scheduledArtifactLanes.length ? (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      {scheduledArtifactSummaries.isLoading ? t('opsPage.status.loading') : '-'}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div>
            <strong>completion boundary</strong>
            <ul className="compact-list">
              {scheduledArtifactBoundary.length
                ? scheduledArtifactBoundary.map((item) => <li key={item}>{item}</li>)
                : <li>-</li>}
            </ul>
          </div>
          {scheduledArtifactSummaries.isError ? (
            <p className="status-line">
              scheduled artifact summaries unavailable: {scheduledMatrixArtifactError(scheduledArtifactSummaries.error)}
            </p>
          ) : null}
        </div>
        <div
          className="grid-2"
          data-testid="ops-business-line-scheduled-artifact-drilldown"
          style={{ alignItems: 'start', marginBottom: 16 }}
        >
          <article className="kpi-card">
            <span>scheduled artifact drilldown</span>
            <strong>
              <span className={scheduledMatrixArtifactClass(scheduledArtifactDrilldownData)}>
                {scheduledMatrixArtifactLabel(scheduledArtifactDrilldownData?.status)}
              </span>
            </strong>
            <small>source checker: {scheduledArtifactDrilldownData?.source_checker || '-'}</small>
          </article>
          <article className="kpi-card">
            <span>observed at</span>
            <strong>{formatDate(scheduledArtifactDrilldownData?.observed_at, locale)}</strong>
            <small>contract: {scheduledArtifactDrilldownData?.contract_version || '-'}</small>
          </article>
          <article className="kpi-card">
            <span>recommended command</span>
            <strong>{scheduledMatrixArtifactLabel(scheduledArtifactDrilldownData?.recommended_command)}</strong>
            <small>
              lanes: {scheduledArtifactDrilldownLanes.length}
              {' '}
              | visible lanes: {scheduledArtifactDrilldownVisibleLanes.length}/{scheduledArtifactDrilldownLanes.length}
            </small>
          </article>
          <div style={{ gridColumn: '1 / -1' }}>
            <strong>quick filter</strong>
            <div className="inline-actions" style={{ marginTop: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className={scheduledArtifactDrilldownLaneFilter === 'warning_only' ? 'chip chip-warn' : 'chip'}
                onClick={() => setScheduledArtifactDrilldownLaneFilter('warning_only')}
              >
                show warning lanes
              </button>
              <button
                type="button"
                className={scheduledArtifactDrilldownLaneFilter === 'all' ? 'chip chip-ok' : 'chip'}
                onClick={() => setScheduledArtifactDrilldownLaneFilter('all')}
              >
                show all lanes
              </button>
              <span className="chip">
                warning lane filter: {scheduledArtifactDrilldownLaneFilter}
              </span>
              <span className="chip">
                visible lanes: {scheduledArtifactDrilldownVisibleLanes.length}/{scheduledArtifactDrilldownLanes.length}
              </span>
              <button
                type="button"
                className={scheduledArtifactDrilldownLaneSort === 'source_order' ? 'chip chip-ok' : 'chip'}
                onClick={() => setScheduledArtifactDrilldownLaneSort('source_order')}
              >
                sort source order
              </button>
              <button
                type="button"
                className={scheduledArtifactDrilldownLaneSort === 'warning_priority' ? 'chip chip-warn' : 'chip'}
                onClick={() => setScheduledArtifactDrilldownLaneSort('warning_priority')}
              >
                sort warning priority
              </button>
              <button
                type="button"
                className={scheduledArtifactDrilldownLaneSort === 'warning_count' ? 'chip chip-warn' : 'chip'}
                onClick={() => setScheduledArtifactDrilldownLaneSort('warning_count')}
              >
                sort warning count
              </button>
              <button
                type="button"
                className={scheduledArtifactDrilldownLaneSort === 'artifact_count' ? 'chip chip-warn' : 'chip'}
                onClick={() => setScheduledArtifactDrilldownLaneSort('artifact_count')}
              >
                sort artifact count
              </button>
              <span className="chip">
                lane sort: {scheduledArtifactDrilldownLaneSort}
              </span>
              <span className="chip">
                lane sort explanation: {scheduledArtifactDrilldownLaneSortExplanation(scheduledArtifactDrilldownLaneSort)}
              </span>
            </div>
            {scheduledArtifactDrilldownEmptyWarningView ? (
              <article className="kpi-card" style={{ marginTop: 8 }}>
                <span>{SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_TITLE}</span>
                <div className="inline-actions" style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    className="chip chip-ok"
                    onClick={recordScheduledArtifactDrilldownEmptyReset}
                  >
                    reset empty warning view: show all lanes
                  </button>
                </div>
                <ul className="compact-list">
                  {SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_LINES.map((item) => <li key={item}>{item}</li>)}
                  {scheduledArtifactDrilldownEmptyWarningDiagnostics.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </article>
            ) : null}
            {scheduledArtifactDrilldownUiEventLog.length > 0 ? (
              <article className="kpi-card" style={{ marginTop: 8 }}>
                <span>scheduled artifact UI event log</span>
                <ul className="compact-list">
                  {scheduledArtifactDrilldownUiEventLog.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </article>
            ) : null}
          </div>
          <div>
            <strong>summary</strong>
            <ul className="compact-list">
              {scheduledArtifactDrilldownSummaryRows.length
                ? scheduledArtifactDrilldownSummaryRows.map((item) => <li key={item}>{item}</li>)
                : <li>-</li>}
            </ul>
          </div>
          <div className="table-wrap" style={{ gridColumn: '1 / -1' }}>
            <table>
              <thead>
                <tr>
                  <th>lane</th>
                  <th>classification/status</th>
                  <th>base_dir</th>
                  <th>artifact_count</th>
                  <th>warning_count</th>
                  <th>warning types</th>
                  <th>severity counts</th>
                  <th>highest severity</th>
                  <th>severity rank</th>
                  <th>severity order</th>
                  <th>status counts</th>
                  <th>completion proof</th>
                  <th>reason</th>
                  <th>recommended command</th>
                </tr>
              </thead>
              <tbody>
                {scheduledArtifactDrilldownVisibleLanes.map((lane, index) => (
                  <tr key={`${lane.lane || 'lane'}-${index}`}>
                    <td><code>{lane.lane || '-'}</code></td>
                    <td>
                      <span className={scheduledMatrixArtifactClass(lane)}>
                        {[
                          scheduledMatrixArtifactLabel(lane.lane_classification),
                          scheduledMatrixArtifactLabel(lane.status),
                        ].join(' / ')}
                      </span>
                    </td>
                    <td><code>{scheduledMatrixArtifactLabel(lane.base_dir)}</code></td>
                    <td>{lane.artifact_count ?? scheduledArtifactDrilldownArtifacts(lane).length}</td>
                    <td>{lane.identity_warning_count ?? 0}</td>
                    <td>
                      <ul className="compact-list">
                        {matrixTextList(lane.identity_warning_types).length
                          ? matrixTextList(lane.identity_warning_types).map((item) => <li key={item}>{item}</li>)
                          : <li>-</li>}
                      </ul>
                    </td>
                    <td>
                      <ul className="compact-list">
                        {matrixTextList(lane.identity_warning_severity_counts).length
                          ? matrixTextList(lane.identity_warning_severity_counts).map((item) => <li key={item}>{item}</li>)
                          : <li>-</li>}
                      </ul>
                    </td>
                    <td>highest severity: {scheduledMatrixArtifactLabel(lane.identity_warning_highest_severity)}</td>
                    <td>severity rank: {scheduledMatrixArtifactLabel(lane.identity_warning_highest_severity_rank)}</td>
                    <td>
                      <ul className="compact-list">
                        {matrixTextList(lane.identity_warning_severity_order).length
                          ? matrixTextList(lane.identity_warning_severity_order).map((item) => <li key={item}>{item}</li>)
                          : <li>-</li>}
                      </ul>
                    </td>
                    <td>
                      <ul className="compact-list">
                        {matrixTextList(lane.identity_status_counts).length
                          ? matrixTextList(lane.identity_status_counts).map((item) => <li key={item}>{item}</li>)
                          : <li>-</li>}
                      </ul>
                    </td>
                    <td>{lane.scheduled_completion_proof ? 'scheduled_run_evidence' : 'not completion proof'}</td>
                    <td>{scheduledMatrixArtifactLabel(lane.reason)}</td>
                    <td><code>{scheduledMatrixArtifactLabel(lane.recommended_command)}</code></td>
                  </tr>
                ))}
                {!scheduledArtifactDrilldownVisibleLanes.length ? (
                  <tr>
                    <td colSpan={14} className="empty-cell">
                      {scheduledArtifactDrilldown.isLoading
                        ? t('opsPage.status.loading')
                        : scheduledArtifactDrilldownEmptyWarningView
                          ? SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_TITLE
                          : '-'}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="table-wrap" style={{ gridColumn: '1 / -1' }}>
            <table>
              <thead>
                <tr>
                  <th>lane</th>
                  <th>artifact path</th>
                  <th>classification</th>
                  <th>completion proof</th>
                  <th>reason</th>
                  <th>freshness</th>
                  <th>size_bytes</th>
                  <th>sha256</th>
                  <th>mtime</th>
                  <th>observed at</th>
                </tr>
              </thead>
              <tbody>
                {scheduledArtifactDrilldownVisibleLanes.flatMap((lane, laneIndex) => {
                  const artifacts = scheduledArtifactDrilldownArtifacts(lane)
                  if (!artifacts.length) {
                    return [
                      <tr key={`${lane.lane || 'lane'}-${laneIndex}-empty`}>
                        <td><code>{lane.lane || '-'}</code></td>
                        <td><code>{scheduledMatrixArtifactPath(lane)}</code></td>
                        <td>
                          <span className={scheduledMatrixArtifactClass(lane)}>
                            {scheduledMatrixArtifactLabel(lane.lane_classification)}
                          </span>
                        </td>
                        <td>{lane.scheduled_completion_proof ? 'scheduled_run_evidence' : 'not completion proof'}</td>
                        <td>{scheduledMatrixArtifactLabel(lane.reason)}</td>
                        <td>-</td>
                        <td>-</td>
                        <td>-</td>
                        <td>-</td>
                        <td>{formatDate(scheduledArtifactDrilldownData?.observed_at, locale)}</td>
                      </tr>,
                    ]
                  }
                  return artifacts.map((artifact, artifactIndex) => (
                    <tr key={`${lane.lane || 'lane'}-${artifact.artifact_path || artifactIndex}`}>
                      <td><code>{lane.lane || '-'}</code></td>
                      <td><code>{scheduledMatrixArtifactLabel(artifact.artifact_path)}</code></td>
                      <td>
                        <span className={scheduledMatrixArtifactClass({ lane_classification: artifact.classification })}>
                          {scheduledMatrixArtifactLabel(artifact.classification)}
                        </span>
                      </td>
                      <td>{artifact.scheduled_completion_proof ? 'scheduled_run_evidence' : 'not completion proof'}</td>
                      <td>{scheduledMatrixArtifactLabel(artifact.reason)}</td>
                      <td>
                        <ul className="compact-list">
                          {scheduledArtifactFreshnessRows(artifact).map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      </td>
                      <td>{scheduledArtifactSizeLabel(artifact.size_bytes)}</td>
                      <td><code>{scheduledArtifactSha256Label(artifact.sha256)}</code></td>
                      <td>{scheduledMatrixArtifactLabel(artifact.mtime)}</td>
                      <td>{formatDate(artifact.observed_at, locale)}</td>
                    </tr>
                  ))
                })}
                {!scheduledArtifactDrilldownVisibleLanes.length ? (
                  <tr>
                    <td colSpan={10} className="empty-cell">
                      {scheduledArtifactDrilldown.isLoading
                        ? t('opsPage.status.loading')
                        : scheduledArtifactDrilldownEmptyWarningView
                          ? SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_TITLE
                          : '-'}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <strong>diagnostics</strong>
            <div className="grid-2" style={{ alignItems: 'start', marginTop: 8 }}>
              {scheduledArtifactDrilldownVisibleLanes.map((lane, index) => {
                const rows = scheduledArtifactDiagnosticsRows(lane.diagnostics)
                return (
                  <article className="kpi-card" key={`${lane.lane || 'lane'}-${index}-diagnostics`}>
                    <span>{lane.lane || '-'}</span>
                    <strong>{scheduledMatrixArtifactLabel(lane.lane_classification)}</strong>
                    <ul className="compact-list">
                      {rows.length
                        ? rows.map(([key, value]) => <li key={key}><code>{key}</code>: {value}</li>)
                        : <li>-</li>}
                    </ul>
                  </article>
                )
              })}
              {!scheduledArtifactDrilldownVisibleLanes.length ? (
                <p className="status-line">
                  {scheduledArtifactDrilldownEmptyWarningView
                    ? SCHEDULED_ARTIFACT_DRILLDOWN_EMPTY_WARNING_VIEW_TITLE
                    : '-'}
                </p>
              ) : null}
            </div>
          </div>
          <div>
            <strong>completion boundary</strong>
            <ul className="compact-list">
              {scheduledArtifactDrilldownBoundary.length
                ? scheduledArtifactDrilldownBoundary.map((item) => <li key={item}>{item}</li>)
                : <li>-</li>}
            </ul>
          </div>
          {scheduledArtifactDrilldown.isError ? (
            <p className="status-line">
              scheduled artifact drilldown unavailable: {scheduledMatrixArtifactError(scheduledArtifactDrilldown.error)}
            </p>
          ) : null}
        </div>
        <div
            className="grid-2"
            data-testid="ops-business-line-matrix-diagnostics-guidance"
            style={{ alignItems: 'start', marginBottom: 16 }}
          >
            <article className="kpi-card">
              <span>source lane</span>
              <strong>{scheduledMatrixDiagnostics?.source_lane || 'unknown/fallback'}</strong>
              <small>source artifact: {scheduledMatrixDiagnostics?.source_artifact || 'unknown/fallback'}</small>
            </article>
            <article className="kpi-card">
              <span>classification boundary</span>
              <ul className="compact-list">
                {matrixClassificationBoundaryList(scheduledMatrixDiagnostics?.classification_boundary).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <small>consumer surface: {scheduledMatrixDiagnostics?.consumer_surface || 'unknown/fallback'}</small>
            </article>
            <div>
              <strong>recommended display order</strong>
              <ul className="compact-list">
                {matrixTextList(scheduledMatrixDiagnostics?.recommended_display_order).map((field) => (
                  <li key={field}><code>{field}</code></li>
                ))}
              </ul>
            </div>
            <div>
              <strong>required fields</strong>
              <ul className="compact-list">
                {matrixTextList(scheduledMatrixDiagnostics?.required_fields).map((field) => (
                  <li key={field}><code>{field}</code></li>
                ))}
              </ul>
            </div>
            <div>
              <strong>blocked project fields</strong>
              <ul className="compact-list">
                {matrixTextList(scheduledMatrixDiagnostics?.blocked_project_fields).map((field) => (
                  <li key={field}><code>{field}</code></li>
                ))}
              </ul>
            </div>
          </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('opsPage.field.lineKey')}</th>
                <th>{t('opsPage.field.entrypoints')}</th>
                <th>{t('opsPage.field.apiGroups')}</th>
                <th>{t('opsPage.field.currentGaps')}</th>
                <th>{t('opsPage.field.nextRemediation')}</th>
                <th>{t('opsPage.field.verificationCommands')}</th>
              </tr>
            </thead>
            <tbody>
              {businessLineEvidenceLines.map((line) => (
                <tr key={line.line_key} data-testid={matrixLineTestId(line)}>
                  <td><code>{line.line_key}</code></td>
                  <td>{matrixFieldCount(line.entrypoints)}</td>
                  <td>{matrixFieldCount(line.api_groups)}</td>
                  <td>
                    <ul className="compact-list">
                      {matrixTextList(line.current_gaps).map((gap) => <li key={gap}>{gap}</li>)}
                    </ul>
                  </td>
                  <td>
                    <ul className="compact-list">
                      {matrixTextList(line.next_remediation).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </td>
                  <td>
                    <ul className="compact-list">
                      {matrixTextList(line.verification_commands).map((command) => <li key={command}><code>{command}</code></li>)}
                    </ul>
                  </td>
                </tr>
              ))}
              {!businessLineEvidenceLines.length ? (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    {businessLineEvidenceMatrix.isLoading ? t('opsPage.status.loading') : t('opsPage.empty.businessLineEvidenceMatrix')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section> : null}

      <section className="panel ops-agent-session-panel">
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
                void runAdminPreview('bulkStructuredWrite', () =>
                  bulkUpdateDocumentExtractedData({
                    doc_ids: selectedDocIds,
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
                  bulkUpdateDocumentExtractedData({
                    doc_ids: selectedDocIds,
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
                void runAdminPreview('deleteDocuments', () =>
                  deleteAdminDocuments({ ids: selectedDocIds, preview: true }),
                )
              }
            >
              {t('opsPage.action.previewDeleteDocuments')}
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
        {adminPreview ? (
          <section className="panel" data-testid="ops-document-governance-preview" style={{ marginTop: 16 }}>
            <div className="panel-header">
              <h3>{t('opsPage.section.adminGovernanceEvidence')}</h3>
              <div className="inline-actions">
                <span className="chip">{actionName(adminPreviewAction || 'deleteDocuments')}</span>
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
                <small>{adminPreview.preview ? t('opsPage.status.previewModeNoExecution') : t('opsPage.status.executionResultReadback')}</small>
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
        <p className="status-line">{formatOpsTemplate(t('opsPage.metric.selectedDocuments'), { count: selectedCount })}</p>
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
              {(adminDocuments.data?.items || []).map((row) => (
                <tr
                  key={row.id}
                  onClick={() => {
                    if (row.readonly) return
                    const candidateId: number | null = typeof row.id === 'number' ? row.id : null
                    const nextId: number | null = activeDocCardId === candidateId ? null : candidateId
                    setActiveDocCardId((prev) => {
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
                      checked={typeof row.id === 'number' && selectedDocIds.includes(row.id)}
                      onChange={() => { if (typeof row.id === 'number') toggleDocSelection(row.id) }}
                      disabled={row.readonly || typeof row.id !== 'number'}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td>{row.id}</td>
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
                  <td>{row.doc_type || '-'}</td>
                  <td>{row.state || '-'}</td>
                  <td>{String(row.has_extracted_data ?? false)}</td>
                  <td>{formatDate(row.updated_at, locale)}</td>
                </tr>
              ))}
              {!adminDocuments.data?.items?.length ? (
                <tr>
                  <td colSpan={8} className="empty-cell">{t('opsPage.empty.documents')}</td>
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
