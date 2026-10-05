import type { GraphEdgeItem, GraphNodeItem } from '../../../lib/types'
import { edgeLegendKey } from './edgeStyleLibrary'
import { normalizeNodeType } from './nodeStyleLibrary'
import { normalizeMaterialGraphId } from '../../../features/information-topology/materialIdentity'
import { normalizeMaterialGraph, normalizeMaterialGraphEdge, normalizeMaterialGraphNode } from './materialGraph'

export type ProjectGraphRelationType = {
  sourceType: string
  targetType: string
  relation: string
}

export type ProjectGraphViewSpec = {
  schema: 'project-graph-view/v1'
  mode: 'all' | 'selection'
  display?: { renderMode: '2d' | 'projection3d' }
  nodeKeys: string[]
  hiddenNodeTypes: string[]
  hiddenEdgeKinds: string[]
  additionalNodes: GraphNodeItem[]
  additionalEdges: GraphEdgeItem[]
  declaredNodeTypes?: string[]
  declaredRelationTypes?: ProjectGraphRelationType[]
}

const PROJECT_GRAPH_VIEW_FIELDS = new Set([
  'schema',
  'mode',
  'display',
  'nodeKeys',
  'hiddenNodeTypes',
  'hiddenEdgeKinds',
  'additionalNodes',
  'additionalEdges',
  'declaredNodeTypes',
  'declaredRelationTypes',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function normalizeStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null
  const items: string[] = []
  const seen = new Set<string>()
  for (const raw of value) {
    if (typeof raw !== 'string') return null
    const item = raw.trim()
    if (!item || seen.has(item)) return null
    seen.add(item)
    items.push(item)
  }
  return items
}

function normalizeNodeKey(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const separator = value.indexOf(':')
  if (separator <= 0 || separator === value.length - 1) return null
  const nodeType = normalizeNodeType(value.slice(0, separator))
  const nodeId = normalizeMaterialGraphId(value.slice(separator + 1).trim())
  if (!nodeType || !nodeId) return null
  return `${nodeType}:${nodeId}`
}

/** Preserve the old material alias only for checking pre-migration duplicates. */
function originalNodeType(value: unknown): string {
  return String(value).trim().toLowerCase() === 'document' ? 'document' : normalizeNodeType(value)
}

function normalizeNodeKeys(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null
  const items: string[] = []
  const seen = new Set<string>()
  const originalKeys = new Set<string>()
  for (const raw of value) {
    const item = normalizeNodeKey(raw)
    if (!item || typeof raw !== 'string') return null
    const separator = raw.indexOf(':')
    const original = `${originalNodeType(raw.slice(0, separator))}:${raw.slice(separator + 1).trim()}`
    if (originalKeys.has(original)) return null
    originalKeys.add(original)
    if (seen.has(item)) continue
    seen.add(item)
    items.push(item)
  }
  return items
}

function normalizeHiddenNodeTypes(value: unknown): string[] | null {
  const items = normalizeStringArray(value)
  if (!items) return null
  const normalized: string[] = []
  const seen = new Set<string>()
  const originalTypes = new Set<string>()
  for (const item of items) {
    const nodeType = normalizeNodeType(item)
    const original = originalNodeType(item)
    if (!nodeType || originalTypes.has(original)) return null
    originalTypes.add(original)
    if (seen.has(nodeType)) continue
    seen.add(nodeType)
    normalized.push(nodeType)
  }
  return normalized
}

function normalizeDisplay(value: unknown): ProjectGraphViewSpec['display'] | null {
  if (value === undefined) return undefined
  if (!isRecord(value) || Object.keys(value).length !== 1) return null
  if (value.renderMode !== '2d' && value.renderMode !== 'projection3d') return null
  return { renderMode: value.renderMode }
}

function normalizeAdditionalNode(raw: unknown): GraphNodeItem | null {
  if (!isRecord(raw)) return null
  const id = raw.id
  if ((typeof id !== 'string' && typeof id !== 'number') || String(id).trim() === '') return null
  if (typeof raw.type !== 'string' || !raw.type.trim()) return null
  const node = normalizeMaterialGraphNode({ ...raw, id, type: raw.type } as GraphNodeItem)
  delete node.x
  delete node.y
  delete node.z
  return node
}

function normalizeAdditionalNodes(value: unknown): GraphNodeItem[] | null {
  if (!Array.isArray(value)) return null
  const nodes: GraphNodeItem[] = []
  const seen = new Set<string>()
  for (const raw of value) {
    const node = normalizeAdditionalNode(raw)
    if (!node || !isRecord(raw)) return null
    const key = `${originalNodeType(raw.type)}:${String(raw.id).trim()}`
    if (seen.has(key)) return null
    seen.add(key)
    nodes.push({ ...node, id: raw.id as string | number, type: raw.type as string })
  }
  return normalizeMaterialGraph({ nodes, edges: [] }).nodes
}

function normalizeEdgeEndpoint(raw: unknown): GraphEdgeItem['from'] | null {
  if (!isRecord(raw)) return null
  const id = raw.id
  if ((typeof id !== 'string' && typeof id !== 'number') || String(id).trim() === '') return null
  if (typeof raw.type !== 'string' || !raw.type.trim()) return null
  return { ...raw, id, type: raw.type } as GraphEdgeItem['from']
}

function normalizeAdditionalEdge(raw: unknown): GraphEdgeItem | null {
  if (!isRecord(raw)) return null
  const from = normalizeEdgeEndpoint(raw.from)
  const to = normalizeEdgeEndpoint(raw.to)
  if (!from || !to) return null
  return normalizeMaterialGraphEdge({ ...raw, from, to } as GraphEdgeItem)
}

function normalizeAdditionalEdges(value: unknown): GraphEdgeItem[] | null {
  if (!Array.isArray(value)) return null
  const edges: GraphEdgeItem[] = []
  const seenStructuralKeys = new Set<string>()
  const seenIds = new Set<string>()
  for (const raw of value) {
    const edge = normalizeAdditionalEdge(raw)
    if (!edge) return null
    const edgeKey = projectGraphEdgeKey(edge)
    const id = String(edge.id ?? '').trim()
    if (seenStructuralKeys.has(edgeKey) || (id && seenIds.has(id))) return null
    seenStructuralKeys.add(edgeKey)
    if (id) seenIds.add(id)
    edges.push(edge)
  }
  return edges
}

function normalizeRelationTypes(value: unknown): ProjectGraphRelationType[] | null {
  if (!Array.isArray(value)) return null
  const relations: ProjectGraphRelationType[] = []
  const seen = new Set<string>()
  const originalKeys = new Set<string>()
  for (const raw of value) {
    if (!isRecord(raw) || Object.keys(raw).some((key) => !['sourceType', 'targetType', 'relation'].includes(key))) return null
    if (typeof raw.sourceType !== 'string' || typeof raw.targetType !== 'string' || typeof raw.relation !== 'string') return null
    const sourceType = normalizeNodeType(raw.sourceType)
    const targetType = normalizeNodeType(raw.targetType)
    const relation = raw.relation.trim().toLowerCase()
    if (!sourceType || !targetType || !relation) return null
    const key = JSON.stringify([sourceType, relation, targetType])
    const original = JSON.stringify([originalNodeType(raw.sourceType), relation, originalNodeType(raw.targetType)])
    if (originalKeys.has(original)) return null
    originalKeys.add(original)
    if (seen.has(key)) continue
    seen.add(key)
    relations.push({ sourceType, targetType, relation })
  }
  return relations
}

export function normalizeProjectGraphViewSpec(value: unknown): ProjectGraphViewSpec | null {
  if (!isRecord(value)) return null
  if (value.schema !== 'project-graph-view/v1') return null
  if (value.mode !== 'all' && value.mode !== 'selection') return null
  if (Object.keys(value).some((key) => !PROJECT_GRAPH_VIEW_FIELDS.has(key))) return null

  const nodeKeys = normalizeNodeKeys(value.nodeKeys)
  const hiddenNodeTypes = normalizeHiddenNodeTypes(value.hiddenNodeTypes)
  const hiddenEdgeKinds = normalizeStringArray(value.hiddenEdgeKinds)
  const display = normalizeDisplay(value.display)
  const additionalNodes = normalizeAdditionalNodes(value.additionalNodes)
  const additionalEdges = normalizeAdditionalEdges(value.additionalEdges)
  const declaredNodeTypes = value.declaredNodeTypes === undefined ? undefined : normalizeHiddenNodeTypes(value.declaredNodeTypes)
  const declaredRelationTypes = value.declaredRelationTypes === undefined ? undefined : normalizeRelationTypes(value.declaredRelationTypes)
  if (!nodeKeys || !hiddenNodeTypes || !hiddenEdgeKinds || display === null || !additionalNodes || !additionalEdges) return null
  if (declaredNodeTypes === null || declaredRelationTypes === null) return null

  return {
    schema: 'project-graph-view/v1',
    mode: value.mode,
    ...(display ? { display } : {}),
    nodeKeys,
    hiddenNodeTypes,
    hiddenEdgeKinds,
    additionalNodes,
    additionalEdges,
    ...(declaredNodeTypes ? { declaredNodeTypes } : {}),
    ...(declaredRelationTypes ? { declaredRelationTypes } : {}),
  }
}

export function projectGraphNodeKey(node: GraphNodeItem): string {
  const nodeType = normalizeNodeType(node.type)
  const nodeId = normalizeMaterialGraphId(String(node.id ?? '').trim())
  return `${nodeType}:${nodeId}`
}

function edgeEndpointKey(endpoint: GraphEdgeItem['from'] | GraphEdgeItem['to']): string | null {
  if (!endpoint) return null
  const nodeType = normalizeNodeType(endpoint.type)
  const nodeId = normalizeMaterialGraphId(String(endpoint.id ?? '').trim())
  return nodeType && nodeId ? `${nodeType}:${nodeId}` : null
}

export function projectGraphEdgeKey(edge: GraphEdgeItem): string {
  const fromKey = edgeEndpointKey(edge.from)
  const toKey = edgeEndpointKey(edge.to)
  const relationToken = String(edge.relation_token || '').trim()
  const relationClass = String(edge.relation_class || '').trim()
  const predicate = String(edge.predicate || edge.predicate_raw || '').trim()
  const type = String(edge.type || '').trim()
  return [
    fromKey || '-',
    toKey || '-',
    relationToken,
    relationClass,
    predicate,
    type,
  ].join('|')
}

export function applyProjectGraphView(
  sourceNodes: GraphNodeItem[],
  sourceEdges: GraphEdgeItem[],
  spec: ProjectGraphViewSpec,
): { nodes: GraphNodeItem[]; edges: GraphEdgeItem[] } {
  const selectionKeys = spec.mode === 'selection' ? new Set(spec.nodeKeys.map(normalizeNodeKey)) : null
  const hiddenNodeTypes = new Set(spec.hiddenNodeTypes.map(normalizeNodeType))
  const nodes: GraphNodeItem[] = []
  const nodeKeys = new Set<string>()
  const sourceNodeKeys = new Set(sourceNodes.map(projectGraphNodeKey))

  sourceNodes.forEach((node) => {
    const key = projectGraphNodeKey(node)
    if (selectionKeys && !selectionKeys.has(key)) return
    if (hiddenNodeTypes.has(normalizeNodeType(node.type))) return
    nodeKeys.add(key)
    nodes.push(node)
  })

  spec.additionalNodes.forEach((node) => {
    if (hiddenNodeTypes.has(normalizeNodeType(node.type))) return
    const key = projectGraphNodeKey(node)
    if (sourceNodeKeys.has(key)) return
    if (nodeKeys.has(key)) return
    nodeKeys.add(key)
    nodes.push(node)
  })

  const hiddenEdgeKinds = new Set(spec.hiddenEdgeKinds)
  const sourceEdgeKeys = new Set(sourceEdges.map(projectGraphEdgeKey))
  const sourceEdgeIds = new Set(sourceEdges.map((edge) => String(edge.id ?? '').trim()).filter(Boolean))
  const additionalStructuralEdgeKeys = new Set<string>()
  const additionalEdgeIds = new Set<string>()
  const edges: GraphEdgeItem[] = []
  const appendVisibleEdge = (edge: GraphEdgeItem, isAdditional: boolean) => {
    if (hiddenEdgeKinds.has(edgeLegendKey(edge))) return
    const fromKey = edgeEndpointKey(edge.from)
    const toKey = edgeEndpointKey(edge.to)
    if (!fromKey || !toKey || !nodeKeys.has(fromKey) || !nodeKeys.has(toKey)) return
    if (isAdditional) {
      const edgeKey = projectGraphEdgeKey(edge)
      const id = String(edge.id ?? '').trim()
      if (sourceEdgeKeys.has(edgeKey)) return
      if (id && sourceEdgeIds.has(id)) return
      if (additionalStructuralEdgeKeys.has(edgeKey)) return
      if (id && additionalEdgeIds.has(id)) return
      additionalStructuralEdgeKeys.add(edgeKey)
      if (id) additionalEdgeIds.add(id)
    }
    edges.push(edge)
  }

  sourceEdges.forEach((edge) => appendVisibleEdge(edge, false))
  spec.additionalEdges.forEach((edge) => appendVisibleEdge(edge, true))
  return { nodes, edges }
}
