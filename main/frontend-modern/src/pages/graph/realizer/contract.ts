import type { MessageKey } from '../../../app/platform/i18n'
import type { GraphEdgeItem, GraphNodeItem } from '../../../lib/types'

/**
 * Canonical read-only graph shape. A graph is a directed multigraph so parallel
 * relations keep their own identity instead of being collapsed into a pair.
 */
export type GraphTopology<N = GraphNodeItem, E = GraphEdgeItem> = {
  nodes: N[]
  edges: E[]
  source: (edge: E) => GraphNodeItem['id']
  target: (edge: E) => GraphNodeItem['id']
}

/** Project-owned declaration consumed by the shared graph realizer. */
export type GraphProjectionDefinition = {
  /** Stable identity of this view, independent of its translated label. */
  id: string
  /** Backend/read adapter scope; not a renderer identity. */
  graphKind: 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'
  /** Canonical total-graph source; multiple views may share one source. */
  dataSourceKind: 'policy' | 'social' | 'market' | 'market_deep_entities' | 'company' | 'product' | 'operation'
  /** Views in the same group are tabs over one canonical source graph. */
  viewGroup?: string
  viewOrder?: number
  labelKey: MessageKey
  /** Configuration namespace and default node vocabulary for this projection. */
  configKey: 'policy' | 'social' | 'market'
  nodeTypes: readonly string[]
  /** Optional connected-component seed selector, expressed in domain type vocabulary. */
  specialNodePrefix?: string
  /** Market endpoint projection parameters. */
  marketView?: 'market_deep_entities'
  topicScope?: 'company' | 'product' | 'operation'
}

/**
 * A graph morphism maps nodes and relations while preserving relation endpoints.
 * The realizer may decorate mapped elements, but it cannot change incidence.
 */
export type GraphRealizerInput = {
  definition: GraphProjectionDefinition
  topology: GraphTopology
}
