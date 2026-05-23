#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/LlmDesignerPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const retiredPageSnippets = [
  '<small>workflow composition</small>',
  '<h2>LLM Designer</h2>',
  '让模板、连线、运行态和结果检查留在同一块安静的画布里',
  '<strong>Nodes</strong>',
  'placeholder="Search node id / label / type"',
  'Connect P2P',
  'Delete Selected',
  '业务链条模板（下拉选择）',
  '生成所选业务链条',
  'Double-click canvas to add selected template',
  'JSON import / export',
  'Paste exported DSL JSON here...',
  'compile response',
  'run response / events',
  'storybook-lite contract',
  'Storybook Contract Surface',
  'Default Workflow Preview',
  'Template Palette',
  'Runtime Contract',
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

function extractPageKeys(source) {
  return Array.from(source.matchAll(/llmDesignerPage\.[A-Za-z0-9_.]+/g))
    .map((match) => match[0])
    .filter((key) => !key.endsWith('.'))
}

const pageSource = readFile(files.page)
const catalogSource = readFile(files.catalog)
const catalogBlocks = catalogNamespaceBlocks(catalogSource, 'llmDesignerPage')
const pageKeys = Array.from(new Set(extractPageKeys(pageSource))).sort()
const failures = []

if (catalogBlocks.length < 3) {
  failures.push('llmDesignerPage namespace must exist in shape, zh-CN, and en-US')
}

if (pageKeys.length < 120) {
  failures.push(`expected at least 120 llmDesignerPage keys in LlmDesignerPage, found ${pageKeys.length}`)
}

for (const key of pageKeys) {
  const shortKey = key.replace(/^llmDesignerPage\./, '')
  const keyPattern = new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')
  for (const block of catalogBlocks) {
    if (!keyPattern.test(block)) {
      failures.push(`llmDesignerPage catalog key ${shortKey} must exist in every catalog block`)
      break
    }
    keyPattern.lastIndex = 0
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired LlmDesignerPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('LlmDesignerPage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'")) {
  failures.push('LlmDesignerPage must use the shared i18n entrypoint')
}
if (!pageSource.includes('formatLlmDesignerTemplate(')) {
  failures.push('LlmDesignerPage must format catalog template strings')
}
if (!catalogSource.includes('llmDesignerPage: {')) {
  failures.push('catalog must expose a llmDesignerPage namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'llm_designer_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'llmDesignerPage',
  page_keys: pageKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
