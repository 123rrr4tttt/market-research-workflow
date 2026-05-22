#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/CatalogPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'catalogPage.title.catalog',
  'catalogPage.title.objectView',
  'catalogPage.variant.catalog',
  'catalogPage.variant.company',
  'catalogPage.variant.product',
  'catalogPage.variant.operation',
  'catalogPage.section.topics',
  'catalogPage.section.products',
  'catalogPage.field.topicName',
  'catalogPage.field.keywords',
  'catalogPage.field.name',
  'catalogPage.field.category',
  'catalogPage.field.enabled',
  'catalogPage.field.actions',
  'catalogPage.action.createTopic',
  'catalogPage.action.createProduct',
  'catalogPage.action.delete',
  'catalogPage.empty.topics',
  'catalogPage.empty.products',
  'catalogPage.status.enabled',
  'catalogPage.status.disabled',
]

const retiredPageSnippets = [
  "variant === 'catalog' ? '行业公司/商品/经营'",
  '`对象视图: ${variant}`',
  '<div className="panel-header"><h2>主题管理</h2></div>',
  '<span>topic_name</span>',
  '<span>keywords(,)</span>',
  '<CopyPlus size={14} />新增主题',
  '<th>name</th><th>enabled</th><th>keywords</th><th>action</th>',
  '<Trash2 size={12} />删除',
  'className="empty-cell">暂无主题',
  '<div className="panel-header"><h2>商品管理</h2></div>',
  '<span>category</span>',
  '<CopyPlus size={14} />新增商品',
  '<th>name</th><th>category</th><th>enabled</th><th>action</th>',
  'className="empty-cell">暂无商品',
  'String(row.enabled)',
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
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'catalogPage')
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('catalogPage namespace must exist in shape, zh-CN, and en-US')
}

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`CatalogPage does not use ${key}`)
  }

  const shortKey = key.replace(/^catalogPage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`catalogPage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired CatalogPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('CatalogPage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale } from '../app/platform/i18n'")) {
  failures.push('CatalogPage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatCatalogTemplate(')) {
  failures.push('CatalogPage must format the variant title through catalog template data')
}
if (!catalogSource.includes('catalogPage: {')) {
  failures.push('catalog must expose a catalogPage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'catalog_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'catalogPage',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
