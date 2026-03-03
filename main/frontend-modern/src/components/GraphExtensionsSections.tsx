import { useMemo, useState, type CSSProperties } from 'react'

type NeighborNodeItem = { id: string; name: string; type: string }
type PredicateRelationItem = { id: string; direction: 'IN' | 'OUT'; targetName: string; targetType: string }
type RelationItem = { id: string; direction: 'IN' | 'OUT'; relation: string; targetName: string; targetType: string }

export type GraphInfoSections = {
  degree: number
  neighborTypeCount: number
  marketDocCount: number
  neighborTypeItems: Array<{ type: string; count: number }>
  predicateItems: Array<{ predicate: string; count: number }>
  neighborNodesByType: Record<string, NeighborNodeItem[]>
  relationsByPredicate: Record<string, PredicateRelationItem[]>
}

export type GraphElementGroup = {
  label: string
  items: Array<{ id: string; value: string; label?: string }>
}

export type GraphRelationGroup = {
  relation: string
  items: RelationItem[]
}

type Props = {
  graphInfo?: GraphInfoSections | null
  nodeElementGroups?: GraphElementGroup[]
  relationGroups?: GraphRelationGroup[]
  nodeTypeColor?: Record<string, string>
  chipColorForIndex?: (index: number) => string
  elementColorForLabel?: (label: string) => string
}

function defaultChipColor(index: number) {
  const hue = Math.round((index * 137.508) % 360)
  return `hsl(${hue} 78% 62%)`
}

export default function GraphExtensionsSections({
  graphInfo,
  nodeElementGroups = [],
  relationGroups = [],
  nodeTypeColor = {},
  chipColorForIndex = defaultChipColor,
  elementColorForLabel,
}: Props) {
  const [expandedNeighborType, setExpandedNeighborType] = useState<string | null>(null)
  const [expandedPredicate, setExpandedPredicate] = useState<string | null>(null)
  const [expandedElementLabel, setExpandedElementLabel] = useState<string | null>(null)
  const [relationGroupOpen, setRelationGroupOpen] = useState<Record<string, boolean>>({})

  const relationGroupOpenResolved = useMemo(() => {
    if (!relationGroups.length) return relationGroupOpen
    if (Object.keys(relationGroupOpen).length) return relationGroupOpen
    return { [relationGroups[0].relation]: true }
  }, [relationGroups, relationGroupOpen])
  const allRelationGroupsOpen = relationGroups.length > 0 && relationGroups.every((group) => relationGroupOpenResolved[group.relation])

  return (
    <>
      {graphInfo ? (
        <div className="gv2-node-context">
          <strong>图谱信息</strong>
          <div className="gv2-node-grid">
            <div className="gv2-node-grid-item">
              <label>连接数（Degree）</label>
              <strong>{graphInfo.degree}</strong>
            </div>
            <div className="gv2-node-grid-item">
              <label>关联类型数</label>
              <strong>{graphInfo.neighborTypeCount}</strong>
            </div>
            <div className="gv2-node-grid-item">
              <label>关联文档数</label>
              <strong>{graphInfo.marketDocCount}</strong>
            </div>
          </div>
          {graphInfo.neighborTypeItems.length ? (
            <div className="gv2-node-tags">
              {graphInfo.neighborTypeItems.map((item, index) => (
                <button
                  key={item.type}
                  type="button"
                  className={`gv2-node-chip ${expandedNeighborType === item.type ? 'is-active' : ''}`}
                  style={{ '--chip-color': chipColorForIndex(index) } as CSSProperties}
                  onClick={() => setExpandedNeighborType((prev) => (prev === item.type ? null : item.type))}
                >
                  {item.type}: {item.count}
                </button>
              ))}
            </div>
          ) : null}
          {expandedNeighborType && graphInfo.neighborNodesByType[expandedNeighborType]?.length ? (
            <div className="gv2-node-expand-list">
              {graphInfo.neighborNodesByType[expandedNeighborType].map((item) => (
                <span key={`${item.type}-${item.id}`}>
                  <i style={{ background: nodeTypeColor[item.type] || '#7dd3fc' }} />
                  {item.name}
                </span>
              ))}
            </div>
          ) : null}
          {graphInfo.predicateItems.length ? (
            <div className="gv2-node-tags">
              {graphInfo.predicateItems.map((item, index) => {
                const color = chipColorForIndex(index)
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
          {expandedPredicate && graphInfo.relationsByPredicate[expandedPredicate]?.length ? (
            <div className="gv2-node-expand-list">
              {graphInfo.relationsByPredicate[expandedPredicate].map((item) => (
                <span key={item.id}>
                  <i style={{ background: nodeTypeColor[item.targetType] || '#7dd3fc' }} />
                  {item.direction === 'OUT' ? '出' : '入'} · {item.targetName}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {nodeElementGroups.length ? (
        <div className="gv2-node-context">
          <strong>节点元素</strong>
          <div className="gv2-node-tags">
            {nodeElementGroups.map((group, index) => {
              const color = chipColorForIndex(index)
              return (
                <button
                  key={group.label}
                  type="button"
                  className={`gv2-node-chip gv2-node-chip--element ${expandedElementLabel === group.label ? 'is-active' : ''}`}
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
                <span
                  key={item.id}
                  className="gv2-node-expand-item gv2-node-expand-item--element"
                  style={{ '--item-color': elementColorForLabel?.(item.label || expandedElementLabel) || '#7dd3fc' } as CSSProperties}
                >
                  <i style={{ background: elementColorForLabel?.(item.label || expandedElementLabel) || '#7dd3fc' }} />
                  {item.value}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {relationGroups.length ? (
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
    </>
  )
}
