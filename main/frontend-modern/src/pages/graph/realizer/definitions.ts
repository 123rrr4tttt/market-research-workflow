import type { GraphProjectionDefinition } from './contract'

/**
 * The existing graph pages are projections over one realizer. Domain-specific
 * variation belongs here; layout, interaction, selection and rendering stay in
 * GraphPage/GraphWorkspace.
 */
export const GRAPH_PROJECTIONS = {
  graphMarket: {
    id: 'market', graphKind: 'market', dataSourceKind: 'market_deep_entities', viewGroup: 'market', viewOrder: 0, marketView: 'market_deep_entities', labelKey: 'graphPage.variant.graphMarket', configKey: 'market',
    nodeTypes: ['MarketData', 'State', 'Segment', 'Entity'],
  },
  graphPolicy: {
    id: 'policy', graphKind: 'policy', dataSourceKind: 'policy', labelKey: 'graphPage.variant.graphPolicy', configKey: 'policy',
    nodeTypes: ['Policy', 'State', 'PolicyType', 'KeyPoint', 'Entity'],
  },
  graphSocial: {
    id: 'social', graphKind: 'social', dataSourceKind: 'social', labelKey: 'graphPage.variant.graphSocial', configKey: 'social',
    nodeTypes: ['Post', 'Keyword', 'Entity', 'Topic', 'SentimentTag', 'User', 'Subreddit'],
  },
  graphCompany: {
    id: 'company', graphKind: 'company', dataSourceKind: 'market_deep_entities', viewGroup: 'market', viewOrder: 2, labelKey: 'graphPage.variant.graphCompany', configKey: 'market',
    nodeTypes: ['MarketData', 'CompanyEntity', 'CompanyBrand', 'CompanyUnit', 'CompanyPartner', 'CompanyChannel', 'TopicTag'],
    specialNodePrefix: 'Company', marketView: 'market_deep_entities', topicScope: 'company',
  },
  graphProduct: {
    id: 'product', graphKind: 'product', dataSourceKind: 'market_deep_entities', viewGroup: 'market', viewOrder: 3, labelKey: 'graphPage.variant.graphProduct', configKey: 'market',
    nodeTypes: ['MarketData', 'ProductEntity', 'ProductModel', 'ProductCategory', 'ProductBrand', 'ProductComponent', 'ProductScenario', 'TopicTag'],
    specialNodePrefix: 'Product', marketView: 'market_deep_entities', topicScope: 'product',
  },
  graphOperation: {
    id: 'operation', graphKind: 'operation', dataSourceKind: 'market_deep_entities', viewGroup: 'market', viewOrder: 4, labelKey: 'graphPage.variant.graphOperation', configKey: 'market',
    nodeTypes: ['MarketData', 'OperationEntity', 'OperationPlatform', 'OperationStore', 'OperationChannel', 'OperationMetric', 'OperationStrategy', 'OperationRegion', 'OperationPeriod', 'TopicTag'],
    specialNodePrefix: 'Operation', marketView: 'market_deep_entities', topicScope: 'operation',
  },
  graphDeep: {
    id: 'market_deep_entities', graphKind: 'market_deep_entities', dataSourceKind: 'market_deep_entities', viewGroup: 'market', viewOrder: 1, labelKey: 'graphPage.variant.graphDeep', configKey: 'market',
    nodeTypes: ['MarketData', 'State', 'Segment', 'Entity', 'CompanyEntity', 'CompanyBrand', 'CompanyUnit', 'CompanyPartner', 'CompanyChannel', 'ProductEntity', 'ProductModel', 'ProductCategory', 'ProductBrand', 'ProductComponent', 'ProductScenario', 'OperationEntity', 'OperationPlatform', 'OperationStore', 'OperationChannel', 'OperationMetric', 'OperationStrategy', 'OperationRegion', 'OperationPeriod', 'TopicTag'],
    marketView: 'market_deep_entities',
  },
} satisfies Record<string, GraphProjectionDefinition>

export type GraphProjectionId = keyof typeof GRAPH_PROJECTIONS
export type GraphKind = GraphProjectionDefinition['graphKind']

export const GRAPH_PROJECTIONS_BY_KIND: Record<GraphKind, GraphProjectionDefinition> = {
  market: GRAPH_PROJECTIONS.graphMarket,
  policy: GRAPH_PROJECTIONS.graphPolicy,
  social: GRAPH_PROJECTIONS.graphSocial,
  company: GRAPH_PROJECTIONS.graphCompany,
  product: GRAPH_PROJECTIONS.graphProduct,
  operation: GRAPH_PROJECTIONS.graphOperation,
  market_deep_entities: GRAPH_PROJECTIONS.graphDeep,
}

export function getGraphProjection(id: GraphProjectionId): GraphProjectionDefinition {
  return GRAPH_PROJECTIONS[id]
}

export function getGraphProjectionTabs(id: GraphProjectionId): Array<{ id: GraphProjectionId; definition: GraphProjectionDefinition }> {
  const selected = getGraphProjection(id)
  if (!selected.viewGroup) return []
  return (Object.entries(GRAPH_PROJECTIONS) as Array<[GraphProjectionId, GraphProjectionDefinition]>)
    .filter(([, definition]) => definition.viewGroup === selected.viewGroup)
    .sort(([, left], [, right]) => (left.viewOrder ?? 0) - (right.viewOrder ?? 0))
    .map(([projectionId, definition]) => ({ id: projectionId, definition }))
}
