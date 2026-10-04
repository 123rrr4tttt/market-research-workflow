import { Component, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsType } from 'echarts/core'
import { Activity, Boxes, Building2, ChartPie, GitBranchPlus, LoaderCircle, Network, Package, Workflow } from 'lucide-react'
import * as THREE from 'three'
import {
  getGraphConfig,
  getAdminDocument,
  getMarketGraph,
  getPolicyGraph,
  getSocialGraph,
  listSourceItems,
  buildWorkflowGraphReportingHandoff,
  listWorkflowGraphCuratedAudits,
  replayWorkflowGraphHandoff,
  rollbackWorkflowGraphCuratedState,
  saveWorkflowGraphCuratedDraft,
  submitGraphStructuredSearchTasks,
  submitWorkflowGraphCuratedDraft,
  syncWorkflowGraphCuratedState,
} from '../lib/api'
import type { WorkflowGraphAuditRecord, WorkflowGraphCuratedStateResponse } from '../lib/api'
import type {
  GraphEdgeItem,
  GraphNodeItem,
  GraphResponse,
  GraphStructuredDashboardParams,
  GraphStructuredSearchResponse,
  SourceLibraryItem,
  WorkflowTemplateStageName,
} from '../lib/types'
import { queryKeys } from '../lib/queryKeys'
import { GRAPH_COLOR_THEMES, assignLegendColors, type PaletteKey } from '../lib/graph-colors'
import { applyRenderer2D, RENDERER_2D_CAPABILITIES } from './graph/renderers/renderer2dEcharts'
import { graphCanvasPixelRatio } from './graph/renderers/canvasPixelRatio'
import {
  applyRendererProjection3D,
  RENDERER_PROJECTION_3D_CAPABILITIES,
  quatFromAxisAngle,
  quatFromEulerDeg,
  quatMul,
  rotateVecByQuat,
  type QuaternionLike,
  type Projection3DPhysicsState,
} from './graph/renderers/renderer3dProjection'
import { getOrCreateForceNodeObject, linkEnds, pruneForceNodeObjectCache } from './graph/renderers/force3dObjects'
import { collectFocusNodeKeys, computeCoreNumber, computePageRank, computeVisibleSubgraph } from './graph/domain/topology'
import { useForceGraph3DLoader } from './graph/hooks/useForceGraph3DLoader'
import { useForceGraphViewport } from './graph/hooks/useForceGraphViewport'
import { useGraphDisplayResourceScheduler } from './graph/hooks/useGraphDisplayResourceScheduler'
import { useGraphVisualState } from './graph/hooks/useGraphVisualState'
import { useGraphSelectionState } from './graph/hooks/useGraphSelectionState'
import { useGraphModeSwitch, type ProjectionEngine } from './graph/hooks/useGraphModeSwitch'
import { useGraphDraft } from './graph/hooks/useGraphDraft'
import { useWorkflowTemplateController } from './graph/hooks/useWorkflowTemplateController'
import type { RenderNode } from './graph/renderers/types'
import { ClueChainInspector } from './graph/ClueChainInspector'
import { GraphTopologyPanel } from './graph/GraphTopologyPanel'
import GraphBusinessCardSections from '../components/GraphBusinessCardSections'
import { getGraphProjection, GRAPH_PROJECTIONS_BY_KIND, type GraphProjectionId } from './graph/realizer/definitions'
import type { GraphProjectionDefinition } from './graph/realizer/contract'
import { readGraphProjection } from './graph/realizer/sourceAdapter'
import {
  applyWorkspaceTabBindings,
  coerceGraphProjectionBindings,
  GRAPH_WORKSPACE_TABS,
  type GraphWorkspaceTab,
} from './graph/realizer/workspaceNavigation'
import {
  classifyGraphLegendType,
  compareGraphLegendGroups,
  GRAPH_LEGEND_GROUP_LABEL_KEY,
  type GraphLegendGroupId,
} from './graph/realizer/legendClassification'
import {
  coerceGraphEdgeStyleBinding,
  defaultRelationTokenBinding,
  EDGE_STYLE_CATALOG,
  edgeLegendKey,
  edgeLegendLabel,
  edgeLegendTier,
  edgeLinePattern,
  graphEdgeProfile,
  mergeEdgeStyleBindings,
  GRAPH_EDGE_STROKE_LABEL_KEY,
  GRAPH_EDGE_LINE_TYPE_LABEL_KEY,
  type EdgeLegendTier,
  type EdgeLegendItem,
  type EdgeLineType,
  type EdgeStrokeKind,
  type EdgeSymbolName,
} from './graph/realizer/edgeStyleLibrary'
import { EdgeLegendBadge } from './graph/realizer/EdgeLegendBadge'
import { NodeLegendShape } from './graph/renderers/NodeLegendShape'
import {
  clampControlPanelWidth,
  clampFloatingPanelHeight,
  clampFloatingPanelWidth,
  computeNodeVisualSize,
  normalizeMapValues,
  percentile,
  NODE_SIZE_MIN_APPROX,
} from './graph/realizer/graphGeometry'
import {
  normalizeNodeType,
  resolveNodeSymbol,
  symbolSizeGain,
  computeEmptyNodeBorderWidth,
  toGraphSymbol,
  TOPIC_TAG_CONVEX_SYMBOL_PATH,
  type BuiltinGraphSymbol,
} from './graph/realizer/nodeStyleLibrary'
import {
  buildCuratedWorkflowGraphDsl,
  curatedSubmitFailure,
  curatedNodeId,
  formatContractList,
  formatWorkflowDiffStepSide,
  formatWorkflowRunScalar,
  isPlainRecord,
  snapshotDslFromCuratedState,
  temporaryCuratedNodeIds,
} from './graph/realizer/workflowTemplate'
import {
  createClueChain,
  decideClueChainCandidate,
  expandClueChain,
  type ClueChainDetail,
  type ClueChainSeedNode,
} from './graph/clueChainClient'
import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'

type Variant = GraphProjectionId

const GRAPH_WORKSPACE_TAB_ICONS: Record<string, typeof Network> = {
  graphMarket: ChartPie,
  graphPolicy: Network,
  graphSocial: Activity,
  graphCompany: Building2,
  graphProduct: Package,
  graphOperation: Workflow,
  graphDeep: Boxes,
  graphBuilder: GitBranchPlus,
}

type Props = {
  projectKey: string
  variant: Variant
  templateBuilder?: boolean
}

type GraphMessageParams = Record<string, number | string>

type ForceLinkStyle = {
  color: string
  width: number
  opacity: number
  curvature: number
  curveRotation: number
  arrowLength: number
}

type GraphKind = GraphProjectionDefinition['graphKind']
type ForceGraphApi = {
  scene?: () => THREE.Scene | undefined
  resumeAnimation?: () => void
  pauseAnimation?: () => void
  width?: (value: number) => void
  height?: (value: number) => void
  d3Force?: (name: string, force?: unknown) => unknown
  d3ReheatSimulation?: () => void
}

type ForceNodePhysics = {
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
}

type Graph3DVisibilityStats = {
  dataNodes: number
  sceneNodeObjects: number
  emptyDataNodes: number
  emptySceneNodeObjects: number
}

type ForceGraphRenderBoundaryProps = {
  children: ReactNode
  onError: (message: string) => void
  fallbackErrorMessage: string
  resetKey: string
}

type ForceGraphRenderBoundaryState = {
  failed: boolean
}

class ForceGraphRenderBoundary extends Component<ForceGraphRenderBoundaryProps, ForceGraphRenderBoundaryState> {
  state: ForceGraphRenderBoundaryState = { failed: false }

  static getDerivedStateFromError(): ForceGraphRenderBoundaryState {
    return { failed: true }
  }

  componentDidCatch(error: Error) {
    this.props.onError(error.message || this.props.fallbackErrorMessage)
  }

  componentDidUpdate(prevProps: ForceGraphRenderBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.failed) {
      this.setState({ failed: false })
    }
  }

  render() {
    if (this.state.failed) return null
    return this.props.children
  }
}

declare global {
  interface Window {
    __graph3dDebug?: {
      getVisibilityStats: () => Graph3DVisibilityStats
    }
    __graphPageE2E?: {
      selectNode: (nodeId: string) => boolean
    }
  }
}

let echartsCorePromise: Promise<typeof import('echarts/core')> | null = null

async function loadGraphEchartsCore() {
  if (!echartsCorePromise) {
    echartsCorePromise = (async () => {
      const echarts = await import('echarts/core')
      const { GraphChart } = await import('echarts/charts')
      const { TooltipComponent } = await import('echarts/components')
      const { CanvasRenderer } = await import('echarts/renderers')
      echarts.use([GraphChart, TooltipComponent, CanvasRenderer])
      return echarts
    })()
  }
  return echartsCorePromise
}

const FORCE_3D_GLOBAL_SIZE_GAIN = 1.32
const FORCE_3D_SIZE_COMPENSATION_MAX_X = 8
const NODE_SIZE_SLIDER_MIN = 0
const NODE_SIZE_SLIDER_MAX = 220
const NODE_CONTRAST_SLIDER_MIN = 0
const NODE_CONTRAST_SLIDER_MAX = 100
const RANK_WEIGHT_SLIDER_MIN = 0
const RANK_WEIGHT_SLIDER_MAX = 100
const RANK_WEIGHT_DEFAULT = 50
// Node labels follow the explicit "show labels" control: density is handled by
// the renderer's overlap hiding, not by hiding every label behind a size gate.
const NODE_LABEL_MAX_VISIBLE_NODES = 220
const NODE_LABEL_MIN_SIZE_PX = 10
function computeForce3DSizeCompensationX(nodeScale: number) {
  void nodeScale
  return FORCE_3D_SIZE_COMPENSATION_MAX_X
}

function hashText(input: string) {
  let h = 0
  for (let i = 0; i < input.length; i += 1) h = (h * 31 + input.charCodeAt(i)) >>> 0
  return h
}

function hexToRgb(hex: string) {
  const raw = hex.replace('#', '')
  return {
    r: parseInt(raw.slice(0, 2), 16),
    g: parseInt(raw.slice(2, 4), 16),
    b: parseInt(raw.slice(4, 6), 16),
  }
}

function distinctChipColor(index: number) {
  const hue = Math.round((index * 137.508) % 360)
  return `hsl(${hue} 78% 62%)`
}

function nodeKey(node: GraphNodeItem) {
  return `${normalizeNodeType(node.type)}:${node.id}`
}

function nodeName(node: GraphNodeItem) {
  return String(node.name || node.title || node.text || node.canonical_name || node.id)
}

function nodeTypeLabel(nodeType: string, labels?: Record<string, string>) {
  if (labels?.[nodeType]) return labels[nodeType]
  return nodeType.startsWith('node:') ? nodeType.slice('node:'.length) : nodeType
}


const GRAPH_EDGE_TIER_LABEL_KEY: Record<EdgeLegendTier, MessageKey> = {
  domain: 'graphPage.edgeTier.domain',
  class: 'graphPage.edgeTier.class',
  pred: 'graphPage.edgeTier.pred',
  type: 'graphPage.edgeTier.type',
}

const GRAPH_RELATION_CLASS_LABEL_KEY: Record<string, MessageKey> = {
  evidence: 'graphPage.relationClass.evidence',
  judgment: 'graphPage.relationClass.judgment',
  clue: 'graphPage.relationClass.clue',
  topology_incidence: 'graphPage.relationClass.incidence',
  governance: 'graphPage.relationClass.governance',
  event: 'graphPage.relationClass.event',
  metric: 'graphPage.relationClass.metric',
  impact: 'graphPage.relationClass.impact',
  collaboration: 'graphPage.relationClass.collaboration',
  dependency: 'graphPage.relationClass.dependency',
  supply_chain: 'graphPage.relationClass.supplyChain',
  distribution: 'graphPage.relationClass.distribution',
  competition: 'graphPage.relationClass.competition',
  operation: 'graphPage.relationClass.operation',
  taxonomy: 'graphPage.relationClass.taxonomy',
  targeting: 'graphPage.relationClass.targeting',
  channel: 'graphPage.relationClass.channel',
  strategy: 'graphPage.relationClass.strategy',
  composition: 'graphPage.relationClass.composition',
  other: 'graphPage.relationClass.other',
}

const GRAPH_CARD_FIELD_LABEL_KEY: Record<string, MessageKey> = {
  type: 'graphPage.field.type',
  id: 'graphPage.field.id',
  title: 'graphPage.field.title',
  name: 'graphPage.field.name',
  state: 'graphPage.field.state',
  platform: 'graphPage.field.platform',
  game: 'graphPage.field.game',
  policyType: 'graphPage.field.policyType',
  status: 'graphPage.field.status',
  date: 'graphPage.field.date',
}

function formatGraphMessage(template: string, params: GraphMessageParams) {
  return Object.entries(params).reduce(
    (message, [key, value]) => message.split(`{${key}}`).join(String(value)),
    template,
  )
}

const DEFAULT_NODE_TYPES_BY_KIND = Object.fromEntries(
  Object.values(GRAPH_PROJECTIONS_BY_KIND).map((definition) => [definition.graphKind, definition.nodeTypes]),
) as Record<GraphKind, readonly string[]>

type FilterState = {
  startDate: string
  endDate: string
  state: string
  policyType: string
  platform: string
  topic: string
  game: string
  limit: number
}

type NodeRankStrategy = 'doc_body' | 'node_connectivity' | 'doc_id'

type NodeCardAnchor = {
  left: number
  top: number
  width: number
}

const NODE_CARD_WIDTH = 360
const NODE_CARD_MARGIN = 14
const NODE_CARD_POINTER_OFFSET = 10
const NODE_CARD_LONG_PRESS_MS = 320
const RIGHT_TOGGLE_DEDUPE_MS = 220
const GRAPH_LIMIT_MIN = 1
const GRAPH_LIMIT_MAX = 2000
const GRAPH_LIMIT_DEFAULT = 100

function clampGraphLimit(value: number) {
  if (!Number.isFinite(value)) return GRAPH_LIMIT_DEFAULT
  return Math.max(GRAPH_LIMIT_MIN, Math.min(GRAPH_LIMIT_MAX, Math.trunc(value)))
}


function cardFields(node: GraphNodeItem, labelFor: (field: keyof typeof GRAPH_CARD_FIELD_LABEL_KEY) => string) {
  const list: Array<[string, string]> = [
    [labelFor('type'), String(node.type || '-')],
    [labelFor('id'), String(node.id || '-')],
    [labelFor('title'), String(node.title || '')],
    [labelFor('name'), String(node.name || node.canonical_name || '')],
    [labelFor('state'), String(node.state || '')],
    [labelFor('platform'), String(node.platform || '')],
    [labelFor('game'), String(node.game || '')],
    [labelFor('policyType'), String(node.policy_type || '')],
    [labelFor('status'), String(node.status || '')],
    [labelFor('date'), String(node.publish_date || node.effective_date || node.date || '')],
  ]
  return list.filter(([, value]) => value && value !== '-')
}

function normalizeValue(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function parseNodeTags(node: GraphNodeItem) {
  const tagKeys = ['key_points', 'keywords', 'topics', 'states', 'platforms']
  const tags: string[] = []
  tagKeys.forEach((key) => {
    const raw = node[key]
    if (Array.isArray(raw)) {
      raw.forEach((item) => {
        const text = normalizeValue(item).trim()
        if (text) tags.push(text)
      })
    }
  })
  return Array.from(new Set(tags)).slice(0, 20)
}

function extraPrimitiveFields(node: GraphNodeItem) {
  const ignored = new Set([
    'id', 'type', 'title', 'name', 'text', 'canonical_name', 'state', 'platform', 'game', 'policy_type', 'status',
    'publish_date', 'effective_date', 'date', 'key_points', 'keywords', 'topics', 'states', 'platforms',
  ])
  return Object.entries(node)
    .filter(([key, value]) => !ignored.has(key) && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'))
    .slice(0, 12)
}

type NodeGraphContext = {
  degree: number
  neighborTypeCount: number
  marketDocCount: number
  neighborTypeItems: Array<{ type: string; count: number }>
  predicateItems: Array<{ predicate: string; count: number }>
  neighborNodesByType: Record<string, Array<{ id: string; name: string; type: string }>>
  relationsByPredicate: Record<string, Array<{
    id: string
    direction: 'IN' | 'OUT'
    relation: string
    targetName: string
    targetType: string
  }>>
  relationItems: Array<{
    id: string
    direction: 'IN' | 'OUT'
    relation: string
    targetName: string
    targetType: string
  }>
}

type NodeElementItem = {
  id: string
  label: string
  value: string
  tone: 'meta' | 'time' | 'metric' | 'tag' | 'text'
}

function elementTone(key: string, value: unknown): NodeElementItem['tone'] {
  const keyLower = key.toLowerCase()
  const valueText = String(value || '')
  if (keyLower.includes('date') || keyLower.includes('time')) return 'time'
  if (keyLower.includes('count') || keyLower.includes('score') || keyLower.includes('rate')) return 'metric'
  if (Array.isArray(value)) return 'tag'
  if (typeof value === 'number') return 'metric'
  if (valueText.length > 50 || keyLower.includes('text') || keyLower.includes('summary')) return 'text'
  return 'meta'
}

function buildNodeElements(node: GraphNodeItem | null): NodeElementItem[] {
  if (!node) return []
  const items: NodeElementItem[] = []
  Object.entries(node).forEach(([key, value]) => {
    if (value == null) return
    if (Array.isArray(value)) {
      value.forEach((entry, index) => {
        const text = normalizeValue(entry).trim()
        if (!text) return
        items.push({
          id: `${key}-${index}-${text}`,
          label: key,
          value: text,
          tone: 'tag',
        })
      })
      return
    }
    if (typeof value === 'object') {
      const text = JSON.stringify(value).slice(0, 120)
      if (!text) return
      items.push({
        id: `${key}-obj`,
        label: key,
        value: text,
        tone: 'text',
      })
      return
    }
    const text = normalizeValue(value).trim()
    if (!text) return
    items.push({
      id: `${key}-${text}`,
      label: key,
      value: text,
      tone: elementTone(key, value),
    })
  })
  return items
}

function parseCommaSeparated(value: string) {
  return String(value || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
}

function buildDefaultCuratedGraphId(projectKey: string, graphKind: GraphKind) {
  const raw = `graphpage-${projectKey || 'default'}-${graphKind || 'market'}`
  return raw.replace(/[^a-zA-Z0-9_.:-]+/g, '-').replace(/^-+|-+$/g, '') || 'graphpage-market'
}

function mergeGraphPayloads(payloads: Array<{ nodes?: GraphNodeItem[]; edges?: GraphEdgeItem[] }>) {
  const nodeMap = new Map<string, GraphNodeItem>()
  const edgeMap = new Map<string, GraphEdgeItem>()
  payloads.forEach((payload) => {
    ;(payload.nodes || []).forEach((node) => {
      const key = `${String(node.type || '').trim()}:${String(node.id || '').trim()}`
      if (!key || key === ':') return
      if (!nodeMap.has(key)) nodeMap.set(key, node)
    })
    ;(payload.edges || []).forEach((edge) => {
      const fk = `${String(edge.from?.type || '').trim()}:${String(edge.from?.id || '').trim()}`
      const tk = `${String(edge.to?.type || '').trim()}:${String(edge.to?.id || '').trim()}`
      if (!fk || !tk || fk === ':' || tk === ':') return
      const rel = String(edge.type || edge.predicate || '').trim()
      const ek = `${fk}>${tk}|${rel}`
      if (!edgeMap.has(ek)) edgeMap.set(ek, edge)
    })
  })
  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
  }
}

function rankVisibleNodeKeysByPriority(params: {
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
  edgeResolvedKeyMap: Map<GraphEdgeItem, { fromKey: string; toKey: string }>
  centralityScoreMap: Map<string, number>
  neighborTightnessScoreMap: Map<string, number>
  centralWeight: number
  neighborWeight: number
}) {
  const {
    nodes,
    edges,
    edgeResolvedKeyMap,
    centralityScoreMap,
    neighborTightnessScoreMap,
    centralWeight,
    neighborWeight,
  } = params
  const keys = nodes.map((node) => nodeKey(node))
  const keySet = new Set(keys)
  const adjacency = new Map<string, Set<string>>()
  keys.forEach((key) => adjacency.set(key, new Set<string>()))
  edges.forEach((edge) => {
    const resolved = edgeResolvedKeyMap.get(edge)
    if (!resolved) return
    if (!keySet.has(resolved.fromKey) || !keySet.has(resolved.toKey)) return
    adjacency.get(resolved.fromKey)?.add(resolved.toKey)
    adjacency.get(resolved.toKey)?.add(resolved.fromKey)
  })

  const componentSizeByKey = new Map<string, number>()
  const visited = new Set<string>()
  keys.forEach((seed) => {
    if (visited.has(seed)) return
    const queue = [seed]
    const comp: string[] = []
    while (queue.length) {
      const current = queue.shift()
      if (!current || visited.has(current)) continue
      visited.add(current)
      comp.push(current)
      ;(adjacency.get(current) || new Set<string>()).forEach((next) => {
        if (!visited.has(next)) queue.push(next)
      })
    }
    const size = comp.length
    comp.forEach((key) => componentSizeByKey.set(key, size))
  })

  const cw = Math.max(0.001, centralWeight)
  const nw = Math.max(0.001, neighborWeight)
  return keys
    .slice()
    .sort((a, b) => {
      const compA = componentSizeByKey.get(a) || 1
      const compB = componentSizeByKey.get(b) || 1
      if (compA !== compB) return compB - compA
      const scoreA = (centralityScoreMap.get(a) || 0) * cw + (neighborTightnessScoreMap.get(a) || 0) * nw
      const scoreB = (centralityScoreMap.get(b) || 0) * cw + (neighborTightnessScoreMap.get(b) || 0) * nw
      if (scoreA !== scoreB) return scoreB - scoreA
      return a.localeCompare(b, 'zh-CN')
    })
}

function rankDocumentNodeKeysById(params: {
  nodes: GraphNodeItem[]
  candidateKeys?: Set<string>
}) {
  const { nodes, candidateKeys } = params
  const rows = nodes
    .map((node) => ({
      key: nodeKey(node),
      id: String(node.id || '').trim(),
    }))
    .filter((item) => !candidateKeys || candidateKeys.has(item.key))

  const numericLike = (value: string) => /^-?\d+(\.\d+)?$/.test(value)
  const asNumber = (value: string) => Number(value)

  return rows
    .slice()
    .sort((a, b) => {
      const aNum = numericLike(a.id) ? asNumber(a.id) : NaN
      const bNum = numericLike(b.id) ? asNumber(b.id) : NaN
      const aHasNum = Number.isFinite(aNum)
      const bHasNum = Number.isFinite(bNum)
      if (aHasNum && bHasNum && aNum !== bNum) return bNum - aNum
      if (a.id !== b.id) return b.id.localeCompare(a.id, 'zh-CN')
      return a.key.localeCompare(b.key, 'zh-CN')
    })
    .map((item) => item.key)
}

const SPECIAL_PREFIX_BY_KIND: Partial<Record<GraphKind, string>> = Object.fromEntries(
  Object.values(GRAPH_PROJECTIONS_BY_KIND)
    .filter((definition) => Boolean(definition.specialNodePrefix))
    .map((definition) => [definition.graphKind, definition.specialNodePrefix]),
)

export default function GraphPage({ projectKey, variant, templateBuilder = false }: Props) {
  const locale = useAppLocale()
  const t = useCallback((key: MessageKey) => translate(locale, key), [locale])
  const tf = useCallback((key: MessageKey, params: GraphMessageParams) => formatGraphMessage(t(key), params), [t])
  const activeProjectionId = variant
  const graphProjection = getGraphProjection(activeProjectionId)
  const graphConfig = useQuery({
    queryKey: queryKeys.graph.config(projectKey),
    queryFn: getGraphConfig,
    enabled: Boolean(projectKey),
  })
  // Projects may bind the projection tabs: which entry points are visible, in
  // what order, their labels, and how each narrows the unified topology.
  const declaredProjections = useMemo(
    () => coerceGraphProjectionBindings(graphConfig.data?.graph_projections),
    [graphConfig.data?.graph_projections],
  )
  const workspaceTabs = useMemo(
    () => applyWorkspaceTabBindings(GRAPH_WORKSPACE_TABS, declaredProjections),
    [declaredProjections],
  )
  const activeWorkspaceTab = useMemo(
    () => workspaceTabs.find((tab) => (
      templateBuilder ? tab.isBuilder : tab.projectionId === activeProjectionId
    )) || workspaceTabs[0],
    [workspaceTabs, activeProjectionId, templateBuilder],
  )
  // Bindings are addressed by graph entry point (module key), which is the same
  // identity the tab strip navigates by.
  const activeBinding = useMemo(
    () => declaredProjections.find((binding) => binding.id === activeWorkspaceTab.moduleKey),
    [declaredProjections, activeWorkspaceTab.moduleKey],
  )
  const activeTopologyFilter = activeBinding?.topologyFilter
  const selectWorkspaceTab = useCallback((moduleKey: GraphWorkspaceTab['moduleKey']) => {
    const target = workspaceTabs.find((tab) => tab.moduleKey === moduleKey)
    if (!target || target.moduleKey === activeWorkspaceTab.moduleKey) return
    window.location.assign(`#${target.routePath}`)
  }, [workspaceTabs, activeWorkspaceTab.moduleKey])
  const graphKind = graphProjection.graphKind
  const sourceProjection = GRAPH_PROJECTIONS_BY_KIND[graphProjection.dataSourceKind]
  const graphVariantLabel = activeBinding?.label || t(graphProjection.labelKey)
  const graphGroupLabel = useCallback((group: string) => {
    const key = GRAPH_LEGEND_GROUP_LABEL_KEY[group as GraphLegendGroupId]
    return key ? t(key) : group
  }, [t])
  const edgeTierLabel = useCallback((tier: EdgeLegendTier) => t(GRAPH_EDGE_TIER_LABEL_KEY[tier]), [t])
  const edgeStrokeLabel = useCallback((strokeKind: EdgeStrokeKind) => t(GRAPH_EDGE_STROKE_LABEL_KEY[strokeKind]), [t])
  const edgeLineTypeLabel = useCallback((lineType: EdgeLineType) => t(GRAPH_EDGE_LINE_TYPE_LABEL_KEY[lineType]), [t])
  const relationClassLabel = useCallback((token: string) => {
    const key = GRAPH_RELATION_CLASS_LABEL_KEY[token]
    return key ? t(key) : token
  }, [t])
  const cardFieldLabel = useCallback((field: keyof typeof GRAPH_CARD_FIELD_LABEL_KEY) => t(GRAPH_CARD_FIELD_LABEL_KEY[field]), [t])
  const defaultCuratedHandoffTopic = graphVariantLabel
  const defaultCuratedGraphId = useMemo(() => buildDefaultCuratedGraphId(projectKey, graphKind), [projectKey, graphKind])
  const previousCuratedGraphIdDefaultRef = useRef(defaultCuratedGraphId)
  const previousCuratedHandoffTopicDefaultRef = useRef(defaultCuratedHandoffTopic)
  const previousGraphKindRef = useRef(graphKind)
  const previousTemplateBuilderRef = useRef(templateBuilder)
  const previousProjectionResetKeyRef = useRef<string | null>(null)
  const chartRef = useRef<HTMLDivElement | null>(null)
  const forceChartRef = useRef<HTMLDivElement | null>(null)
  const fullscreenWrapRef = useRef<HTMLDivElement | null>(null)
  const controlPanelRef = useRef<HTMLDivElement | null>(null)
  const projectionPanelRef = useRef<HTMLDivElement | null>(null)
  const legendPanelRef = useRef<HTMLDivElement | null>(null)
  const controlResizeRightRef = useRef<number | null>(null)
  const controlResizeBottomRef = useRef<number | null>(null)
  const projectionResizeRightRef = useRef<number | null>(null)
  const projectionResizeBottomRef = useRef<number | null>(null)
  const legendResizeRightRef = useRef<number | null>(null)
  const legendResizeBottomRef = useRef<number | null>(null)
  const chartInstRef = useRef<EChartsType | null>(null)
  const echartsLibRef = useRef<typeof import('echarts/core') | null>(null)
  const nodeLookupRef = useRef<Record<string, GraphNodeItem>>({})
  const nodePositionRef = useRef<Record<string, { x?: number; y?: number }>>({})

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [filterApplyError, setFilterApplyError] = useState('')
  const [state, setState] = useState('')
  const [policyType, setPolicyType] = useState('')
  const [platform, setPlatform] = useState('')
  const [topic, setTopic] = useState('')
  const [game, setGame] = useState('')
  const [limit, setLimit] = useState(templateBuilder ? 50 : GRAPH_LIMIT_DEFAULT)
  const { visualDraft, visualApplied, updateVisual, startVisualInteraction, endVisualInteraction } = useGraphVisualState()
  const [hiddenTypes, setHiddenTypes] = useState<Record<string, boolean>>({})
  const [appliedFilters, setAppliedFilters] = useState<FilterState>({
    startDate: '',
    endDate: '',
    state: '',
    policyType: '',
    platform: '',
    topic: '',
    game: '',
    limit: templateBuilder ? 50 : GRAPH_LIMIT_DEFAULT,
  })
  const [selectedNode, setSelectedNode] = useState<GraphNodeItem | null>(null)
  const selectedDocumentId = typeof selectedNode?.document_id === 'number' ? selectedNode.document_id : null
  const selectedDocument = useQuery({
    queryKey: queryKeys.admin.documentDetail(projectKey, selectedDocumentId),
    queryFn: () => getAdminDocument(Number(selectedDocumentId)),
    enabled: Boolean(projectKey && selectedDocumentId),
  })
  const [nodeCardAnchor, setNodeCardAnchor] = useState<NodeCardAnchor | null>(null)
  const [chartReadyRaw, setChartReady] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isCompactViewport, setIsCompactViewport] = useState(false)
  const [showOverlay, setShowOverlay] = useState(true)
  const [showSymbolDebug, setShowSymbolDebug] = useState(true)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [expandedEdgeGroup, setExpandedEdgeGroup] = useState<EdgeLegendTier | null>(null)
  const [paletteKey, setPaletteKey] = useState<PaletteKey>('bcp_unified')
  const [colorRotate, setColorRotate] = useState(58)
  const [absoluteContrast, setAbsoluteContrast] = useState(62)
  const {
    renderMode,
    projectionEngine,
    renderModeRef,
    requestRenderModeChange,
    requestProjectionEngineChange,
  } = useGraphModeSwitch()
  const [projectionRotateX] = useState(12)
  const [projectionRotateY] = useState(18)
  const [projectionRotateZ] = useState(0)
  const [physicsFrame, setPhysicsFrame] = useState(0)
  const [projectionFrameEpoch, setProjectionFrameEpoch] = useState(0)
  const [controlPanelWidth, setControlPanelWidth] = useState(430)
  const [controlPanelHeight, setControlPanelHeight] = useState(620)
  const [projectionPanelWidth, setProjectionPanelWidth] = useState(430)
  const [projectionPanelHeight, setProjectionPanelHeight] = useState(360)
  const [legendPanelWidth, setLegendPanelWidth] = useState(360)
  const [legendPanelHeight, setLegendPanelHeight] = useState(620)
  const [controlSectionOpen, setControlSectionOpen] = useState<Record<'view' | 'projection' | 'color' | 'filter' | 'edit', boolean>>({
    view: true,
    projection: true,
    color: true,
    filter: true,
    edit: true,
  })
  const [editMode, setEditMode] = useState(templateBuilder)
  const [graphEditStatus, setGraphEditStatus] = useState('')
  const [curatedGraphId, setCuratedGraphId] = useState(defaultCuratedGraphId)
  const [curatedBusy, setCuratedBusy] = useState(false)
  const [curatedRevision, setCuratedRevision] = useState<number | null>(null)
  const [curatedStatus, setCuratedStatus] = useState('')
  const [curatedHandoffTopic, setCuratedHandoffTopic] = useState(defaultCuratedHandoffTopic)
  const [curatedRollbackVersionId, setCuratedRollbackVersionId] = useState('')
  const [curatedRollbackReason, setCuratedRollbackReason] = useState('')
  const [curatedAuditItems, setCuratedAuditItems] = useState<WorkflowGraphAuditRecord[]>([])
  const [curatedHandoffReplay, setCuratedHandoffReplay] = useState({ runId: '', handoffId: '' })
  const [newNodeType, setNewNodeType] = useState('Entity')
  const [newNodeName, setNewNodeName] = useState('')
  const [edgeDraft, setEdgeDraft] = useState({ sourceKey: '', targetKey: '', relation: '' })
  const [nodeEditDraft, setNodeEditDraft] = useState({
    key: '',
    id: '',
    type: '',
    name: '',
    title: '',
    x: '',
    y: '',
    z: '',
  })
  const [hiddenEdgeKinds, setHiddenEdgeKinds] = useState<Record<string, boolean>>({})
  const [relationGroupOpen, setRelationGroupOpen] = useState<Record<string, boolean>>({})
  const [expandedNeighborType, setExpandedNeighborType] = useState<string | null>(null)
  const [expandedPredicate, setExpandedPredicate] = useState<string | null>(null)
  const [expandedElementLabel, setExpandedElementLabel] = useState<string | null>(null)
  const [nodeDragCapturedFx, setNodeDragCapturedFx] = useState(false)
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [submittingMap, setSubmittingMap] = useState<Record<'collect' | 'source_collect', boolean>>({
    collect: false,
    source_collect: false,
  })
  const [structuredResultMap, setStructuredResultMap] = useState<Record<'collect' | 'source_collect', GraphStructuredSearchResponse | null>>({
    collect: null,
    source_collect: null,
  })
  const [clueChainOpen, setClueChainOpen] = useState(false)
  const [clueChainBusy, setClueChainBusy] = useState(false)
  const [clueChainStatus, setClueChainStatus] = useState('')
  const [activeClueChain, setActiveClueChain] = useState<ClueChainDetail | null>(null)
  const [selectedClueEvidenceId, setSelectedClueEvidenceId] = useState<string | null>(null)
  const [dashboard, setDashboard] = useState({
    language: 'en',
    provider: 'auto',
    maxItems: 100,
    startOffset: '',
    daysBack: '7',
    enableExtraction: true,
    asyncMode: true,
    platforms: 'reddit',
    enableSubredditDiscovery: false,
    baseSubreddits: '',
    llmAssist: true,
    sourceItemKeys: [] as string[],
  })
  const [sourceItemKeyword, setSourceItemKeyword] = useState('')
  const [forceGraphFallbackNotice, setForceGraphFallbackNotice] = useState<string | null>(null)
  const [rankingWeightCentral, setRankingWeightCentral] = useState(RANK_WEIGHT_DEFAULT)
  const [rankingWeightNeighbor, setRankingWeightNeighbor] = useState(RANK_WEIGHT_DEFAULT)
  const [appliedRankingWeights, setAppliedRankingWeights] = useState(() => ({
    central: RANK_WEIGHT_DEFAULT,
    neighbor: RANK_WEIGHT_DEFAULT,
  }))
  const [rankingStrategy, setRankingStrategy] = useState<NodeRankStrategy>('doc_body')
  const [appliedRankingStrategy, setAppliedRankingStrategy] = useState<NodeRankStrategy>('doc_body')
  const adjacencyConnectedMapRef = useRef<Map<string, Set<string>>>(new Map())
  const dragFocusNodeKeyRef = useRef<string | null>(null)
  const nodeCardDragRef = useRef<{ active: boolean; offsetX: number; offsetY: number }>({ active: false, offsetX: 0, offsetY: 0 })
  const nodeCardHoldTimerRef = useRef<number | null>(null)
  const nodeCardHoldActiveRef = useRef(false)
  const nodeCardHoldTriggeredRef = useRef(false)
  const suppressNextClickToggleRef = useRef(false)
  const rightToggleDedupeRef = useRef<{ key: string; ts: number }>({ key: '', ts: 0 })
  const nodeDragFxTimerRef = useRef<number | null>(null)
  const nodeDragHoldTimerRef = useRef<number | null>(null)
  const nodeDragUnlockedRef = useRef(false)
  const lastForceNodeClickAtRef = useRef(0)
  const selectedNodeOpenRef = useRef(false)
  const projectionPhysicsRef = useRef<Projection3DPhysicsState>({ positions: {}, velocities: {} })
  const forceGraphRef = useRef<ForceGraphApi | null>(null)
  const forceNodeObjectCacheRef = useRef<Map<string, THREE.Object3D>>(new Map())
  const forceNodePhysicsRef = useRef<Map<string, ForceNodePhysics>>(new Map())
  const [forceNodeSeedPhysics, setForceNodeSeedPhysics] = useState<Map<string, ForceNodePhysics>>(() => new Map())
  const forceGlobalGravityStrengthRef = useRef(0)
  const forceGlobalGravityForceRef = useRef<(((alpha: number) => void) & { initialize?: (nodes: Array<Record<string, unknown>>) => void }) | null>(null)
  const force3DVisibilityStatsGetterRef = useRef<() => Graph3DVisibilityStats>(() => ({
    dataNodes: 0,
    sceneNodeObjects: 0,
    emptyDataNodes: 0,
    emptySceneNodeObjects: 0,
  }))
  const forceHoverRafRef = useRef<number | null>(null)
  const forceHoverPendingKeyRef = useRef<string | null>(null)
  const forceGraphFallbackAppliedRef = useRef(false)
  const projectionInteractionQuatRef = useRef<QuaternionLike>({ x: 0, y: 0, z: 0, w: 1 })
  const projectionAngularVelRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const projectionDragStateRef = useRef<{ active: boolean; x: number; y: number }>({ active: false, x: 0, y: 0 })
  const fullscreenWantedRef = useRef(false)
  const visualSliderInteractionHandlers = useMemo(
    () => ({
      onPointerDown: () => startVisualInteraction(),
      onPointerUp: () => endVisualInteraction(),
      onPointerCancel: () => endVisualInteraction(),
      onBlur: () => endVisualInteraction(),
    }),
    [startVisualInteraction, endVisualInteraction],
  )


  useEffect(() => {
    selectedNodeOpenRef.current = Boolean(selectedNode)
  }, [selectedNode])


  useEffect(() => {
    return () => {
      if (nodeCardHoldTimerRef.current != null) window.clearTimeout(nodeCardHoldTimerRef.current)
      if (nodeDragFxTimerRef.current != null) window.clearTimeout(nodeDragFxTimerRef.current)
      if (nodeDragHoldTimerRef.current != null) window.clearTimeout(nodeDragHoldTimerRef.current)
      if (forceHoverRafRef.current != null) window.cancelAnimationFrame(forceHoverRafRef.current)
    }
  }, [setCuratedRevision, setCuratedStatus])

  const effectiveLimit = clampGraphLimit(appliedFilters.limit)

  const effectiveQueryLimit = templateBuilder ? GRAPH_LIMIT_MAX : effectiveLimit
  const graphDataQueryKind = templateBuilder ? `${graphKind}:template_builder` : graphProjection.dataSourceKind
  // The data cache follows the actual read scope, not the presenting tab. Tabs
  // without a filter share the total graph; equivalent topology filters share
  // one narrowed read. Token order is not part of contains-any semantics.
  const graphDataViewKey = activeTopologyFilter
    ? ['topology-filter', activeTopologyFilter.attribute, [...activeTopologyFilter.containsAny].sort()]
    : ['total-graph']
  const graphData = useQuery<GraphResponse>({
    queryKey: [
      ...queryKeys.graph.data(
        projectKey,
        graphDataQueryKind,
        appliedFilters.startDate,
        appliedFilters.endDate,
        appliedFilters.state,
        appliedFilters.policyType,
        appliedFilters.platform,
        appliedFilters.topic,
        appliedFilters.game,
        effectiveLimit,
      ),
      graphDataViewKey,
    ],
    queryFn: async () => {
      if (templateBuilder) {
        const [policy, social, marketDeep] = await Promise.all([
          getPolicyGraph({
            start_date: appliedFilters.startDate,
            end_date: appliedFilters.endDate,
            state: appliedFilters.state,
            policy_type: appliedFilters.policyType,
            limit: effectiveQueryLimit,
          }),
          getSocialGraph({
            start_date: appliedFilters.startDate,
            end_date: appliedFilters.endDate,
            platform: appliedFilters.platform,
            topic: appliedFilters.topic,
            limit: effectiveQueryLimit,
          }),
          getMarketGraph({
            start_date: appliedFilters.startDate,
            end_date: appliedFilters.endDate,
            state: appliedFilters.state,
            game: appliedFilters.game,
            view: 'market_deep_entities',
            limit: effectiveQueryLimit,
          }),
        ])
        return mergeGraphPayloads([policy, social, marketDeep])
      }
      return readGraphProjection(sourceProjection, {
        startDate: appliedFilters.startDate,
        endDate: appliedFilters.endDate,
        state: appliedFilters.state,
        policyType: appliedFilters.policyType,
        platform: appliedFilters.platform,
        topic: appliedFilters.topic,
        game: appliedFilters.game,
        limit: effectiveQueryLimit,
      }, activeTopologyFilter)
    },
    enabled: Boolean(projectKey),
  })
  const realizedGraphLabel = graphData.data?.source_label || graphVariantLabel
  const topologyEdgeStyleBinding = useMemo(
    () => coerceGraphEdgeStyleBinding(graphData.data?.edge_style_bindings),
    [graphData.data?.edge_style_bindings],
  )
  const configuredEdgeStyleBinding = useMemo(
    () => coerceGraphEdgeStyleBinding(graphConfig.data?.graph_edge_style_bindings),
    [graphConfig.data?.graph_edge_style_bindings],
  )
  // Projects declare their relation vocabulary in authored order; that order
  // seeds distinct default styles per relation, and explicit bindings win.
  const derivedEdgeStyleBinding = useMemo(
    () => defaultRelationTokenBinding(graphData.data?.relation_vocabulary),
    [graphData.data?.relation_vocabulary],
  )
  const edgeStyleBinding = useMemo(
    () => mergeEdgeStyleBindings(derivedEdgeStyleBinding, topologyEdgeStyleBinding, configuredEdgeStyleBinding),
    [derivedEdgeStyleBinding, topologyEdgeStyleBinding, configuredEdgeStyleBinding],
  )

  const sourceItemsQuery = useQuery({
    queryKey: queryKeys.sourceLibrary.itemsForGraph(projectKey),
    queryFn: listSourceItems,
    enabled: Boolean(projectKey) && taskModalOpen,
  })

  const sourceGraphNodes = useMemo(() => graphData.data?.nodes || [], [graphData.data?.nodes])
  const sourceGraphEdges = useMemo(() => graphData.data?.edges || [], [graphData.data?.edges])
  const {
    draftNodes,
    draftEdges,
    nodeByKey: draftNodeMap,
    dirty: isDraftDirty,
    resetDraft,
    markSaved: markDraftSaved,
    replaceDraft,
    createNode: createDraftNode,
    updateNodeByKey: updateDraftNodeByKey,
    removeNodesByKeys: removeDraftNodesByKeys,
    createEdgeByNodeKeys: createDraftEdgeByNodeKeys,
    removeEdgeAt: removeDraftEdgeAt,
  } = useGraphDraft({
    sourceNodes: sourceGraphNodes,
    sourceEdges: sourceGraphEdges,
    getNodeKey: nodeKey,
  })
  const {
    templateItems,
    versionItems,
    templateStageItems,
    templateStageAuditSummary,
    templateRollbackDraft,
    setTemplateRollbackDraft,
    templateRollbackPreview,
    templateRollbackError,
    templateNameDraft,
    setTemplateNameDraft,
    renameTemplateDraft,
    setRenameTemplateDraft,
    versionNameDraft,
    setVersionNameDraft,
    activeTemplateKey,
    activeVersionKey,
    setActiveVersionKey,
    templateBusy,
    templateStageBusy,
    templateRollbackBusy,
    templateDiffBusy,
    templateDiffPreview,
    templateDryRunBusy,
    templateDryRunResult,
    templateDryRunSummary,
    templateDryRunSteps,
    templateRollbackPlan,
    templateRollbackAudit,
    templateRollbackHistoryCount,
    hasDraftTemplateStage,
    hasStagingTemplateStage,
    loadTemplateList,
    selectTemplate,
    handleLoadTemplateVersions,
    handlePreviewWorkflowTemplateDiff,
    handleWorkflowTemplateDryRun,
    handleRefreshWorkflowTemplateStages,
    handleSaveWorkflowTemplateDraftStage,
    handlePromoteWorkflowTemplateStage,
    handlePreviewWorkflowTemplateRollback,
    handleApplyWorkflowTemplateRollback,
    handleCreateTemplate,
    handleRenameTemplate,
    handleDeleteTemplate,
    handleSaveVersion,
    handleLoadVersion,
    handleActivateVersion,
  } = useWorkflowTemplateController({
    enabled: editMode,
    projectKey,
    graphKind,
    draftNodes,
    draftEdges,
    markDraftSaved,
    replaceDraft,
    setGraphEditStatus,
    translate: t,
    formatMessage: tf,
  })
  const effectiveGraphData = useMemo(
    () => ({
      nodes: editMode ? draftNodes : sourceGraphNodes,
      edges: editMode ? draftEdges : sourceGraphEdges,
    }),
    [editMode, draftNodes, draftEdges, sourceGraphNodes, sourceGraphEdges],
  )

  const colorDistribution = useMemo(() => {
    const rotateT = Math.max(0, Math.min(1, colorRotate / 100))
    const contrastT = Math.max(0, Math.min(1, absoluteContrast / 100))
    return {
      // 在同色系内：旋转控制色相起点，绝对色差控制间距并同步扩张分配域。
      rotation: rotateT,
      spread: 0.5 + rotateT * 1.4,
      // 绝对色差越大，同步扩张配色域，避免图例扎堆在同一小段颜色。
      contrast: contrastT,
      domainExpand: contrastT,
    }
  }, [colorRotate, absoluteContrast])

  const nodeTypes = useMemo(() => {
    const nodes = effectiveGraphData.nodes || []
    if (nodes.some((node) => 'topology_ref' in node)) {
      return Array.from(new Set(nodes.map((node) => normalizeNodeType(node.type)).filter(Boolean)))
        .sort((a, b) => a.localeCompare(b, 'zh-CN'))
    }
    const set = new Set<string>(DEFAULT_NODE_TYPES_BY_KIND[graphKind])
    const cfg = graphConfig.data?.graph_node_types || {}
    const cfgKey = graphProjection.configKey
    const fromCfg = Array.isArray(cfg[cfgKey]) ? cfg[cfgKey] : []
    fromCfg.forEach((t) => set.add(normalizeNodeType(t)))
    nodes.forEach((n) => set.add(normalizeNodeType(n.type)))
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [effectiveGraphData.nodes, graphConfig.data?.graph_node_types, graphKind, graphProjection])

  const nodeTypeColor = useMemo(() => {
    return assignLegendColors(nodeTypes, paletteKey, 'node', colorDistribution)
  }, [nodeTypes, paletteKey, colorDistribution])

  const stats = useMemo(() => {
    const nodes = effectiveGraphData.nodes || []
    const edges = effectiveGraphData.edges || []
    const typeCount = nodeTypes.length
    return { nodes: nodes.length, edges: edges.length, typeCount }
  }, [effectiveGraphData.nodes, effectiveGraphData.edges, nodeTypes.length])

  const legendGroups = useMemo(() => {
    const grouped: Record<string, string[]> = {}
    nodeTypes.forEach((type) => {
      const g = classifyGraphLegendType(type)
      if (!grouped[g]) grouped[g] = []
      grouped[g].push(type)
    })
    return (Object.entries(grouped) as Array<[GraphLegendGroupId, string[]]>)
      .sort(([a], [b]) => compareGraphLegendGroups(a, b))
  }, [nodeTypes])

  const defaultNodeTypesForCompute = useMemo(() => {
    const cfg = graphConfig.data?.graph_node_types || {}
    const cfgKey = graphProjection.configKey
    const configuredTypes = Array.isArray(cfg[cfgKey])
      ? cfg[cfgKey].map((item) => normalizeNodeType(item)).filter(Boolean)
      : []
    const allTypes = Array.from(new Set([
      ...DEFAULT_NODE_TYPES_BY_KIND[graphKind],
      ...configuredTypes,
      ...(effectiveGraphData.nodes.some((node) => 'topology_ref' in node)
        ? effectiveGraphData.nodes.map((node) => normalizeNodeType(node.type)).filter(Boolean)
        : []),
      ...(templateBuilder
        ? (effectiveGraphData.nodes || []).map((n) => normalizeNodeType(n.type)).filter(Boolean)
        : []),
    ]))
    return {
      ...DEFAULT_NODE_TYPES_BY_KIND,
      [graphKind]: allTypes,
    }
  }, [templateBuilder, effectiveGraphData.nodes, graphConfig.data?.graph_node_types, graphKind, graphProjection])

  const docNodeTypeSetForBuilder = useMemo(() => {
    if (!templateBuilder) return new Set<string>()
    const cfg = graphConfig.data?.graph_doc_types || {}
    const rawTypes = new Set<string>()
    Object.values(cfg).forEach((arr) => {
      if (!Array.isArray(arr)) return
      arr.forEach((item) => rawTypes.add(normalizeNodeType(item)))
    })
    ;['Post', 'Policy', 'MarketData'].forEach((item) => rawTypes.add(normalizeNodeType(item)))
    return rawTypes
  }, [templateBuilder, graphConfig.data?.graph_doc_types])

  const topology = useMemo(() => {
    const nodes = effectiveGraphData.nodes || []
    const edges = effectiveGraphData.edges || []
    const { connectedNodes, connectedEdges, connectedNodeKeys, visibleNodes, visibleEdges, visibleNodeKeys, edgeResolvedKeyMap } = computeVisibleSubgraph({
      nodes,
      edges,
      graphKind,
      hiddenTypes,
      defaultNodeTypesByKind: Object.fromEntries(Object.entries(defaultNodeTypesForCompute).map(([key, values]) => [key, [...values]])),
      specialPrefixByKind: SPECIAL_PREFIX_BY_KIND,
      normalizeNodeType,
    })

    const degreeMap = new Map<string, number>()
    const directedEdges: Array<{ fromKey: string; toKey: string; weight: number }> = []
    const connectedAdjacencyMap = new Map<string, Set<string>>()
    connectedNodes.forEach((node) => {
      connectedAdjacencyMap.set(nodeKey(node), new Set<string>())
    })
    connectedEdges.forEach((edge) => {
      const resolved = edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      const rawWeight = edge?.weight ?? (edge?.properties as { weight?: unknown } | undefined)?.weight
      const weight = Number.isFinite(Number(rawWeight)) && Number(rawWeight) > 0 ? Number(rawWeight) : 1
      directedEdges.push({ fromKey: resolved.fromKey, toKey: resolved.toKey, weight })
      if (resolved.fromKey === resolved.toKey) return
      connectedAdjacencyMap.get(resolved.fromKey)?.add(resolved.toKey)
      connectedAdjacencyMap.get(resolved.toKey)?.add(resolved.fromKey)
    })
    visibleEdges.forEach((edge) => {
      const resolved = edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      degreeMap.set(resolved.fromKey, (degreeMap.get(resolved.fromKey) || 0) + 1)
      degreeMap.set(resolved.toKey, (degreeMap.get(resolved.toKey) || 0) + 1)
    })
    visibleNodes.forEach((node) => {
      const key = nodeKey(node)
      if (!degreeMap.has(key)) degreeMap.set(key, 0)
    })
    // Difference score components:
    // 1) centrality: blend core-number and PageRank.
    // 2) neighbor-tightness: 1/2-hop neighborhood influence with degree decay.
    const connectedKeys = Array.from(connectedNodeKeys)
    const prForward = normalizeMapValues(computePageRank(connectedKeys, directedEdges))
    const coreNorm = normalizeMapValues(computeCoreNumber(connectedKeys, connectedAdjacencyMap))
    const connectedBaseCentralityMap = new Map<string, number>()
    connectedKeys.forEach((key) => {
      const baseCentrality = 0.7 * (coreNorm.get(key) || 0) + 0.3 * (prForward.get(key) || 0)
      connectedBaseCentralityMap.set(key, baseCentrality)
    })
    const connectedCentralityScoreMap = normalizeMapValues(connectedBaseCentralityMap)
    const connectedDegreeMap = new Map<string, number>()
    connectedKeys.forEach((key) => {
      connectedDegreeMap.set(key, connectedAdjacencyMap.get(key)?.size || 0)
    })
    const neighborhoodDecayAlpha = 0.5
    const degreeBoostGamma = 0.45
    const connectedNeighborTightnessRawMap = new Map<string, number>()
    connectedKeys.forEach((key) => {
      const neighbors1 = connectedAdjacencyMap.get(key) || new Set<string>()
      let hop1Score = 0
      neighbors1.forEach((u) => {
        const du = connectedDegreeMap.get(u) || 0
        hop1Score += (connectedCentralityScoreMap.get(u) || 0) / Math.pow(du + 1, neighborhoodDecayAlpha)
      })
      const localDegree = connectedDegreeMap.get(key) || 0
      const degreeBoost = Math.pow(localDegree + 1, degreeBoostGamma)
      const neighborhoodMass = hop1Score
      connectedNeighborTightnessRawMap.set(key, Math.log1p(neighborhoodMass) * degreeBoost)
    })
    const connectedNeighborTightnessScoreMap = normalizeMapValues(connectedNeighborTightnessRawMap)
    const centralityScoreMap = new Map<string, number>()
    const neighborTightnessScoreMap = new Map<string, number>()
    const scoreMap = new Map<string, number>()
    visibleNodes.forEach((node) => {
      const key = nodeKey(node)
      const centralityScore = connectedCentralityScoreMap.get(key) || 0
      const neighborTightnessScore = connectedNeighborTightnessScoreMap.get(key) || 0
      centralityScoreMap.set(key, centralityScore)
      neighborTightnessScoreMap.set(key, neighborTightnessScore)
      scoreMap.set(key, centralityScore + neighborTightnessScore)
    })
    // Align centrality and neighborhood to a shared robust scale
    // so both sliders operate on comparable magnitude.
    const componentScores = [
      ...Array.from(centralityScoreMap.values()),
      ...Array.from(neighborTightnessScoreMap.values()),
    ]
    const sharedQ10 = percentile(componentScores, 0.1)
    const sharedQ95 = percentile(componentScores, 0.95)
    const sharedMinScore = sharedQ10
    const sharedRangeScore = Math.max(sharedQ95 - sharedQ10, 1e-12)
    const centralityMinScore = sharedMinScore
    const centralityRangeScore = sharedRangeScore
    const neighborMinScore = sharedMinScore
    const neighborRangeScore = sharedRangeScore
    let limitedVisibleNodes = visibleNodes
    let limitedVisibleEdges = visibleEdges
    let limitedVisibleNodeKeys = visibleNodeKeys
    const topN = clampGraphLimit(appliedFilters.limit)
    if (topN > 0 && visibleNodes.length > topN) {
      const visibleNodeByKey = new Map(visibleNodes.map((node) => [nodeKey(node), node]))
      const ordered = rankVisibleNodeKeysByPriority({
        nodes: visibleNodes,
        edges: visibleEdges,
        edgeResolvedKeyMap,
        centralityScoreMap,
        neighborTightnessScoreMap,
        centralWeight: appliedRankingWeights.central / 100,
        neighborWeight: appliedRankingWeights.neighbor / 100,
      })
      const orderedDocKeys = ordered.filter((key) => {
        const node = visibleNodeByKey.get(key)
        if (!node) return false
        return docNodeTypeSetForBuilder.has(normalizeNodeType(node.type))
      })
      const orderedDocKeysById = rankDocumentNodeKeysById({
        nodes: visibleNodes,
        candidateKeys: new Set(orderedDocKeys),
      })
      const rankedPool = (() => {
        if (appliedRankingStrategy === 'doc_body') {
          return orderedDocKeys.length ? orderedDocKeys : ordered
        }
        if (appliedRankingStrategy === 'doc_id') {
          return orderedDocKeysById.length ? orderedDocKeysById : ordered
        }
        return ordered
      })()
      const primaryKeys = rankedPool.slice(0, topN)
      const keep = new Set(primaryKeys)
      const adjacency = new Map<string, Set<string>>()
      visibleEdges.forEach((edge) => {
        const resolved = edgeResolvedKeyMap.get(edge)
        if (!resolved) return
        if (!adjacency.has(resolved.fromKey)) adjacency.set(resolved.fromKey, new Set<string>())
        if (!adjacency.has(resolved.toKey)) adjacency.set(resolved.toKey, new Set<string>())
        adjacency.get(resolved.fromKey)?.add(resolved.toKey)
        adjacency.get(resolved.toKey)?.add(resolved.fromKey)
      })
      primaryKeys.forEach((seed) => {
        ;(adjacency.get(seed) || new Set<string>()).forEach((neighbor) => keep.add(neighbor))
      })
      limitedVisibleNodes = visibleNodes.filter((node) => keep.has(nodeKey(node)))
      limitedVisibleNodeKeys = new Set(limitedVisibleNodes.map((node) => nodeKey(node)))
      limitedVisibleEdges = visibleEdges.filter((edge) => {
        const resolved = edgeResolvedKeyMap.get(edge)
        if (!resolved) return false
        return limitedVisibleNodeKeys.has(resolved.fromKey) && limitedVisibleNodeKeys.has(resolved.toKey)
      })
    }
    return {
      nodes,
      connectedNodes,
      connectedEdges,
      connectedNodeKeys,
      visibleNodes: limitedVisibleNodes,
      visibleEdges: limitedVisibleEdges,
      degreeMap,
      centralityScoreMap,
      neighborTightnessScoreMap,
      scoreMap,
      centralityMinScore,
      centralityRangeScore,
      neighborMinScore,
      neighborRangeScore,
      visibleNodeKeys: limitedVisibleNodeKeys,
      edgeResolvedKeyMap,
      rawNodeCount: limitedVisibleNodes.length,
      rawEdgeCount: limitedVisibleEdges.length,
    }
  }, [
    effectiveGraphData,
    hiddenTypes,
    graphKind,
    defaultNodeTypesForCompute,
    appliedFilters.limit,
    appliedRankingWeights,
    appliedRankingStrategy,
    docNodeTypeSetForBuilder,
  ])

  // Derived-state repair happens during render, before topology consumers read
  // a stale mask or selected node.  The setters make the next render idempotent.
  if (topology.connectedNodes.length > 0 && topology.visibleNodes.length === 0) {
    if (Object.values(hiddenTypes).some(Boolean)) setHiddenTypes({})
  }
  if (selectedNode && !topology.connectedNodeKeys.has(nodeKey(selectedNode))) {
    setSelectedNode(null)
  }

  const symbolDebug = useMemo(() => {
    if (!showSymbolDebug) {
      return { total: 0, unique: 0, forcedCircle: 0, items: [] as Array<{ raw: string; normalized: string; rawSymbol: string; graphSymbol: BuiltinGraphSymbol; count: number }> }
    }
    const rows = new Map<string, { raw: string; normalized: string; rawSymbol: string; graphSymbol: BuiltinGraphSymbol; count: number }>()
    topology.visibleNodes.forEach((node) => {
      const raw = String(node.type || '').trim() || '-'
      const normalized = normalizeNodeType(node.type)
      const rawSymbol = resolveNodeSymbol(normalized)
      const graphSymbol = toGraphSymbol(rawSymbol)
      const key = `${raw}__${normalized}__${rawSymbol}__${graphSymbol}`
      const prev = rows.get(key)
      if (prev) {
        prev.count += 1
      } else {
        rows.set(key, { raw, normalized, rawSymbol, graphSymbol, count: 1 })
      }
    })
    const items = Array.from(rows.values()).sort((a, b) => b.count - a.count || a.raw.localeCompare(b.raw, 'zh-CN'))
    const forcedCircle = items.filter((item) => item.graphSymbol === 'circle' && item.rawSymbol !== 'circle').reduce((acc, item) => acc + item.count, 0)
    return {
      total: topology.visibleNodes.length,
      unique: items.length,
      forcedCircle,
      items: items.slice(0, 14),
    }
  }, [topology.visibleNodes, showSymbolDebug])

  const edgeLegendItems = useMemo(() => {
    const labels = graphConfig.data?.graph_relation_labels
    const counters = new Map<string, { sample: GraphEdgeItem; count: number }>()
    topology.connectedEdges.forEach((edge) => {
      const key = edgeLegendKey(edge)
      const prev = counters.get(key)
      if (prev) {
        prev.count += 1
        return
      }
      counters.set(key, { sample: edge, count: 1 })
    })
    const sortedKeys = Array.from(counters.keys()).sort((a, b) => a.localeCompare(b, 'zh-CN'))
    const colorByKey = assignLegendColors(sortedKeys, paletteKey, 'edge', colorDistribution)
    const items = Array.from(counters.entries()).map(([key, info]) => {
      const tier = edgeLegendTier(info.sample)
      const profile = graphEdgeProfile(info.sample, edgeStyleBinding)
      return {
        key,
        tier,
        shapeKind: 'directed',
        styleId: profile.styleId,
        strokeKind: profile.strokeKind,
        lineType: profile.lineType,
        label: `${edgeLegendLabel(info.sample, labels, relationClassLabel)} · ${edgeStrokeLabel(profile.strokeKind)} · ${edgeLineTypeLabel(profile.lineType)}`,
        count: info.count,
        color: colorByKey[key] || '#7dd3fc',
      } satisfies EdgeLegendItem
    })
    return items.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh-CN'))
  }, [topology.connectedEdges, graphConfig.data?.graph_relation_labels, paletteKey, colorDistribution, relationClassLabel, edgeStrokeLabel, edgeLineTypeLabel, edgeStyleBinding])

  const edgeLegendItemByKey = useMemo(() => {
    return new Map(edgeLegendItems.map((item) => [item.key, item]))
  }, [edgeLegendItems])

  const edgeLegendGroups = useMemo(() => {
    const grouped: Record<EdgeLegendTier, EdgeLegendItem[]> = {
      domain: [],
      class: [],
      pred: [],
      type: [],
    }
    edgeLegendItems.forEach((item) => grouped[item.tier].push(item))
    return (Object.keys(grouped) as EdgeLegendTier[])
      .map((tier) => [tier, grouped[tier]] as const)
      .filter(([, items]) => items.length > 0)
  }, [edgeLegendItems])

  const visibleEdges = useMemo(() => {
    return topology.visibleEdges.filter((edge) => !hiddenEdgeKinds[edgeLegendKey(edge)])
  }, [topology.visibleEdges, hiddenEdgeKinds])

  const edgeBadgeScale = useMemo(() => {
    return Math.max(0.6, Math.min(1.8, visualApplied.edgeWidth / 100))
  }, [visualApplied.edgeWidth])

  const useForceGraph3D = renderMode === 'projection3d' && projectionEngine === 'force3d'
  const useLegacyProjection3D = renderMode === 'projection3d' && projectionEngine === 'legacy'
  const { component: ForceGraph3DComp, error: forceGraphLoadError, retry: retryForceGraph3D } = useForceGraph3DLoader(useForceGraph3D)
  const displayResourceKey = `${projectKey}:${activeProjectionId}:${graphDataQueryKind}`
  const displayResource = useGraphDisplayResourceScheduler(displayResourceKey, useForceGraph3D, fullscreenWrapRef, forceGraphRef)
  const forceViewport = useForceGraphViewport(useForceGraph3D && displayResource.ready, fullscreenWrapRef)
  const synced3DRepulsionPercent = Math.max(0, Math.min(400, visualApplied.repulsion / 1.8))
  const synced3DGravity = Math.max(0, Math.min(0.6, 0.1 * (visualApplied.gravityPercent / 100)))
  const chartReady = chartReadyRaw && !useForceGraph3D
  const showForceGraphCanvas = useForceGraph3D && displayResource.ready && Boolean(ForceGraph3DComp) && !forceGraphLoadError

  const projectionResetKey = useLegacyProjection3D ? graphKind : null
  useEffect(() => {
    if (projectionResetKey === previousProjectionResetKeyRef.current) return
    previousProjectionResetKeyRef.current = projectionResetKey
    setProjectionFrameEpoch((epoch) => epoch + 1)
  }, [projectionResetKey])

  useEffect(() => {
    if (projectionEngine !== 'force3d') {
      forceGraphFallbackAppliedRef.current = false
      return
    }
    if (!useForceGraph3D || !forceGraphLoadError) return
    if (forceGraphFallbackAppliedRef.current) return
    forceGraphFallbackAppliedRef.current = true
    setForceGraphFallbackNotice(t('graphPage.error.force3dLoadFallback'))
    requestProjectionEngineChange('legacy')
  }, [projectionEngine, useForceGraph3D, forceGraphLoadError, requestProjectionEngineChange, t])

  const activeRendererCapabilities = useMemo(
    () => (renderMode === 'projection3d'
      ? RENDERER_PROJECTION_3D_CAPABILITIES
      : RENDERER_2D_CAPABILITIES),
    [renderMode],
  )

  const connectedNodeMap = useMemo(() => {
    return new Map(topology.connectedNodes.map((node) => [nodeKey(node), node]))
  }, [topology.connectedNodes])

  const adjacencyConnectedMap = useMemo(() => {
    const map = new Map<string, Set<string>>()
    const edges = topology.connectedEdges || []
    edges.forEach((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      const from = resolved.fromKey
      const to = resolved.toKey
      if (!map.has(from)) map.set(from, new Set())
      if (!map.has(to)) map.set(to, new Set())
      map.get(from)?.add(to)
      map.get(to)?.add(from)
    })
    return map
  }, [topology.connectedEdges, topology.edgeResolvedKeyMap])

  useEffect(() => {
    adjacencyConnectedMapRef.current = adjacencyConnectedMap
  }, [adjacencyConnectedMap])

  const {
    selectionEnabled,
    setSelectionEnabled,
    setManualSelectedNodeKeys,
    setManualDeselectedNodeKeys,
    setRadiationSelectionByCenter,
    selectionPinned,
    setSelectionPinned,
    autoFocusEnabled,
    setAutoFocusEnabled,
    hoverNodeKey,
    setHoverNodeKey,
    selectedNodeKeys,
    selectionEnabledRef,
    autoFocusEnabledRef,
    selectedNodeKeysRef,
    hoverNodeKeyRef,
  } = useGraphSelectionState(adjacencyConnectedMap)

  useEffect(() => {
    if (!import.meta.env.DEV) return
    window.__graphPageE2E = {
      selectNode: (nodeId: string) => {
        const entry = Array.from(connectedNodeMap.entries()).find(([, node]) => String(node.id) === nodeId)
        if (!entry) return false
        const [key, node] = entry
        setSelectedNode(node)
        setManualSelectedNodeKeys(new Set([key]))
        setManualDeselectedNodeKeys(new Set())
        setSelectionEnabled(true)
        return true
      },
    }
    return () => {
      delete window.__graphPageE2E
    }
  }, [connectedNodeMap, setManualSelectedNodeKeys, setManualDeselectedNodeKeys, setSelectionEnabled])

  useEffect(() => {
    if (previousGraphKindRef.current === graphKind) return
    previousGraphKindRef.current = graphKind
    setHiddenTypes({})
    setHiddenEdgeKinds({})
    setExpandedGroup(null)
    setExpandedEdgeGroup(null)
    setManualSelectedNodeKeys(new Set())
    setManualDeselectedNodeKeys(new Set())
    setRadiationSelectionByCenter({})
    setSelectionPinned(false)
    setHoverNodeKey(null)
  }, [
    graphKind,
    setHoverNodeKey,
    setManualDeselectedNodeKeys,
    setManualSelectedNodeKeys,
    setRadiationSelectionByCenter,
    setSelectionPinned,
  ])

  useEffect(() => {
    projectionPhysicsRef.current = { positions: {}, velocities: {} }
    projectionInteractionQuatRef.current = { x: 0, y: 0, z: 0, w: 1 }
    projectionAngularVelRef.current = { x: 0, y: 0 }
    projectionDragStateRef.current = { active: false, x: 0, y: 0 }
  }, [
    graphKind,
  ])

  useEffect(() => {
    if (!selectionEnabled) {
      nodeDragUnlockedRef.current = false
      if (nodeDragHoldTimerRef.current != null) {
        window.clearTimeout(nodeDragHoldTimerRef.current)
        nodeDragHoldTimerRef.current = null
      }
    }
  }, [selectionEnabled])


  useEffect(() => {
    setManualSelectedNodeKeys((prev) => {
      if (!prev.size) return prev
      const next = new Set(Array.from(prev).filter((key) => topology.connectedNodeKeys.has(key)))
      if (next.size === prev.size && Array.from(prev).every((key) => next.has(key))) return prev
      return next
    })
    setManualDeselectedNodeKeys((prev) => {
      if (!prev.size) return prev
      const next = new Set(Array.from(prev).filter((key) => topology.connectedNodeKeys.has(key)))
      if (next.size === prev.size && Array.from(prev).every((key) => next.has(key))) return prev
      return next
    })
    setRadiationSelectionByCenter((prev) => {
      const nextEntries = Object.entries(prev).filter(([key]) => topology.connectedNodeKeys.has(key))
      if (nextEntries.length === Object.keys(prev).length) return prev
      return Object.fromEntries(nextEntries)
    })
  }, [
    topology.connectedNodeKeys,
    setManualSelectedNodeKeys,
    setManualDeselectedNodeKeys,
    setRadiationSelectionByCenter,
  ])

  const dashboardParams: GraphStructuredDashboardParams = useMemo(() => {
    const maxItems = Math.min(100, Math.max(1, Number(dashboard.maxItems) || 100))
    const startOffsetRaw = Number(dashboard.startOffset)
    const daysBackRaw = Number(dashboard.daysBack)
    const startOffset = Number.isFinite(startOffsetRaw) && startOffsetRaw > 0 ? Math.trunc(startOffsetRaw) : null
    const daysBack = Number.isFinite(daysBackRaw) && daysBackRaw > 0 ? Math.min(365, Math.trunc(daysBackRaw)) : null
    const platforms = parseCommaSeparated(dashboard.platforms)
    const baseSubreddits = parseCommaSeparated(dashboard.baseSubreddits)
    return {
      language: dashboard.language.trim() || 'en',
      provider: dashboard.provider.trim() || 'auto',
      max_items: maxItems,
      start_offset: startOffset,
      days_back: daysBack,
      enable_extraction: dashboard.enableExtraction,
      async_mode: dashboard.asyncMode,
      platforms: platforms.length ? platforms : ['reddit'],
      enable_subreddit_discovery: dashboard.enableSubredditDiscovery,
      base_subreddits: baseSubreddits.length ? baseSubreddits : null,
      source_item_keys: dashboard.sourceItemKeys,
      project_key: projectKey,
    }
  }, [dashboard, projectKey])

  const filteredSourceItems = useMemo(() => {
    const keyword = sourceItemKeyword.trim().toLowerCase()
    const rows = Array.isArray(sourceItemsQuery.data) ? sourceItemsQuery.data : []
    if (!keyword) return rows
    return rows.filter((item: SourceLibraryItem) => {
      const key = String(item.item_key || '').toLowerCase()
      const name = String(item.name || '').toLowerCase()
      const desc = String(item.description || '').toLowerCase()
      const tags = Array.isArray(item.tags) ? item.tags.map((t) => String(t).toLowerCase()).join(' ') : ''
      return key.includes(keyword) || name.includes(keyword) || desc.includes(keyword) || tags.includes(keyword)
    })
  }, [sourceItemsQuery.data, sourceItemKeyword])

  const selectedNodeKeyList = useMemo(() => Array.from(selectedNodeKeys), [selectedNodeKeys])
  const [previousNodeEditSource, setPreviousNodeEditSource] = useState<{ firstKey: string; map: typeof draftNodeMap } | null>(null)
  const editableNodeItems = useMemo(
    () => draftNodes.map((node) => ({ key: nodeKey(node), label: `${nodeName(node)} (${node.type}:${String(node.id)})` })),
    [draftNodes],
  )
  const selectedEditableNodes = useMemo(
    () => selectedNodeKeyList.map((key) => draftNodeMap.get(key)).filter((item): item is GraphNodeItem => Boolean(item)),
    [selectedNodeKeyList, draftNodeMap],
  )
  const editableEdges = useMemo(
    () => draftEdges.map((edge, index) => ({
      index,
      key: `${String(edge.from?.type || '')}:${String(edge.from?.id || '')}>${String(edge.to?.type || '')}:${String(edge.to?.id || '')}:${String(edge.predicate || edge.type || '')}`,
      label: `${String(edge.from?.type || '')}:${String(edge.from?.id || '')} -> ${String(edge.to?.type || '')}:${String(edge.to?.id || '')} (${String(edge.predicate || edge.type || 'REL')})`,
    })),
    [draftEdges],
  )
  const activeEditableNode = useMemo(() => {
    if (!nodeEditDraft.key) return null
    return draftNodeMap.get(nodeEditDraft.key) || null
  }, [nodeEditDraft.key, draftNodeMap])

  useEffect(() => {
    if (templateBuilder && !editMode && previousTemplateBuilderRef.current !== templateBuilder) {
      previousTemplateBuilderRef.current = templateBuilder
      setEditMode(true)
      return
    }
    if (templateBuilder) return
    previousTemplateBuilderRef.current = templateBuilder
  }, [editMode, templateBuilder])

  if (editMode) {
    const firstKey = selectedNodeKeyList[0] || ''
    const editSource = { firstKey, map: draftNodeMap }
    if (
      firstKey
      && (!previousNodeEditSource
        || previousNodeEditSource.firstKey !== firstKey
        || previousNodeEditSource.map !== draftNodeMap)
    ) {
      setPreviousNodeEditSource(editSource)
      const node = draftNodeMap.get(firstKey)
      if (node) {
        setNodeEditDraft({
          key: firstKey,
          id: String(node.id ?? ''),
          type: String(node.type || ''),
          name: String(node.name || ''),
          title: String(node.title || ''),
          x: String(node.x ?? ''),
          y: String(node.y ?? ''),
          z: String(node.z ?? ''),
        })
      }
    }
  } else if (previousNodeEditSource) {
    setPreviousNodeEditSource(null)
  }

  useEffect(() => {
    if (previousCuratedGraphIdDefaultRef.current === defaultCuratedGraphId) return
    previousCuratedGraphIdDefaultRef.current = defaultCuratedGraphId
    setCuratedGraphId((prev) => (prev.trim() ? prev : defaultCuratedGraphId))
  }, [defaultCuratedGraphId])

  useEffect(() => {
    if (previousCuratedHandoffTopicDefaultRef.current === defaultCuratedHandoffTopic) return
    previousCuratedHandoffTopicDefaultRef.current = defaultCuratedHandoffTopic
    setCuratedHandoffTopic((prev) => (prev.trim() ? prev : defaultCuratedHandoffTopic))
  }, [defaultCuratedHandoffTopic])

  const applyCuratedState = useCallback((state: WorkflowGraphCuratedStateResponse, fallbackLabel: string) => {
    if (typeof state.revision === 'number') setCuratedRevision(state.revision)
    const status = String(state.sync_status || state.submit_status || state.rollback_status || fallbackLabel)
    const revision = typeof state.revision === 'number' ? ` r${state.revision}` : ''
    const version = state.active_version_id ? ` ${state.active_version_id}` : ''
    setCuratedStatus(`${status}${revision}${version}`)
  }, [setCuratedRevision, setCuratedStatus])

  const readCuratedAudits = async (graphId: string) => {
    const auditList = await listWorkflowGraphCuratedAudits(graphId, 10)
    const items = Array.isArray(auditList.items) ? auditList.items : []
    setCuratedAuditItems(items)
    const rollbackCandidate = items.find((item) => item.action === 'submit' && typeof item.version_id === 'string')?.version_id
    if (rollbackCandidate) {
      setCuratedRollbackVersionId((prev) => (prev.trim() ? prev : String(rollbackCandidate)))
    }
    return items
  }

  const handleListCuratedAudits = async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert(t('graphPage.error.curatedGraphIdRequired'))
      return
    }
    setCuratedBusy(true)
    try {
      const items = await readCuratedAudits(graphId)
      const latest = items[0]
      const latestText = latest ? ` latest=${String(latest.action || 'unknown')} ${String(latest.version_id || '')}`.trimEnd() : ''
      setCuratedStatus(`audit_readback items=${items.length}${latestText ? ` ${latestText}` : ''}`)
      setGraphEditStatus(tf('graphPage.status.curatedAuditReadback', { graphId }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.auditReadFailed')
      setCuratedStatus(`audit_failed: ${message}`)
      setGraphEditStatus(tf('graphPage.error.curatedAuditReadFailed', { message }))
      window.alert(tf('graphPage.error.curatedAuditReadFailed', { message }))
    } finally {
      setCuratedBusy(false)
    }
  }

  const handleRollbackCuratedGraph = async () => {
    const graphId = curatedGraphId.trim()
    const targetVersionId = curatedRollbackVersionId.trim()
    if (!graphId) {
      window.alert(t('graphPage.error.curatedGraphIdRequired'))
      return
    }
    if (!targetVersionId) {
      window.alert(t('graphPage.error.rollbackVersionRequired'))
      return
    }
    setCuratedBusy(true)
    try {
      const state = await rollbackWorkflowGraphCuratedState(graphId, {
        target_version_id: targetVersionId,
        actor_id: 'graphpage.curated-consumer',
        reason: curatedRollbackReason.trim() || undefined,
        ...(curatedRevision == null ? {} : { base_revision: curatedRevision }),
      })
      applyCuratedState(state, 'rollback')
      const items = await readCuratedAudits(graphId)
      const revision = typeof state.revision === 'number' ? ` r${state.revision}` : ''
      setCuratedStatus(`rollback_succeeded${revision} audits=${items.length}`)
      markDraftSaved()
      setGraphEditStatus(tf('graphPage.status.curatedRollbackSubmitted', { versionId: targetVersionId }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.rollbackFailed')
      setCuratedStatus(`rollback_failed: ${message}`)
      setGraphEditStatus(tf('graphPage.error.curatedRollbackFailed', { message }))
      window.alert(tf('graphPage.error.curatedRollbackFailed', { message }))
    } finally {
      setCuratedBusy(false)
    }
  }

  const handleReplayCuratedHandoff = useCallback(async () => {
    const runId = curatedHandoffReplay.runId.trim()
    const handoffId = curatedHandoffReplay.handoffId.trim()
    if (!runId || !handoffId) {
      window.alert(t('graphPage.error.handoffPersistenceRequired'))
      return
    }
    setCuratedBusy(true)
    try {
      const replay = await replayWorkflowGraphHandoff(runId, handoffId)
      const events = Array.isArray(replay.events) ? replay.events : []
      setCuratedStatus(`handoff_replay_ready events=${events.length}`)
      setGraphEditStatus(tf('graphPage.status.curatedHandoffReplayRead', { handoffId }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.handoffReplayFailed')
      setCuratedStatus(`handoff_replay_failed: ${message}`)
      setGraphEditStatus(tf('graphPage.error.curatedHandoffReplayFailed', { message }))
      window.alert(tf('graphPage.error.curatedHandoffReplayFailed', { message }))
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedHandoffReplay, setCuratedBusy, setCuratedStatus, setGraphEditStatus, t, tf])

  const handleSyncCuratedGraph = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert(t('graphPage.error.curatedGraphIdRequired'))
      return
    }
    setCuratedBusy(true)
    try {
      const state = await syncWorkflowGraphCuratedState(
        graphId,
        curatedRevision == null ? {} : { since_revision: curatedRevision },
      )
      const snapshot = snapshotDslFromCuratedState(state)
      if (snapshot) {
        replaceDraft(snapshot.nodes as GraphNodeItem[], snapshot.edges as GraphEdgeItem[], { markAsDirty: false })
      }
      applyCuratedState(state, 'synced')
      setGraphEditStatus(tf('graphPage.status.curatedSynced', { graphId }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.syncFailed')
      setCuratedStatus(`sync_failed: ${message}`)
      setGraphEditStatus(tf('graphPage.error.curatedSyncFailed', { message }))
      window.alert(tf('graphPage.error.curatedSyncFailed', { message }))
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedRevision, replaceDraft, applyCuratedState, setCuratedBusy, setCuratedStatus, setGraphEditStatus, t, tf])

  const handleSaveCuratedDraft = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert(t('graphPage.error.curatedGraphIdRequired'))
      return
    }
    const dsl = buildCuratedWorkflowGraphDsl(draftNodes, draftEdges)
    if (!dsl.nodes.length) {
      window.alert(t('graphPage.error.noSubmittableDraftNodes'))
      return
    }
    setCuratedBusy(true)
    try {
      const state = await saveWorkflowGraphCuratedDraft(graphId, {
        dsl,
        actor_id: 'graphpage.curated-consumer',
        ...(curatedRevision == null ? {} : { base_revision: curatedRevision }),
      })
      applyCuratedState(state, 'draft_saved')
      markDraftSaved()
      setGraphEditStatus(tf('graphPage.status.curatedDraftSaved', { graphId }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.saveFailed')
      setCuratedStatus(`draft_failed: ${message}`)
      setGraphEditStatus(tf('graphPage.error.curatedDraftSaveFailed', { message }))
      window.alert(tf('graphPage.error.curatedDraftSaveFailed', { message }))
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedRevision, draftNodes, draftEdges, applyCuratedState, markDraftSaved, setCuratedBusy, setCuratedStatus, setGraphEditStatus, t, tf])

  const handleSubmitCuratedGraph = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert(t('graphPage.error.curatedGraphIdRequired'))
      return
    }
    const dsl = buildCuratedWorkflowGraphDsl(draftNodes, draftEdges)
    if (!dsl.nodes.length) {
      window.alert(t('graphPage.error.noSubmittableDraftNodes'))
      return
    }
    const temporaryIds = temporaryCuratedNodeIds(dsl)
    if (temporaryIds.length) {
      const sample = temporaryIds.slice(0, 3).join(', ')
      const message = tf('graphPage.error.temporaryCuratedNodeIds', { sample })
      setCuratedStatus(`submit_blocked: ${message}`)
      window.alert(message)
      return
    }
    setCuratedBusy(true)
    try {
      const draftState = await saveWorkflowGraphCuratedDraft(graphId, {
        dsl,
        actor_id: 'graphpage.curated-consumer',
        ...(curatedRevision == null ? {} : { base_revision: curatedRevision }),
      })
      const nextBaseRevision = typeof draftState.revision === 'number' ? draftState.revision : curatedRevision ?? undefined
      const submittedState = await submitWorkflowGraphCuratedDraft(graphId, {
        actor_id: 'graphpage.curated-consumer',
        object_scope: 'curated_business_graph',
        ...(nextBaseRevision == null ? {} : { base_revision: nextBaseRevision }),
      })
      applyCuratedState(submittedState, 'submitted')
      markDraftSaved()
      setGraphEditStatus(tf('graphPage.status.curatedGraphSubmitted', { graphId }))
    } catch (error) {
      const failure = curatedSubmitFailure(error, tf)
      setCuratedStatus(failure.status)
      setGraphEditStatus(failure.graphStatus)
      window.alert(failure.alertMessage)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedRevision, draftNodes, draftEdges, applyCuratedState, markDraftSaved, setCuratedBusy, setCuratedStatus, setGraphEditStatus, t, tf])

  const handleBuildCuratedReportingHandoff = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert(t('graphPage.error.curatedGraphIdRequired'))
      return
    }
    const topic = curatedHandoffTopic.trim()
    if (!topic) {
      window.alert(t('graphPage.error.reportingTopicRequired'))
      return
    }
    const selected_node_ids = selectedEditableNodes
      .map((node) => curatedNodeId(node))
      .filter(Boolean)

    setCuratedBusy(true)
    try {
      const handoff = await buildWorkflowGraphReportingHandoff(graphId, {
        topic,
        ...(selected_node_ids.length ? { selected_node_ids } : {}),
      })
      const reportRequest = handoff.report_generate_request || {}
      const sourceCount = Array.isArray(reportRequest.sources) ? reportRequest.sources.length : 0
      const persistence = handoff.persistence || {}
      const runId = String(persistence.run_id || '').trim()
      const handoffId = String(handoff.handoff_id || '').trim()
      if (runId && handoffId) {
        setCuratedHandoffReplay({ runId, handoffId })
      }
      setCuratedStatus(`report_handoff_ready${sourceCount ? ` sources=${sourceCount}` : ''}${runId ? ` ${runId}` : ''}`)
      setGraphEditStatus(tf('graphPage.status.curatedReportingHandoffGenerated', { handoffId: handoffId || graphId }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.handoffBuildFailed')
      setCuratedStatus(`report_handoff_failed: ${message}`)
      setGraphEditStatus(tf('graphPage.error.curatedReportingHandoffFailed', { message }))
      window.alert(tf('graphPage.error.curatedReportingHandoffFailed', { message }))
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedHandoffTopic, selectedEditableNodes, setCuratedBusy, setCuratedHandoffReplay, setCuratedStatus, setGraphEditStatus, t, tf])

  const selectedExportPayload = useMemo(() => {
    const scopedTopicFocus = graphProjection.topicScope
    const selectedNodes = Array.from(selectedNodeKeys)
      .map((key) => connectedNodeMap.get(key))
      .filter((node): node is GraphNodeItem => Boolean(node))
    const selectedSet = new Set(selectedNodes.map((node) => nodeKey(node)))
    const selectedEdges = visibleEdges.filter((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return false
      return selectedSet.has(resolved.fromKey) && selectedSet.has(resolved.toKey)
    })
    return {
      project_key: projectKey,
      graph_type: graphKind,
      selected_count: selectedNodes.length,
      edge_count: selectedEdges.length,
      dashboard: dashboardParams,
      llm_assist: dashboard.llmAssist,
      selected_nodes: selectedNodes.map((node) => ({
        type: String(node.type || ''),
        id: String(node.id || ''),
        entry_id: String(node.entry_id || node.id || ''),
        label: nodeName(node),
        topic_focus: scopedTopicFocus,
      })),
      selected_edges: selectedEdges.map((edge) => ({
        source_entry_id: String(edge.from?.id || '').trim() || undefined,
        target_entry_id: String(edge.to?.id || '').trim() || undefined,
        relation: String(edge.type || '').trim() || undefined,
        label: String(edge.predicate || edge.type || '').trim() || undefined,
      })),
      edges: selectedEdges,
    }
  }, [selectedNodeKeys, connectedNodeMap, visibleEdges, topology.edgeResolvedKeyMap, projectKey, graphKind, graphProjection.topicScope, dashboardParams, dashboard.llmAssist])

  const clueChainSeedNodes = useMemo<ClueChainSeedNode[]>(() => {
    const selectedSeeds = selectedExportPayload.selected_nodes.map((node) => ({
      node_id: String(node.id || node.entry_id || '').trim(),
      node_type: String(node.type || '').trim() || 'Entity',
      entry_id: String(node.entry_id || node.id || '').trim(),
      label: String(node.label || node.id || '').trim() || t('graphPage.label.unnamedNode'),
    })).filter((node) => node.node_id)
    if (selectedSeeds.length) return selectedSeeds
    return topology.visibleNodes.slice(0, 3).map((node) => ({
      node_id: String(node.id || '').trim(),
      node_type: String(node.type || '').trim() || 'Entity',
      entry_id: String(node.entry_id || node.id || '').trim(),
      label: nodeName(node),
    })).filter((node) => node.node_id)
  }, [selectedExportPayload.selected_nodes, topology.visibleNodes, t])

  const handleCreateClueChain = useCallback(async () => {
    if (!clueChainSeedNodes.length) {
      window.alert(t('graphPage.error.noClueChainNodes'))
      return
    }
    setClueChainBusy(true)
    setClueChainStatus(t('graphPage.status.clueChainCreating'))
    try {
      const chain = await createClueChain({
        project_key: projectKey,
        graph_type: graphKind,
        title: `${graphVariantLabel} · ${clueChainSeedNodes[0]?.label || t('graphPage.clueChain.defaultTitle')}`,
        seed_nodes: clueChainSeedNodes,
        selected_edges: selectedExportPayload.selected_edges,
        graph_context: {
          variant,
          selected_count: selectedExportPayload.selected_count,
          edge_count: selectedExportPayload.edge_count,
          visible_nodes: topology.visibleNodes.length,
          visible_edges: topology.visibleEdges.length,
        },
      })
      setActiveClueChain(chain)
      setSelectedClueEvidenceId(chain.evidence?.[0]?.evidence_id || null)
      setClueChainOpen(true)
      setClueChainStatus(tf('graphPage.status.clueChainCreated', { chainId: chain.chain_id }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.createFailed')
      setClueChainStatus(tf('graphPage.error.createFailedWithMessage', { message }))
      window.alert(tf('graphPage.error.clueChainCreateFailed', { message }))
    } finally {
      setClueChainBusy(false)
    }
  }, [
    clueChainSeedNodes,
    graphKind,
    projectKey,
    selectedExportPayload.edge_count,
    selectedExportPayload.selected_count,
    selectedExportPayload.selected_edges,
    topology.visibleEdges.length,
    topology.visibleNodes.length,
    variant,
    graphVariantLabel,
    setActiveClueChain,
    setClueChainBusy,
    setClueChainOpen,
    setClueChainStatus,
    setSelectedClueEvidenceId,
    t,
    tf,
  ])

  const handleRunClueChainExpand = useCallback(async (mode: 'source_library' | 'external_search') => {
    if (!activeClueChain) return
    setClueChainBusy(true)
    const modeLabel = mode === 'source_library' ? t('graphPage.clueChain.mode.sourceLibrary') : t('graphPage.clueChain.mode.externalSearch')
    setClueChainStatus(tf('graphPage.status.clueChainExpanding', { mode: modeLabel }))
    try {
      const frontierNodeIds = (activeClueChain.frontier || [])
        .map((item) => String(item.node_id || '').trim())
        .filter(Boolean)
      const chain = await expandClueChain(activeClueChain.chain_id, {
        mode,
        project_key: projectKey,
        graph_type: graphKind,
        frontier_node_ids: frontierNodeIds.length ? frontierNodeIds : clueChainSeedNodes.map((node) => node.node_id),
      })
      setActiveClueChain(chain)
      setSelectedClueEvidenceId((current) => current || chain.evidence?.[0]?.evidence_id || null)
      setClueChainOpen(true)
      setClueChainStatus(tf('graphPage.status.clueChainExpanded', { mode: modeLabel }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.expandFailed')
      setClueChainStatus(tf('graphPage.error.expandFailedWithMessage', { message }))
      window.alert(tf('graphPage.error.clueChainExpandFailed', { message }))
    } finally {
      setClueChainBusy(false)
    }
  }, [activeClueChain, clueChainSeedNodes, graphKind, projectKey, setActiveClueChain, setClueChainBusy, setClueChainOpen, setClueChainStatus, setSelectedClueEvidenceId, t, tf])

  const handleReviewClueChainCandidate = useCallback(async (candidateId: string, decision: 'promote' | 'reject') => {
    if (!activeClueChain) return
    setClueChainBusy(true)
    setClueChainStatus(decision === 'promote' ? t('graphPage.status.promoteDecisionRecording') : t('graphPage.status.rejectDecisionRecording'))
    try {
      const chain = await decideClueChainCandidate(activeClueChain.chain_id, candidateId, {
        decision,
        actor_id: 'graphpage.clue-chain-ui',
        reason: decision === 'promote'
          ? 'reviewed_from_graphpage_candidate_queue'
          : 'rejected_from_graphpage_candidate_queue',
      })
      setActiveClueChain(chain)
      setClueChainOpen(true)
      setClueChainStatus(decision === 'promote' ? t('graphPage.status.promoteDecisionRecorded') : t('graphPage.status.rejectDecisionRecorded'))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.reviewFailed')
      setClueChainStatus(tf('graphPage.error.reviewFailedWithMessage', { message }))
      window.alert(tf('graphPage.error.clueChainReviewFailed', { message }))
    } finally {
      setClueChainBusy(false)
    }
  }, [activeClueChain, setActiveClueChain, setClueChainBusy, setClueChainOpen, setClueChainStatus, t, tf])

  const copyStructuredPayload = async () => {
    const text = JSON.stringify(selectedExportPayload, null, 2)
    await navigator.clipboard.writeText(text)
  }

  const submitStructuredTasks = async (flowType: 'collect' | 'source_collect') => {
    if (!selectedExportPayload.selected_nodes.length) {
      window.alert(t('graphPage.error.selectNode'))
      return
    }
    setSubmittingMap((prev) => ({ ...prev, [flowType]: true }))
    setStructuredResultMap((prev) => ({
      ...prev,
      [flowType]: {
        flow_type: flowType,
        summary: { accepted: 0, queued: 0, failed: 0 },
        batches: [],
      },
    }))
    try {
      const result = await submitGraphStructuredSearchTasks({
        selected_nodes: selectedExportPayload.selected_nodes,
        selected_edges: selectedExportPayload.selected_edges,
        dashboard: selectedExportPayload.dashboard,
        llm_assist: selectedExportPayload.llm_assist,
        flow_type: flowType,
        intent_mode: 'keyword_llm',
      })
      setStructuredResultMap((prev) => ({ ...prev, [flowType]: result }))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('graphPage.error.submitFailed')
      setStructuredResultMap((prev) => ({
        ...prev,
        [flowType]: {
          flow_type: flowType,
          summary: { accepted: 0, queued: 0, failed: 1 },
          batches: [],
          error_message: message,
        },
      }))
    } finally {
      setSubmittingMap((prev) => ({ ...prev, [flowType]: false }))
    }
  }

  const selectedNodeContext = useMemo<NodeGraphContext | null>(() => {
    if (!selectedNode) return null
    const centerKey = nodeKey(selectedNode)
    if (!topology.connectedNodeKeys.has(centerKey)) return null
    const edges = topology.connectedEdges
    const nodeByKey = connectedNodeMap
    const incident = edges.filter((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return false
      const fk = resolved.fromKey
      const tk = resolved.toKey
      return fk === centerKey || tk === centerKey
    })
    if (!incident.length) {
      return {
        degree: 0,
        neighborTypeCount: 0,
        marketDocCount: 0,
        neighborTypeItems: [],
        predicateItems: [],
        neighborNodesByType: {},
        relationsByPredicate: {},
        relationItems: [],
      }
    }

    const neighborTypeCount = new Map<string, number>()
    const predicateCount = new Map<string, number>()
    const relatedDocs = new Set<string>()
    const relationItems: NodeGraphContext['relationItems'] = []
    const neighborNodesByType = new Map<string, Array<{ id: string; name: string; type: string }>>()
    const relationsByPredicate = new Map<string, NodeGraphContext['relationItems']>()
    const defaultRelation = t('graphPage.label.defaultRelation')

    incident.forEach((edge, index) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      const fk = resolved.fromKey
      const tk = resolved.toKey
      const outbound = fk === centerKey
      const otherKey = fk === centerKey ? tk : fk
      const other = nodeByKey.get(otherKey)
      if (other?.type) {
        neighborTypeCount.set(other.type, (neighborTypeCount.get(other.type) || 0) + 1)
        const bucket = neighborNodesByType.get(other.type) || []
        bucket.push({
          id: String(other.id),
          name: nodeName(other),
          type: other.type,
        })
        neighborNodesByType.set(other.type, bucket)
      }
      const pred = String(edge.predicate || edge.type || '').trim()
      if (pred) {
        predicateCount.set(pred, (predicateCount.get(pred) || 0) + 1)
      }
      if (other?.type === 'MarketData' && other.id != null) {
        relatedDocs.add(String(other.id))
      }
      relationItems.push({
        id: `${index}-${otherKey}-${pred || defaultRelation}`,
        direction: outbound ? 'OUT' : 'IN',
        relation: pred || defaultRelation,
        targetName: other ? nodeName(other) : otherKey,
        targetType: other?.type || '-',
      })
      if (pred) {
        const group = relationsByPredicate.get(pred) || []
        group.push({
          id: `${index}-${otherKey}-${pred || defaultRelation}-pred`,
          direction: outbound ? 'OUT' : 'IN',
          relation: pred,
          targetName: other ? nodeName(other) : otherKey,
          targetType: other?.type || '-',
        })
        relationsByPredicate.set(pred, group)
      }
    })

    return {
      degree: incident.length,
      neighborTypeCount: neighborTypeCount.size,
      marketDocCount: relatedDocs.size,
      neighborTypeItems: Array.from(neighborTypeCount.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([type, count]) => ({ type, count }))
        .slice(0, 12),
      predicateItems: Array.from(predicateCount.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([predicate, count]) => ({ predicate, count }))
        .slice(0, 12),
      neighborNodesByType: Object.fromEntries(
        Array.from(neighborNodesByType.entries()).map(([type, items]) => [
          type,
          Array.from(new Map(items.map((item) => [`${item.type}:${item.id}`, item])).values()),
        ]),
      ),
      relationsByPredicate: Object.fromEntries(relationsByPredicate.entries()),
      relationItems,
    }
  }, [selectedNode, topology.connectedNodeKeys, topology.connectedEdges, topology.edgeResolvedKeyMap, connectedNodeMap, t])

  const selectedNodeKey = useMemo(() => {
    if (!selectedNode) return null
    const key = nodeKey(selectedNode)
    return topology.connectedNodeKeys.has(key) ? key : null
  }, [selectedNode, topology.connectedNodeKeys])

  useEffect(() => {
    setForceNodeSeedPhysics(new Map(forceNodePhysicsRef.current))
  }, [activeProjectionId])

  const forceGraphData = useMemo(() => {
    if (renderMode !== 'projection3d') return { nodes: [] as Array<{ id: string; key: string; name: string; rawNode: GraphNodeItem; score: number; x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number }>, links: [] as Array<{ source: string; target: string }> }
    const nodes = topology.connectedNodes.map((node) => {
      const key = nodeKey(node)
      const score = topology.scoreMap.get(key) || 0
      const prev = forceNodeSeedPhysics.get(`${activeProjectionId}\u0000${key}`) || {}
      return {
        id: key,
        key,
        name: nodeName(node),
        rawNode: node,
        score,
        x: prev.x,
        y: prev.y,
        z: prev.z,
        vx: prev.vx,
        vy: prev.vy,
        vz: prev.vz,
      }
    })
    const links = topology.connectedEdges
      .map((edge) => {
        const resolved = topology.edgeResolvedKeyMap.get(edge)
        if (!resolved) return null
        return {
          source: resolved.fromKey,
          target: resolved.toKey,
        }
      })
      .filter((item): item is { source: string; target: string } => Boolean(item))
    return { nodes, links }
  }, [renderMode, activeProjectionId, forceNodeSeedPhysics, topology.connectedNodes, topology.connectedEdges, topology.scoreMap, topology.edgeResolvedKeyMap])

  const forceVisibleNodeKeySet = useMemo(() => new Set(topology.visibleNodes.map((node) => nodeKey(node))), [topology.visibleNodes])
  const forceVisibleLinkKeySet = useMemo(() => {
    const set = new Set<string>()
    visibleEdges.forEach((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      set.add(`${resolved.fromKey}>${resolved.toKey}`)
    })
    return set
  }, [visibleEdges, topology.edgeResolvedKeyMap])

  const forceNodeStyleById = useMemo(() => {
    if (renderMode !== 'projection3d') return new Map<string, { color: string; val: number; opacity: number }>()
    const map = new Map<string, { color: string; val: number; opacity: number }>()
    forceGraphData.nodes.forEach((node) => {
      const rawNode = (node as { rawNode?: GraphNodeItem }).rawNode
      const normalizedType = normalizeNodeType(rawNode?.type || '')
      const key = String((node as { id?: string }).id || '')
      const nodeColor = nodeTypeColor[normalizedType] || '#7dd3fc'
      const centralityScore = topology.centralityScoreMap.get(key) || 0
      const neighborTightnessScore = topology.neighborTightnessScoreMap.get(key) || 0
      const rawSymbol = resolveNodeSymbol(normalizedType)
      const baseSize = computeNodeVisualSize(
        centralityScore,
        topology.centralityMinScore,
        topology.centralityRangeScore,
        neighborTightnessScore,
        topology.neighborMinScore,
        topology.neighborRangeScore,
        visualApplied.nodeScale,
        visualApplied.nodeContrastCentral,
        visualApplied.nodeContrastNeighbor,
      )
      const size = Math.max(0.001, baseSize * symbolSizeGain(rawSymbol) * FORCE_3D_GLOBAL_SIZE_GAIN)
      const compensationX = computeForce3DSizeCompensationX(visualApplied.nodeScale)
      const compensatedSize = Math.max(0.001, size * compensationX)
      const alphaBase = Math.max(0.14, Math.min(1, visualApplied.nodeAlpha / 100))
      map.set(key, {
        color: nodeColor,
        val: Math.max(0.02, compensatedSize / 6.5),
        opacity: alphaBase,
      })
    })
    return map
  }, [
    renderMode,
    forceGraphData.nodes,
    nodeTypeColor,
    topology.centralityScoreMap,
    topology.neighborTightnessScoreMap,
    topology.centralityMinScore,
    topology.centralityRangeScore,
    topology.neighborMinScore,
    topology.neighborRangeScore,
    visualApplied.nodeScale,
    visualApplied.nodeContrastCentral,
    visualApplied.nodeContrastNeighbor,
    visualApplied.nodeAlpha,
  ])

  const forceAutoFocusSet = useMemo(() => {
    const set = new Set<string>()
    const focusCenterKey = autoFocusEnabled ? hoverNodeKey : null
    if (!focusCenterKey || !topology.visibleNodeKeys.has(focusCenterKey)) return set
    collectFocusNodeKeys(focusCenterKey, adjacencyConnectedMap).forEach((item) => set.add(item))
    return set
  }, [autoFocusEnabled, hoverNodeKey, topology.visibleNodeKeys, adjacencyConnectedMap])

  const forceLinkStyleByKey = useMemo(() => {
    if (renderMode !== 'projection3d') return new Map<string, ForceLinkStyle>()
    const map = new Map<string, ForceLinkStyle>()
    const enableAutoFocusDim = autoFocusEnabled && forceAutoFocusSet.size > 0
    const edgeAlphaT = Math.max(0, Math.min(1, visualApplied.edgeAlpha / 100))
    topology.connectedEdges.forEach((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      const fromKey = resolved.fromKey
      const toKey = resolved.toKey
      const style = edgeLegendItemByKey.get(edgeLegendKey(edge))
      const colorHex = style?.color || '#7dd3fc'
      const profile = graphEdgeProfile(edge, edgeStyleBinding)
      const { r, g, b } = hexToRgb(colorHex)
      const dimByAutoFocus = enableAutoFocusDim && !(forceAutoFocusSet.has(fromKey) && forceAutoFocusSet.has(toKey))
      map.set(
        `${fromKey}>${toKey}`,
        {
          color: dimByAutoFocus
            ? 'rgba(125, 211, 252, 0.05)'
            : `rgba(${r}, ${g}, ${b}, ${Math.max(0.04, edgeAlphaT)})`,
          width: dimByAutoFocus
            ? 0.7
            : Math.max(0.5, profile.width * (visualApplied.edgeWidth / 100)),
          opacity: dimByAutoFocus ? 0.08 : Math.max(0.08, edgeAlphaT),
          curvature: Math.abs(profile.curveness),
          curveRotation: profile.curveness < 0 ? Math.PI : 0,
          arrowLength: profile.symbol[1] === 'none' || dimByAutoFocus
            ? 0
            : Math.max(0, 4.5 * (visualApplied.edgeWidth / 100)),
        },
      )
    })
    return map
  }, [renderMode, topology.connectedEdges, topology.edgeResolvedKeyMap, edgeLegendItemByKey, edgeStyleBinding, visualApplied.edgeWidth, visualApplied.edgeAlpha, autoFocusEnabled, forceAutoFocusSet])

  const applyForceObjectVisualState = useCallback((object: THREE.Object3D, selected: boolean, dimmed: boolean) => {
    if (!object || typeof object !== 'object') return
    if (object.userData?.__graphNodeSelected === selected && object.userData?.__graphNodeDimmed === dimmed) return
    const scaleBase = object.userData?.__graphNodeBaseScale || {
      x: Number(object.scale?.x || 1),
      y: Number(object.scale?.y || 1),
      z: Number(object.scale?.z || 1),
    }
    object.userData = {
      ...(object.userData || {}),
      __graphNodeBaseScale: scaleBase,
      __graphNodeSelected: selected,
      __graphNodeDimmed: dimmed,
    }
    const scaleGain = selected ? 1.08 : (dimmed ? 0.9 : 1)
    if (object.scale?.set) {
      object.scale.set(scaleBase.x * scaleGain, scaleBase.y * scaleGain, scaleBase.z * scaleGain)
    }
    const applyMaterial = (mesh: THREE.Mesh) => {
      const materials = Array.isArray(mesh?.material) ? mesh.material : [mesh?.material]
      materials.forEach((mat) => {
        if (!mat) return
        const typedMat = mat as THREE.Material & {
          userData?: Record<string, unknown>
          opacity?: number
          transparent?: boolean
          emissive?: THREE.Color
          emissiveIntensity?: number
        }
        const baseOpacity = Number(typedMat.userData?.__graphNodeBaseOpacity ?? typedMat.opacity ?? 1)
        const baseTransparent = Boolean(typedMat.userData?.__graphNodeBaseTransparent ?? typedMat.transparent)
        mat.userData = {
          ...(typedMat.userData || {}),
          __graphNodeBaseOpacity: baseOpacity,
          __graphNodeBaseTransparent: baseTransparent,
        }
        if (typedMat.emissive) typedMat.emissive.set(selected ? '#facc15' : '#000000')
        if (typeof typedMat.emissiveIntensity === 'number') typedMat.emissiveIntensity = selected ? 0.28 : 0
        // Keep material pipeline stable: do not toggle transparent at runtime.
        if (dimmed) {
          // Dim all nodes (including white-filled empty symbols) when focus-hide is active.
          typedMat.transparent = true
          typedMat.opacity = Math.max(0.12, baseOpacity * 0.35)
        } else {
          typedMat.transparent = baseTransparent
          typedMat.opacity = baseOpacity
        }
        typedMat.needsUpdate = true
      })
    }
    if (object instanceof THREE.Mesh) {
      applyMaterial(object)
      return
    }
    if (object instanceof THREE.Group) {
      object.traverse((child) => {
        if (child instanceof THREE.Mesh) applyMaterial(child)
      })
    }
  }, [])

  useEffect(() => {
    if (!useForceGraph3D || !displayResource.ready) return
    const raf = window.requestAnimationFrame(() => {
      const api = forceGraphRef.current
      const scene = api?.scene?.()
      if (!scene?.traverse) return
      const selected = selectedNodeKeysRef.current
      const enableAutoFocusDim = autoFocusEnabled && forceAutoFocusSet.size > 0
      // Avoid touching 3D material states when neither selection nor effective autofocus is active.
      // This prevents "toggle-on flicker/disappear" on unstable node materials before any focus center exists.
      if (!enableAutoFocusDim && selected.size === 0) return
      scene.traverse((obj) => {
        if (!obj?.userData?.__graphNodeObject) return
        const id = String(obj?.userData?.__graphNodeId || '')
        if (!id) return
        const dimmed = enableAutoFocusDim && !forceAutoFocusSet.has(id)
        applyForceObjectVisualState(obj, selected.has(id), dimmed)
      })
    })
    return () => window.cancelAnimationFrame(raf)
  }, [useForceGraph3D, displayResource.ready, selectedNodeKeys, selectedNodeKeysRef, forceGraphData.nodes, autoFocusEnabled, forceAutoFocusSet, applyForceObjectVisualState])

  useEffect(() => {
    if (renderMode === 'projection3d') return
    forceNodeObjectCacheRef.current.clear()
  }, [renderMode])

  useEffect(() => {
    if (!useForceGraph3D) return
    const activeNodeIds = new Set(forceGraphData.nodes.map((node) => String(node.id || '')))
    pruneForceNodeObjectCache(forceNodeObjectCacheRef.current, activeNodeIds)
  }, [useForceGraph3D, forceGraphData.nodes])

  useEffect(() => {
    if (!autoFocusEnabled) {
      dragFocusNodeKeyRef.current = null
      forceHoverPendingKeyRef.current = null
      if (forceHoverRafRef.current != null) {
        window.cancelAnimationFrame(forceHoverRafRef.current)
        forceHoverRafRef.current = null
      }
      if (hoverNodeKeyRef.current != null) {
        hoverNodeKeyRef.current = null
        setHoverNodeKey(null)
      }
      return
    }
    if (hoverNodeKey && !topology.visibleNodeKeys.has(hoverNodeKey)) {
      setHoverNodeKey(null)
    }
  }, [autoFocusEnabled, hoverNodeKey, topology.visibleNodeKeys, selectedNodeKeysRef, setHoverNodeKey, hoverNodeKeyRef])

  useEffect(() => {
    try {
      if (useForceGraph3D && displayResource.ready) {
        forceGraphRef.current?.resumeAnimation?.()
      } else {
        forceGraphRef.current?.pauseAnimation?.()
      }
    } catch {
      // noop
    }
  }, [useForceGraph3D, displayResource.ready])

  useEffect(() => {
    if (!useForceGraph3D) return
    const api = forceGraphRef.current
    if (!api) return
    try {
      api.width?.(forceViewport.width)
      api.height?.(forceViewport.height)
    } catch {
      // noop
    }
  }, [useForceGraph3D, forceViewport.width, forceViewport.height])

  useEffect(() => {
    if (!useForceGraph3D) return
    const api = forceGraphRef.current
    if (!api) return
    try {
      if (typeof api.d3Force !== 'function') return
      const chargeForce = api.d3Force('charge') as { strength?: (v?: number) => unknown } | null
      const linkForce = api.d3Force('link') as {
        strength?: (v?: number | ((link: unknown) => number)) => unknown
        distance?: (v?: number | ((link: unknown) => number)) => unknown
        iterations?: (v?: number) => unknown
      } | null
      const repulsion = Math.max(20, synced3DRepulsionPercent * 2.2)
      forceGlobalGravityStrengthRef.current = synced3DGravity
      if (!forceGlobalGravityForceRef.current) {
        let nodes: Array<Record<string, unknown>> = []
        const globalGravityForce = ((alpha: number) => {
          const g = forceGlobalGravityStrengthRef.current
          if (!(g > 0)) return
          const k = g * 0.06 * Math.max(0, alpha)
          for (let i = 0; i < nodes.length; i += 1) {
            const node = nodes[i]
            const x = Number(node.x || 0)
            const y = Number(node.y || 0)
            const z = Number(node.z || 0)
            node.vx = Number(node.vx || 0) - x * k
            node.vy = Number(node.vy || 0) - y * k
            node.vz = Number(node.vz || 0) - z * k
          }
        }) as ((alpha: number) => void) & { initialize?: (items: Array<Record<string, unknown>>) => void }
        globalGravityForce.initialize = (items: Array<Record<string, unknown>>) => {
          nodes = Array.isArray(items) ? items : []
        }
        forceGlobalGravityForceRef.current = globalGravityForce
        api.d3Force('global-gravity', globalGravityForce as unknown as object)
      }
      chargeForce?.strength?.(-repulsion)
      // Keep link force as topology constraint; gravity slider now controls global center pull.
      linkForce?.strength?.(0.08)
      linkForce?.distance?.(70)
      linkForce?.iterations?.(2)
      if (typeof api.d3ReheatSimulation === 'function') api.d3ReheatSimulation()
    } catch {
      // Keep 3D graph alive even if force-engine tuning fails.
    }
  }, [useForceGraph3D, synced3DRepulsionPercent, synced3DGravity])

  useEffect(() => {
    if (!useLegacyProjection3D || !chartReady) return
    let rafId = 0
    const tick = () => {
      const av = projectionAngularVelRef.current
      if (Math.abs(av.x) > 1e-5 || Math.abs(av.y) > 1e-5) {
        const curr = projectionInteractionQuatRef.current
        const right = rotateVecByQuat({ x: 1, y: 0, z: 0 }, curr)
        const qYaw = quatFromAxisAngle(0, 1, 0, av.y)
        const qPitch = quatFromAxisAngle(right.x, right.y, right.z, av.x)
        projectionInteractionQuatRef.current = quatMul(qPitch, quatMul(qYaw, curr))
        av.x *= 0.92
        av.y *= 0.92
      }
      setPhysicsFrame((prev) => (prev >= 1000000 ? 0 : prev + 1))
      rafId = window.requestAnimationFrame(tick)
    }
    rafId = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(rafId)
  }, [useLegacyProjection3D, chartReady])

  useEffect(() => {
    if (!chartReady || !useLegacyProjection3D) return
    const chart = chartInstRef.current
    if (!chart) return
    const zr = chart.getZr()
    const onMouseDown = (evt: unknown) => {
      const e = evt as { offsetX?: number; offsetY?: number; event?: MouseEvent }
      if ((e.event?.button ?? 0) !== 0) return
      projectionDragStateRef.current = {
        active: true,
        x: e.offsetX ?? 0,
        y: e.offsetY ?? 0,
      }
    }
    const onMouseMove = (evt: unknown) => {
      const drag = projectionDragStateRef.current
      if (!drag.active) return
      const e = evt as { offsetX?: number; offsetY?: number }
      const x = e.offsetX ?? drag.x
      const y = e.offsetY ?? drag.y
      const dx = x - drag.x
      const dy = y - drag.y
      drag.x = x
      drag.y = y
      const yaw = dx * 0.0045
      const pitch = -dy * 0.0045
      const curr = projectionInteractionQuatRef.current
      const right = rotateVecByQuat({ x: 1, y: 0, z: 0 }, curr)
      const qYaw = quatFromAxisAngle(0, 1, 0, yaw)
      const qPitch = quatFromAxisAngle(right.x, right.y, right.z, pitch)
      projectionInteractionQuatRef.current = quatMul(qPitch, quatMul(qYaw, curr))
      projectionAngularVelRef.current.x = projectionAngularVelRef.current.x * 0.35 + pitch * 0.65
      projectionAngularVelRef.current.y = projectionAngularVelRef.current.y * 0.35 + yaw * 0.65
      setPhysicsFrame((prev) => (prev >= 1000000 ? 0 : prev + 1))
    }
    const onMouseUp = () => {
      projectionDragStateRef.current.active = false
    }
    zr.on('mousedown', onMouseDown)
    zr.on('mousemove', onMouseMove)
    zr.on('mouseup', onMouseUp)
    zr.on('globalout', onMouseUp)
    return () => {
      zr.off('mousedown', onMouseDown)
      zr.off('mousemove', onMouseMove)
      zr.off('mouseup', onMouseUp)
      zr.off('globalout', onMouseUp)
      projectionDragStateRef.current.active = false
    }
  }, [chartReady, useLegacyProjection3D])

  useEffect(() => {
    // Reset accumulated roam transform when switching render modes,
    // otherwise projection mode may look off-center from previous pan/zoom state.
    chartInstRef.current?.clear()
    projectionDragStateRef.current.active = false
    if (!useLegacyProjection3D) {
      projectionAngularVelRef.current = { x: 0, y: 0 }
    }
  }, [useLegacyProjection3D])

  useEffect(() => {
    if (!useLegacyProjection3D) return
    const basisQuat = quatFromAxisAngle(1, 0, 0, -Math.PI / 2)
    const sliderQuat = quatFromEulerDeg(projectionRotateX, projectionRotateY, projectionRotateZ)
    projectionInteractionQuatRef.current = quatMul(sliderQuat, basisQuat)
    projectionAngularVelRef.current = { x: 0, y: 0 }
  }, [useLegacyProjection3D, graphKind, projectionRotateX, projectionRotateY, projectionRotateZ])

  const nodeAllElements = useMemo(() => buildNodeElements(selectedNode), [selectedNode])
  const nodeElementGroups = useMemo(() => {
    const grouped = new Map<string, NodeElementItem[]>()
    nodeAllElements.forEach((item) => {
      const bucket = grouped.get(item.label) || []
      bucket.push(item)
      grouped.set(item.label, bucket)
    })
    return Array.from(grouped.entries())
      .map(([label, items]) => ({
        label,
        items,
      }))
      .sort((a, b) => b.items.length - a.items.length)
  }, [nodeAllElements])
  const relationGroups = useMemo(() => {
    if (!selectedNodeContext?.relationItems.length) return []
    const grouped = new Map<string, NodeGraphContext['relationItems']>()
    selectedNodeContext.relationItems.forEach((item) => {
      const bucket = grouped.get(item.relation) || []
      bucket.push(item)
      grouped.set(item.relation, bucket)
    })
    return Array.from(grouped.entries())
      .map(([relation, items]) => ({ relation, items }))
      .sort((a, b) => b.items.length - a.items.length)
  }, [selectedNodeContext])
  const relationGroupOpenResolved = useMemo(() => {
    if (!relationGroups.length) return relationGroupOpen
    if (Object.keys(relationGroupOpen).length) return relationGroupOpen
    return { [relationGroups[0].relation]: true }
  }, [relationGroups, relationGroupOpen])
  const allRelationGroupsOpen = relationGroups.length > 0 && relationGroups.every((group) => relationGroupOpenResolved[group.relation])

  useEffect(() => {
    const onResize = () => chartInstRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [hoverNodeKeyRef, setHoverNodeKey])

  useEffect(() => {
    if (!chartRef.current) return
    const chartElement = chartRef.current
    const preventContextMenu = (event: MouseEvent) => event.preventDefault()
    chartElement.addEventListener('contextmenu', preventContextMenu)
    return () => chartElement.removeEventListener('contextmenu', preventContextMenu)
  }, [hoverNodeKeyRef, setHoverNodeKey])

  useEffect(() => {
    const onWindowResize = () => {
      setIsCompactViewport(window.innerWidth <= 980)
      setControlPanelWidth((prev) => clampControlPanelWidth(prev, window.innerWidth))
    }
    onWindowResize()
    window.addEventListener('resize', onWindowResize)
    return () => window.removeEventListener('resize', onWindowResize)
  }, [
    selectionEnabledRef,
    selectedNodeKeysRef,
    setManualSelectedNodeKeys,
    setManualDeselectedNodeKeys,
  ])

  const clearTransientInteractionState = useCallback(() => {
    dragFocusNodeKeyRef.current = null
    forceHoverPendingKeyRef.current = null
    if (forceHoverRafRef.current != null) {
      window.cancelAnimationFrame(forceHoverRafRef.current)
      forceHoverRafRef.current = null
    }
    if (hoverNodeKeyRef.current != null) {
      hoverNodeKeyRef.current = null
      setHoverNodeKey(null)
    }
    projectionDragStateRef.current = { active: false, x: 0, y: 0 }
    nodeCardDragRef.current = { active: false, offsetX: 0, offsetY: 0 }
    nodeCardHoldActiveRef.current = false
    nodeCardHoldTriggeredRef.current = false
    if (nodeCardHoldTimerRef.current != null) {
      window.clearTimeout(nodeCardHoldTimerRef.current)
      nodeCardHoldTimerRef.current = null
    }
    if (nodeDragHoldTimerRef.current != null) {
      window.clearTimeout(nodeDragHoldTimerRef.current)
      nodeDragHoldTimerRef.current = null
    }
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }, [hoverNodeKeyRef, setHoverNodeKey])

  const scheduleForceHoverNodeKey = useCallback((nextKey: string | null) => {
    const normalized = nextKey ? String(nextKey).trim() : ''
    const next = normalized || null
    forceHoverPendingKeyRef.current = next
    if (forceHoverRafRef.current != null) return
    forceHoverRafRef.current = window.requestAnimationFrame(() => {
      forceHoverRafRef.current = null
      const pending = forceHoverPendingKeyRef.current || null
      forceHoverPendingKeyRef.current = null
      if (hoverNodeKeyRef.current === pending) return
      hoverNodeKeyRef.current = pending
      setHoverNodeKey(pending)
    })
  }, [hoverNodeKeyRef, setHoverNodeKey])

  const clearAutoFocusState = useCallback(() => {
    dragFocusNodeKeyRef.current = null
    forceHoverPendingKeyRef.current = null
    if (forceHoverRafRef.current != null) {
      window.cancelAnimationFrame(forceHoverRafRef.current)
      forceHoverRafRef.current = null
    }
    if (hoverNodeKeyRef.current != null) {
      hoverNodeKeyRef.current = null
      setHoverNodeKey(null)
    }
  }, [hoverNodeKeyRef, setHoverNodeKey])

  const toggleForceNodeSelectionByKey = useCallback((key: string) => {
    if (!selectionEnabledRef.current || !key) return
    const currentlySelected = selectedNodeKeysRef.current.has(key)
    if (currentlySelected) {
      setManualSelectedNodeKeys((prev) => {
        if (!prev.has(key)) return prev
        const next = new Set(prev)
        next.delete(key)
        return next
      })
      setManualDeselectedNodeKeys((prev) => {
        if (prev.has(key)) return prev
        const next = new Set(prev)
        next.add(key)
        return next
      })
      return
    }
    setManualDeselectedNodeKeys((prev) => {
      if (!prev.has(key)) return prev
      const next = new Set(prev)
      next.delete(key)
      return next
    })
    setManualSelectedNodeKeys((prev) => {
      if (prev.has(key)) return prev
      const next = new Set(prev)
      next.add(key)
      return next
    })
  }, [
    selectionEnabledRef,
    selectedNodeKeysRef,
    setManualSelectedNodeKeys,
    setManualDeselectedNodeKeys,
  ])

  const toggleRadiationSelectionCenterByKey = useCallback((key: string) => {
    if (!selectionEnabledRef.current || !key) return
    const now = Date.now()
    if (rightToggleDedupeRef.current.key === key && now - rightToggleDedupeRef.current.ts <= RIGHT_TOGGLE_DEDUPE_MS) {
      return
    }
    rightToggleDedupeRef.current = { key, ts: now }
    setRadiationSelectionByCenter((prev) => {
      const enabled = Boolean(prev[key])
      const next = { ...prev }
      if (enabled) {
        delete next[key]
      } else {
        next[key] = true
      }
      return next
    })
    // If center was manually deselected before, remove the block so one-hop mode can take effect.
    setManualDeselectedNodeKeys((prev) => {
      if (!prev.has(key)) return prev
      const next = new Set(prev)
      next.delete(key)
      return next
    })
  }, [
    selectionEnabledRef,
    setManualDeselectedNodeKeys,
    setRadiationSelectionByCenter,
  ])

  useEffect(() => {
    const onFullscreenChange = () => {
      const active = document.fullscreenElement === fullscreenWrapRef.current
      if (!active && fullscreenWantedRef.current) {
        setIsFullscreen(true)
      } else {
        setIsFullscreen(active)
      }
      clearTransientInteractionState()
      chartInstRef.current?.resize()
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange)
    }
  }, [clearTransientInteractionState])

  useEffect(() => {
    clearTransientInteractionState()
  }, [renderMode, projectionEngine, clearTransientInteractionState])

  useEffect(() => {
    const wrap = fullscreenWrapRef.current
    if (!wrap) return
    const observer = new ResizeObserver(() => {
      chartInstRef.current?.resize()
    })
    observer.observe(wrap)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!chartReady || useForceGraph3D) return
    const chart = chartInstRef.current
    if (!chart) return
    const raf = window.requestAnimationFrame(() => {
      chart.resize()
    })
    return () => window.cancelAnimationFrame(raf)
  }, [isFullscreen, chartReady, useForceGraph3D])

  useEffect(() => {
    setHoverNodeKey(null)
    setManualDeselectedNodeKeys(new Set())
    setRadiationSelectionByCenter({})
  }, [variant, setHoverNodeKey, setManualDeselectedNodeKeys, setRadiationSelectionByCenter])

  useEffect(() => {
    if (useForceGraph3D) {
      if (chartInstRef.current) {
        chartInstRef.current.dispose()
        chartInstRef.current = null
      }
      return
    }
    if (!chartRef.current) return
    let canceled = false
    const ensureChart = async () => {
      if (!echartsLibRef.current) {
        echartsLibRef.current = await loadGraphEchartsCore()
      }
      if (canceled || !chartRef.current) return
      if (!chartInstRef.current) {
        chartInstRef.current = echartsLibRef.current.init(chartRef.current, undefined, {
          renderer: 'canvas',
          useDirtyRect: true,
          devicePixelRatio: graphCanvasPixelRatio(),
        })
        const syncNodeCardFromParams = (
          params: { event?: { event?: MouseEvent } },
          node: GraphNodeItem,
        ) => {
          const wrap = fullscreenWrapRef.current || chartRef.current
          const mouseEvent = params.event?.event
          if (wrap && mouseEvent) {
            const rect = wrap.getBoundingClientRect()
            const maxWidth = Math.max(220, rect.width - NODE_CARD_MARGIN * 2)
            const width = Math.min(NODE_CARD_WIDTH, maxWidth)
            const targetLeft = mouseEvent.clientX - rect.left + NODE_CARD_POINTER_OFFSET
            const targetTop = mouseEvent.clientY - rect.top + NODE_CARD_POINTER_OFFSET
            const maxLeft = Math.max(NODE_CARD_MARGIN, rect.width - width - NODE_CARD_MARGIN)
            const maxTop = Math.max(NODE_CARD_MARGIN, rect.height - NODE_CARD_MARGIN * 4)
            setNodeCardAnchor({
              left: Math.min(maxLeft, Math.max(NODE_CARD_MARGIN, targetLeft)),
              top: Math.min(maxTop, Math.max(NODE_CARD_MARGIN, targetTop)),
              width,
            })
          }
          setSelectedNode(node)
        }
        const toggleNodeSelectionBoolean = (key: string) => {
          const currentlySelected = selectedNodeKeysRef.current.has(key)
          if (currentlySelected) {
            setManualSelectedNodeKeys((prev) => {
              if (!prev.has(key)) return prev
              const next = new Set(prev)
              next.delete(key)
              return next
            })
            setManualDeselectedNodeKeys((prev) => {
              if (prev.has(key)) return prev
              const next = new Set(prev)
              next.add(key)
              return next
            })
          } else {
            setManualDeselectedNodeKeys((prev) => {
              if (!prev.has(key)) return prev
              const next = new Set(prev)
              next.delete(key)
              return next
            })
            setManualSelectedNodeKeys((prev) => {
              if (prev.has(key)) return prev
              const next = new Set(prev)
              next.add(key)
              return next
            })
          }
        }
        const triggerNodeDragCapturedFx = () => {
          setNodeDragCapturedFx(false)
          window.requestAnimationFrame(() => setNodeDragCapturedFx(true))
          if (nodeDragFxTimerRef.current != null) window.clearTimeout(nodeDragFxTimerRef.current)
          nodeDragFxTimerRef.current = window.setTimeout(() => {
            setNodeDragCapturedFx(false)
            nodeDragFxTimerRef.current = null
          }, 900)
        }
        const clearNodeCardHold = () => {
          nodeCardHoldActiveRef.current = false
          if (nodeCardHoldTimerRef.current != null) {
            window.clearTimeout(nodeCardHoldTimerRef.current)
            nodeCardHoldTimerRef.current = null
          }
        }
        const armNodeCardHold = (
          params: { event?: { event?: MouseEvent } },
          node: GraphNodeItem,
        ) => {
          clearNodeCardHold()
          nodeCardHoldActiveRef.current = true
          nodeCardHoldTriggeredRef.current = false
          nodeCardHoldTimerRef.current = window.setTimeout(() => {
            if (!nodeCardHoldActiveRef.current) return
            syncNodeCardFromParams(params, node)
            nodeCardHoldTriggeredRef.current = true
            clearNodeCardHold()
          }, NODE_CARD_LONG_PRESS_MS)
        }
        const setNodeDragUnlocked = (next: boolean) => {
          if (nodeDragUnlockedRef.current === next) return
          nodeDragUnlockedRef.current = next
          chartInstRef.current?.setOption(
            { series: [{ id: 'graph-main', draggable: next || !(selectionEnabledRef.current && renderModeRef.current === '2d') }] },
            { lazyUpdate: true },
          )
        }
        const clearNodeDragHold = () => {
          if (nodeDragHoldTimerRef.current != null) {
            window.clearTimeout(nodeDragHoldTimerRef.current)
            nodeDragHoldTimerRef.current = null
          }
        }
        const armNodeDragHold = () => {
          clearNodeDragHold()
          nodeDragHoldTimerRef.current = window.setTimeout(() => {
            setNodeDragUnlocked(true)
            triggerNodeDragCapturedFx()
          }, NODE_CARD_LONG_PRESS_MS)
        }
        const resolveNodeFromEventParams = (params: {
          dataType?: string
          data?: unknown
          dataIndex?: number
          seriesIndex?: number
          name?: string
          value?: unknown
        }) => {
          if (params.dataType && params.dataType !== 'node') return null
          const data = params.data as
            | { id?: string; value?: { id?: string | number; type?: string } }
            | undefined
          const tryResolveByKey = (candidate: string) => {
            const key = String(candidate || '').trim()
            if (!key) return null
            const node = nodeLookupRef.current[key]
            return node ? { node, key } : null
          }
          const tryResolveByValue = (idRaw: unknown, typeRaw: unknown) => {
            const valueId = String(idRaw ?? '').trim()
            const valueType = String(typeRaw || '').trim()
            if (!valueId || !valueType) return null
            const composite = `${normalizeNodeType(valueType)}:${valueId}`
            return tryResolveByKey(composite)
          }
          const directCandidates = [
            String(data?.id || '').trim(),
            String(params.name || '').trim(),
          ]
          for (const candidate of directCandidates) {
            const resolved = tryResolveByKey(candidate)
            if (resolved) return resolved
          }
          const byDataValue = tryResolveByValue(data?.value?.id, data?.value?.type)
          if (byDataValue) return byDataValue
          const byParamsValue = (() => {
            const val = params.value as { id?: string | number; type?: string } | undefined
            return tryResolveByValue(val?.id, val?.type)
          })()
          if (byParamsValue) return byParamsValue
          if (typeof params.dataIndex === 'number' && params.dataIndex >= 0) {
            const option = chartInstRef.current?.getOption() as { series?: Array<{ id?: string; data?: Array<{ id?: string; value?: { id?: string | number; type?: string } }> }> } | undefined
            const seriesList = Array.isArray(option?.series) ? option.series : []
            const fallbackSeriesIndex = seriesList.findIndex((item) => item?.id === 'graph-main')
            const resolvedSeriesIndex = typeof params.seriesIndex === 'number'
              ? params.seriesIndex
              : (fallbackSeriesIndex >= 0 ? fallbackSeriesIndex : 0)
            const seriesData = seriesList[resolvedSeriesIndex]?.data
            const indexed = Array.isArray(seriesData) ? seriesData[params.dataIndex] : undefined
            const byIndexedId = tryResolveByKey(String(indexed?.id || '').trim())
            if (byIndexedId) return byIndexedId
            const byIndexedValue = tryResolveByValue(indexed?.value?.id, indexed?.value?.type)
            if (byIndexedValue) return byIndexedValue
          }
          const looseId = String(data?.id || params.name || '').trim()
          if (looseId) {
            const matchedKeys = Object.keys(nodeLookupRef.current).filter((key) => key.endsWith(`:${looseId}`))
            if (matchedKeys.length === 1) {
              const matched = matchedKeys[0]
              const node = nodeLookupRef.current[matched]
              if (node) return { node, key: matched }
            }
          }
          return null
        }
        const handleRightToggleInSelection2D = (params: { dataType?: string; data?: unknown }) => {
          if (!selectionEnabledRef.current) return
          if (renderModeRef.current !== '2d') return
          const resolved = resolveNodeFromEventParams(params)
          if (!resolved) return
          const { key } = resolved
          toggleRadiationSelectionCenterByKey(key)
        }
        const isRightLike = (mouseEvent?: MouseEvent) => {
          if (!mouseEvent) return false
          return mouseEvent.button === 2 || (mouseEvent.button === 0 && mouseEvent.ctrlKey)
        }

        chartInstRef.current.on('click', (params) => {
          const mouseEvent = (params as { event?: { event?: MouseEvent } }).event?.event
          const resolved = resolveNodeFromEventParams(params as { dataType?: string; data?: unknown })
          if (!resolved) return
          const { node, key } = resolved
          if (!selectionEnabledRef.current || renderModeRef.current !== '2d') {
            syncNodeCardFromParams(params as { event?: { event?: MouseEvent } }, node)
          }
          if (!selectionEnabledRef.current) return
          if (renderModeRef.current === '2d') {
            if (suppressNextClickToggleRef.current) {
              suppressNextClickToggleRef.current = false
              return
            }
            if ((mouseEvent?.button ?? 0) !== 0 || Boolean(mouseEvent?.ctrlKey)) return
            if (nodeCardHoldTriggeredRef.current) {
              nodeCardHoldTriggeredRef.current = false
              return
            }
          }
          toggleNodeSelectionBoolean(key)
        })
        chartInstRef.current.on('dblclick', (params) => {
          void params
        })
        chartInstRef.current.on('contextmenu', (params) => {
          clearNodeCardHold()
          clearNodeDragHold()
          setNodeDragUnlocked(false)
          handleRightToggleInSelection2D(params as { dataType?: string; data?: unknown })
        })
        chartInstRef.current.on('mouseover', (params) => {
          if (!autoFocusEnabledRef.current) return
          if (params.dataType !== 'node') return
          const mouseEvent = (params as { event?: { event?: MouseEvent } }).event?.event
          if (dragFocusNodeKeyRef.current && (mouseEvent?.buttons ?? 0) > 0) {
            // During drag, keep focus pinned to the drag-origin node.
            setHoverNodeKey(dragFocusNodeKeyRef.current)
            return
          }
          if (dragFocusNodeKeyRef.current && (mouseEvent?.buttons ?? 0) === 0) {
            dragFocusNodeKeyRef.current = null
          }
          const nodeId = params.data && typeof params.data === 'object' && 'id' in params.data
            ? String(params.data.id || '')
            : ''
          if (!nodeId) return
          setHoverNodeKey(nodeId)
        })
        chartInstRef.current.on('mousedown', (params) => {
          const mouseEvent = (params as { event?: { event?: MouseEvent } }).event?.event
          const resolved = resolveNodeFromEventParams(params as { dataType?: string; data?: unknown })
          if (!resolved) return
          const { node, key } = resolved
          if (selectionEnabledRef.current && renderModeRef.current === '2d') {
            const rightLike = isRightLike(mouseEvent)
            if (rightLike && node) {
              handleRightToggleInSelection2D(params as { dataType?: string; data?: unknown })
              suppressNextClickToggleRef.current = true
              clearNodeCardHold()
              clearNodeDragHold()
              setNodeDragUnlocked(false)
            } else if ((mouseEvent?.button ?? 0) === 0 && !mouseEvent?.ctrlKey && node) {
              armNodeCardHold(params as { event?: { event?: MouseEvent } }, node)
              armNodeDragHold()
            } else {
              clearNodeCardHold()
              clearNodeDragHold()
              setNodeDragUnlocked(false)
            }
          } else {
            clearNodeCardHold()
            clearNodeDragHold()
            setNodeDragUnlocked(false)
          }
          if (!autoFocusEnabledRef.current) return
          dragFocusNodeKeyRef.current = key
          setHoverNodeKey(key)
        })
        chartInstRef.current.on('mouseup', (params) => {
          clearNodeCardHold()
          clearNodeDragHold()
          setNodeDragUnlocked(false)
          if (!autoFocusEnabledRef.current) return
          if (dragFocusNodeKeyRef.current == null) return
          dragFocusNodeKeyRef.current = null
          if (params.dataType === 'node') {
            const nodeId = params.data && typeof params.data === 'object' && 'id' in params.data
              ? String(params.data.id || '')
              : ''
            setHoverNodeKey(nodeId || null)
            return
          }
          setHoverNodeKey(null)
        })
        chartInstRef.current.on('mouseout', (params) => {
          clearNodeCardHold()
          clearNodeDragHold()
          setNodeDragUnlocked(false)
          if (!autoFocusEnabledRef.current) return
          const mouseEvent = (params as { event?: { event?: MouseEvent } }).event?.event
          if (dragFocusNodeKeyRef.current && (mouseEvent?.buttons ?? 0) === 0) {
            dragFocusNodeKeyRef.current = null
          }
          if (dragFocusNodeKeyRef.current) return
          if (params.dataType === 'node') {
            setHoverNodeKey(null)
          }
        })
        chartInstRef.current.on('mousemove', (params) => {
          const mouseEvent = (params as { event?: { event?: MouseEvent } }).event?.event
          if ((mouseEvent?.buttons ?? 0) === 0) {
            clearNodeCardHold()
            clearNodeDragHold()
            setNodeDragUnlocked(false)
          }
          if (!autoFocusEnabledRef.current) return
          if (dragFocusNodeKeyRef.current && (mouseEvent?.buttons ?? 0) === 0) {
            dragFocusNodeKeyRef.current = null
          }
          if (dragFocusNodeKeyRef.current) {
            setHoverNodeKey(dragFocusNodeKeyRef.current)
            return
          }
          if (params.dataType !== 'node') {
            setHoverNodeKey(null)
          }
        })
        chartInstRef.current.on('globalout', () => {
          clearNodeCardHold()
          clearNodeDragHold()
          setNodeDragUnlocked(false)
          if (!autoFocusEnabledRef.current) return
          dragFocusNodeKeyRef.current = null
          setHoverNodeKey(null)
        })
      }
      if (canceled) return
      setChartReady(true)
    }
    void ensureChart()
    return () => {
      canceled = true
      if (nodeDragHoldTimerRef.current != null) {
        window.clearTimeout(nodeDragHoldTimerRef.current)
        nodeDragHoldTimerRef.current = null
      }
      nodeDragUnlockedRef.current = false
      if (chartInstRef.current) {
        chartInstRef.current.dispose()
        chartInstRef.current = null
      }
      dragFocusNodeKeyRef.current = null
    }
  }, [
    variant,
    useForceGraph3D,
    toggleRadiationSelectionCenterByKey,
    autoFocusEnabledRef,
    renderModeRef,
    selectedNodeKeysRef,
    selectionEnabledRef,
    setHoverNodeKey,
    setManualDeselectedNodeKeys,
    setManualSelectedNodeKeys,
  ])

  useEffect(() => {
    if (!chartReady) return
    const chart = chartInstRef.current
    if (!chart) return
    const { nodes, visibleNodes, centralityScoreMap, neighborTightnessScoreMap, centralityMinScore, centralityRangeScore, neighborMinScore, neighborRangeScore } = topology
    nodeLookupRef.current = Object.fromEntries(nodes.map((n) => [nodeKey(n), n]))
    const prevPos2D = { ...nodePositionRef.current }
    let currentCenter: [string | number, string | number] | undefined
    let currentZoom: number | undefined
    try {
      const current = chart.getOption() as {
        series?: Array<{
          data?: Array<{ id?: string; x?: number; y?: number }>
          center?: [string | number, string | number]
          zoom?: number
        }>
      }
      const currentSeries = current?.series?.[0]
      const currentData = currentSeries?.data || []
      currentData.forEach((item) => {
        const id = String(item?.id || '')
        if (!id) return
        prevPos2D[id] = { x: item.x, y: item.y }
      })
      if (renderMode !== 'projection3d') {
        if (Array.isArray(currentSeries?.center) && currentSeries.center.length === 2) {
          currentCenter = [currentSeries.center[0], currentSeries.center[1]]
        }
        if (typeof currentSeries?.zoom === 'number' && Number.isFinite(currentSeries.zoom)) {
          currentZoom = currentSeries.zoom
        }
      }
    } catch {
      // keep previous cached positions
    }
    const shouldShowNodeLabel =
      visualApplied.showLabel && visibleNodes.length <= NODE_LABEL_MAX_VISIBLE_NODES
    const shouldShowEdgeLabel = false
    const autoFocusSet = new Set<string>()
    // In 3D mode, card selection should not become autofocus center.
    const focusCenterKey = autoFocusEnabled && !selectedNode ? hoverNodeKey : null
    if (focusCenterKey && topology.visibleNodeKeys.has(focusCenterKey)) {
      collectFocusNodeKeys(focusCenterKey, adjacencyConnectedMap).forEach((item) => autoFocusSet.add(item))
    }
    const enablePinnedOnlyDim = selectionPinned && selectedNodeKeys.size > 0
    const enableAutoFocusDim = autoFocusEnabled && autoFocusSet.size > 0

    const seriesNodes = visibleNodes.map((node) => {
      const key = nodeKey(node)
      const normalizedType = normalizeNodeType(node.type)
      const rawSymbol = resolveNodeSymbol(normalizedType)
      const centralityScore = centralityScoreMap.get(key) || 0
      const neighborTightnessScore = neighborTightnessScoreMap.get(key) || 0
      const baseSize = computeNodeVisualSize(
        centralityScore,
        centralityMinScore,
        centralityRangeScore,
        neighborTightnessScore,
        neighborMinScore,
        neighborRangeScore,
        visualApplied.nodeScale,
        visualApplied.nodeContrastCentral,
        visualApplied.nodeContrastNeighbor,
      )
      const size = Math.max(NODE_SIZE_MIN_APPROX, baseSize * symbolSizeGain(rawSymbol))
      const show = shouldShowNodeLabel && size >= NODE_LABEL_MIN_SIZE_PX
      const selected = selectedNodeKeys.has(key)
      const dimByPinnedOnly = enablePinnedOnlyDim && !selected
      const dimByAutoFocus = enableAutoFocusDim && !autoFocusSet.has(key)
      const dimByFocus = enablePinnedOnlyDim ? dimByPinnedOnly : dimByAutoFocus
      const effectiveDimByFocus = dimByFocus
      const nodeColor = nodeTypeColor[normalizedType] || '#7dd3fc'
      const { r, g, b } = hexToRgb(nodeColor)
      const nodeAlphaT = Math.max(0, Math.min(1, visualApplied.nodeAlpha / 100))
      const nodeFillAlpha = selected ? Math.min(1, nodeAlphaT + 0.08) : nodeAlphaT
      const borderAlpha = effectiveDimByFocus ? 0.2 : Math.max(0.28, Math.min(1, nodeFillAlpha + 0.2))
      const borderWidth = rawSymbol.startsWith('empty')
        ? computeEmptyNodeBorderWidth(size, selected)
        : (selected ? 1.25 : 1)
      return {
        id: key,
        name: nodeName(node),
        value: { id: node.id, type: normalizedType, name: nodeName(node) },
        symbol: rawSymbol === 'convexStar' ? TOPIC_TAG_CONVEX_SYMBOL_PATH : toGraphSymbol(rawSymbol),
        x: prevPos2D[key]?.x,
        y: prevPos2D[key]?.y,
        symbolSize: effectiveDimByFocus ? Math.max(NODE_SIZE_MIN_APPROX, size * 0.88) : size,
        itemStyle: {
          opacity: effectiveDimByFocus ? 0.12 : 1,
          color: rawSymbol.startsWith('empty')
            ? `rgba(255, 255, 255, ${effectiveDimByFocus ? 0.08 : nodeFillAlpha})`
            : `rgba(${r}, ${g}, ${b}, ${effectiveDimByFocus ? 0.08 : nodeFillAlpha})`,
          borderColor: `rgba(${r}, ${g}, ${b}, ${borderAlpha})`,
          borderWidth,
          shadowBlur: 0,
          shadowColor: selected ? 'rgba(250, 204, 21, 0.45)' : 'transparent',
        },
        label: {
          show: show && !effectiveDimByFocus,
          color: '#dbeafe',
          fontSize: 11,
          formatter: () => {
            const raw = nodeName(node)
            return raw.length > 22 ? `${raw.slice(0, 22)}…` : raw
          },
        },
      }
    })
    const seriesEdges = visibleEdges.flatMap((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return []
      const fromKey = resolved.fromKey
      const toKey = resolved.toKey
      const fromSelected = selectedNodeKeys.has(fromKey)
      const toSelected = selectedNodeKeys.has(toKey)
      const dimByPinnedOnly = enablePinnedOnlyDim && !(fromSelected && toSelected)
      const dimByAutoFocus =
        enableAutoFocusDim &&
        !(autoFocusSet.has(fromKey) && autoFocusSet.has(toKey))
      const dimByFocus = enablePinnedOnlyDim ? dimByPinnedOnly : dimByAutoFocus
      const style = edgeLegendItemByKey.get(edgeLegendKey(edge))
      const profile = graphEdgeProfile(edge, edgeStyleBinding)
      const strokeKind = style?.strokeKind || profile.strokeKind
      const lineType = style?.lineType || profile.lineType
      const edgeColor = style?.color || '#7dd3fc'
      const { r, g, b } = hexToRgb(edgeColor)
      const edgeAlphaT = Math.max(0, Math.min(1, visualApplied.edgeAlpha / 100))
      const widthFactor = Math.max(0, Math.min(2.4, visualApplied.edgeWidth / 100))
      const symbolScale = Math.max(0, Math.min(2.2, widthFactor))
      const scaledSymbolSize: [number, number] = [
        Math.max(0, profile.symbolSize[0] * symbolScale),
        Math.max(0, profile.symbolSize[1] * symbolScale),
      ]
      const hideEdgeSymbol = scaledSymbolSize[1] < 2
      const baseCurveness = edge.type === 'POLICY_RELATION' ? 0.18 : profile.curveness
      const resolvedEdgeAlpha = edgeAlphaT
      const baseColor = dimByFocus
        ? 'rgba(125, 211, 252, 0.04)'
        : `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, resolvedEdgeAlpha))})`
      const baseWidth = dimByFocus ? 0.7 : Math.max(0, profile.width * widthFactor)
      const baseLine = {
        source: fromKey,
        target: toKey,
        value: edge,
        symbol: hideEdgeSymbol ? (['none', 'none'] as [EdgeSymbolName, EdgeSymbolName]) : profile.symbol,
        symbolSize: hideEdgeSymbol ? ([0, 0] as [number, number]) : scaledSymbolSize,
        lineStyle: {
          color: baseColor,
          width: baseWidth,
          type: edgeLinePattern(lineType),
          curveness: baseCurveness,
        },
        label: {
          show: !dimByFocus && shouldShowEdgeLabel && Boolean(edge.predicate),
          formatter: edge.predicate || '',
          color: 'rgba(147, 197, 253, 0.8)',
        },
      }
      if (strokeKind !== 'double') return [baseLine]
      // 双线近似：同源同目标叠加两条微偏移曲线。
      return [
        {
          ...baseLine,
          lineStyle: {
            ...baseLine.lineStyle,
            width: Math.max(0, baseWidth - 0.35),
            curveness: baseCurveness + 0.06,
          },
        },
        {
          ...baseLine,
          lineStyle: {
            ...baseLine.lineStyle,
            width: Math.max(0, baseWidth - 0.35),
            curveness: -Math.abs(baseCurveness + 0.06),
          },
          symbol: ['none', 'none'] as [EdgeSymbolName, EdgeSymbolName],
          symbolSize: [0, 0] as [number, number],
        },
      ]
    })

    const rendererResult = useLegacyProjection3D
      ? (() => {
        const projectionEdges = visibleEdges
          .map((edge) => {
            const resolved = topology.edgeResolvedKeyMap.get(edge)
            if (!resolved) return null
            return { from: resolved.fromKey, to: resolved.toKey }
          })
          .filter((item): item is { from: string; to: string } => Boolean(item))
        const applied = applyRendererProjection3D(
          seriesNodes as RenderNode[],
          projectionEdges,
          projectionPhysicsRef.current,
          {
            rotateXDeg: projectionRotateX,
            rotateYDeg: projectionRotateY,
            rotateZDeg: projectionRotateZ,
            repulsionPercent: synced3DRepulsionPercent,
            interactionQuat: projectionInteractionQuatRef.current,
          },
        )
        projectionPhysicsRef.current = applied.physics
        return applied.render
      })()
      : applyRenderer2D(seriesNodes as RenderNode[])

    const seriesOption = {
      id: 'graph-main',
      type: 'graph',
      layout: rendererResult.series.layout,
      roam: true,
      draggable: renderMode === '2d' && selectionEnabled ? nodeDragUnlockedRef.current : true,
      center: currentCenter,
      zoom: currentZoom,
      hoverAnimation: false,
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
      animation: rendererResult.series.animation,
      animationDurationUpdate: rendererResult.series.animationDurationUpdate,
      animationEasingUpdate: rendererResult.series.animationEasingUpdate,
      progressive: 0,
      progressiveThreshold: 800,
      force: rendererResult.series.layout === 'force'
        ? {
          repulsion: visualApplied.repulsion,
          edgeLength: [55, 180],
          gravity: Math.max(0, Math.min(0.6, 0.1 * (visualApplied.gravityPercent / 100))),
          friction: 0.16,
          layoutAnimation: true,
        }
        : undefined,
      data: rendererResult.nodes,
      links: seriesEdges,
      labelLayout: { hideOverlap: true },
      lineStyle: { opacity: 0.85 },
      emphasis: {
        focus: 'none',
        scale: false,
      },
    }

    const option = {
        backgroundColor: '#030712',
        animationThreshold: 1000,
        hoverLayerThreshold: 1500,
        tooltip: {
          triggerOn: 'click',
          backgroundColor: 'rgba(2,6,23,0.92)',
          borderColor: '#334155',
          textStyle: { color: '#e2e8f0' },
          formatter(params: { dataType?: string; data?: { value?: { type?: string; name?: string } | GraphEdgeItem } }) {
            if (params.dataType === 'node') {
              const node = (params.data?.value || {}) as { type?: string; name?: string }
              return `${t('graphPage.field.type')}: ${node.type || '-'}<br/>${t('graphPage.field.name')}: ${node.name || '-'}`
            }
            if (params.dataType === 'edge') {
              const edge = (params.data?.value || {}) as GraphEdgeItem
              const classToken = String(edge.relation_class || '').trim().toLowerCase()
              const classLabel = classToken ? relationClassLabel(classToken) : ''
              const predicate = String(edge.predicate || '').trim()
              const profile = graphEdgeProfile(edge, edgeStyleBinding)
              return `${t('graphPage.tooltip.relation')}: ${edge.type || 'REL'}${classLabel ? `<br/>${t('graphPage.tooltip.class')}: ${classLabel}` : ''}${predicate ? `<br/>${t('graphPage.tooltip.predicate')}: ${predicate}` : ''}<br/>${t('graphPage.tooltip.stroke')}: ${edgeStrokeLabel(profile.strokeKind)} · ${edgeLineTypeLabel(profile.lineType)}`
            }
            return ''
          },
        },
        series: [seriesOption],
      }

    chart.setOption(
      option,
      { lazyUpdate: true },
    )
    if (rendererResult.cacheNodePositions) {
      const mergedPositions = { ...nodePositionRef.current }
      rendererResult.nodes.forEach((item) => {
        const id = String(item.id || '')
        if (!id) return
        mergedPositions[id] = {
          x: item.x as number | undefined,
          y: item.y as number | undefined,
        }
      })
      nodePositionRef.current = mergedPositions
    }
  }, [topology, visibleEdges, edgeLegendItemByKey, edgeStyleBinding, visualApplied, nodeTypeColor, graphKind, chartReady, isFullscreen, selectedNodeKeys, selectionPinned, adjacencyConnectedMap, hoverNodeKey, autoFocusEnabled, selectedNode, selectedNodeKey, renderMode, selectionEnabled, projectionRotateX, projectionRotateY, projectionRotateZ, synced3DRepulsionPercent, physicsFrame, projectionFrameEpoch, useLegacyProjection3D, useForceGraph3D, t, relationClassLabel, edgeStrokeLabel, edgeLineTypeLabel])

  const onControlResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = controlPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    const startX = event.clientX
    const startWidth = rect.width
    const onMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX
      const next = startWidth - deltaX
      setControlPanelWidth(clampControlPanelWidth(next, window.innerWidth))
    }
    const onEnd = () => {
      controlResizeRightRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const onControlResizeBottomStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = controlPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    const startY = event.clientY
    const startHeight = rect.height
    const onMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY
      const next = startHeight + deltaY
      setControlPanelHeight(clampFloatingPanelHeight(next, window.innerHeight))
    }
    const onEnd = () => {
      controlResizeBottomRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'row-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const onProjectionResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = projectionPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    const startX = event.clientX
    const startWidth = rect.width
    const onMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX
      const next = startWidth + deltaX
      setProjectionPanelWidth(clampFloatingPanelWidth(next, window.innerWidth))
    }
    const onEnd = () => {
      projectionResizeRightRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const onProjectionResizeBottomStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = projectionPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    const startY = event.clientY
    const startHeight = rect.height
    const onMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY
      const next = startHeight + deltaY
      setProjectionPanelHeight(clampFloatingPanelHeight(next, window.innerHeight))
    }
    const onEnd = () => {
      projectionResizeBottomRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'row-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const onLegendResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = legendPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    const startX = event.clientX
    const startWidth = rect.width
    const onMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX
      const next = startWidth + deltaX
      setLegendPanelWidth(clampFloatingPanelWidth(next, window.innerWidth))
    }
    const onEnd = () => {
      legendResizeRightRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const onLegendResizeBottomStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = legendPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    const startY = event.clientY
    const startHeight = rect.height
    const onMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY
      const next = startHeight + deltaY
      setLegendPanelHeight(clampFloatingPanelHeight(next, window.innerHeight))
    }
    const onEnd = () => {
      legendResizeBottomRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'row-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const onNodeCardDragStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (target?.closest('button')) return
    const wrap = fullscreenWrapRef.current || chartRef.current
    if (!wrap) return
    const rect = wrap.getBoundingClientRect()
    const maxWidth = Math.max(220, rect.width - NODE_CARD_MARGIN * 2)
    const width = Math.min(NODE_CARD_WIDTH, maxWidth)
    const current = nodeCardAnchor || {
      left: NODE_CARD_MARGIN,
      top: NODE_CARD_MARGIN,
      width,
    }
    nodeCardDragRef.current = {
      active: true,
      offsetX: event.clientX - current.left - rect.left,
      offsetY: event.clientY - current.top - rect.top,
    }
    const onMove = (moveEvent: MouseEvent) => {
      if (!nodeCardDragRef.current.active) return
      const maxLeft = Math.max(NODE_CARD_MARGIN, rect.width - width - NODE_CARD_MARGIN)
      const maxTop = Math.max(NODE_CARD_MARGIN, rect.height - NODE_CARD_MARGIN * 4)
      const nextLeft = moveEvent.clientX - rect.left - nodeCardDragRef.current.offsetX
      const nextTop = moveEvent.clientY - rect.top - nodeCardDragRef.current.offsetY
      setNodeCardAnchor({
        left: Math.min(maxLeft, Math.max(NODE_CARD_MARGIN, nextLeft)),
        top: Math.min(maxTop, Math.max(NODE_CARD_MARGIN, nextTop)),
        width,
      })
    }
    const onEnd = () => {
      nodeCardDragRef.current.active = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'grabbing'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const nodeCardStyle = useMemo(() => {
    if (!nodeCardAnchor) return undefined
    return {
      left: Math.round(nodeCardAnchor.left),
      top: Math.round(nodeCardAnchor.top),
      width: nodeCardAnchor.width,
    }
  }, [nodeCardAnchor])

  const handleForceNodeHover = useCallback((node: unknown) => {
    if (selectionEnabledRef.current || !autoFocusEnabledRef.current || selectedNodeOpenRef.current) {
      if (hoverNodeKeyRef.current) scheduleForceHoverNodeKey(null)
      return
    }
    if (!node) {
      scheduleForceHoverNodeKey(null)
      return
    }
    const n = node as { key?: string; id?: string }
    const key = String(n.key || n.id || '')
    scheduleForceHoverNodeKey(key || null)
  }, [scheduleForceHoverNodeKey, selectionEnabledRef, autoFocusEnabledRef, hoverNodeKeyRef])

  const handleForceNodeClick = useCallback((node: unknown, event: unknown) => {
    const nodeData = node as { key?: string; id?: string; rawNode?: GraphNodeItem }
    const key = String(nodeData.key || nodeData.id || '')
    const rawNode = nodeData.rawNode
    if (!key || !rawNode) return
    const mouseEvent = event as MouseEvent | undefined
    mouseEvent?.preventDefault?.()
    mouseEvent?.stopPropagation?.()
    lastForceNodeClickAtRef.current = Date.now()
    const wrap = fullscreenWrapRef.current || forceChartRef.current || chartRef.current
    if (wrap && mouseEvent) {
      const rect = wrap.getBoundingClientRect()
      const maxWidth = Math.max(220, rect.width - NODE_CARD_MARGIN * 2)
      const width = Math.min(NODE_CARD_WIDTH, maxWidth)
      const targetLeft = mouseEvent.clientX - rect.left + NODE_CARD_POINTER_OFFSET
      const targetTop = mouseEvent.clientY - rect.top + NODE_CARD_POINTER_OFFSET
      const maxLeft = Math.max(NODE_CARD_MARGIN, rect.width - width - NODE_CARD_MARGIN)
      const maxTop = Math.max(NODE_CARD_MARGIN, rect.height - NODE_CARD_MARGIN * 4)
      setNodeCardAnchor({
        left: Math.min(maxLeft, Math.max(NODE_CARD_MARGIN, targetLeft)),
        top: Math.min(maxTop, Math.max(NODE_CARD_MARGIN, targetTop)),
        width,
      })
    }
    setSelectedNode(rawNode)
    if (autoFocusEnabledRef.current) scheduleForceHoverNodeKey(null)
    // In selection mode, left click toggles selection directly.
    if (selectionEnabledRef.current) toggleForceNodeSelectionByKey(key)
  }, [scheduleForceHoverNodeKey, toggleForceNodeSelectionByKey, autoFocusEnabledRef, selectionEnabledRef, setNodeCardAnchor, setSelectedNode])

  const handleForceNodeRightClick = useCallback((node: unknown, event: unknown) => {
    const mouseEvent = event as MouseEvent | undefined
    mouseEvent?.preventDefault?.()
    mouseEvent?.stopPropagation?.()
    lastForceNodeClickAtRef.current = Date.now()
    const n = node as { key?: string; id?: string }
    const key = String(n.key || n.id || '')
    toggleRadiationSelectionCenterByKey(key)
  }, [toggleRadiationSelectionCenterByKey])

  const handleForceBackgroundClick = useCallback(() => {
    if (Date.now() - lastForceNodeClickAtRef.current < 180) return
    if (autoFocusEnabledRef.current) setHoverNodeKey(null)
  }, [autoFocusEnabledRef, setHoverNodeKey])

  const collectForce3DSceneStats = useCallback(() => {
    const api = forceGraphRef.current
    const scene = api?.scene?.()
    let meshCount = 0
    let nodeObjectCount = 0
    const nodeIds = new Set<string>()
    if (scene?.traverse) {
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) meshCount += 1
        if (obj?.userData?.__graphNodeObject) {
          nodeObjectCount += 1
          const nodeId = String(obj?.userData?.__graphNodeId || '')
          if (nodeId) nodeIds.add(nodeId)
        }
      })
    }
    return { meshCount, nodeObjectCount, uniqueNodeIdCount: nodeIds.size }
  }, [])

  const collectForce3DVisibilityStats = useCallback<() => Graph3DVisibilityStats>(() => {
    const api = forceGraphRef.current
    const scene = api?.scene?.()
    let sceneNodeObjects = 0
    let emptySceneNodeObjects = 0
    if (scene?.traverse) {
      scene.traverse((obj) => {
        if (!obj?.userData?.__graphNodeObject) return
        sceneNodeObjects += 1
        if (obj?.userData?.__graphNodeIsEmpty) emptySceneNodeObjects += 1
      })
    }
    const visibleForceNodes = forceGraphData.nodes.filter((node) => forceVisibleNodeKeySet.has(String(node.id || '')))
    const dataNodes = visibleForceNodes.length
    const emptyDataNodes = visibleForceNodes.reduce((acc, item) => {
      const rawNode = (item as { rawNode?: GraphNodeItem }).rawNode
      return resolveNodeSymbol(rawNode?.type || '').startsWith('empty') ? acc + 1 : acc
    }, 0)
    return {
      dataNodes,
      sceneNodeObjects,
      emptyDataNodes,
      emptySceneNodeObjects,
    }
  }, [forceGraphData.nodes, forceVisibleNodeKeySet])

  useEffect(() => {
    force3DVisibilityStatsGetterRef.current = collectForce3DVisibilityStats
  }, [collectForce3DVisibilityStats])

  useEffect(() => {
    if (!import.meta.env.DEV) return
    const debugApi = {
      getVisibilityStats: () => force3DVisibilityStatsGetterRef.current(),
    }
    window.__graph3dDebug = debugApi
    return () => {
      if (window.__graph3dDebug === debugApi) {
        delete window.__graph3dDebug
      }
    }
  }, [])

  const logForce3DDiagnostics = useCallback((stage: string, extra?: Record<string, unknown>) => {
    const stats = collectForce3DSceneStats()
    const expectedNodes = forceGraphData.nodes.length
    const expectedWhite = forceGraphData.nodes.reduce((acc, item) => {
      const rawNode = (item as { rawNode?: GraphNodeItem }).rawNode
      return resolveNodeSymbol(rawNode?.type || '').startsWith('empty') ? acc + 1 : acc
    }, 0)
    console.info('[Graph3D][diag]', {
      stage,
      renderMode,
      useForceGraph3D,
      expectedNodes,
      expectedWhite,
      meshCount: stats.meshCount,
      nodeObjectCount: stats.nodeObjectCount,
      uniqueNodeIdCount: stats.uniqueNodeIdCount,
      ...extra,
    })
  }, [collectForce3DSceneStats, forceGraphData.nodes, renderMode, useForceGraph3D])

  const handleToggleSelectionMode = useCallback(() => {
    const nextEnabled = !selectionEnabledRef.current
    logForce3DDiagnostics('selection-toggle:before', { nextEnabled })
    setSelectionEnabled((prev) => {
      const next = !prev
      if (next) {
        // Avoid unnecessary state churn: only reset when state is actually non-empty.
        setManualSelectedNodeKeys((curr) => (curr.size ? new Set() : curr))
        setManualDeselectedNodeKeys((curr) => (curr.size ? new Set() : curr))
        setRadiationSelectionByCenter((curr) => (Object.keys(curr).length ? {} : curr))
        setSelectionPinned((curr) => (curr ? false : curr))
      } else {
        setSelectionPinned((curr) => (curr ? false : curr))
      }
      return next
    })
    if (useForceGraph3D) {
      window.setTimeout(() => {
        logForce3DDiagnostics('selection-toggle:after', { nextEnabled })
      }, 120)
    }
  }, [
    useForceGraph3D,
    logForce3DDiagnostics,
    setSelectionEnabled,
    selectionEnabledRef,
    setManualDeselectedNodeKeys,
    setManualSelectedNodeKeys,
    setRadiationSelectionByCenter,
    setSelectionPinned,
  ])

  const handleCreateDraftNode = useCallback(() => {
    const node = createDraftNode({
      type: newNodeType.trim() || 'Entity',
      name: newNodeName.trim() || undefined,
      title: newNodeName.trim() || undefined,
    })
    const key = nodeKey(node)
    setNodeEditDraft({
      key,
      id: String(node.id),
      type: String(node.type || ''),
      name: String(node.name || ''),
      title: String(node.title || ''),
      x: String(node.x ?? ''),
      y: String(node.y ?? ''),
      z: String(node.z ?? ''),
    })
    setNewNodeName('')
    setGraphEditStatus(tf('graphPage.status.nodeCreated', { key }))
  }, [createDraftNode, newNodeType, newNodeName, setGraphEditStatus, setNewNodeName, setNodeEditDraft, tf])

  const handleDeleteSelectedDraftNodes = useCallback(() => {
    const result = removeDraftNodesByKeys(selectedNodeKeyList)
    if (!result.removedNodes) {
      setGraphEditStatus(t('graphPage.status.nodeDeleteSkipped'))
      return
    }
    setManualSelectedNodeKeys(new Set())
    setManualDeselectedNodeKeys(new Set())
    setRadiationSelectionByCenter({})
    setGraphEditStatus(tf('graphPage.status.nodesDeleted', { nodes: result.removedNodes, edges: result.removedEdges }))
  }, [removeDraftNodesByKeys, selectedNodeKeyList, setGraphEditStatus, setManualSelectedNodeKeys, setManualDeselectedNodeKeys, setRadiationSelectionByCenter, t, tf])

  const handleCreateDraftEdge = useCallback(() => {
    const sourceKey = edgeDraft.sourceKey.trim()
    const targetKey = edgeDraft.targetKey.trim()
    if (!sourceKey || !targetKey) {
      window.alert(t('graphPage.error.selectSourceAndTarget'))
      return
    }
    const created = createDraftEdgeByNodeKeys(sourceKey, targetKey, {
      type: edgeDraft.relation.trim() || 'REL',
      predicate: edgeDraft.relation.trim() || undefined,
    })
    if (!created.ok) {
      if (created.reason === 'already_exists') window.alert(t('graphPage.error.edgeAlreadyExists'))
      else window.alert(t('graphPage.error.edgeCreateMissingNode'))
      return
    }
    setGraphEditStatus(tf('graphPage.status.edgeCreated', { source: sourceKey, target: targetKey }))
  }, [edgeDraft, createDraftEdgeByNodeKeys, setGraphEditStatus, t, tf])

  const handleApplyNodeEditDraft = useCallback(() => {
    if (!nodeEditDraft.key) return
    const patch: Partial<GraphNodeItem> = {
      id: nodeEditDraft.id.trim() || nodeEditDraft.id,
      type: nodeEditDraft.type.trim() || 'Entity',
      name: nodeEditDraft.name.trim() || undefined,
      title: nodeEditDraft.title.trim() || undefined,
    }
    const numericOrUndefined = (raw: string) => {
      const text = raw.trim()
      if (!text) return undefined
      const n = Number(text)
      return Number.isFinite(n) ? n : undefined
    }
    patch.x = numericOrUndefined(nodeEditDraft.x)
    patch.y = numericOrUndefined(nodeEditDraft.y)
    patch.z = numericOrUndefined(nodeEditDraft.z)
    const ok = updateDraftNodeByKey(nodeEditDraft.key, patch)
    if (!ok) {
      window.alert(t('graphPage.error.nodeUpdateFailed'))
      return
    }
    setGraphEditStatus(tf('graphPage.status.nodeUpdated', { key: nodeEditDraft.key }))
  }, [nodeEditDraft, updateDraftNodeByKey, setGraphEditStatus, t, tf])

  const handleForceGraphRenderError = useCallback((message: string) => {
    setForceGraphFallbackNotice(tf('graphPage.error.force3dRenderFallback', { message: message ? ` (${message})` : '' }))
    requestProjectionEngineChange('legacy')
  }, [requestProjectionEngineChange, setForceGraphFallbackNotice, tf])

  const forceGraphRenderBoundaryKey = `${displayResourceKey}:${displayResource.epoch}:${renderMode}:${projectionEngine}:${forceGraphData.nodes.length}:${forceGraphData.links.length}`

  const forceGraphCanvasNode = useMemo(() => {
    if (!(renderMode === 'projection3d' && showForceGraphCanvas && ForceGraph3DComp && displayResource.ready)) return null
    return (
      <div
        ref={forceChartRef}
        className="gv2-chart gv2-chart--force3d"
        data-testid="graph-force3d-canvas-host"
        style={showForceGraphCanvas ? undefined : { display: 'none' }}
      >
        <ForceGraphRenderBoundary
          resetKey={forceGraphRenderBoundaryKey}
          fallbackErrorMessage={t('graphPage.error.renderFailed')}
          onError={handleForceGraphRenderError}
        >
          <ForceGraph3DComp
            key={`${displayResourceKey}:${displayResource.epoch}`}
            ref={forceGraphRef}
            width={forceViewport.width || displayResource.width}
            height={forceViewport.height || displayResource.height}
            graphData={forceGraphData}
            nodeVisibility={(node: unknown) => {
              const id = String((node as { id?: string }).id || '')
              return forceVisibleNodeKeySet.has(id)
            }}
            linkVisibility={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return forceVisibleLinkKeySet.has(`${source}>${target}`)
            }}
            backgroundColor="#030712"
            showNavInfo={false}
            nodeVal={(node: unknown) => {
              const id = String((node as { id?: string }).id || '')
              return Number(forceNodeStyleById.get(id)?.val || 1)
            }}
            nodeColor={(node: unknown) => {
              const id = String((node as { id?: string }).id || '')
              return String(forceNodeStyleById.get(id)?.color || '#7dd3fc')
            }}
            nodeOpacity={Math.max(0.2, Math.min(1, visualApplied.nodeAlpha / 100))}
            nodeLabel={(node: unknown) => String((node as { name?: string }).name || '')}
            nodeThreeObject={(node: unknown) => {
              const n = node as { id?: string; rawNode?: GraphNodeItem }
              const id = String(n.id || '')
              const rawSymbol = resolveNodeSymbol(n.rawNode?.type || '')
              const graphSymbol = toGraphSymbol(rawSymbol)
              const style = forceNodeStyleById.get(id)
              const size = Math.max(1.8, Number(style?.val || 1))
              const color = String(style?.color || '#7dd3fc')
              const opacity = Math.max(0.16, Math.min(1, Number(style?.opacity || 0.8)))
              return getOrCreateForceNodeObject({
                cache: forceNodeObjectCacheRef.current,
                id,
                style: { size, color, opacity, rawSymbol, graphSymbol },
                isSelected: selectedNodeKeysRef.current.has(id),
                applyVisualState: applyForceObjectVisualState,
              })
            }}
            linkColor={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return String(forceLinkStyleByKey.get(`${source}>${target}`)?.color || '#7dd3fc')
            }}
            linkWidth={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return Number(forceLinkStyleByKey.get(`${source}>${target}`)?.width || 1)
            }}
            linkCurvature={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return Number(forceLinkStyleByKey.get(`${source}>${target}`)?.curvature || 0)
            }}
            linkCurveRotation={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return Number(forceLinkStyleByKey.get(`${source}>${target}`)?.curveRotation || 0)
            }}
            linkOpacity={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return Number(forceLinkStyleByKey.get(`${source}>${target}`)?.opacity || Math.max(0.06, Math.min(1, visualApplied.edgeAlpha / 100)))
            }}
            linkDirectionalArrowLength={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return Number(forceLinkStyleByKey.get(`${source}>${target}`)?.arrowLength || 0)
            }}
            linkDirectionalArrowColor={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return String(forceLinkStyleByKey.get(`${source}>${target}`)?.color || '#7dd3fc')
            }}
            onNodeHover={handleForceNodeHover}
            onNodeClick={handleForceNodeClick}
            onNodeRightClick={handleForceNodeRightClick}
            onBackgroundClick={handleForceBackgroundClick}
            onEngineTick={() => {
              const next = new Map(forceNodePhysicsRef.current)
              forceGraphData.nodes.forEach((node) => {
                const id = String(node.id || '')
                if (!id) return
                next.set(`${activeProjectionId}\u0000${id}`, {
                  x: node.x,
                  y: node.y,
                  z: node.z,
                  vx: node.vx,
                  vy: node.vy,
                  vz: node.vz,
                })
              })
              forceNodePhysicsRef.current = next
            }}
          />
        </ForceGraphRenderBoundary>
      </div>
    )
  }, [
    renderMode,
    showForceGraphCanvas,
    displayResource.ready,
    displayResourceKey,
    displayResource.epoch,
    displayResource.width,
    displayResource.height,
    ForceGraph3DComp,
    forceGraphRenderBoundaryKey,
    forceViewport.width,
    forceViewport.height,
    forceGraphData,
    activeProjectionId,
    forceVisibleNodeKeySet,
    forceVisibleLinkKeySet,
    visualApplied.nodeAlpha,
    visualApplied.edgeAlpha,
    forceNodeStyleById,
    forceLinkStyleByKey,
    handleForceNodeHover,
    handleForceNodeClick,
    handleForceNodeRightClick,
    handleForceBackgroundClick,
    handleForceGraphRenderError,
    applyForceObjectVisualState,
    selectedNodeKeysRef,
    t,
  ])

  const detachProjectionControls = renderMode === 'projection3d' && activeRendererCapabilities.supportsProjectionControls
  const projectionControlSection = activeRendererCapabilities.supportsProjectionControls ? (
    <label className="gv2-control-chip">
      {t('graphPage.control.force3dEngine')}
      <select
        value={projectionEngine}
        onChange={(e) => requestProjectionEngineChange(e.target.value as ProjectionEngine)}
      >
        <option value="legacy">legacy-projection</option>
        <option value="force3d">react-force-graph-3d</option>
      </select>
    </label>
  ) : null
  const templateDiffSummary = templateDiffPreview?.version_summary || {}
  const templateDiff = templateDiffPreview?.diff || {}
  const templateDiffSteps = templateDiff.steps || []
  const templateDiffContract = isPlainRecord(templateDiffPreview) ? templateDiffPreview : {}
  const templateDiffImpact = isPlainRecord(templateDiffContract.impact_summary) ? templateDiffContract.impact_summary : {}
  const templateDiffPolicy = isPlainRecord(templateDiffContract.policy_change) ? templateDiffContract.policy_change : {}
  const templateDiffAffectedAreas = Array.isArray(templateDiffContract.affected_areas)
    ? templateDiffContract.affected_areas
    : templateDiffImpact.affected_areas
  const templateDiffReasonCode = String(templateDiffContract.reason_code || templateDiffImpact.reason_code || '-')
  const templateDiffRiskLevel = String(templateDiffContract.risk_level || templateDiffImpact.risk_level || '-')

  return (
    <div className="content-stack gv2-root">
      <section className="panel gv2-main">
        {workspaceTabs.length > 1 ? (
          <div
            role="tablist"
            aria-label={t('graphPage.macro.graph')}
            className="gv2-projection-tabs"
            onKeyDown={(event) => {
              if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
              event.preventDefault()
              const currentIndex = workspaceTabs.findIndex((tab) => tab.moduleKey === activeWorkspaceTab.moduleKey)
              let nextIndex = currentIndex
              if (event.key === 'ArrowLeft') nextIndex = currentIndex === -1 ? 0 : (currentIndex - 1 + workspaceTabs.length) % workspaceTabs.length
              if (event.key === 'ArrowRight') nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % workspaceTabs.length
              if (event.key === 'Home') nextIndex = 0
              if (event.key === 'End') nextIndex = workspaceTabs.length - 1
              const nextTab = workspaceTabs[nextIndex]
              if (!nextTab) return
              selectWorkspaceTab(nextTab.moduleKey)
              window.requestAnimationFrame(() => {
                document.getElementById(`graph-workspace-tab-${nextTab.moduleKey}`)?.focus()
              })
            }}
          >
            <div className="gv2-projection-tab-track">
              {workspaceTabs.map((tab) => {
                const Icon = GRAPH_WORKSPACE_TAB_ICONS[tab.moduleKey]
                const active = tab.moduleKey === activeWorkspaceTab.moduleKey
                return (
                  <button
                    key={tab.moduleKey}
                    id={`graph-workspace-tab-${tab.moduleKey}`}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    aria-controls="graph-projection-panel"
                    tabIndex={active ? 0 : -1}
                    data-testid={`graph-workspace-tab-${tab.moduleKey}`}
                    className={`gv2-projection-tab ${tab.isBuilder ? 'is-builder' : ''} ${active ? 'is-active' : ''}`.trim()}
                    onClick={() => selectWorkspaceTab(tab.moduleKey)}
                  >
                    <Icon aria-hidden="true" className="gv2-projection-tab-icon" />
                    <span className="gv2-projection-tab-label">{tab.label || t(tab.labelKey)}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ) : null}
        <div className="gv2-layout">
          <div
            className={`gv2-chart-wrap gv2-chart-wrap--fullscreen-ready ${isFullscreen ? 'is-fullscreen' : ''}`}
            ref={fullscreenWrapRef}
            id="graph-projection-panel"
            role="tabpanel"
            aria-labelledby={`graph-workspace-tab-${activeWorkspaceTab.moduleKey}`}
          >
            {graphData.isFetching ? <div className="gv2-loading">{t('graphPage.loading.fetching')}</div> : null}
            {graphData.error ? (
              <div className="gv2-loading gv2-loading-error">
                {t('graphPage.error.loadFailed')}{graphData.error instanceof Error ? graphData.error.message : t('graphPage.error.requestException')}
              </div>
            ) : null}
            <div
              ref={chartRef}
              className="gv2-chart"
              data-testid="graph-chart-2d"
              style={showForceGraphCanvas ? { display: 'none' } : undefined}
            />
            {forceGraphCanvasNode}
            {useForceGraph3D && !ForceGraph3DComp ? (
              <div className="gv2-loading">{t('graphPage.loading.force3d')}</div>
            ) : null}
            {useForceGraph3D && forceGraphLoadError ? (
              <div className="gv2-loading gv2-loading-error">{t('graphPage.error.force3dLoadFailed')}{forceGraphLoadError}</div>
            ) : null}
            {renderMode === 'projection3d' && projectionEngine === 'legacy' && forceGraphFallbackNotice ? (
              <div className="gv2-loading">
                {forceGraphFallbackNotice}
                <button
                  type="button"
                  className="gv2-select-mode-btn"
                  style={{ marginLeft: 8 }}
                  onClick={() => {
                    setForceGraphFallbackNotice(null)
                    retryForceGraph3D()
                    requestProjectionEngineChange('force3d')
                  }}
                >
                  {t('graphPage.action.retryForce3d')}
                </button>
              </div>
            ) : null}
            <div className="gv2-floating-toolbar-layer">
              <div
                className="gv2-overlay-top"
                onMouseDown={(e) => {
                  const targetEl = e.target as HTMLElement | null
                  const hitButton = targetEl?.closest('button') as HTMLButtonElement | null
                  if (hitButton) {
                    e.stopPropagation()
                  }
                }}
                onClick={(e) => {
                  const targetEl = e.target as HTMLElement | null
                  const hitButton = targetEl?.closest('button') as HTMLButtonElement | null
                  if (hitButton) e.stopPropagation()
                }}
              >
              <button
                type="button"
                className={`gv2-select-mode-btn ${selectionEnabled ? '' : 'is-off'}`.trim()}
                onClick={handleToggleSelectionMode}
              >
                {t('graphPage.action.selectionMode')}
              </button>
              {templateBuilder ? (
              <button
                type="button"
                className={`gv2-select-mode-btn ${editMode ? '' : 'is-off'}`.trim()}
                onClick={() => setEditMode((prev) => !prev)}
                title={t('graphPage.tooltip.editMode')}
              >
                {t('graphPage.action.editMode')}{isDraftDirty ? ' *' : ''}
              </button>
              ) : null}
              <button
                type="button"
                className={`gv2-select-mode-btn ${autoFocusEnabled ? '' : 'is-off'}`.trim()}
                onClick={() => {
                  setAutoFocusEnabled((prev) => {
                    const next = !prev
                    if (!next) clearAutoFocusState()
                    return next
                  })
                }}
                title={t('graphPage.tooltip.autoFocusHide')}
              >
                {t('graphPage.action.autoFocusHide')}
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${renderMode === 'projection3d' ? '' : 'is-off'}`.trim()}
                onClick={() => requestRenderModeChange(renderMode === '2d' ? 'projection3d' : '2d')}
                title={t('graphPage.tooltip.projectionMode')}
              >
                {renderMode === 'projection3d' ? t('graphPage.action.mode2d') : t('graphPage.action.mode3d')}
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${showSymbolDebug ? '' : 'is-off'}`.trim()}
                onClick={() => setShowSymbolDebug((v) => !v)}
                title={t('graphPage.tooltip.symbolDebug')}
              >
                {t('graphPage.action.symbolDebug')}
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${selectionPinned ? '' : 'is-off'}`.trim()}
                onClick={() => setSelectionPinned((v) => !v)}
                disabled={!selectedNodeKeys.size}
              >
                {t('graphPage.action.pinSelection')}
              </button>
              <button
                type="button"
                onClick={() => setTaskModalOpen(true)}
                disabled={!selectedNodeKeys.size}
              >
                {t('graphPage.action.structuredTasks')}（{selectedNodeKeys.size}）
              </button>
              <button
                type="button"
                className="gv2-select-mode-btn"
                data-testid="graph-create-clue-chain"
                onClick={() => void handleCreateClueChain()}
                disabled={clueChainBusy || !clueChainSeedNodes.length}
                title={t('graphPage.tooltip.createClueChain')}
              >
                {clueChainBusy ? <LoaderCircle size={14} className="spinning" /> : <GitBranchPlus size={14} />}
                {tf('graphPage.action.clueChainWithCount', { count: selectedNodeKeys.size || clueChainSeedNodes.length })}
              </button>
              <button onClick={async () => { await graphData.refetch() }} disabled={graphData.isFetching}>{t('graphPage.action.refresh')}</button>
              <button
                onClick={async () => {
                  if (!fullscreenWrapRef.current) return
                  const nativeFullscreenActive = document.fullscreenElement === fullscreenWrapRef.current
                  try {
                    if (nativeFullscreenActive) {
                      fullscreenWantedRef.current = false
                      await document.exitFullscreen?.()
                      return
                    }
                    if (isFullscreen && !nativeFullscreenActive) {
                      fullscreenWantedRef.current = false
                      setIsFullscreen(false)
                      return
                    }
                    fullscreenWantedRef.current = true
                    await fullscreenWrapRef.current.requestFullscreen?.()
                  } catch (error) {
                    console.warn('fullscreen_toggle_failed', error)
                  }
                }}
              >
                {isFullscreen ? t('graphPage.action.exitFullscreen') : t('graphPage.action.fullscreen')}
              </button>
              <button onClick={() => setShowOverlay((v) => !v)}>{showOverlay ? t('graphPage.action.collapsePanel') : t('graphPage.action.expandPanel')}</button>
              {nodeDragCapturedFx ? <span className="gv2-drag-captured">{t('graphPage.status.dragCaptured')}</span> : null}
              </div>
            </div>
            {renderMode === 'projection3d' && !isFullscreen ? (
              <div className="gv2-graph-controls-hint">
                {t('graphPage.hint.force3dControls')}
              </div>
            ) : null}
            <div
              ref={controlPanelRef}
              className={`gv2-floating-controls ${showOverlay ? '' : 'is-collapsed'}`}
              style={isCompactViewport ? undefined : { width: `${controlPanelWidth}px`, maxHeight: `${controlPanelHeight}px` }}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="gv2-floating-resizer gv2-floating-resizer--left" onMouseDown={onControlResizeStart} />
              <div className="gv2-floating-resizer gv2-floating-resizer--bottom" onMouseDown={onControlResizeBottomStart} />
              <section className={`gv2-control-section ${controlSectionOpen.view ? '' : 'is-collapsed'}`}>
                <button
                  type="button"
                  className="gv2-control-section-head"
                  onClick={() => setControlSectionOpen((prev) => ({ ...prev, view: !prev.view }))}
                >
                  <strong>{t('graphPage.section.view')}</strong>
                  <span>{controlSectionOpen.view ? t('graphPage.action.collapse') : t('graphPage.action.expand')}</span>
                </button>
                {controlSectionOpen.view ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip">
                      {t('graphPage.control.repulsion')}
                      <input
                        type="range"
                        min={0}
                        max={200}
                        step={0.1}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.repulsion / 7.2}
                        onChange={(e) => {
                          const repulsion = Number(e.target.value) * 7.2
                          updateVisual('repulsion', repulsion, { mode: 'raf' })
                        }}
                      />
                      <span>{(visualDraft.repulsion / 7.2).toFixed(1)}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.gravity')}
                      <input
                        type="range"
                        min={0}
                        max={300}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.gravityPercent}
                        onChange={(e) => {
                          const gravityPercent = Number(e.target.value)
                          updateVisual('gravityPercent', gravityPercent, { mode: 'raf' })
                        }}
                      />
                      <span>{visualDraft.gravityPercent}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.nodeSize')}
                      <input
                        type="range"
                        min={NODE_SIZE_SLIDER_MIN}
                        max={NODE_SIZE_SLIDER_MAX}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.nodeScale}
                        onChange={(e) => {
                          const nodeScale = Number(e.target.value)
                          updateVisual('nodeScale', nodeScale, { mode: 'throttle', delayMs: 80 })
                        }}
                      />
                      <span>{visualDraft.nodeScale}% · 3D {computeForce3DSizeCompensationX(visualDraft.nodeScale).toFixed(1)}x</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.centralityBoost')}
                      <input
                        type="range"
                        min={NODE_CONTRAST_SLIDER_MIN}
                        max={NODE_CONTRAST_SLIDER_MAX}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.nodeContrastCentral}
                        onChange={(e) => {
                          const nodeContrastCentral = Number(e.target.value)
                          updateVisual('nodeContrastCentral', nodeContrastCentral, { mode: 'raf' })
                        }}
                      />
                      <span>{visualDraft.nodeContrastCentral}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.neighborBoost')}
                      <input
                        type="range"
                        min={NODE_CONTRAST_SLIDER_MIN}
                        max={NODE_CONTRAST_SLIDER_MAX}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.nodeContrastNeighbor}
                        onChange={(e) => {
                          const nodeContrastNeighbor = Number(e.target.value)
                          updateVisual('nodeContrastNeighbor', nodeContrastNeighbor, { mode: 'raf' })
                        }}
                      />
                      <span>{visualDraft.nodeContrastNeighbor}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.nodeAlpha')}
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.nodeAlpha}
                        onChange={(e) => {
                          const nodeAlpha = Number(e.target.value)
                          updateVisual('nodeAlpha', nodeAlpha, { mode: 'raf' })
                        }}
                      />
                      <span>{visualDraft.nodeAlpha}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.edgeWidth')}
                      <input
                        type="range"
                        min={0}
                        max={200}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.edgeWidth}
                        onChange={(e) => {
                          const edgeWidth = Number(e.target.value)
                          updateVisual('edgeWidth', edgeWidth, { mode: 'raf' })
                        }}
                      />
                      <span>{visualDraft.edgeWidth}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.edgeAlpha')}
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={0.5}
                        {...visualSliderInteractionHandlers}
                        value={visualDraft.edgeAlpha}
                        onChange={(e) => {
                          const edgeAlpha = Number(e.target.value)
                          updateVisual('edgeAlpha', edgeAlpha, { mode: 'raf' })
                        }}
                      />
                      <span>{visualDraft.edgeAlpha}%</span>
                    </label>
                    <label className="gv2-control-chip gv2-checkbox">
                      <input
                        type="checkbox"
                        checked={visualDraft.showLabel}
                        onChange={(e) => {
                          const checked = e.target.checked
                          updateVisual('showLabel', checked, { immediate: true })
                        }}
                      />
                      {t('graphPage.control.showLabels')}
                    </label>
                    <div className="gv2-control-chip">
                      <span>{t('graphPage.status.selected')} {selectedNodeKeys.size}</span>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setManualSelectedNodeKeys(new Set())
                          setManualDeselectedNodeKeys(new Set())
                          setRadiationSelectionByCenter({})
                        }}
                        disabled={!selectedNodeKeys.size}
                      >
                        {t('graphPage.action.clear')}
                      </button>
                    </div>
                  </div>
                ) : null}
              </section>

              {!detachProjectionControls ? projectionControlSection : null}

              {templateBuilder ? (
              <section className={`gv2-control-section ${controlSectionOpen.edit ? '' : 'is-collapsed'}`}>
                <button
                  type="button"
                  className="gv2-control-section-head"
                  onClick={() => setControlSectionOpen((prev) => ({ ...prev, edit: !prev.edit }))}
                >
                  <strong>{t('graphPage.section.edit')}</strong>
                  <span>{controlSectionOpen.edit ? t('graphPage.action.collapse') : t('graphPage.action.expand')}</span>
                </button>
                {controlSectionOpen.edit ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip gv2-checkbox">
                      <input type="checkbox" checked={editMode} onChange={(e) => setEditMode(e.target.checked)} />
                      {t('graphPage.control.editModeLocalDraft')}
                    </label>
                    <div className="gv2-control-chip">
                      <span>
                        {tf('graphPage.status.draftSummary', {
                          nodes: draftNodes.length,
                          edges: draftEdges.length,
                          state: isDraftDirty ? t('graphPage.status.draftDirty') : t('graphPage.status.draftClean'),
                        })}
                      </span>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          resetDraft()
                          setGraphEditStatus(t('graphPage.status.resetRemoteSnapshot'))
                        }}
                        disabled={!isDraftDirty}
                      >
                        {t('graphPage.action.discardLocalChanges')}
                      </button>
                    </div>
                    <label className="gv2-control-chip" data-testid="graph-curated-panel">
                      {t('graphPage.field.curatedGraphId')}
                      <input
                        data-testid="graph-curated-graph-id"
                        value={curatedGraphId}
                        onChange={(e) => setCuratedGraphId(e.target.value)}
                        disabled={!editMode || curatedBusy}
                      />
                    </label>
                    <div className="gv2-control-chip">
                      <button
                        type="button"
                        data-testid="graph-curated-save-draft"
                        onClick={() => void handleSaveCuratedDraft()}
                        disabled={!editMode || curatedBusy || !draftNodes.length}
                      >
                        {t('graphPage.action.saveCuratedDraft')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-submit"
                        onClick={() => void handleSubmitCuratedGraph()}
                        disabled={!editMode || curatedBusy || !draftNodes.length}
                      >
                        {t('graphPage.action.submitCuratedGraph')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-sync"
                        onClick={() => void handleSyncCuratedGraph()}
                        disabled={!editMode || curatedBusy}
                      >
                        {t('graphPage.action.syncCurated')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-audit"
                        onClick={() => void handleListCuratedAudits()}
                        disabled={!editMode || curatedBusy}
                      >
                        {t('graphPage.action.readAudit')}
                      </button>
                    </div>
                    <div className="gv2-control-chip">
                      <label>
                        {t('graphPage.field.rollbackVersion')}
                        <input
                          data-testid="graph-curated-rollback-version"
                          value={curatedRollbackVersionId}
                          onChange={(e) => setCuratedRollbackVersionId(e.target.value)}
                          disabled={!editMode || curatedBusy}
                        />
                      </label>
                      <input
                        aria-label={t('graphPage.field.rollbackReason')}
                        data-testid="graph-curated-rollback-reason"
                        value={curatedRollbackReason}
                        onChange={(e) => setCuratedRollbackReason(e.target.value)}
                        placeholder={t('graphPage.placeholder.rollbackReason')}
                        disabled={!editMode || curatedBusy}
                      />
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-rollback"
                        onClick={() => void handleRollbackCuratedGraph()}
                        disabled={!editMode || curatedBusy || !curatedRollbackVersionId.trim()}
                      >
                        {t('graphPage.action.executeRollback')}
                      </button>
                    </div>
                    {curatedAuditItems.length ? (
                      <div className="status-line" data-testid="graph-curated-audit-list">
                        {t('graphPage.status.auditPrefix')} {curatedAuditItems.slice(0, 3).map((item) => (
                          `${String(item.action || 'unknown')}#${String(item.version_id || item.audit_id || 'n/a')}`
                        )).join(' / ')}
                      </div>
                    ) : null}
                    <label className="gv2-control-chip">
                      {t('graphPage.field.reportingTopic')}
                      <input
                        data-testid="graph-curated-reporting-topic"
                        value={curatedHandoffTopic}
                        onChange={(e) => setCuratedHandoffTopic(e.target.value)}
                        disabled={!editMode || curatedBusy}
                      />
                    </label>
                    <div className="gv2-control-chip">
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-reporting-handoff"
                        onClick={() => void handleBuildCuratedReportingHandoff()}
                        disabled={!editMode || curatedBusy || !curatedHandoffTopic.trim()}
                      >
                        {t('graphPage.action.buildReportingHandoff')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-handoff-replay"
                        onClick={() => void handleReplayCuratedHandoff()}
                        disabled={!editMode || curatedBusy || !curatedHandoffReplay.runId || !curatedHandoffReplay.handoffId}
                      >
                        {t('graphPage.action.replayHandoff')}
                      </button>
                    </div>
                    <div className="status-line" data-testid="graph-curated-status">
                      {curatedBusy ? t('graphPage.status.curatedBusy') : (curatedStatus || t('graphPage.status.curatedReady'))}
                    </div>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.newNodeType')}
                      <input value={newNodeType} onChange={(e) => setNewNodeType(e.target.value)} disabled={!editMode} />
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.newNodeName')}
                      <input value={newNodeName} onChange={(e) => setNewNodeName(e.target.value)} disabled={!editMode} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={handleCreateDraftNode} disabled={!editMode}>{t('graphPage.action.addNode')}</button>
                      <button type="button" className="secondary" onClick={handleDeleteSelectedDraftNodes} disabled={!editMode || !selectedNodeKeyList.length}>
                        {tf('graphPage.action.deleteSelectedNodes', { count: selectedNodeKeyList.length })}
                      </button>
                    </div>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.edgeSource')}
                      <select value={edgeDraft.sourceKey} onChange={(e) => setEdgeDraft((prev) => ({ ...prev, sourceKey: e.target.value }))} disabled={!editMode}>
                        <option value="">{t('graphPage.placeholder.selectSource')}</option>
                        {editableNodeItems.map((item) => (
                          <option key={item.key} value={item.key}>{item.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.edgeTarget')}
                      <select value={edgeDraft.targetKey} onChange={(e) => setEdgeDraft((prev) => ({ ...prev, targetKey: e.target.value }))} disabled={!editMode}>
                        <option value="">{t('graphPage.placeholder.selectTarget')}</option>
                        {editableNodeItems.map((item) => (
                          <option key={item.key} value={item.key}>{item.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.relation')}
                      <input value={edgeDraft.relation} onChange={(e) => setEdgeDraft((prev) => ({ ...prev, relation: e.target.value }))} placeholder={t('graphPage.placeholder.relation')} disabled={!editMode} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={handleCreateDraftEdge} disabled={!editMode}>{t('graphPage.action.createEdge')}</button>
                    </div>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.nodeEditTarget')}
                      <select
                        value={nodeEditDraft.key}
                        onChange={(e) => {
                          const key = e.target.value
                          const node = draftNodeMap.get(key)
                          if (!node) return
                          setNodeEditDraft({
                            key,
                            id: String(node.id ?? ''),
                            type: String(node.type || ''),
                            name: String(node.name || ''),
                            title: String(node.title || ''),
                            x: String(node.x ?? ''),
                            y: String(node.y ?? ''),
                            z: String(node.z ?? ''),
                          })
                        }}
                        disabled={!editMode}
                      >
                        <option value="">{t('graphPage.placeholder.selectNode')}</option>
                        {selectedEditableNodes.map((node) => {
                          const key = nodeKey(node)
                          return <option key={key} value={key}>{nodeName(node)} ({key})</option>
                        })}
                      </select>
                    </label>
                    {activeEditableNode ? (
                      <>
                        <label className="gv2-control-chip">{t('graphPage.field.id')}<input value={nodeEditDraft.id} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, id: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">{t('graphPage.field.type')}<input value={nodeEditDraft.type} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, type: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">{t('graphPage.field.name')}<input value={nodeEditDraft.name} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, name: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">{t('graphPage.field.title')}<input value={nodeEditDraft.title} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, title: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">x<input value={nodeEditDraft.x} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, x: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">y<input value={nodeEditDraft.y} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, y: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">z<input value={nodeEditDraft.z} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, z: e.target.value }))} disabled={!editMode} /></label>
                        <div className="gv2-control-chip">
                          <button type="button" onClick={handleApplyNodeEditDraft} disabled={!editMode}>{t('graphPage.action.applyNodeFields')}</button>
                        </div>
                      </>
                    ) : null}
                    <label className="gv2-control-chip">
                      {t('graphPage.field.templateList')}
                      <select
                        value={activeTemplateKey}
                        data-testid="graph-template-select"
                        onChange={(e) => selectTemplate(e.target.value)}
                        disabled={!editMode || templateBusy}
                      >
                        <option value="">{t('graphPage.placeholder.selectTemplate')}</option>
                        {templateItems.map((item) => (
                          <option key={item.key} value={item.key}>
                            {item.name}{item.activeVersion ? tf('graphPage.status.activeVersionSuffix', { version: item.activeVersion }) : ''}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.createTemplate')}
                      <input value={templateNameDraft} data-testid="graph-template-create-name" onChange={(e) => setTemplateNameDraft(e.target.value)} placeholder={t('graphPage.placeholder.templateName')} disabled={!editMode || templateBusy} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" data-testid="graph-template-create" onClick={() => void handleCreateTemplate()} disabled={!editMode || templateBusy || !templateNameDraft.trim()}>{t('graphPage.action.createTemplate')}</button>
                      <button type="button" className="secondary" onClick={() => void loadTemplateList()} disabled={!editMode || templateBusy}>{t('graphPage.action.refreshTemplateList')}</button>
                    </div>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.renameTemplate')}
                      <input value={renameTemplateDraft} data-testid="graph-template-rename-name" onChange={(e) => setRenameTemplateDraft(e.target.value)} placeholder={t('graphPage.placeholder.newName')} disabled={!editMode || !activeTemplateKey || templateBusy} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" data-testid="graph-template-rename" onClick={() => void handleRenameTemplate()} disabled={!editMode || !activeTemplateKey || !renameTemplateDraft.trim() || templateBusy}>{t('graphPage.action.rename')}</button>
                      <button type="button" className="secondary" data-testid="graph-template-delete" onClick={() => void handleDeleteTemplate()} disabled={!editMode || !activeTemplateKey || templateBusy}>{t('graphPage.action.deleteTemplate')}</button>
                    </div>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.versionList')}
                      <select value={activeVersionKey} data-testid="graph-template-version-select" onChange={(e) => setActiveVersionKey(e.target.value)} disabled={!editMode || !activeTemplateKey || templateBusy}>
                        <option value="">{t('graphPage.placeholder.selectVersion')}</option>
                        {versionItems.map((item) => (
                          <option key={item.key} value={item.key}>{item.name}{item.activated ? t('graphPage.status.activeSuffix') : ''}</option>
                        ))}
                      </select>
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" className="secondary" onClick={() => void handleLoadTemplateVersions()} disabled={!editMode || !activeTemplateKey || templateBusy}>{t('graphPage.action.refreshVersions')}</button>
                    </div>
                    <div className="gv2-control-chip">
                      <strong>{t('graphPage.field.templateStageAudit')}</strong>
                      <button type="button" className="secondary" data-testid="graph-template-stage-audit-refresh" onClick={() => void handleRefreshWorkflowTemplateStages()} disabled={!editMode || !activeTemplateKey || templateStageBusy}>{t('graphPage.action.refreshStageAudit')}</button>
                    </div>
                    <div className="gv2-control-chip">
                      <button type="button" data-testid="graph-template-stage-save" onClick={() => void handleSaveWorkflowTemplateDraftStage()} disabled={!editMode || !activeTemplateKey || templateStageBusy || !draftNodes.length}>{t('graphPage.action.saveDraftStage')}</button>
                      <button type="button" className="secondary" data-testid="graph-template-stage-promote" onClick={() => void handlePromoteWorkflowTemplateStage('draft', 'staging')} disabled={!editMode || !activeTemplateKey || templateStageBusy || !hasDraftTemplateStage}>{t('graphPage.action.promoteDraftToStaging')}</button>
                      <button type="button" className="secondary" data-testid="graph-template-stage-apply" onClick={() => void handlePromoteWorkflowTemplateStage('staging', 'active')} disabled={!editMode || !activeTemplateKey || templateStageBusy || !hasStagingTemplateStage}>{t('graphPage.action.applyStaging')}</button>
                    </div>
                    {templateStageAuditSummary ? (
                      <div className="status-line">
                        {tf('graphPage.status.templateStageSummary', {
                          stage: templateStageAuditSummary.stage || '-',
                          active: templateStageAuditSummary.activeVersion ?? '-',
                          draft: templateStageAuditSummary.draftVersion ?? '-',
                          staging: templateStageAuditSummary.stagingVersion ?? '-',
                          current: templateStageAuditSummary.currentVersion ?? '-',
                          next: templateStageAuditSummary.nextVersion ?? '-',
                          requiresPublish: String(Boolean(templateStageAuditSummary.requiresPublish)),
                        })}
                      </div>
                    ) : null}
                    {templateStageItems.length ? templateStageItems.map((item) => (
                      <div key={`${String(item.stage)}:${String(item.version ?? '')}`} className="gv2-control-chip">
                        <strong>{String(item.stage)}</strong>
                        <span>
                          {tf('graphPage.status.templateStageRecord', {
                            version: item.version ?? '-',
                            stepCount: Array.isArray(item.steps) ? item.steps.length : 0,
                            requiresPublish: String(Boolean(item.requires_publish)),
                            promotedFrom: item.promoted_from || '-',
                          })}
                        </span>
                      </div>
                    )) : (
                      <div className="status-line">{t('graphPage.status.templateStageAuditEmpty')}</div>
                    )}
                    <div className="gv2-control-chip" data-testid="graph-template-rollback-controls">
                      <strong>{t('graphPage.field.templateRollback')}</strong>
                      <label>
                        {t('graphPage.field.rollbackTargetStage')}
                        <select
                          value={templateRollbackDraft.targetStage}
                          data-testid="graph-template-rollback-stage"
                          onChange={(e) => setTemplateRollbackDraft((prev) => ({
                            ...prev,
                            targetStage: e.target.value as WorkflowTemplateStageName,
                          }))}
                          disabled={!editMode || templateRollbackBusy}
                        >
                          <option value="draft">draft</option>
                          <option value="staging">staging</option>
                          <option value="active">active</option>
                        </select>
                      </label>
                      <label>
                        {t('graphPage.field.rollbackTargetVersion')}
                        <input
                          type="number"
                          min="1"
                          value={templateRollbackDraft.targetVersion}
                          data-testid="graph-template-rollback-version"
                          onChange={(e) => setTemplateRollbackDraft((prev) => ({ ...prev, targetVersion: e.target.value }))}
                          placeholder={t('graphPage.placeholder.rollbackTargetVersion')}
                          disabled={!editMode || templateRollbackBusy}
                        />
                      </label>
                      <label>
                        {t('graphPage.field.rollbackReason')}
                        <input
                          value={templateRollbackDraft.reason}
                          data-testid="graph-template-rollback-reason"
                          onChange={(e) => setTemplateRollbackDraft((prev) => ({ ...prev, reason: e.target.value }))}
                          placeholder={t('graphPage.placeholder.rollbackReason')}
                          disabled={!editMode || templateRollbackBusy}
                        />
                      </label>
                    </div>
                    <div className="gv2-control-chip">
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-template-rollback-preview"
                        onClick={() => void handlePreviewWorkflowTemplateRollback()}
                        disabled={!editMode || !activeTemplateKey || templateRollbackBusy || !templateRollbackDraft.targetVersion.trim()}
                      >
                        {templateRollbackBusy ? t('graphPage.status.templateRollbackBusy') : t('graphPage.action.previewRollback')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-template-rollback-apply"
                        onClick={() => void handleApplyWorkflowTemplateRollback()}
                        disabled={!editMode || !activeTemplateKey || templateRollbackBusy || !templateRollbackDraft.targetVersion.trim()}
                      >
                        {t('graphPage.action.applyRollback')}
                      </button>
                    </div>
                    {templateRollbackPreview ? (
                      <div data-testid="graph-template-rollback-result">
                        <div className="status-line">
                          {tf('graphPage.status.templateRollbackPlan', {
                            mode: templateRollbackPlan.mode,
                            canExecute: String(templateRollbackPlan.canExecute),
                            willMutate: String(templateRollbackPlan.willMutate),
                            fromStage: templateRollbackPlan.fromStage,
                            toStage: templateRollbackPlan.toStage,
                            targetVersion: String(templateRollbackPlan.targetVersion),
                            targetStepCount: templateRollbackPlan.targetStepCount,
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.templateRollbackAudit', {
                            action: templateRollbackAudit.action,
                            actor: templateRollbackAudit.actor,
                            appliedBy: templateRollbackAudit.appliedBy,
                            traceId: templateRollbackAudit.traceId,
                            fromStage: templateRollbackAudit.fromStage,
                            toStage: templateRollbackAudit.toStage,
                            createdAt: templateRollbackAudit.createdAt,
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.templateRollbackRisk', {
                            blockedReason: templateRollbackPlan.blockedReason,
                            applyEndpoint: templateRollbackPlan.applyEndpoint,
                            requiresExplicitApply: String(templateRollbackPlan.requiresExplicitApply),
                            historyCount: templateRollbackHistoryCount,
                          })}
                        </div>
                      </div>
                    ) : null}
                    {templateRollbackError ? (
                      <div className="status-line" data-testid="graph-template-rollback-error">
                        {tf('graphPage.error.templateRollbackRecoverableError', { message: templateRollbackError })}
                      </div>
                    ) : null}
                    <label className="gv2-control-chip">
                      {t('graphPage.field.versionName')}
                      <input value={versionNameDraft} data-testid="graph-template-version-name" onChange={(e) => setVersionNameDraft(e.target.value)} placeholder={t('graphPage.placeholder.versionName')} disabled={!editMode || templateBusy} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" data-testid="graph-template-version-save" onClick={() => void handleSaveVersion()} disabled={!editMode || !activeTemplateKey || templateBusy}>{t('graphPage.action.saveVersion')}</button>
                      <button type="button" className="secondary" data-testid="graph-template-version-load" onClick={() => void handleLoadVersion()} disabled={!editMode || !activeTemplateKey || !activeVersionKey || templateBusy}>{t('graphPage.action.loadVersion')}</button>
                      <button type="button" className="secondary" data-testid="graph-template-version-activate" onClick={() => void handleActivateVersion()} disabled={!editMode || !activeTemplateKey || !activeVersionKey || templateBusy}>{t('graphPage.action.activateVersion')}</button>
                    </div>
                    <div className="gv2-control-chip">
                      <strong>{t('graphPage.field.configDiff')}</strong>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-template-diff"
                        onClick={() => void handlePreviewWorkflowTemplateDiff()}
                        disabled={!editMode || !activeTemplateKey || templateDiffBusy || !draftNodes.length}
                      >
                        {templateDiffBusy ? t('graphPage.status.configDiffLoading') : t('graphPage.action.previewConfigDiff')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-template-dry-run"
                        onClick={() => void handleWorkflowTemplateDryRun()}
                        disabled={!editMode || !activeTemplateKey || templateDryRunBusy}
                      >
                        {templateDryRunBusy ? t('graphPage.status.workflowDryRunLoading') : t('graphPage.action.previewWorkflowDryRun')}
                      </button>
                    </div>
                    {templateDryRunResult ? (
                      <div data-testid="graph-template-dry-run-result">
                        <div className="status-line">
                          {tf('graphPage.status.workflowDryRunSummary', {
                            configVersion: formatWorkflowRunScalar(templateDryRunSummary.configVersion),
                            readiness: formatWorkflowRunScalar(templateDryRunSummary.readiness),
                            willExecute: formatWorkflowRunScalar(templateDryRunSummary.willExecute),
                            writesBlocked: formatWorkflowRunScalar(templateDryRunSummary.writesBlocked),
                            requiresPublish: formatWorkflowRunScalar(templateDryRunSummary.requiresPublish),
                          })}
                        </div>
                        {templateDryRunSteps.length ? templateDryRunSteps.slice(0, 8).map((step) => (
                          <div key={`${step.index}:${step.name}`} className="gv2-control-chip">
                            <span>
                              {tf('graphPage.status.workflowDryRunStep', {
                                index: step.index,
                                step: step.name,
                                status: formatWorkflowRunScalar(step.status),
                                willExecute: formatWorkflowRunScalar(step.willExecute),
                                writesBlocked: formatWorkflowRunScalar(step.writesBlocked),
                              })}
                            </span>
                          </div>
                        )) : (
                          <div className="status-line">{t('graphPage.status.workflowDryRunNoSteps')}</div>
                        )}
                      </div>
                    ) : null}
                    {templateDiffPreview ? (
                      <div data-testid="graph-template-diff-result">
                        <div className="status-line">
                          {tf('graphPage.status.configDiffVersions', {
                            stage: String(templateDiffSummary.stage || '-'),
                            active: templateDiffSummary.active_version ?? '-',
                            draft: templateDiffSummary.draft_version ?? '-',
                            current: templateDiffPreview.current_version ?? '-',
                            next: templateDiffPreview.next_version ?? '-',
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.configDiffMutation', {
                            willMutate: String(Boolean(templateDiffSummary.will_mutate)),
                            requiresPublish: String(Boolean(templateDiffSummary.requires_publish)),
                            boardChanged: String(Boolean(templateDiff.board_layout_changed)),
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.configDiffStepCounts', {
                            before: templateDiff.step_count_before ?? 0,
                            after: templateDiff.step_count_after ?? 0,
                            changes: templateDiffSteps.length,
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.configDiffReason', {
                            reasonCode: templateDiffReasonCode,
                            riskLevel: templateDiffRiskLevel,
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.configDiffAffectedAreas', {
                            areas: formatContractList(templateDiffAffectedAreas),
                          })}
                        </div>
                        <div className="status-line">
                          {tf('graphPage.status.configDiffPolicyImpact', {
                            changed: String(Boolean(templateDiffPolicy.changed)),
                            requiresPublish: String(Boolean(templateDiffPolicy.requires_publish)),
                            stage: String(templateDiffPolicy.stage || templateDiffSummary.stage || '-'),
                          })}
                        </div>
                        {templateDiffSteps.length ? templateDiffSteps.slice(0, 8).map((step) => (
                          <div key={`${step.index}:${step.change_type}`} className="gv2-control-chip">
                            <span>
                              {tf('graphPage.status.configDiffStep', {
                                index: step.index,
                                changeType: String(step.change_type || 'changed'),
                                before: formatWorkflowDiffStepSide(step.before, tf),
                                after: formatWorkflowDiffStepSide(step.after, tf),
                              })}
                            </span>
                          </div>
                        )) : (
                          <div className="status-line">{t('graphPage.status.configDiffNoStepChanges')}</div>
                        )}
                      </div>
                    ) : null}
                    <div className="status-line">
                      {(templateBusy || templateStageBusy || templateRollbackBusy || templateDryRunBusy) ? t('graphPage.status.templateBusy') : (graphEditStatus || t('graphPage.status.editReady'))}
                    </div>
                    <div className="gv2-control-chip">
                      <span>{tf('graphPage.status.draftEdgeCount', { count: editableEdges.length })}</span>
                    </div>
                    {editableEdges.slice(0, 8).map((edge) => (
                      <div key={edge.key} className="gv2-control-chip">
                        <span>{edge.label}</span>
                        <button type="button" className="secondary" onClick={() => removeDraftEdgeAt(edge.index)} disabled={!editMode}>{t('graphPage.action.delete')}</button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
              ) : null}

              <section className={`gv2-control-section ${controlSectionOpen.color ? '' : 'is-collapsed'}`}>
                <button
                  type="button"
                  className="gv2-control-section-head"
                  onClick={() => setControlSectionOpen((prev) => ({ ...prev, color: !prev.color }))}
                >
                  <strong>{t('graphPage.section.color')}</strong>
                  <span>{controlSectionOpen.color ? t('graphPage.action.collapse') : t('graphPage.action.expand')}</span>
                </button>
                {controlSectionOpen.color ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip">
                      {t('graphPage.control.paletteTheme')}
                      <select value={paletteKey} onChange={(e) => setPaletteKey(e.target.value as PaletteKey)}>
                        {Object.entries(GRAPH_COLOR_THEMES).map(([key, val]) => (
                          <option key={key} value={key}>{val.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.colorRotate')}
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={1}
                        value={colorRotate}
                        onChange={(e) => setColorRotate(Number(e.target.value))}
                      />
                      <span>{colorRotate}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.control.absoluteContrast')}
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={1}
                        value={absoluteContrast}
                        onChange={(e) => setAbsoluteContrast(Number(e.target.value))}
                      />
                      <span>{absoluteContrast}%</span>
                    </label>
                  </div>
                ) : null}
              </section>

              <section className={`gv2-control-section ${controlSectionOpen.filter ? '' : 'is-collapsed'}`}>
                <button
                  type="button"
                  className="gv2-control-section-head"
                  onClick={() => setControlSectionOpen((prev) => ({ ...prev, filter: !prev.filter }))}
                >
                  <strong>{t('graphPage.section.filter')}</strong>
                  <span>{controlSectionOpen.filter ? t('graphPage.action.collapse') : t('graphPage.action.expand')}</span>
                </button>
                {controlSectionOpen.filter ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip">
                      {t('graphPage.field.startDate')}
                      <input
                        type="date"
                        value={startDate}
                        onChange={(e) => {
                          setStartDate(e.target.value)
                          if (filterApplyError) setFilterApplyError('')
                        }}
                      />
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.endDate')}
                      <input
                        type="date"
                        value={endDate}
                        onChange={(e) => {
                          setEndDate(e.target.value)
                          if (filterApplyError) setFilterApplyError('')
                        }}
                      />
                    </label>
                    {(graphProjection.configKey === 'policy' || graphKind === 'market' || Boolean(graphProjection.marketView)) ? (
                      <label className="gv2-control-chip">
                        {t('graphPage.field.state')}
                        <input value={state} placeholder={t('graphPage.placeholder.state')} onChange={(e) => setState(e.target.value)} />
                      </label>
                    ) : null}
                    {graphKind === 'policy' ? (
                      <label className="gv2-control-chip">
                        {t('graphPage.field.policyType')}
                        <input value={policyType} placeholder={t('graphPage.placeholder.policyType')} onChange={(e) => setPolicyType(e.target.value)} />
                      </label>
                    ) : null}
                    {graphKind === 'social' ? (
                      <>
                        <label className="gv2-control-chip">
                          {t('graphPage.field.platform')}
                          <input value={platform} placeholder={t('graphPage.placeholder.platform')} onChange={(e) => setPlatform(e.target.value)} />
                        </label>
                        <label className="gv2-control-chip">
                          {t('graphPage.field.topic')}
                          <input value={topic} placeholder={t('graphPage.placeholder.topic')} onChange={(e) => setTopic(e.target.value)} />
                        </label>
                      </>
                    ) : null}
                    {(graphKind === 'market' || Boolean(graphProjection.marketView)) ? (
                      <label className="gv2-control-chip">
                        {t('graphPage.field.game')}
                        <input value={game} placeholder={t('graphPage.placeholder.game')} onChange={(e) => setGame(e.target.value)} />
                      </label>
                    ) : null}
                    <label className="gv2-control-chip">
                      {t('graphPage.field.limit')}
                      <input
                        type="range"
                        min={GRAPH_LIMIT_MIN}
                        max={GRAPH_LIMIT_MAX}
                        step={1}
                        value={limit}
                        onChange={(e) => {
                          setLimit(clampGraphLimit(Number(e.target.value)))
                        }}
                      />
                      <span>{limit}</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.rankingStrategy')}
                      <select value={rankingStrategy} onChange={(e) => setRankingStrategy(e.target.value as NodeRankStrategy)}>
                        <option value="doc_body">{t('graphPage.ranking.docBody')}</option>
                        <option value="node_connectivity">{t('graphPage.ranking.nodeConnectivity')}</option>
                        <option value="doc_id">{t('graphPage.ranking.docId')}</option>
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.centralityWeight')}
                      <input
                        type="range"
                        min={RANK_WEIGHT_SLIDER_MIN}
                        max={RANK_WEIGHT_SLIDER_MAX}
                        step={1}
                        value={rankingWeightCentral}
                        onChange={(e) => setRankingWeightCentral(Number(e.target.value))}
                      />
                      <span>{rankingWeightCentral}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      {t('graphPage.field.neighborDegreeWeight')}
                      <input
                        type="range"
                        min={RANK_WEIGHT_SLIDER_MIN}
                        max={RANK_WEIGHT_SLIDER_MAX}
                        step={1}
                        value={rankingWeightNeighbor}
                        onChange={(e) => setRankingWeightNeighbor(Number(e.target.value))}
                      />
                      <span>{rankingWeightNeighbor}%</span>
                    </label>
                    <div className="gv2-control-chip">
                      <button
                        onClick={() => {
                          const nextStartDate = String(startDate || '').trim()
                          const nextEndDate = String(endDate || '').trim()
                          if (nextStartDate && nextEndDate && nextStartDate > nextEndDate) {
                            setFilterApplyError(t('graphPage.error.invalidDateRange'))
                            return
                          }
                          setFilterApplyError('')
                          setAppliedRankingWeights({
                            central: rankingWeightCentral,
                            neighbor: rankingWeightNeighbor,
                          })
                          setAppliedRankingStrategy(rankingStrategy)
                          setAppliedFilters({
                            startDate: nextStartDate,
                            endDate: nextEndDate,
                            state,
                            policyType,
                            platform,
                            topic,
                            game,
                            limit: clampGraphLimit(limit),
                          })
                          // Keep filter behavior predictable: applying query filters should reset legend hide masks.
                          setHiddenTypes({})
                          setHiddenEdgeKinds({})
                        }}
                      >
                        {t('graphPage.action.applyFilter')}
                      </button>
                      <button
                        className="secondary"
                        onClick={() => {
                          setRankingWeightCentral(RANK_WEIGHT_DEFAULT)
                          setRankingWeightNeighbor(RANK_WEIGHT_DEFAULT)
                          setAppliedRankingWeights({
                            central: RANK_WEIGHT_DEFAULT,
                            neighbor: RANK_WEIGHT_DEFAULT,
                          })
                          setRankingStrategy('doc_body')
                          setAppliedRankingStrategy('doc_body')
                          setFilterApplyError('')
                          setStartDate('')
                          setEndDate('')
                          setState('')
                          setPolicyType('')
                          setPlatform('')
                          setTopic('')
                          setGame('')
                          const resetLimit = templateBuilder ? 50 : GRAPH_LIMIT_DEFAULT
                          setLimit(resetLimit)
                          setAppliedFilters({
                            startDate: '',
                            endDate: '',
                            state: '',
                            policyType: '',
                            platform: '',
                            topic: '',
                            game: '',
                            limit: resetLimit,
                          })
                          setHiddenTypes({})
                          setHiddenEdgeKinds({})
                          setExpandedGroup(null)
                          setExpandedEdgeGroup(null)
                        }}
                      >
                        {t('graphPage.action.reset')}
                      </button>
                    </div>
                    {filterApplyError ? (
                      <p style={{ margin: '6px 0 0', color: '#d93025', fontSize: '12px' }}>{filterApplyError}</p>
                    ) : null}
                  </div>
                ) : null}
              </section>
            </div>
            {detachProjectionControls ? (
              <div
                ref={projectionPanelRef}
                className={`gv2-floating-projection-left ${showOverlay ? '' : 'is-collapsed'}`}
                style={isCompactViewport ? undefined : { width: `${projectionPanelWidth}px`, maxHeight: `${projectionPanelHeight}px` }}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="gv2-floating-resizer gv2-floating-resizer--right" onMouseDown={onProjectionResizeStart} />
                <div className="gv2-floating-resizer gv2-floating-resizer--bottom" onMouseDown={onProjectionResizeBottomStart} />
                {projectionControlSection}
              </div>
            ) : null}
            <div
              ref={legendPanelRef}
              className={`gv2-legend-float ${showOverlay ? '' : 'is-collapsed'}`}
              style={isCompactViewport ? undefined : { width: `${legendPanelWidth}px`, maxHeight: `${legendPanelHeight}px` }}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="gv2-floating-resizer gv2-floating-resizer--right" onMouseDown={onLegendResizeStart} />
              <div className="gv2-floating-resizer gv2-floating-resizer--bottom" onMouseDown={onLegendResizeBottomStart} />
              <div className="gv2-legend-groups">
                {legendGroups.map(([group, types]) => {
                  const groupColor = nodeTypeColor[types[0]] || '#7dd3fc'
                  const active = expandedGroup === group
                  return (
                    <button
                      key={group}
                      type="button"
                      className={`gv2-legend-node ${active ? 'is-active' : ''}`}
                      title={graphGroupLabel(group)}
                      onClick={(e) => {
                        if (e.detail > 1) return
                        setExpandedGroup((prev) => (prev === group ? null : group))
                      }}
                      onDoubleClick={() => {
                        setHiddenTypes((prev) => {
                          const next = { ...prev }
                          types.forEach((type) => {
                            next[type] = !next[type]
                          })
                          return next
                        })
                      }}
                    >
                      <NodeLegendShape nodeType={types[0]} color={groupColor} />
                      <span className="gv2-legend-node-label">{graphGroupLabel(group)}</span>
                    </button>
                  )
                })}
              </div>
              {expandedGroup ? (
                <div className="gv2-type-grid">
                  {(legendGroups.find(([group]) => group === expandedGroup)?.[1] || []).map((type) => {
                    const hidden = Boolean(hiddenTypes[type])
                    return (
                      <button
                        key={type}
                        type="button"
                        className={`gv2-type ${hidden ? 'is-hidden' : ''}`}
                        onClick={() => setHiddenTypes((prev) => ({ ...prev, [type]: !prev[type] }))}
                      >
                        <NodeLegendShape nodeType={type} color={nodeTypeColor[type] || '#7dd3fc'} />
                        <span>{nodeTypeLabel(type, graphConfig.data?.graph_node_labels)}</span>
                      </button>
                    )
                  })}
                </div>
              ) : null}
              {edgeLegendGroups.length ? (
                <div className="gv2-legend-edge-wrap">
                  <div className="gv2-legend-section-title">{t('graphPage.legend.edge')}</div>
                  <div className="gv2-legend-groups gv2-edge-legend-groups">
                    {edgeLegendGroups.map(([tier, items]) => {
                      const sample = items[0]
                      const active = expandedEdgeGroup === tier
                      return (
                        <button
                          key={tier}
                          type="button"
                          className={`gv2-legend-node gv2-edge-legend-node ${active ? 'is-active' : ''}`}
                          title={edgeTierLabel(tier)}
                          onClick={(e) => {
                            if (e.detail > 1) return
                            setExpandedEdgeGroup((prev) => (prev === tier ? null : tier))
                          }}
                          onDoubleClick={() => {
                            setHiddenEdgeKinds((prev) => {
                              const next = { ...prev }
                              items.forEach((item) => {
                                next[item.key] = !next[item.key]
                              })
                              return next
                            })
                          }}
                        >
                          <EdgeLegendBadge profile={EDGE_STYLE_CATALOG[sample.styleId]} color={sample.color} scale={edgeBadgeScale} />
                          <span className="gv2-legend-node-label">{edgeTierLabel(tier)}</span>
                        </button>
                      )
                    })}
                  </div>
                  {expandedEdgeGroup ? (
                    <div className="gv2-type-grid gv2-edge-type-grid">
                      {(edgeLegendGroups.find(([tier]) => tier === expandedEdgeGroup)?.[1] || []).map((item) => {
                        const hidden = Boolean(hiddenEdgeKinds[item.key])
                        return (
                          <button
                            key={item.key}
                            type="button"
                            className={`gv2-type gv2-type--edge ${hidden ? 'is-hidden' : ''}`}
                            onClick={() => setHiddenEdgeKinds((prev) => ({ ...prev, [item.key]: !prev[item.key] }))}
                          >
                        <EdgeLegendBadge profile={EDGE_STYLE_CATALOG[item.styleId]} color={item.color} scale={edgeBadgeScale} />
                            <span>{item.label}</span>
                            <small>{item.count}</small>
                          </button>
                        )
                      })}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {showSymbolDebug ? (
                <div className="gv2-legend-debug">
                  <div className="gv2-legend-section-title">{t('graphPage.legend.symbolDebug')}</div>
                  <div className="gv2-legend-debug-meta">
                    <span>{t('graphPage.legend.visibleNodes')} {symbolDebug.total}</span>
                    <span>{t('graphPage.legend.typeMappings')} {symbolDebug.unique}</span>
                    <span>{t('graphPage.legend.fallbackCircle')} {symbolDebug.forcedCircle}</span>
                  </div>
                  <div className="gv2-legend-debug-list">
                    {symbolDebug.items.map((item) => (
                      <div key={`${item.raw}-${item.normalized}-${item.rawSymbol}-${item.graphSymbol}`} className="gv2-legend-debug-row">
                        <NodeLegendShape nodeType={item.normalized} color="#7dd3fc" />
                        <code>{item.raw}</code>
                        <span>→</span>
                        <code>{item.normalized}</code>
                        <span>→</span>
                        <code>{item.graphSymbol}</code>
                        <small>{item.count}</small>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            {taskModalOpen ? (
              <div className="gv2-task-modal-backdrop" onClick={() => setTaskModalOpen(false)}>
                <div className="gv2-task-modal" onClick={(e) => e.stopPropagation()}>
                  <div className="gv2-task-modal-head">
                    <strong>{t('graphPage.section.structuredTasks')}</strong>
                    <button type="button" onClick={() => setTaskModalOpen(false)}>×</button>
                  </div>
                  <p className="gv2-task-modal-hint">{t('graphPage.hint.structuredTasks')}</p>
                  <div className="gv2-task-grid">
                    <label>{t('graphPage.field.language')}<input value={dashboard.language} onChange={(e) => setDashboard((p) => ({ ...p, language: e.target.value }))} /></label>
                    <label>{t('graphPage.field.provider')}<input value={dashboard.provider} onChange={(e) => setDashboard((p) => ({ ...p, provider: e.target.value }))} /></label>
                    <label>{t('graphPage.field.maxItems')}<input type="number" min={1} max={100} value={dashboard.maxItems} onChange={(e) => setDashboard((p) => ({ ...p, maxItems: Math.min(100, Math.max(1, Number(e.target.value) || 1)) }))} /></label>
                    <label>{t('graphPage.field.startOffset')}<input type="number" min={1} value={dashboard.startOffset} onChange={(e) => setDashboard((p) => ({ ...p, startOffset: e.target.value }))} /></label>
                    <label>{t('graphPage.field.daysBack')}<input type="number" min={0} max={365} value={dashboard.daysBack} onChange={(e) => setDashboard((p) => ({ ...p, daysBack: e.target.value }))} /></label>
                    <label>{t('graphPage.field.platforms')}<input value={dashboard.platforms} onChange={(e) => setDashboard((p) => ({ ...p, platforms: e.target.value }))} /></label>
                    <label>{t('graphPage.field.baseSubreddits')}<input value={dashboard.baseSubreddits} onChange={(e) => setDashboard((p) => ({ ...p, baseSubreddits: e.target.value }))} /></label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.enableExtraction} onChange={(e) => setDashboard((p) => ({ ...p, enableExtraction: e.target.checked }))} />{t('graphPage.control.enableExtraction')}</label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.asyncMode} onChange={(e) => setDashboard((p) => ({ ...p, asyncMode: e.target.checked }))} />{t('graphPage.control.asyncMode')}</label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.enableSubredditDiscovery} onChange={(e) => setDashboard((p) => ({ ...p, enableSubredditDiscovery: e.target.checked }))} />{t('graphPage.control.enableSubredditDiscovery')}</label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.llmAssist} onChange={(e) => setDashboard((p) => ({ ...p, llmAssist: e.target.checked }))} />{t('graphPage.control.llmAssist')}</label>
                  </div>
                  <div className="gv2-source-panel">
                    <div className="gv2-source-panel-head">
                      <strong>{t('graphPage.section.sourceLibrary')}</strong>
                      <span>{tf('graphPage.status.selectedCount', { count: dashboard.sourceItemKeys.length })}</span>
                    </div>
                    <div className="gv2-source-panel-tools">
                      <input
                        value={sourceItemKeyword}
                        onChange={(e) => setSourceItemKeyword(e.target.value)}
                        placeholder={t('graphPage.placeholder.sourceItemFilter')}
                      />
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          const visibleKeys = filteredSourceItems.map((item) => String(item.item_key || '').trim()).filter(Boolean)
                          setDashboard((prev) => ({ ...prev, sourceItemKeys: Array.from(new Set([...(prev.sourceItemKeys || []), ...visibleKeys])) }))
                        }}
                      >
                        {t('graphPage.action.selectVisible')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setDashboard((prev) => ({ ...prev, sourceItemKeys: [] }))}
                      >
                        {t('graphPage.action.clear')}
                      </button>
                    </div>
                    <div className="gv2-source-panel-list">
                      {sourceItemsQuery.isLoading ? <div className="status-line">{t('graphPage.status.sourceLibraryLoading')}</div> : null}
                      {sourceItemsQuery.isError ? <div className="status-line">{t('graphPage.error.sourceLibraryLoadFailed')}</div> : null}
                      {!sourceItemsQuery.isLoading && !sourceItemsQuery.isError && !filteredSourceItems.length ? (
                        <div className="status-line">{t('graphPage.empty.sourceItems')}</div>
                      ) : null}
                      {filteredSourceItems.map((item) => {
                        const itemKey = String(item.item_key || '').trim()
                        const checked = dashboard.sourceItemKeys.includes(itemKey)
                        if (!itemKey) return null
                        return (
                          <label key={itemKey} className="gv2-source-item">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => {
                                setDashboard((prev) => {
                                  const set = new Set(prev.sourceItemKeys || [])
                                  if (set.has(itemKey)) set.delete(itemKey)
                                  else set.add(itemKey)
                                  return { ...prev, sourceItemKeys: Array.from(set) }
                                })
                              }}
                            />
                            <span>{item.name || itemKey}</span>
                            <small>{itemKey}</small>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                  <textarea className="gv2-task-json" readOnly value={JSON.stringify(selectedExportPayload, null, 2)} />
                  <div className="gv2-task-actions">
                    <button type="button" className="secondary" onClick={() => void copyStructuredPayload()}>{t('graphPage.action.copyStructuredTasksJson')}</button>
                    <button
                      type="button"
                      disabled={Boolean(submittingMap.collect)}
                      onClick={() => void submitStructuredTasks('collect')}
                    >
                      {submittingMap.collect ? t('graphPage.status.submitting') : t('graphPage.action.createStructuredCollectTasks')}
                    </button>
                    <button
                      type="button"
                      disabled={Boolean(submittingMap.source_collect)}
                      onClick={() => void submitStructuredTasks('source_collect')}
                    >
                      {submittingMap.source_collect ? t('graphPage.status.submitting') : t('graphPage.action.createSourceCollectTasks')}
                    </button>
                  </div>
                  <div className="gv2-task-result">
                    <div>{t('graphPage.result.collectAccepted')}: {String(structuredResultMap.collect?.summary?.accepted ?? '-')}</div>
                    <div>{t('graphPage.result.collectQueued')}: {String(structuredResultMap.collect?.summary?.queued ?? '-')}</div>
                    <div>{t('graphPage.result.collectFailed')}: {String(structuredResultMap.collect?.summary?.failed ?? '-')}</div>
                    <div>
                      {t('graphPage.result.collectBatchNames')}: {(structuredResultMap.collect?.batches || []).map((b, idx) => String(b.batch_name || tf('graphPage.result.batchNameFallback', { index: idx + 1 }))).join(', ') || '-'}
                    </div>
                    <hr style={{ borderColor: 'rgba(148,163,184,0.2)' }} />
                    <div>{t('graphPage.result.sourceCollectAccepted')}: {String(structuredResultMap.source_collect?.summary?.accepted ?? '-')}</div>
                    <div>{t('graphPage.result.sourceCollectQueued')}: {String(structuredResultMap.source_collect?.summary?.queued ?? '-')}</div>
                    <div>{t('graphPage.result.sourceCollectFailed')}: {String(structuredResultMap.source_collect?.summary?.failed ?? '-')}</div>
                    <div>
                      {t('graphPage.result.sourceCollectBatchNames')}: {(structuredResultMap.source_collect?.batches || []).map((b, idx) => String(b.batch_name || tf('graphPage.result.batchNameFallback', { index: idx + 1 }))).join(', ') || '-'}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

          {clueChainOpen && activeClueChain ? (
            <ClueChainInspector
              chain={activeClueChain}
              busy={clueChainBusy}
              status={clueChainStatus}
              selectedEvidenceId={selectedClueEvidenceId}
              onClose={() => setClueChainOpen(false)}
              onRunExpand={(mode) => void handleRunClueChainExpand(mode)}
              onReviewCandidate={(candidateId, decision) => void handleReviewClueChainCandidate(candidateId, decision)}
              onOpenEvidence={setSelectedClueEvidenceId}
            />
          ) : null}

          {selectedNode ? (
            <article
              className="gv2-node-card"
              data-testid="graph-selected-node-card"
              style={nodeCardStyle}
              onMouseEnter={() => {
                if (autoFocusEnabled) scheduleForceHoverNodeKey(null)
              }}
            >
              <div className="gv2-node-card-head" onMouseDown={onNodeCardDragStart}>
                <div>
                  <strong>{nodeName(selectedNode)}</strong>
                  <small>{String(selectedNode.type || '-')}</small>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setRelationGroupOpen({})
                    setExpandedNeighborType(null)
                    setExpandedPredicate(null)
                    setExpandedElementLabel(null)
                    setSelectedNode(null)
                  }}
                  aria-label={t('graphPage.action.close')}
                >
                  ×
                </button>
              </div>
              <div className="gv2-node-card-body">
                  {selectedDocumentId && selectedDocument.isLoading ? <LoaderCircle size={18} aria-label={t('graphPage.action.refresh')} /> : null}
                  {selectedDocument.error ? <p role="alert">{selectedDocument.error.message}</p> : null}
                  {selectedDocument.data ? <GraphBusinessCardSections node={selectedDocument.data as unknown as Record<string, unknown>} /> : null}
                  <div className="gv2-node-grid">
                    {cardFields(selectedNode, cardFieldLabel).map(([k, v]) => (
                      <div key={`${k}-${v}`} className="gv2-node-grid-item">
                        <label>{k}</label>
                        <strong>{v}</strong>
                      </div>
                    ))}
                  </div>
                  {selectedNodeContext ? (
                    <div className="gv2-node-context">
                      <strong>{t('graphPage.section.graphInfo')}</strong>
                      <div className="gv2-node-grid">
                        <div className="gv2-node-grid-item">
                          <label>{t('graphPage.field.degree')}</label>
                          <strong>{selectedNodeContext.degree}</strong>
                        </div>
                        <div className="gv2-node-grid-item">
                          <label>{t('graphPage.field.neighborTypeCount')}</label>
                          <strong>{selectedNodeContext.neighborTypeCount}</strong>
                        </div>
                        <div className="gv2-node-grid-item">
                          <label>{t('graphPage.field.relatedDocCount')}</label>
                          <strong>{selectedNodeContext.marketDocCount}</strong>
                        </div>
                      </div>
                      {selectedNodeContext.neighborTypeItems.length ? (
                        <div className="gv2-node-tags">
                          {selectedNodeContext.neighborTypeItems.map((item, index) => (
                            <button
                              key={item.type}
                              type="button"
                              className={`gv2-node-chip ${expandedNeighborType === item.type ? 'is-active' : ''}`}
                              style={{ '--chip-color': distinctChipColor(index) } as CSSProperties}
                              onClick={() => setExpandedNeighborType((prev) => (prev === item.type ? null : item.type))}
                            >
                              {item.type}: {item.count}
                            </button>
                          ))}
                        </div>
                      ) : null}
                      {expandedNeighborType && selectedNodeContext.neighborNodesByType[expandedNeighborType]?.length ? (
                        <div className="gv2-node-expand-list">
                          {selectedNodeContext.neighborNodesByType[expandedNeighborType].map((item) => (
                            <span key={`${item.type}-${item.id}`}>
                              <i style={{ background: nodeTypeColor[item.type] || '#7dd3fc' }} />
                              {item.name}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {selectedNodeContext.predicateItems.length ? (
                        <div className="gv2-node-tags">
                          {selectedNodeContext.predicateItems.map((item, index) => {
                            const color = distinctChipColor(index)
                            return (
                              <button
                                key={item.predicate}
                                type="button"
                                className={`gv2-node-chip ${expandedPredicate === item.predicate ? 'is-active' : ''}`}
                                style={{ '--chip-color': color } as CSSProperties}
                                onClick={() => setExpandedPredicate((prev) => (prev === item.predicate ? null : item.predicate))}
                              >
                                {item.predicate} ({item.count})
                              </button>
                            )
                          })}
                        </div>
                      ) : null}
                      {expandedPredicate && selectedNodeContext.relationsByPredicate[expandedPredicate]?.length ? (
                        <div className="gv2-node-expand-list">
                          {selectedNodeContext.relationsByPredicate[expandedPredicate].map((item) => (
                            <span key={item.id}>
                              <i style={{ background: nodeTypeColor[item.targetType] || '#7dd3fc' }} />
                              {item.direction === 'OUT' ? t('graphPage.direction.out') : t('graphPage.direction.in')} · {item.targetName}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {nodeAllElements.length ? (
                    <div className="gv2-node-context">
                      <strong>{t('graphPage.section.nodeElements')}</strong>
                      <div className="gv2-node-tags">
                        {nodeElementGroups.map((group, index) => {
                          const color = distinctChipColor(index)
                          return (
                            <button
                              key={group.label}
                              type="button"
                              className={`gv2-node-chip ${expandedElementLabel === group.label ? 'is-active' : ''}`}
                              style={{ '--chip-color': color } as CSSProperties}
                              onClick={() => setExpandedElementLabel((prev) => (prev === group.label ? null : group.label))}
                            >
                              {group.label}: {group.items.length}
                            </button>
                          )
                        })}
                      </div>
                      {expandedElementLabel ? (
                        <div className="gv2-node-expand-list">
                          {(nodeElementGroups.find((group) => group.label === expandedElementLabel)?.items || []).map((item) => (
                            <span key={item.id}>
                              <i style={{ background: GRAPH_COLOR_THEMES[paletteKey].colors[hashText(`el:${item.label}`) % GRAPH_COLOR_THEMES[paletteKey].colors.length] }} />
                              {item.value}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {selectedNodeContext?.relationItems.length ? (
                    <div className="gv2-node-context">
                      <strong>{t('graphPage.section.entityRelationInfo')}</strong>
                      <div className="gv2-rel-group-list">
                        {relationGroups.map((group) => {
                          const open = Boolean(relationGroupOpenResolved[group.relation])
                          return (
                            <section key={group.relation} className="gv2-rel-group">
                              <button
                                type="button"
                                className="gv2-rel-group-head"
                                onClick={() =>
                                  setRelationGroupOpen((prev) => {
                                    const base =
                                      Object.keys(prev).length || !relationGroups.length
                                        ? prev
                                        : { [relationGroups[0].relation]: true }
                                    return { ...base, [group.relation]: !base[group.relation] }
                                  })
                                }
                              >
                                <span className="gv2-rel-group-title">{group.relation}</span>
                                <span className="gv2-rel-group-meta">{tf('graphPage.status.relationItemCount', { count: group.items.length })}</span>
                                <span className="gv2-rel-group-action">{open ? t('graphPage.action.collapse') : t('graphPage.action.expand')}</span>
                              </button>
                              {open ? (
                                <div className="gv2-node-relations">
                                  {group.items.map((item) => (
                                    <div key={item.id} className="gv2-node-relation">
                                      <span className={`gv2-rel-badge ${item.direction === 'OUT' ? 'out' : 'in'}`}>{item.direction === 'OUT' ? t('graphPage.direction.out') : t('graphPage.direction.in')}</span>
                                      <span className="gv2-rel-name">{item.relation}</span>
                                      <span className="gv2-rel-target">
                                        <i style={{ background: nodeTypeColor[item.targetType] || '#7dd3fc' }} />
                                        {item.targetName}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              ) : null}
                            </section>
                          )
                        })}
                      </div>
                      {relationGroups.length > 1 ? (
                        <button
                          type="button"
                          className="gv2-node-toggle"
                          onClick={() => setRelationGroupOpen(
                            allRelationGroupsOpen
                              ? {}
                              : Object.fromEntries(relationGroups.map((group) => [group.relation, true])),
                          )}
                        >
                          {allRelationGroupsOpen
                            ? t('graphPage.action.collapseAllRelationGroups')
                            : tf('graphPage.action.expandAllRelationGroups', { count: relationGroups.length })}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                  {parseNodeTags(selectedNode).length ? (
                    <div className="gv2-node-tags">
                      {parseNodeTags(selectedNode).map((tag) => <span key={tag}>{tag}</span>)}
                    </div>
                  ) : null}
                  {extraPrimitiveFields(selectedNode).length ? (
                    <div className="gv2-node-extra">
                      {extraPrimitiveFields(selectedNode).map(([k, v]) => (
                        <div key={k}>
                          <label>{k}</label>
                          <span>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {selectedNode.text ? <pre>{String(selectedNode.text).slice(0, 220)}</pre> : null}
                </div>
            </article>
          ) : null}
          </div>
          <div className="gv2-macro-stats">
            <div className="gv2-macro-stat"><span>{t('graphPage.macro.graph')}</span><strong>{realizedGraphLabel}</strong></div>
            <div className="gv2-macro-stat"><span>{t('graphPage.macro.totalNodes')}</span><strong>{stats.nodes}</strong></div>
            <div className="gv2-macro-stat"><span>{t('graphPage.macro.totalEdges')}</span><strong>{stats.edges}</strong></div>
            <div className="gv2-macro-stat"><span>{t('graphPage.macro.nodeTypes')}</span><strong>{stats.typeCount}</strong></div>
            <div className="gv2-macro-stat"><span>{t('graphPage.macro.selectedNodes')}</span><strong>{selectedNodeKeys.size}</strong></div>
            <div className="gv2-macro-stat"><span>{t('graphPage.macro.visibleNow')}</span><strong>{topology.visibleNodes.length} / {topology.visibleEdges.length}</strong></div>
          </div>
          <GraphTopologyPanel
            graphIdentity={graphKind}
          />
        </div>
      </section>
    </div>
  )
}
