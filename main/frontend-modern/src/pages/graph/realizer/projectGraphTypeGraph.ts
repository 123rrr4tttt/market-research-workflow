import type { GraphEdgeItem, GraphNodeItem } from '../../../lib/types'
import { edgeLegendRaw } from './edgeStyleLibrary'
import { normalizeNodeType } from './nodeStyleLibrary'
import { projectGraphNodeKey, type ProjectGraphRelationType } from './projectGraphView'

const FALLBACK_RELATION = 'REL'

function relationKey(relation: ProjectGraphRelationType) {
  return JSON.stringify([relation.sourceType, relation.relation.toLowerCase(), relation.targetType])
}

function appendType(types: string[], seen: Set<string>, rawType: unknown) {
  const type = String(rawType || '').trim()
  if (!type) return
  const normalized = normalizeNodeType(type)
  if (!normalized || seen.has(normalized)) return
  seen.add(normalized)
  types.push(normalized)
}

function appendRelation(
  relations: ProjectGraphRelationType[],
  seen: Set<string>,
  relation: ProjectGraphRelationType,
) {
  const key = relationKey(relation)
  if (seen.has(key)) return
  seen.add(key)
  relations.push(relation)
}

function effectiveRelation(edge: GraphEdgeItem) {
  return String(edgeLegendRaw(edge) || FALLBACK_RELATION).trim() || FALLBACK_RELATION
}

function normalizeRelation(value: string) {
  const relation = value.trim().toLowerCase()
  return relation || FALLBACK_RELATION
}

export function buildProjectGraphTypeGraph(
  nodes: GraphNodeItem[],
  edges: GraphEdgeItem[],
  declaredNodeTypes: string[],
  declaredRelationTypes: ProjectGraphRelationType[],
): { nodeTypes: string[]; relations: ProjectGraphRelationType[] } {
  const nodeTypes: string[] = []
  const nodeTypeSeen = new Set<string>()
  const relations: ProjectGraphRelationType[] = []
  const relationSeen = new Set<string>()
  const typeByNodeKey = new Map(nodes.map((node) => [projectGraphNodeKey(node), normalizeNodeType(node.type)]))

  declaredNodeTypes.forEach((type) => appendType(nodeTypes, nodeTypeSeen, type))
  declaredRelationTypes.forEach((relation) => {
    appendType(nodeTypes, nodeTypeSeen, relation.sourceType)
    appendType(nodeTypes, nodeTypeSeen, relation.targetType)
    appendRelation(relations, relationSeen, {
      sourceType: normalizeNodeType(relation.sourceType),
      targetType: normalizeNodeType(relation.targetType),
      relation: normalizeRelation(relation.relation),
    })
  })

  nodes.forEach((node) => {
    appendType(nodeTypes, nodeTypeSeen, node.type)
  })
  edges.forEach((edge) => {
    const sourceType = typeByNodeKey.get(projectGraphNodeKey(edge.from))
    const targetType = typeByNodeKey.get(projectGraphNodeKey(edge.to))
    if (!sourceType || !targetType) return
    appendType(nodeTypes, nodeTypeSeen, sourceType)
    appendType(nodeTypes, nodeTypeSeen, targetType)
    appendRelation(relations, relationSeen, {
      sourceType,
      targetType,
      relation: effectiveRelation(edge),
    })
  })

  nodeTypes.sort((a, b) => a.localeCompare(b, 'zh-CN'))
  relations.sort((a, b) => relationKey(a).localeCompare(relationKey(b), 'zh-CN'))
  return { nodeTypes, relations }
}
