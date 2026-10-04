export const TOPOLOGY_DISPLAY_SCHEMA_VERSION = 'hk-water.content-display.v1'

export type TopologyDisplayRule = {
  /** Ordered content-name fields. Identity and administrative fields are excluded. */
  contentFields: readonly string[]
  /** Stable fallback when content fields are absent; never exposes a long identity. */
  fallbackLabel: string
}

const GENERIC_RULES: Record<string, TopologyDisplayRule> = {
  judgment: { contentFields: ['judgment'], fallbackLabel: '未命名判断' },
  evidence: { contentFields: ['name', 'original_excerpt'], fallbackLabel: '未命名证据' },
  clue: { contentFields: ['name'], fallbackLabel: '未命名线索' },
  material: { contentFields: ['title'], fallbackLabel: '未命名材料' },
  document: { contentFields: ['title'], fallbackLabel: '未命名文档' },
  attempt: { contentFields: ['result_note', 'actual_query'], fallbackLabel: '未命名检索尝试' },
  domain_vocabulary: { contentFields: ['name'], fallbackLabel: '未命名域词表' },
  source_route: { contentFields: ['entry'], fallbackLabel: '未命名来源路线' },
  keyword_plan: { contentFields: ['expression'], fallbackLabel: '未命名关键词计划' },
  source_registry: { contentFields: [], fallbackLabel: '未命名来源记录' },
  candidate: { contentFields: ['source_note'], fallbackLabel: '未命名候选' },
  gap: { contentFields: ['description'], fallbackLabel: '未命名缺口' },
  logical_dependency: { contentFields: [], fallbackLabel: '逻辑依赖' },
  report_source_binding: { contentFields: ['summary'], fallbackLabel: '未命名报告来源绑定' },
}

const NODE_DISPLAY_RULE: TopologyDisplayRule = {
  contentFields: ['name'],
  fallbackLabel: '未命名语义节点',
}

export function topologyDisplayRule(typeId: string): TopologyDisplayRule {
  return typeId.startsWith('node:') ? NODE_DISPLAY_RULE : GENERIC_RULES[typeId] || {
    contentFields: ['name', 'title', 'description'],
    fallbackLabel: '未命名拓扑元素',
  }
}

const COMMON_CONTENT_FIELDS: readonly string[] = ['content_name', 'content_summary']

function textValue(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized || undefined
}

export function topologyDisplayName(
  typeId: string,
  attributes: Record<string, unknown> = {},
): string {
  if (typeId === 'material' && attributes.reference_status === 'unresolved_reference') {
    return '未解析材料引用'
  }
  const rule = topologyDisplayRule(typeId)
  const contentName = [...COMMON_CONTENT_FIELDS, ...rule.contentFields]
    .map((field) => textValue(attributes[field]))
    .find(Boolean)
  return contentName || rule.fallbackLabel
}
