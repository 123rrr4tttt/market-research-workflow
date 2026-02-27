import { GRAPH_SHAPES } from '../../lib/graph-kit'
import GraphShapeBadge from './GraphShapeBadge'

export default function GraphLegend() {
  return (
    <section className="gk-panel">
      <div className="gk-panel-head"><h3>Shape Legend</h3></div>
      <div className="gk-legend-grid">
        {GRAPH_SHAPES.map((item) => (
          <div key={item.key} className="gk-legend-item">
            <GraphShapeBadge shape={item.key} />
            <span>{item.label}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
