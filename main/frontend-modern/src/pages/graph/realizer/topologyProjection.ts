import type { CurrentTopologyItem, BoundRef } from '../../../features/information-topology/types'
import type { GraphEdgeItem, GraphNodeItem, GraphResponse } from '../../../lib/types'
import { topologyDisplayName } from './displaySchema'

/** Relation realization depth guard: a relation axis resolves through at most this many hops. */
const RELATION_AXIS_MAX_DEPTH = 4

/** Identity follows the complete observed reference so revisions never merge silently. */
export function topologyBoundIdentity(bound: BoundRef): string {
  const ref = bound.ref
  return JSON.stringify([
    ref.project_key, ref.module_id, ref.namespace, ref.type_id, ref.local_id,
    bound.observed_revision, bound.content_digest ?? null,
  ])
}

function textValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

type ProjectedElement = CurrentTopologyItem['topology']['elements'][number]

/**
 * Reads the profile-declared projection role. A relation element is realized as
 * one edge between the two endpoints its axis names; anything else stays a node.
 */
function declaredRelationAxis(element: ProjectedElement): [string, string] | undefined {
  const attributes = element.attributes as Record<string, unknown>
  if (attributes.structural_role !== 'relation') return undefined
  const axis = attributes.relation_axis
  if (!Array.isArray(axis) || axis.length !== 2) return undefined
  const [sourceRole, targetRole] = axis.map((role) => textValue(role))
  if (!sourceRole || !targetRole) return undefined
  return [sourceRole, targetRole]
}

/**
 * Reads the profile-declared projection role. Annotated elements record the
 * retrieval process — execution logs, plans, registries, vocabulary snapshots
 * and chain threads — so they stay in the topology read model but out of the
 * graph, whose subject is the researched events and their materials.
 */
function isAnnotatedElement(element: ProjectedElement): boolean {
  return (element.attributes as Record<string, unknown>).structural_role === 'annotation'
}

type ProjectedNodeRef = { id: string; type: string }

/** Project-declared narrowing: keep elements whose attribute text matches, plus their closure. */
export type TopologyProjectionFilter = {
  attribute: string
  containsAny: readonly string[]
}

/**
 * Read-model projection from heterogeneous topology states to GraphPage's
 * directed graph.
 *
 * The profile declares which types are elements and which are relations. An
 * element becomes a node; a relation becomes one edge between the two endpoints
 * its declared axis names. Elements that keep their own endpoints (candidates,
 * gaps, …) project those endpoints as directed incidence edges, so higher-arity
 * membership stays visible without materializing relation nodes. Types the
 * profile marks as annotations stay out of the graph entirely.
 */
export function projectInformationTopologies(
  items: CurrentTopologyItem[],
  filter?: TopologyProjectionFilter,
): GraphResponse {
  const nodesByIdentity = new Map<string, GraphNodeItem>()
  const edges: GraphEdgeItem[] = []
  let sourceLabel: string | undefined
  let edgeStyleBindings: Record<string, unknown> | undefined
  const relationVocabulary: string[] = []
  const elementsByIdentity = new Map<string, ProjectedElement>()
  const edgeIds = new Set<string>()
  const ensureNode = (bound: BoundRef, attributes: Record<string, unknown> = {}): string => {
    const id = topologyBoundIdentity(bound)
    if (!nodesByIdentity.has(id)) {
      const ref = bound.ref
      const type = ref.type_id
      const displayName = topologyDisplayName(type, attributes)
      nodesByIdentity.set(id, {
        id,
        entry_id: ref.local_id,
        type,
        name: displayName,
        title: displayName,
        canonical_name: displayName,
        topology_ref: ref,
        observed_revision: bound.observed_revision,
        content_digest: bound.content_digest,
        topology_attributes: attributes,
      })
    }
    return id
  }

  const endpointByRole = (element: ProjectedElement, role: string) =>
    element.endpoints.find((endpoint) => endpoint.role === role)

  /**
   * Resolve an endpoint to a node. A target that is itself a relation is
   * followed along its axis target, so relations never become nodes; an
   * unresolvable target yields no node and the edge is skipped.
   */
  const resolveNode = (bound: BoundRef, seen: ReadonlySet<string> = new Set<string>()): ProjectedNodeRef | undefined => {
    const identity = topologyBoundIdentity(bound)
    const element = elementsByIdentity.get(identity)
    if (!element) {
      if (keptIdentities) return undefined
      return { id: ensureNode(bound), type: bound.ref.type_id }
    }
    if (keptIdentities && !keptIdentities.has(identity)) return undefined
    if (isAnnotatedElement(element)) return undefined
    if (seen.has(identity) || seen.size >= RELATION_AXIS_MAX_DEPTH) return undefined
    const axis = declaredRelationAxis(element)
    if (!axis) return { id: ensureNode(bound, element.attributes), type: bound.ref.type_id }
    const target = endpointByRole(element, axis[1])
    if (!target) return undefined
    const nextSeen = new Set<string>(seen)
    nextSeen.add(identity)
    return resolveNode(target.target, nextSeen)
  }

  /**
   * Close a project-declared view over the topology: seed elements match the
   * declared attribute, then their endpoints join, then relations whose axis
   * endpoints are all present join too (that is how evidence reaches a chapter
   * view even though evidence itself carries no chapter attribute).
   */
  function computeKeptIdentities(viewFilter: TopologyProjectionFilter): Set<string> {
    const attributeText = (element: ProjectedElement) => {
      const value = element.attributes[viewFilter.attribute]
      if (Array.isArray(value)) return value.map((entry) => String(entry ?? '')).join(' ')
      return value == null ? '' : String(value)
    }
    const keep = new Set<string>()
    elementsByIdentity.forEach((element, identity) => {
      if (isAnnotatedElement(element)) return
      const text = attributeText(element)
      if (!text) return
      if (viewFilter.containsAny.some((token) => text.includes(token))) keep.add(identity)
    })
    for (let pass = 0; pass < 3; pass += 1) {
      let changed = false
      elementsByIdentity.forEach((element, identity) => {
        if (isAnnotatedElement(element)) return
        if (keep.has(identity)) {
          for (const endpoint of element.endpoints) {
            const targetIdentity = topologyBoundIdentity(endpoint.target)
            if (keep.has(targetIdentity) || !elementsByIdentity.has(targetIdentity)) continue
            keep.add(targetIdentity)
            changed = true
          }
          return
        }
        if (!declaredRelationAxis(element)) return
        const targets = element.endpoints.map((endpoint) => topologyBoundIdentity(endpoint.target))
        if (!targets.length || !targets.every((target) => keep.has(target))) return
        keep.add(identity)
        changed = true
      })
      if (!changed) break
    }
    return keep
  }

  const pushEdge = (edge: GraphEdgeItem) => {
    const edgeId = edge.id
    if (!edgeId) return
    if (edgeIds.has(edgeId)) return
    edgeIds.add(edgeId)
    edges.push(edge)
  }

  // Index every source element first: attributes must exist before any node or
  // edge is materialized, otherwise an endpoint would freeze an empty shell.
  for (const item of items) {
    for (const element of item.topology.elements) {
      elementsByIdentity.set(topologyBoundIdentity(element.ref), element)
      if (element.ref.ref.type_id === 'domain_vocabulary') {
        sourceLabel ||= textValue(element.attributes.name)
        // The declared relation vocabulary is authored in its project order;
        // readers reuse that order to derive default edge styles.
        const declaredEdgeTypes = element.attributes.edge_types
        if (Array.isArray(declaredEdgeTypes)) {
          for (const value of declaredEdgeTypes) {
            const token = textValue(value)
            if (token && !relationVocabulary.includes(token)) relationVocabulary.push(token)
          }
        }
        const rawStyleBindings = element.attributes.edge_style_bindings
        if (rawStyleBindings && typeof rawStyleBindings === 'object' && !Array.isArray(rawStyleBindings)) {
          edgeStyleBindings ||= rawStyleBindings as Record<string, unknown>
        }
      }
    }
  }

  const keptIdentities = filter ? computeKeptIdentities(filter) : undefined
  const isKept = (element: ProjectedElement) =>
    !keptIdentities || keptIdentities.has(topologyBoundIdentity(element.ref))

  // Materialize element nodes. Relations are realized as edges below and
  // annotated elements stay out of the graph; neither becomes a node.
  for (const item of items) {
    for (const element of item.topology.elements) {
      if (isAnnotatedElement(element) || declaredRelationAxis(element) || !isKept(element)) continue
      ensureNode(element.ref, element.attributes)
    }
  }
  for (const item of items) {
    for (const element of item.topology.elements) {
      if (isAnnotatedElement(element) || !isKept(element)) continue
      const axis = declaredRelationAxis(element)
      if (axis) {
        const source = endpointByRole(element, axis[0])
        const target = endpointByRole(element, axis[1])
        if (!source || !target) continue
        const sourceNode = resolveNode(source.target)
        const targetNode = resolveNode(target.target)
        if (!sourceNode || !targetNode) continue
        pushEdge({
          id: `relation:${topologyBoundIdentity(element.ref)}`,
          type: 'topology_relation',
          predicate: axis[0],
          predicate_raw: axis[0],
          relation_class: element.ref.ref.type_id,
          relation_token: textValue(element.attributes.relation_token),
          topology_relation_ref: element.ref.ref,
          topology_relation_revision: element.ref.observed_revision,
          topology_attributes: element.attributes,
          from: { id: sourceNode.id, type: sourceNode.type },
          to: { id: targetNode.id, type: targetNode.type },
        })
        continue
      }
      const sourceId = ensureNode(element.ref, element.attributes)
      // A profile may declare which authored attribute carries the element's
      // domain relation token; the read model derives it, readers only consume it.
      const relationToken = textValue((element.attributes as Record<string, unknown>).relation_token)
      for (const endpoint of element.endpoints) {
        const targetNode = resolveNode(endpoint.target)
        if (!targetNode) continue
        pushEdge({
          id: `${sourceId}→${endpoint.role}→${targetNode.id}→${endpoint.position ?? ''}`,
          type: 'topology_incidence',
          predicate: endpoint.role,
          predicate_raw: endpoint.role,
          relation_class: element.ref.ref.type_id,
          relation_token: relationToken,
          topology_relation_ref: element.ref.ref,
          topology_relation_revision: element.ref.observed_revision,
          endpoint_position: endpoint.position,
          from: { id: sourceId, type: element.ref.ref.type_id },
          to: { id: targetNode.id, type: targetNode.type },
        })
      }
    }
  }
  return {
    nodes: Array.from(nodesByIdentity.values()),
    edges,
    source_label: sourceLabel,
    edge_style_bindings: edgeStyleBindings,
    relation_vocabulary: relationVocabulary.length ? relationVocabulary : undefined,
  }
}

/** Retrieval-domain profile is a project-bound semantic contract, not a renderer kind. */
export function hasProjectRetrievalSemantics(items: CurrentTopologyItem[]): boolean {
  return items.some((item) => item.profile_id.startsWith('retrieval.domain.'))
}
