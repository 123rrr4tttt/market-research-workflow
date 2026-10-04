import type { MessageKey } from '../../../app/platform/i18n'

export type GraphLegendGroupId =
  | 'company'
  | 'product'
  | 'operation'
  | 'policy'
  | 'social'
  | 'market'
  | 'method'
  | 'field'
  | 'organization'
  | 'entity'
  | 'activity'
  | 'reflection'
  | 'evidence'
  | 'semantic'
  | 'topology'
  | 'other'

const LEGEND_GROUP_BY_TYPE: Record<string, GraphLegendGroupId> = {
  // Project-bound semantic topology vocabulary.
  'node:现场': 'field',
  'node:行动者': 'organization',
  'node:制度安排': 'organization',
  'node:社会关系': 'organization',
  'node:阶级机体': 'organization',
  'node:技术物': 'entity',
  'node:货币流': 'entity',
  'node:剩余': 'entity',
  'node:环节': 'activity',
  'node:生活实践': 'activity',
  'node:意识形式': 'reflection',
  judgment: 'reflection',
  evidence: 'evidence',
  material: 'evidence',
  attempt: 'activity',
  clue: 'method',
  domain_vocabulary: 'method',
}

export const GRAPH_LEGEND_GROUP_LABEL_KEY: Record<GraphLegendGroupId, MessageKey> = {
  company: 'graphPage.group.company',
  product: 'graphPage.group.product',
  operation: 'graphPage.group.operation',
  policy: 'graphPage.group.policy',
  social: 'graphPage.group.social',
  market: 'graphPage.group.market',
  method: 'graphPage.group.method',
  field: 'graphPage.group.field',
  organization: 'graphPage.group.organization',
  entity: 'graphPage.group.entity',
  activity: 'graphPage.group.activity',
  reflection: 'graphPage.group.reflection',
  evidence: 'graphPage.group.evidence',
  semantic: 'graphPage.group.semantic',
  topology: 'graphPage.group.topology',
  other: 'graphPage.group.other',
}

const GROUP_ORDER: Record<GraphLegendGroupId, number> = {
  method: 0,
  field: 1,
  organization: 2,
  entity: 3,
  activity: 4,
  reflection: 5,
  evidence: 6,
  semantic: 7,
  topology: 8,
  company: 9,
  product: 10,
  operation: 11,
  policy: 12,
  social: 13,
  market: 14,
  other: 15,
}

export function compareGraphLegendGroups(left: GraphLegendGroupId, right: GraphLegendGroupId): number {
  return GROUP_ORDER[left] - GROUP_ORDER[right]
}

export function classifyGraphLegendType(type: string): GraphLegendGroupId {
  const explicit = LEGEND_GROUP_BY_TYPE[type]
  if (explicit) return explicit
  if (type.startsWith('Company')) return 'company'
  if (type.startsWith('Product')) return 'product'
  if (type.startsWith('Operation')) return 'operation'
  if (['Policy', 'PolicyType', 'KeyPoint', 'State'].includes(type)) return 'policy'
  if (['Post', 'Keyword', 'Topic', 'SentimentTag', 'User', 'Subreddit'].includes(type)) return 'social'
  if (['MarketData', 'Segment', 'Game', 'Entity', 'TopicTag'].includes(type)) return 'market'
  if (type.startsWith('node:')) return 'semantic'
  if (type.includes(':')) return 'topology'
  return 'other'
}
