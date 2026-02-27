import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as echarts from 'echarts'
import { getGraphConfig, getMarketGraph, getPolicyGraph, getSocialGraph } from '../lib/api'
import type { GraphEdgeItem, GraphNodeItem } from '../lib/types'

type Variant = 'graphMarket' | 'graphPolicy' | 'graphSocial' | 'graphCompany' | 'graphProduct' | 'graphOperation' | 'graphDeep'

type Props = {
  projectKey: string
  variant: Variant
}

const TYPE_TO_KIND: Record<Variant, 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'> = {
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

const NODE_TONE_PALETTE = [
  '#4f99fa', '#c0030a', '#fed78f', '#4df676', '#cd1ea5', '#9f874d', '#b7d3f6', '#3b850d', '#009386',
  '#f97316', '#22c55e', '#f43f5e', '#a78bfa', '#eab308', '#06b6d4', '#84cc16',
]

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

function nodeKey(node: GraphNodeItem) {
  return `${node.type}:${node.id}`
}

function edgeNodeKey(node: GraphEdgeItem['from'] | GraphEdgeItem['to']) {
  return `${node.type}:${node.id}`
}

function nodeName(node: GraphNodeItem) {
  return String(node.title || node.name || node.text || node.canonical_name || node.id)
}

function nodeTypeLabel(nodeType: string, labels?: Record<string, string>, lang: 'zh' | 'en' = 'zh') {
  if (lang === 'en') return nodeType
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
  operation: '经营',
  policy: '政策',
  social: '社媒',
  market: '市场',
  other: '其他',
}

export default function GraphPage({ projectKey, variant }: Props) {
  const graphKind = TYPE_TO_KIND[variant]
  const chartRef = useRef<HTMLDivElement | null>(null)
  const graphWrapRef = useRef<HTMLDivElement | null>(null)
  const chartInstRef = useRef<echarts.ECharts | null>(null)

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [state, setState] = useState('')
  const [policyType, setPolicyType] = useState('')
  const [platform, setPlatform] = useState('')
  const [topic, setTopic] = useState('')
  const [game, setGame] = useState('')
  const [limit, setLimit] = useState(100)
  const [repulsion, setRepulsion] = useState(180)
  const [nodeScale, setNodeScale] = useState(100)
  const [nodeAlpha, setNodeAlpha] = useState(72)
  const [nodeGlow, setNodeGlow] = useState(60)
  const [showLabel, setShowLabel] = useState(true)
  const [legendLang, setLegendLang] = useState<'zh' | 'en'>('zh')
  const [hiddenTypes, setHiddenTypes] = useState<Record<string, boolean>>({})
  const [legendCols, setLegendCols] = useState(2)
  const [expandedGroup, setExpandedGroup] = useState<string | null>('policy')
  const [applyTick, setApplyTick] = useState(0)

  const graphConfig = useQuery({
    queryKey: ['graph-config', projectKey],
    queryFn: getGraphConfig,
    enabled: Boolean(projectKey),
  })

  const graphData = useQuery({
    queryKey: ['graph', projectKey, graphKind, applyTick, startDate, endDate, state, policyType, platform, topic, game, limit],
    queryFn: async () => {
      if (graphKind === 'policy') {
        return getPolicyGraph({ start_date: startDate, end_date: endDate, state, policy_type: policyType, limit })
      }
      if (graphKind === 'social') {
        return getSocialGraph({ start_date: startDate, end_date: endDate, platform, topic, limit })
      }
      return getMarketGraph({
        start_date: startDate,
        end_date: endDate,
        state,
        game,
        view: graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation'
          ? 'market_deep_entities'
          : undefined,
        limit,
      })
    },
    enabled: Boolean(projectKey),
  })

  const nodeTypes = useMemo(() => {
    const fromData = Array.from(new Set((graphData.data?.nodes || []).map((n) => n.type))).filter(Boolean)
    return fromData.sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [graphData.data?.nodes])

  const nodeTypeColor = useMemo(() => {
    const map: Record<string, string> = {}
    nodeTypes.forEach((type) => {
      const h = hashText(type)
      const base = NODE_TONE_PALETTE[h % NODE_TONE_PALETTE.length]
      const mix = ((h >> 8) % 20) / 100
      map[type] = tint(brightenHex(base), 0.06 + mix)
    })
    return map
  }, [nodeTypes])

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

  useEffect(() => {
    const onResize = () => chartInstRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstRef.current) chartInstRef.current = echarts.init(chartRef.current)
    return () => {
      if (chartInstRef.current) {
        chartInstRef.current.dispose()
        chartInstRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const chart = chartInstRef.current
    if (!chart) return
    const nodes = graphData.data?.nodes || []
    const edges = graphData.data?.edges || []

    const visibleNodes = nodes.filter((n) => !hiddenTypes[n.type])
    const visibleNodeKeys = new Set(visibleNodes.map(nodeKey))
    const visibleEdges = edges.filter((e) => visibleNodeKeys.has(edgeNodeKey(e.from)) && visibleNodeKeys.has(edgeNodeKey(e.to)))

    const degreeMap = new Map<string, number>()
    visibleEdges.forEach((edge) => {
      degreeMap.set(edgeNodeKey(edge.from), (degreeMap.get(edgeNodeKey(edge.from)) || 0) + 1)
      degreeMap.set(edgeNodeKey(edge.to), (degreeMap.get(edgeNodeKey(edge.to)) || 0) + 1)
    })
    const degrees = Array.from(degreeMap.values())
    const minDeg = degrees.length ? Math.min(...degrees) : 0
    const maxDeg = degrees.length ? Math.max(...degrees) : 1
    const rangeDeg = Math.max(maxDeg - minDeg, 1)

    const seriesNodes = visibleNodes.map((node) => {
      const key = nodeKey(node)
      const deg = degreeMap.get(key) || 0
      const size = Math.round((18 + ((deg - minDeg) / rangeDeg) * 28) * (nodeScale / 100))
      const show = showLabel && size >= 20
      const nodeColor = nodeTypeColor[node.type] || '#7dd3fc'
      const { r, g, b } = hexToRgb(nodeColor)
      return {
        id: key,
        name: nodeName(node),
        value: node,
        symbol: SYMBOLS[node.type] || 'circle',
        symbolSize: size,
        itemStyle: {
          color: `rgba(${r}, ${g}, ${b}, ${nodeAlpha / 100})`,
          borderColor: `rgba(${r}, ${g}, ${b}, 0.95)`,
          borderWidth: 1,
          shadowBlur: 6 + nodeGlow * 0.3,
          shadowColor: `rgba(${r}, ${g}, ${b}, ${Math.min(0.95, nodeGlow / 100)})`,
        },
        label: {
          show,
          color: '#dbeafe',
          fontSize: 11,
          formatter: () => {
            const raw = nodeName(node)
            return raw.length > 22 ? `${raw.slice(0, 22)}…` : raw
          },
        },
      }
    })

    const seriesEdges = visibleEdges.map((edge) => ({
      source: edgeNodeKey(edge.from),
      target: edgeNodeKey(edge.to),
      value: edge,
      lineStyle: {
        color: edge.type === 'POLICY_RELATION' ? 'rgba(125, 211, 252, 0.68)' : 'rgba(125, 211, 252, 0.2)',
        width: edge.type === 'POLICY_RELATION' ? 1.6 : 1,
        curveness: edge.type === 'POLICY_RELATION' ? 0.18 : 0,
      },
      label: {
        show: Boolean(edge.predicate),
        formatter: edge.predicate || '',
        color: 'rgba(147, 197, 253, 0.8)',
      },
    }))

    chart.setOption(
      {
        backgroundColor: '#030712',
        tooltip: {
          backgroundColor: 'rgba(2,6,23,0.92)',
          borderColor: '#334155',
          textStyle: { color: '#e2e8f0' },
          formatter(params: { dataType?: string; data?: { value?: GraphNodeItem | GraphEdgeItem } }) {
            if (params.dataType === 'node') {
              const node = (params.data?.value || {}) as GraphNodeItem
              return `类型: ${node.type}<br/>名称: ${nodeName(node)}`
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
            draggable: true,
            animationDurationUpdate: 250,
            force: {
              repulsion,
              edgeLength: [55, 180],
              gravity: 0.06,
              friction: 0.16,
            },
            data: seriesNodes,
            links: seriesEdges,
            lineStyle: { opacity: 0.85 },
            emphasis: {
              focus: 'adjacency',
              lineStyle: { width: 2 },
            },
          },
        ],
      },
      { lazyUpdate: true },
    )
  }, [graphData.data, hiddenTypes, repulsion, nodeScale, showLabel, nodeTypeColor, nodeAlpha, nodeGlow, graphKind])

  return (
    <div className="content-stack gv2-root">
      <section className="panel gv2-head">
        <div className="panel-header">
          <h2>{TYPE_LABEL[variant]}</h2>
          <div className="inline-actions">
            <button onClick={() => graphData.refetch()} disabled={graphData.isFetching}>刷新</button>
            <button
              onClick={() => {
                if (!graphWrapRef.current) return
                void graphWrapRef.current.requestFullscreen?.()
              }}
            >
              全屏查看
            </button>
          </div>
        </div>
      </section>

      <section className="panel gv2-controls">
        <div className="gv2-filter-grid">
          <label><span>开始日期</span><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
          <label><span>结束日期</span><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
          {(graphKind === 'policy' || graphKind === 'market' || graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation') ? (
            <label><span>州</span><input value={state} placeholder="CA / NY / TX" onChange={(e) => setState(e.target.value)} /></label>
          ) : null}
          {graphKind === 'policy' ? (
            <label><span>政策类型</span><input value={policyType} placeholder="regulation / bill" onChange={(e) => setPolicyType(e.target.value)} /></label>
          ) : null}
          {graphKind === 'social' ? (
            <>
              <label><span>平台</span><input value={platform} placeholder="reddit / twitter" onChange={(e) => setPlatform(e.target.value)} /></label>
              <label><span>主题</span><input value={topic} placeholder="关键词" onChange={(e) => setTopic(e.target.value)} /></label>
            </>
          ) : null}
          {(graphKind === 'market' || graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation') ? (
            <label><span>游戏</span><input value={game} placeholder="游戏名" onChange={(e) => setGame(e.target.value)} /></label>
          ) : null}
          <label><span>数量限制</span><input type="number" min={1} max={500} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} /></label>
          <div className="gv2-filter-actions">
            <button onClick={() => setApplyTick((x) => x + 1)}>应用筛选</button>
            <button className="secondary" onClick={() => {
              setStartDate('')
              setEndDate('')
              setState('')
              setPolicyType('')
              setPlatform('')
              setTopic('')
              setGame('')
              setLimit(100)
              setApplyTick((x) => x + 1)
            }}
            >
              重置
            </button>
          </div>
        </div>
      </section>

      <section className="kpi-grid">
        <article className="kpi-card"><span>节点数</span><strong>{stats.nodes}</strong></article>
        <article className="kpi-card"><span>关系数</span><strong>{stats.edges}</strong></article>
        <article className="kpi-card"><span>节点类型</span><strong>{stats.typeCount}</strong></article>
        <article className="kpi-card"><span>可见类型</span><strong>{nodeTypes.filter((t) => !hiddenTypes[t]).length}</strong></article>
      </section>

      <section className="panel gv2-main">
        <div className="gv2-layout" ref={graphWrapRef}>
          <div className="gv2-chart-wrap gv2-chart-wrap--fullscreen-ready">
            {graphData.isFetching ? <div className="gv2-loading">加载中...</div> : null}
            <div ref={chartRef} className="gv2-chart" />
            <div className="gv2-floating-controls">
              <label className="gv2-control-chip">
                节点斥力
                <input type="range" min={0} max={720} step={10} value={repulsion} onChange={(e) => setRepulsion(Number(e.target.value))} />
                <span>{repulsion}</span>
              </label>
              <label className="gv2-control-chip">
                节点尺寸
                <input type="range" min={50} max={180} step={5} value={nodeScale} onChange={(e) => setNodeScale(Number(e.target.value))} />
                <span>{nodeScale}%</span>
              </label>
              <label className="gv2-control-chip">
                节点透明
                <input type="range" min={20} max={95} step={5} value={nodeAlpha} onChange={(e) => setNodeAlpha(Number(e.target.value))} />
                <span>{nodeAlpha}%</span>
              </label>
              <label className="gv2-control-chip">
                荧光亮度
                <input type="range" min={10} max={100} step={5} value={nodeGlow} onChange={(e) => setNodeGlow(Number(e.target.value))} />
                <span>{nodeGlow}%</span>
              </label>
              <label className="gv2-control-chip">
                图例语言
                <select value={legendLang} onChange={(e) => setLegendLang(e.target.value as 'zh' | 'en')}>
                  <option value="zh">中文</option>
                  <option value="en">English</option>
                </select>
              </label>
              <label className="gv2-control-chip gv2-checkbox">
                <input type="checkbox" checked={showLabel} onChange={(e) => setShowLabel(e.target.checked)} />
                显示标签
              </label>
            </div>

            <div className="gv2-legend-dock">
              {legendGroups.map(([group, types]) => {
                const groupColor = nodeTypeColor[types[0]] || '#7dd3fc'
                const active = expandedGroup === group
                return (
                  <button
                    key={group}
                    type="button"
                    className={`gv2-legend-node ${active ? 'is-active' : ''}`}
                    title={GROUP_LABEL[group] || group}
                    onClick={() => setExpandedGroup((prev) => (prev === group ? null : group))}
                  >
                    <span className="dot" style={{ background: groupColor }} />
                  </button>
                )
              })}
            </div>

            {expandedGroup ? (
              <div className="gv2-legend-pop">
                <div className="gv2-legend-top">
                  <strong>{GROUP_LABEL[expandedGroup] || expandedGroup}</strong>
                  <label>
                    分栏
                    <select value={legendCols} onChange={(e) => setLegendCols(Number(e.target.value))}>
                      <option value={1}>1</option>
                      <option value={2}>2</option>
                      <option value={3}>3</option>
                    </select>
                  </label>
                </div>
                <div className="gv2-type-list" style={{ gridTemplateColumns: `repeat(${legendCols}, minmax(0, 1fr))` }}>
                  {(legendGroups.find(([group]) => group === expandedGroup)?.[1] || []).map((t) => {
                    const hidden = Boolean(hiddenTypes[t])
                    return (
                      <button
                        key={t}
                        type="button"
                        className={`gv2-type ${hidden ? 'is-hidden' : ''}`}
                        onClick={() => setHiddenTypes((prev) => ({ ...prev, [t]: !prev[t] }))}
                      >
                        <span className="dot" style={{ background: nodeTypeColor[t] || '#7dd3fc' }} />
                        <span>{nodeTypeLabel(t, graphConfig.data?.graph_node_labels, legendLang)}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  )
}
