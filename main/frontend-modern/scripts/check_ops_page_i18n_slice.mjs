#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/OpsPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
  businessStringAudit: 'scripts/check_frontend_business_string_audit.mjs',
}

const requiredAnchorKeys = [
  'opsPage.title.ops',
  'opsPage.title.backend',
  'opsPage.section.agentSessions',
  'opsPage.section.governanceActions',
  'opsPage.section.documentGovernance',
  'opsPage.actionName.graphExport',
  'opsPage.status.running',
  'opsPage.status.graphExportCompleted',
  'opsPage.empty.documents',
  'opsPage.tab.graphExtension',
]

const retiredPageSnippets = [
  "toLocaleString('zh-CN')",
  "useState('就绪')",
  "error.message : '未知错误'",
  "Review the current agent-session state and outstanding approvals.",
  "variant === 'backend' ? '后端监控视图' : '数据运维视图'",
  '<span>文档</span>',
  '<span>社媒文档</span>',
  '<span>来源数</span>',
  '<span>搜索历史</span>',
  'Agent Session 面板',
  '创建 Session',
  '新建 Session',
  'project compat projection',
  'Session 列表',
  'Session 详情',
  '取消 Session',
  '刷新详情',
  '回收过期 Lease',
  '暂无 session',
  '暂无任务',
  '暂无审批',
  '暂无执行策略事件',
  '暂无事件',
  '暂无消息',
  '治理动作',
  '清理旧数据',
  '图谱导出完成，nodes=',
  '请先输入 doc_ids（逗号或空格分隔）',
  '文档治理',
  '刷新文档',
  '选择当前页',
  '清空选择',
  '标题关键词',
  'extracted_data 不是合法 JSON',
  '批量写入结构化',
  '已选择文档:',
  '暂无文档',
  '上一页',
  '下一页',
  '暂无搜索历史',
  '卡片标签',
  '业务数据',
  '图谱扩展',
  '加载中...',
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

function extractOpsPageKeys(source) {
  return Array.from(new Set(
    Array.from(source.matchAll(/opsPage\.[A-Za-z0-9_.-]+/g)).map((match) => match[0]),
  )).sort()
}

const pageSource = readFile(files.page)
const catalogSource = readFile(files.catalog)
const auditSource = readFile(files.businessStringAudit)
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'opsPage')
const pageKeys = extractOpsPageKeys(pageSource)
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('opsPage namespace must exist in shape, zh-CN, and en-US')
}

for (const key of requiredAnchorKeys) {
  if (!pageKeys.includes(key)) {
    failures.push(`OpsPage does not use required anchor ${key}`)
  }
}

for (const key of pageKeys) {
  const shortKey = key.replace(/^opsPage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`opsPage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired OpsPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('OpsPage must read the shared app locale')
}
if (!pageSource.includes("import { DEFAULT_APP_LOCALE, translate, useAppLocale, type AppLocale, type MessageKey } from '../app/platform/i18n'")) {
  failures.push('OpsPage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatOpsTemplate(')) {
  failures.push('OpsPage must format status/count labels through catalog template data')
}
if (!pageSource.includes('toLocaleString(locale)')) {
  failures.push('OpsPage must format dates through the active app locale')
}
if (!pageSource.includes('OPS_ACTION_NAME_KEYS')) {
  failures.push('OpsPage must use stable action keys for localized status messages')
}
if (!auditSource.includes('opsPage')) {
  failures.push('business-string audit must recognize the opsPage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'ops_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'opsPage',
  page_keys: pageKeys.length,
  required_anchor_keys: requiredAnchorKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
