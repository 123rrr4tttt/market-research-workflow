#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/ProcessPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'processPage.title.process',
  'processPage.title.processing',
  'processPage.kpi.runningTasks',
  'processPage.kpi.activeTasks',
  'processPage.kpi.scheduledTasks',
  'processPage.kpi.reservedTasks',
  'processPage.kpi.workers',
  'processPage.kpi.totalTasks',
  'processPage.kpi.pendingTasks',
  'processPage.section.currentQueue',
  'processPage.section.taskDetail',
  'processPage.section.taskHistory',
  'processPage.section.rejectionBreakdown',
  'processPage.control.autoRefresh',
  'processPage.control.interval',
  'processPage.action.refresh',
  'processPage.action.refreshing',
  'processPage.action.selectCancellable',
  'processPage.action.clearSelection',
  'processPage.action.cancelSelected',
  'processPage.action.collapse',
  'processPage.action.details',
  'processPage.action.cancel',
  'processPage.action.close',
  'processPage.field.id',
  'processPage.field.taskId',
  'processPage.field.name',
  'processPage.field.status',
  'processPage.field.worker',
  'processPage.field.source',
  'processPage.field.started',
  'processPage.field.finished',
  'processPage.field.selected',
  'processPage.field.actions',
  'processPage.field.type',
  'processPage.field.start',
  'processPage.field.end',
  'processPage.field.durationSeconds',
  'processPage.field.result',
  'processPage.field.resultSummary',
  'processPage.field.insertedValid',
  'processPage.field.rejected',
  'processPage.field.topRejectionReason',
  'processPage.field.lightFilter',
  'processPage.field.reason',
  'processPage.field.score',
  'processPage.field.keepForVectorization',
  'processPage.field.jobType',
  'processPage.field.displayMeta',
  'processPage.field.args',
  'processPage.field.kwargs',
  'processPage.field.progress',
  'processPage.field.resultRaw',
  'processPage.field.traceback',
  'processPage.field.logsTail',
  'processPage.field.params',
  'processPage.field.error',
  'processPage.summary.inserted',
  'processPage.summary.updated',
  'processPage.summary.skipped',
  'processPage.summary.errors',
  'processPage.summary.urls',
  'processPage.status.yes',
  'processPage.status.no',
  'processPage.detail.historyId',
  'processPage.empty.runningTasks',
  'processPage.empty.history',
  'processPage.error.logsFailed',
]

const retiredPageSnippets = [
  "toLocaleString('zh-CN')",
  "'数据处理任务视图'",
  "'任务调度视图'",
  '<span>运行任务</span>',
  '<span>总任务</span>',
  'active {processStats?.active_tasks',
  'pending {processList?.stats?.pending_tasks',
  '当前队列',
  '自动刷新',
  '选择可取消',
  '清空选择',
  '批量取消(',
  '<th>来源</th>',
  '<th>选中</th>',
  '暂无运行中任务',
  '任务详情',
  '结果摘要',
  '有效入库',
  '主要剔除原因',
  '轻过滤',
  '向量化保留',
  '剔除明细',
  '日志加载失败',
  '任务历史',
  '<th>类型</th>',
  '<th>状态</th>',
  '<th>开始</th>',
  '<th>结束</th>',
  '<th>耗时(秒)</th>',
  '<th>结果</th>',
  '<th>有效入库</th>',
  '<th>剔除</th>',
  '<th>主要剔除原因</th>',
  '<th>操作</th>',
  '暂无历史数据',
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
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'processPage')
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('processPage namespace must exist in shape, zh-CN, and en-US')
}

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`ProcessPage does not use ${key}`)
  }

  const shortKey = key.replace(/^processPage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`processPage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired ProcessPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('ProcessPage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale, type AppLocale } from '../app/platform/i18n'")) {
  failures.push('ProcessPage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatProcessTemplate(')) {
  failures.push('ProcessPage must format count/detail templates through catalog data')
}
if (!pageSource.includes('toLocaleString(locale)')) {
  failures.push('ProcessPage must format dates through the active app locale')
}
if (!catalogSource.includes('processPage: {')) {
  failures.push('catalog must expose a processPage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'process_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'processPage',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
