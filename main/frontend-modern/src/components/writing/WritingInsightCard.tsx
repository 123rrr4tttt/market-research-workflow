import { useMemo, useState, type CSSProperties, type DragEvent, type MouseEventHandler } from 'react'
import GraphBusinessCardSections from '../GraphBusinessCardSections'
import GraphExtensionsSections, { type GraphElementGroup, type GraphRelationGroup } from '../GraphExtensionsSections'
import GraphNodeCard from '../graph-kit/GraphNodeCard'
import type { WritingKeywordCardDetail, WritingKeywordCardPreview } from '../../lib/api'
import { toDraggedCardPayload, writeDraggedCard } from './dragPayload'

export type WritingInsightCardProps = {
  preview?: WritingKeywordCardPreview | null
  detail?: WritingKeywordCardDetail | null
  loading?: boolean
  pinned?: boolean
  style?: CSSProperties
  onClose?: () => void
  onHeadMouseDown?: MouseEventHandler<HTMLDivElement>
  onAddCitation?: (cardId: string) => void
  onTogglePin?: () => void
  onDragCardStart?: (cardId: string) => void
  onDragCardEnd?: () => void
}

type WritingCardTab = 'business' | 'graph_ext'

function sourceLabel(preview?: WritingKeywordCardPreview | null, detail?: WritingKeywordCardDetail | null) {
  return detail?.publisher || preview?.publisher || detail?.source_type || preview?.source_type || 'reference'
}

function normalizeValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map((item) => normalizeValue(item)).filter(Boolean).join(' | ')
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function buildBusinessNode(preview?: WritingKeywordCardPreview | null, detail?: WritingKeywordCardDetail | null) {
  const infoCard = detail || preview
  if (!infoCard) return null
  return {
    id: infoCard.card_id,
    type: infoCard.source_type,
    title: infoCard.title,
    name: sourceLabel(preview, detail),
    status: detail ? 'resolved' : 'preview',
    publish_date: detail?.published_at || detail?.retrieved_at || '',
    summary: detail?.evidence || preview?.snippet || '',
    content: detail?.evidence || '',
    keywords: preview?.quick_actions || [],
    url: infoCard.url || '',
    publisher: sourceLabel(preview, detail),
    normalized_query: detail?.normalized_query || '',
    extracted_data: detail
      ? {
          provenance: detail.provenance,
          selection_matches: detail.selection_matches,
        }
      : undefined,
  }
}

function buildGraphExtension(preview?: WritingKeywordCardPreview | null, detail?: WritingKeywordCardDetail | null) {
  const provenanceEntries = Object.entries(detail?.provenance || {})
  const matchEntries = Object.entries(detail?.selection_matches || {})
  const quickActions = preview?.quick_actions || []

  const nodeElementGroups: GraphElementGroup[] = [
    quickActions.length
      ? {
          label: 'quick_actions',
          items: quickActions.map((value, index) => ({ id: `qa-${index}`, value, label: 'quick_actions' })),
        }
      : null,
    detail?.normalized_query
      ? {
          label: 'normalized_query',
          items: detail.normalized_query
            .split(/\s+/)
            .filter(Boolean)
            .map((value, index) => ({ id: `query-${index}`, value, label: 'normalized_query' })),
        }
      : null,
    detail?.publisher
      ? {
          label: 'publisher',
          items: [{ id: 'publisher-0', value: detail.publisher, label: 'publisher' }],
        }
      : null,
  ].filter(Boolean) as GraphElementGroup[]

  const relationGroups: GraphRelationGroup[] = [
    provenanceEntries.length
      ? {
          relation: 'provenance',
          items: provenanceEntries.map(([key, value], index) => ({
            id: `prov-${index}`,
            direction: 'OUT' as const,
            relation: key,
            targetName: normalizeValue(value) || key,
            targetType: 'Provenance',
          })),
        }
      : null,
    matchEntries.length
      ? {
          relation: 'selection_matches',
          items: matchEntries.map(([key, value], index) => ({
            id: `match-${index}`,
            direction: 'OUT' as const,
            relation: key,
            targetName: normalizeValue(value) || key,
            targetType: 'Match',
          })),
        }
      : null,
  ].filter(Boolean) as GraphRelationGroup[]

  const graphInfo = {
    degree: provenanceEntries.length + matchEntries.length,
    neighborTypeCount: [
      provenanceEntries.length ? 'provenance' : null,
      matchEntries.length ? 'selection_matches' : null,
      quickActions.length ? 'quick_actions' : null,
    ].filter(Boolean).length,
    marketDocCount: relationGroups.reduce((sum, group) => sum + group.items.length, 0),
    neighborTypeItems: [
      provenanceEntries.length ? { type: 'provenance', count: provenanceEntries.length } : null,
      matchEntries.length ? { type: 'selection_matches', count: matchEntries.length } : null,
      quickActions.length ? { type: 'quick_actions', count: quickActions.length } : null,
    ].filter(Boolean) as Array<{ type: string; count: number }>,
    predicateItems: relationGroups.map((group) => ({ predicate: group.relation, count: group.items.length })),
    neighborNodesByType: {
      ...(provenanceEntries.length
        ? {
            provenance: provenanceEntries.map(([key, value], index) => ({
              id: `prov-node-${index}`,
              name: `${key}: ${normalizeValue(value) || key}`,
              type: 'Provenance',
            })),
          }
        : {}),
      ...(matchEntries.length
        ? {
            selection_matches: matchEntries.map(([key, value], index) => ({
              id: `match-node-${index}`,
              name: `${key}: ${normalizeValue(value) || key}`,
              type: 'Match',
            })),
          }
        : {}),
      ...(quickActions.length
        ? {
            quick_actions: quickActions.map((value, index) => ({
              id: `qa-node-${index}`,
              name: value,
              type: 'Action',
            })),
          }
        : {}),
    },
    relationsByPredicate: Object.fromEntries(
      relationGroups.map((group) => [
        group.relation,
        group.items.map((item) => ({
          id: item.id,
          direction: item.direction,
          targetName: item.targetName,
          targetType: item.targetType,
        })),
      ]),
    ),
  }

  return {
    graphInfo,
    nodeElementGroups,
    relationGroups,
    nodeTypeColor: {
      Provenance: '#93c5fd',
      Match: '#86efac',
      Action: '#f9a8d4',
    },
  }
}

export default function WritingInsightCard({
  preview,
  detail,
  loading = false,
  pinned = false,
  style,
  onClose,
  onHeadMouseDown,
  onAddCitation,
  onTogglePin,
  onDragCardStart,
  onDragCardEnd,
}: WritingInsightCardProps) {
  const infoCard = detail || preview
  const [activeTab, setActiveTab] = useState<WritingCardTab>('business')
  const businessNode = useMemo(() => buildBusinessNode(preview, detail), [preview, detail])
  const graphExtension = useMemo(() => buildGraphExtension(preview, detail), [preview, detail])
  const handleDragStart = (event: DragEvent<HTMLElement>) => {
    if (!preview) return
    writeDraggedCard(event.nativeEvent, toDraggedCardPayload(preview))
    onDragCardStart?.(preview.card_id)
  }

  return (
    <GraphNodeCard
      title={infoCard?.title || '资料卡详情'}
      subtitle={sourceLabel(preview, detail)}
      style={style}
      draggable={Boolean(preview)}
      onDragStart={handleDragStart}
      onDragEnd={() => onDragCardEnd?.()}
      onClose={onClose}
      onHeadMouseDown={onHeadMouseDown}
      actions={
        <div className="writing-insight-card-actions">
          <div className="gv2-card-tabs" role="tablist" aria-label="卡片标签">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'business'}
              className={`gv2-card-tab ${activeTab === 'business' ? 'is-active' : ''}`.trim()}
              onClick={() => setActiveTab('business')}
              title="业务数据"
            >
              业务数据
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'graph_ext'}
              className={`gv2-card-tab ${activeTab === 'graph_ext' ? 'is-active' : ''}`.trim()}
              onClick={() => setActiveTab('graph_ext')}
              title="图谱扩展"
            >
              图谱扩展
            </button>
          </div>
          <button
            type="button"
            className={`writing-insight-card-action${pinned ? ' is-active' : ''}`}
            onClick={() => onTogglePin?.()}
            title={pinned ? '取消固定' : '固定在画布'}
            aria-pressed={pinned}
          >
            钉
          </button>
          {preview ? (
            <span
              role="button"
              tabIndex={0}
              draggable
              className="writing-insight-card-action writing-insight-card-action--drag"
              title="拖入下方引用带"
              onDragStart={handleDragStart}
              onDragEnd={() => onDragCardEnd?.()}
            >
              拖
            </span>
          ) : null}
          {preview ? (
            <button type="button" className="writing-insight-card-action" onClick={() => onAddCitation?.(preview.card_id)} title="加入引用">
              引
            </button>
          ) : null}
          {infoCard?.url ? (
            <a
              href={infoCard.url}
              target="_blank"
              rel="noreferrer"
              className="writing-insight-card-action writing-insight-card-link"
              title="打开来源"
            >
              源
            </a>
          ) : null}
        </div>
      }
    >
      {loading && !businessNode ? (
        <div className="gv2-node-grid">
          <div className="gv2-node-grid-item">
            <label>状态</label>
            <strong>加载中...</strong>
          </div>
        </div>
      ) : null}
      {businessNode && activeTab === 'business' ? <GraphBusinessCardSections node={businessNode} /> : null}
      {activeTab === 'graph_ext' ? (
        <GraphExtensionsSections
          graphInfo={graphExtension.graphInfo}
          nodeElementGroups={graphExtension.nodeElementGroups}
          relationGroups={graphExtension.relationGroups}
          nodeTypeColor={graphExtension.nodeTypeColor}
        />
      ) : null}
    </GraphNodeCard>
  )
}
