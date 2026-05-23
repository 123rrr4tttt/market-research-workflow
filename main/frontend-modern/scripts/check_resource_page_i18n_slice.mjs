#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/ResourcePage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
  businessAudit: 'scripts/check_frontend_business_string_audit.mjs',
}

const retiredPageSnippets = [
  '就绪',
  '新增入口成功',
  '新增入口失败',
  '执行中',
  '执行完成',
  '失败详情',
  '信息资源库管理',
  '信息源库 Items 列表',
  '来源项编辑',
  'External Project 注册',
  'Handler 聚类',
  '站点入口推荐与绑定',
  '手动新增入口',
  'URL 池',
  'Site Entries',
  '刷新列表',
  '提取 URL',
  '发现入口',
  '简化去重',
  '预览 manifest',
  '注册到项目',
  '一键生成/更新',
  '一键绑定',
  '单条推荐',
  '当前页批量推荐',
  '新增入口',
  '上一页',
  '下一页',
  '暂无',
  'one url per line',
  'display name',
  'search handler or item',
  'preferred_execution_modes:',
  'View registration_context',
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
const businessAuditSource = readFile(files.businessAudit)
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'resourcePage')
const usedKeys = Array.from(new Set(Array.from(pageSource.matchAll(/resourcePage\.[A-Za-z0-9_.-]+/g), (match) => match[0]))).sort()
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('resourcePage namespace must exist in shape, zh-CN, and en-US')
}

if (usedKeys.length < 80) {
  failures.push(`ResourcePage should use a broad resourcePage catalog slice; found only ${usedKeys.length} keys`)
}

for (const key of usedKeys) {
  const shortKey = key.replace(/^resourcePage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`resourcePage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired ResourcePage literal still present: ${snippet}`)
  }
}

if (/[\u4e00-\u9fff]/.test(pageSource)) {
  failures.push('ResourcePage should not retain inline CJK copy after this i18n slice')
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('ResourcePage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'")) {
  failures.push('ResourcePage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatResourceTemplate(')) {
  failures.push('ResourcePage must format runtime messages through catalog template data')
}
if (!businessAuditSource.includes('resourcePage')) {
  failures.push('business-string audit must recognize the resourcePage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'resource_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'resourcePage',
  used_keys: usedKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
