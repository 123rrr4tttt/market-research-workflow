#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/DashboardPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'dashboardPage.title.dashboard',
  'dashboardPage.title.market',
  'dashboardPage.title.social',
  'dashboardPage.title.analysis',
  'dashboardPage.title.board',
  'dashboardPage.hint.dashboard',
  'dashboardPage.hint.market',
  'dashboardPage.hint.social',
  'dashboardPage.hint.analysis',
  'dashboardPage.hint.board',
  'dashboardPage.kpi.documents',
  'dashboardPage.kpi.documentsRecent',
  'dashboardPage.kpi.sources',
  'dashboardPage.kpi.sourcesTotal',
  'dashboardPage.kpi.marketStats',
  'dashboardPage.kpi.marketStates',
  'dashboardPage.kpi.runningTasks',
  'dashboardPage.kpi.tasksFailed',
  'dashboardPage.action.refresh',
  'dashboardPage.action.refreshing',
  'dashboardPage.metric.documentsToday',
  'dashboardPage.metric.tasksTotal',
  'dashboardPage.metric.tasksCompleted',
  'dashboardPage.metric.extractionRate',
  'dashboardPage.error.loadFailed',
  'dashboardPage.section.documentTypeDistribution',
  'dashboardPage.field.type',
  'dashboardPage.field.count',
  'dashboardPage.empty.distribution',
]

const retiredPageSnippets = [
  "toLocaleString('zh-CN')",
  "dashboard: '综合数据概览'",
  "market: '市场视角概览'",
  "social: '舆情视角概览'",
  "analysis: '分析视角概览'",
  "board: '看板视角概览'",
  "dashboard: '跨域总览指标'",
  "market: '重点关注 market 数据和州覆盖'",
  '<span>文档总数</span>',
  '<span>数据源</span>',
  '<span>市场数据</span>',
  '<span>任务运行</span>',
  '7天新增',
  '覆盖州',
  "dashboardStats.isFetching ? '刷新中...' : '刷新'",
  '今日文档新增:',
  '任务总量:',
  '任务完成:',
  '结构化提取率:',
  '看板加载失败，请稍后重试',
  '文档类型分布',
  '<th>类型</th>',
  '<th>数量</th>',
  '暂无分布数据',
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
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'dashboardPage')
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('dashboardPage namespace must exist in shape, zh-CN, and en-US')
}

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`DashboardPage does not use ${key}`)
  }

  const shortKey = key.replace(/^dashboardPage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`dashboardPage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired DashboardPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('DashboardPage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale } from '../app/platform/i18n'")) {
  failures.push('DashboardPage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatDashboardTemplate(')) {
  failures.push('DashboardPage must format count/rate copy through dashboard template data')
}
if (!pageSource.includes('toLocaleString(locale)')) {
  failures.push('DashboardPage must format numbers through the active app locale')
}
if (!catalogSource.includes('dashboardPage: {')) {
  failures.push('catalog must expose a dashboardPage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'dashboard_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'dashboardPage',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
