import type { GraphEdgeItem } from '../../../lib/types'
import type { MessageKey } from '../../../app/platform/i18n'

export type EdgeLegendTier = 'domain' | 'class' | 'pred' | 'type'
export const EDGE_STROKE_KINDS = ['straight', 'curved', 'wavy', 'double'] as const
export const EDGE_LINE_TYPES = ['solid', 'dashed', 'dotted', 'longDash', 'dashDot'] as const

export type EdgeLineType = (typeof EDGE_LINE_TYPES)[number]
export type EdgeStrokeKind = (typeof EDGE_STROKE_KINDS)[number]
export type EdgeSymbolName = 'none' | 'arrow' | 'circle' | 'diamond' | 'triangle'

/**
 * The facility spaces the renderer can express: stroke kind × line pattern ×
 * endpoint symbol set. Every cell of that product is a first-class catalog
 * entry, so a project can pick any combination instead of a hand-picked few.
 */
export const EDGE_SYMBOL_SETS = {
  arrow: { symbol: ['none', 'arrow'], symbolSize: [0, 7] },
  circleArrow: { symbol: ['circle', 'arrow'], symbolSize: [4, 7] },
  circles: { symbol: ['circle', 'circle'], symbolSize: [4, 4] },
  circleTriangle: { symbol: ['circle', 'triangle'], symbolSize: [4, 7] },
  triangle: { symbol: ['none', 'triangle'], symbolSize: [0, 8] },
  diamond: { symbol: ['none', 'diamond'], symbolSize: [0, 8] },
  plain: { symbol: ['none', 'none'], symbolSize: [0, 0] },
} as const

export type EdgeSymbolSetName = keyof typeof EDGE_SYMBOL_SETS
export type EdgeSymbolSetOrder = readonly EdgeSymbolSetName[]

/** Curated presets kept for stable project bindings and named semantics. */
export type EdgeStylePresetId =
  | 'solidStraightArrow'
  | 'thinSolidArrow'
  | 'boldSolidArrow'
  | 'dashedStraightArrow'
  | 'dottedStraightCircles'
  | 'dottedStraightCircleTriangle'
  | 'longDashStraightArrow'
  | 'dashDotStraightArrow'
  | 'doubleSolidDiamond'
  | 'doubleDashedDiamond'
  | 'arcUpArrow'
  | 'arcDownTriangle'
  | 'dashedArcCircles'
  | 'wavyDashedCircles'
  | 'wavySolidArrow'
  | 'doubleArcDiamond'

export type EdgeGridStyleId = `${EdgeStrokeKind}-${EdgeLineType}-${EdgeSymbolSetName}`
export type EdgeStyleId = EdgeStylePresetId | EdgeGridStyleId

export type EdgeShapeKind =
  | 'evidenceMembership'
  | 'judgmentFrom'
  | 'judgmentTo'
  | 'clueMembership'
  | 'incidence'
  | 'influence'
  | 'hierarchy'
  | 'flow'
  | 'association'
  | 'temporal'
  | 'directed'

export type GraphEdgeVisualProfile = {
  styleId: EdgeStyleId
  strokeKind: EdgeStrokeKind
  lineType: EdgeLineType
  curveness: number
  symbol: [EdgeSymbolName, EdgeSymbolName]
  symbolSize: [number, number]
  width: number
}

export type GraphEdgeStyleBinding = {
  byRelationToken?: Record<string, EdgeStyleId>
  byRelationClass?: Record<string, EdgeStyleId>
  byPredicate?: Record<string, EdgeStyleId>
  byType?: Record<string, EdgeStyleId>
  default?: EdgeStyleId
}

export const GRAPH_EDGE_STROKE_LABEL_KEY: Record<EdgeStrokeKind, MessageKey> = {
  straight: 'graphPage.edgeStroke.straight',
  curved: 'graphPage.edgeStroke.curved',
  wavy: 'graphPage.edgeStroke.wavy',
  double: 'graphPage.edgeStroke.double',
}

export const GRAPH_EDGE_LINE_TYPE_LABEL_KEY: Record<EdgeLineType, MessageKey> = {
  solid: 'graphPage.edgeLine.solid',
  dashed: 'graphPage.edgeLine.dashed',
  dotted: 'graphPage.edgeLine.dotted',
  longDash: 'graphPage.edgeLine.longDash',
  dashDot: 'graphPage.edgeLine.dashDot',
}

function gridStyleId(kind: EdgeStrokeKind, lineType: EdgeLineType, symbolSet: EdgeSymbolSetName): EdgeGridStyleId {
  return `${kind}-${lineType}-${symbolSet}`
}

/** Curveness stays a declared property of the cell: 直曲 is part of the space. */
function gridCurveness(kind: EdgeStrokeKind, lineIndex: number): number {
  if (kind === 'curved') return lineIndex % 2 === 0 ? 0.2 : -0.18
  if (kind === 'double') return lineIndex % 2 === 0 ? 0 : 0.12
  return 0
}

function gridWidth(kind: EdgeStrokeKind, lineType: EdgeLineType): number {
  const base = kind === 'double' ? 1.6 : kind === 'curved' ? 1.35 : kind === 'wavy' ? 1.3 : 1.2
  return lineType === 'dotted' ? Math.max(1, base - 0.1) : base
}

function buildEdgeStyleGrid(): Record<EdgeGridStyleId, GraphEdgeVisualProfile> {
  const grid = {} as Record<EdgeGridStyleId, GraphEdgeVisualProfile>
  for (const symbolSet of Object.keys(EDGE_SYMBOL_SETS) as EdgeSymbolSetName[]) {
    for (const kind of EDGE_STROKE_KINDS) {
      EDGE_LINE_TYPES.forEach((lineType, lineIndex) => {
        const id = gridStyleId(kind, lineType, symbolSet)
        const symbols = EDGE_SYMBOL_SETS[symbolSet]
        grid[id] = {
          styleId: id,
          strokeKind: kind,
          lineType,
          curveness: gridCurveness(kind, lineIndex),
          symbol: [symbols.symbol[0], symbols.symbol[1]] as [EdgeSymbolName, EdgeSymbolName],
          symbolSize: [symbols.symbolSize[0], symbols.symbolSize[1]] as [number, number],
          width: gridWidth(kind, lineType),
        }
      })
    }
  }
  return grid
}

export const EDGE_STYLE_GRID = buildEdgeStyleGrid()

/**
 * Default assignment for project-declared relation tokens.
 *
 * The walk advances 直曲 and 虚实 together (a diagonal over stroke × line), so
 * consecutive relation types never look alike; endpoint symbols rotate only
 * after every stroke/line cell has been used. A project that declares N relation
 * types therefore gets N distinct defaults in the order it authored them, and
 * overrides any entry through `byRelationToken`.
 */
function buildRelationTokenStyleOrder(): EdgeStyleId[] {
  const order: EdgeStyleId[] = []
  for (const symbolSet of Object.keys(EDGE_SYMBOL_SETS) as EdgeSymbolSetName[]) {
    for (let index = 0; index < EDGE_STROKE_KINDS.length * EDGE_LINE_TYPES.length; index += 1) {
      const kindIndex = index % EDGE_STROKE_KINDS.length
      const lineIndex = (index + kindIndex) % EDGE_LINE_TYPES.length
      order.push(gridStyleId(EDGE_STROKE_KINDS[kindIndex], EDGE_LINE_TYPES[lineIndex], symbolSet))
    }
  }
  return order
}

export const EDGE_RELATION_TOKEN_STYLE_ORDER: readonly EdgeStyleId[] = buildRelationTokenStyleOrder()

export function defaultRelationTokenBinding(
  relationTokens: readonly string[] | undefined,
): GraphEdgeStyleBinding | undefined {
  const tokens = (relationTokens || []).map((token) => normalizeEdgeToken(token)).filter(Boolean)
  if (!tokens.length) return undefined
  const byRelationToken: Record<string, EdgeStyleId> = {}
  tokens.forEach((token, index) => {
    if (byRelationToken[token]) return
    byRelationToken[token] = EDGE_RELATION_TOKEN_STYLE_ORDER[index % EDGE_RELATION_TOKEN_STYLE_ORDER.length]
  })
  return { byRelationToken }
}

/** Compose bindings with later entries winning per axis and per token. */
export function mergeEdgeStyleBindings(
  ...bindings: (GraphEdgeStyleBinding | undefined)[]
): GraphEdgeStyleBinding | undefined {
  const merged: GraphEdgeStyleBinding = {}
  for (const binding of bindings) {
    if (!binding) continue
    if (binding.byRelationToken) merged.byRelationToken = { ...merged.byRelationToken, ...binding.byRelationToken }
    if (binding.byRelationClass) merged.byRelationClass = { ...merged.byRelationClass, ...binding.byRelationClass }
    if (binding.byPredicate) merged.byPredicate = { ...merged.byPredicate, ...binding.byPredicate }
    if (binding.byType) merged.byType = { ...merged.byType, ...binding.byType }
    if (binding.default) merged.default = binding.default
  }
  return Object.keys(merged).length ? merged : undefined
}

const EDGE_STYLE_PRESETS: Record<EdgeStylePresetId, GraphEdgeVisualProfile> = {
  solidStraightArrow: { styleId: 'solidStraightArrow', strokeKind: 'straight', lineType: 'solid', curveness: 0, symbol: ['none', 'arrow'], symbolSize: [0, 7], width: 1.2 },
  thinSolidArrow: { styleId: 'thinSolidArrow', strokeKind: 'straight', lineType: 'solid', curveness: 0, symbol: ['none', 'arrow'], symbolSize: [0, 6], width: 1 },
  boldSolidArrow: { styleId: 'boldSolidArrow', strokeKind: 'straight', lineType: 'solid', curveness: 0, symbol: ['none', 'arrow'], symbolSize: [0, 8], width: 1.55 },
  dashedStraightArrow: { styleId: 'dashedStraightArrow', strokeKind: 'straight', lineType: 'dashed', curveness: 0, symbol: ['none', 'arrow'], symbolSize: [0, 7], width: 1.2 },
  dottedStraightCircles: { styleId: 'dottedStraightCircles', strokeKind: 'straight', lineType: 'dotted', curveness: 0, symbol: ['circle', 'circle'], symbolSize: [4, 4], width: 1.1 },
  dottedStraightCircleTriangle: { styleId: 'dottedStraightCircleTriangle', strokeKind: 'straight', lineType: 'dotted', curveness: 0, symbol: ['circle', 'triangle'], symbolSize: [4, 7], width: 1.1 },
  longDashStraightArrow: { styleId: 'longDashStraightArrow', strokeKind: 'straight', lineType: 'longDash', curveness: 0, symbol: ['none', 'arrow'], symbolSize: [0, 7], width: 1.25 },
  dashDotStraightArrow: { styleId: 'dashDotStraightArrow', strokeKind: 'straight', lineType: 'dashDot', curveness: 0, symbol: ['none', 'arrow'], symbolSize: [0, 7], width: 1.25 },
  doubleSolidDiamond: { styleId: 'doubleSolidDiamond', strokeKind: 'double', lineType: 'solid', curveness: 0, symbol: ['none', 'diamond'], symbolSize: [0, 8], width: 1.65 },
  doubleDashedDiamond: { styleId: 'doubleDashedDiamond', strokeKind: 'double', lineType: 'dashed', curveness: 0, symbol: ['none', 'diamond'], symbolSize: [0, 8], width: 1.55 },
  arcUpArrow: { styleId: 'arcUpArrow', strokeKind: 'curved', lineType: 'solid', curveness: 0.2, symbol: ['circle', 'arrow'], symbolSize: [4, 8], width: 1.35 },
  arcDownTriangle: { styleId: 'arcDownTriangle', strokeKind: 'curved', lineType: 'solid', curveness: -0.18, symbol: ['none', 'triangle'], symbolSize: [0, 8], width: 1.25 },
  dashedArcCircles: { styleId: 'dashedArcCircles', strokeKind: 'curved', lineType: 'dashed', curveness: 0.16, symbol: ['circle', 'circle'], symbolSize: [4, 4], width: 1.15 },
  wavyDashedCircles: { styleId: 'wavyDashedCircles', strokeKind: 'wavy', lineType: 'dashed', curveness: 0, symbol: ['circle', 'circle'], symbolSize: [4, 4], width: 1.15 },
  wavySolidArrow: { styleId: 'wavySolidArrow', strokeKind: 'wavy', lineType: 'solid', curveness: 0, symbol: ['circle', 'arrow'], symbolSize: [4, 7], width: 1.3 },
  doubleArcDiamond: { styleId: 'doubleArcDiamond', strokeKind: 'double', lineType: 'solid', curveness: 0.12, symbol: ['none', 'diamond'], symbolSize: [0, 8], width: 1.55 },
}

/** Curated presets plus every cell of the stroke × line × symbol product. */
export const EDGE_STYLE_CATALOG: Record<EdgeStyleId, GraphEdgeVisualProfile> = {
  ...EDGE_STYLE_PRESETS,
  ...EDGE_STYLE_GRID,
}

const DEFAULT_STYLE_BY_SHAPE: Record<EdgeShapeKind, EdgeStyleId> = {
  evidenceMembership: 'dashedStraightArrow',
  judgmentFrom: 'doubleSolidDiamond',
  judgmentTo: 'doubleSolidDiamond',
  clueMembership: 'dottedStraightCircleTriangle',
  incidence: 'thinSolidArrow',
  influence: 'boldSolidArrow',
  hierarchy: 'doubleSolidDiamond',
  flow: 'arcUpArrow',
  association: 'wavyDashedCircles',
  temporal: 'arcDownTriangle',
  directed: 'solidStraightArrow',
}

export const EDGE_PROFILE_BY_SHAPE = Object.fromEntries(
  Object.entries(DEFAULT_STYLE_BY_SHAPE).map(([shape, styleId]) => [
    shape,
    EDGE_STYLE_CATALOG[styleId],
  ]),
) as Record<EdgeShapeKind, GraphEdgeVisualProfile>

function normalizeEdgeToken(value: unknown) {
  return String(value || '').trim().toLowerCase()
}

function edgeSemanticTokens(edge: GraphEdgeItem) {
  return [
    normalizeEdgeToken(edge.relation_class),
    normalizeEdgeToken(edge.predicate),
    normalizeEdgeToken(edge.type),
  ].filter(Boolean)
}

function matchEdgeToken(tokens: string[], patterns: string[]) {
  return tokens.some((token) => patterns.some((pattern) => token.includes(pattern)))
}

export function edgeShapeKind(edge: GraphEdgeItem): EdgeShapeKind {
  const relationClass = normalizeEdgeToken(edge.relation_class)
  const predicate = normalizeEdgeToken(edge.predicate)
  const type = normalizeEdgeToken(edge.type)

  if (relationClass === 'judgment') return predicate === 'from' ? 'judgmentFrom' : 'judgmentTo'
  if (relationClass === 'evidence') return 'evidenceMembership'
  if (relationClass === 'clue' || relationClass === 'attempt' || relationClass === 'material') return 'clueMembership'
  if (type === 'topology_incidence' || relationClass.includes(':')) return 'incidence'

  const tokens = edgeSemanticTokens(edge)
  if (matchEdgeToken(tokens, ['taxonomy', 'category', 'classify', 'compose', 'composition', 'part', 'belong', 'include'])) return 'hierarchy'
  if (matchEdgeToken(tokens, ['supply', 'distribution', 'channel', 'pipeline', 'flow', 'route'])) return 'flow'
  if (matchEdgeToken(tokens, ['impact', 'influ', 'cause', 'drive', 'effect', 'lift', 'drop'])) return 'influence'
  if (matchEdgeToken(tokens, ['competition', 'collab', 'partner', 'depend', 'relation', 'associate', 'peer'])) return 'association'
  if (matchEdgeToken(tokens, ['event', 'period', 'time', 'timeline', 'phase', 'season', 'date'])) return 'temporal'
  return 'directed'
}

function validStyleId(value: unknown): EdgeStyleId | undefined {
  const id = String(value || '').trim()
  return id in EDGE_STYLE_CATALOG ? id as EdgeStyleId : undefined
}

function validStyleMap(value: unknown): Record<string, EdgeStyleId> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const output: Record<string, EdgeStyleId> = {}
  for (const [key, rawStyle] of Object.entries(value as Record<string, unknown>)) {
    const styleId = validStyleId(rawStyle)
    if (styleId) output[normalizeEdgeToken(key)] = styleId
  }
  return Object.keys(output).length ? output : undefined
}

export function coerceGraphEdgeStyleBinding(value: unknown): GraphEdgeStyleBinding | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const raw = value as Record<string, unknown>
  const binding: GraphEdgeStyleBinding = {}
  const byRelationToken = validStyleMap(raw.byRelationToken)
  const byRelationClass = validStyleMap(raw.byRelationClass)
  const byPredicate = validStyleMap(raw.byPredicate)
  const byType = validStyleMap(raw.byType)
  const defaultStyle = validStyleId(raw.default)
  if (byRelationToken) binding.byRelationToken = byRelationToken
  if (byRelationClass) binding.byRelationClass = byRelationClass
  if (byPredicate) binding.byPredicate = byPredicate
  if (byType) binding.byType = byType
  if (defaultStyle) binding.default = defaultStyle
  return Object.keys(binding).length ? binding : undefined
}

export function edgeStyleId(edge: GraphEdgeItem, binding?: GraphEdgeStyleBinding): EdgeStyleId {
  const explicit = validStyleId(edge.style_id)
  if (explicit) return explicit

  const relationClass = normalizeEdgeToken(edge.relation_class)
  const relationToken = normalizeEdgeToken(edge.relation_token)
  const predicate = normalizeEdgeToken(edge.predicate)
  const type = normalizeEdgeToken(edge.type)
  return binding?.byRelationToken?.[relationToken]
    || binding?.byRelationClass?.[relationClass]
    || binding?.byPredicate?.[predicate]
    || binding?.byType?.[type]
    || binding?.default
    || DEFAULT_STYLE_BY_SHAPE[edgeShapeKind(edge)]
}

export function graphEdgeProfile(edge: GraphEdgeItem, binding?: GraphEdgeStyleBinding): GraphEdgeVisualProfile {
  return EDGE_STYLE_CATALOG[edgeStyleId(edge, binding)]
}

export function edgeLinePattern(lineType: EdgeLineType): string | number[] {
  if (lineType === 'dashed') return 'dashed'
  if (lineType === 'dotted') return 'dotted'
  if (lineType === 'longDash') return [12, 5]
  if (lineType === 'dashDot') return [8, 3, 2, 3]
  return 'solid'
}

export type EdgeLegendItem = {
  key: string
  tier: EdgeLegendTier
  shapeKind: EdgeShapeKind
  styleId: EdgeStyleId
  strokeKind: EdgeStrokeKind
  lineType: EdgeLineType
  label: string
  count: number
  color: string
}

export function edgeLegendTier(edge: GraphEdgeItem): EdgeLegendTier {
  if (normalizeEdgeToken(edge.relation_token)) return 'domain'
  if (normalizeEdgeToken(edge.relation_class)) return 'class'
  if (normalizeEdgeToken(edge.predicate)) return 'pred'
  return 'type'
}

function edgeLegendRawValue(edge: GraphEdgeItem): string {
  const tier = edgeLegendTier(edge)
  if (tier === 'domain') return normalizeEdgeToken(edge.relation_token)
  if (tier === 'class') return normalizeEdgeToken(edge.relation_class)
  if (tier === 'pred') return normalizeEdgeToken(edge.predicate)
  return String(edge.type || '').trim().toUpperCase() || 'REL'
}

export function edgeLegendKey(edge: GraphEdgeItem): string {
  return `${edgeLegendTier(edge)}:${edgeLegendRawValue(edge)}`
}

export function edgeLegendRaw(edge: GraphEdgeItem): string {
  return edgeLegendRawValue(edge)
}

export function relationLabel(token: string, labels?: Record<string, string>) {
  const raw = String(token || '').trim()
  if (!raw) return '-'
  const variants = [raw, raw.toUpperCase(), raw.toLowerCase()]
  for (const key of variants) {
    if (labels?.[key]) return labels[key]
  }
  return raw
}

export function edgeLegendLabel(
  edge: GraphEdgeItem,
  labels: Record<string, string> | undefined,
  relationClassLabel: (token: string) => string,
) {
  if (edgeLegendTier(edge) === 'domain') return relationLabel(edgeLegendRawValue(edge), labels)
  if (edgeLegendTier(edge) === 'class') return relationClassLabel(edgeLegendRawValue(edge))
  return relationLabel(edgeLegendRawValue(edge), labels)
}
