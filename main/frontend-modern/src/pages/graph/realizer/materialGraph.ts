import { isCanonicalMaterialRef, normalizeMaterialGraphId, normalizeMaterialRef } from '../../../features/information-topology/materialIdentity'
import type { AdminDocumentItem, GraphEdgeItem, GraphNodeItem, GraphResponse } from '../../../lib/types'
import { normalizeNodeType } from './nodeStyleLibrary'

export function materialReaderId(node: GraphNodeItem | null): number | null {
  if (!node) return null
  const ref = node.material_ref ?? node.topology_ref
  const value = node.material_id ?? node.document_id ?? (isCanonicalMaterialRef(ref) ? ref.local_id
    : !node.topology_ref && normalizeNodeType(node.type) === 'material' ? node.id : undefined)
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}

export function normalizeMaterialGraphNode(node: GraphNodeItem): GraphNodeItem {
  const legacyPlacement = node.document_id != null && !isCanonicalMaterialRef(node.material_ref) ? node.material_ref : undefined
  const ref = isCanonicalMaterialRef(node.material_ref) ? node.material_ref : node.topology_ref
  return {
    ...node,
    id: normalizeMaterialGraphId(node.id),
    type: normalizeNodeType(node.type),
    ...(isCanonicalMaterialRef(ref) ? { topology_ref: normalizeMaterialRef(ref), material_ref: normalizeMaterialRef(ref) } : {}),
    ...(node.placement_ref || legacyPlacement ? { placement_ref: node.placement_ref ?? legacyPlacement } : {}),
    ...(materialReaderId(node) != null ? { material_id: materialReaderId(node) } : {}),
  }
}

export function normalizeMaterialGraphEdge(edge: GraphEdgeItem): GraphEdgeItem {
  const endpoint = (value: GraphEdgeItem['from']) => ({
    ...value, id: value.id == null ? value.id : normalizeMaterialGraphId(value.id), type: normalizeNodeType(value.type),
  })
  return { ...edge, from: endpoint(edge.from), to: endpoint(edge.to) }
}

function populatedFields(record: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(record).filter(([, value]) => value != null && value !== ''
    && (!Array.isArray(value) || value.length > 0)))
}

function mergeMaterialNode(fallback: GraphNodeItem, preferred: GraphNodeItem): GraphNodeItem {
  const merged = { ...fallback, ...populatedFields(preferred) } as GraphNodeItem
  // Hydrated metadata and placement observations can arrive on different aliases.
  for (const field of ['topology_attributes', 'extracted_data']) {
    const left = fallback[field]
    const right = preferred[field]
    if (left && right && typeof left === 'object' && typeof right === 'object'
      && !Array.isArray(left) && !Array.isArray(right)) {
      merged[field] = { ...left, ...populatedFields(right as Record<string, unknown>) }
    }
  }
  return merged
}

export function normalizeMaterialGraph(graph: GraphResponse): GraphResponse {
  const nodes = new Map<string, GraphNodeItem>()
  const canonicalKeys = new Set<string>()
  for (const raw of graph.nodes) {
    const node = normalizeMaterialGraphNode(raw)
    const key = `${node.type}:${node.id}`
    const previous = nodes.get(key)
    const canonical = raw.type === 'material' && raw.id === node.id
    nodes.set(key, previous && node.type === 'material'
      ? canonical || !canonicalKeys.has(key) ? mergeMaterialNode(previous, node) : mergeMaterialNode(node, previous)
      : node)
    if (canonical) canonicalKeys.add(key)
  }
  return { ...graph, nodes: [...nodes.values()], edges: graph.edges.map(normalizeMaterialGraphEdge) }
}

/** Read-only projection of canonical Document rows into GraphPage material nodes. */
export function projectDocumentMaterials(items: AdminDocumentItem[], projectKey: string): GraphResponse {
  const nodes = items.flatMap((item): GraphNodeItem[] => {
    const materialId = Number(item.material_id ?? item.id)
    if (!Number.isSafeInteger(materialId) || materialId <= 0) return []
    const materialRef = {
      project_key: projectKey,
      module_id: 'materials',
      namespace: 'materials',
      type_id: 'material',
      local_id: String(materialId),
    }
    const title = String(item.title || item.uri || `Material ${materialId}`)
    return [{
      id: String(materialId),
      entry_id: String(materialId),
      type: 'material',
      name: title,
      title,
      material_id: materialId,
      topology_ref: materialRef,
      material_ref: materialRef,
      observed_revision: String(item.updated_at || item.created_at || 'current'),
      doc_type: item.doc_type,
      state: item.state,
      uri: item.uri,
    }]
  })
  return normalizeMaterialGraph({ nodes, edges: [], source_kind: 'document_materials' })
}
