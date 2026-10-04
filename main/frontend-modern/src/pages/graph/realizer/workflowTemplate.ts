import { isApiClientError } from '../../../lib/api/client'
import type { WorkflowGraphCuratedDsl, WorkflowGraphCuratedStateResponse } from '../../../lib/api'
import type { MessageKey } from '../../../app/platform/i18n'
import type {
  GraphEdgeItem,
  GraphNodeItem,
  WorkflowRunResult,
  WorkflowTemplateDiffStep,
  WorkflowTemplatePayload,
  WorkflowTemplateRollbackResponse,
  WorkflowTemplateStageMutationResponse,
  WorkflowTemplateStageName,
  WorkflowTemplateStageRecord,
  WorkflowTemplateVersionListResponse,
} from '../../../lib/types'
import type { GraphProjectionDefinition } from './contract'
import { normalizeNodeType } from './nodeStyleLibrary'

type GraphKind = GraphProjectionDefinition['graphKind']
type GraphMessageParams = Record<string, number | string>

export type GraphTemplateRecord = {
  key: string
  name: string
  activeVersion?: string | null
}

export type GraphTemplateVersionRecord = {
  key: string
  name: string
  activated?: boolean
}

export type TemplateStageAuditSummary = {
  currentVersion?: number | null
  nextVersion?: number | null
  stage?: string | null
  activeVersion?: number | null
  draftVersion?: number | null
  stagingVersion?: number | null
  requiresPublish?: boolean
}

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function nodeKey(node: GraphNodeItem) {
  return `${normalizeNodeType(node.type)}:${node.id}`
}

function nodeName(node: GraphNodeItem) {
  return String(node.name || node.title || node.text || node.canonical_name || node.id)
}

export function curatedNodeId(node: GraphNodeItem) {
  return String(node.node_id || node.id || node.key || '').trim()
}

function curatedNodeType(node: GraphNodeItem) {
  return String(node.node_type || node.type || '').trim() || 'Entity'
}

function curatedRefId(ref: GraphEdgeItem['from'] | GraphEdgeItem['to']) {
  if (!ref) return ''
  const row = ref as Record<string, unknown>
  return String(row.node_id || row.id || row.key || '').trim()
}

function curatedEdgeType(edge: GraphEdgeItem) {
  return String(edge.edge_type || edge.type || edge.predicate || '').trim() || 'RELATED_TO'
}

function readOptionalString(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = String(row[key] || '').trim()
    if (value) return value
  }
  return ''
}

export function buildCuratedWorkflowGraphDsl(nodes: GraphNodeItem[], edges: GraphEdgeItem[]): WorkflowGraphCuratedDsl {
  const nodeById = new Map<string, { node_id: string; node_type: string }>()
  const normalizedNodes = nodes
    .map<WorkflowGraphCuratedDsl['nodes'][number] | null>((node) => {
      const row = node as Record<string, unknown>
      const node_id = curatedNodeId(node)
      if (!node_id) return null
      const node_type = curatedNodeType(node)
      const title = readOptionalString(row, ['title', 'name', 'label', 'text', 'canonical_name']) || node_id
      const name = readOptionalString(row, ['name', 'title', 'label', 'text', 'canonical_name']) || title
      const summary = readOptionalString(row, ['summary', 'description', 'text'])
      const source_uri = readOptionalString(row, ['source_uri', 'uri', 'url'])
      const provenance = row.provenance && typeof row.provenance === 'object'
        ? row.provenance as Record<string, unknown>
        : {}
      nodeById.set(node_id, { node_id, node_type })
      return {
        id: node_id,
        type: node_type,
        node_id,
        node_type,
        title,
        name,
        ...(summary ? { summary } : {}),
        ...(source_uri ? { source_uri } : {}),
        provenance,
      }
    })
    .filter((node): node is WorkflowGraphCuratedDsl['nodes'][number] => node !== null)

  const edgeByKey = new Map<string, WorkflowGraphCuratedDsl['edges'][number]>()
  edges.forEach((edge) => {
    const from_node_id = String(edge.from_node_id || curatedRefId(edge.from)).trim()
    const to_node_id = String(edge.to_node_id || curatedRefId(edge.to)).trim()
    if (!from_node_id || !to_node_id || !nodeById.has(from_node_id) || !nodeById.has(to_node_id)) return
    const edge_type = curatedEdgeType(edge)
    const key = `${from_node_id}>${to_node_id}|${edge_type}`
    if (edgeByKey.has(key)) return
    const fromNode = nodeById.get(from_node_id)
    const toNode = nodeById.get(to_node_id)
    edgeByKey.set(key, {
      from_node_id,
      to_node_id,
      edge_type,
      type: edge_type,
      predicate: String(edge.predicate || edge_type),
      from: { id: from_node_id, type: fromNode?.node_type || String(edge.from?.type || '') || 'Entity' },
      to: { id: to_node_id, type: toNode?.node_type || String(edge.to?.type || '') || 'Entity' },
      ...(edge.evidence ? { evidence: String(edge.evidence) } : {}),
      ...(edge.confidence != null ? { confidence: edge.confidence } : {}),
    })
  })

  return {
    nodes: normalizedNodes,
    edges: Array.from(edgeByKey.values()),
  }
}

export function temporaryCuratedNodeIds(dsl: WorkflowGraphCuratedDsl) {
  return dsl.nodes
    .map((node) => String(node.node_id || node.id || '').trim())
    .filter((id) => /^(draft|tmp|temp)-/i.test(id))
}

export function snapshotDslFromCuratedState(state: WorkflowGraphCuratedStateResponse) {
  const snapshot = state.server_snapshot?.dsl || state.draft?.dsl
  if (!snapshot || !Array.isArray(snapshot.nodes) || !Array.isArray(snapshot.edges)) return null
  return snapshot
}

function recordFrom(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
}

export function curatedSubmitFailure(error: unknown, formatMessage: (key: MessageKey, params: GraphMessageParams) => string) {
  const errorRecord = recordFrom(error)
  const response = recordFrom(errorRecord?.response)
  const responseData = recordFrom(response?.data)
  const responseError = recordFrom(responseData?.error)
  const details = isApiClientError(error) ? error.details : recordFrom(responseError?.details)
  const code = isApiClientError(error) ? error.code : String(responseError?.code || '')
  const message = isApiClientError(error)
    ? error.message
    : String(responseError?.message || errorRecord?.message || formatMessage('graphPage.error.submitFailed', {}))
  const category = String(details?.category || '')
  const expected = details?.expected_revision
  const actual = details?.actual_revision
  const isConflict =
    category === 'version_conflict' ||
    /conflict|revision mismatch|version_conflict/i.test(`${code} ${message}`)
  if (!isConflict) {
    return {
      status: `submit_failed: ${message}`,
      graphStatus: formatMessage('graphPage.error.curatedSubmitFailed', { message }),
      alertMessage: formatMessage('graphPage.error.curatedSubmitFailed', { message }),
    }
  }
  const revisionHint =
    expected !== undefined || actual !== undefined
      ? ` expected=${String(expected ?? 'unknown')} actual=${String(actual ?? 'unknown')}`
      : ''
  return {
    status: `submit_conflict: version_conflict${revisionHint}`,
    graphStatus: formatMessage('graphPage.error.curatedSubmitConflict', { message }),
    alertMessage: formatMessage('graphPage.error.curatedSubmitConflict', { message }),
  }
}

function inferWorkflowHandlerFromNode(node: GraphNodeItem) {
  const row = node as Record<string, unknown>
  return String(
    row.handler ||
    row.module_key ||
    row.moduleKey ||
    row.task_key ||
    row.type ||
    row.id ||
    'custom',
  ).trim() || 'custom'
}

export function buildWorkflowTemplatePayloadFromDraft({
  projectKey,
  nodes,
  edges,
  graphKind,
}: {
  projectKey: string
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
  graphKind: GraphKind
}): WorkflowTemplatePayload {
  const workflowNodes = nodes.map((node) => {
    const row = node as Record<string, unknown>
    const params = isPlainRecord(row.params) ? row.params : {}
    return {
      id: nodeKey(node),
      name: nodeName(node),
      title: nodeName(node),
      type: String(node.type || 'Entity'),
      module_key: String(row.module_key || row.moduleKey || inferWorkflowHandlerFromNode(node)),
      handler: inferWorkflowHandlerFromNode(node),
      params,
      data_type: String(row.data_type || row.dataType || graphKind),
    }
  })

  const workflowEdges = edges.map((edge, index) => {
    const sourceType = String(edge.from?.type || '').trim()
    const sourceId = String(curatedRefId(edge.from) || '').trim()
    const targetType = String(edge.to?.type || '').trim()
    const targetId = String(curatedRefId(edge.to) || '').trim()
    return {
      id: String(edge.id || `e${index + 1}`),
      source: sourceType || sourceId ? `${normalizeNodeType(sourceType)}:${sourceId}` : '',
      target: targetType || targetId ? `${normalizeNodeType(targetType)}:${targetId}` : '',
      mapping: isPlainRecord(edge.mapping) ? edge.mapping : { relation: String(edge.predicate || edge.type || 'RELATED_TO') },
    }
  }).filter((edge) => edge.source && edge.target)

  return {
    project_key: projectKey,
    steps: workflowNodes.map((node) => ({
      handler: node.handler,
      params: node.params,
      enabled: true,
      name: node.name,
    })),
    board_layout: {
      layout: graphKind,
      graph: {
        nodes: workflowNodes,
        edges: workflowEdges,
      },
      auto_interface: true,
      design: {
        global_data_type: graphKind,
        visualization_module: graphKind,
        llm_policy: 'auto',
      },
      data_flow: ['documents', 'extracted_data', 'visualization'],
    },
  }
}

export function asTemplateRecord(raw: unknown): GraphTemplateRecord | null {
  if (!isPlainRecord(raw)) return null
  const key = String(raw.template_id || raw.template_key || raw.key || raw.name || raw.template || '').trim()
  if (!key) return null
  return {
    key,
    name: String(raw.name || raw.template_name || raw.label || key),
    activeVersion: String(raw.active_version_id || raw.active_version || raw.activated_version || raw.current_version || '').trim() || null,
  }
}

export function asVersionRecord(raw: unknown): GraphTemplateVersionRecord | null {
  if (!isPlainRecord(raw)) return null
  const key = String(raw.version_id || raw.version_key || raw.key || raw.version || raw.name || '').trim()
  if (!key) return null
  return {
    key,
    name: String(raw.version_name || raw.name || raw.label || key),
    activated: Boolean(raw.activated ?? raw.active ?? raw.is_active),
  }
}

function asNumberOrNull(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function normalizeWorkflowTemplateStageRecords(items: unknown[]): WorkflowTemplateStageRecord[] {
  const order: WorkflowTemplateStageName[] = ['draft', 'staging', 'active']
  return items
    .map((item) => (isPlainRecord(item) ? item as WorkflowTemplateStageRecord : null))
    .filter((item): item is WorkflowTemplateStageRecord => Boolean(item && String(item.stage || '').trim()))
    .sort((a, b) => {
      const aIndex = order.indexOf(String(a.stage) as WorkflowTemplateStageName)
      const bIndex = order.indexOf(String(b.stage) as WorkflowTemplateStageName)
      return (aIndex === -1 ? 99 : aIndex) - (bIndex === -1 ? 99 : bIndex)
    })
}

export function buildTemplateStageAuditSummary(
  payload: WorkflowTemplateVersionListResponse | WorkflowTemplateStageMutationResponse,
): TemplateStageAuditSummary {
  const record = payload as Record<string, unknown>
  const versionSummary = isPlainRecord(record.version_summary) ? record.version_summary : {}
  const stageSummary = isPlainRecord(record.stage_summary) ? record.stage_summary : {}
  const currentVersion = asNumberOrNull(record.current_version)
  const nextVersion = asNumberOrNull(record.next_version) ?? (currentVersion !== null ? currentVersion + 1 : null)
  const draftVersion = asNumberOrNull(versionSummary.draft_version ?? stageSummary.draft_version)
  const stagingVersion = asNumberOrNull(versionSummary.staging_version ?? stageSummary.staging_version)
  const activeVersion = asNumberOrNull(versionSummary.active_version ?? stageSummary.active_version)
  const stage = String(versionSummary.stage || record.stage || record.to_stage || (stagingVersion ? 'staging' : draftVersion ? 'draft' : 'active'))
  const explicitRequiresPublish = versionSummary.requires_publish
  const requiresPublish = typeof explicitRequiresPublish === 'boolean'
    ? explicitRequiresPublish
    : Boolean(draftVersion || stagingVersion)
  return {
    currentVersion,
    nextVersion,
    stage,
    activeVersion,
    draftVersion,
    stagingVersion,
    requiresPublish,
  }
}

export function buildTemplateRollbackTraceId(workflowName: string, targetStage: string, targetVersion: number | null) {
  const versionPart = targetVersion === null ? 'latest' : String(targetVersion)
  return `graph-ui-rollback-${workflowName}-${targetStage}-${versionPart}`
}

export function parseTemplateRollbackVersion(value: string) {
  const n = Number(value.trim())
  return Number.isInteger(n) && n > 0 ? n : null
}

export function describeTemplateRollbackPlan(response: WorkflowTemplateRollbackResponse | null) {
  const plan = response?.rollback_plan || {}
  const canExecute = Boolean(plan.can_execute ?? plan.executable)
  const willMutate = Boolean(plan.will_mutate)
  const targetRecord = isPlainRecord(plan.target_stage_record) ? plan.target_stage_record : {}
  const targetStepCount = Array.isArray(targetRecord.steps) ? targetRecord.steps.length : 0
  return {
    mode: String(plan.mode || (response?.rollback_preview ? 'preview_only' : '-')),
    canExecute,
    willMutate,
    targetVersion: plan.target_version ?? response?.version_summary?.target_version ?? '-',
    fromStage: plan.from_stage || '-',
    toStage: plan.to_stage || response?.version_summary?.stage || '-',
    targetStepCount,
    blockedReason: String(plan.blocked_reason || plan.reason || '-'),
    applyEndpoint: String(plan.apply_endpoint || '-'),
    requiresExplicitApply: Boolean(plan.requires_explicit_apply),
  }
}

export function describeTemplateRollbackAudit(response: WorkflowTemplateRollbackResponse | null) {
  const audit = response?.audit || {}
  return {
    action: audit.action || '-',
    actor: audit.actor || audit.requested_by || '-',
    appliedBy: audit.applied_by || '-',
    traceId: audit.trace_id || '-',
    createdAt: audit.created_at || '-',
    fromStage: audit.from_stage || '-',
    toStage: audit.to_stage || '-',
  }
}

export function formatWorkflowRunScalar(value: unknown) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return String(value)
  if (typeof value === 'number' || typeof value === 'string') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function getWorkflowRunField(result: WorkflowRunResult | null, key: string) {
  if (!result) return undefined
  return (result as Record<string, unknown>)[key]
}

export function summarizeWorkflowDryRunResult(result: WorkflowRunResult | null) {
  const versionSummary = isPlainRecord(getWorkflowRunField(result, 'version_summary'))
    ? getWorkflowRunField(result, 'version_summary') as Record<string, unknown>
    : {}
  const readiness = getWorkflowRunField(result, 'readiness')
    ?? getWorkflowRunField(result, 'ready')
    ?? versionSummary.readiness
    ?? versionSummary.ready
  return {
    configVersion: getWorkflowRunField(result, 'config_version')
      ?? getWorkflowRunField(result, 'configVersion')
      ?? versionSummary.config_version
      ?? versionSummary.active_version
      ?? versionSummary.current_version,
    readiness,
    willExecute: getWorkflowRunField(result, 'will_execute') ?? getWorkflowRunField(result, 'willExecute'),
    writesBlocked: getWorkflowRunField(result, 'writes_blocked') ?? getWorkflowRunField(result, 'writesBlocked'),
    requiresPublish: getWorkflowRunField(result, 'requires_publish') ?? getWorkflowRunField(result, 'requiresPublish') ?? versionSummary.requires_publish,
  }
}

export function normalizeWorkflowDryRunSteps(result: WorkflowRunResult | null) {
  const raw = result?.steps
  const rows = Array.isArray(raw)
    ? raw
    : (isPlainRecord(raw) ? Object.entries(raw).map(([key, value]) => ({ key, ...(isPlainRecord(value) ? value : { status: value }) })) : [])
  return rows
    .map((step, index) => {
      const row: Record<string, unknown> = isPlainRecord(step) ? step : {}
      const name = row.name ?? row.step ?? row.step_name ?? row.key ?? row.id ?? index + 1
      return {
        index: index + 1,
        name: String(name),
        status: row.status ?? row.readiness ?? row.state ?? '-',
        willExecute: row.will_execute ?? row.willExecute ?? '-',
        writesBlocked: row.writes_blocked ?? row.writesBlocked ?? '-',
      }
    })
}

function formatDiffValue(value: unknown) {
  if (value == null) return '-'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function formatWorkflowDiffStepSide(
  step: WorkflowTemplateDiffStep['before'] | WorkflowTemplateDiffStep['after'],
  formatMessage: (key: MessageKey, params: GraphMessageParams) => string,
) {
  if (!step) return '-'
  const handler = formatDiffValue(step.handler)
  const parts = [
    handler,
    step.name ? String(step.name) : '',
    typeof step.enabled === 'boolean'
      ? formatMessage('graphPage.status.configDiffStepEnabled', { value: String(step.enabled) })
      : '',
    step.params && Object.keys(step.params).length
      ? formatMessage('graphPage.status.configDiffStepParams', { value: formatDiffValue(step.params) })
      : '',
  ].filter(Boolean)
  return parts.join(' ')
}

export function formatContractList(value: unknown) {
  return Array.isArray(value) && value.length ? value.map((item) => String(item)).join(', ') : '-'
}
