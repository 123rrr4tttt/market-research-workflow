import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import {
  buildE2eProjectKey,
  createE2eProject,
  deleteE2eProject,
  deleteE2eWritingDocument,
  setProjectKeyForPage,
} from './helpers/project-fixtures'

const PROJECT_KEY = buildE2eProjectKey('e2e_cross')
const createdDocumentIds = new Set<number>()

type ApiEnvelope<T> = {
  status: string
  data: T
}

type WritingDocument = {
  id: number
  title: string
  body_md: string
}

async function mockFastAgentAnswer(page: Page, finalAnswer: string) {
  await page.route('**/api/v1/agent-chat/turn/stream', async (route) => {
    const result = {
      runtime_variant: 'agent_core_v3',
      agent_mode: 'conversation',
      final_answer: finalAnswer,
      capability_calls: [],
      suggested_next_actions: ['打开写作工作台并保存为草稿'],
      session: {
        session_id: 'as-e2e-crossflow',
        current_phase: 'conversation',
        compat_mode: false,
      },
      contract_version: 'agent_chat.turn.v1',
    }
    await route.fulfill({
      status: 200,
      headers: {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-cache',
      },
      body: `event: agent_core.final_answer\ndata: ${JSON.stringify(result)}\n\n`,
    })
  })
}

async function openAgentChat(page: Page) {
  await setProjectKeyForPage(page, PROJECT_KEY)
  const response = await page.goto('/#agent-chat.html')
  if (response) expect(response.ok()).toBeTruthy()
  await expect(page.getByTestId('agent-chat-page')).toBeVisible()
  await expect(page.getByTestId('agent-chat-input')).toBeVisible()
}

test.describe('agent chat to writing workbench crossflow', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(async ({ request }) => {
    await createE2eProject(request, PROJECT_KEY)
  })

  test.afterEach(async ({ request }) => {
    for (const docId of Array.from(createdDocumentIds)) {
      await deleteE2eWritingDocument(request, PROJECT_KEY, docId)
      createdDocumentIds.delete(docId)
    }
  })

  test.afterAll(async ({ request }) => {
    await deleteE2eProject(request, PROJECT_KEY)
  })

  test.describe('mock crossflow with mocked agent stream', () => {
    test('keeps chat context while creating and verifying a writing draft', async ({ page, request }) => {
      const chatAnswer = '可以，我会把这次写作任务整理成工作台草稿。'
      const title = `Mock Crossflow Draft ${Date.now()}`
      const markdown = `## 跨页面实测\n\n来自 Agent Chat 的写作任务已经进入工作台。`

      await mockFastAgentAnswer(page, chatAnswer)
      await openAgentChat(page)
      await page.getByTestId('agent-chat-input').fill('帮我把机器人主题整理成一段写作草稿')
      await page.getByTestId('agent-chat-send-button').click()
      await expect(page.locator('.agent-chat-message.role-assistant').last()).toContainText(chatAnswer)

      await page.goto('/#writing-workbench.html')
      await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
      await page.getByTestId('writing-new-draft').click()
      await page.getByTestId('writing-title-input').fill(title)
      await page.getByTestId('writing-markdown-editor').fill(markdown)

      const saveResponse = page.waitForResponse((response) => {
        return response.url().includes('/api/v1/writing/documents') && response.request().method() === 'POST' && response.status() === 200
      })
      await page.getByTestId('writing-save').click()
      const response = await saveResponse
      const body = (await response.json()) as ApiEnvelope<WritingDocument>
      expect(body.status).toBe('ok')
      createdDocumentIds.add(body.data.id)
      expect(body.data.title).toBe(title)

      const readResponse = await request.get(
        `/api/v1/writing/documents/${body.data.id}?project_key=${encodeURIComponent(PROJECT_KEY)}`,
        { headers: { 'X-Project-Key': PROJECT_KEY } },
      )
      expect(readResponse.ok()).toBeTruthy()
      const readBody = (await readResponse.json()) as ApiEnvelope<WritingDocument>
      expect(readBody.data.body_md).toContain('跨页面实测')

      await page.goto('/#agent-chat.html')
      await expect(page.getByTestId('agent-chat-page')).toBeVisible()
      await expect(page.locator('.agent-chat-thread')).toContainText(chatAnswer)
    })
  })

  test.describe('live crossflow with real writing API readback', () => {
    test('opens a backend-created workbench draft after leaving agent chat', async ({ page, request }) => {
      const title = `Live Crossflow Draft ${Date.now()}`
      const marker = `live-crossflow-marker-${Date.now()}`
      const markdown = `## Live Crossflow\n\n${marker}`

      const createResponse = await request.post('/api/v1/writing/documents', {
        headers: { 'X-Project-Key': PROJECT_KEY },
        data: {
          project_key: PROJECT_KEY,
          title,
          body_md: markdown,
          metadata_json: { source: 'e2e-live-crossflow', project_key: PROJECT_KEY },
        },
      })
      if (!createResponse.ok()) expect(createResponse.ok(), await createResponse.text()).toBeTruthy()
      const created = (await createResponse.json()) as ApiEnvelope<WritingDocument>
      expect(created.status).toBe('ok')
      createdDocumentIds.add(created.data.id)

      await openAgentChat(page)
      await expect(page.getByTestId('agent-chat-page')).toBeVisible()

      await page.goto('/#writing-workbench.html')
      await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
      const card = page.getByTestId('writing-document-card').filter({ hasText: title }).first()
      await expect(card).toBeVisible()
      await expect(page.getByTestId('writing-title-input')).toHaveValue(title)
      await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(new RegExp(marker))

      const readResponse = await request.get(
        `/api/v1/writing/documents/${created.data.id}?project_key=${encodeURIComponent(PROJECT_KEY)}`,
        { headers: { 'X-Project-Key': PROJECT_KEY } },
      )
      if (!readResponse.ok()) expect(readResponse.ok(), await readResponse.text()).toBeTruthy()
      const readBody = (await readResponse.json()) as ApiEnvelope<WritingDocument>
      expect(readBody.data.title).toBe(title)
      expect(readBody.data.body_md).toContain(marker)
    })
  })
})
