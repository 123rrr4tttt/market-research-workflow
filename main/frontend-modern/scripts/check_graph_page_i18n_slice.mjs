#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/GraphPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'graphPage.variant.graphMarket',
  'graphPage.variant.graphPolicy',
  'graphPage.variant.graphSocial',
  'graphPage.variant.graphCompany',
  'graphPage.variant.graphProduct',
  'graphPage.variant.graphOperation',
  'graphPage.variant.graphDeep',
  'graphPage.group.company',
  'graphPage.group.product',
  'graphPage.group.operation',
  'graphPage.group.policy',
  'graphPage.group.social',
  'graphPage.group.market',
  'graphPage.group.other',
  'graphPage.edgeTier.class',
  'graphPage.edgeTier.pred',
  'graphPage.edgeTier.type',
  'graphPage.edgeStroke.straight',
  'graphPage.edgeStroke.curved',
  'graphPage.edgeStroke.wavy',
  'graphPage.edgeStroke.double',
  'graphPage.relationClass.governance',
  'graphPage.relationClass.event',
  'graphPage.relationClass.metric',
  'graphPage.relationClass.impact',
  'graphPage.relationClass.collaboration',
  'graphPage.relationClass.dependency',
  'graphPage.relationClass.supplyChain',
  'graphPage.relationClass.distribution',
  'graphPage.relationClass.competition',
  'graphPage.relationClass.operation',
  'graphPage.relationClass.taxonomy',
  'graphPage.relationClass.targeting',
  'graphPage.relationClass.channel',
  'graphPage.relationClass.strategy',
  'graphPage.relationClass.composition',
  'graphPage.relationClass.other',
  'graphPage.field.type',
  'graphPage.field.id',
  'graphPage.field.title',
  'graphPage.field.name',
  'graphPage.field.state',
  'graphPage.field.platform',
  'graphPage.field.game',
  'graphPage.field.policyType',
  'graphPage.field.status',
  'graphPage.field.date',
  'graphPage.tooltip.relation',
  'graphPage.tooltip.class',
  'graphPage.tooltip.predicate',
  'graphPage.tooltip.stroke',
  'graphPage.legend.edge',
  'graphPage.legend.symbolDebug',
  'graphPage.legend.visibleNodes',
  'graphPage.legend.typeMappings',
  'graphPage.legend.fallbackCircle',
  'graphPage.macro.graph',
  'graphPage.macro.totalNodes',
  'graphPage.macro.totalEdges',
  'graphPage.macro.nodeTypes',
  'graphPage.macro.selectedNodes',
  'graphPage.macro.visibleNow',
  'graphPage.action.close',
  'graphPage.error.renderFailed',
  'graphPage.clueChain.defaultTitle',
]

const retiredPageSnippets = [
  "graphMarket: '市场图谱'",
  "graphPolicy: '政策图谱'",
  "graphSocial: '社媒图谱'",
  "graphCompany: '公司图谱'",
  "graphProduct: '商品图谱'",
  "graphOperation: '电商/经营图谱'",
  "graphDeep: '市场实体加细图'",
  "company: '公司'",
  "product: '商品'",
  "operation: '运营'",
  "class: '关系大类'",
  "pred: '关系谓词'",
  "type: '边类型'",
  "straight: '直线'",
  "curved: '曲线'",
  "wavy: '波浪线'",
  "double: '双线'",
  "governance: '治理/监管'",
  "event: '事件发布'",
  "metric: '指标披露'",
  "impact: '影响变化'",
  "collaboration: '合作关系'",
  "dependency: '依赖关系'",
  "supply_chain: '供应链'",
  "distribution: '分销渠道'",
  "competition: '竞争关系'",
  "taxonomy: '分类归属'",
  "targeting: '场景指向'",
  "channel: '渠道目标'",
  "strategy: '经营策略'",
  "composition: '组成关系'",
  "other: '其他关系'",
  "this.props.onError(error.message || '渲染失败')",
  "['类型', String(node.type || '-')]",
  "['标题', String(node.title || '')]",
  "['名称', String(node.name || node.canonical_name || '')]",
  "['政策类型', String(node.policy_type || '')]",
  'TYPE_LABEL[variant]',
  'GROUP_LABEL[group]',
  'EDGE_TIER_LABEL[tier]',
  'EDGE_STROKE_LABEL[strokeKind]',
  'RELATION_CLASS_LABEL[classToken]',
  '<span>图谱</span>',
  '<span>节点总数</span>',
  '<span>边总数</span>',
  '<span>节点类型</span>',
  '<span>已选节点</span>',
  '<span>当前可见</span>',
]

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function catalogNamespaceBlocks(source, namespace) {
  const blocks = []
  const pattern = new RegExp(`${escapeRegExp(namespace)}:\\s*\\{([\\s\\S]*?)\\n\\s*\\}`, 'g')
  let match = pattern.exec(source)
  while (match) {
    blocks.push(match[1])
    match = pattern.exec(source)
  }
  return blocks
}

const pageSource = readFile(files.page)
const catalogSource = readFile(files.catalog)
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'graphPage')
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('graphPage namespace must exist in shape, zh-CN, and en-US')
}

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`GraphPage does not use ${key}`)
  }

  const shortKey = key.replace(/^graphPage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`graphPage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired GraphPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('GraphPage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'")) {
  failures.push('GraphPage must use the shared i18n entrypoint')
}
if (!pageSource.includes('GRAPH_VARIANT_LABEL_KEY')) {
  failures.push('GraphPage must route variant labels through catalog keys')
}
if (!pageSource.includes('graphGroupLabel(')) {
  failures.push('GraphPage must route legend group labels through catalog keys')
}
if (!pageSource.includes('edgeTierLabel(') || !pageSource.includes('edgeStrokeLabel(')) {
  failures.push('GraphPage must route edge legend labels through catalog keys')
}
if (!pageSource.includes('relationClassLabel(')) {
  failures.push('GraphPage must route relation class labels through catalog keys')
}
if (!catalogSource.includes('graphPage: {')) {
  failures.push('catalog must expose a graphPage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'graph_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'graphPage',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
