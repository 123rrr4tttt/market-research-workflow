import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { EChartsType } from 'echarts/core'
import { Maximize } from 'lucide-react'
import type { GraphEdgeItem, GraphNodeItem } from '../../lib/types'
import { loadGraphEchartsCore } from './renderers/loadGraphEchartsCore'
import { graphCanvasPixelRatio } from './renderers/canvasPixelRatio'
import type { ProjectGraphRelationType } from './realizer/projectGraphView'
import { buildProjectGraphTypeGraph } from './realizer/projectGraphTypeGraph'
import './project-graph-type-view.css'

type Props = {
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
  declaredNodeTypes: string[]
  declaredRelationTypes: ProjectGraphRelationType[]
  nodeTypeColor: Record<string, string>
  typeLabel: (type: string) => string
  title: string
  emptyLabel: string
  fitLabel: string
  relationsLabel: string
  allRelationsLabel: string
  errorLabel: string
}

type ChartNodePosition = { x?: number; y?: number }

const CHART_SERIES_ID = 'project-graph-type'

function relationIdentity(relation: ProjectGraphRelationType) {
  return `${relation.sourceType}\0${relation.relation}\0${relation.targetType}`
}

function truncateLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value
}

function relationColor(relation: ProjectGraphRelationType) {
  let hash = 0
  const value = relationIdentity(relation)
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash * 31) + value.charCodeAt(index)) >>> 0
  }
  return `hsl(${hash % 360} 64% 70%)`
}

function safeRichText(value: string) {
  return value.replace(/[{}<>&]/g, (char) => ({ '{': '｛', '}': '｝', '<': '＜', '>': '＞', '&': '＆' })[char] || char)
}

export function ProjectGraphTypeView({
  nodes,
  edges,
  declaredNodeTypes,
  declaredRelationTypes,
  nodeTypeColor,
  typeLabel,
  title,
  emptyLabel,
  fitLabel,
  relationsLabel,
  allRelationsLabel,
  errorLabel,
}: Props) {
  const chartElementRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<EChartsType | null>(null)
  const nodePositionsRef = useRef<Map<string, ChartNodePosition>>(new Map())
  const [chartReady, setChartReady] = useState(false)
  const [chartFailed, setChartFailed] = useState(false)
  const [relationFocus, setRelationFocus] = useState('')

  const graph = useMemo(
    () => buildProjectGraphTypeGraph(nodes, edges, declaredNodeTypes, declaredRelationTypes),
    [declaredNodeTypes, declaredRelationTypes, edges, nodes],
  )
  const relationTokens = useMemo(() => Array.from(new Set(graph.relations.map((relation) => relation.relation))).sort(), [graph.relations])
  const effectiveRelationFocus = relationTokens.includes(relationFocus) ? relationFocus : ''
  const visibleRelations = useMemo(() => graph.relations.filter((relation) => !effectiveRelationFocus || relation.relation === effectiveRelationFocus), [effectiveRelationFocus, graph.relations])
  const relationRows = useMemo(
    () => visibleRelations.map((relation) => ({
      relation,
      label: relation.relation,
      sourceLabel: typeLabel(relation.sourceType),
      targetLabel: typeLabel(relation.targetType),
      color: relationColor(relation),
    })),
    [visibleRelations, typeLabel],
  )
  const hasGraph = graph.nodeTypes.length > 0
  const selfRelationsByType = useMemo(() => {
    const result = new Map<string, ProjectGraphRelationType[]>()
    visibleRelations.forEach((relation) => {
      if (relation.sourceType !== relation.targetType) return
      const current = result.get(relation.sourceType) || []
      current.push(relation)
      result.set(relation.sourceType, current)
    })
    return result
  }, [visibleRelations])

  useEffect(() => {
    let canceled = false
    void loadGraphEchartsCore().then((echarts) => {
      if (canceled || !chartElementRef.current || chartRef.current) return
      const chart = echarts.init(chartElementRef.current, undefined, {
        renderer: 'canvas',
        useDirtyRect: true,
        devicePixelRatio: graphCanvasPixelRatio(),
      })
      chartRef.current = chart
      setChartReady(true)
    }).catch(() => { if (!canceled) setChartFailed(true) })
    return () => {
      canceled = true
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const element = chartElementRef.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      chartRef.current?.resize()
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !chartReady) return

    try {
      const current = chart.getOption() as {
        series?: Array<{ data?: Array<{ id?: string; x?: number; y?: number }> }>
      }
      current.series?.[0]?.data?.forEach((item) => {
        const id = String(item.id || '')
        if (!id) return
        nodePositionsRef.current.set(id, { x: item.x, y: item.y })
      })
    } catch {
      // Keep the last force positions when ECharts reports an intermediate option.
    }

    const radius = Math.max(110, Math.min(190, 44 + graph.nodeTypes.length * 15))
    const chartNodes = graph.nodeTypes.map((type, index) => {
      const previous = nodePositionsRef.current.get(type)
      const angle = (index / Math.max(1, graph.nodeTypes.length)) * Math.PI * 2
      return {
        id: type,
        name: typeLabel(type),
        x: previous?.x ?? Math.cos(angle) * radius,
        y: previous?.y ?? Math.sin(angle) * radius,
        symbolSize: 30,
        value: { type },
        itemStyle: {
          color: nodeTypeColor[type] || '#7dd3fc',
          borderColor: '#02050b',
          borderWidth: 1.5,
        },
        label: {
          show: true,
          position: 'bottom',
          distance: 8,
          color: '#dbeafe',
          fontSize: 11,
          // Native graph self-loops collapse to zero-length curves in ECharts;
          // project their relations onto the type node as visible loop badges.
          formatter: () => `${truncateLabel(typeLabel(type), 22)}${selfRelationsByType.has(type) ? ` ↺${effectiveRelationFocus ? ` ${truncateLabel(effectiveRelationFocus, 16)}` : ''}` : ''}`,
        },
      }
    })

    const parallelCounts = new Map<string, number>()
    visibleRelations.forEach((relation) => {
      if (relation.sourceType === relation.targetType) return
      const key = JSON.stringify([relation.sourceType, relation.targetType].sort())
      parallelCounts.set(key, (parallelCounts.get(key) || 0) + 1)
    })
    const parallelIndex = new Map<string, number>()
    const chartLinks = visibleRelations.filter((relation) => relation.sourceType !== relation.targetType).map((relation) => {
      const unorderedKey = JSON.stringify([relation.sourceType, relation.targetType].sort())
      const index = parallelIndex.get(unorderedKey) || 0
      parallelIndex.set(unorderedKey, index + 1)
      const color = relationColor(relation)
      const count = parallelCounts.get(unorderedKey) || 1
      const curvature = (index - (count - 1) / 2) * Math.min(0.14, 0.84 / Math.max(1, count - 1))
      const curveness = relation.sourceType < relation.targetType ? curvature : -curvature
      return {
        source: relation.sourceType,
        target: relation.targetType,
        value: relation,
        symbol: ['none', 'arrow'],
        symbolSize: 9,
        lineStyle: { color, width: effectiveRelationFocus ? 1.6 : 1, curveness, opacity: effectiveRelationFocus ? 0.88 : 0.16 },
        label: {
          show: Boolean(effectiveRelationFocus),
          formatter: () => truncateLabel(relation.relation, 18),
          color,
          fontSize: 10,
          backgroundColor: 'rgba(2, 6, 23, 0.82)',
          padding: [2, 4],
          borderRadius: 3,
        },
        emphasis: { label: { show: true }, lineStyle: { width: 2, opacity: 1 } },
      }
    })

    chart.setOption(
      {
        backgroundColor: '#02050b',
        tooltip: {
          trigger: 'item',
          renderMode: 'richText',
          backgroundColor: 'rgba(2, 6, 23, 0.94)',
          borderColor: '#334155',
          padding: 8,
          textStyle: { color: '#e2e8f0', fontSize: 12 },
          formatter(params: { dataType?: string; data?: { value?: { type?: string; count?: number } | ProjectGraphRelationType } }) {
            if (params.dataType === 'node') {
              const value = params.data?.value as { type?: string; count?: number } | undefined
              const type = String(value?.type || '')
              return [
                safeRichText(typeLabel(type)),
                ...(selfRelationsByType.get(type) || []).map((relation) => `↺ ${safeRichText(relation.relation)}`),
              ].join('\n')
            }
            if (params.dataType === 'edge') {
              const value = params.data?.value as ProjectGraphRelationType | undefined
              if (!value) return ''
              return safeRichText(
                `${typeLabel(value.sourceType)} → ${value.relation} → ${typeLabel(value.targetType)}`,
              )
            }
            return ''
          },
        },
        series: [{
          id: CHART_SERIES_ID,
          type: 'graph',
          layout: 'circular',
          circular: { rotateLabel: false },
          preserveAspect: 'contain',
          roam: true,
          draggable: true,
          animation: false,
          progressive: 0,
          left: 20,
          right: 20,
          top: 26,
          bottom: 42,
          data: chartNodes,
          links: chartLinks,
          emphasis: { focus: 'adjacency', scale: false },
        }],
      },
      { replaceMerge: ['series'] },
    )
  }, [chartReady, effectiveRelationFocus, graph, nodeTypeColor, selfRelationsByType, typeLabel, visibleRelations])

  const handleFit = useCallback(() => {
    chartRef.current?.setOption({
      series: [{ id: CHART_SERIES_ID, center: ['50%', '50%'], zoom: 1 }],
    })
  }, [])

  return (
    <section className="gv2-type-view" aria-label={title} data-testid="graph-type-view">
      <header className="gv2-type-view-header">
        <h3>{title}</h3>
        <select aria-label={relationsLabel} data-testid="graph-type-relation-filter" value={effectiveRelationFocus} onChange={(event) => setRelationFocus(event.target.value)}>
          <option value="">{allRelationsLabel}</option>
          {relationTokens.map((token) => <option key={token} value={token}>{token}</option>)}
        </select>
        <button
          type="button"
          onClick={handleFit}
          title={fitLabel}
          aria-label={fitLabel}
          disabled={!chartReady || !hasGraph}
        >
          <Maximize aria-hidden="true" size={14} />
        </button>
      </header>
      <div className="gv2-type-chart" data-testid="graph-type-chart" role="img" aria-label={title} aria-description={graph.nodeTypes.map(typeLabel).join(', ')}>
        <div ref={chartElementRef} className="gv2-type-canvas" />
        {!hasGraph ? <p>{emptyLabel}</p> : null}
        {chartFailed ? <p role="alert">{errorLabel}</p> : null}
      </div>
      {hasGraph ? (
        <details className="gv2-type-relations" data-testid="graph-type-view-relations">
          <summary>{`${relationsLabel} · ${relationRows.length}`}</summary>
          <ul>
            {relationRows.map((row) => (
              <li key={relationIdentity(row.relation)} style={{ borderColor: row.color }}>
                <span>{row.sourceLabel}</span>
                <strong>{row.label}</strong>
                <span>{row.targetLabel}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  )
}
