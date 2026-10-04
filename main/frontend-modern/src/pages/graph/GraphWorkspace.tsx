import './GraphWorkspace.css'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { EChartsType } from 'echarts/core'
import { GRAPH_COLOR_THEMES, assignLegendColors, type PaletteKey } from '../../lib/graph-colors'
import type { GraphEdgeItem } from '../../lib/types'
import { applyRenderer2D } from './renderers/renderer2dEcharts'
import { graphCanvasPixelRatio } from './renderers/canvasPixelRatio'
import { edgeLinePattern, graphEdgeProfile } from './realizer/edgeStyleLibrary'
import type { RenderNode } from './renderers/types'
import { useGraphVisualState } from './hooks/useGraphVisualState'

export type GraphWorkspaceNode = {
  id: string
  name: string
  type: string
  symbolSize?: number
  color?: string
  detail?: string[]
}

export type GraphWorkspaceEdge = {
  source: string
  target: string
  type: string
  color?: string
  dashed?: boolean
  arrow?: boolean
}

type Props = {
  nodes: GraphWorkspaceNode[]
  edges: GraphWorkspaceEdge[]
  loading?: boolean
  error?: string | null
  resetKey: string
  testId?: string
  toolbar?: ReactNode
  controls?: ReactNode
  onNodeClick?: (nodeId: string) => void
  dataAttributes?: Record<string, string | number>
}

let echartsCorePromise: Promise<typeof import('echarts/core')> | null = null

function loadGraphEchartsCore() {
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

function groupLabel(type: string) {
  return type.split(':')[0]
}

export default function GraphWorkspace({
  nodes,
  edges,
  loading = false,
  error = null,
  resetKey,
  testId = 'graph-workspace',
  toolbar,
  controls,
  onNodeClick,
  dataAttributes = {},
}: Props) {
  const paletteKey: PaletteKey = 'bcp_unified'
  const palette = GRAPH_COLOR_THEMES[paletteKey]
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstRef = useRef<EChartsType | null>(null)
  const positionRef = useRef<Record<string, { x?: number; y?: number }>>({})
  const onNodeClickRef = useRef<((nodeId: string) => void) | undefined>(undefined)
  const [chartReady, setChartReady] = useState(false)
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<Record<string, boolean>>({})
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<Record<string, boolean>>({})
  const [expandedNodeGroup, setExpandedNodeGroup] = useState<string | null>(null)
  const [expandedEdgeGroup, setExpandedEdgeGroup] = useState<string | null>(null)
  const [showOverlay, setShowOverlay] = useState(true)
  const { visualDraft, visualApplied, updateVisual, startVisualInteraction, endVisualInteraction } = useGraphVisualState()

  const nodeTypes = useMemo(
    () => Array.from(new Set(nodes.map((node) => node.type))).sort((a, b) => a.localeCompare(b, 'zh-CN')),
    [nodes],
  )
  const edgeTypes = useMemo(
    () => Array.from(new Set(edges.map((edge) => edge.type))).sort((a, b) => a.localeCompare(b, 'zh-CN')),
    [edges],
  )
  const nodeTypeColor = useMemo(
    () => assignLegendColors(nodeTypes, paletteKey, 'node', { contrast: 0.58, spread: 1.16, domainExpand: 0.24 }),
    [nodeTypes, paletteKey],
  )
  const edgeTypeColor = useMemo(
    () => assignLegendColors(edgeTypes, paletteKey, 'edge', { contrast: 0.52, spread: 0.82, domainExpand: 0.2 }),
    [edgeTypes, paletteKey],
  )
  const nodeGroups = useMemo(() => {
    const groups = new Map<string, string[]>()
    nodeTypes.forEach((type) => {
      const group = groupLabel(type)
      groups.set(group, [...(groups.get(group) || []), type])
    })
    return Array.from(groups.entries())
  }, [nodeTypes])
  const edgeGroups = useMemo(() => {
    const groups = new Map<string, string[]>()
    edgeTypes.forEach((type) => {
      const group = groupLabel(type)
      groups.set(group, [...(groups.get(group) || []), type])
    })
    return Array.from(groups.entries())
  }, [edgeTypes])

  const visibleNodes = useMemo(
    () => nodes.filter((node) => !hiddenNodeTypes[node.type]),
    [nodes, hiddenNodeTypes],
  )
  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes])
  const visibleEdges = useMemo(
    () => edges.filter((edge) =>
      !hiddenEdgeTypes[edge.type] && visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)),
    [edges, hiddenEdgeTypes, visibleNodeIds],
  )

  useEffect(() => {
    onNodeClickRef.current = onNodeClick
  }, [onNodeClick])

  const handleNodeClick = useCallback((nodeId: string) => {
    onNodeClickRef.current?.(nodeId)
  }, [])

  useEffect(() => {
    let canceled = false
    void loadGraphEchartsCore().then((echarts) => {
      if (canceled || !chartRef.current || chartInstRef.current) return
      const chart = echarts.init(chartRef.current, undefined, {
        renderer: 'canvas',
        useDirtyRect: true,
        devicePixelRatio: graphCanvasPixelRatio(),
      })
      chart.on('click', (params) => {
        const dataType = (params as { dataType?: string }).dataType
        const data = (params as { data?: { id?: unknown } }).data
        if (dataType === 'node' && typeof data?.id === 'string' && data.id) handleNodeClick(data.id)
      })
      chartInstRef.current = chart
      ;(window as unknown as { __GRAPH_WORKSPACE_CHART__?: EChartsType }).__GRAPH_WORKSPACE_CHART__ = chart
      setChartReady(true)
    })
    return () => {
      canceled = true
    }
  }, [handleNodeClick])

  useEffect(() => () => {
    chartInstRef.current?.dispose()
    chartInstRef.current = null
    delete (window as unknown as { __GRAPH_WORKSPACE_CHART__?: unknown }).__GRAPH_WORKSPACE_CHART__
  }, [])

  useEffect(() => {
    const chart = chartInstRef.current
    if (!chart) return
    chart.setOption({ series: [] }, { replaceMerge: ['series'] })
    positionRef.current = {}
  }, [resetKey, chartReady])

  useEffect(() => {
    const chart = chartInstRef.current
    if (!chart || !chartReady) return

    let currentCenter: [number, number] | undefined
    let currentZoom: number | undefined
    try {
      const current = chart.getOption() as {
        series?: Array<{ center?: [number, number]; zoom?: number; data?: Array<{ id?: string; x?: number; y?: number }> }>
      }
      const currentSeries = current.series?.[0]
      currentSeries?.data?.forEach((item) => {
        if (!item.id) return
        positionRef.current[item.id] = { x: item.x, y: item.y }
      })
      if (Array.isArray(currentSeries?.center)) currentCenter = currentSeries.center
      if (typeof currentSeries?.zoom === 'number') currentZoom = currentSeries.zoom
    } catch {
      // A fresh force layout remains valid when option inspection fails.
    }

    const nodeScale = Math.max(0, Math.min(2.4, visualApplied.nodeScale / 100))
    const alpha = Math.max(0, Math.min(1, visualApplied.nodeAlpha / 100))
    const edgeAlpha = Math.max(0, Math.min(1, visualApplied.edgeAlpha / 100))
    const edgeWidth = Math.max(0, Math.min(2.4, visualApplied.edgeWidth / 100))
    const renderNodes: RenderNode[] = visibleNodes.map((node) => ({
      id: node.id,
      name: node.id,
      x: positionRef.current[node.id]?.x,
      y: positionRef.current[node.id]?.y,
      symbolSize: Math.max(8, (node.symbolSize || 30) * nodeScale),
      value: { type: node.type, name: node.name, detail: node.detail },
      itemStyle: {
        color: node.color || nodeTypeColor[node.type] || palette.anchors[1],
        borderColor: 'rgba(15, 23, 42, 0.85)',
        borderWidth: 1,
        opacity: alpha,
      },
      label: {
        show: visualApplied.showLabel,
        position: 'bottom',
        distance: 8,
        color: '#dbeafe',
        fontSize: 10,
        formatter: () => (node.name.length > 24 ? `${node.name.slice(0, 24)}…` : node.name),
      },
    }))
    const applied = applyRenderer2D(renderNodes)
    const links = visibleEdges.map((edge) => {
      const profile = graphEdgeProfile({ type: edge.type, predicate: edge.type } as GraphEdgeItem)
      return {
        source: edge.source,
        target: edge.target,
        value: { type: edge.type },
        symbol: edge.arrow === false ? ['none', 'none'] : profile.symbol,
        symbolSize: edge.arrow === false ? [0, 0] : profile.symbolSize,
        lineStyle: {
          color: edge.color || edgeTypeColor[edge.type] || palette.anchors[0],
          width: Math.max(0.4, profile.width * edgeWidth),
          opacity: edgeAlpha,
          type: edge.dashed ? 'dashed' : edgeLinePattern(profile.lineType),
          curveness: profile.curveness,
        },
      }
    })

    chart.setOption(
      {
        backgroundColor: '#030712',
        tooltip: {
          triggerOn: 'click',
          backgroundColor: 'rgba(2,6,23,0.92)',
          borderColor: '#334155',
          textStyle: { color: '#e2e8f0' },
          formatter(params: { dataType?: string; data?: { id?: unknown } }) {
            if (params.dataType !== 'node') return ''
            const id = String(params.data?.id || '')
            const node = visibleNodes.find((item) => item.id === id)
            return [node?.name || id, node ? `<code>${node.id}</code>` : null, ...(node?.detail || [])]
              .filter(Boolean)
              .join('<br/>')
          },
        },
        series: [{
          id: 'graph-workspace',
          type: 'graph',
          layout: applied.series.layout,
          roam: true,
          draggable: true,
          center: currentCenter,
          zoom: currentZoom,
          animation: applied.series.animation,
          animationDurationUpdate: applied.series.animationDurationUpdate,
          animationEasingUpdate: applied.series.animationEasingUpdate,
          progressive: 0,
          force: {
            repulsion: visualApplied.repulsion,
            edgeLength: [55, 180],
            gravity: Math.max(0, Math.min(0.6, 0.1 * (visualApplied.gravityPercent / 100))),
            friction: 0.16,
            layoutAnimation: true,
          },
          data: applied.nodes,
          links,
          labelLayout: { hideOverlap: true },
          emphasis: { focus: 'adjacency', scale: true },
        }],
      },
      { lazyUpdate: true },
    )
  }, [chartReady, visibleNodes, visibleEdges, visualApplied, nodeTypeColor, edgeTypeColor, palette.anchors])

  useEffect(() => {
    const chart = chartInstRef.current
    if (!chart) return
    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [chartReady])

  const sliderHandlers = {
    onPointerDown: () => startVisualInteraction(),
    onPointerUp: () => endVisualInteraction(),
    onPointerCancel: () => endVisualInteraction(),
    onBlur: () => endVisualInteraction(),
  }
  const hasHidden = Object.values(hiddenNodeTypes).some(Boolean) || Object.values(hiddenEdgeTypes).some(Boolean)

  return (
    <div className="gv2-chart-wrap gv2-chart-wrap--fullscreen-ready" data-testid={testId} {...dataAttributes}>
      {loading ? <div className="gv2-loading" role="status">正在加载数据…</div> : null}
      {error ? <div className="gv2-loading gv2-loading-error" role="alert">{error}</div> : null}
      <div ref={chartRef} className="gv2-chart" />
      <div className="gv2-floating-toolbar-layer">
        <div className="gv2-overlay-top">
          {toolbar}
          <button type="button" className="gv2-select-mode-btn" onClick={() => setShowOverlay((value) => !value)}>
            {showOverlay ? '收起面板' : '展开面板'}
          </button>
        </div>
      </div>

      <aside className={`gv2-floating-controls${showOverlay ? '' : ' is-collapsed'}`} aria-label="图谱控制">
        <section className="gv2-control-section">
          <button
            type="button"
            className="gv2-control-section-head"
            onClick={() => updateVisual('showLabel', !visualDraft.showLabel, { immediate: true })}
          >
            <strong>视图</strong>
            <span>{visualDraft.showLabel ? '标签开' : '标签关'}</span>
          </button>
          {showOverlay ? (
            <div className="gv2-control-section-body">
              <label className="gv2-control-chip">
                斥力
                <input
                  type="range"
                  min={0}
                  max={200}
                  step={0.1}
                  {...sliderHandlers}
                  value={visualDraft.repulsion / 7.2}
                  onChange={(event) => updateVisual('repulsion', Number(event.target.value) * 7.2, { mode: 'raf' })}
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
                  {...sliderHandlers}
                  value={visualDraft.gravityPercent}
                  onChange={(event) => updateVisual('gravityPercent', Number(event.target.value), { mode: 'raf' })}
                />
                <span>{visualDraft.gravityPercent}%</span>
              </label>
              <label className="gv2-control-chip">
                节点大小
                <input
                  type="range"
                  min={35}
                  max={220}
                  step={0.5}
                  {...sliderHandlers}
                  value={visualDraft.nodeScale}
                  onChange={(event) => updateVisual('nodeScale', Number(event.target.value), { mode: 'throttle', delayMs: 80 })}
                />
                <span>{visualDraft.nodeScale}%</span>
              </label>
              <label className="gv2-control-chip">
                节点透明度
                <input
                  type="range"
                  min={10}
                  max={100}
                  step={1}
                  {...sliderHandlers}
                  value={visualDraft.nodeAlpha}
                  onChange={(event) => updateVisual('nodeAlpha', Number(event.target.value), { mode: 'raf' })}
                />
                <span>{visualDraft.nodeAlpha}%</span>
              </label>
              <label className="gv2-control-chip">
                边宽
                <input
                  type="range"
                  min={20}
                  max={220}
                  step={1}
                  {...sliderHandlers}
                  value={visualDraft.edgeWidth}
                  onChange={(event) => updateVisual('edgeWidth', Number(event.target.value), { mode: 'raf' })}
                />
                <span>{visualDraft.edgeWidth}%</span>
              </label>
              <label className="gv2-control-chip">
                边透明度
                <input
                  type="range"
                  min={10}
                  max={100}
                  step={1}
                  {...sliderHandlers}
                  value={visualDraft.edgeAlpha}
                  onChange={(event) => updateVisual('edgeAlpha', Number(event.target.value), { mode: 'raf' })}
                />
                <span>{visualDraft.edgeAlpha}%</span>
              </label>
            </div>
          ) : null}
        </section>
        {showOverlay ? controls : null}
      </aside>

      <aside className={`gv2-legend-float${showOverlay ? '' : ' is-collapsed'}`} aria-label="图谱图例">
        <div className="gv2-legend-groups">
          {nodeGroups.map(([group, types]) => (
            <button
              key={group}
              type="button"
              className={`gv2-legend-node${expandedNodeGroup === group ? ' is-active' : ''}`}
              onClick={() => setExpandedNodeGroup((prev) => (prev === group ? null : group))}
              onDoubleClick={() => setHiddenNodeTypes((prev) => {
                const next = { ...prev }
                const makeVisible = types.some((type) => !next[type])
                types.forEach((type) => { next[type] = makeVisible })
                return next
              })}
            >
              <i className="dot" style={{ background: nodeTypeColor[types[0]] || '#7dd3fc' }} aria-hidden />
              <span className="gv2-legend-node-label">{group}</span>
            </button>
          ))}
        </div>
        {expandedNodeGroup ? (
          <div className="gv2-type-grid">
            {(nodeGroups.find(([group]) => group === expandedNodeGroup)?.[1] || []).map((type) => (
              <button
                key={type}
                type="button"
                className={`gv2-type${hiddenNodeTypes[type] ? ' is-hidden' : ''}`}
                onClick={() => setHiddenNodeTypes((prev) => ({ ...prev, [type]: !prev[type] }))}
              >
                <i className="dot" style={{ background: nodeTypeColor[type] || '#7dd3fc' }} aria-hidden />
                <span>{type}</span>
              </button>
            ))}
          </div>
        ) : null}
        {edgeGroups.length ? (
          <div className="gv2-legend-edge-wrap">
            <div className="gv2-legend-section-title">边</div>
            <div className="gv2-legend-groups gv2-edge-legend-groups">
              {edgeGroups.map(([group, types]) => (
                <button
                  key={group}
                  type="button"
                  className={`gv2-legend-node gv2-edge-legend-node${expandedEdgeGroup === group ? ' is-active' : ''}`}
                  onClick={() => setExpandedEdgeGroup((prev) => (prev === group ? null : group))}
                  onDoubleClick={() => setHiddenEdgeTypes((prev) => {
                    const next = { ...prev }
                    const makeVisible = types.some((type) => !next[type])
                    types.forEach((type) => { next[type] = makeVisible })
                    return next
                  })}
                >
                  <span
                    className="gv2-edge-line-badge"
                    style={{ '--edge-color': edgeTypeColor[types[0]] || '#7dd3fc' } as CSSProperties}
                  >
                    <i />
                  </span>
                  <span className="gv2-legend-node-label">{group}</span>
                </button>
              ))}
            </div>
            {expandedEdgeGroup ? (
              <div className="gv2-type-grid gv2-edge-type-grid">
                {(edgeGroups.find(([group]) => group === expandedEdgeGroup)?.[1] || []).map((type) => (
                  <button
                    key={type}
                    type="button"
                    className={`gv2-type gv2-type--edge${hiddenEdgeTypes[type] ? ' is-hidden' : ''}`}
                    onClick={() => setHiddenEdgeTypes((prev) => ({ ...prev, [type]: !prev[type] }))}
                  >
                    <span
                      className="gv2-edge-line-badge"
                      style={{ '--edge-color': edgeTypeColor[type] || '#7dd3fc' } as CSSProperties}
                    >
                      <i />
                    </span>
                    <span>{type}</span>
                    <small>{edges.filter((edge) => edge.type === type).length}</small>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {hasHidden ? (
          <button
            type="button"
            className="gv2-legend-restore"
            onClick={() => {
              setHiddenNodeTypes({})
              setHiddenEdgeTypes({})
            }}
          >
            恢复全部
          </button>
        ) : null}
      </aside>
    </div>
  )
}
