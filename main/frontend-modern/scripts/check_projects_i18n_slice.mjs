#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/ProjectsPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'projects.create.title',
  'projects.field.projectKey',
  'projects.field.name',
  'projects.field.templateProject',
  'projects.field.llmServiceName',
  'projects.field.llmPromptTemplate',
  'projects.field.schema',
  'projects.field.enabled',
  'projects.field.active',
  'projects.field.actions',
  'projects.placeholder.projectKey',
  'projects.placeholder.projectName',
  'projects.placeholder.llmPromptTemplate',
  'projects.action.create',
  'projects.action.createFromTemplate',
  'projects.action.refresh',
  'projects.action.activate',
  'projects.action.save',
  'projects.action.rename',
  'projects.action.archive',
  'projects.action.restore',
  'projects.action.delete',
  'projects.list.title',
  'projects.list.empty',
  'projects.status.current',
  'projects.error.missingProjectKey',
]

const retiredPageSnippets = [
  '<h2><CopyPlus size={15} />创建项目</h2>',
  '<span>模板项目</span>',
  '<span>LLM 服务名</span>',
  '<CopyPlus size={14} />模板+提示词自动创建',
  '<span>LLM user_prompt_template（可选）</span>',
  'placeholder="填写后会写入新项目的 llm_service_configs"',
  '<h2><HardDriveDownload size={15} />项目列表</h2>',
  '<RefreshCw size={14} />刷新',
  '<th>操作</th>',
  "' (current)'",
  '>切换</button>',
  '<Edit3 size={12} />保存',
  '<Edit3 size={12} />改名',
  '<Archive size={12} />归档',
  '<RefreshCw size={12} />恢复',
  '<Trash2 size={12} />删除',
  'className="empty-cell">暂无项目',
  "throw new Error('缺少项目标识')",
]

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const pageSource = readFile(files.page)
const catalogSource = readFile(files.catalog)
const failures = []

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`ProjectsPage does not use ${key}`)
  }

  const shortKey = key.replace(/^projects\./, '')
  const catalogOccurrences = catalogSource.match(new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')) || []
  if (catalogOccurrences.length < 3) {
    failures.push(`projects catalog key ${shortKey} must exist in shape, zh-CN, and en-US`)
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired ProjectsPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('ProjectsPage must read the shared app locale')
}
if (!pageSource.includes("import { translate, useAppLocale } from '../app/platform/i18n'")) {
  failures.push('ProjectsPage must use the shared i18n entrypoint')
}
if (!catalogSource.includes('projects: {')) {
  failures.push('catalog must expose a projects namespace')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'projects_i18n_slice',
  page: files.page,
  catalog_namespace: 'projects',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
