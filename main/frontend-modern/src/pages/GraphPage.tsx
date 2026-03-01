import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
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

type PaletteKey = 'tol_bright' | 'tol_vibrant' | 'tol_muted' | 'okabe_ito' | 'tableau10'

const COLOR_PALETTES: Record<PaletteKey, { label: string; colors: string[] }> = {
  tol_bright: {
    label: 'Tol Bright（推荐）',
    colors: ['#4477AA', '#EE6677', '#228833', '#CCBB44', '#66CCEE', '#AA3377', '#BBBBBB'],
  },
  tol_vibrant: {
    label: 'Tol Vibrant',
    colors: ['#EE7733', '#0077BB', '#33BBEE', '#EE3377', '#CC3311', '#009988', '#BBBBBB'],
  },
  tol_muted: {
    label: 'Tol Muted',
    colors: ['#CC6677', '#332288', '#DDCC77', '#117733', '#88CCEE', '#882255', '#44AA99', '#999933', '#AA4499'],
  },
  okabe_ito: {
    label: 'Okabe-Ito（色盲友好）',
    colors: ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7', '#000000'],
  },
  tableau10: {
    label: 'Tableau 10',
    colors: ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC'],
  },
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

function rgbToHex(r: number, g: number, b: number) {
  return `#${Math.round(r).toString(16).padStart(2, '0')}${Math.round(g).toString(16).padStart(2, '0')}${Math.round(b).toString(16).padStart(2, '0')}`
}

function tint(hex: string, ratio: number) {
  const { r, g, b } = hexToRgb(hex)
  return rgbToHex(
    r + (255 - r) * ratio,
    g + (255 - g) * ratio,
    b + (255 - b) * ratio,
  )
}

function brightenHex(hex: string) {
  const raw = hex.replace('#', '')
  const r = parseInt(raw.slice(0, 2), 16)
  const g = parseInt(raw.slice(2, 4), 16)
  const b = parseInt(raw.slice(4, 6), 16)
  const lift = (v: number) => Math.min(255, Math.round(v + (255 - v) * 0.14))
  return `#${lift(r).toString(16).padStart(2, '0')}${lift(g).toString(16).padStart(2, '0')}${lift(b).toString(16).padStart(2, '0')}`
}

function distinctChipColor(index: number) {
  const hue = Math.round((index * 137.508) % 360)
  return `hsl(${hue} 78% 62%)`
}

function nodeKey(node: GraphNodeItem) {
  return `${node.type}:${node.id}`
}

function edgeNodeKey(node: GraphEdgeItem['from'] | GraphEdgeItem['to']) {
  return `${node.type}:${node.id}`
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
const DOUBLE_CLICK_WINDOW_MS = 300

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
}

function computeVisibleSubgraph(
  nodes: GraphNodeItem[],
  edges: GraphEdgeItem[],
  graphKind: GraphKind,
  hiddenTypes: Record<string, boolean>,
): VisibleSubgraph {
  const variantTypes = new Set(DEFAULT_NODE_TYPES_BY_KIND[graphKind])
  const variantNodes = nodes.filter((n) => variantTypes.has(n.type))
  const variantNodeKeys = new Set(variantNodes.map(nodeKey))
  const variantEdges = edges.filter((e) => variantNodeKeys.has(edgeNodeKey(e.from)) && variantNodeKeys.has(edgeNodeKey(e.to)))

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
        const from = edgeNodeKey(edge.from)
        const to = edgeNodeKey(edge.to)
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
        (edge) => connectedNodeKeys.has(edgeNodeKey(edge.from)) && connectedNodeKeys.has(edgeNodeKey(edge.to)),
      )
    }
  }

  const visibleNodes = connectedNodes.filter((node) => !hiddenTypes[node.type])
  const visibleNodeKeys = new Set(visibleNodes.map(nodeKey))
  const visibleEdges = connectedEdges.filter(
    (edge) => visibleNodeKeys.has(edgeNodeKey(edge.from)) && visibleNodeKeys.has(edgeNodeKey(edge.to)),
  )

  return {
    connectedNodes,
    connectedEdges,
    connectedNodeKeys,
    visibleNodes,
    visibleEdges,
    visibleNodeKeys,
  }
}

export default function GraphPage({ projectKey, variant }: Props) {
  const graphKind = TYPE_TO_KIND[variant]
  const chartRef = useRef<HTMLDivElement | null>(null)
  const fullscreenWrapRef = useRef<HTMLDivElement | null>(null)
  const chartInstRef = useRef<EChartsType | null>(null)
  const echartsLibRef = useRef<typeof import('echarts/core') | null>(null)
  const nodeLookupRef = useRef<Record<string, GraphNodeItem>>({})
  const nodePositionRef = useRef<Record<string, { x?: number; y?: number }>>({})
  const renderFrameRef = useRef<number | null>(null)

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [state, setState] = useState('')
  const [policyType, setPolicyType] = useState('')
  const [platform, setPlatform] = useState('')
  const [topic, setTopic] = useState('')
  const [game, setGame] = useState('')
  const [limit, setLimit] = useState(100)
  const [visualDraft, setVisualDraft] = useState({
    repulsion: 180,
    nodeScale: 100,
    nodeAlpha: 72,
    showLabel: true,
  })
  const [visualApplied, setVisualApplied] = useState({
    repulsion: 180,
    nodeScale: 100,
    nodeAlpha: 72,
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
    limit: 100,
  })
  const [selectedNode, setSelectedNode] = useState<GraphNodeItem | null>(null)
  const [nodeCardAnchor, setNodeCardAnchor] = useState<NodeCardAnchor | null>(null)
  const [chartReady, setChartReady] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showOverlay, setShowOverlay] = useState(true)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [paletteKey, setPaletteKey] = useState<PaletteKey>('tol_bright')
  const [relationGroupOpen, setRelationGroupOpen] = useState<Record<string, boolean>>({})
  const [expandedNeighborType, setExpandedNeighborType] = useState<string | null>(null)
  const [expandedPredicate, setExpandedPredicate] = useState<string | null>(null)
  const [expandedElementLabel, setExpandedElementLabel] = useState<string | null>(null)
  const [selectionEnabled, setSelectionEnabled] = useState(false)
  const [selectedNodeKeys, setSelectedNodeKeys] = useState<Set<string>>(new Set())
  const [selectionPinned, setSelectionPinned] = useState(false)
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
  const adjacencyConnectedMapRef = useRef<Map<string, Set<string>>>(new Map())

  useEffect(() => {
    selectionEnabledRef.current = selectionEnabled
  }, [selectionEnabled])

  useEffect(() => {
    // Avoid carrying hidden type masks across graph variants.
    setHiddenTypes({})
    setExpandedGroup(null)
    setSelectedNodeKeys(new Set())
    setSelectionPinned(false)
    setHoverNodeKey(null)
  }, [graphKind])

  const graphConfig = useQuery({
    queryKey: ['graph-config', projectKey],
    queryFn: getGraphConfig,
    enabled: Boolean(projectKey),
  })

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
      appliedFilters.limit,
    ],
    queryFn: async () => {
      if (graphKind === 'policy') {
        return getPolicyGraph({
          start_date: appliedFilters.startDate,
          end_date: appliedFilters.endDate,
          state: appliedFilters.state,
          policy_type: appliedFilters.policyType,
          limit: appliedFilters.limit,
        })
      }
      if (graphKind === 'social') {
        return getSocialGraph({
          start_date: appliedFilters.startDate,
          end_date: appliedFilters.endDate,
          platform: appliedFilters.platform,
          topic: appliedFilters.topic,
          limit: appliedFilters.limit,
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
        limit: appliedFilters.limit,
      })
    },
    enabled: Boolean(projectKey),
  })

  const sourceItemsQuery = useQuery({
    queryKey: ['source-library-items', projectKey],
    queryFn: listSourceItems,
    enabled: Boolean(projectKey) && taskModalOpen,
  })

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
    const map: Record<string, string> = {}
    const palette = COLOR_PALETTES[paletteKey].colors
    nodeTypes.forEach((type) => {
      const h = hashText(type)
      const base = palette[h % palette.length]
      const mix = ((h >> 8) % 20) / 100
      map[type] = tint(brightenHex(base), 0.06 + mix)
    })
    return map
  }, [nodeTypes, paletteKey])

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
    const { connectedNodes, connectedEdges, connectedNodeKeys, visibleNodes, visibleEdges, visibleNodeKeys } = computeVisibleSubgraph(
      nodes,
      edges,
      graphKind,
      hiddenTypes,
    )

    const degreeMap = new Map<string, number>()
    visibleEdges.forEach((edge) => {
      degreeMap.set(edgeNodeKey(edge.from), (degreeMap.get(edgeNodeKey(edge.from)) || 0) + 1)
      degreeMap.set(edgeNodeKey(edge.to), (degreeMap.get(edgeNodeKey(edge.to)) || 0) + 1)
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
      rawNodeCount: visibleNodes.length,
      rawEdgeCount: visibleEdges.length,
    }
  }, [graphData.data, hiddenTypes, graphKind])

  const connectedNodeMap = useMemo(() => {
    return new Map(topology.connectedNodes.map((node) => [nodeKey(node), node]))
  }, [topology.connectedNodes])

  const adjacencyConnectedMap = useMemo(() => {
    const map = new Map<string, Set<string>>()
    const edges = topology.connectedEdges || []
    edges.forEach((edge) => {
      const from = edgeNodeKey(edge.from)
      const to = edgeNodeKey(edge.to)
      if (!map.has(from)) map.set(from, new Set())
      if (!map.has(to)) map.set(to, new Set())
      map.get(from)?.add(to)
      map.get(to)?.add(from)
    })
    return map
  }, [topology.connectedEdges])

  useEffect(() => {
    adjacencyConnectedMapRef.current = adjacencyConnectedMap
  }, [adjacencyConnectedMap])

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
    setSelectedNodeKeys((prev) => {
      if (!prev.size) return prev
      const next = new Set(Array.from(prev).filter((key) => topology.connectedNodeKeys.has(key)))
      if (next.size === prev.size && Array.from(prev).every((key) => next.has(key))) return prev
      return next
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
    const selectedEdges = topology.visibleEdges.filter((edge) => {
      return selectedSet.has(edgeNodeKey(edge.from)) && selectedSet.has(edgeNodeKey(edge.to))
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
  }, [selectedNodeKeys, connectedNodeMap, topology.visibleEdges, projectKey, graphKind, dashboardParams, dashboard.llmAssist])

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
      const fk = edgeNodeKey(edge.from)
      const tk = edgeNodeKey(edge.to)
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
      const fk = edgeNodeKey(edge.from)
      const tk = edgeNodeKey(edge.to)
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
  }, [selectedNode, topology.connectedNodeKeys, topology.connectedEdges, connectedNodeMap])

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
            const neighbors = Array.from(adjacencyConnectedMapRef.current.get(key) || [])
            if (GRAPH_SELECT_DEBUG) console.info('[graph-select] double-toggle-neighbors', { key, neighborCount: neighbors.length, neighbors })
            setSelectedNodeKeys((prev) => {
              const next = new Set(prev)
              neighbors.forEach((item) => {
                if (next.has(item)) next.delete(item)
                else next.add(item)
              })
              return next
            })
            return
          }
          if (clickTimerRef.current !== null) window.clearTimeout(clickTimerRef.current)
          clickTimerRef.current = window.setTimeout(() => {
            if (GRAPH_SELECT_DEBUG) console.info('[graph-select] dispatch-single', { nodeKey: key })
            setSelectedNodeKeys((prev) => {
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
          if (params.dataType !== 'node') return
          const nodeId = params.data && typeof params.data === 'object' && 'id' in params.data
            ? String(params.data.id || '')
            : ''
          if (!nodeId) return
          setHoverNodeKey(nodeId)
        })
        chartInstRef.current.on('globalout', () => {
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
      if (renderFrameRef.current !== null) {
        window.cancelAnimationFrame(renderFrameRef.current)
        renderFrameRef.current = null
      }
    }
  }, [variant])

  useEffect(() => {
    if (!chartReady) return
    const chart = chartInstRef.current
    if (!chart) return
    const { nodes, visibleNodes, visibleEdges, degreeMap, minDeg, rangeDeg } = topology
    nodeLookupRef.current = Object.fromEntries(nodes.map((n) => [nodeKey(n), n]))
    const prevPos = { ...nodePositionRef.current }
    try {
      const current = chart.getOption() as { series?: Array<{ data?: Array<{ id?: string; x?: number; y?: number }> }> }
      const currentData = current?.series?.[0]?.data || []
      currentData.forEach((item) => {
        const id = String(item?.id || '')
        if (!id) return
        prevPos[id] = { x: item.x, y: item.y }
      })
    } catch {
      // keep previous cached positions
    }
    const shouldShowNodeLabel = visualApplied.showLabel && visibleNodes.length <= 220
    const shouldShowEdgeLabel = false
    const focusSet = new Set<string>()
    if (selectionPinned) {
      selectedNodeKeys.forEach((center) => focusSet.add(center))
      if (hoverNodeKey && selectedNodeKeys.has(hoverNodeKey)) {
        focusSet.add(hoverNodeKey)
        ;(adjacencyConnectedMap.get(hoverNodeKey) || new Set()).forEach((neighbor) => focusSet.add(neighbor))
      }
    }
    const enableFocusDim = selectionPinned && focusSet.size > 0

    const seriesNodes = visibleNodes.map((node) => {
      const key = nodeKey(node)
      const deg = degreeMap.get(key) || 0
      const size = Math.round((18 + ((deg - minDeg) / rangeDeg) * 28) * (visualApplied.nodeScale / 100))
      const show = shouldShowNodeLabel && size >= 24
      const selected = selectedNodeKeys.has(key)
      const dimByFocus = enableFocusDim && !selected && !focusSet.has(key)
      const nodeColor = nodeTypeColor[node.type] || '#7dd3fc'
      const { r, g, b } = hexToRgb(nodeColor)
      return {
        id: key,
        name: nodeName(node),
        value: { id: node.id, type: node.type, name: nodeName(node) },
        symbol: SYMBOLS[node.type] || 'circle',
        x: prevPos[key]?.x,
        y: prevPos[key]?.y,
        symbolSize: dimByFocus ? Math.max(10, Math.round(size * 0.88)) : size,
        itemStyle: {
          opacity: dimByFocus ? 0.12 : 1,
          color: `rgba(${r}, ${g}, ${b}, ${dimByFocus ? 0.08 : (selected ? 0.95 : visualApplied.nodeAlpha / 100)})`,
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

    const seriesEdges = visibleEdges.map((edge) => {
      const fromKey = edgeNodeKey(edge.from)
      const toKey = edgeNodeKey(edge.to)
      const fromSelected = selectedNodeKeys.has(fromKey)
      const toSelected = selectedNodeKeys.has(toKey)
      const dimByFocus = enableFocusDim && !fromSelected && !toSelected && !(focusSet.has(fromKey) && focusSet.has(toKey))
      return {
        source: fromKey,
        target: toKey,
        value: edge,
        lineStyle: {
          color: dimByFocus
            ? 'rgba(125, 211, 252, 0.04)'
            : (edge.type === 'POLICY_RELATION' ? 'rgba(125, 211, 252, 0.68)' : 'rgba(125, 211, 252, 0.2)'),
          width: dimByFocus ? 0.7 : (edge.type === 'POLICY_RELATION' ? 1.6 : 1),
          curveness: edge.type === 'POLICY_RELATION' ? 0.18 : 0,
        },
        label: {
          show: !dimByFocus && shouldShowEdgeLabel && Boolean(edge.predicate),
          formatter: edge.predicate || '',
          color: 'rgba(147, 197, 253, 0.8)',
        },
      }
    })

    const option = {
        backgroundColor: '#030712',
        animationThreshold: 1000,
        hoverLayerThreshold: 1500,
        tooltip: {
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
              return `关系: ${edge.type || 'REL'}${edge.predicate ? `<br/>谓词: ${edge.predicate}` : ''}`
            }
            return ''
          },
        },
        series: [
          {
            type: 'graph',
            layout: 'force',
            roam: true,
            draggable: false,
            left: 0,
            right: 0,
            top: 0,
            bottom: 0,
            animation: true,
            animationDurationUpdate: 90,
            animationEasingUpdate: 'linear',
            progressive: 0,
            progressiveThreshold: 800,
            force: {
              repulsion: visualApplied.repulsion,
              edgeLength: [55, 180],
              gravity: 0.1,
              friction: 0.16,
              layoutAnimation: true,
            },
            data: seriesNodes,
            links: seriesEdges,
            labelLayout: { hideOverlap: true },
            lineStyle: { opacity: 0.85 },
            blur: {
              itemStyle: { opacity: 0.1 },
              lineStyle: { opacity: 0.06 },
              label: { show: false },
            },
            emphasis: {
              focus: 'adjacency',
              blurScope: 'global',
              scale: false,
            },
          },
        ],
      }

    chart.setOption(
      option,
      { lazyUpdate: false },
    )
    nodePositionRef.current = Object.fromEntries(
      seriesNodes.map((item) => [String(item.id), { x: item.x, y: item.y }]),
    )
  }, [topology, visualApplied, nodeTypeColor, graphKind, chartReady, isFullscreen, selectedNodeKeys, selectionPinned, adjacencyConnectedMap, hoverNodeKey])

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
                className={`gv2-select-mode-btn ${selectionEnabled ? 'is-active' : ''}`.trim()}
                onClick={() => setSelectionEnabled((v) => !v)}
              >
                选择模式
              </button>
              <button
                type="button"
                className={`gv2-select-mode-btn ${selectionPinned ? 'is-active' : ''}`.trim()}
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

            <div className={`gv2-floating-controls ${showOverlay ? '' : 'is-collapsed'}`}>
              <label className="gv2-control-chip">
                节点斥力
                <input
                  type="range"
                  min={0}
                  max={720}
                  step={10}
                  value={visualDraft.repulsion}
                  onChange={(e) => {
                    const repulsion = Number(e.target.value)
                    setVisualDraft((prev) => ({ ...prev, repulsion }))
                    setVisualApplied((prev) => ({ ...prev, repulsion }))
                  }}
                />
                <span>{visualDraft.repulsion}</span>
              </label>
              <label className="gv2-control-chip">
                节点尺寸
                <input
                  type="range"
                  min={0}
                  max={180}
                  step={5}
                  value={visualDraft.nodeScale}
                  onChange={(e) => {
                    const nodeScale = Number(e.target.value)
                    setVisualDraft((prev) => ({ ...prev, nodeScale }))
                    setVisualApplied((prev) => ({ ...prev, nodeScale }))
                  }}
                />
                <span>{visualDraft.nodeScale}%</span>
              </label>
              <label className="gv2-control-chip">
                节点透明
                <input
                  type="range"
                  min={20}
                  max={95}
                  step={5}
                  value={visualDraft.nodeAlpha}
                  onChange={(e) => {
                    const nodeAlpha = Number(e.target.value)
                    setVisualDraft((prev) => ({ ...prev, nodeAlpha }))
                    setVisualApplied((prev) => ({ ...prev, nodeAlpha }))
                  }}
                />
                <span>{visualDraft.nodeAlpha}%</span>
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
              <div className="gv2-control-chip"><span>已选 {selectedNodeKeys.size}</span><button type="button" className="secondary" onClick={() => setSelectedNodeKeys(new Set())} disabled={!selectedNodeKeys.size}>清空</button></div>
              <label className="gv2-control-chip">
                色系主题
                <select value={paletteKey} onChange={(e) => setPaletteKey(e.target.value as PaletteKey)}>
                  {Object.entries(COLOR_PALETTES).map(([key, val]) => (
                    <option key={key} value={key}>{val.label}</option>
                  ))}
                </select>
              </label>
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
                  min={1}
                  max={2000}
                  step={1}
                  value={limit}
                  onChange={(e) => setLimit(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))}
                />
                <span>{limit}</span>
              </label>
              <div className="gv2-control-chip">
                <button onClick={() => setAppliedFilters({
                  startDate,
                  endDate,
                  state,
                  policyType,
                  platform,
                  topic,
                  game,
                  limit,
                })}
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
                    setLimit(100)
                    setAppliedFilters({
                      startDate: '',
                      endDate: '',
                      state: '',
                      policyType: '',
                      platform: '',
                      topic: '',
                      game: '',
                      limit: 100,
                    })
                  }}
                >
                  重置
                </button>
              </div>
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
                              <i style={{ background: COLOR_PALETTES[paletteKey].colors[hashText(`el:${item.label}`) % COLOR_PALETTES[paletteKey].colors.length] }} />
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
