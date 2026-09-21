import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import {
  buildE2eProjectKey,
  createE2eProject,
  deleteE2eProject,
} from './helpers/project-fixtures'

const PROJECT_KEY = buildE2eProjectKey('e2e_agent_real')

type AgentTurn = {
  finalAnswer: string
  sessionId: string
  streamText: string
}

class AgentConversation {
  private sessionId: string | null = null

  constructor(private readonly request: APIRequestContext) {}

  async send(message: string): Promise<AgentTurn> {
    const response = await this.request.post('/api/v1/agent-chat/turn/stream', {
      data: {
        message,
        project_key: PROJECT_KEY,
        session_id: this.sessionId,
        enable_model_tool_loop: true,
        require_high_risk_approval: false,
      },
    })
    expect(response.ok(), `agent turn failed with HTTP ${response.status()}`).toBeTruthy()
    const streamText = await response.text()
    expect(streamText).not.toContain('event: agent_core.error')
    const result = extractFinalResult(streamText)
    const sessionId = readSessionId(result)
    expect(sessionId, 'agent turn should return a persistent session id').not.toBe('')
    if (this.sessionId) expect(sessionId).toBe(this.sessionId)
    this.sessionId = sessionId
    return {
      finalAnswer: String(result.final_answer || ''),
      sessionId,
      streamText,
    }
  }
}

test.describe('agent chat real backend long-task flow', () => {
  test.describe.configure({ mode: 'serial' })
  test.skip(process.env.AGENT_CORE_REAL_BACKEND_E2E !== '1', 'requires a real backend started with AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true')

  test.beforeAll(async ({ request }) => {
    await createE2eProject(request, PROJECT_KEY)
  })

  test.afterAll(async ({ request }) => {
    await deleteE2eProject(request, PROJECT_KEY)
  })

  test('routes material source and writing supplement semantics through the real backend', async ({ page, request }) => {
    await openCodexAgent(page)
    const conversation = new AgentConversation(request)

    const fact = await conversation.send('解释一下 CAPM 的核心假设')
    expect(fact.streamText).toContain('CAPM')
    expect(fact.streamText).not.toContain('event: agent_core.tool_call_requested')
    expect(fact.finalAnswer).toContain('CAPM')

    const projectMaterials = await conversation.send('项目库里已有资料有哪些')
    expect(projectMaterials.streamText).toContain('project.context.bundle')
    expect(projectMaterials.streamText).not.toContain('tool_name":"source_library.item.list')
    expect(projectMaterials.finalAnswer).toContain('内部已有资料')

    const sourceCatalog = await conversation.send('当前有哪些来源库 item？')
    expect(sourceCatalog.streamText).toContain('source_library.item.list')
    expect(sourceCatalog.finalAnswer).toContain('采集入口')

    const generalSupplement = await conversation.send('帮我搜集一些机器人资料')
    expect(generalSupplement.streamText).toContain('project.context.bundle')
    expect(generalSupplement.streamText).toContain('source.discovery.plan')
    expect(generalSupplement.streamText).toContain('source.web.search')
    expect(generalSupplement.streamText).toContain('capability_matrix')
    expect(generalSupplement.streamText).toContain('matrix_summary')
    expect(generalSupplement.finalAnswer).toContain('一般补充资料')

    const writingInternal = await conversation.send('写作的时候帮我搜索一些资料')
    expect(writingInternal.streamText).toContain('project.context.bundle')
    expect(writingInternal.streamText).toContain('writing.document.list')
    expect(writingInternal.streamText).not.toContain('ingest.source_library.run')
    expect(writingInternal.finalAnswer).toContain('写作补资料')

    const writingCollected = await conversation.send('这段文字用已入库资料补一些事实')
    expect(writingCollected.streamText).toContain('project.context.bundle')
    expect(writingCollected.streamText).toContain('writing.document.list')
    expect(writingCollected.streamText).not.toContain('ingest.source_library.run')
    expect(writingCollected.finalAnswer).toContain('写作补资料')

    const writingGapSearch = await conversation.send('这段正文已有资料不足，帮我再找参考来源')
    expect(writingGapSearch.streamText).toContain('project.context.bundle')
    expect(writingGapSearch.streamText).toContain('source.discovery.plan')
    expect(writingGapSearch.streamText).toContain('source.web.search')
    expect(writingGapSearch.streamText).toContain('ingest.source_library.run')
    expect(writingGapSearch.streamText).toContain('matrix_summary')
    expect(writingGapSearch.finalAnswer).toContain('外部资料')

    const writingExternal = await conversation.send('这段文字需要补一点站外公开来源')
    expect(writingExternal.streamText).toContain('project.context.bundle')
    expect(writingExternal.streamText).toContain('source.discovery.plan')
    expect(writingExternal.streamText).toContain('source.web.search')
    expect(writingExternal.streamText).toContain('ingest.source_library.run')
    expect(writingExternal.finalAnswer).toContain('外部资料')
  })

  test('surfaces real AgentCore source intake and writing output after refresh', async ({ page, request }) => {
    await openCodexAgent(page)
    const conversation = new AgentConversation(request)
    const longTask = await conversation.send('执行一个长任务：调查机器人商业化并写入工作台，先看内部资料，不足时补充外部资料')
    const { sessionId, streamText } = longTask

    expect(streamText).toContain('event: agent_core.tool_call_requested')
    expect(streamText).toContain('project.context.bundle')
    expect(streamText).toContain('source.discovery.plan')
    expect(streamText).toContain('source.web.search')
    expect(streamText).toContain('capability_matrix')
    expect(streamText).toContain('matrix_summary')
    expect(streamText).toContain('ingest.source_library.run')
    expect(streamText).toContain('agent_long_task.stage.update')
    expect(streamText).toContain('writing.document.insert_paragraph')

    expect(longTask.finalAnswer).toContain('source intake')
    expect(longTask.finalAnswer).not.toContain('TimeoutExpired')
    expect(longTask.finalAnswer).not.toContain('agent_batch.nl_command.submit')

    const persistedLongTask = await readPersistedAgentSession(request, sessionId)
    expect(persistedLongTask.text).toContain('draft_output')
    expect(persistedLongTask.text).toContain('source_intake')
    expectCompletedSourceIntake(persistedLongTask.json)
    expect(persistedLongTask.text).toContain('等待采集结果完成后替换为正式引用')
    expect(persistedLongTask.text).toContain('ingest.source_library.run')
    expect(persistedLongTask.text).toContain('writing.document.insert_paragraph')
    expect(persistedLongTask.text).toContain('example.com')
    expect(persistedLongTask.text).toContain('E2E Robotics Policy Candidate')
    expect(persistedLongTask.text).toContain('review_candidates_then_source_library_or_url_pool_ingest')
    expect(persistedLongTask.text).toContain('"added_lines":1')
    expect(persistedLongTask.text).toContain('"removed_lines":0')

    await page.reload()
    await expect(page.getByTestId('codex-agent-page')).toBeVisible()
    await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', '/codex/')
    const reloadedLongTask = await readPersistedAgentSession(request, sessionId)
    expect(reloadedLongTask.text).toContain('source_intake')
    expect(reloadedLongTask.text).toContain('draft_output')
    expect(reloadedLongTask.text).toContain('review_candidates_then_source_library_or_url_pool_ingest')

    const review = await conversation.send(`采集这个候选来源。source_candidate_review JSON：${JSON.stringify({
      decision: 'approved',
      candidate: {
        title: 'E2E Robotics Policy Candidate',
        url: 'https://example.gov/robotics-policy',
        snippet: 'Deterministic external search candidate for AgentCore browser E2E.',
        provider: 'e2e_scripted_search',
      },
      preferred_ingest: 'url_pool',
      reason: '用户在候选来源卡片中选择采集。',
      idempotency_key: `e2e-source-candidate-review-${PROJECT_KEY}`,
    })}`)
    const reviewText = review.streamText
    expect(reviewText).toContain('source.candidate.review')
    expect(reviewText).toContain('ingest.url_pool.submit')
    expect(reviewText).toContain('url_pool')
    expect(review.finalAnswer).toContain('ingest.url_pool.submit')
    const reviewedCandidate = await readPersistedAgentSession(request, sessionId)
    expect(reviewedCandidate.text).toContain('approved')
    expect(reviewedCandidate.text).toContain('e2e-url-pool')
    expectCompletedUrlPoolTaskEvent(reviewedCandidate.json)

    const status = await conversation.send('检查刚才 URL-pool 采集任务是否完成')
    expect(status.streamText).toContain('source.history.read')
    expect(status.streamText).toContain('ingest.url_pool.status')
    expect(status.streamText).toContain('task_event_artifact_found')
    expect(status.streamText).toContain('completed')
    expect(status.finalAnswer).toContain('task event')

    const writingAppend = await conversation.send('把刚才采集的候选来源写进工作台草稿，标记为待复核来源')
    expect(writingAppend.streamText).toContain('agent_artifact.search')
    expect(writingAppend.streamText).toContain('agent_artifact.read')
    expect(writingAppend.streamText).toContain('writing.document.insert_paragraph')
    expect(writingAppend.finalAnswer).toContain('待复核来源')

    await page.goto('/#writing-workbench.html')
    await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
    await expect(page.getByTestId('writing-document-card').filter({ hasText: 'E2E AgentCore Robotics Draft' }).first()).toBeVisible()
    await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(/e2e\.robotics\.baseline/)
    await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(/URL-pool 采集边界提交/)
  })
})

async function openCodexAgent(page: Page) {
  await page.addInitScript((key) => {
    window.localStorage.setItem('market_project_key', key)
  }, PROJECT_KEY)
  const response = await page.goto('/#/workbench/agent')
  if (response) expect(response.ok()).toBeTruthy()
  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', '/codex/')
  await expect(page.locator('.codex-agent-page__project')).toHaveText(PROJECT_KEY)
}

function extractFinalResult(streamText: string): Record<string, unknown> {
  const blocks = streamText.split(/\r?\n\r?\n+/)
  for (const block of blocks.reverse()) {
    if (!block.includes('event: agent_core.final_answer') && !block.includes('event: interactive_agent.final_answer')) continue
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.replace(/^data:\s?/, ''))
      .join('\n')
    if (!data) continue
    const payload = JSON.parse(data) as Record<string, unknown>
    const result = payload.result
    return result && typeof result === 'object' ? result as Record<string, unknown> : payload
  }
  throw new Error('agent chat stream closed without a final answer payload')
}

function readSessionId(result: Record<string, unknown>) {
  const session = result.session
  if (!session || typeof session !== 'object') return ''
  return String((session as Record<string, unknown>).session_id || '')
}

async function readPersistedAgentSession(request: APIRequestContext, sessionId: string) {
  const paths = [
    `/api/v1/agent-sessions/${encodeURIComponent(sessionId)}`,
    `/api/v1/agent-sessions/${encodeURIComponent(sessionId)}/tasks`,
    `/api/v1/agent-sessions/${encodeURIComponent(sessionId)}/events`,
    `/api/v1/agent-sessions/${encodeURIComponent(sessionId)}/artifacts`,
  ]
  const bodies: string[] = []
  const json: unknown[] = []
  for (const path of paths) {
    const response = await request.get(path)
    expect(response.ok(), `persisted session read failed for ${path}: HTTP ${response.status()}`).toBeTruthy()
    const body = await response.text()
    bodies.push(body)
    json.push(JSON.parse(body) as unknown)
  }
  return { json, text: bodies.join('\n') }
}

function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function collectJsonRecords(value: unknown, records: Array<Record<string, unknown>> = []) {
  if (Array.isArray(value)) {
    for (const item of value) collectJsonRecords(item, records)
    return records
  }
  if (!isJsonRecord(value)) return records
  records.push(value)
  for (const item of Object.values(value)) collectJsonRecords(item, records)
  return records
}

function expectCompletedSourceIntake(documents: unknown[]) {
  const records = collectJsonRecords(documents)
  const intakeStage = records.find((record) => (
    record.stage === 'source_intake'
    && record.status === 'completed'
    && isJsonRecord(record.counts)
    && record.counts.source_intake === 1
  ))
  expect(intakeStage, 'persisted long-task stage should record exactly one completed source intake').toBeDefined()
  expect(records.some((record) => (
    record.item_key === 'e2e.robotics.baseline'
    && record.task_id === 'e2e-task-robotics-baseline'
  )), 'persisted source-intake record should exact-bind the scripted item and task').toBeTruthy()
}

function expectCompletedUrlPoolTaskEvent(documents: unknown[]) {
  const taskEvent = collectJsonRecords(documents).find((record) => (
    record.contract_version === 'ingest.url_pool.task_event.v1'
    && record.status === 'completed'
    && record.url === 'https://example.gov/robotics-policy'
    && typeof record.task_id === 'string'
    && record.task_id.startsWith('e2e-url-pool-')
    && isJsonRecord(record.result)
    && record.result.e2e_scripted_task_event === true
  ))
  expect(taskEvent, 'persisted URL-pool task event should be a completed scripted event exact-bound to the candidate URL').toBeDefined()
}
