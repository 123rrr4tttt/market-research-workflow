import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import {
  buildE2eProjectKey,
  createE2eProject,
  deleteE2eProject,
  deleteE2eWritingDocument,
  setProjectKeyForPage,
} from './helpers/project-fixtures'

const PROJECT_KEY = buildE2eProjectKey('e2e_writing')
const createdDocumentIds = new Set<number>()

type ApiEnvelope<T> = {
  status: string
  data: T
}

type WritingDocument = {
  id: number
  title: string
  body_md: string
  version: number
  etag: string
  metadata_json?: Record<string, unknown>
}

async function createWritingDocument(
  request: APIRequestContext,
  payload: Record<string, unknown>,
): Promise<WritingDocument> {
  const response = await request.post(`/api/v1/writing/documents?project_key=${PROJECT_KEY}`, {
    headers: { 'X-Project-Key': PROJECT_KEY },
    data: {
      status: 'draft',
      ...payload,
    },
  })
  expect(response.ok()).toBeTruthy()
  const body = (await response.json()) as ApiEnvelope<WritingDocument>
  expect(body.status).toBe('ok')
  createdDocumentIds.add(body.data.id)
  return body.data
}

async function getWritingDocument(request: APIRequestContext, docId: number): Promise<WritingDocument> {
  const response = await request.get(`/api/v1/writing/documents/${docId}?project_key=${PROJECT_KEY}`, {
    headers: { 'X-Project-Key': PROJECT_KEY },
  })
  expect(response.ok()).toBeTruthy()
  const body = (await response.json()) as ApiEnvelope<WritingDocument>
  expect(body.status).toBe('ok')
  return body.data
}

async function openWritingWorkbench(page: Page) {
  await setProjectKeyForPage(page, PROJECT_KEY)
  const response = await page.goto('/#writing-workbench.html')
  if (response) expect(response.ok()).toBeTruthy()
  await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
  await expect(page.getByTestId('writing-workbench-toolbar')).toBeVisible()
  await expect(page.getByTestId('writing-markdown-editor')).toBeVisible()
}

async function selectDocument(page: Page, docId: number) {
  const titleInput = page.getByTestId('writing-title-input')
  await page.getByTestId('writing-panel-documents').click()
  const card = page.locator(`[data-testid="writing-document-card"][data-document-id="${docId}"]`)
  await expect(card).toBeVisible({ timeout: 15000 })
  await card.click()
  await expect(titleInput).not.toHaveValue('')
}

test.describe('writing workbench user interaction', () => {
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

  test('creates, edits, saves, and previews a writing document', async ({ page }) => {
    await openWritingWorkbench(page)

    const title = `E2E Writing Draft ${Date.now()}`
    const markdown = `## 研究背景\n\n这是一段用于实测矩阵的正文。\n\n- 结构化数据\n- Agent 写作`

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
    await expect(page.getByTestId('writing-title-input')).toHaveValue(title)
    await expect(page.getByText(/文档已创建|正文已保存/)).toBeVisible()

    await page.getByTestId('writing-panel-llm').click()
    const codexRouteLink = page.getByTestId('writing-agent-route-link')
    await expect(codexRouteLink).toBeVisible()
    await expect(codexRouteLink).toHaveAttribute('href', '#/workbench/agent')

    await page.getByTestId('writing-mode-split').click()
    await expect(page.getByTestId('writing-editor-pane')).toBeVisible()
    await expect(page.getByTestId('writing-preview-pane')).toBeVisible()
    await expect(page.getByTestId('writing-preview-pane')).toContainText('研究背景')
    await expect(page.getByTestId('writing-preview-pane')).toContainText('Agent 写作')
  })

  test('reviews an agent-written paragraph with locate and accept controls', async ({ page, request }) => {
    const insertedText = 'Agent inserted paragraph for e2e review.'
    const document = await createWritingDocument(request, {
      title: `E2E Agent Update ${Date.now()}`,
      body_md: `# Agent Review\n\n${insertedText}\n\nBase paragraph.`,
      metadata_json: {
        source: 'e2e-writing-workbench',
        agent_updates: [
          {
            id: 'agent-update-e2e',
            call_id: 'call-agent-e2e',
            tool_name: 'writing.document.insert_paragraph',
            actor: 'agent_core',
            operation: 'append',
            created_at: '2026-05-11T00:00:00Z',
            summary: insertedText,
            old_version: 1,
            new_version: 2,
            inserted_text: insertedText,
            review_status: 'pending',
            source_refs: ['doc:e2e'],
            provenance: { scenario: 'writing-workbench-e2e' },
            locator: {
              anchor_id: 'agent-update-e2e',
              anchor_text: insertedText,
              anchor_heading: 'Agent Review',
              anchor_line: 3,
            },
          },
        ],
      },
    })

    await openWritingWorkbench(page)
    await selectDocument(page, document.id)
    await expect(page.getByTestId('writing-title-input')).toHaveValue(document.title)

    const anchorCard = page.getByTestId('writing-agent-anchor-card')
    await expect(page.getByTestId('writing-agent-collab-rail')).toBeVisible()
    await expect(anchorCard).toContainText(insertedText)
    await expect(anchorCard).toContainText('L3')
    await expect(anchorCard).toContainText('待处理')

    await page.getByTestId('writing-agent-anchor-locate').click()
    await expect.poll(async () => {
      return page.evaluate(() => {
        const textarea = document.querySelector<HTMLTextAreaElement>('[data-testid="writing-markdown-editor"]')
        if (!textarea) return ''
        return textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)
      })
    }).toBe(insertedText)

    await page.getByTestId('writing-panel-agent-updates').click()
    const updateCard = page.getByTestId('writing-agent-update-card')
    await expect(updateCard).toContainText(insertedText)
    await expect(updateCard).toContainText('待处理')

    await page.getByTestId('writing-agent-update-diff').click()
    const diffPanel = page.getByTestId('writing-agent-update-diff-panel')
    await expect(diffPanel).toContainText('v1 -> v2')
    await expect(diffPanel).toContainText(insertedText)
    await expect(diffPanel).toContainText('refs: doc:e2e')
    await expect(diffPanel).toContainText('provenance: scenario')

    await page.getByTestId('writing-agent-update-locate').click()
    await expect.poll(async () => {
      return page.evaluate(() => {
        const textarea = document.querySelector<HTMLTextAreaElement>('[data-testid="writing-markdown-editor"]')
        if (!textarea) return ''
        return textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)
      })
    }).toBe(insertedText)

    const patchResponse = page.waitForResponse((response) => {
      return response.url().includes(`/api/v1/writing/documents/${document.id}`) && response.request().method() === 'PATCH' && response.status() === 200
    })
    await page.getByTestId('writing-agent-update-accept').click()
    await patchResponse

    await expect(updateCard).toContainText('已采纳')
    const refreshed = await getWritingDocument(request, document.id)
    const updates = refreshed.metadata_json?.agent_updates as Array<Record<string, unknown>>
    expect(updates?.[0]?.review_status).toBe('accepted')
  })

  test('locates an agent range edit by explicit range metadata', async ({ page, request }) => {
    const repeatedText = 'Agent range paragraph repeated.'
    const body = `# Range Review\n\n${repeatedText}\n\nBase paragraph.\n\n${repeatedText}\n\nTail paragraph.`
    const secondStart = body.lastIndexOf(repeatedText)
    const document = await createWritingDocument(request, {
      title: `E2E Agent Range ${Date.now()}`,
      body_md: body,
      metadata_json: {
        source: 'e2e-writing-workbench',
        agent_updates: [
          {
            id: 'agent-range-e2e',
            call_id: 'call-agent-range-e2e',
            tool_name: 'writing.document.insert_paragraph',
            actor: 'agent_core',
            operation: 'replace_range',
            created_at: '2026-05-13T00:00:00Z',
            summary: repeatedText,
            old_version: 1,
            new_version: 2,
            inserted_text: repeatedText,
            review_status: 'pending',
            source_refs: ['range:e2e'],
            provenance: {
              selection_snapshot: {
                selected_text: 'old selected paragraph',
                start: secondStart,
                end: secondStart + repeatedText.length,
              },
            },
            locator: {
              anchor_id: 'agent-range-e2e',
              anchor_text: '',
              anchor_heading: 'Range Review',
              range_start: secondStart,
              range_end: secondStart + repeatedText.length,
            },
          },
        ],
      },
    })

    await openWritingWorkbench(page)
    await selectDocument(page, document.id)

    await page.getByTestId('writing-agent-anchor-locate').click()
    await expect.poll(async () => {
      return page.evaluate(() => {
        const textarea = document.querySelector<HTMLTextAreaElement>('[data-testid="writing-markdown-editor"]')
        if (!textarea) return null
        return {
          start: textarea.selectionStart,
          end: textarea.selectionEnd,
          text: textarea.value.slice(textarea.selectionStart, textarea.selectionEnd),
        }
      })
    }).toEqual({ start: secondStart, end: secondStart + repeatedText.length, text: repeatedText })
  })

  test('mobile writing layout keeps the toolbar and canvas inside the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openWritingWorkbench(page)

    const overflow = await page.evaluate(() => {
      const selectors = [
        '.writing-workbench-page',
        '.writing-canvas-shell',
        '.writing-floating-toolbar',
        '.writing-canvas-stage',
        '.writing-editor__textarea',
      ]
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
