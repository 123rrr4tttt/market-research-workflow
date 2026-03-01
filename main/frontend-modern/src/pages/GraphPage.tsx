import { useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsType } from 'echarts/core'
import { getGraphConfig, getMarketGraph, getPolicyGraph, getSocialGraph, listSourceItems, submitGraphStructuredSearchTasks } from '../lib/api'
import type {
  GraphEdgeItem,
  GraphNodeItem,
  GraphStructuredDashboardParams,
  GraphStructuredSearchResponse,
  SourceLibraryItem,
} from '../lib/types'
import { GRAPH_COLOR_THEMES, assignLegendColors, type PaletteKey } from '../lib/graph-colors'
import { applyRenderer2D, RENDERER_2D_CAPABILITIES } from './graph/renderers/renderer2dEcharts'
import { applyRendererProjection3D, RENDERER_PROJECTION_3D_CAPABILITIES, type Projection3DPhysicsState } from './graph/renderers/renderer3dProjection'
import type { RenderMode, RenderNode } from './graph/renderers/types'

type Variant = 'graphMarket' | 'graphPolicy' | 'graphSocial' | 'graphCompany' | 'graphProduct' | 'graphOperation' | 'graphDeep'

type Props = {
  projectKey: string
  variant: Variant
}

type GraphKind = 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'

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
  TopicTag: 'arrow',
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
  return aliasMap[compact] || raw
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

function edgeNodeKey(node: GraphEdgeItem['from'] | GraphEdgeItem['to']) {
  return `${normalizeNodeType(node.type)}:${node.id}`
}

function collectFocusNodeKeys(centerKey: string, adjacency: Map<string, Set<string>>) {
  const keys = new Set<string>()
  keys.add(centerKey)
  ;(adjacency.get(centerKey) || new Set()).forEach((neighbor) => keys.add(neighbor))
  return keys
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

type NodeCardAnchor = {
  left: number
  top: number
  width: number
}

const NODE_CARD_WIDTH = 360
const NODE_CARD_MARGIN = 14
const NODE_CARD_POINTER_OFFSET = 10
const GRAPH_SELECT_DEBUG = true
const GRAPH_SELECT_DEEP_DEBUG = false
const DOUBLE_CLICK_WINDOW_MS = 420
const GRAPH_LIMIT_MIN = 1
const GRAPH_LIMIT_MAX = 2000
const GRAPH_LIMIT_DEFAULT = 100
const CONTROL_PANEL_MIN_WIDTH = 280
const CONTROL_PANEL_MAX_WIDTH = 720

function clampGraphLimit(value: number) {
  if (!Number.isFinite(value)) return GRAPH_LIMIT_DEFAULT
  return Math.max(GRAPH_LIMIT_MIN, Math.min(GRAPH_LIMIT_MAX, Math.trunc(value)))
}

function clampControlPanelWidth(value: number, viewportWidth: number) {
  const viewportBound = Math.max(CONTROL_PANEL_MIN_WIDTH, viewportWidth - 28)
  const maxAllowed = Math.min(CONTROL_PANEL_MAX_WIDTH, viewportBound)
  return Math.max(CONTROL_PANEL_MIN_WIDTH, Math.min(maxAllowed, Math.round(value)))
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

const SPECIAL_PREFIX_BY_KIND: Partial<Record<GraphKind, string>> = {
  company: 'Company',
  product: 'Product',
  operation: 'Operation',
}

type VisibleSubgraph = {
  connectedNodes: GraphNodeItem[]
  connectedEdges: GraphEdgeItem[]
  connectedNodeKeys: Set<string>
  visibleNodes: GraphNodeItem[]
  visibleEdges: GraphEdgeItem[]
  visibleNodeKeys: Set<string>
  edgeResolvedKeyMap: Map<GraphEdgeItem, { fromKey: string; toKey: string }>
}

function computeVisibleSubgraph(
  nodes: GraphNodeItem[],
  edges: GraphEdgeItem[],
  graphKind: GraphKind,
  hiddenTypes: Record<string, boolean>,
): VisibleSubgraph {
  const variantTypes = new Set(DEFAULT_NODE_TYPES_BY_KIND[graphKind])
  const variantNodes = nodes.filter((n) => variantTypes.has(normalizeNodeType(n.type)))
  const variantNodeKeys = new Set(variantNodes.map(nodeKey))
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
    const canonical = nodeKey(node)
    appendIdAlias(node.id, canonical)
    const entryId = node.entry_id
    if (entryId == null || String(entryId).trim() === '') return
    variantAliasToCanonicalKey.set(`${node.type}:${entryId}`, canonical)
    appendIdAlias(entryId, canonical)
  })
  const resolveVariantRefKey = (ref: GraphEdgeItem['from'] | GraphEdgeItem['to']) => {
    const raw = edgeNodeKey(ref)
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
  let connectedNodeKeys = new Set(connectedNodes.map(nodeKey))
  const specialPrefix = SPECIAL_PREFIX_BY_KIND[graphKind]
  if (specialPrefix) {
    const specialSeedKeys = variantNodes
      .filter((node) => node.type.startsWith(specialPrefix))
      .map((node) => nodeKey(node))
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
      connectedNodes = variantNodes.filter((node) => reachableFromSpecial.has(nodeKey(node)))
      connectedNodeKeys = new Set(connectedNodes.map(nodeKey))
      connectedEdges = variantEdges.filter(
        (edge) => {
          const resolved = edgeResolvedKeyMap.get(edge)
          if (!resolved) return false
          return connectedNodeKeys.has(resolved.fromKey) && connectedNodeKeys.has(resolved.toKey)
        },
      )
    }
  }

  const visibleNodes = connectedNodes.filter((node) => !hiddenTypes[node.type])
  const visibleNodeKeys = new Set(visibleNodes.map(nodeKey))
  const visibleEdges = connectedEdges.filter(
    (edge) => {
      const resolved = edgeResolvedKeyMap.get(edge)
      if (!resolved) return false
      return visibleNodeKeys.has(resolved.fromKey) && visibleNodeKeys.has(resolved.toKey)
    },
  )

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

export default function GraphPage({ projectKey, variant }: Props) {
  const graphKind = TYPE_TO_KIND[variant]
  const chartRef = useRef<HTMLDivElement | null>(null)
  const fullscreenWrapRef = useRef<HTMLDivElement | null>(null)
  const controlPanelRef = useRef<HTMLDivElement | null>(null)
  const controlResizeRightRef = useRef<number | null>(null)
  const chartInstRef = useRef<EChartsType | null>(null)
  const echartsLibRef = useRef<typeof import('echarts/core') | null>(null)
  const nodeLookupRef = useRef<Record<string, GraphNodeItem>>({})
  const nodePositionRef = useRef<Record<string, { x?: number; y?: number }>>({})

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [state, setState] = useState('')
  const [policyType, setPolicyType] = useState('')
  const [platform, setPlatform] = useState('')
  const [topic, setTopic] = useState('')
  const [game, setGame] = useState('')
  const [limit, setLimit] = useState(GRAPH_LIMIT_DEFAULT)
  const [visualDraft, setVisualDraft] = useState({
    repulsion: 180,
    nodeScale: 100,
    nodeAlpha: 72,
    edgeWidth: 100,
    edgeAlpha: 100,
    showLabel: true,
  })
  const [visualApplied, setVisualApplied] = useState({
    repulsion: 180,
    nodeScale: 100,
    nodeAlpha: 72,
    edgeWidth: 100,
    edgeAlpha: 100,
    showLabel: true,
  })
  const [hiddenTypes, setHiddenTypes] = useState<Record<string, boolean>>({})
  const [appliedFilters, setAppliedFilters] = useState<FilterState>({
    startDate: '',
    endDate: '',
    state: '',
    policyType: '',
    platform: '',
    topic: '',
    game: '',
    limit: GRAPH_LIMIT_DEFAULT,
  })
  const [selectedNode, setSelectedNode] = useState<GraphNodeItem | null>(null)
  const [nodeCardAnchor, setNodeCardAnchor] = useState<NodeCardAnchor | null>(null)
  const [chartReady, setChartReady] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isCompactViewport, setIsCompactViewport] = useState(false)
  const [showOverlay, setShowOverlay] = useState(true)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [expandedEdgeGroup, setExpandedEdgeGroup] = useState<EdgeLegendTier | null>(null)
  const [paletteKey, setPaletteKey] = useState<PaletteKey>('bcp_unified')
  const [colorRotate, setColorRotate] = useState(58)
  const [absoluteContrast, setAbsoluteContrast] = useState(62)
  const [renderMode, setRenderMode] = useState<RenderMode>('2d')
  const [projectionRotateX, setProjectionRotateX] = useState(12)
  const [projectionRotateY, setProjectionRotateY] = useState(18)
  const [projectionRotateZ, setProjectionRotateZ] = useState(0)
  const [projection3DRepulsionPercent, setProjection3DRepulsionPercent] = useState(100)
  const [physicsFrame, setPhysicsFrame] = useState(0)
  const [controlPanelWidth, setControlPanelWidth] = useState(430)
  const [controlSectionOpen, setControlSectionOpen] = useState<Record<'view' | 'projection' | 'color' | 'filter', boolean>>({
    view: true,
    projection: true,
    color: true,
    filter: true,
  })
  const [hiddenEdgeKinds, setHiddenEdgeKinds] = useState<Record<string, boolean>>({})
  const [relationGroupOpen, setRelationGroupOpen] = useState<Record<string, boolean>>({})
  const [expandedNeighborType, setExpandedNeighborType] = useState<string | null>(null)
  const [expandedPredicate, setExpandedPredicate] = useState<string | null>(null)
  const [expandedElementLabel, setExpandedElementLabel] = useState<string | null>(null)
  const [selectionEnabled, setSelectionEnabled] = useState(false)
  const [manualSelectedNodeKeys, setManualSelectedNodeKeys] = useState<Set<string>>(new Set())
  const [radiationSelectionByCenter, setRadiationSelectionByCenter] = useState<Record<string, boolean>>({})
  const [selectionPinned, setSelectionPinned] = useState(false)
  const [autoFocusEnabled, setAutoFocusEnabled] = useState(true)
  const [hoverNodeKey, setHoverNodeKey] = useState<string | null>(null)
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [submittingMap, setSubmittingMap] = useState<Record<'collect' | 'source_collect', boolean>>({
    collect: false,
    source_collect: false,
  })
  const [structuredResultMap, setStructuredResultMap] = useState<Record<'collect' | 'source_collect', GraphStructuredSearchResponse | null>>({
    collect: null,
    source_collect: null,
  })
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
  const clickTimerRef = useRef<number | null>(null)
  const lastClickRef = useRef<{ key: string; ts: number } | null>(null)
  const selectionEnabledRef = useRef(false)
  const autoFocusEnabledRef = useRef(true)
  const adjacencyConnectedMapRef = useRef<Map<string, Set<string>>>(new Map())
  const dragFocusNodeKeyRef = useRef<string | null>(null)
  const projectionPhysicsRef = useRef<Projection3DPhysicsState>({ positions: {}, velocities: {} })
  const projectionInteractionQuatRef = useRef<QuaternionLike>({ x: 0, y: 0, z: 0, w: 1 })
  const projectionAngularVelRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const projectionDragStateRef = useRef<{ active: boolean; x: number; y: number }>({ active: false, x: 0, y: 0 })

  useEffect(() => {
    selectionEnabledRef.current = selectionEnabled
  }, [selectionEnabled])

  useEffect(() => {
    autoFocusEnabledRef.current = autoFocusEnabled
  }, [autoFocusEnabled])

  useEffect(() => {
    // Avoid carrying hidden type masks across graph variants.
    setHiddenTypes({})
    setHiddenEdgeKinds({})
    setExpandedGroup(null)
    setExpandedEdgeGroup(null)
    setManualSelectedNodeKeys(new Set())
    setRadiationSelectionByCenter({})
    setSelectionPinned(false)
    setHoverNodeKey(null)
    projectionPhysicsRef.current = { positions: {}, velocities: {} }
    projectionInteractionQuatRef.current = { x: 0, y: 0, z: 0, w: 1 }
    projectionAngularVelRef.current = { x: 0, y: 0 }
    projectionDragStateRef.current = { active: false, x: 0, y: 0 }
  }, [graphKind])

  const graphConfig = useQuery({
    queryKey: ['graph-config', projectKey],
    queryFn: getGraphConfig,
    enabled: Boolean(projectKey),
  })

  const effectiveLimit = clampGraphLimit(appliedFilters.limit)

  const graphData = useQuery({
    queryKey: [
      'graph',
      projectKey,
      graphKind,
      appliedFilters.startDate,
      appliedFilters.endDate,
      appliedFilters.state,
      appliedFilters.policyType,
      appliedFilters.platform,
      appliedFilters.topic,
      appliedFilters.game,
      effectiveLimit,
    ],
    queryFn: async () => {
      if (graphKind === 'policy') {
        return getPolicyGraph({
          start_date: appliedFilters.startDate,
          end_date: appliedFilters.endDate,
          state: appliedFilters.state,
          policy_type: appliedFilters.policyType,
          limit: effectiveLimit,
        })
      }
      if (graphKind === 'social') {
        return getSocialGraph({
          start_date: appliedFilters.startDate,
          end_date: appliedFilters.endDate,
          platform: appliedFilters.platform,
          topic: appliedFilters.topic,
          limit: effectiveLimit,
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
        limit: effectiveLimit,
      })
    },
    enabled: Boolean(projectKey),
  })

  const sourceItemsQuery = useQuery({
    queryKey: ['source-library-items', projectKey],
    queryFn: listSourceItems,
    enabled: Boolean(projectKey) && taskModalOpen,
  })

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
    fromCfg.forEach((t) => set.add(String(t)))
    ;(graphData.data?.nodes || []).forEach((n) => set.add(String(n.type)))
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [graphData.data?.nodes, graphConfig.data?.graph_node_types, graphKind])

  const nodeTypeColor = useMemo(() => {
    return assignLegendColors(nodeTypes, paletteKey, 'node', colorDistribution)
  }, [nodeTypes, paletteKey, colorDistribution])

  const stats = useMemo(() => {
    const nodes = graphData.data?.nodes || []
    const edges = graphData.data?.edges || []
    const typeCount = nodeTypes.length
    return { nodes: nodes.length, edges: edges.length, typeCount }
  }, [graphData.data?.nodes, graphData.data?.edges, nodeTypes.length])

  const legendGroups = useMemo(() => {
    const grouped: Record<string, string[]> = {}
    nodeTypes.forEach((type) => {
      const g = groupOfType(type)
      if (!grouped[g]) grouped[g] = []
      grouped[g].push(type)
    })
    return Object.entries(grouped).sort(([a], [b]) => (GROUP_LABEL[a] || a).localeCompare((GROUP_LABEL[b] || b), 'zh-CN'))
  }, [nodeTypes])

  const topology = useMemo(() => {
    const nodes = graphData.data?.nodes || []
    const edges = graphData.data?.edges || []
    const { connectedNodes, connectedEdges, connectedNodeKeys, visibleNodes, visibleEdges, visibleNodeKeys, edgeResolvedKeyMap } = computeVisibleSubgraph(
      nodes,
      edges,
      graphKind,
      hiddenTypes,
    )

    const degreeMap = new Map<string, number>()
    visibleEdges.forEach((edge) => {
      const resolved = edgeResolvedKeyMap.get(edge)
      if (!resolved) return
      degreeMap.set(resolved.fromKey, (degreeMap.get(resolved.fromKey) || 0) + 1)
      degreeMap.set(resolved.toKey, (degreeMap.get(resolved.toKey) || 0) + 1)
    })
    const degrees = Array.from(degreeMap.values())
    const minDeg = degrees.length ? Math.min(...degrees) : 0
    const maxDeg = degrees.length ? Math.max(...degrees) : 1
    const rangeDeg = Math.max(maxDeg - minDeg, 1)
    return {
      nodes,
      connectedNodes,
      connectedEdges,
      connectedNodeKeys,
      visibleNodes,
      visibleEdges,
      degreeMap,
      minDeg,
      rangeDeg,
      visibleNodeKeys,
      edgeResolvedKeyMap,
      rawNodeCount: visibleNodes.length,
      rawEdgeCount: visibleEdges.length,
    }
  }, [graphData.data, hiddenTypes, graphKind])

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

  const activeRendererCapabilities = useMemo(
    () => (renderMode === 'projection3d' ? RENDERER_PROJECTION_3D_CAPABILITIES : RENDERER_2D_CAPABILITIES),
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

  const selectedNodeKeys = useMemo(() => {
    const merged = new Set(manualSelectedNodeKeys)
    Object.entries(radiationSelectionByCenter).forEach(([centerKey, enabled]) => {
      if (!enabled) return
      collectFocusNodeKeys(centerKey, adjacencyConnectedMap).forEach((item) => merged.add(item))
    })
    return merged
  }, [manualSelectedNodeKeys, radiationSelectionByCenter, adjacencyConnectedMap])

  useEffect(() => {
    if (selectionPinned && !selectedNodeKeys.size) setSelectionPinned(false)
  }, [selectionPinned, selectedNodeKeys])

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
    setRadiationSelectionByCenter((prev) => {
      const nextEntries = Object.entries(prev).filter(([key]) => topology.connectedNodeKeys.has(key))
      if (nextEntries.length === Object.keys(prev).length) return prev
      return Object.fromEntries(nextEntries)
    })
    setSelectedNode((prev) => {
      if (!prev) return prev
      return topology.connectedNodeKeys.has(nodeKey(prev)) ? prev : null
    })
  }, [topology.connectedNodeKeys])

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

  useEffect(() => {
    if (!autoFocusEnabled) {
      setHoverNodeKey(null)
      return
    }
    if (!hoverNodeKey && selectedNodeKey) {
      setHoverNodeKey(selectedNodeKey)
    }
  }, [autoFocusEnabled, hoverNodeKey, selectedNodeKey])

  useEffect(() => {
    if (renderMode !== 'projection3d' || !chartReady) return
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
  }, [renderMode, chartReady])

  useEffect(() => {
    if (!chartReady || renderMode !== 'projection3d') return
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
  }, [chartReady, renderMode])

  useEffect(() => {
    // Reset accumulated roam transform when switching render modes,
    // otherwise projection mode may look off-center from previous pan/zoom state.
    chartInstRef.current?.clear()
    projectionDragStateRef.current.active = false
    if (renderMode !== 'projection3d') {
      projectionAngularVelRef.current = { x: 0, y: 0 }
    }
  }, [renderMode])

  useEffect(() => {
    if (renderMode !== 'projection3d') return
    const basisQuat = quatFromAxisAngle(1, 0, 0, -Math.PI / 2)
    const sliderQuat = quatFromEulerDeg(projectionRotateX, projectionRotateY, projectionRotateZ)
    projectionInteractionQuatRef.current = quatMul(sliderQuat, basisQuat)
    projectionAngularVelRef.current = { x: 0, y: 0 }
    setPhysicsFrame((prev) => (prev >= 1000000 ? 0 : prev + 1))
  }, [renderMode, graphKind, projectionRotateX, projectionRotateY, projectionRotateZ])

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
  }, [])

  useEffect(() => {
    const onWindowResize = () => {
      setIsCompactViewport(window.innerWidth <= 980)
      setControlPanelWidth((prev) => clampControlPanelWidth(prev, window.innerWidth))
    }
    onWindowResize()
    window.addEventListener('resize', onWindowResize)
    return () => window.removeEventListener('resize', onWindowResize)
  }, [])

  useEffect(() => {
    const onFullscreenChange = () => {
      const active = document.fullscreenElement === fullscreenWrapRef.current
      setIsFullscreen(active)
      chartInstRef.current?.resize()
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  useEffect(() => {
    if (!chartReady) return
    const chart = chartInstRef.current
    if (!chart) return
    const raf = window.requestAnimationFrame(() => {
      chart.resize()
    })
    return () => window.cancelAnimationFrame(raf)
  }, [isFullscreen, chartReady])

  useEffect(() => {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current)
      clickTimerRef.current = null
    }
    lastClickRef.current = null
    setHoverNodeKey(null)
    setRadiationSelectionByCenter({})
  }, [variant])

  useEffect(() => {
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

        chartInstRef.current.on('click', (params) => {
          if (params.dataType !== 'node') return
          const nodeId = params.data && typeof params.data === 'object' && 'id' in params.data
            ? String(params.data.id || '')
            : ''
          const node = nodeLookupRef.current[nodeId]
          if (!node) return
          const key = nodeKey(node)
          syncNodeCardFromParams(params as { event?: { event?: MouseEvent } }, node)
          if (!selectionEnabledRef.current) return
          const now = Date.now()
          const last = lastClickRef.current
          const isDouble = Boolean(last && last.key === key && now - last.ts <= DOUBLE_CLICK_WINDOW_MS)
          lastClickRef.current = { key, ts: now }
          if (GRAPH_SELECT_DEBUG) {
            console.info('[graph-select] click', {
              nodeKey: key,
              isDouble,
              hasTimer: clickTimerRef.current !== null,
            })
          }
          if (isDouble) {
            if (clickTimerRef.current !== null) {
              window.clearTimeout(clickTimerRef.current)
              clickTimerRef.current = null
            }
            if (GRAPH_SELECT_DEBUG) console.info('[graph-select] dispatch-double', { nodeKey: key })
            const radiationSet = collectFocusNodeKeys(key, adjacencyConnectedMapRef.current)
            const neighbors = Array.from(radiationSet).filter((item) => item !== key)
            if (GRAPH_SELECT_DEEP_DEBUG) {
              const incident = (topology.connectedEdges || []).reduce((acc, edge) => {
                const resolved = topology.edgeResolvedKeyMap.get(edge)
                if (!resolved) return acc
                if (resolved.fromKey === key || resolved.toKey === key) {
                  acc.push({
                    from: resolved.fromKey,
                    to: resolved.toKey,
                    type: edge.type,
                    predicate: edge.predicate,
                  })
                }
                return acc
              }, [] as Array<{ from: string; to: string; type?: string; predicate?: string }>)
              console.info('[graph-select] double-neighbor-debug', {
                key,
                neighborCount: neighbors.length,
                neighbors,
                incidentCount: incident.length,
                incident,
              })
            }
            if (GRAPH_SELECT_DEBUG) console.info('[graph-select] double-toggle-neighbors', { key, neighborCount: neighbors.length, neighbors })
            setRadiationSelectionByCenter((prev) => {
              const nextOn = !prev[key]
              return { ...prev, [key]: nextOn }
            })
            return
          }
          if (clickTimerRef.current !== null) window.clearTimeout(clickTimerRef.current)
          clickTimerRef.current = window.setTimeout(() => {
            if (GRAPH_SELECT_DEBUG) console.info('[graph-select] dispatch-single', { nodeKey: key })
            setManualSelectedNodeKeys((prev) => {
              const next = new Set(prev)
              if (next.has(key)) next.delete(key)
              else next.add(key)
              return next
            })
            clickTimerRef.current = null
          }, DOUBLE_CLICK_WINDOW_MS)
          return
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
          if (!autoFocusEnabledRef.current) return
          if (params.dataType !== 'node') return
          const nodeId = params.data && typeof params.data === 'object' && 'id' in params.data
            ? String(params.data.id || '')
            : ''
          if (!nodeId) return
          dragFocusNodeKeyRef.current = nodeId
          setHoverNodeKey(nodeId)
        })
        chartInstRef.current.on('mouseup', (params) => {
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
          if (!autoFocusEnabledRef.current) return
          const mouseEvent = (params as { event?: { event?: MouseEvent } }).event?.event
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
      if (clickTimerRef.current !== null) {
        window.clearTimeout(clickTimerRef.current)
        clickTimerRef.current = null
      }
      lastClickRef.current = null
      if (chartInstRef.current) {
        chartInstRef.current.dispose()
        chartInstRef.current = null
      }
      dragFocusNodeKeyRef.current = null
    }
  }, [variant])

  useEffect(() => {
    if (!chartReady) return
    const chart = chartInstRef.current
    if (!chart) return
    const { nodes, visibleNodes, degreeMap, minDeg, rangeDeg } = topology
    nodeLookupRef.current = Object.fromEntries(nodes.map((n) => [nodeKey(n), n]))
    const prevPos2D = { ...nodePositionRef.current }
    try {
      const current = chart.getOption() as { series?: Array<{ data?: Array<{ id?: string; x?: number; y?: number }> }> }
      const currentData = current?.series?.[0]?.data || []
      currentData.forEach((item) => {
        const id = String(item?.id || '')
        if (!id) return
        prevPos2D[id] = { x: item.x, y: item.y }
      })
    } catch {
      // keep previous cached positions
    }
    const shouldShowNodeLabel = visualApplied.showLabel && visibleNodes.length <= 220
    const shouldShowEdgeLabel = false
    const autoFocusSet = new Set<string>()
    const focusCenterKey = autoFocusEnabled ? (hoverNodeKey || selectedNodeKey) : null
    if (focusCenterKey) {
      collectFocusNodeKeys(focusCenterKey, adjacencyConnectedMap).forEach((item) => autoFocusSet.add(item))
    }
    const enablePinnedOnlyDim = selectionPinned && selectedNodeKeys.size > 0
    const enableAutoFocusDim = autoFocusEnabled && autoFocusSet.size > 0

    const seriesNodes = visibleNodes.map((node) => {
      const key = nodeKey(node)
      const deg = degreeMap.get(key) || 0
      const size = Math.round((18 + ((deg - minDeg) / rangeDeg) * 28) * (visualApplied.nodeScale / 100))
      const show = shouldShowNodeLabel && size >= 24
      const selected = selectedNodeKeys.has(key)
      const dimByPinnedOnly = enablePinnedOnlyDim && !selected
      const dimByAutoFocus = enableAutoFocusDim && !autoFocusSet.has(key)
      const dimByFocus = enablePinnedOnlyDim ? dimByPinnedOnly : dimByAutoFocus
      const nodeColor = nodeTypeColor[node.type] || '#7dd3fc'
      const { r, g, b } = hexToRgb(nodeColor)
      const nodeAlphaT = Math.max(0, Math.min(1, visualApplied.nodeAlpha / 100))
      const nodeFillAlpha = selected ? Math.min(1, nodeAlphaT + 0.08) : nodeAlphaT
      return {
        id: key,
        name: nodeName(node),
        value: { id: node.id, type: node.type, name: nodeName(node) },
        symbol: SYMBOLS[node.type] || 'circle',
        x: prevPos2D[key]?.x,
        y: prevPos2D[key]?.y,
        symbolSize: dimByFocus ? Math.max(10, Math.round(size * 0.88)) : size,
        itemStyle: {
          opacity: dimByFocus ? 0.12 : 1,
          color: `rgba(${r}, ${g}, ${b}, ${dimByFocus ? 0.08 : nodeFillAlpha})`,
          borderColor: selected ? '#facc15' : `rgba(${r}, ${g}, ${b}, ${dimByFocus ? 0.2 : 0.95})`,
          borderWidth: selected ? 1.6 : 1,
          shadowBlur: 0,
          shadowColor: selected ? 'rgba(250, 204, 21, 0.45)' : 'transparent',
        },
        label: {
          show: show && !dimByFocus,
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

    const rendererResult = renderMode === 'projection3d'
      ? (() => {
        const result3d = applyRendererProjection3D(
          seriesNodes as RenderNode[],
          visibleEdges
            .map((edge) => {
              const resolved = topology.edgeResolvedKeyMap.get(edge)
              if (!resolved) return null
              return { from: resolved.fromKey, to: resolved.toKey }
            })
            .filter((x): x is { from: string; to: string } => Boolean(x)),
          projectionPhysicsRef.current,
          {
            rotateXDeg: 0,
            rotateYDeg: 0,
            rotateZDeg: 0,
            repulsionPercent: projection3DRepulsionPercent * 2,
            interactionQuat: projectionInteractionQuatRef.current,
          },
        )
        projectionPhysicsRef.current = result3d.physics
        return result3d.render
      })()
      : applyRenderer2D(seriesNodes as RenderNode[])

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
        series: [
          {
            type: 'graph',
            layout: rendererResult.series.layout,
            // Lock projection mode to viewport center; keep roam/drag only in 2D.
            roam: renderMode === 'projection3d' ? false : true,
            draggable: renderMode !== 'projection3d',
            center: renderMode === 'projection3d' ? ['50%', '50%'] : undefined,
            zoom: renderMode === 'projection3d' ? 1 : undefined,
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
            force: {
              repulsion: visualApplied.repulsion,
              edgeLength: [55, 180],
              gravity: 0.1,
              friction: 0.16,
              layoutAnimation: true,
            },
            data: rendererResult.nodes,
            links: seriesEdges,
            labelLayout: { hideOverlap: true },
            lineStyle: { opacity: 0.85 },
            emphasis: {
              focus: 'none',
              scale: false,
            },
          },
        ],
      }

    chart.setOption(
      option,
      { lazyUpdate: false },
    )
    if (rendererResult.cacheNodePositions) {
      nodePositionRef.current = Object.fromEntries(
        rendererResult.nodes.map((item) => [String(item.id), { x: item.x as number | undefined, y: item.y as number | undefined }]),
      )
    }
  }, [topology, visibleEdges, edgeLegendItemByKey, visualApplied, nodeTypeColor, graphKind, chartReady, isFullscreen, selectedNodeKeys, selectionPinned, adjacencyConnectedMap, hoverNodeKey, autoFocusEnabled, selectedNode, selectedNodeKey, renderMode, projectionRotateX, projectionRotateY, projectionRotateZ, projection3DRepulsionPercent, physicsFrame])

  const onControlResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isCompactViewport) return
    event.preventDefault()
    const panel = controlPanelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    controlResizeRightRef.current = rect.right
    const onMove = (moveEvent: MouseEvent) => {
      const right = controlResizeRightRef.current
      if (!Number.isFinite(right)) return
      const next = (right as number) - moveEvent.clientX
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

  return (
    <div className="content-stack gv2-root">
      <section className="panel gv2-main">
        <div className="gv2-layout">
          <div className={`gv2-chart-wrap gv2-chart-wrap--fullscreen-ready ${isFullscreen ? 'is-fullscreen' : ''}`} ref={fullscreenWrapRef}>
            {graphData.isFetching ? <div className="gv2-loading">加载中...</div> : null}
            {graphData.error ? (
              <div className="gv2-loading gv2-loading-error">
                加载失败：{graphData.error instanceof Error ? graphData.error.message : '请求异常'}
              </div>
            ) : null}
            <div ref={chartRef} className="gv2-chart" />
            <div className="gv2-overlay-top">
              <button
                type="button"
                className={`gv2-select-mode-btn ${selectionEnabled ? '' : 'is-off'}`.trim()}
                onClick={() => setSelectionEnabled((v) => !v)}
              >
                选择模式
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${autoFocusEnabled ? '' : 'is-off'}`.trim()}
                onClick={() => setAutoFocusEnabled((v) => !v)}
                title="基于当前节点详情自动隐没无关节点（与选择模式独立）"
              >
                聚焦隐没
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${renderMode === 'projection3d' ? '' : 'is-off'}`.trim()}
                onClick={() => setRenderMode((prev) => (prev === '2d' ? 'projection3d' : '2d'))}
                title="轻量3D模型模式（中心锁定，非相机视角）"
              >
                {renderMode === 'projection3d' ? '回到2D' : '3D模式'}
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
              <button onClick={() => graphData.refetch()} disabled={graphData.isFetching}>刷新</button>
              <button
                onClick={async () => {
                  if (!fullscreenWrapRef.current) return
                  if (document.fullscreenElement === fullscreenWrapRef.current) {
                    await document.exitFullscreen?.()
                    return
                  }
                  await fullscreenWrapRef.current.requestFullscreen?.()
                }}
              >
                {isFullscreen ? '退出全屏' : '全屏'}
              </button>
              <button onClick={() => setShowOverlay((v) => !v)}>{showOverlay ? '收起面板' : '展开面板'}</button>
            </div>

            <div
              ref={controlPanelRef}
              className={`gv2-floating-controls ${showOverlay ? '' : 'is-collapsed'}`}
              style={isCompactViewport ? undefined : { width: `${controlPanelWidth}px` }}
            >
              <div className="gv2-floating-controls-resizer" onMouseDown={onControlResizeStart} />
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
                      2D节点斥力
                      <input
                        type="range"
                        min={0}
                        max={200}
                        step={1}
                        value={Math.round(visualDraft.repulsion / 7.2)}
                        disabled={!activeRendererCapabilities.supportsForceControl}
                        onChange={(e) => {
                          const repulsion = Math.round(Number(e.target.value) * 7.2)
                          setVisualDraft((prev) => ({ ...prev, repulsion }))
                          setVisualApplied((prev) => ({ ...prev, repulsion }))
                        }}
                      />
                      <span>{Math.round(visualDraft.repulsion / 7.2)}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      节点尺寸
                      <input
                        type="range"
                        min={0}
                        max={200}
                        step={1}
                        value={Math.round(visualDraft.nodeScale / 1.8)}
                        onChange={(e) => {
                          const nodeScale = Math.round(Number(e.target.value) * 1.8)
                          setVisualDraft((prev) => ({ ...prev, nodeScale }))
                          setVisualApplied((prev) => ({ ...prev, nodeScale }))
                        }}
                      />
                      <span>{Math.round(visualDraft.nodeScale / 1.8)}%</span>
                    </label>
                    <label className="gv2-control-chip">
                      节点透明
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={1}
                        value={visualDraft.nodeAlpha}
                        onChange={(e) => {
                          const nodeAlpha = Number(e.target.value)
                          setVisualDraft((prev) => ({ ...prev, nodeAlpha }))
                          setVisualApplied((prev) => ({ ...prev, nodeAlpha }))
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
                        step={1}
                        value={visualDraft.edgeWidth}
                        onChange={(e) => {
                          const edgeWidth = Number(e.target.value)
                          setVisualDraft((prev) => ({ ...prev, edgeWidth }))
                          setVisualApplied((prev) => ({ ...prev, edgeWidth }))
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
                        step={1}
                        value={visualDraft.edgeAlpha}
                        onChange={(e) => {
                          const edgeAlpha = Number(e.target.value)
                          setVisualDraft((prev) => ({ ...prev, edgeAlpha }))
                          setVisualApplied((prev) => ({ ...prev, edgeAlpha }))
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
                          setVisualDraft((prev) => ({ ...prev, showLabel: checked }))
                          setVisualApplied((prev) => ({ ...prev, showLabel: checked }))
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

              {activeRendererCapabilities.supportsProjectionControls ? (
                <section className={`gv2-control-section ${controlSectionOpen.projection ? '' : 'is-collapsed'}`}>
                  <button
                    type="button"
                    className="gv2-control-section-head"
                    onClick={() => setControlSectionOpen((prev) => ({ ...prev, projection: !prev.projection }))}
                  >
                    <strong>3D模型参数</strong>
                    <span>{controlSectionOpen.projection ? '收起' : '展开'}</span>
                  </button>
                  {controlSectionOpen.projection ? (
                    <div className="gv2-control-section-body">
                      <label className="gv2-control-chip">
                        模型旋转X
                        <input
                          type="range"
                          min={-80}
                          max={80}
                          step={0.2}
                          value={projectionRotateX}
                          onChange={(e) => setProjectionRotateX(Number(e.target.value))}
                        />
                        <span>{projectionRotateX}deg</span>
                      </label>
                      <label className="gv2-control-chip">
                        模型旋转Y
                        <input
                          type="range"
                          min={-180}
                          max={180}
                          step={0.2}
                          value={projectionRotateY}
                          onChange={(e) => setProjectionRotateY(Number(e.target.value))}
                        />
                        <span>{projectionRotateY}deg</span>
                      </label>
                      <label className="gv2-control-chip">
                        模型旋转Z
                        <input
                          type="range"
                          min={-180}
                          max={180}
                          step={0.2}
                          value={projectionRotateZ}
                          onChange={(e) => setProjectionRotateZ(Number(e.target.value))}
                        />
                        <span>{projectionRotateZ}deg</span>
                      </label>
                      <label className="gv2-control-chip">
                        3D节点斥力
                        <input
                          type="range"
                          min={0}
                          max={200}
                          step={1}
                          value={projection3DRepulsionPercent}
                          onChange={(e) => setProjection3DRepulsionPercent(Number(e.target.value))}
                        />
                        <span>{projection3DRepulsionPercent}%</span>
                      </label>
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
                      <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                    </label>
                    <label className="gv2-control-chip">
                      结束日期
                      <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
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
                    <div className="gv2-control-chip">
                      <button
                        onClick={() => {
                          setAppliedFilters({
                            startDate,
                            endDate,
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
                          setStartDate('')
                          setEndDate('')
                          setState('')
                          setPolicyType('')
                          setPlatform('')
                          setTopic('')
                          setGame('')
                          setLimit(GRAPH_LIMIT_DEFAULT)
                          setAppliedFilters({
                            startDate: '',
                            endDate: '',
                            state: '',
                            policyType: '',
                            platform: '',
                            topic: '',
                            game: '',
                            limit: GRAPH_LIMIT_DEFAULT,
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
                  </div>
                ) : null}
              </section>
            </div>
            <div className={`gv2-legend-float ${showOverlay ? '' : 'is-collapsed'}`}>
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
                      <span className="dot" style={{ background: groupColor }} />
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
                        <span className="dot" style={{ background: nodeTypeColor[type] || '#7dd3fc' }} />
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

            {selectedNode ? (
              <article
                className="gv2-node-card"
                style={nodeCardAnchor ? { left: nodeCardAnchor.left, top: nodeCardAnchor.top, width: nodeCardAnchor.width } : undefined}
              >
                <div className="gv2-node-card-head">
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
