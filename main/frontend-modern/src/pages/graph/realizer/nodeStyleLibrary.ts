export type BuiltinGraphSymbol = 'circle' | 'rect' | 'roundRect' | 'triangle' | 'diamond' | 'pin' | 'arrow'

export const SYMBOLS: Record<string, string> = {
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
  TopicTag: 'convexStar',
  'node:现场': 'pin',
  'node:行动者': 'roundRect',
  'node:制度安排': 'rect',
  'node:社会关系': 'emptyRect',
  'node:阶级机体': 'diamond',
  'node:技术物': 'triangle',
  'node:货币流': 'emptyTriangle',
  'node:剩余': 'circle',
  'node:环节': 'arrow',
  'node:生活实践': 'emptyPin',
  'node:意识形式': 'emptyDiamond',
  judgment: 'diamond',
  evidence: 'circle',
  material: 'emptyCircle',
  attempt: 'arrow',
  clue: 'convexStar',
  domain_vocabulary: 'convexStar',
}

export const TOPIC_TAG_CONVEX_SYMBOL_PATH = 'path://M10 2.2 L12.6 6.6 L17.6 7.8 L14.2 11.4 L15 16.6 L10 14.4 L5 16.6 L5.8 11.4 L2.4 7.8 L7.4 6.6 Z'

const SYMBOL_SIZE_GAIN: Record<string, number> = {
  circle: 1.0,
  rect: 0.92,
  roundRect: 0.92,
  diamond: 1.05,
  triangle: 1.12,
  pin: 1.12,
  arrow: 1.18,
  emptyCircle: 1.0,
  emptyRect: 0.92,
  emptyRoundRect: 0.92,
  emptyDiamond: 1.05,
  emptyTriangle: 1.12,
  emptyPin: 1.12,
  convexStar: 0.9,
}

const SYMBOL_TYPE_BY_COMPACT: Record<string, string> = Object.fromEntries(
  Object.keys(SYMBOLS).map((key) => [key.toLowerCase().replace(/[\s_-]+/g, ''), key]),
)

export function normalizeNodeType(rawType: unknown) {
  const raw = String(rawType || '').trim()
  if (!raw) return raw
  const compact = raw.toLowerCase().replace(/[\s_-]+/g, '')
  const aliasMap: Record<string, string> = {
    productsenario: 'ProductScenario',
    prodctscenario: 'ProductScenario',
    prodctsenario: 'ProductScenario',
    proudctscenario: 'ProductScenario',
    proudctsenario: 'ProductScenario',
    productcomponent: 'ProductComponent',
    prodctcomponent: 'ProductComponent',
    productmodel: 'ProductModel',
    prodctmodel: 'ProductModel',
    productentity: 'ProductEntity',
    prodctentity: 'ProductEntity',
    productcategory: 'ProductCategory',
    prodctcategory: 'ProductCategory',
    productbrand: 'ProductBrand',
    prodctbrand: 'ProductBrand',
    product: 'ProductEntity',
    prodct: 'ProductEntity',
    proudct: 'ProductEntity',
  }
  return aliasMap[compact] || SYMBOL_TYPE_BY_COMPACT[compact] || raw
}

export function resolveNodeSymbol(rawType: string) {
  const normalized = normalizeNodeType(rawType)
  return String(SYMBOLS[normalized] || SYMBOLS[rawType] || 'circle')
}

export function toGraphSymbol(symbol: string): BuiltinGraphSymbol {
  const key = String(symbol || '').trim()
  if (key === 'emptyCircle') return 'circle'
  if (key === 'emptyRect') return 'rect'
  if (key === 'emptyRoundRect') return 'roundRect'
  if (key === 'emptyDiamond') return 'diamond'
  if (key === 'emptyTriangle') return 'triangle'
  if (key === 'emptyPin') return 'pin'
  if (key === 'rect' || key === 'roundRect' || key === 'triangle' || key === 'diamond' || key === 'pin' || key === 'arrow') return key
  return 'circle'
}

export function symbolSizeGain(symbol: string) {
  return SYMBOL_SIZE_GAIN[String(symbol || '').trim()] || 1
}

export function computeEmptyNodeBorderWidth(size: number, selected: boolean) {
  const base = Math.max(1.35, Math.min(4.8, size * 0.16 + 0.55))
  return selected ? Math.max(1.5, base * 1.18) : base
}
