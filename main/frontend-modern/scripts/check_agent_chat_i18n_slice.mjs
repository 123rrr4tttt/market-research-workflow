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
  'agentChat.brand.agent',
  'agentChat.workbench.ariaLabel',
  'agentChat.workbench.tab.overview',
  'agentChat.workbench.tab.tasks',
  'agentChat.workbench.tab.tools',
  'agentChat.workbench.tab.approvals',
  'agentChat.workbench.tab.artifacts',
  'agentChat.runtime.title',
  'agentChat.runtime.summary',
  'agentChat.runtime.compatLabel',
  'agentChat.runtime.projectionLabel',
  'agentChat.runtime.projectionEmpty',
  'agentChat.metric.phase',
  'agentChat.metric.status',
  'agentChat.metric.root',
  'agentChat.metric.stream',
  'agentChat.message.role.user',
  'agentChat.message.role.system',
  'agentChat.message.role.assistant',
  'agentChat.message.runToolsCount',
  'agentChat.message.runtimeMeta',
  'agentChat.message.details',
  'agentChat.stream.toolCallRequestedWithTool',
  'agentChat.stream.toolCallRequested',
  'agentChat.stream.toolCallStartedWithTool',
  'agentChat.stream.toolCallStarted',
  'agentChat.stream.toolProgressWithTool',
  'agentChat.stream.toolProgress',
  'agentChat.stream.toolResultWithToolAndSummary',
  'agentChat.stream.toolResultWithTool',
  'agentChat.stream.toolResult',
  'agentChat.stream.permissionRequestedWithTool',
  'agentChat.stream.permissionRequested',
  'agentChat.stream.turnModelStep',
  'agentChat.stream.turnToolCalls',
  'agentChat.stream.turnFinalAnswer',
  'agentChat.stream.turnTransition',
  'agentChat.stream.runResumed',
  'agentChat.status.thinking',
  'agentChat.status.loading',
  'agentChat.error.backendSessionLoadFailed',
  'agentChat.error.taskListLoadFailed',
  'agentChat.error.eventStreamLoadFailed',
  'agentChat.error.artifactLoadFailed',
  'agentChat.error.capabilityCatalogLoadFailed',
  'agentChat.error.invalidApprovalJson',
  'agentChat.action.continueCurrentSession',
  'agentChat.action.retryFailedTask',
  'agentChat.action.stopCurrentSession',
  'agentChat.action.retry',
  'agentChat.action.continue',
  'agentChat.action.refresh',
  'agentChat.action.approveAndContinue',
  'agentChat.action.reject',
  'agentChat.section.taskPlan',
  'agentChat.section.longTaskStages',
  'agentChat.section.capabilities',
  'agentChat.section.toolCalls',
  'agentChat.section.progressiveEvents',
  'agentChat.section.investigationTrace',
  'agentChat.section.writingDiff',
  'agentChat.section.sourceQuality',
  'agentChat.section.approvals',
  'agentChat.section.artifacts',
  'agentChat.empty.events',
  'agentChat.empty.tasks',
  'agentChat.empty.capabilityCatalog',
  'agentChat.empty.governedCapabilities',
  'agentChat.empty.externalBoundary',
  'agentChat.empty.toolCalls',
  'agentChat.empty.progressiveEvents',
  'agentChat.empty.sourceHistory',
  'agentChat.empty.approvals',
  'agentChat.empty.artifacts',
  'agentChat.task.pendingModel',
  'agentChat.task.blockedByCount',
  'agentChat.task.blocksCount',
  'agentChat.task.readCount',
  'agentChat.task.writeCount',
  'agentChat.longTask.completed',
  'agentChat.longTask.next',
  'agentChat.capability.group.core',
  'agentChat.capability.group.governed',
  'agentChat.capability.group.externalBoundary',
  'agentChat.capability.readOnlyTitle',
  'agentChat.capability.externalBoundaryTitle',
  'agentChat.capability.notAvailableBoundary',
  'agentChat.source.filter.all',
  'agentChat.source.filter.open',
  'agentChat.source.filter.approved',
  'agentChat.source.filter.deferred',
  'agentChat.source.filter.rejected',
  'agentChat.source.decision.approved',
  'agentChat.source.decision.deferred',
  'agentChat.source.decision.rejected',
  'agentChat.source.scoreMeta',
  'agentChat.source.taskLabel',
  'agentChat.source.action.collect',
  'agentChat.source.action.defer',
  'agentChat.source.action.reject',
  'agentChat.approval.pending',
  'agentChat.approval.overrideAriaLabel',
  'agentChat.approval.approvedContinue',
  'agentChat.approval.rejectedWithId',
  'agentChat.approval.rejected',
  'agentChat.approval.invalidOverrideObject',
  'agentChat.approval.highRiskCapability',
  'agentChat.approval.overridePlaceholder',
  'agentChat.event.summary.turnState',
  'agentChat.event.title.toolRequested',
  'agentChat.event.title.toolStarted',
  'agentChat.event.title.toolResult',
  'agentChat.event.title.turnState',
  'agentChat.event.title.approvalUpdate',
  'agentChat.event.title.taskUpdate',
  'agentChat.event.meta.event',
  'agentChat.event.meta.task',
  'agentChat.event.meta.sequence',
  'agentChat.tool.genericAgentLoop',
  'agentChat.tool.genericTool',
  'agentChat.toolCall.runLabel',
  'agentChat.source.fallback.candidate',
  'agentChat.source.nextGate.urlPool',
  'agentChat.source.decision.reason',
  'agentChat.source.decision.command',
  'agentChat.writing.fallback.toolName',
  'agentChat.writing.fallback.summary',
  'agentChat.investigation.fallback.focus',
  'agentChat.investigation.fallback.summary',
  'agentChat.investigation.counts',
  'agentChat.longTask.counter.evidenceRefs',
  'agentChat.longTask.counter.gapList',
  'agentChat.longTask.counter.externalDiscoveryPlan',
  'agentChat.longTask.counter.sourceIntake',
  'agentChat.longTask.counter.clueRefs',
  'agentChat.longTask.counter.draftRefs',
  'agentChat.longTask.fallback.artifactName',
  'agentChat.longTask.fallback.summary',
  'agentChat.longTask.noCounters',
  'agentChat.longTask.none',
  'agentChat.diff.docLabel',
  'agentChat.status.streamDetail',
  'agentChat.composer.inputAriaLabel',
  'agentChat.message.defaultAssistantComplete',
  'agentChat.message.backendCallFailed',
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
  'title="继续当前 agent 会话"',
  'title="重试失败任务"',
  'title="停止当前会话"',
  '后端会话读取失败',
  '任务列表读取失败',
  '事件流读取失败',
  '产物读取失败',
  '能力目录读取失败',
  'JSON 参数无效',
  '准备调用工具：',
  '正在调用工具：',
  '工具运行中：',
  '工具已完成。',
  '等待确认...',
  '模型正在阅读上下文...',
  '模型正在选择并调用工具...',
  '正在生成最终回答...',
  '已恢复会话，继续执行...',
  '<small>Agent</small>',
  '<span>正在思考</span>',
  '运行细节',
  'aria-label="agent workbench view"',
  '<span>phase</span>',
  '<span>status</span>',
  '<span>root</span>',
  '<span>stream</span>',
  '<p>暂无事件</p>',
  '<span><Play size={13} /> task plan</span>',
  '等待模型继续处理',
  'title="只读能力目录项"',
  'title="未作为可执行工具暴露"',
  'not available in the current AgentCore tool boundary',
  '暂无工具调用',
  'progressive events',
  'source quality',
  '当前筛选下没有候选来源',
  '<small>待审批</small>',
  'aria-label="approval override JSON"',
  '批准并继续',
  '审批已拒绝',
  '<p>暂无产物</p>',
  '刷新',
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
