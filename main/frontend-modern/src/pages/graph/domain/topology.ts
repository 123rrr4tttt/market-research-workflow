import type { GraphEdgeItem, GraphNodeItem } from '../../../lib/types'

export type VisibleSubgraph = {
  connectedNodes: GraphNodeItem[]
  connectedEdges: GraphEdgeItem[]
  connectedNodeKeys: Set<string>
  visibleNodes: GraphNodeItem[]
  visibleEdges: GraphEdgeItem[]
  visibleNodeKeys: Set<string>
  edgeResolvedKeyMap: Map<GraphEdgeItem, { fromKey: string; toKey: string }>
}

function edgeNodeKey(
  node: GraphEdgeItem['from'] | GraphEdgeItem['to'],
  normalizeNodeType: (rawType: unknown) => string,
) {
  return `${normalizeNodeType(node.type)}:${node.id}`
}

function nodeKey(
  node: GraphNodeItem,
  normalizeNodeType: (rawType: unknown) => string,
) {
  return `${normalizeNodeType(node.type)}:${node.id}`
}

export function collectFocusNodeKeys(centerKey: string, adjacency: Map<string, Set<string>>) {
  const keys = new Set<string>()
  keys.add(centerKey)
  ;(adjacency.get(centerKey) || new Set()).forEach((neighbor) => keys.add(neighbor))
  return keys
}

export function computePageRank(
  nodeKeys: string[],
  directedEdges: Array<{ fromKey: string; toKey: string; weight: number }>,
  damping = 0.85,
  maxIter = 60,
  tol = 1e-7,
) {
  const rank = new Map<string, number>()
  const n = nodeKeys.length
  if (n === 0) return rank
  const init = 1 / n
  nodeKeys.forEach((key) => rank.set(key, init))

  const incoming = new Map<string, Array<{ fromKey: string; weight: number }>>()
  const outWeight = new Map<string, number>()
  directedEdges.forEach(({ fromKey, toKey, weight }) => {
    if (!rank.has(fromKey) || !rank.has(toKey)) return
    const w = Number.isFinite(weight) && weight > 0 ? weight : 1
    const out = (outWeight.get(fromKey) || 0) + w
    outWeight.set(fromKey, out)
    const bucket = incoming.get(toKey) || []
    bucket.push({ fromKey, weight: w })
    incoming.set(toKey, bucket)
  })

  for (let i = 0; i < maxIter; i += 1) {
    let danglingMass = 0
    nodeKeys.forEach((key) => {
      if ((outWeight.get(key) || 0) <= 0) danglingMass += rank.get(key) || 0
    })
    const base = (1 - damping) / n + (damping * danglingMass) / n
    const next = new Map<string, number>()
    let delta = 0
    nodeKeys.forEach((toKey) => {
      let score = base
      const fromList = incoming.get(toKey) || []
      fromList.forEach(({ fromKey, weight }) => {
        const out = outWeight.get(fromKey) || 0
        if (out <= 0) return
        score += damping * ((rank.get(fromKey) || 0) * weight) / out
      })
      next.set(toKey, score)
      delta += Math.abs(score - (rank.get(toKey) || 0))
    })
    nodeKeys.forEach((key) => rank.set(key, next.get(key) || 0))
    if (delta < tol) break
  }
  const total = nodeKeys.reduce((acc, key) => acc + (rank.get(key) || 0), 0)
  if (total > 0) {
    rank.forEach((value, key) => rank.set(key, value / total))
  }
  return rank
}

export function computeCoreNumber(nodeKeys: string[], adjacency: Map<string, Set<string>>) {
  const core = new Map<string, number>()
  if (!nodeKeys.length) return core
  const degree = new Map<string, number>()
  let maxDegree = 0
  nodeKeys.forEach((key) => {
    const d = adjacency.get(key)?.size || 0
    degree.set(key, d)
    if (d > maxDegree) maxDegree = d
  })
  const bins: Array<Set<string>> = Array.from({ length: maxDegree + 1 }, () => new Set<string>())
  nodeKeys.forEach((key) => {
    const d = degree.get(key) || 0
    bins[d].add(key)
  })
  const removed = new Set<string>()
  for (let k = 0; k <= maxDegree; k += 1) {
    while (bins[k].size > 0) {
      const v = bins[k].values().next().value as string
      bins[k].delete(v)
      if (removed.has(v)) continue
      removed.add(v)
      core.set(v, k)
      const neighbors = adjacency.get(v)
      if (!neighbors) continue
      neighbors.forEach((u) => {
        if (removed.has(u)) return
        const du = degree.get(u) || 0
        if (du > k) {
          bins[du].delete(u)
          degree.set(u, du - 1)
          bins[du - 1].add(u)
        }
      })
    }
  }
  return core
}

export function computeVisibleSubgraph(params: {
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
  graphKind: string
  hiddenTypes: Record<string, boolean>
  defaultNodeTypesByKind: Record<string, string[]>
  specialPrefixByKind: Partial<Record<string, string>>
  normalizeNodeType: (rawType: unknown) => string
}): VisibleSubgraph {
  const {
    nodes,
    edges,
    graphKind,
    hiddenTypes,
    defaultNodeTypesByKind,
    specialPrefixByKind,
    normalizeNodeType,
  } = params
  const variantTypes = new Set(defaultNodeTypesByKind[graphKind] || [])
  const variantNodes = nodes.filter((n) => variantTypes.has(normalizeNodeType(n.type)))
  const variantNodeKeys = new Set(variantNodes.map((node) => nodeKey(node, normalizeNodeType)))
  const variantAliasToCanonicalKey = new Map<string, string>()
  const variantIdToCanonicalKeys = new Map<string, Set<string>>()
  const appendIdAlias = (idRaw: unknown, canonical: string) => {
    const id = String(idRaw ?? '').trim()
    if (!id) return
    const bucket = variantIdToCanonicalKeys.get(id) || new Set<string>()
    bucket.add(canonical)
    variantIdToCanonicalKeys.set(id, bucket)
  }
  variantNodes.forEach((node) => {
    const canonical = nodeKey(node, normalizeNodeType)
    appendIdAlias(node.id, canonical)
    const entryId = node.entry_id
    if (entryId == null || String(entryId).trim() === '') return
    variantAliasToCanonicalKey.set(`${node.type}:${entryId}`, canonical)
    appendIdAlias(entryId, canonical)
  })
  const resolveVariantRefKey = (ref: GraphEdgeItem['from'] | GraphEdgeItem['to']) => {
    const raw = edgeNodeKey(ref, normalizeNodeType)
    if (variantNodeKeys.has(raw)) return raw
    const alias = variantAliasToCanonicalKey.get(raw)
    if (alias) return alias
    const idOnly = String(ref.id ?? '').trim()
    if (!idOnly) return null
    const candidates = variantIdToCanonicalKeys.get(idOnly)
    if (!candidates || candidates.size !== 1) return null
    return Array.from(candidates)[0] || null
  }

  const edgeResolvedKeyMap = new Map<GraphEdgeItem, { fromKey: string; toKey: string }>()
  const variantEdges = edges.filter((e) => {
    const fromKey = resolveVariantRefKey(e.from)
    const toKey = resolveVariantRefKey(e.to)
    if (!fromKey || !toKey) return false
    edgeResolvedKeyMap.set(e, { fromKey, toKey })
    return true
  })

  let connectedNodes = variantNodes
  let connectedEdges = variantEdges
  let connectedNodeKeys = new Set(connectedNodes.map((node) => nodeKey(node, normalizeNodeType)))
  const specialPrefix = specialPrefixByKind[graphKind]
  if (specialPrefix) {
    const specialSeedKeys = variantNodes
      .filter((node) => node.type.startsWith(specialPrefix))
      .map((node) => nodeKey(node, normalizeNodeType))
    if (specialSeedKeys.length) {
      const adjacency = new Map<string, Set<string>>()
      variantEdges.forEach((edge) => {
        const resolved = edgeResolvedKeyMap.get(edge)
        if (!resolved) return
        const from = resolved.fromKey
        const to = resolved.toKey
        if (!adjacency.has(from)) adjacency.set(from, new Set())
        if (!adjacency.has(to)) adjacency.set(to, new Set())
        adjacency.get(from)?.add(to)
        adjacency.get(to)?.add(from)
      })
      const reachableFromSpecial = new Set<string>()
      const queue = [...specialSeedKeys]
      while (queue.length) {
        const current = queue.shift()
        if (!current || reachableFromSpecial.has(current)) continue
        reachableFromSpecial.add(current)
        ;(adjacency.get(current) || new Set<string>()).forEach((neighbor) => {
          if (!reachableFromSpecial.has(neighbor)) queue.push(neighbor)
        })
      }
      connectedNodes = variantNodes.filter((node) => reachableFromSpecial.has(nodeKey(node, normalizeNodeType)))
      connectedNodeKeys = new Set(connectedNodes.map((node) => nodeKey(node, normalizeNodeType)))
      connectedEdges = variantEdges.filter((edge) => {
        const resolved = edgeResolvedKeyMap.get(edge)
        if (!resolved) return false
        return connectedNodeKeys.has(resolved.fromKey) && connectedNodeKeys.has(resolved.toKey)
      })
    }
  }

  const visibleNodes = connectedNodes.filter((node) => !hiddenTypes[node.type])
  const visibleNodeKeys = new Set(visibleNodes.map((node) => nodeKey(node, normalizeNodeType)))
  const visibleEdges = connectedEdges.filter((edge) => {
    const resolved = edgeResolvedKeyMap.get(edge)
    if (!resolved) return false
    return visibleNodeKeys.has(resolved.fromKey) && visibleNodeKeys.has(resolved.toKey)
  })

  return {
    connectedNodes,
    connectedEdges,
    connectedNodeKeys,
    visibleNodes,
    visibleEdges,
    visibleNodeKeys,
    edgeResolvedKeyMap,
  }
}
