import { Component, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsType } from 'echarts/core'
import { GitBranchPlus, LoaderCircle } from 'lucide-react'
import * as THREE from 'three'
import * as graphApi from '../lib/api'
import {
  getGraphConfig,
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
import type { WorkflowGraphAuditRecord, WorkflowGraphCuratedDsl, WorkflowGraphCuratedStateResponse } from '../lib/api'
import type {
  GraphEdgeItem,
  GraphNodeItem,
  GraphStructuredDashboardParams,
  GraphStructuredSearchResponse,
  SourceLibraryItem,
} from '../lib/types'
import { queryKeys } from '../lib/queryKeys'
import { GRAPH_COLOR_THEMES, assignLegendColors, type PaletteKey } from '../lib/graph-colors'
import { applyRenderer2D, RENDERER_2D_CAPABILITIES } from './graph/renderers/renderer2dEcharts'
import {
  applyRendererProjection3D,
  RENDERER_PROJECTION_3D_CAPABILITIES,
  type Projection3DPhysicsState,
} from './graph/renderers/renderer3dProjection'
import { getOrCreateForceNodeObject, linkEnds, pruneForceNodeObjectCache } from './graph/renderers/force3dObjects'
import { collectFocusNodeKeys, computeCoreNumber, computePageRank, computeVisibleSubgraph } from './graph/domain/topology'
import { useForceGraph3DLoader } from './graph/hooks/useForceGraph3DLoader'
import { useForceGraphViewport } from './graph/hooks/useForceGraphViewport'
import { useGraphVisualState } from './graph/hooks/useGraphVisualState'
import { useGraphSelectionState } from './graph/hooks/useGraphSelectionState'
import { useGraphModeSwitch, type ProjectionEngine } from './graph/hooks/useGraphModeSwitch'
import { useGraphDraft } from './graph/hooks/useGraphDraft'
import type { RenderNode } from './graph/renderers/types'
import { ClueChainInspector } from './graph/ClueChainInspector'
import {
  createClueChain,
  decideClueChainCandidate,
  expandClueChain,
  type ClueChainDetail,
  type ClueChainSeedNode,
} from './graph/clueChainClient'

type Variant = 'graphMarket' | 'graphPolicy' | 'graphSocial' | 'graphCompany' | 'graphProduct' | 'graphOperation' | 'graphDeep'

type Props = {
  projectKey: string
  variant: Variant
  templateBuilder?: boolean
}

type GraphKind = 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'
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
    this.props.onError(error.message || '渲染失败')
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

const TYPE_TO_KIND: Record<Variant, GraphKind> = {
  graphMarket: 'market',
  graphPolicy: 'policy',
  graphSocial: 'social',
  graphCompany: 'company',
  graphProduct: 'product',
  graphOperation: 'operation',
  graphDeep: 'market_deep_entities',
}

const TYPE_LABEL: Record<Variant, string> = {
  graphMarket: '市场图谱',
  graphPolicy: '政策图谱',
  graphSocial: '社媒图谱',
  graphCompany: '公司图谱',
  graphProduct: '商品图谱',
  graphOperation: '电商/经营图谱',
  graphDeep: '市场实体加细图',
}

const SYMBOLS: Record<string, string> = {
  Policy: 'circle',
  State: 'rect',
  PolicyType: 'diamond',
  KeyPoint: 'roundRect',
  Entity: 'triangle',
  Post: 'circle',
  Keyword: 'diamond',
  Topic: 'triangle',
  SentimentTag: 'pin',
  User: 'roundRect',
  Subreddit: 'arrow',
  MarketData: 'circle',
  Segment: 'diamond',
  Game: 'diamond',
  CompanyEntity: 'circle',
  CompanyBrand: 'emptyDiamond',
  CompanyUnit: 'rect',
  CompanyPartner: 'emptyTriangle',
  CompanyChannel: 'pin',
  ProductEntity: 'roundRect',
  ProductModel: 'emptyDiamond',
  ProductCategory: 'rect',
  ProductBrand: 'emptyCircle',
  ProductComponent: 'triangle',
  ProductScenario: 'emptyPin',
  OperationEntity: 'roundRect',
  OperationPlatform: 'emptyCircle',
  OperationStore: 'diamond',
  OperationChannel: 'emptyRect',
  OperationMetric: 'triangle',
  OperationStrategy: 'emptyPin',
  OperationRegion: 'arrow',
  OperationPeriod: 'emptyRoundRect',
  TopicTag: 'convexStar',
}

type BuiltinGraphSymbol = 'circle' | 'rect' | 'roundRect' | 'triangle' | 'diamond' | 'pin' | 'arrow'
const TOPIC_TAG_CONVEX_SYMBOL_PATH = 'path://M10 2.2 L12.6 6.6 L17.6 7.8 L14.2 11.4 L15 16.6 L10 14.4 L5 16.6 L5.8 11.4 L2.4 7.8 L7.4 6.6 Z'
const FORCE_3D_GLOBAL_SIZE_GAIN = 1.32
const FORCE_3D_SIZE_COMPENSATION_MAX_X = 8
const NODE_BASE_SIZE_MULTIPLIER = 4
const NODE_SIZE_SLIDER_MIN = 0
const NODE_SIZE_SLIDER_MAX = 220
const NODE_CONTRAST_SLIDER_MIN = 0
const NODE_CONTRAST_SLIDER_MAX = 100
const RANK_WEIGHT_SLIDER_MIN = 0
const RANK_WEIGHT_SLIDER_MAX = 100
const RANK_WEIGHT_DEFAULT = 50
const NODE_SIZE_MIN_APPROX = 0.2
const SYMBOL_SIZE_GAIN: Record<string, number> = {
  circle: 1.0,
  rect: 0.92,
  roundRect: 0.92,
  diamond: 1.05,
  triangle: 1.12,
  pin: 1.12,
  arrow: 1.18,
  emptyCircle: 1.0,
  emptyRect: 0.92,
  emptyRoundRect: 0.92,
  emptyDiamond: 1.05,
  emptyTriangle: 1.12,
  emptyPin: 1.12,
  convexStar: 0.9,
}
function symbolSizeGain(symbol: string) {
  const key = String(symbol || '').trim()
  return SYMBOL_SIZE_GAIN[key] || 1
}

function computeEmptyNodeBorderWidth(size: number, selected: boolean) {
  const base = Math.max(1.35, Math.min(4.8, size * 0.16 + 0.55))
  return selected ? Math.max(1.5, base * 1.18) : base
}

function computeForce3DSizeCompensationX(nodeScale: number) {
  void nodeScale
  return FORCE_3D_SIZE_COMPENSATION_MAX_X
}
const SYMBOL_TYPE_BY_COMPACT: Record<string, string> = Object.fromEntries(
  Object.keys(SYMBOLS).map((key) => [key.toLowerCase().replace(/[\s_-]+/g, ''), key]),
)

function resolveNodeSymbol(rawType: string) {
  const normalized = normalizeNodeType(rawType)
  return String(SYMBOLS[normalized] || SYMBOLS[rawType] || 'circle')
}

function toGraphSymbol(symbol: string): BuiltinGraphSymbol {
  const key = String(symbol || '').trim()
  if (key === 'emptyCircle') return 'circle'
  if (key === 'emptyRect') return 'rect'
  if (key === 'emptyRoundRect') return 'roundRect'
  if (key === 'emptyDiamond') return 'diamond'
  if (key === 'emptyTriangle') return 'triangle'
  if (key === 'emptyPin') return 'pin'
  if (key === 'rect' || key === 'roundRect' || key === 'triangle' || key === 'diamond' || key === 'pin' || key === 'arrow') return key
  return 'circle'
}

function NodeLegendShape({ nodeType, color }: { nodeType: string; color: string }) {
  const rawSymbol = resolveNodeSymbol(nodeType)
  const stroke = color
  const fill = rawSymbol.startsWith('empty') ? '#ffffff' : color
  const common = { strokeWidth: 1.5, strokeLinejoin: 'round' as const }
  const icon = (() => {
    if (rawSymbol === 'rect' || rawSymbol === 'emptyRect') {
      return <rect x="4.6" y="4.6" width="10.8" height="10.8" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'roundRect' || rawSymbol === 'emptyRoundRect') {
      return <rect x="4.2" y="5" width="11.6" height="10" rx="2.4" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'diamond' || rawSymbol === 'emptyDiamond') {
      return <polygon points="10,3.8 16.2,10 10,16.2 3.8,10" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'triangle' || rawSymbol === 'emptyTriangle') {
      return <polygon points="10,3.8 16.2,15.8 3.8,15.8" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'pin' || rawSymbol === 'emptyPin') {
      return (
        <>
          <circle cx="10" cy="8.1" r="3.4" fill={fill} stroke={stroke} {...common} />
          <polygon points="10,17 6.8,11.6 13.2,11.6" fill={fill} stroke={stroke} {...common} />
        </>
      )
    }
    if (rawSymbol === 'arrow') {
      return <polygon points="4,6 15.6,10 4,14.2 7.3,10" fill={color} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'convexStar') {
      return <polygon points="10,3 12.8,7.1 17.3,8.2 14.4,11.7 15.1,16.3 10,14.3 4.9,16.3 5.6,11.7 2.7,8.2 7.2,7.1" fill={color} stroke={stroke} {...common} />
    }
    return <circle cx="10" cy="10" r="5.2" fill={fill} stroke={stroke} {...common} />
  })()
  return (
    <span className="gv2-node-shape-badge" data-symbol={rawSymbol}>
      <svg viewBox="0 0 20 20" aria-hidden="true">{icon}</svg>
    </span>
  )
}

function normalizeNodeType(rawType: unknown) {
  const raw = String(rawType || '').trim()
  if (!raw) return raw
  const compact = raw.toLowerCase().replace(/[\s_-]+/g, '')
  const aliasMap: Record<string, string> = {
    productsenario: 'ProductScenario',
    prodctscenario: 'ProductScenario',
    prodctsenario: 'ProductScenario',
    proudctscenario: 'ProductScenario',
    proudctsenario: 'ProductScenario',
    productcomponent: 'ProductComponent',
    prodctcomponent: 'ProductComponent',
    productmodel: 'ProductModel',
    prodctmodel: 'ProductModel',
    productentity: 'ProductEntity',
    prodctentity: 'ProductEntity',
    productcategory: 'ProductCategory',
    prodctcategory: 'ProductCategory',
    productbrand: 'ProductBrand',
    prodctbrand: 'ProductBrand',
    product: 'ProductEntity',
    prodct: 'ProductEntity',
    proudct: 'ProductEntity',
  }
  return aliasMap[compact] || SYMBOL_TYPE_BY_COMPACT[compact] || raw
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
  return String(node.title || node.name || node.text || node.canonical_name || node.id)
}

function nodeTypeLabel(nodeType: string, labels?: Record<string, string>) {
  return labels?.[nodeType] || nodeType
}

function groupOfType(type: string) {
  if (type.startsWith('Company')) return 'company'
  if (type.startsWith('Product')) return 'product'
  if (type.startsWith('Operation')) return 'operation'
  if (['Policy', 'PolicyType', 'KeyPoint', 'State'].includes(type)) return 'policy'
  if (['Post', 'Keyword', 'Topic', 'SentimentTag', 'User', 'Subreddit'].includes(type)) return 'social'
  if (['MarketData', 'Segment', 'Game', 'Entity', 'TopicTag'].includes(type)) return 'market'
  return 'other'
}

const GROUP_LABEL: Record<string, string> = {
  company: '公司',
  product: '商品',
  operation: '运营',
  policy: '政策',
  social: '社媒',
  market: '市场',
  other: '其他',
}

type EdgeLegendTier = 'class' | 'pred' | 'type'

type EdgeLineType = 'solid' | 'dashed' | 'dotted'

type EdgeLegendItem = {
  key: string
  tier: EdgeLegendTier
  shapeKind: EdgeShapeKind
  strokeKind: EdgeStrokeKind
  lineType: EdgeLineType
  label: string
  count: number
  color: string
}

const EDGE_TIER_LABEL: Record<EdgeLegendTier, string> = {
  class: '关系大类',
  pred: '关系谓词',
  type: '边类型',
}

type EdgeShapeKind = 'influence' | 'hierarchy' | 'flow' | 'association' | 'temporal' | 'directed'

type EdgeSymbolName = 'none' | 'arrow' | 'circle' | 'diamond' | 'triangle'
type EdgeStrokeKind = 'straight' | 'curved' | 'wavy' | 'double'

const EDGE_PROFILE_BY_SHAPE: Record<EdgeShapeKind, {
  strokeKind: EdgeStrokeKind
  symbol: [EdgeSymbolName, EdgeSymbolName]
  symbolSize: [number, number]
}> = {
  influence: { strokeKind: 'straight', symbol: ['none', 'arrow'], symbolSize: [0, 8] },
  hierarchy: { strokeKind: 'double', symbol: ['none', 'diamond'], symbolSize: [0, 9] },
  flow: { strokeKind: 'curved', symbol: ['circle', 'arrow'], symbolSize: [4, 8] },
  association: { strokeKind: 'wavy', symbol: ['circle', 'circle'], symbolSize: [4, 4] },
  temporal: { strokeKind: 'curved', symbol: ['none', 'triangle'], symbolSize: [0, 8] },
  directed: { strokeKind: 'straight', symbol: ['none', 'arrow'], symbolSize: [0, 7] },
}

const EDGE_LINE_TYPE_BY_STROKE: Record<EdgeStrokeKind, EdgeLineType> = {
  straight: 'solid',
  curved: 'solid',
  wavy: 'dashed',
  double: 'solid',
}

const EDGE_CURVENESS_BY_STROKE: Record<EdgeStrokeKind, number> = {
  straight: 0,
  curved: 0.2,
  wavy: 0.34,
  double: 0.06,
}

const EDGE_STROKE_LABEL: Record<EdgeStrokeKind, string> = {
  straight: '直线',
  curved: '曲线',
  wavy: '波浪线',
  double: '双线',
}

const RELATION_CLASS_LABEL: Record<string, string> = {
  governance: '治理/监管',
  event: '事件发布',
  metric: '指标披露',
  impact: '影响变化',
  collaboration: '合作关系',
  dependency: '依赖关系',
  supply_chain: '供应链',
  distribution: '分销渠道',
  competition: '竞争关系',
  operation: '运营关系',
  taxonomy: '分类归属',
  targeting: '场景指向',
  channel: '渠道目标',
  strategy: '经营策略',
  composition: '组成关系',
  other: '其他关系',
}

const EDGE_WIDTH_BY_TIER: Record<EdgeLegendTier, number> = {
  class: 1.8,
  pred: 1.4,
  type: 1.2,
}

function normalizeEdgeToken(value: unknown) {
  return String(value || '').trim()
}

function edgeSemanticTokens(edge: GraphEdgeItem) {
  return [
    normalizeEdgeToken(edge.relation_class).toLowerCase(),
    normalizeEdgeToken(edge.predicate).toLowerCase(),
    normalizeEdgeToken(edge.type).toLowerCase(),
  ].filter(Boolean)
}

function matchEdgeToken(tokens: string[], patterns: string[]) {
  return tokens.some((token) => patterns.some((pattern) => token.includes(pattern)))
}

function edgeShapeKind(edge: GraphEdgeItem): EdgeShapeKind {
  const tokens = edgeSemanticTokens(edge)
  if (matchEdgeToken(tokens, ['taxonomy', 'category', 'classify', 'compose', 'composition', 'part', 'belong', 'include'])) {
    return 'hierarchy'
  }
  if (matchEdgeToken(tokens, ['supply', 'distribution', 'channel', 'pipeline', 'flow', 'route'])) {
    return 'flow'
  }
  if (matchEdgeToken(tokens, ['impact', 'influ', 'cause', 'drive', 'effect', 'lift', 'drop'])) {
    return 'influence'
  }
  if (matchEdgeToken(tokens, ['competition', 'collab', 'partner', 'depend', 'relation', 'associate', 'peer'])) {
    return 'association'
  }
  if (matchEdgeToken(tokens, ['event', 'period', 'time', 'timeline', 'phase', 'season', 'date'])) {
    return 'temporal'
  }
  return 'directed'
}

function edgeLegendTier(edge: GraphEdgeItem): EdgeLegendTier {
  if (normalizeEdgeToken(edge.relation_class)) return 'class'
  if (normalizeEdgeToken(edge.predicate)) return 'pred'
  return 'type'
}

function edgeLegendRawValue(edge: GraphEdgeItem): string {
  const tier = edgeLegendTier(edge)
  if (tier === 'class') return normalizeEdgeToken(edge.relation_class).toLowerCase()
  if (tier === 'pred') return normalizeEdgeToken(edge.predicate).toLowerCase()
  return normalizeEdgeToken(edge.type).toUpperCase() || 'REL'
}

function edgeLegendKey(edge: GraphEdgeItem): string {
  const tier = edgeLegendTier(edge)
  return `${tier}:${edgeLegendRawValue(edge)}`
}

function relationLabel(token: string, labels?: Record<string, string>) {
  const raw = String(token || '').trim()
  if (!raw) return '-'
  const variants = [raw, raw.toUpperCase(), raw.toLowerCase()]
  for (const key of variants) {
    if (labels?.[key]) return labels[key]
  }
  return raw
}

function edgeLegendLabel(edge: GraphEdgeItem, labels?: Record<string, string>) {
  const tier = edgeLegendTier(edge)
  if (tier === 'class') {
    const cls = edgeLegendRawValue(edge)
    return RELATION_CLASS_LABEL[cls] || cls
  }
  return relationLabel(edgeLegendRawValue(edge), labels)
}

const DEFAULT_NODE_TYPES_BY_KIND: Record<GraphKind, string[]> = {
  policy: ['Policy', 'State', 'PolicyType', 'KeyPoint', 'Entity'],
  social: ['Post', 'Keyword', 'Entity', 'Topic', 'SentimentTag', 'User', 'Subreddit'],
  market: ['MarketData', 'State', 'Segment', 'Entity'],
  market_deep_entities: ['MarketData', 'State', 'Segment', 'Entity', 'CompanyEntity', 'CompanyBrand', 'CompanyUnit', 'CompanyPartner', 'CompanyChannel', 'ProductEntity', 'ProductModel', 'ProductCategory', 'ProductBrand', 'ProductComponent', 'ProductScenario', 'OperationEntity', 'OperationPlatform', 'OperationStore', 'OperationChannel', 'OperationMetric', 'OperationStrategy', 'OperationRegion', 'OperationPeriod', 'TopicTag'],
  company: ['MarketData', 'CompanyEntity', 'CompanyBrand', 'CompanyUnit', 'CompanyPartner', 'CompanyChannel', 'TopicTag'],
  product: ['MarketData', 'ProductEntity', 'ProductModel', 'ProductCategory', 'ProductBrand', 'ProductComponent', 'ProductScenario', 'TopicTag'],
  operation: ['MarketData', 'OperationEntity', 'OperationPlatform', 'OperationStore', 'OperationChannel', 'OperationMetric', 'OperationStrategy', 'OperationRegion', 'OperationPeriod', 'TopicTag'],
}

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
const CONTROL_PANEL_MIN_WIDTH = 280
const CONTROL_PANEL_MAX_WIDTH = 720
const FLOATING_PANEL_MIN_HEIGHT = 120
const FLOATING_PANEL_MAX_HEIGHT = 920

function clampGraphLimit(value: number) {
  if (!Number.isFinite(value)) return GRAPH_LIMIT_DEFAULT
  return Math.max(GRAPH_LIMIT_MIN, Math.min(GRAPH_LIMIT_MAX, Math.trunc(value)))
}

function clampControlPanelWidth(value: number, viewportWidth: number) {
  const viewportBound = Math.max(CONTROL_PANEL_MIN_WIDTH, viewportWidth - 28)
  const maxAllowed = Math.min(CONTROL_PANEL_MAX_WIDTH, viewportBound)
  return Math.max(CONTROL_PANEL_MIN_WIDTH, Math.min(maxAllowed, Math.round(value)))
}

function clampFloatingPanelWidth(value: number, viewportWidth: number) {
  const maxAllowed = Math.max(40, viewportWidth - 28)
  return Math.max(16, Math.min(maxAllowed, Math.round(value)))
}

function clampFloatingPanelHeight(value: number, viewportHeight: number) {
  const maxAllowed = Math.max(FLOATING_PANEL_MIN_HEIGHT, viewportHeight - 24)
  return Math.max(16, Math.min(Math.max(FLOATING_PANEL_MAX_HEIGHT, maxAllowed), Math.round(value)))
}

function computeNodeVisualSize(
  centralScore: number,
  centralMinValue: number,
  centralRangeValue: number,
  neighborScore: number,
  neighborMinValue: number,
  neighborRangeValue: number,
  nodeScale: number,
  centralContrast: number,
  neighborContrast: number,
) {
  const centralNorm = Math.max(0, (centralScore - centralMinValue) / Math.max(1e-12, centralRangeValue))
  const neighborNorm = Math.max(0, (neighborScore - neighborMinValue) / Math.max(1e-12, neighborRangeValue))
  const scaleT = Math.max(0, nodeScale / 100)
  const centralStrength = Math.max(0, centralContrast / 100)
  const neighborStrength = Math.max(0, neighborContrast / 100)
  // Pure enhancement formula:
  // no base term, only (difference term * coefficient).
  // strength=0 => contribution is exactly 0.
  const centralContrastExponent = 1 + centralStrength * 0.9
  const neighborContrastExponent = 1 + neighborStrength * 0.9
  const minPx = NODE_SIZE_MIN_APPROX + scaleT * 4
  const maxPx = NODE_SIZE_MIN_APPROX + scaleT * 30
  const centralEnhanced = Math.pow(centralNorm, centralContrastExponent)
  const neighborEnhanced = Math.pow(neighborNorm, neighborContrastExponent)
  const blendedContribution = Math.max(0, (centralStrength * centralEnhanced + neighborStrength * neighborEnhanced) / 2)
  const size = (minPx + (maxPx - minPx) * blendedContribution) * NODE_BASE_SIZE_MULTIPLIER
  return Math.max(NODE_SIZE_MIN_APPROX, size)
}

function percentile(values: number[], p: number) {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const t = Math.max(0, Math.min(1, p))
  const idx = t * (sorted.length - 1)
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  if (lo === hi) return sorted[lo]
  const w = idx - lo
  return sorted[lo] * (1 - w) + sorted[hi] * w
}

function normalizeMapValues(input: Map<string, number>) {
  const values = Array.from(input.values())
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const range = Math.max(max - min, 1e-12)
  const out = new Map<string, number>()
  input.forEach((value, key) => {
    out.set(key, Math.max(0, Math.min(1, (value - min) / range)))
  })
  return out
}

type QuaternionLike = { x: number; y: number; z: number; w: number }

function normalizeQuat(q: QuaternionLike): QuaternionLike {
  const len = Math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w) || 1
  return { x: q.x / len, y: q.y / len, z: q.z / len, w: q.w / len }
}

function quatMul(a: QuaternionLike, b: QuaternionLike): QuaternionLike {
  return normalizeQuat({
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
  })
}

function quatFromAxisAngle(ax: number, ay: number, az: number, angle: number): QuaternionLike {
  const norm = Math.sqrt(ax * ax + ay * ay + az * az) || 1
  const half = angle / 2
  const s = Math.sin(half) / norm
  return normalizeQuat({
    x: ax * s,
    y: ay * s,
    z: az * s,
    w: Math.cos(half),
  })
}

function quatFromEulerDeg(xDeg: number, yDeg: number, zDeg: number): QuaternionLike {
  const qx = quatFromAxisAngle(1, 0, 0, (xDeg * Math.PI) / 180)
  const qy = quatFromAxisAngle(0, 1, 0, (yDeg * Math.PI) / 180)
  const qz = quatFromAxisAngle(0, 0, 1, (zDeg * Math.PI) / 180)
  return quatMul(qz, quatMul(qy, qx))
}

function rotateVecByQuat(v: { x: number; y: number; z: number }, q: QuaternionLike) {
  const nq = normalizeQuat(q)
  const qx = nq.x
  const qy = nq.y
  const qz = nq.z
  const qw = nq.w
  const tx = 2 * (qy * v.z - qz * v.y)
  const ty = 2 * (qz * v.x - qx * v.z)
  const tz = 2 * (qx * v.y - qy * v.x)
  return {
    x: v.x + qw * tx + (qy * tz - qz * ty),
    y: v.y + qw * ty + (qz * tx - qx * tz),
    z: v.z + qw * tz + (qx * ty - qy * tx),
  }
}

function cardFields(node: GraphNodeItem) {
  const list: Array<[string, string]> = [
    ['类型', String(node.type || '-')],
    ['ID', String(node.id || '-')],
    ['标题', String(node.title || '')],
    ['名称', String(node.name || node.canonical_name || '')],
    ['州', String(node.state || '')],
    ['平台', String(node.platform || '')],
    ['游戏', String(node.game || '')],
    ['政策类型', String(node.policy_type || '')],
    ['状态', String(node.status || '')],
    ['日期', String(node.publish_date || node.effective_date || node.date || '')],
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

function curatedNodeId(node: GraphNodeItem) {
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

function buildCuratedWorkflowGraphDsl(nodes: GraphNodeItem[], edges: GraphEdgeItem[]): WorkflowGraphCuratedDsl {
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

function temporaryCuratedNodeIds(dsl: WorkflowGraphCuratedDsl) {
  return dsl.nodes
    .map((node) => String(node.node_id || node.id || '').trim())
    .filter((id) => /^(draft|tmp|temp)-/i.test(id))
}

function snapshotDslFromCuratedState(state: WorkflowGraphCuratedStateResponse) {
  const snapshot = state.server_snapshot?.dsl || state.draft?.dsl
  if (!snapshot || !Array.isArray(snapshot.nodes) || !Array.isArray(snapshot.edges)) return null
  return snapshot
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

type GraphTemplateRecord = {
  key: string
  name: string
  activeVersion?: string | null
}

type GraphTemplateVersionRecord = {
  key: string
  name: string
  activated?: boolean
}

type ApiMethod = (...args: unknown[]) => Promise<unknown> | unknown

function readCandidateApiMethod(...names: string[]) {
  const bag = graphApi as unknown as Record<string, unknown>
  for (const name of names) {
    const fn = bag[name]
    if (typeof fn === 'function') {
      return { name, fn: fn as ApiMethod }
    }
  }
  return null
}

function asTemplateRecord(raw: unknown): GraphTemplateRecord | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const key = String(row.template_id || row.template_key || row.key || row.name || row.template || '').trim()
  if (!key) return null
  return {
    key,
    name: String(row.name || row.template_name || row.label || key),
    activeVersion: String(row.active_version_id || row.active_version || row.activated_version || row.current_version || '').trim() || null,
  }
}

function asVersionRecord(raw: unknown): GraphTemplateVersionRecord | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const key = String(row.version_id || row.version_key || row.key || row.version || row.name || '').trim()
  if (!key) return null
  return {
    key,
    name: String(row.version_name || row.name || row.label || key),
    activated: Boolean(row.activated ?? row.active ?? row.is_active),
  }
}

const SPECIAL_PREFIX_BY_KIND: Partial<Record<GraphKind, string>> = {
  company: 'Company',
  product: 'Product',
  operation: 'Operation',
}

export default function GraphPage({ projectKey, variant, templateBuilder = false }: Props) {
  const graphKind = TYPE_TO_KIND[variant]
  const defaultCuratedHandoffTopic = TYPE_LABEL[variant]
  const defaultCuratedGraphId = useMemo(() => buildDefaultCuratedGraphId(projectKey, graphKind), [projectKey, graphKind])
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
  const [nodeCardAnchor, setNodeCardAnchor] = useState<NodeCardAnchor | null>(null)
  const [chartReady, setChartReady] = useState(false)
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
  const [editMode, setEditMode] = useState(false)
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
  const [templateItems, setTemplateItems] = useState<GraphTemplateRecord[]>([])
  const [versionItems, setVersionItems] = useState<GraphTemplateVersionRecord[]>([])
  const [templateNameDraft, setTemplateNameDraft] = useState('')
  const [renameTemplateDraft, setRenameTemplateDraft] = useState('')
  const [versionNameDraft, setVersionNameDraft] = useState('')
  const [activeTemplateKey, setActiveTemplateKey] = useState('')
  const [activeVersionKey, setActiveVersionKey] = useState('')
  const [templateBusy, setTemplateBusy] = useState(false)
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
  }, [])

  const graphConfig = useQuery({
    queryKey: queryKeys.graph.config(projectKey),
    queryFn: getGraphConfig,
    enabled: Boolean(projectKey),
  })

  const effectiveLimit = clampGraphLimit(appliedFilters.limit)

  const effectiveQueryLimit = templateBuilder ? GRAPH_LIMIT_MAX : effectiveLimit
  const graphDataQueryKind = templateBuilder ? `${graphKind}:template_builder` : graphKind
  const graphData = useQuery({
    queryKey: queryKeys.graph.data(
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
      if (graphKind === 'policy') {
        return getPolicyGraph({
          start_date: appliedFilters.startDate,
          end_date: appliedFilters.endDate,
          state: appliedFilters.state,
          policy_type: appliedFilters.policyType,
          limit: effectiveQueryLimit,
        })
      }
      if (graphKind === 'social') {
        return getSocialGraph({
          start_date: appliedFilters.startDate,
          end_date: appliedFilters.endDate,
          platform: appliedFilters.platform,
          topic: appliedFilters.topic,
          limit: effectiveQueryLimit,
        })
      }
      return getMarketGraph({
        start_date: appliedFilters.startDate,
        end_date: appliedFilters.endDate,
        state: appliedFilters.state,
        game: appliedFilters.game,
        view: graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation'
          ? 'market_deep_entities'
          : undefined,
        topic_scope: graphKind === 'company' || graphKind === 'product' || graphKind === 'operation'
          ? graphKind
          : undefined,
        limit: effectiveQueryLimit,
      })
    },
    enabled: Boolean(projectKey),
  })

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
    const set = new Set<string>(DEFAULT_NODE_TYPES_BY_KIND[graphKind])
    const cfg = graphConfig.data?.graph_node_types || {}
    const cfgKey = graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation'
      ? 'market'
      : graphKind
    const fromCfg = Array.isArray(cfg[cfgKey]) ? cfg[cfgKey] : []
    fromCfg.forEach((t) => set.add(normalizeNodeType(t)))
    ;(effectiveGraphData.nodes || []).forEach((n) => set.add(normalizeNodeType(n.type)))
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [effectiveGraphData.nodes, graphConfig.data?.graph_node_types, graphKind])

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
      const g = groupOfType(type)
      if (!grouped[g]) grouped[g] = []
      grouped[g].push(type)
    })
    return Object.entries(grouped).sort(([a], [b]) => (GROUP_LABEL[a] || a).localeCompare((GROUP_LABEL[b] || b), 'zh-CN'))
  }, [nodeTypes])

  const defaultNodeTypesForCompute = useMemo(() => {
    if (!templateBuilder) return DEFAULT_NODE_TYPES_BY_KIND
    const allTypes = Array.from(new Set((effectiveGraphData.nodes || []).map((n) => normalizeNodeType(n.type)).filter(Boolean)))
    return {
      ...DEFAULT_NODE_TYPES_BY_KIND,
      [graphKind]: allTypes.length ? allTypes : DEFAULT_NODE_TYPES_BY_KIND[graphKind],
    }
  }, [templateBuilder, effectiveGraphData.nodes, graphKind])

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
      defaultNodeTypesByKind: defaultNodeTypesForCompute,
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
      const shapeKind = edgeShapeKind(info.sample)
      const strokeKind = EDGE_PROFILE_BY_SHAPE[shapeKind].strokeKind
      return {
        key,
        tier,
        shapeKind,
        strokeKind,
        lineType: EDGE_LINE_TYPE_BY_STROKE[strokeKind],
        label: `${edgeLegendLabel(info.sample, labels)} · ${EDGE_STROKE_LABEL[strokeKind]}`,
        count: info.count,
        color: colorByKey[key] || '#7dd3fc',
      } satisfies EdgeLegendItem
    })
    return items.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh-CN'))
  }, [topology.connectedEdges, graphConfig.data?.graph_relation_labels, paletteKey, colorDistribution])

  const edgeLegendItemByKey = useMemo(() => {
    return new Map(edgeLegendItems.map((item) => [item.key, item]))
  }, [edgeLegendItems])

  const edgeLegendGroups = useMemo(() => {
    const grouped: Record<EdgeLegendTier, EdgeLegendItem[]> = {
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
  const forceViewport = useForceGraphViewport(renderMode === 'projection3d', fullscreenWrapRef)
  const synced3DRepulsionPercent = Math.max(0, Math.min(400, visualApplied.repulsion / 1.8))
  const synced3DGravity = Math.max(0, Math.min(0.6, 0.1 * (visualApplied.gravityPercent / 100)))
  const showForceGraphCanvas = renderMode === 'projection3d' && useForceGraph3D && Boolean(ForceGraph3DComp) && !forceGraphLoadError

  useEffect(() => {
    if (projectionEngine !== 'force3d') {
      forceGraphFallbackAppliedRef.current = false
      return
    }
    if (!useForceGraph3D || !forceGraphLoadError) return
    if (forceGraphFallbackAppliedRef.current) return
    forceGraphFallbackAppliedRef.current = true
    setForceGraphFallbackNotice('3D引擎加载失败，已自动降级到 legacy-projection。')
    requestProjectionEngineChange('legacy')
  }, [projectionEngine, useForceGraph3D, forceGraphLoadError, requestProjectionEngineChange])

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
    // Avoid carrying hidden type masks across graph variants.
    setHiddenTypes({})
    setHiddenEdgeKinds({})
    setExpandedGroup(null)
    setExpandedEdgeGroup(null)
    setManualSelectedNodeKeys(new Set())
    setManualDeselectedNodeKeys(new Set())
    setRadiationSelectionByCenter({})
    setSelectionPinned(false)
    setHoverNodeKey(null)
    projectionPhysicsRef.current = { positions: {}, velocities: {} }
    projectionInteractionQuatRef.current = { x: 0, y: 0, z: 0, w: 1 }
    projectionAngularVelRef.current = { x: 0, y: 0 }
    projectionDragStateRef.current = { active: false, x: 0, y: 0 }
  }, [
    graphKind,
    setHiddenTypes,
    setHiddenEdgeKinds,
    setExpandedGroup,
    setExpandedEdgeGroup,
    setManualSelectedNodeKeys,
    setManualDeselectedNodeKeys,
    setRadiationSelectionByCenter,
    setSelectionPinned,
    setHoverNodeKey,
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
    // Safety net: if a graph has connected nodes but all become hidden by type mask,
    // auto restore visibility to avoid "empty graph" dead-end state.
    if (topology.connectedNodes.length > 0 && topology.visibleNodes.length === 0) {
      const hasAnyHidden = Object.values(hiddenTypes).some(Boolean)
      if (hasAnyHidden) {
        setHiddenTypes({})
      }
    }
  }, [topology.connectedNodes.length, topology.visibleNodes.length, hiddenTypes])

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
    setSelectedNode((prev) => {
      if (!prev) return prev
      return topology.connectedNodeKeys.has(nodeKey(prev)) ? prev : null
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

  const callApiByCandidates = useCallback(async (methodNames: string[], ...args: unknown[]) => {
    const candidate = readCandidateApiMethod(...methodNames)
    if (!candidate) {
      throw new Error(`missing_api_method:${methodNames[0] || 'unknown'}`)
    }
    return candidate.fn(...args)
  }, [])

  const loadTemplateList = useCallback(async () => {
    const raw = await callApiByCandidates(
      ['listWorkflowGraphTemplates', 'listGraphTemplates', 'listGraphDraftTemplates', 'listGraphEditTemplates', 'listWorkflows'],
    )
    const rows = Array.isArray(raw)
      ? raw
      : (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)
        ? ((raw as { items?: unknown[] }).items || [])
        : [])
    const parsed = rows.map(asTemplateRecord).filter((item): item is GraphTemplateRecord => Boolean(item))
    setTemplateItems(parsed)
    if (!activeTemplateKey && parsed[0]) setActiveTemplateKey(parsed[0].key)
    return parsed
  }, [callApiByCandidates, activeTemplateKey])

  const loadVersionList = useCallback(async (templateKey: string) => {
    if (!templateKey) {
      setVersionItems([])
      return []
    }
    const raw = await callApiByCandidates(
      ['listWorkflowGraphTemplateVersions', 'listGraphTemplateVersions', 'listGraphDraftTemplateVersions', 'listGraphVersions'],
      templateKey,
    )
    const activeVersion = raw && typeof raw === 'object'
      ? String((raw as { active_version_id?: unknown }).active_version_id || '').trim()
      : ''
    const rows = Array.isArray(raw)
      ? raw
      : (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)
        ? ((raw as { items?: unknown[] }).items || [])
        : [])
    const parsed = rows
      .map(asVersionRecord)
      .filter((item): item is GraphTemplateVersionRecord => Boolean(item))
      .map((item) => ({ ...item, activated: item.key === activeVersion || item.activated }))
    setVersionItems(parsed)
    if (activeVersion) setActiveVersionKey(activeVersion)
    else if (!activeVersionKey && parsed[0]) setActiveVersionKey(parsed[0].key)
    return parsed
  }, [callApiByCandidates, activeVersionKey])

  useEffect(() => {
    if (!editMode) return
    let canceled = false
    const run = async () => {
      setTemplateBusy(true)
      try {
        const list = await loadTemplateList()
        const key = activeTemplateKey || list[0]?.key || ''
        if (!canceled && key) await loadVersionList(key)
      } catch (error) {
        if (canceled) return
        const message = error instanceof Error ? error.message : '模板列表加载失败'
        setGraphEditStatus(`模板列表加载失败: ${message}`)
      } finally {
        if (!canceled) setTemplateBusy(false)
      }
    }
    void run()
    return () => {
      canceled = true
    }
  }, [editMode, loadTemplateList, loadVersionList, activeTemplateKey])

  useEffect(() => {
    if (!editMode) return
    const firstKey = selectedNodeKeyList[0] || ''
    if (!firstKey) return
    const node = draftNodeMap.get(firstKey)
    if (!node) return
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
  }, [editMode, selectedNodeKeyList, draftNodeMap])

  useEffect(() => {
    if (templateBuilder) setEditMode(true)
  }, [templateBuilder])

  useEffect(() => {
    setCuratedGraphId((prev) => (prev.trim() ? prev : defaultCuratedGraphId))
  }, [defaultCuratedGraphId])

  useEffect(() => {
    setCuratedHandoffTopic((prev) => (prev.trim() ? prev : defaultCuratedHandoffTopic))
  }, [defaultCuratedHandoffTopic])

  const applyCuratedState = useCallback((state: WorkflowGraphCuratedStateResponse, fallbackLabel: string) => {
    if (typeof state.revision === 'number') setCuratedRevision(state.revision)
    const status = String(state.sync_status || state.submit_status || state.rollback_status || fallbackLabel)
    const revision = typeof state.revision === 'number' ? ` r${state.revision}` : ''
    const version = state.active_version_id ? ` ${state.active_version_id}` : ''
    setCuratedStatus(`${status}${revision}${version}`)
  }, [])

  const readCuratedAudits = useCallback(async (graphId: string) => {
    const auditList = await listWorkflowGraphCuratedAudits(graphId, 10)
    const items = Array.isArray(auditList.items) ? auditList.items : []
    setCuratedAuditItems(items)
    const rollbackCandidate = items.find((item) => item.action === 'submit' && typeof item.version_id === 'string')?.version_id
    if (rollbackCandidate) {
      setCuratedRollbackVersionId((prev) => (prev.trim() ? prev : String(rollbackCandidate)))
    }
    return items
  }, [])

  const handleListCuratedAudits = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert('请填写 Curated graph_id')
      return
    }
    setCuratedBusy(true)
    try {
      const items = await readCuratedAudits(graphId)
      const latest = items[0]
      const latestText = latest ? ` latest=${String(latest.action || 'unknown')} ${String(latest.version_id || '')}`.trimEnd() : ''
      setCuratedStatus(`audit_readback items=${items.length}${latestText ? ` ${latestText}` : ''}`)
      setGraphEditStatus(`Curated audit readback 已读取: ${graphId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'audit 读取失败'
      setCuratedStatus(`audit_failed: ${message}`)
      setGraphEditStatus(`Curated audit 读取失败: ${message}`)
      window.alert(`Curated audit 读取失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, readCuratedAudits])

  const handleRollbackCuratedGraph = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    const targetVersionId = curatedRollbackVersionId.trim()
    if (!graphId) {
      window.alert('请填写 Curated graph_id')
      return
    }
    if (!targetVersionId) {
      window.alert('请填写 rollback target version_id')
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
      setGraphEditStatus(`Curated rollback 已提交: ${targetVersionId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'rollback 失败'
      setCuratedStatus(`rollback_failed: ${message}`)
      setGraphEditStatus(`Curated rollback 失败: ${message}`)
      window.alert(`Curated rollback 失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [
    applyCuratedState,
    curatedGraphId,
    curatedRevision,
    curatedRollbackReason,
    curatedRollbackVersionId,
    markDraftSaved,
    readCuratedAudits,
  ])

  const handleReplayCuratedHandoff = useCallback(async () => {
    const runId = curatedHandoffReplay.runId.trim()
    const handoffId = curatedHandoffReplay.handoffId.trim()
    if (!runId || !handoffId) {
      window.alert('请先生成带 persistence 的 handoff')
      return
    }
    setCuratedBusy(true)
    try {
      const replay = await replayWorkflowGraphHandoff(runId, handoffId)
      const events = Array.isArray(replay.events) ? replay.events : []
      setCuratedStatus(`handoff_replay_ready events=${events.length}`)
      setGraphEditStatus(`Curated handoff replay 已读取: ${handoffId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'handoff replay 失败'
      setCuratedStatus(`handoff_replay_failed: ${message}`)
      setGraphEditStatus(`Curated handoff replay 失败: ${message}`)
      window.alert(`Curated handoff replay 失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedHandoffReplay])

  const handleSyncCuratedGraph = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert('请填写 Curated graph_id')
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
      setGraphEditStatus(`Curated 已同步: ${graphId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '同步失败'
      setCuratedStatus(`sync_failed: ${message}`)
      setGraphEditStatus(`Curated 同步失败: ${message}`)
      window.alert(`Curated 同步失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedRevision, replaceDraft, applyCuratedState])

  const handleSaveCuratedDraft = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert('请填写 Curated graph_id')
      return
    }
    const dsl = buildCuratedWorkflowGraphDsl(draftNodes, draftEdges)
    if (!dsl.nodes.length) {
      window.alert('当前草稿没有可提交节点')
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
      setGraphEditStatus(`Curated draft 已保存: ${graphId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败'
      setCuratedStatus(`draft_failed: ${message}`)
      setGraphEditStatus(`Curated draft 保存失败: ${message}`)
      window.alert(`Curated draft 保存失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedRevision, draftNodes, draftEdges, applyCuratedState, markDraftSaved])

  const handleSubmitCuratedGraph = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert('请填写 Curated graph_id')
      return
    }
    const dsl = buildCuratedWorkflowGraphDsl(draftNodes, draftEdges)
    if (!dsl.nodes.length) {
      window.alert('当前草稿没有可提交节点')
      return
    }
    const temporaryIds = temporaryCuratedNodeIds(dsl)
    if (temporaryIds.length) {
      const sample = temporaryIds.slice(0, 3).join(', ')
      const message = `提交前需要把临时节点 id 改成稳定 id: ${sample}`
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
      setGraphEditStatus(`Curated graph 已提交: ${graphId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '提交失败'
      setCuratedStatus(`submit_failed: ${message}`)
      setGraphEditStatus(`Curated graph 提交失败: ${message}`)
      window.alert(`Curated graph 提交失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedRevision, draftNodes, draftEdges, applyCuratedState, markDraftSaved])

  const handleBuildCuratedReportingHandoff = useCallback(async () => {
    const graphId = curatedGraphId.trim()
    if (!graphId) {
      window.alert('请填写 Curated graph_id')
      return
    }
    const topic = curatedHandoffTopic.trim()
    if (!topic) {
      window.alert('请填写 Reporting topic')
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
      setGraphEditStatus(`Curated reporting handoff 已生成: ${handoffId || graphId}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'handoff 生成失败'
      setCuratedStatus(`report_handoff_failed: ${message}`)
      setGraphEditStatus(`Curated reporting handoff 生成失败: ${message}`)
      window.alert(`Curated reporting handoff 生成失败: ${message}`)
    } finally {
      setCuratedBusy(false)
    }
  }, [curatedGraphId, curatedHandoffTopic, selectedEditableNodes])

  const selectedExportPayload = useMemo(() => {
    const scopedTopicFocus = graphKind === 'company' || graphKind === 'product' || graphKind === 'operation'
      ? graphKind
      : undefined
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
  }, [selectedNodeKeys, connectedNodeMap, visibleEdges, topology.edgeResolvedKeyMap, projectKey, graphKind, dashboardParams, dashboard.llmAssist])

  const clueChainSeedNodes = useMemo<ClueChainSeedNode[]>(() => {
    const selectedSeeds = selectedExportPayload.selected_nodes.map((node) => ({
      node_id: String(node.id || node.entry_id || '').trim(),
      node_type: String(node.type || '').trim() || 'Entity',
      entry_id: String(node.entry_id || node.id || '').trim(),
      label: String(node.label || node.id || '').trim() || '未命名节点',
    })).filter((node) => node.node_id)
    if (selectedSeeds.length) return selectedSeeds
    return topology.visibleNodes.slice(0, 3).map((node) => ({
      node_id: String(node.id || '').trim(),
      node_type: String(node.type || '').trim() || 'Entity',
      entry_id: String(node.entry_id || node.id || '').trim(),
      label: nodeName(node),
    })).filter((node) => node.node_id)
  }, [selectedExportPayload.selected_nodes, topology.visibleNodes])

  const handleCreateClueChain = useCallback(async () => {
    if (!clueChainSeedNodes.length) {
      window.alert('当前图谱没有可用于创建 Chain 的节点')
      return
    }
    setClueChainBusy(true)
    setClueChainStatus('正在创建 Chain...')
    try {
      const chain = await createClueChain({
        project_key: projectKey,
        graph_type: graphKind,
        title: `${TYPE_LABEL[variant]} · ${clueChainSeedNodes[0]?.label || 'Clue Chain'}`,
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
      setClueChainStatus(`已创建 ${chain.chain_id}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建失败'
      setClueChainStatus(`创建失败: ${message}`)
      window.alert(`Clue Chain 创建失败: ${message}`)
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
  ])

  const handleRunClueChainExpand = useCallback(async (mode: 'source_library' | 'external_search') => {
    if (!activeClueChain) return
    setClueChainBusy(true)
    setClueChainStatus(`正在运行 ${mode === 'source_library' ? 'Source Library' : 'External Search'} hop...`)
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
      setClueChainStatus(`${mode === 'source_library' ? 'Source Library' : 'External Search'} hop 完成`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '展开失败'
      setClueChainStatus(`展开失败: ${message}`)
      window.alert(`Clue Chain 展开失败: ${message}`)
    } finally {
      setClueChainBusy(false)
    }
  }, [activeClueChain, clueChainSeedNodes, graphKind, projectKey])

  const handleReviewClueChainCandidate = useCallback(async (candidateId: string, decision: 'promote' | 'reject') => {
    if (!activeClueChain) return
    setClueChainBusy(true)
    setClueChainStatus(decision === 'promote' ? '正在记录 Promote decision...' : '正在记录 Reject decision...')
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
      setClueChainStatus(decision === 'promote' ? '已记录 Promote decision' : '已记录 Reject decision')
    } catch (error) {
      const message = error instanceof Error ? error.message : '审核失败'
      setClueChainStatus(`审核失败: ${message}`)
      window.alert(`Clue Chain 候选审核失败: ${message}`)
    } finally {
      setClueChainBusy(false)
    }
  }, [activeClueChain])

  const copyStructuredPayload = async () => {
    const text = JSON.stringify(selectedExportPayload, null, 2)
    await navigator.clipboard.writeText(text)
  }

  const submitStructuredTasks = async (flowType: 'collect' | 'source_collect') => {
    if (!selectedExportPayload.selected_nodes.length) {
      window.alert('请先选择节点')
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
      const message = error instanceof Error ? error.message : '提交失败'
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
        id: `${index}-${otherKey}-${pred || '关联'}`,
        direction: outbound ? 'OUT' : 'IN',
        relation: pred || '关联',
        targetName: other ? nodeName(other) : otherKey,
        targetType: other?.type || '-',
      })
      if (pred) {
        const group = relationsByPredicate.get(pred) || []
        group.push({
          id: `${index}-${otherKey}-${pred || '关联'}-pred`,
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
  }, [selectedNode, topology.connectedNodeKeys, topology.connectedEdges, topology.edgeResolvedKeyMap, connectedNodeMap])

  const selectedNodeKey = useMemo(() => {
    if (!selectedNode) return null
    const key = nodeKey(selectedNode)
    return topology.connectedNodeKeys.has(key) ? key : null
  }, [selectedNode, topology.connectedNodeKeys])

  const forceGraphData = useMemo(() => {
    if (renderMode !== 'projection3d') return { nodes: [] as Array<{ id: string; key: string; name: string; rawNode: GraphNodeItem; score: number; x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number }>, links: [] as Array<{ source: string; target: string }> }
    const nodes = topology.connectedNodes.map((node) => {
      const key = nodeKey(node)
      const score = topology.scoreMap.get(key) || 0
      const prev = forceNodePhysicsRef.current.get(key) || {}
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
  }, [renderMode, topology.connectedNodes, topology.connectedEdges, topology.scoreMap, topology.edgeResolvedKeyMap])

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
    if (renderMode !== 'projection3d') return new Map<string, { color: string; width: number; opacity: number }>()
    const map = new Map<string, { color: string; width: number; opacity: number }>()
    const enableAutoFocusDim = autoFocusEnabled && forceAutoFocusSet.size > 0
    const edgeAlphaT = Math.max(0, Math.min(1, visualApplied.edgeAlpha / 100))
    topology.connectedEdges.forEach((edge) => {
      const resolved = topology.edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      const fromKey = resolved.fromKey
      const toKey = resolved.toKey
      const style = edgeLegendItemByKey.get(edgeLegendKey(edge))
      const colorHex = style?.color || '#7dd3fc'
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
            : Math.max(0.5, (EDGE_WIDTH_BY_TIER[style?.tier || 'type'] || 1.2) * (visualApplied.edgeWidth / 100)),
          opacity: dimByAutoFocus ? 0.08 : Math.max(0.08, edgeAlphaT),
        },
      )
    })
    return map
  }, [renderMode, topology.connectedEdges, topology.edgeResolvedKeyMap, edgeLegendItemByKey, visualApplied.edgeWidth, visualApplied.edgeAlpha, autoFocusEnabled, forceAutoFocusSet])

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
    if (!useForceGraph3D) return
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
  }, [useForceGraph3D, selectedNodeKeys, selectedNodeKeysRef, forceGraphData.nodes, autoFocusEnabled, forceAutoFocusSet, applyForceObjectVisualState])

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
      if (useForceGraph3D) {
        forceGraphRef.current?.resumeAnimation?.()
      } else {
        forceGraphRef.current?.pauseAnimation?.()
      }
    } catch {
      // noop
    }
  }, [useForceGraph3D])

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
    setPhysicsFrame((prev) => (prev >= 1000000 ? 0 : prev + 1))
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
      setChartReady(false)
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
          // Prioritize frame throughput over retina sharpness for smoother motion.
          devicePixelRatio: 1,
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
    const shouldShowNodeLabel = visualApplied.showLabel && visibleNodes.length <= 220
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
      const show = shouldShowNodeLabel && size >= 24
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
      const tier = style?.tier || 'type'
      const shapeKind = style?.shapeKind || edgeShapeKind(edge)
      const profile = EDGE_PROFILE_BY_SHAPE[shapeKind]
      const strokeKind = style?.strokeKind || profile.strokeKind
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
      const baseCurveness = edge.type === 'POLICY_RELATION' ? 0.18 : EDGE_CURVENESS_BY_STROKE[strokeKind]
      const resolvedEdgeAlpha = edgeAlphaT
      const baseColor = dimByFocus
        ? 'rgba(125, 211, 252, 0.04)'
        : `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, resolvedEdgeAlpha))})`
      const baseWidth = dimByFocus ? 0.7 : Math.max(0, EDGE_WIDTH_BY_TIER[tier] * widthFactor)
      const baseLine = {
        source: fromKey,
        target: toKey,
        value: edge,
        symbol: hideEdgeSymbol ? (['none', 'none'] as [EdgeSymbolName, EdgeSymbolName]) : profile.symbol,
        symbolSize: hideEdgeSymbol ? ([0, 0] as [number, number]) : scaledSymbolSize,
        lineStyle: {
          color: baseColor,
          width: baseWidth,
          type: style?.lineType || EDGE_LINE_TYPE_BY_STROKE[strokeKind],
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
              return `类型: ${node.type || '-'}<br/>名称: ${node.name || '-'}`
            }
            if (params.dataType === 'edge') {
              const edge = (params.data?.value || {}) as GraphEdgeItem
              const classToken = String(edge.relation_class || '').trim().toLowerCase()
              const classLabel = classToken ? (RELATION_CLASS_LABEL[classToken] || classToken) : ''
              const predicate = String(edge.predicate || '').trim()
              const shapeKind = edgeShapeKind(edge)
              const strokeKind = EDGE_PROFILE_BY_SHAPE[shapeKind].strokeKind
              return `关系: ${edge.type || 'REL'}${classLabel ? `<br/>大类: ${classLabel}` : ''}${predicate ? `<br/>谓词: ${predicate}` : ''}<br/>线型: ${EDGE_STROKE_LABEL[strokeKind]}`
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
  }, [topology, visibleEdges, edgeLegendItemByKey, visualApplied, nodeTypeColor, graphKind, chartReady, isFullscreen, selectedNodeKeys, selectionPinned, adjacencyConnectedMap, hoverNodeKey, autoFocusEnabled, selectedNode, selectedNodeKey, renderMode, selectionEnabled, projectionRotateX, projectionRotateY, projectionRotateZ, synced3DRepulsionPercent, physicsFrame, useLegacyProjection3D, useForceGraph3D])

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
  }, [scheduleForceHoverNodeKey, toggleForceNodeSelectionByKey, autoFocusEnabledRef, selectionEnabledRef])

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
    const dataNodes = forceGraphData.nodes.length
    const emptyDataNodes = forceGraphData.nodes.reduce((acc, item) => {
      const rawNode = (item as { rawNode?: GraphNodeItem }).rawNode
      return resolveNodeSymbol(rawNode?.type || '').startsWith('empty') ? acc + 1 : acc
    }, 0)
    return {
      dataNodes,
      sceneNodeObjects,
      emptyDataNodes,
      emptySceneNodeObjects,
    }
  }, [forceGraphData.nodes])

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
    setGraphEditStatus(`已新增节点: ${key}`)
  }, [createDraftNode, newNodeType, newNodeName])

  const handleDeleteSelectedDraftNodes = useCallback(() => {
    const result = removeDraftNodesByKeys(selectedNodeKeyList)
    if (!result.removedNodes) {
      setGraphEditStatus('未删除节点：当前选择为空或节点不在草稿中')
      return
    }
    setManualSelectedNodeKeys(new Set())
    setManualDeselectedNodeKeys(new Set())
    setRadiationSelectionByCenter({})
    setGraphEditStatus(`已删除节点 ${result.removedNodes}，关联边 ${result.removedEdges}`)
  }, [removeDraftNodesByKeys, selectedNodeKeyList, setManualSelectedNodeKeys, setManualDeselectedNodeKeys, setRadiationSelectionByCenter])

  const handleCreateDraftEdge = useCallback(() => {
    const sourceKey = edgeDraft.sourceKey.trim()
    const targetKey = edgeDraft.targetKey.trim()
    if (!sourceKey || !targetKey) {
      window.alert('请选择 source 和 target 节点')
      return
    }
    const created = createDraftEdgeByNodeKeys(sourceKey, targetKey, {
      type: edgeDraft.relation.trim() || 'REL',
      predicate: edgeDraft.relation.trim() || undefined,
    })
    if (!created.ok) {
      if (created.reason === 'already_exists') window.alert('边已存在')
      else window.alert('创建边失败：节点不存在')
      return
    }
    setGraphEditStatus(`已新增边: ${sourceKey} -> ${targetKey}`)
  }, [edgeDraft, createDraftEdgeByNodeKeys])

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
      window.alert('节点更新失败：节点可能已被删除')
      return
    }
    setGraphEditStatus(`已更新节点: ${nodeEditDraft.key}`)
  }, [nodeEditDraft, updateDraftNodeByKey])

  const handleLoadTemplateVersions = useCallback(async () => {
    if (!activeTemplateKey) return
    setTemplateBusy(true)
    try {
      await loadVersionList(activeTemplateKey)
      setGraphEditStatus(`已加载模板版本列表: ${activeTemplateKey}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '版本列表加载失败'
      setGraphEditStatus(`版本列表加载失败: ${message}`)
      window.alert(`版本列表加载失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, loadVersionList])

  const handleCreateTemplate = useCallback(async () => {
    const name = templateNameDraft.trim()
    if (!name) return
    setTemplateBusy(true)
    try {
      const templateId = name.replace(/\s+/g, '_')
      await callApiByCandidates(
        ['createWorkflowGraphTemplate', 'createGraphTemplate', 'createGraphDraftTemplate', 'upsertGraphTemplate'],
        {
          template_id: templateId,
          name,
          dsl: { nodes: draftNodes, edges: draftEdges },
        },
      )
      setTemplateNameDraft('')
      setGraphEditStatus(`模板创建成功: ${name}`)
      await loadTemplateList()
    } catch (error) {
      const message = error instanceof Error ? error.message : '模板创建失败'
      setGraphEditStatus(`模板创建失败: ${message}`)
      window.alert(`模板创建失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [templateNameDraft, callApiByCandidates, draftNodes, draftEdges, loadTemplateList])

  const handleRenameTemplate = useCallback(async () => {
    if (!activeTemplateKey) return
    const name = renameTemplateDraft.trim()
    if (!name) return
    setTemplateBusy(true)
    try {
      await callApiByCandidates(
        ['updateWorkflowGraphTemplate', 'renameGraphTemplate', 'renameGraphDraftTemplate'],
        activeTemplateKey,
        { name },
      )
      setRenameTemplateDraft('')
      setGraphEditStatus(`模板已重命名为: ${name}`)
      await loadTemplateList()
    } catch (error) {
      const message = error instanceof Error ? error.message : '模板重命名失败'
      setGraphEditStatus(`模板重命名失败: ${message}`)
      window.alert(`模板重命名失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, renameTemplateDraft, callApiByCandidates, loadTemplateList])

  const handleDeleteTemplate = useCallback(async () => {
    if (!activeTemplateKey) return
    setTemplateBusy(true)
    try {
      await callApiByCandidates(
        ['deleteWorkflowGraphTemplate', 'deleteGraphTemplate', 'deleteGraphDraftTemplate', 'deleteWorkflowTemplate'],
        activeTemplateKey,
      )
      setGraphEditStatus(`模板已删除: ${activeTemplateKey}`)
      setActiveTemplateKey('')
      setActiveVersionKey('')
      setVersionItems([])
      await loadTemplateList()
    } catch (error) {
      const message = error instanceof Error ? error.message : '模板删除失败'
      setGraphEditStatus(`模板删除失败: ${message}`)
      window.alert(`模板删除失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, callApiByCandidates, loadTemplateList])

  const handleSaveVersion = useCallback(async () => {
    if (!activeTemplateKey) {
      window.alert('请先选择模板')
      return
    }
    const versionName = versionNameDraft.trim() || `v-${new Date().toISOString()}`
    setTemplateBusy(true)
    try {
      await callApiByCandidates(
        ['createWorkflowGraphTemplateVersion', 'saveGraphTemplateVersion', 'createGraphTemplateVersion', 'saveGraphVersion'],
        activeTemplateKey,
        { version_id: versionName, dsl: { nodes: draftNodes, edges: draftEdges } },
      )
      setVersionNameDraft('')
      setGraphEditStatus(`已保存版本: ${versionName}`)
      await loadVersionList(activeTemplateKey)
      markDraftSaved()
    } catch (error) {
      const message = error instanceof Error ? error.message : '版本保存失败'
      setGraphEditStatus(`版本保存失败: ${message}`)
      window.alert(`版本保存失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, versionNameDraft, callApiByCandidates, draftNodes, draftEdges, loadVersionList, markDraftSaved])

  const handleLoadVersion = useCallback(async () => {
    if (!activeTemplateKey || !activeVersionKey) return
    setTemplateBusy(true)
    try {
      const raw = await callApiByCandidates(
        ['getWorkflowGraphTemplateVersion', 'loadGraphTemplateVersion', 'getGraphTemplateVersion'],
        activeTemplateKey,
        activeVersionKey,
      )
      const payload = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
      const versionPayload = payload.version && typeof payload.version === 'object' ? payload.version as Record<string, unknown> : payload
      const dslPayload = versionPayload.dsl && typeof versionPayload.dsl === 'object' ? versionPayload.dsl as Record<string, unknown> : versionPayload
      const nextNodes = Array.isArray(dslPayload.nodes) ? dslPayload.nodes as GraphNodeItem[] : []
      const nextEdges = Array.isArray(dslPayload.edges) ? dslPayload.edges as GraphEdgeItem[] : []
      if (!nextNodes.length && !nextEdges.length) {
        window.alert('加载版本成功，但返回为空')
      }
      replaceDraft(nextNodes, nextEdges, { markAsDirty: true })
      setGraphEditStatus(`已加载版本: ${activeVersionKey}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '版本加载失败'
      setGraphEditStatus(`版本加载失败: ${message}`)
      window.alert(`版本加载失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, activeVersionKey, callApiByCandidates, replaceDraft])

  const handleActivateVersion = useCallback(async () => {
    if (!activeTemplateKey || !activeVersionKey) return
    setTemplateBusy(true)
    try {
      await callApiByCandidates(
        ['activateWorkflowGraphTemplateVersion', 'activateGraphTemplateVersion', 'activateGraphVersion'],
        activeTemplateKey,
        activeVersionKey,
      )
      setGraphEditStatus(`已激活版本: ${activeVersionKey}`)
      await loadVersionList(activeTemplateKey)
    } catch (error) {
      const message = error instanceof Error ? error.message : '版本激活失败'
      setGraphEditStatus(`版本激活失败: ${message}`)
      window.alert(`版本激活失败: ${message}`)
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, activeVersionKey, callApiByCandidates, loadVersionList])

  const handleForceGraphRenderError = useCallback((message: string) => {
    setForceGraphFallbackNotice(`3D引擎渲染失败，已自动降级到 legacy-projection。${message ? ` (${message})` : ''}`)
    requestProjectionEngineChange('legacy')
  }, [requestProjectionEngineChange])

  const forceGraphRenderBoundaryKey = `${renderMode}:${projectionEngine}:${forceGraphData.nodes.length}:${forceGraphData.links.length}`

  const forceGraphCanvasNode = useMemo(() => {
    if (!(renderMode === 'projection3d' && showForceGraphCanvas && ForceGraph3DComp)) return null
    return (
      <div
        ref={forceChartRef}
        className="gv2-chart gv2-chart--force3d"
        data-testid="graph-force3d-canvas-host"
        style={showForceGraphCanvas ? undefined : { display: 'none' }}
      >
        <ForceGraphRenderBoundary
          resetKey={forceGraphRenderBoundaryKey}
          onError={handleForceGraphRenderError}
        >
          <ForceGraph3DComp
            ref={forceGraphRef}
            width={forceViewport.width}
            height={forceViewport.height}
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
            linkOpacity={(link: unknown) => {
              const { source, target } = linkEnds(link)
              return Number(forceLinkStyleByKey.get(`${source}>${target}`)?.opacity || Math.max(0.06, Math.min(1, visualApplied.edgeAlpha / 100)))
            }}
            onNodeHover={handleForceNodeHover}
            onNodeClick={handleForceNodeClick}
            onNodeRightClick={handleForceNodeRightClick}
            onBackgroundClick={handleForceBackgroundClick}
            onEngineTick={() => {
              const next = new Map<string, ForceNodePhysics>()
              forceGraphData.nodes.forEach((node) => {
                const id = String(node.id || '')
                if (!id) return
                next.set(id, {
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
    ForceGraph3DComp,
    forceGraphRenderBoundaryKey,
    forceViewport.width,
    forceViewport.height,
    forceGraphData,
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
  ])

  const detachProjectionControls = renderMode === 'projection3d' && activeRendererCapabilities.supportsProjectionControls
  const projectionControlSection = activeRendererCapabilities.supportsProjectionControls ? (
    <label className="gv2-control-chip">
      3D引擎
      <select
        value={projectionEngine}
        onChange={(e) => requestProjectionEngineChange(e.target.value as ProjectionEngine)}
      >
        <option value="legacy">legacy-projection</option>
        <option value="force3d">react-force-graph-3d</option>
      </select>
    </label>
  ) : null

  return (
    <div className="content-stack gv2-root">
      <section className="panel gv2-main">
        <div className="gv2-layout">
          <div
            className={`gv2-chart-wrap gv2-chart-wrap--fullscreen-ready ${isFullscreen ? 'is-fullscreen' : ''}`}
            ref={fullscreenWrapRef}
          >
            {graphData.isFetching ? <div className="gv2-loading">加载中...</div> : null}
            {graphData.error ? (
              <div className="gv2-loading gv2-loading-error">
                加载失败：{graphData.error instanceof Error ? graphData.error.message : '请求异常'}
              </div>
            ) : null}
            <div
              ref={chartRef}
              className="gv2-chart"
              style={showForceGraphCanvas ? { display: 'none' } : undefined}
            />
            {forceGraphCanvasNode}
            {useForceGraph3D && !ForceGraph3DComp ? (
              <div className="gv2-loading">3D引擎加载中...</div>
            ) : null}
            {useForceGraph3D && forceGraphLoadError ? (
              <div className="gv2-loading gv2-loading-error">3D引擎加载失败：{forceGraphLoadError}</div>
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
                  重试 force3d
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
                选择模式
              </button>
              {templateBuilder ? (
              <button
                type="button"
                className={`gv2-select-mode-btn ${editMode ? '' : 'is-off'}`.trim()}
                onClick={() => setEditMode((prev) => !prev)}
                title="编辑模式下可本地增删改节点与边"
              >
                编辑模式{isDraftDirty ? ' *' : ''}
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
                title="基于当前节点详情自动隐没无关节点（与选择模式独立）"
              >
                聚焦隐没
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${renderMode === 'projection3d' ? '' : 'is-off'}`.trim()}
                onClick={() => requestRenderModeChange(renderMode === '2d' ? 'projection3d' : '2d')}
                title="轻量3D模型模式（中心锁定，非相机视角）"
              >
                {renderMode === 'projection3d' ? '回到2D' : '3D模式'}
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${showSymbolDebug ? '' : 'is-off'}`.trim()}
                onClick={() => setShowSymbolDebug((v) => !v)}
                title="显示节点类型到GL符号的映射调试信息"
              >
                符号调试
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${selectionPinned ? '' : 'is-off'}`.trim()}
                onClick={() => setSelectionPinned((v) => !v)}
                disabled={!selectedNodeKeys.size}
              >
                固化选中
              </button>
              <button
                type="button"
                onClick={() => setTaskModalOpen(true)}
                disabled={!selectedNodeKeys.size}
              >
                结构化任务（{selectedNodeKeys.size}）
              </button>
              <button
                type="button"
                className="gv2-select-mode-btn"
                data-testid="graph-create-clue-chain"
                onClick={() => void handleCreateClueChain()}
                disabled={clueChainBusy || !clueChainSeedNodes.length}
                title="从当前选中节点创建 Clue Chain；未选中时使用当前图谱上下文"
              >
                {clueChainBusy ? <LoaderCircle size={14} className="spinning" /> : <GitBranchPlus size={14} />}
                Chain（{selectedNodeKeys.size || clueChainSeedNodes.length}）
              </button>
              <button onClick={async () => { await graphData.refetch() }} disabled={graphData.isFetching}>刷新</button>
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
                    console.warn('Fullscreen toggle failed:', error)
                  }
                }}
              >
                {isFullscreen ? '退出全屏' : '全屏'}
              </button>
              <button onClick={() => setShowOverlay((v) => !v)}>{showOverlay ? '收起面板' : '展开面板'}</button>
              {nodeDragCapturedFx ? <span className="gv2-drag-captured">已捕获</span> : null}
              </div>
            </div>
            {renderMode === 'projection3d' && !isFullscreen ? (
              <div className="gv2-graph-controls-hint">
                force-graph 左拖旋转；选择模式下右键节点切换一跳邻域
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
                  <strong>视图调节</strong>
                  <span>{controlSectionOpen.view ? '收起' : '展开'}</span>
                </button>
                {controlSectionOpen.view ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip">
                      斥力
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
                      引力
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
                      节点尺寸
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
                      中心化增强
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
                      邻近数增强
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
                      节点透明
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
                      边粗细
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
                      边透明
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
                      显示标签
                    </label>
                    <div className="gv2-control-chip">
                      <span>已选 {selectedNodeKeys.size}</span>
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
                        清空
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
                  <strong>图谱编辑与模板</strong>
                  <span>{controlSectionOpen.edit ? '收起' : '展开'}</span>
                </button>
                {controlSectionOpen.edit ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip gv2-checkbox">
                      <input type="checkbox" checked={editMode} onChange={(e) => setEditMode(e.target.checked)} />
                      Edit Mode（本地 Draft）
                    </label>
                    <div className="gv2-control-chip">
                      <span>Draft: nodes={draftNodes.length} edges={draftEdges.length} {isDraftDirty ? '· dirty' : '· clean'}</span>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          resetDraft()
                          setGraphEditStatus('已重置为远端图谱快照')
                        }}
                        disabled={!isDraftDirty}
                      >
                        放弃本地修改
                      </button>
                    </div>
                    <label className="gv2-control-chip" data-testid="graph-curated-panel">
                      Curated graph_id
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
                        保存 Curated Draft
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-submit"
                        onClick={() => void handleSubmitCuratedGraph()}
                        disabled={!editMode || curatedBusy || !draftNodes.length}
                      >
                        提交 Curated Graph
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-sync"
                        onClick={() => void handleSyncCuratedGraph()}
                        disabled={!editMode || curatedBusy}
                      >
                        同步 Curated
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-audit"
                        onClick={() => void handleListCuratedAudits()}
                        disabled={!editMode || curatedBusy}
                      >
                        读取 Audit
                      </button>
                    </div>
                    <div className="gv2-control-chip">
                      <label>
                        Rollback version
                        <input
                          data-testid="graph-curated-rollback-version"
                          value={curatedRollbackVersionId}
                          onChange={(e) => setCuratedRollbackVersionId(e.target.value)}
                          disabled={!editMode || curatedBusy}
                        />
                      </label>
                      <input
                        aria-label="Rollback reason"
                        data-testid="graph-curated-rollback-reason"
                        value={curatedRollbackReason}
                        onChange={(e) => setCuratedRollbackReason(e.target.value)}
                        placeholder="reason"
                        disabled={!editMode || curatedBusy}
                      />
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-rollback"
                        onClick={() => void handleRollbackCuratedGraph()}
                        disabled={!editMode || curatedBusy || !curatedRollbackVersionId.trim()}
                      >
                        执行 Rollback
                      </button>
                    </div>
                    {curatedAuditItems.length ? (
                      <div className="status-line" data-testid="graph-curated-audit-list">
                        Audit: {curatedAuditItems.slice(0, 3).map((item) => (
                          `${String(item.action || 'unknown')}#${String(item.version_id || item.audit_id || 'n/a')}`
                        )).join(' / ')}
                      </div>
                    ) : null}
                    <label className="gv2-control-chip">
                      Reporting topic
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
                        生成 Reporting Handoff
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid="graph-curated-handoff-replay"
                        onClick={() => void handleReplayCuratedHandoff()}
                        disabled={!editMode || curatedBusy || !curatedHandoffReplay.runId || !curatedHandoffReplay.handoffId}
                      >
                        回放 Handoff
                      </button>
                    </div>
                    <div className="status-line" data-testid="graph-curated-status">
                      {curatedBusy ? 'Curated API 调用中...' : (curatedStatus || 'Curated API：就绪')}
                    </div>
                    <label className="gv2-control-chip">
                      新节点类型
                      <input value={newNodeType} onChange={(e) => setNewNodeType(e.target.value)} disabled={!editMode} />
                    </label>
                    <label className="gv2-control-chip">
                      新节点名称
                      <input value={newNodeName} onChange={(e) => setNewNodeName(e.target.value)} disabled={!editMode} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={handleCreateDraftNode} disabled={!editMode}>新增节点</button>
                      <button type="button" className="secondary" onClick={handleDeleteSelectedDraftNodes} disabled={!editMode || !selectedNodeKeyList.length}>
                        删除选中节点（{selectedNodeKeyList.length}）
                      </button>
                    </div>
                    <label className="gv2-control-chip">
                      边 Source
                      <select value={edgeDraft.sourceKey} onChange={(e) => setEdgeDraft((prev) => ({ ...prev, sourceKey: e.target.value }))} disabled={!editMode}>
                        <option value="">选择 source</option>
                        {editableNodeItems.map((item) => (
                          <option key={item.key} value={item.key}>{item.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      边 Target
                      <select value={edgeDraft.targetKey} onChange={(e) => setEdgeDraft((prev) => ({ ...prev, targetKey: e.target.value }))} disabled={!editMode}>
                        <option value="">选择 target</option>
                        {editableNodeItems.map((item) => (
                          <option key={item.key} value={item.key}>{item.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      关系
                      <input value={edgeDraft.relation} onChange={(e) => setEdgeDraft((prev) => ({ ...prev, relation: e.target.value }))} placeholder="REL / influences" disabled={!editMode} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={handleCreateDraftEdge} disabled={!editMode}>创建边 {'source->target'}</button>
                    </div>
                    <label className="gv2-control-chip">
                      节点编辑对象
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
                        <option value="">选择节点</option>
                        {selectedEditableNodes.map((node) => {
                          const key = nodeKey(node)
                          return <option key={key} value={key}>{nodeName(node)} ({key})</option>
                        })}
                      </select>
                    </label>
                    {activeEditableNode ? (
                      <>
                        <label className="gv2-control-chip">id<input value={nodeEditDraft.id} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, id: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">type<input value={nodeEditDraft.type} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, type: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">name<input value={nodeEditDraft.name} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, name: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">title<input value={nodeEditDraft.title} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, title: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">x<input value={nodeEditDraft.x} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, x: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">y<input value={nodeEditDraft.y} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, y: e.target.value }))} disabled={!editMode} /></label>
                        <label className="gv2-control-chip">z<input value={nodeEditDraft.z} onChange={(e) => setNodeEditDraft((prev) => ({ ...prev, z: e.target.value }))} disabled={!editMode} /></label>
                        <div className="gv2-control-chip">
                          <button type="button" onClick={handleApplyNodeEditDraft} disabled={!editMode}>应用节点字段</button>
                        </div>
                      </>
                    ) : null}
                    <label className="gv2-control-chip">
                      模板列表
                      <select
                        value={activeTemplateKey}
                        onChange={(e) => {
                          const key = e.target.value
                          setActiveTemplateKey(key)
                          void loadVersionList(key)
                        }}
                        disabled={!editMode || templateBusy}
                      >
                        <option value="">选择模板</option>
                        {templateItems.map((item) => (
                          <option key={item.key} value={item.key}>
                            {item.name}{item.activeVersion ? ` (active:${item.activeVersion})` : ''}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      创建模板
                      <input value={templateNameDraft} onChange={(e) => setTemplateNameDraft(e.target.value)} placeholder="template name" disabled={!editMode || templateBusy} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={() => void handleCreateTemplate()} disabled={!editMode || templateBusy || !templateNameDraft.trim()}>创建模板</button>
                      <button type="button" className="secondary" onClick={() => void loadTemplateList()} disabled={!editMode || templateBusy}>刷新模板列表</button>
                    </div>
                    <label className="gv2-control-chip">
                      模板重命名
                      <input value={renameTemplateDraft} onChange={(e) => setRenameTemplateDraft(e.target.value)} placeholder="new name" disabled={!editMode || !activeTemplateKey || templateBusy} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={() => void handleRenameTemplate()} disabled={!editMode || !activeTemplateKey || !renameTemplateDraft.trim() || templateBusy}>重命名</button>
                      <button type="button" className="secondary" onClick={() => void handleDeleteTemplate()} disabled={!editMode || !activeTemplateKey || templateBusy}>删除模板</button>
                    </div>
                    <label className="gv2-control-chip">
                      版本列表
                      <select value={activeVersionKey} onChange={(e) => setActiveVersionKey(e.target.value)} disabled={!editMode || !activeTemplateKey || templateBusy}>
                        <option value="">选择版本</option>
                        {versionItems.map((item) => (
                          <option key={item.key} value={item.key}>{item.name}{item.activated ? ' (active)' : ''}</option>
                        ))}
                      </select>
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" className="secondary" onClick={() => void handleLoadTemplateVersions()} disabled={!editMode || !activeTemplateKey || templateBusy}>刷新版本</button>
                    </div>
                    <label className="gv2-control-chip">
                      保存版本名
                      <input value={versionNameDraft} onChange={(e) => setVersionNameDraft(e.target.value)} placeholder="version name" disabled={!editMode || templateBusy} />
                    </label>
                    <div className="gv2-control-chip">
                      <button type="button" onClick={() => void handleSaveVersion()} disabled={!editMode || !activeTemplateKey || templateBusy}>保存版本</button>
                      <button type="button" className="secondary" onClick={() => void handleLoadVersion()} disabled={!editMode || !activeTemplateKey || !activeVersionKey || templateBusy}>加载版本</button>
                      <button type="button" className="secondary" onClick={() => void handleActivateVersion()} disabled={!editMode || !activeTemplateKey || !activeVersionKey || templateBusy}>激活版本</button>
                    </div>
                    <div className="status-line">
                      {templateBusy ? '模板/版本操作中...' : (graphEditStatus || '编辑状态：就绪')}
                    </div>
                    <div className="gv2-control-chip">
                      <span>草稿边数量 {editableEdges.length}</span>
                    </div>
                    {editableEdges.slice(0, 8).map((edge) => (
                      <div key={edge.key} className="gv2-control-chip">
                        <span>{edge.label}</span>
                        <button type="button" className="secondary" onClick={() => removeDraftEdgeAt(edge.index)} disabled={!editMode}>删除</button>
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
                  <strong>配色调节</strong>
                  <span>{controlSectionOpen.color ? '收起' : '展开'}</span>
                </button>
                {controlSectionOpen.color ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip">
                      色系主题
                      <select value={paletteKey} onChange={(e) => setPaletteKey(e.target.value as PaletteKey)}>
                        {Object.entries(GRAPH_COLOR_THEMES).map(([key, val]) => (
                          <option key={key} value={key}>{val.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      色差旋转
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
                      绝对色差
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
                  <strong>数据筛选</strong>
                  <span>{controlSectionOpen.filter ? '收起' : '展开'}</span>
                </button>
                {controlSectionOpen.filter ? (
                  <div className="gv2-control-section-body">
                    <label className="gv2-control-chip">
                      开始日期
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
                      结束日期
                      <input
                        type="date"
                        value={endDate}
                        onChange={(e) => {
                          setEndDate(e.target.value)
                          if (filterApplyError) setFilterApplyError('')
                        }}
                      />
                    </label>
                    {(graphKind === 'policy' || graphKind === 'market' || graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation') ? (
                      <label className="gv2-control-chip">
                        州
                        <input value={state} placeholder="CA / NY / TX" onChange={(e) => setState(e.target.value)} />
                      </label>
                    ) : null}
                    {graphKind === 'policy' ? (
                      <label className="gv2-control-chip">
                        政策类型
                        <input value={policyType} placeholder="regulation / bill" onChange={(e) => setPolicyType(e.target.value)} />
                      </label>
                    ) : null}
                    {graphKind === 'social' ? (
                      <>
                        <label className="gv2-control-chip">
                          平台
                          <input value={platform} placeholder="reddit / twitter" onChange={(e) => setPlatform(e.target.value)} />
                        </label>
                        <label className="gv2-control-chip">
                          主题
                          <input value={topic} placeholder="关键词" onChange={(e) => setTopic(e.target.value)} />
                        </label>
                      </>
                    ) : null}
                    {(graphKind === 'market' || graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation') ? (
                      <label className="gv2-control-chip">
                        游戏
                        <input value={game} placeholder="游戏名" onChange={(e) => setGame(e.target.value)} />
                      </label>
                    ) : null}
                    <label className="gv2-control-chip">
                      数量限制
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
                      排序策略
                      <select value={rankingStrategy} onChange={(e) => setRankingStrategy(e.target.value as NodeRankStrategy)}>
                        <option value="doc_body">数据本体排序</option>
                        <option value="node_connectivity">节点关联度排序</option>
                        <option value="doc_id">文档ID排序</option>
                      </select>
                    </label>
                    <label className="gv2-control-chip">
                      中心度权重
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
                      邻域度权重
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
                            setFilterApplyError('开始日期不能晚于结束日期')
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
                        应用筛选
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
                        重置
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
                      title={GROUP_LABEL[group] || group}
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
                      <span className="gv2-legend-node-label">{GROUP_LABEL[group] || group}</span>
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
                  <div className="gv2-legend-section-title">边图例</div>
                  <div className="gv2-legend-groups gv2-edge-legend-groups">
                    {edgeLegendGroups.map(([tier, items]) => {
                      const sample = items[0]
                      const active = expandedEdgeGroup === tier
                      return (
                        <button
                          key={tier}
                          type="button"
                          className={`gv2-legend-node gv2-edge-legend-node ${active ? 'is-active' : ''}`}
                          title={EDGE_TIER_LABEL[tier]}
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
                          <span
                            className={`gv2-edge-line-badge is-${sample.lineType} is-stroke-${sample.strokeKind}`}
                            style={{ '--edge-color': sample.color, '--edge-badge-scale': edgeBadgeScale } as CSSProperties}
                          >
                            <i />
                          </span>
                          <span className="gv2-legend-node-label">{EDGE_TIER_LABEL[tier]}</span>
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
                            <span
                              className={`gv2-edge-line-badge is-${item.lineType} is-stroke-${item.strokeKind}`}
                              style={{ '--edge-color': item.color, '--edge-badge-scale': edgeBadgeScale } as CSSProperties}
                            >
                              <i />
                            </span>
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
                  <div className="gv2-legend-section-title">符号调试</div>
                  <div className="gv2-legend-debug-meta">
                    <span>可见节点 {symbolDebug.total}</span>
                    <span>类型映射 {symbolDebug.unique}</span>
                    <span>回退circle {symbolDebug.forcedCircle}</span>
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
                    <strong>结构化搜索任务</strong>
                    <button type="button" onClick={() => setTaskModalOpen(false)}>×</button>
                  </div>
                  <p className="gv2-task-modal-hint">单击仅节点，双击节点及其一跳邻居。可复制 JSON 或直接提交采集任务。来源采集可勾选来源库面板。</p>
                  <div className="gv2-task-grid">
                    <label>language<input value={dashboard.language} onChange={(e) => setDashboard((p) => ({ ...p, language: e.target.value }))} /></label>
                    <label>provider<input value={dashboard.provider} onChange={(e) => setDashboard((p) => ({ ...p, provider: e.target.value }))} /></label>
                    <label>max_items<input type="number" min={1} max={100} value={dashboard.maxItems} onChange={(e) => setDashboard((p) => ({ ...p, maxItems: Math.min(100, Math.max(1, Number(e.target.value) || 1)) }))} /></label>
                    <label>start_offset<input type="number" min={1} value={dashboard.startOffset} onChange={(e) => setDashboard((p) => ({ ...p, startOffset: e.target.value }))} /></label>
                    <label>days_back<input type="number" min={0} max={365} value={dashboard.daysBack} onChange={(e) => setDashboard((p) => ({ ...p, daysBack: e.target.value }))} /></label>
                    <label>platforms<input value={dashboard.platforms} onChange={(e) => setDashboard((p) => ({ ...p, platforms: e.target.value }))} /></label>
                    <label>base_subreddits<input value={dashboard.baseSubreddits} onChange={(e) => setDashboard((p) => ({ ...p, baseSubreddits: e.target.value }))} /></label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.enableExtraction} onChange={(e) => setDashboard((p) => ({ ...p, enableExtraction: e.target.checked }))} />enable_extraction</label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.asyncMode} onChange={(e) => setDashboard((p) => ({ ...p, asyncMode: e.target.checked }))} />async_mode</label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.enableSubredditDiscovery} onChange={(e) => setDashboard((p) => ({ ...p, enableSubredditDiscovery: e.target.checked }))} />enable_subreddit_discovery</label>
                    <label className="gv2-checkbox"><input type="checkbox" checked={dashboard.llmAssist} onChange={(e) => setDashboard((p) => ({ ...p, llmAssist: e.target.checked }))} />llm_assist</label>
                  </div>
                  <div className="gv2-source-panel">
                    <div className="gv2-source-panel-head">
                      <strong>来源库面板</strong>
                      <span>已选 {dashboard.sourceItemKeys.length}</span>
                    </div>
                    <div className="gv2-source-panel-tools">
                      <input
                        value={sourceItemKeyword}
                        onChange={(e) => setSourceItemKeyword(e.target.value)}
                        placeholder="筛选 item_key / 名称 / tags"
                      />
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          const visibleKeys = filteredSourceItems.map((item) => String(item.item_key || '').trim()).filter(Boolean)
                          setDashboard((prev) => ({ ...prev, sourceItemKeys: Array.from(new Set([...(prev.sourceItemKeys || []), ...visibleKeys])) }))
                        }}
                      >
                        全选可见
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setDashboard((prev) => ({ ...prev, sourceItemKeys: [] }))}
                      >
                        清空
                      </button>
                    </div>
                    <div className="gv2-source-panel-list">
                      {sourceItemsQuery.isLoading ? <div className="status-line">来源库加载中...</div> : null}
                      {sourceItemsQuery.isError ? <div className="status-line">来源库加载失败</div> : null}
                      {!sourceItemsQuery.isLoading && !sourceItemsQuery.isError && !filteredSourceItems.length ? (
                        <div className="status-line">没有匹配的来源项</div>
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
                    <button type="button" className="secondary" onClick={() => void copyStructuredPayload()}>复制结构化任务JSON</button>
                    <button
                      type="button"
                      disabled={Boolean(submittingMap.collect)}
                      onClick={() => void submitStructuredTasks('collect')}
                    >
                      {submittingMap.collect ? '提交中...' : '生成结构化采集任务'}
                    </button>
                    <button
                      type="button"
                      disabled={Boolean(submittingMap.source_collect)}
                      onClick={() => void submitStructuredTasks('source_collect')}
                    >
                      {submittingMap.source_collect ? '提交中...' : '生成来源采集任务'}
                    </button>
                  </div>
                  <div className="gv2-task-result">
                    <div>collect.accepted: {String(structuredResultMap.collect?.summary?.accepted ?? '-')}</div>
                    <div>collect.queued: {String(structuredResultMap.collect?.summary?.queued ?? '-')}</div>
                    <div>collect.failed: {String(structuredResultMap.collect?.summary?.failed ?? '-')}</div>
                    <div>
                      collect.batch_names: {(structuredResultMap.collect?.batches || []).map((b, idx) => String(b.batch_name || `批次 ${idx + 1}`)).join(', ') || '-'}
                    </div>
                    <hr style={{ borderColor: 'rgba(148,163,184,0.2)' }} />
                    <div>source_collect.accepted: {String(structuredResultMap.source_collect?.summary?.accepted ?? '-')}</div>
                    <div>source_collect.queued: {String(structuredResultMap.source_collect?.summary?.queued ?? '-')}</div>
                    <div>source_collect.failed: {String(structuredResultMap.source_collect?.summary?.failed ?? '-')}</div>
                    <div>
                      source_collect.batch_names: {(structuredResultMap.source_collect?.batches || []).map((b, idx) => String(b.batch_name || `批次 ${idx + 1}`)).join(', ') || '-'}
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
                  aria-label="关闭"
                >
                  ×
                </button>
              </div>
              <div className="gv2-node-card-body">
                  <div className="gv2-node-grid">
                    {cardFields(selectedNode).map(([k, v]) => (
                      <div key={`${k}-${v}`} className="gv2-node-grid-item">
                        <label>{k}</label>
                        <strong>{v}</strong>
                      </div>
                    ))}
                  </div>
                  {selectedNodeContext ? (
                    <div className="gv2-node-context">
                      <strong>图谱信息</strong>
                      <div className="gv2-node-grid">
                        <div className="gv2-node-grid-item">
                          <label>连接数（Degree）</label>
                          <strong>{selectedNodeContext.degree}</strong>
                        </div>
                        <div className="gv2-node-grid-item">
                          <label>关联类型数</label>
                          <strong>{selectedNodeContext.neighborTypeCount}</strong>
                        </div>
                        <div className="gv2-node-grid-item">
                          <label>关联文档数</label>
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
                              {item.direction === 'OUT' ? '出' : '入'} · {item.targetName}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {nodeAllElements.length ? (
                    <div className="gv2-node-context">
                      <strong>节点元素</strong>
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
                      <strong>实体关系信息</strong>
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
                                <span className="gv2-rel-group-meta">{group.items.length} 条</span>
                                <span className="gv2-rel-group-action">{open ? '收起' : '展开'}</span>
                              </button>
                              {open ? (
                                <div className="gv2-node-relations">
                                  {group.items.map((item) => (
                                    <div key={item.id} className="gv2-node-relation">
                                      <span className={`gv2-rel-badge ${item.direction === 'OUT' ? 'out' : 'in'}`}>{item.direction === 'OUT' ? '出' : '入'}</span>
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
                          {allRelationGroupsOpen ? '收起全部关系组' : `展开全部关系组（${relationGroups.length}）`}
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
            <div className="gv2-macro-stat"><span>图谱</span><strong>{TYPE_LABEL[variant]}</strong></div>
            <div className="gv2-macro-stat"><span>节点总数</span><strong>{stats.nodes}</strong></div>
            <div className="gv2-macro-stat"><span>边总数</span><strong>{stats.edges}</strong></div>
            <div className="gv2-macro-stat"><span>节点类型</span><strong>{stats.typeCount}</strong></div>
            <div className="gv2-macro-stat"><span>已选节点</span><strong>{selectedNodeKeys.size}</strong></div>
            <div className="gv2-macro-stat"><span>当前可见</span><strong>{topology.visibleNodes.length} / {topology.visibleEdges.length}</strong></div>
          </div>
        </div>
      </section>
    </div>
  )
}
