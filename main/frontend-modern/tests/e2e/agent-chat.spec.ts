import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

async function openAgentChat(page: Page) {
  const initial = await page.goto('/#agent-chat.html')
  if (initial) expect(initial.ok()).toBeTruthy()
  await page.evaluate(() => window.localStorage.clear())
  const response = await page.reload()
  if (response) expect(response.ok()).toBeTruthy()
  await expect(page.locator('.agent-chat-page')).toBeVisible()
  await expect(page.getByTestId('agent-chat-active-session-title')).toBeVisible()
}

async function sendAgentMessage(page: Page, message: string) {
  const streamResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/agent-chat/turn/stream') && response.status() === 200
  })
  await page.getByTestId('agent-chat-input').fill(message)
  await page.getByTestId('agent-chat-send-button').click()
  const response = await streamResponse
  const streamText = await response.text()
  const finalAnswer = extractFinalAnswer(streamText)
  await expect(page.locator('.agent-chat-message.role-assistant').last()).not.toContainText('正在解析指令')
  return { answer: page.locator('.agent-chat-message.role-assistant').last(), finalAnswer, streamText }
}

function extractFinalAnswer(streamText: string) {
  const blocks = streamText.split(/\n\n+/)
  for (const block of blocks.reverse()) {
    if (!block.includes('event: interactive_agent.final_answer') && !block.includes('event: agent_core.final_answer')) continue
    const data = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.replace(/^data:\s?/, ''))
      .join('\n')
    if (!data) continue
    const parsed = JSON.parse(data) as { final_answer?: string, result?: { final_answer?: string } }
    return parsed.result?.final_answer || parsed.final_answer || ''
  }
  return ''
}

function compactText(value: string) {
  return value.replace(/\s+/g, ' ').trim()
}

function buildAgentCoreFinalSse(result: Record<string, unknown>) {
  return [
    'event: agent_core.final_answer',
    `data: ${JSON.stringify({
      event_type: 'agent_core.final_answer',
      seq: 1,
      result,
    })}`,
    '',
    '',
  ].join('\n')
}

function buildAgentCoreEventSse(eventType: string, data: Record<string, unknown>) {
  return [
    `event: agent_core.${eventType}`,
    `data: ${JSON.stringify({
      event_type: eventType,
      ...data,
    })}`,
    '',
    '',
  ].join('\n')
}

async function installAgentChatScenarioMocks(page: Page) {
  let activeScenario: 'conversation' | 'project-data' | 'source-run' | 'long-task' | 'mobile' | 'control' = 'conversation'
  const approval = {
    approval_id: 'ap-e2e-source-library',
    status: 'pending',
    binding_payload: {
      capability_id: 'ingest.source_library.run',
      command: '用来源库 market.general.baseline 补一轮证据',
    },
    metadata: { capability_id: 'ingest.source_library.run' },
  }

  await page.route('**/api/v1/agent-chat/capabilities**', async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        tool_pool: {
          groups: {
            core: [
              { capability_id: 'project.summary.read', approval_level: 'none', concurrency_class: 'readonly', implemented: true, implementation_state: 'ready', enabled: true },
              { capability_id: 'source_library.item.list', approval_level: 'none', concurrency_class: 'readonly', implemented: true, implementation_state: 'ready', enabled: true },
            ],
            deferred: [
              { capability_id: 'ingest.source_library.run', approval_level: 'approval_required', concurrency_class: 'governed', implemented: true, implementation_state: 'ready', enabled: true },
            ],
          },
        },
      },
    })
  })
  await page.route('**/api/v1/agent-sessions/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/stream')) {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: 'event: agent_session.keepalive\ndata: {"event_type":"agent_session.keepalive","seq":1}\n\n',
    })
      return
    }
    if (url.includes('/tasks')) {
      await route.fulfill({
        status: 200,
        json: {
          items: activeScenario === 'long-task'
            ? [
                {
                  task_id: 'task-research',
                  subject: '候选来源调查',
                  description: '规划机器人商业化候选来源',
                  status: 'completed',
                  phase: 'research',
                  priority: 1,
                  result_summary: '已记录 1 条高可信候选来源',
                  read_set: ['source_library'],
                  write_set: ['investigation.leads'],
                },
                {
                  task_id: 'task-writing',
                  subject: '写作工作台补段',
                  description: '把调查结果写入工作台草稿',
                  status: 'completed',
                  phase: 'implementation',
                  priority: 2,
                  result_summary: '已追加写作段落并保留 provenance',
                  read_set: ['investigation.leads'],
                  write_set: ['writing.document'],
                },
              ]
            : [],
        },
      })
      return
    }
    if (url.includes('/events')) {
      await route.fulfill({ status: 200, json: { items: [] } })
      return
    }
    if (url.includes('/artifacts')) {
      const longTaskState = {
        contract_version: 'agent_long_task.stage.v1',
        current_stage: 'draft_output',
        completed_stages: ['plan', 'internal_evidence', 'gap_analysis', 'external_discovery', 'clue_trace'],
        next_actions: ['校验写作草稿并补监管来源'],
        stage_summaries: [
          { stage: 'plan', status: 'completed', summary: '已拆分长任务。', counts: {} },
          { stage: 'internal_evidence', status: 'completed', summary: '已完成内部资料检索，发现仍缺官方来源。', counts: { evidence_refs: 2, gap_list: 2 } },
          { stage: 'external_discovery', status: 'completed', summary: '已规划候选外部来源。', counts: { external_discovery_plan: 1 } },
          { stage: 'clue_trace', status: 'completed', summary: '已保存机器人商业化线索。', counts: { clue_refs: 1 } },
        ],
      }
      await route.fulfill({
        status: 200,
        json: {
          items: activeScenario === 'long-task'
            ? [
                {
                  artifact_id: 'artifact-long-task-state',
                  artifact_type: 'agent_long_task_state',
                  name: 'agent_long_task.state.json',
                  status: 'completed',
                  summary: 'long task stage state',
                  content: JSON.stringify(longTaskState),
                },
              ]
            : [],
        },
      })
      return
    }
    await route.fulfill({
      status: 200,
      json: {
        session: { session_id: `as-${activeScenario}`, current_phase: 'final', status: 'completed' },
        approvals: [],
      },
    })
  })
  await page.route(/\/api\/v1\/agent-approvals\/[^/]+\/resolve(?:\?|$)/, async (route) => {
    await route.fulfill({
      status: 200,
      json: { ...approval, status: 'rejected' },
    })
  })
  await page.route('**/api/v1/agent-chat/turn/stream', async (route) => {
    const payload = route.request().postDataJSON() as { message?: string }
    const message = String(payload.message || '')
    let controlToolName = ''
    if (message.includes('长任务')) activeScenario = 'long-task'
    else if (message.includes('项目里有什么数据')) activeScenario = 'project-data'
    else if (message.includes('来源库')) activeScenario = 'source-run'
    else if (message.includes('你是谁')) activeScenario = 'mobile'
    else if (message.includes('取消')) {
      activeScenario = 'control'
      controlToolName = 'task.cancel'
    } else if (message.includes('继续')) {
      activeScenario = 'control'
      controlToolName = 'task.continue'
    } else if (message.includes('重试')) {
      activeScenario = 'control'
      controlToolName = 'task.retry'
    }
    else activeScenario = 'conversation'
    if (activeScenario === 'source-run') expect((payload as Record<string, unknown>).require_high_risk_approval).toBe(false)

    const session = {
      session_id: `as-${activeScenario}`,
      current_phase: 'final',
      status: controlToolName === 'task.cancel' ? 'canceled' : 'completed',
    }
    const longTaskSourceResult = {
      candidate_urls: [
        {
          normalized_url: 'https://example.com/robot-market',
          domain: 'example.com',
          status: 'accepted',
          trust_score: 85,
          trust_level: 'high',
          trust_reasons: ['https', 'requested_domain_match'],
        },
      ],
    }
    const longTaskTraceResult = {
      contract_version: 'agent_investigation.trace.v1',
      artifact_name: 'robot-investigation.leads.json',
      focus_node_id: 'robot_market',
      counts: { nodes: 2, edges: 1, all_nodes: 3, all_edges: 2 },
      trace_summary: 'Expanded 2 node(s) and 1 edge(s) from focus node robot_market.',
      pending_questions: [{ text: '需要补充官方或监管来源' }],
    }
    const longTaskWritingResult = {
      doc_id: 77,
      operation: 'append',
      diff: { added_lines: 2, removed_lines: 0 },
      source_refs: ['https://example.com/robot-market'],
    }
    const longTaskStageResult = {
      contract_version: 'agent_long_task.stage.v1',
      artifact_name: 'agent_long_task.state.json',
      state: {
        current_stage: 'draft_output',
        completed_stages: ['plan', 'internal_evidence', 'gap_analysis', 'external_discovery', 'clue_trace'],
        next_actions: ['校验写作草稿并补监管来源'],
        stage_summaries: [
          { stage: 'plan', status: 'completed', summary: '已拆分长任务。', counts: {} },
          { stage: 'internal_evidence', status: 'completed', summary: '已完成内部资料检索，发现仍缺官方来源。', counts: { evidence_refs: 2, gap_list: 2 } },
          { stage: 'external_discovery', status: 'completed', summary: '已规划候选外部来源。', counts: { external_discovery_plan: 1 } },
          { stage: 'clue_trace', status: 'completed', summary: '已保存机器人商业化线索。', counts: { clue_refs: 1 } },
        ],
      },
    }
    const capabilityCalls = activeScenario === 'project-data'
      ? [
          { capability_id: 'project.summary.read', tool_name: 'project.summary.read', status: 'completed', summary: '读取项目结构化数据概览' },
          { capability_id: 'source_library.item.list', tool_name: 'source_library.item.list', status: 'completed', summary: '读取来源库条目' },
        ]
      : activeScenario === 'source-run'
        ? [{ capability_id: 'ingest.source_library.run', tool_name: 'ingest.source_library.run', status: 'completed', summary: '来源库补证任务已提交' }]
        : activeScenario === 'long-task'
          ? [
              { capability_id: 'agent_long_task.stage.update', tool_name: 'agent_long_task.stage.update', status: 'completed', summary: '阶段状态已保存', result: longTaskStageResult },
              { capability_id: 'source.discovery.plan', tool_name: 'source.discovery.plan', status: 'completed', summary: '候选来源已规划', result: longTaskSourceResult },
              { capability_id: 'agent_investigation.trace.read', tool_name: 'agent_investigation.trace.read', status: 'completed', summary: '线索 trace 已读取', result: longTaskTraceResult },
              { capability_id: 'writing.document.insert_paragraph', tool_name: 'writing.document.insert_paragraph', status: 'completed', summary: '写作草稿已更新', result: longTaskWritingResult },
            ]
          : activeScenario === 'control'
            ? [{ capability_id: controlToolName, tool_name: controlToolName, status: 'completed', summary: `${controlToolName} completed` }]
        : []
    const events = activeScenario === 'project-data'
      ? [
          buildAgentCoreEventSse('tool_call_requested', { seq: 1, payload: { capability_id: 'project.summary.read', tool_name: 'project.summary.read', status: 'requested' } }),
          buildAgentCoreEventSse('tool_result', { seq: 2, payload: { capability_id: 'project.summary.read', tool_name: 'project.summary.read', status: 'completed', summary: 'project data ready' } }),
          buildAgentCoreEventSse('tool_call_requested', { seq: 3, payload: { capability_id: 'source_library.item.list', tool_name: 'source_library.item.list', status: 'requested' } }),
        ]
      : activeScenario === 'source-run'
        ? [
            buildAgentCoreEventSse('tool_call_requested', { seq: 1, payload: { capability_id: 'ingest.source_library.run', tool_name: 'ingest.source_library.run', status: 'requested' } }),
            buildAgentCoreEventSse('tool_result', { seq: 2, payload: { capability_id: 'ingest.source_library.run', tool_name: 'ingest.source_library.run', status: 'completed', summary: 'source-library run submitted' } }),
          ]
        : activeScenario === 'long-task'
          ? [
              buildAgentCoreEventSse('turn_state', { seq: 1, payload: { phase: 'model_call', iteration: 1, max_iterations: 6, tool_call_count: 0, max_tool_calls: 8 } }),
              buildAgentCoreEventSse('tool_call_requested', { seq: 2, call_id: 'call-stage', payload: { tool_call: { tool_name: 'agent_long_task.stage.update', call_id: 'call-stage' }, status: 'requested' } }),
              buildAgentCoreEventSse('tool_result', { seq: 3, call_id: 'call-stage', payload: { tool_name: 'agent_long_task.stage.update', status: 'completed', model_summary: 'Updated long-task stage state', structured_content: longTaskStageResult } }),
              buildAgentCoreEventSse('tool_call_requested', { seq: 4, call_id: 'call-discovery', payload: { tool_call: { tool_name: 'source.discovery.plan', call_id: 'call-discovery' }, status: 'requested' } }),
              buildAgentCoreEventSse('tool_result', { seq: 5, call_id: 'call-discovery', payload: { tool_name: 'source.discovery.plan', status: 'completed', model_summary: 'Planned source candidates', structured_content: longTaskSourceResult } }),
              buildAgentCoreEventSse('tool_call_requested', { seq: 6, call_id: 'call-trace', payload: { tool_call: { tool_name: 'agent_investigation.trace.read', call_id: 'call-trace' }, status: 'requested' } }),
              buildAgentCoreEventSse('tool_result', { seq: 7, call_id: 'call-trace', payload: { tool_name: 'agent_investigation.trace.read', status: 'completed', model_summary: 'Read investigation trace', structured_content: longTaskTraceResult } }),
              buildAgentCoreEventSse('tool_call_requested', { seq: 8, call_id: 'call-writing', payload: { tool_call: { tool_name: 'writing.document.insert_paragraph', call_id: 'call-writing' }, status: 'requested' } }),
              buildAgentCoreEventSse('tool_result', { seq: 9, call_id: 'call-writing', payload: { tool_name: 'writing.document.insert_paragraph', status: 'completed', model_summary: 'Updated writing document 77', structured_content: longTaskWritingResult } }),
            ]
          : activeScenario === 'control'
            ? [
                buildAgentCoreEventSse('tool_call_requested', { seq: 1, call_id: `call-${controlToolName.replace('.', '-')}`, payload: { tool_call: { tool_name: controlToolName, call_id: `call-${controlToolName.replace('.', '-')}` }, status: 'requested' } }),
                buildAgentCoreEventSse('tool_result', { seq: 2, call_id: `call-${controlToolName.replace('.', '-')}`, payload: { tool_name: controlToolName, status: 'completed', model_summary: `${controlToolName} completed` } }),
              ]
        : []
    const tasks = activeScenario === 'long-task'
      ? [
          {
            task_id: 'task-research',
            subject: '候选来源调查',
            description: '规划机器人商业化候选来源',
            status: 'completed',
            phase: 'research',
            priority: 1,
            result_summary: '已记录 1 条高可信候选来源',
            read_set: ['source_library'],
            write_set: ['investigation.leads'],
            result_payload: { long_task_stage_state: longTaskStageResult.state },
          },
          {
            task_id: 'task-writing',
            subject: '写作工作台补段',
            description: '把调查结果写入工作台草稿',
            status: 'completed',
            phase: 'implementation',
            priority: 2,
            result_summary: '已追加写作段落并保留 provenance',
            read_set: ['investigation.leads'],
            write_set: ['writing.document'],
          },
        ]
      : []
    const finalAnswer =
      activeScenario === 'project-data'
        ? '我已读取项目结构化数据：当前有 documents、graph_nodes、resource_pool_urls 等数据集，并可继续按主题检索。'
        : activeScenario === 'source-run'
          ? '已通过 ingest.source_library.run 启动来源库补证任务，后续结果会进入项目任务与产物记录。'
          : activeScenario === 'long-task'
            ? '已完成一轮候选来源调查、线索记录和写作工作台更新。'
          : activeScenario === 'control' && controlToolName === 'task.cancel'
            ? '已取消当前会话。'
          : activeScenario === 'control' && controlToolName === 'task.continue'
            ? '已继续当前会话。'
          : activeScenario === 'control' && controlToolName === 'task.retry'
            ? '已重试失败任务。'
          : activeScenario === 'mobile'
            ? '我是项目内的 Agent，可以回答普通问题，也可以在需要时调用项目数据、来源库和写作工具。'
            : 'CAPM 的核心假设包括均值方差偏好、同质预期、无摩擦市场、可自由借贷和所有投资者持有市场组合。'
    const result = {
      final_answer: finalAnswer,
      agent_mode: 'core',
      contract_version: 'agent_core.turn.v1',
      runtime_variant: 'agent_core_v3',
      session,
      tasks,
      capability_calls: capabilityCalls,
      suggested_next_actions: [],
      approvals: [],
      stream: { url: `/api/v1/agent-sessions/${session.session_id}/stream` },
    }
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: `${events.join('\n')}${buildAgentCoreFinalSse(result)}`,
    })
  })
}

test.describe('agent chat user interaction', () => {
  test.beforeEach(async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })
    page.on('pageerror', (error) => consoleErrors.push(error.message))
    await installAgentChatScenarioMocks(page)
    await openAgentChat(page)
    test.info().annotations.push({ type: 'console-errors', description: consoleErrors.join('\n') || 'none' })
  })

  test('free conversation returns a streamed model answer without execution chrome', async ({ page }) => {
    const { answer, finalAnswer } = await sendAgentMessage(page, '解释一下 CAPM 的核心假设')
    const uiText = compactText(await answer.innerText())
    const runtimeSummary = page.locator('.agent-chat-runtime-panel summary')

    expect(compactText(finalAnswer).length).toBeGreaterThan(20)
    expect(uiText).toContain(compactText(finalAnswer).slice(0, 20))
    await expect(answer).not.toContainText('请补充你希望我')
    await expect(answer).not.toContainText('agent_batch.nl_command.submit')
    await expect(answer).not.toContainText('pending approval')
    await expect(answer).not.toContainText('parsed')
    await expect(runtimeSummary).toContainText('0 tools')
    await expect(answer.locator('.agent-chat-message-meta')).toHaveCount(0)
    await expect(answer.locator('.agent-chat-run-details')).toHaveCount(0)
  })

  test('project and source-library fact questions use read-only project tools', async ({ page }) => {
    const { answer, streamText } = await sendAgentMessage(page, '项目里有什么数据')
    const thread = page.locator('.agent-chat-thread')
    const toolList = answer.locator('.agent-chat-run-details')

    expect(streamText).toContain('event: agent_core.tool_call_requested')
    expect(streamText).toContain('project.summary.read')
    expect(streamText).toContain('source_library.item.list')
    await expect(toolList).toContainText('project.summary.read')
    await expect(toolList).toContainText('source_library.item.list')
    await expect(answer).not.toContainText('模型自由回答暂时')
    await expect(answer).not.toContainText('TimeoutExpired')
    await expect(answer).not.toContainText('agent_batch.nl_command.submit')
    await expect(answer.locator('.agent-chat-debug-details')).toHaveCount(0)
    await expect(thread).not.toContainText('pending approval')
  })

  test('explicit source-library execution stays on the frozen mainline without approval pause', async ({ page }) => {
    const { answer, streamText } = await sendAgentMessage(page, '用来源库 market.general.baseline 补一轮证据')

    expect(streamText).toContain('event: agent_core.tool_call_requested')
    expect(streamText).toContain('event: agent_core.tool_result')
    expect(streamText).not.toContain('event: agent_core.permission_requested')
    expect(streamText).toContain('ingest.source_library.run')
    await expect(answer.locator('.agent-chat-run-details')).toContainText('ingest.source_library.run')
    await expect(page.locator('.agent-chat-approval-callout')).toHaveCount(0)
    await expect(answer).not.toContainText('待审批')
  })

  test('long task shows split tasks, progressive tool events, source quality, and writing diff', async ({ page }) => {
    const { answer, streamText } = await sendAgentMessage(page, '执行一个长任务：调查机器人商业化并写入工作台')

    expect(streamText).toContain('event: agent_core.turn_state')
    expect(streamText).toContain('agent_long_task.stage.update')
    expect(streamText).toContain('source.discovery.plan')
    expect(streamText).toContain('agent_investigation.trace.read')
    expect(streamText).toContain('writing.document.insert_paragraph')
    await expect(answer.locator('.agent-chat-run-details')).toContainText('agent_long_task.stage.update')
    await expect(answer.locator('.agent-chat-run-details')).toContainText('source.discovery.plan')
    await expect(answer.locator('.agent-chat-run-details')).toContainText('agent_investigation.trace.read')
    await expect(answer.locator('.agent-chat-run-details')).toContainText('writing.document.insert_paragraph')

    await page.locator('.agent-chat-runtime-panel summary').click()
    await page.getByRole('button', { name: 'tasks' }).click()
    await expect(page.getByTestId('agent-chat-task-plan-card')).toHaveCount(2)
    await expect(page.getByTestId('agent-chat-task-plan-card').first()).toContainText('候选来源调查')
    await expect(page.getByTestId('agent-chat-task-plan-card').nth(1)).toContainText('写作工作台补段')
    await expect(page.getByTestId('agent-chat-long-task-stage-card')).toContainText('draft_output')
    await expect(page.getByTestId('agent-chat-long-task-stage-card')).toContainText('internal_evidence')
    await expect(page.getByTestId('agent-chat-long-task-stage-card')).toContainText('evidence 2 · gaps 2')

    await page.getByRole('button', { name: 'tools' }).click()
    await expect(page.getByTestId('agent-chat-progressive-tool-event')).toHaveCount(9)
    await expect(page.getByTestId('agent-chat-source-quality-card')).toContainText('score 85')
    await expect(page.getByTestId('agent-chat-investigation-trace-card')).toContainText('robot_market')
    await expect(page.getByTestId('agent-chat-investigation-trace-card')).toContainText('2 nodes · 1 edges')
    await expect(page.getByTestId('agent-chat-investigation-trace-card')).toContainText('需要补充官方或监管来源')
    await expect(page.getByTestId('agent-chat-diff-event')).toContainText('+2 / -0')

    await page.reload()
    await expect(page.getByTestId('agent-chat-active-session-title')).toBeVisible()
    await page.locator('.agent-chat-runtime-panel summary').click()
    await page.getByRole('button', { name: 'tasks' }).click()
    await expect(page.getByTestId('agent-chat-long-task-stage-card')).toContainText('draft_output')
    await expect(page.getByTestId('agent-chat-long-task-stage-card')).toContainText('校验写作草稿并补监管来源')
  })

  test('natural cancel renders the AgentCore control tool', async ({ page }) => {
    const turn = await sendAgentMessage(page, '取消当前会话')
    expect(turn.streamText).toContain('task.cancel')
    expect(turn.streamText).toContain('event: agent_core.tool_call_requested')
    await expect(turn.answer).toContainText('已取消当前会话')
    await turn.answer.locator('.agent-chat-run-details').evaluate((node) => { (node as HTMLDetailsElement).open = true })
    await expect(turn.answer.locator('.agent-chat-run-details')).toContainText('task.cancel')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('agent_batch.nl_command.submit')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('请补充你希望我')
  })

  test('natural continue renders the AgentCore control tool', async ({ page }) => {
    const turn = await sendAgentMessage(page, '继续')
    expect(turn.streamText).toContain('task.continue')
    expect(turn.streamText).toContain('event: agent_core.tool_call_requested')
    await expect(turn.answer).toContainText('已继续当前会话')
    await turn.answer.locator('.agent-chat-run-details').evaluate((node) => { (node as HTMLDetailsElement).open = true })
    await expect(turn.answer.locator('.agent-chat-run-details')).toContainText('task.continue')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('agent_batch.nl_command.submit')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('请补充你希望我')
  })

  test('natural retry renders the AgentCore control tool', async ({ page }) => {
    const turn = await sendAgentMessage(page, '重试失败任务')
    expect(turn.streamText).toContain('task.retry')
    expect(turn.streamText).toContain('event: agent_core.tool_call_requested')
    await expect(turn.answer).toContainText('已重试失败任务')
    await turn.answer.locator('.agent-chat-run-details').evaluate((node) => { (node as HTMLDetailsElement).open = true })
    await expect(turn.answer.locator('.agent-chat-run-details')).toContainText('task.retry')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('agent_batch.nl_command.submit')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('请补充你希望我')
  })

  test('mobile layout has no horizontal overflow after a chat turn', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openAgentChat(page)
    await sendAgentMessage(page, '你是谁')

    const overflow = await page.evaluate(() => {
      const selectors = ['.agent-chat-page', '.agent-chat-layout', '.agent-chat-thread', '.agent-chat-message-body']
      return selectors.map((selector) => {
        const element = document.querySelector(selector) as HTMLElement | null
        return {
          selector,
          scrollWidth: element?.scrollWidth || 0,
          clientWidth: element?.clientWidth || 0,
        }
      })
    })
    for (const item of overflow) {
      expect(item.scrollWidth, item.selector).toBeLessThanOrEqual(item.clientWidth + 1)
    }
  })
})

test.describe('agent chat formal behavior guards', () => {
  test('keeps default chat empty, renders capabilities as read-only, and surfaces backend failure as retryable error', async ({ page }) => {
    await page.route('**/api/v1/agent-chat/capabilities**', async (route) => {
      await route.fulfill({
        status: 200,
        json: {
          tool_pool: {
            groups: {
              core: [
                {
                  capability_id: 'project.summary.read',
                  approval_level: 'none',
                  concurrency_class: 'readonly',
                  implemented: true,
                  implementation_state: 'ready',
                  enabled: true,
                },
              ],
              deferred: [
                {
                  capability_id: 'ingest.source_library.run',
                  approval_level: 'approval_required',
                  concurrency_class: 'governed',
                  implemented: true,
                  implementation_state: 'ready',
                  enabled: true,
                },
              ],
              disabled: [
                {
                  capability_id: 'mcp.service.browser-playwright',
                  approval_level: 'none',
                  concurrency_class: 'readonly',
                  implemented: false,
                  implementation_state: 'not_configured',
                  service_status: 'not_configured',
                  configured: false,
                  reachable: false,
                  auth_ok: null,
                  enabled: false,
                  disabled_reason: 'Browser automation requires a concrete local MCP/browser server before it is executable.',
                },
                {
                  capability_id: 'mcp.service.external-search',
                  approval_level: 'none',
                  concurrency_class: 'readonly',
                  implemented: false,
                  implementation_state: 'not_mounted',
                  service_status: 'not_mounted',
                  configured: true,
                  reachable: false,
                  auth_ok: null,
                  enabled: false,
                  disabled_reason: 'Configured search MCP service has no mounted AgentCore tool.',
                },
              ],
            },
          },
        },
      })
    })
    await page.route('**/api/v1/agent-chat/turn**', async (route) => {
      const url = route.request().url()
      if (url.includes('/turn/stream')) {
        await route.fulfill({ status: 503, body: 'stream unavailable' })
        return
      }
      await route.fulfill({
        status: 500,
        json: { status: 'error', error: { code: 'AGENT_CHAT_DOWN', message: 'agent chat unavailable' } },
      })
    })

    await openAgentChat(page)
    await expect(page.locator('.agent-chat-session-item')).toHaveCount(1)
    await expect(page.locator('.agent-chat-session-list')).toContainText('新对话')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('Texas power market')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('approval binding 漏检')

    await page.locator('.agent-chat-runtime-panel summary').click()
    await expect(page.getByTestId('agent-chat-capability-item')).toHaveCount(2)
    await expect(page.locator('.agent-chat-capability-groups button')).toHaveCount(0)
    await expect(page.getByTestId('agent-chat-capability-item').first()).toContainText('ready')
    await expect(page.getByTestId('agent-chat-external-boundary-item')).toHaveCount(2)
    await expect(page.getByTestId('agent-chat-external-boundary-item').first()).toContainText('mcp.service.browser-playwright')
    await expect(page.getByTestId('agent-chat-external-boundary-item').first()).toContainText('not_configured')
    await expect(page.getByTestId('agent-chat-external-boundary-item').first()).toContainText('configured:no')
    await expect(page.getByTestId('agent-chat-external-boundary-item').nth(1)).toContainText('mcp.service.external-search')
    await expect(page.getByTestId('agent-chat-external-boundary-item').nth(1)).toContainText('not_mounted')

    await page.getByTestId('agent-chat-input').fill('后端失败时不要伪装成成功回复')
    await page.getByTestId('agent-chat-send-button').click()

    const errorMessage = page.locator('.agent-chat-message.is-error').last()
    await expect(errorMessage).toContainText('后端调用失败')
    await expect(page.getByTestId('agent-chat-retry-last')).toBeVisible()
    await expect(page.locator('.agent-chat-message.role-assistant')).toHaveCount(0)
    await expect(page.locator('.agent-chat-thread')).not.toContainText('fallback-local')
    await expect(page.locator('.agent-chat-thread')).not.toContainText('交互式 agent 已完成本轮处理')
    await expect(page.locator('.agent-chat-debug-details')).toHaveCount(0)
  })

  test('clear session detaches backend session before the next turn', async ({ page }) => {
    const turnPayloads: Array<Record<string, unknown>> = []
    await page.route('**/api/v1/agent-chat/capabilities**', async (route) => {
      await route.fulfill({
        status: 200,
        json: { tool_pool: { groups: { core: [], deferred: [] } } },
      })
    })
    await page.route('**/api/v1/agent-sessions/**', async (route) => {
      const url = route.request().url()
      if (url.includes('/events') || url.includes('/tasks') || url.includes('/artifacts')) {
        await route.fulfill({ status: 200, json: { items: [] } })
        return
      }
      await route.fulfill({
        status: 200,
        json: {
          session: { session_id: 'as-current', current_phase: 'conversation', status: 'completed' },
          approvals: [],
        },
      })
    })
    await page.route('**/api/v1/agent-chat/turn/stream', async (route) => {
      const payload = route.request().postDataJSON() as Record<string, unknown>
      turnPayloads.push(payload)
      const index = turnPayloads.length
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: buildAgentCoreFinalSse({
          final_answer: `mock answer ${index}`,
          agent_mode: 'core',
          contract_version: 'agent-core-v3',
          session: {
            session_id: `as-${index}`,
            current_phase: 'conversation',
            status: 'completed',
          },
          capability_calls: [],
          suggested_next_actions: [],
        }),
      })
    })

    await openAgentChat(page)
    await sendAgentMessage(page, '第一句')
    expect(turnPayloads[0]?.session_id ?? null).toBeNull()
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('mock answer 1')

    await page.getByTestId('agent-chat-clear-session').click()
    await expect(page.locator('.agent-chat-message.role-assistant')).toHaveCount(0)

    await sendAgentMessage(page, '第二句')
    expect(turnPayloads[1]?.session_id ?? null).toBeNull()
    await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText('mock answer 2')
  })
})
