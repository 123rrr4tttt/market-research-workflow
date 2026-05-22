#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/AgentChatPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'agentChat.stage.context',
  'agentChat.stage.tools',
  'agentChat.stage.answer',
  'agentChat.system.ready',
  'agentChat.system.newSessionCreated',
  'agentChat.session.newTitle',
  'agentChat.session.recoveredTitle',
  'agentChat.session.updatedNow',
  'agentChat.session.searchPlaceholder',
  'agentChat.session.label',
  'agentChat.session.current',
  'agentChat.session.emptyPreview',
  'agentChat.session.noMatchesTitle',
  'agentChat.session.noMatchesHint',
  'agentChat.session.running',
  'agentChat.session.runningTasksCount',
  'agentChat.session.messageCount',
  'agentChat.status.approvalNeeded',
  'agentChat.status.approvalNeededDetail',
  'agentChat.status.live',
  'agentChat.status.idle',
  'agentChat.status.idleDetail',
  'agentChat.composer.idleHint',
  'agentChat.composer.inputPlaceholder',
  'agentChat.composer.quickCommand.marketDrivers',
  'agentChat.composer.quickCommand.ingestBatch',
  'agentChat.composer.quickCommand.runtimeRisk',
  'agentChat.action.newConversation',
  'agentChat.action.newFromDraft',
  'agentChat.action.clearSession',
  'agentChat.action.send',
]

const retiredPageSnippets = [
  'const DEFAULT_QUICK_COMMANDS = [',
  'const DEFAULT_SESSIONS',
  '<span>新对话</span>',
  'placeholder="搜索"',
  '直接输入问题或任务。工具和产物会作为运行细节折叠在同一条对话流里。',
  '基于当前草稿新建会话',
  'placeholder="输入问题或任务"',
  'title="清空当前会话"',
  'title="发送"',
  '`${activeMessages.length} 条消息`',
  '新会话已创建。可继续围绕这条任务展开',
  'New Agent Session',
  'Recovered Session',
  "updatedAt: '刚刚'",
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
    failures.push(`AgentChatPage does not use ${key}`)
  }

  const shortKey = key.replace(/^agentChat\./, '')
  const catalogOccurrences = catalogSource.match(new RegExp(`'${escapeRegExp(shortKey)}'\\s*:`, 'g')) || []
  if (catalogOccurrences.length < 3) {
    failures.push(`agentChat catalog key ${shortKey} must exist in shape, zh-CN, and en-US`)
  }
}

for (const snippet of retiredPageSnippets) {
  if (pageSource.includes(snippet)) {
    failures.push(`retired AgentChat page literal still present: ${snippet}`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('AgentChatPage must read the shared app locale')
}
if (!pageSource.includes('formatCatalogTemplate(')) {
  failures.push('AgentChatPage must format catalog templates for count/command labels')
}
if (!catalogSource.includes('const namespaceCatalog = catalog[namespace as keyof CatalogShape]')) {
  failures.push('catalog readback must support the agentChat namespace through generic namespace lookup')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'agent_chat_i18n_slice',
  page: files.page,
  catalog_namespace: 'agentChat',
  required_keys: requiredKeys.length,
  retired_page_snippets: retiredPageSnippets.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
