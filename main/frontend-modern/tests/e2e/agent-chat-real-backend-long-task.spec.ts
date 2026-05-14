import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import {
  buildE2eProjectKey,
  createE2eProject,
  deleteE2eProject,
} from './helpers/project-fixtures'

const PROJECT_KEY = buildE2eProjectKey('e2e_agent_real')

test.describe('agent chat real backend long-task flow', () => {
  test.describe.configure({ mode: 'serial' })
  test.skip(process.env.AGENT_CORE_REAL_BACKEND_E2E !== '1', 'requires a real backend started with AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true')

  test.beforeAll(async ({ request }) => {
    await createE2eProject(request, PROJECT_KEY)
  })

  test.afterAll(async ({ request }) => {
    await deleteE2eProject(request, PROJECT_KEY)
  })

  test('routes material source and writing supplement semantics through the real backend', async ({ page }) => {
    await openAgentChat(page)

    const fact = await sendAgentMessage(page, '解释一下 CAPM 的核心假设')
    expect(fact).toContain('CAPM')
    expect(fact).not.toContain('event: agent_core.tool_call_requested')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('CAPM')

    const projectMaterials = await sendAgentMessage(page, '项目库里已有资料有哪些')
    expect(projectMaterials).toContain('project.context.bundle')
    expect(projectMaterials).not.toContain('tool_name":"source_library.item.list')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('内部已有资料')

    const sourceCatalog = await sendAgentMessage(page, '当前有哪些来源库 item？')
    expect(sourceCatalog).toContain('source_library.item.list')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('采集入口')

    const generalSupplement = await sendAgentMessage(page, '帮我搜集一些机器人资料')
    expect(generalSupplement).toContain('project.context.bundle')
    expect(generalSupplement).toContain('source.discovery.plan')
    expect(generalSupplement).toContain('source.web.search')
    expect(generalSupplement).toContain('capability_matrix')
    expect(generalSupplement).toContain('matrix_summary')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('一般补充资料')

    const writingInternal = await sendAgentMessage(page, '写作的时候帮我搜索一些资料')
    expect(writingInternal).toContain('project.context.bundle')
    expect(writingInternal).toContain('writing.document.list')
    expect(writingInternal).not.toContain('ingest.source_library.run')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('写作补资料')

    const writingCollected = await sendAgentMessage(page, '这段文字用已入库资料补一些事实')
    expect(writingCollected).toContain('project.context.bundle')
    expect(writingCollected).toContain('writing.document.list')
    expect(writingCollected).not.toContain('ingest.source_library.run')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('写作补资料')

    const writingGapSearch = await sendAgentMessage(page, '这段正文已有资料不足，帮我再找参考来源')
    expect(writingGapSearch).toContain('project.context.bundle')
    expect(writingGapSearch).toContain('source.discovery.plan')
    expect(writingGapSearch).toContain('source.web.search')
    expect(writingGapSearch).toContain('ingest.source_library.run')
    expect(writingGapSearch).toContain('matrix_summary')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('外部资料')

    const writingExternal = await sendAgentMessage(page, '这段文字需要补一点站外公开来源')
    expect(writingExternal).toContain('project.context.bundle')
    expect(writingExternal).toContain('source.discovery.plan')
    expect(writingExternal).toContain('source.web.search')
    expect(writingExternal).toContain('ingest.source_library.run')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('外部资料')
  })

  test('surfaces real AgentCore source intake and writing output after refresh', async ({ page }) => {
    await openAgentChat(page)
    const streamText = await sendAgentMessage(page, '执行一个长任务：调查机器人商业化并写入工作台，先看内部资料，不足时补充外部资料')

    expect(streamText).toContain('event: agent_core.tool_call_requested')
    expect(streamText).toContain('project.context.bundle')
    expect(streamText).toContain('source.discovery.plan')
    expect(streamText).toContain('source.web.search')
    expect(streamText).toContain('capability_matrix')
    expect(streamText).toContain('matrix_summary')
    expect(streamText).toContain('ingest.source_library.run')
    expect(streamText).toContain('agent_long_task.stage.update')
    expect(streamText).toContain('writing.document.insert_paragraph')

    const answer = page.locator('.agent-chat-message.role-assistant').last()
    await expect(answer).toContainText('source intake')
    await expect(answer).not.toContainText('TimeoutExpired')
    await expect(answer).not.toContainText('agent_batch.nl_command.submit')

    await page.locator('.agent-chat-runtime-panel summary').click()
    await page.getByRole('button', { name: 'tasks' }).click()
    const latestStageCard = page.getByTestId('agent-chat-long-task-stage-card').first()
    await expect(latestStageCard).toContainText('draft_output')
    await expect(latestStageCard).toContainText('source_intake')
    await expect(latestStageCard).toContainText('intake 1')
    await expect(latestStageCard).toContainText('等待采集结果完成后替换为正式引用')

    await page.getByRole('button', { name: 'tools' }).click()
    await expect(answer.locator('.agent-chat-run-details')).toContainText('ingest.source_library.run')
    await expect(answer.locator('.agent-chat-run-details')).toContainText('writing.document.insert_paragraph')
    const sourceQualityCards = page.getByTestId('agent-chat-source-quality-card')
    await expect(sourceQualityCards.filter({ hasText: 'example.com' }).first()).toBeVisible()
    await expect(sourceQualityCards.filter({ hasText: 'E2E Robotics Policy Candidate' }).first()).toContainText('review_candidates_then_source_library_or_url_pool_ingest')
    await expect(page.getByTestId('agent-chat-diff-event')).toContainText('+1 / -0')

    await page.reload()
    await expect(page.getByTestId('agent-chat-active-session-title')).toBeVisible()
    await page.locator('.agent-chat-runtime-panel summary').click()
    await page.getByRole('button', { name: 'tasks' }).click()
    const reloadedStageCard = page.getByTestId('agent-chat-long-task-stage-card').first()
    await expect(reloadedStageCard).toContainText('source_intake')
    await expect(reloadedStageCard).toContainText('draft_output')

    await page.getByRole('button', { name: 'tools' }).click()
    const candidateCard = page.getByTestId('agent-chat-source-quality-card').filter({ hasText: 'E2E Robotics Policy Candidate' }).first()
    await expect(candidateCard).toContainText('review_candidates_then_source_library_or_url_pool_ingest')
    const reviewStream = page.waitForResponse((response) => {
      return response.url().includes('/api/v1/agent-chat/turn/stream') && response.status() === 200
    })
    await candidateCard.getByTestId('agent-chat-source-candidate-approve').click()
    const reviewText = await (await reviewStream).text()
    expect(reviewText).toContain('source.candidate.review')
    expect(reviewText).toContain('ingest.url_pool.submit')
    expect(reviewText).toContain('url_pool')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('ingest.url_pool.submit')
    await page.reload()
    await expect(page.getByTestId('agent-chat-active-session-title')).toBeVisible()
    await page.locator('.agent-chat-runtime-panel summary').click()
    await page.getByRole('button', { name: 'tools' }).click()
    const reviewedCandidateCard = page.getByTestId('agent-chat-source-quality-card').filter({ hasText: 'E2E Robotics Policy Candidate' }).first()
    await expect(reviewedCandidateCard.getByTestId('agent-chat-source-candidate-decision')).toContainText('已采集')
    await expect(reviewedCandidateCard.getByTestId('agent-chat-source-candidate-decision')).toContainText('e2e-url-pool')
    await expect(reviewedCandidateCard.getByTestId('agent-chat-source-candidate-decision')).toContainText('URL-pool completed')

    const statusStream = await sendAgentMessage(page, '检查刚才 URL-pool 采集任务是否完成')
    expect(statusStream).toContain('source.history.read')
    expect(statusStream).toContain('ingest.url_pool.status')
    expect(statusStream).toContain('task_event_artifact_found')
    expect(statusStream).toContain('completed')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('task event')

    const writingAppendStream = await sendAgentMessage(page, '把刚才采集的候选来源写进工作台草稿，标记为待复核来源')
    expect(writingAppendStream).toContain('agent_artifact.search')
    expect(writingAppendStream).toContain('agent_artifact.read')
    expect(writingAppendStream).toContain('writing.document.insert_paragraph')
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('待复核来源')

    await page.goto('/#writing-workbench.html')
    await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
    await expect(page.getByTestId('writing-document-card').filter({ hasText: 'E2E AgentCore Robotics Draft' }).first()).toBeVisible()
    await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(/e2e\.robotics\.baseline/)
    await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(/URL-pool 采集边界提交/)
  })
})

async function openAgentChat(page: Page) {
  await page.addInitScript((key) => {
    if (!window.sessionStorage.getItem('agent_core_real_backend_e2e_initialized')) {
      window.localStorage.clear()
      window.sessionStorage.setItem('agent_core_real_backend_e2e_initialized', '1')
    }
    window.localStorage.setItem('market_project_key', key)
  }, PROJECT_KEY)
  const response = await page.goto('/#agent-chat.html')
  if (response) expect(response.ok()).toBeTruthy()
  await expect(page.getByTestId('agent-chat-page')).toBeVisible()
  await expect(page.getByTestId('agent-chat-input')).toBeVisible()
}

async function sendAgentMessage(page: Page, message: string): Promise<string> {
  const stream = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/agent-chat/turn/stream') && response.status() === 200
  })
  await page.getByTestId('agent-chat-input').fill(message)
  await page.getByTestId('agent-chat-send-button').click()
  const streamResponse = await stream
  return streamResponse.text()
}
