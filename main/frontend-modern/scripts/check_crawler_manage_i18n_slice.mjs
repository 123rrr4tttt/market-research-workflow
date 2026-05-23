#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/CrawlerManagePage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'crawlerManagePage.section.import',
  'crawlerManagePage.section.projects',
  'crawlerManagePage.section.deployRunsDetail',
  'crawlerManagePage.field.project',
  'crawlerManagePage.field.crawlerProjectKey',
  'crawlerManagePage.field.name',
  'crawlerManagePage.field.gitUrl',
  'crawlerManagePage.field.branchTag',
  'crawlerManagePage.field.providerHint',
  'crawlerManagePage.field.description',
  'crawlerManagePage.field.selectedProject',
  'crawlerManagePage.field.deployVersion',
  'crawlerManagePage.field.rollbackToVersion',
  'crawlerManagePage.field.planner',
  'crawlerManagePage.field.projectKey',
  'crawlerManagePage.field.status',
  'crawlerManagePage.field.provider',
  'crawlerManagePage.field.deployedVersion',
  'crawlerManagePage.field.id',
  'crawlerManagePage.field.action',
  'crawlerManagePage.field.requestedVersion',
  'crawlerManagePage.field.fromTo',
  'crawlerManagePage.field.startedAt',
  'crawlerManagePage.field.finishedAt',
  'crawlerManagePage.field.field',
  'crawlerManagePage.field.value',
  'crawlerManagePage.field.sourceUri',
  'crawlerManagePage.field.currentVersion',
  'crawlerManagePage.field.previousVersion',
  'crawlerManagePage.field.updatedAt',
  'crawlerManagePage.placeholder.crawlerProjectKey',
  'crawlerManagePage.placeholder.name',
  'crawlerManagePage.placeholder.gitUrl',
  'crawlerManagePage.placeholder.branchTag',
  'crawlerManagePage.placeholder.description',
  'crawlerManagePage.placeholder.deployVersion',
  'crawlerManagePage.placeholder.rollbackVersion',
  'crawlerManagePage.control.enableNow',
  'crawlerManagePage.action.draftAutosave',
  'crawlerManagePage.action.importCrawlerProject',
  'crawlerManagePage.action.refreshList',
  'crawlerManagePage.action.submitDeploy',
  'crawlerManagePage.action.submitRollback',
  'crawlerManagePage.action.refreshDetail',
  'crawlerManagePage.action.refresh',
  'crawlerManagePage.tooltip.draftAutosave',
  'crawlerManagePage.empty.select',
  'crawlerManagePage.empty.selectProject',
  'crawlerManagePage.empty.crawlerProjects',
  'crawlerManagePage.empty.deployRuns',
  'crawlerManagePage.empty.detailNotSelected',
  'crawlerManagePage.detail.label',
  'crawlerManagePage.detail.summary',
  'crawlerManagePage.message.draftAutosaved',
  'crawlerManagePage.message.importSuccess',
  'crawlerManagePage.message.importSuccessWithKey',
  'crawlerManagePage.message.importFailed',
  'crawlerManagePage.message.deploySubmitted',
  'crawlerManagePage.message.deployRunCreated',
  'crawlerManagePage.message.deployFailed',
  'crawlerManagePage.message.rollbackSubmitted',
  'crawlerManagePage.message.rollbackRunCreated',
  'crawlerManagePage.message.rollbackFailed',
  'crawlerManagePage.error.missingGitUrl',
  'crawlerManagePage.error.missingCrawlerProject',
  'crawlerManagePage.error.unknown',
]

const retiredPageSnippets = [
  '请先填写爬虫项目 Git URL。',
  '导入成功',
  '导入失败',
  '请先选择爬虫项目',
  '部署已提交',
  '部署失败',
  '回滚已提交',
  '回滚失败',
  '爬虫项目接入',
  '导入后立即启用',
  '草稿已自动本地保存。',
  '当前页面变更会自动保存到本地，无需手动保存',
  '草稿自动保存',
  '导入爬虫项目',
  '刷新列表',
  '请选择',
  '提交部署',
  '提交回滚',
  '刷新详情',
  '暂无 crawler 项目',
  'Deploy Runs / 详情',
  '请选择项目',
  '暂无 deploy/rollback 记录',
  '尚未选择 crawler 项目',
  '<span>Crawler Project Key</span>',
  '<span>Selected Project</span>',
  '<span>Deploy Version</span>',
  '<span>Rollback To Version</span>',
  '<th>project_key</th>',
  '<th>requested_version</th>',
  '<th>from → to</th>',
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
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'crawlerManagePage')
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('crawlerManagePage namespace must exist in shape, zh-CN, and en-US')
}

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`CrawlerManagePage does not use ${key}`)
  }

  const shortKey = key.replace(/^crawlerManagePage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`crawlerManagePage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired CrawlerManagePage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('CrawlerManagePage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'")) {
  failures.push('CrawlerManagePage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatCrawlerTemplate(')) {
  failures.push('CrawlerManagePage must format runtime messages through catalog template data')
}
if (!catalogSource.includes('crawlerManagePage: {')) {
  failures.push('catalog must expose a crawlerManagePage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'crawler_manage_i18n_slice',
  page: files.page,
  catalog_namespace: 'crawlerManagePage',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
