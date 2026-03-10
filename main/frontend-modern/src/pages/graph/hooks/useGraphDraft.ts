import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { GraphEdgeItem, GraphNodeItem } from '../../../lib/types'

type GraphNodeKeyGetter = (node: GraphNodeItem) => string

type UseGraphDraftParams = {
  sourceNodes: GraphNodeItem[]
  sourceEdges: GraphEdgeItem[]
  getNodeKey: GraphNodeKeyGetter
}

function cloneNode(node: GraphNodeItem): GraphNodeItem {
  return { ...node }
}

function cloneEdge(edge: GraphEdgeItem): GraphEdgeItem {
  return {
    ...edge,
    from: { ...(edge.from || {}) },
    to: { ...(edge.to || {}) },
  }
}

function cloneSnapshot(nodes: GraphNodeItem[], edges: GraphEdgeItem[]) {
  return {
    nodes: nodes.map(cloneNode),
    edges: edges.map(cloneEdge),
  }
}

function buildEdgeKey(edge: GraphEdgeItem) {
  const fromType = String(edge.from?.type || '').trim()
  const fromId = String(edge.from?.id || '').trim()
  const toType = String(edge.to?.type || '').trim()
  const toId = String(edge.to?.id || '').trim()
  const rel = String(edge.predicate || edge.type || '').trim()
  return `${fromType}:${fromId}>${toType}:${toId}|${rel}`
}

export function useGraphDraft({ sourceNodes, sourceEdges, getNodeKey }: UseGraphDraftParams) {
  const [draftNodes, setDraftNodes] = useState<GraphNodeItem[]>(() => sourceNodes.map(cloneNode))
  const [draftEdges, setDraftEdges] = useState<GraphEdgeItem[]>(() => sourceEdges.map(cloneEdge))
  const [dirty, setDirty] = useState(false)
  const baseRef = useRef(cloneSnapshot(sourceNodes, sourceEdges))
  const nextNodeSeqRef = useRef(1)

  useEffect(() => {
    if (dirty) return
    const snap = cloneSnapshot(sourceNodes, sourceEdges)
    baseRef.current = snap
    const timerId = window.setTimeout(() => {
      setDraftNodes(snap.nodes)
      setDraftEdges(snap.edges)
    }, 0)
    return () => {
      window.clearTimeout(timerId)
    }
  }, [sourceNodes, sourceEdges, dirty])

  const nodeByKey = useMemo(() => {
    return new Map(draftNodes.map((node) => [getNodeKey(node), node]))
  }, [draftNodes, getNodeKey])

  const resetDraft = useCallback(() => {
    const snap = cloneSnapshot(baseRef.current.nodes, baseRef.current.edges)
    setDraftNodes(snap.nodes)
    setDraftEdges(snap.edges)
    setDirty(false)
  }, [])

  const markSaved = useCallback(() => {
    const snap = cloneSnapshot(draftNodes, draftEdges)
    baseRef.current = snap
    setDirty(false)
  }, [draftNodes, draftEdges])

  const replaceDraft = useCallback((nodes: GraphNodeItem[], edges: GraphEdgeItem[], options?: { markAsDirty?: boolean }) => {
    const snap = cloneSnapshot(nodes, edges)
    setDraftNodes(snap.nodes)
    setDraftEdges(snap.edges)
    setDirty(options?.markAsDirty ?? true)
  }, [])

  const createNode = useCallback((seed?: Partial<GraphNodeItem>) => {
    const idSeed = `${Date.now()}-${nextNodeSeqRef.current}`
    nextNodeSeqRef.current += 1
    const node: GraphNodeItem = {
      id: String(seed?.id || `draft-${idSeed}`),
      type: String(seed?.type || 'Entity'),
      name: String(seed?.name || seed?.title || `Node ${idSeed}`),
      ...seed,
    }
    setDraftNodes((prev) => [...prev, cloneNode(node)])
    setDirty(true)
    return node
  }, [])

  const updateNodeByKey = useCallback((key: string, patch: Partial<GraphNodeItem>) => {
    let changed = false
    setDraftNodes((prev) => prev.map((node) => {
      if (getNodeKey(node) !== key) return node
      changed = true
      return { ...node, ...patch }
    }))
    if (changed) setDirty(true)
    return changed
  }, [getNodeKey])

  const removeNodesByKeys = useCallback((keys: Iterable<string>) => {
    const drop = new Set(Array.from(keys))
    if (!drop.size) return { removedNodes: 0, removedEdges: 0 }
    const keepNodes = draftNodes.filter((node) => !drop.has(getNodeKey(node)))
    if (keepNodes.length === draftNodes.length) return { removedNodes: 0, removedEdges: 0 }
    const keepNodePairs = new Set(keepNodes.map((node) => `${String(node.type)}:${String(node.id)}`))
    const keepEdges = draftEdges.filter((edge) => {
      const fromPair = `${String(edge.from?.type || '')}:${String(edge.from?.id || '')}`
      const toPair = `${String(edge.to?.type || '')}:${String(edge.to?.id || '')}`
      return keepNodePairs.has(fromPair) && keepNodePairs.has(toPair)
    })
    setDraftNodes(keepNodes)
    setDraftEdges(keepEdges)
    setDirty(true)
    return {
      removedNodes: draftNodes.length - keepNodes.length,
      removedEdges: draftEdges.length - keepEdges.length,
    }
  }, [draftNodes, draftEdges, getNodeKey])

  const createEdgeByNodeKeys = useCallback((sourceKey: string, targetKey: string, patch?: Partial<GraphEdgeItem>) => {
    const source = nodeByKey.get(sourceKey)
    const target = nodeByKey.get(targetKey)
    if (!source || !target) return { ok: false, reason: 'source_or_target_not_found' as const }
    const candidate: GraphEdgeItem = {
      type: String(patch?.type || 'REL'),
      predicate: String(patch?.predicate || ''),
      from: { id: source.id, type: source.type },
      to: { id: target.id, type: target.type },
      ...patch,
    }
    const edgeKey = buildEdgeKey(candidate)
    const exists = draftEdges.some((edge) => buildEdgeKey(edge) === edgeKey)
    if (exists) return { ok: false, reason: 'already_exists' as const }
    setDraftEdges((prev) => [...prev, cloneEdge(candidate)])
    setDirty(true)
    return { ok: true as const }
  }, [nodeByKey, draftEdges])

  const removeEdgeAt = useCallback((index: number) => {
    if (!(index >= 0 && index < draftEdges.length)) return false
    setDraftEdges((prev) => prev.filter((_, idx) => idx !== index))
    setDirty(true)
    return true
  }, [draftEdges.length])

  return {
    draftNodes,
    draftEdges,
    nodeByKey,
    dirty,
    resetDraft,
    markSaved,
    replaceDraft,
    createNode,
    updateNodeByKey,
    removeNodesByKeys,
    createEdgeByNodeKeys,
    removeEdgeAt,
  }
}
