#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/SettingsPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
  audit: 'scripts/check_frontend_business_string_audit.mjs',
}

const requiredKeys = [
  'settingsPage.title.llmView',
  'settingsPage.title.settingsView',
  'settingsPage.section.envConfig',
  'settingsPage.section.projectLlmTemplates',
  'settingsPage.guide.title',
  'settingsPage.guide.llm',
  'settingsPage.guide.search',
  'settingsPage.guide.news',
  'settingsPage.guide.db',
  'settingsPage.guide.es',
  'settingsPage.guide.focusField',
  'settingsPage.action.refreshing',
  'settingsPage.action.refresh',
  'settingsPage.action.copyExampleConfig',
  'settingsPage.action.goToCrawlerManage',
  'settingsPage.action.closeGuide',
  'settingsPage.action.saving',
  'settingsPage.action.saveEnv',
  'settingsPage.action.copying',
  'settingsPage.action.copyFromProject',
  'settingsPage.action.collapse',
  'settingsPage.action.edit',
  'settingsPage.action.saveServiceTemplate',
  'settingsPage.placeholder.envKey',
  'settingsPage.placeholder.sourceProjectKey',
  'settingsPage.field.copyOverwrite',
  'settingsPage.field.service',
  'settingsPage.field.model',
  'settingsPage.field.temperature',
  'settingsPage.field.topP',
  'settingsPage.field.maxTokens',
  'settingsPage.field.enabled',
  'settingsPage.field.updated',
  'settingsPage.field.actions',
  'settingsPage.field.presencePenalty',
  'settingsPage.field.frequencyPenalty',
  'settingsPage.field.systemPrompt',
  'settingsPage.field.userPromptTemplate',
  'settingsPage.value.enabledTrue',
  'settingsPage.value.enabledFalse',
  'settingsPage.message.envUpdated',
  'settingsPage.message.envUpdateFailed',
  'settingsPage.message.exampleCopied',
  'settingsPage.message.exampleCopyFailed',
  'settingsPage.message.templateSaved',
  'settingsPage.message.templateSaveFailed',
  'settingsPage.message.copyDone',
  'settingsPage.message.copyFailed',
  'settingsPage.empty.projectLlmTemplates',
  'settingsPage.error.envLoadFailed',
  'settingsPage.error.templatesLoadFailed',
  'settingsPage.error.unknown',
  'settingsPage.error.codeDetail',
  'settingsPage.error.traceDetail',
  'settingsPage.error.withDetails',
  'settingsPage.error.detailSeparator',
  'settingsPage.snippet.llm',
  'settingsPage.snippet.search',
  'settingsPage.snippet.news',
  'settingsPage.snippet.db',
  'settingsPage.snippet.es',
]

const retiredPageSnippets = [
  'LLM 配置视图',
  '系统设置视图',
  '环境配置已更新',
  '模板已保存：',
  '复制完成：copied=',
  '示例配置已复制到剪贴板',
  '复制失败，请手动复制页面中的示例字段。',
  '环境配置',
  '刷新中...',
  '安装/配置指引',
  '请配置 LLM provider',
  '已自动定位字段：',
  '复制示例配置',
  '前往爬虫管理（安装/接入）',
  '关闭指引',
  '输入 ${key}',
  '保存配置',
  '环境配置加载失败，请稍后重试',
  '项目级 LLM 模板',
  '来源 project_key',
  '覆盖已存在模板',
  '复制中...',
  '从项目复制模板',
  '<th>service</th>',
  '<th>model</th>',
  '<th>操作</th>',
  '>收起</button>',
  '>编辑</button>',
  '<span>enabled</span>',
  '暂无项目级 LLM 模板',
  '项目级 LLM 模板加载失败，请稍后重试',
  '未知错误',
]

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const pageSource = readFile(files.page)
const catalogSource = readFile(files.catalog)
const auditSource = readFile(files.audit)
const failures = []

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`SettingsPage does not use ${key}`)
  }

  const shortKey = key.replace(/^settingsPage\./, '')
  const catalogOccurrences = catalogSource.match(new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')) || []
  if (catalogOccurrences.length < 3) {
    failures.push(`settingsPage catalog key ${shortKey} must exist in shape, zh-CN, and en-US`)
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired SettingsPage literal still present: ${snippet}`)
  }
}

if (!pageSource.includes("import { APP_LOCALES, setAppLocale, translate, useAppLocale, type MessageKey } from '../app/platform/i18n'")) {
  failures.push('SettingsPage must use the shared i18n entrypoint and typed MessageKey')
}
if (!catalogSource.includes('settingsPage: {')) {
  failures.push('catalog must expose a settingsPage namespace')
}
if ((auditSource.match(/settingsPage/g) || []).length < 2) {
  failures.push('business-string audit must classify settingsPage catalog keys')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'settings_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'settingsPage',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
