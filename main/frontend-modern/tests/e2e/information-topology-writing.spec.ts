import { expect, test } from '@playwright/test'
import { buildE2eProjectKey, createE2eProject, deleteE2eProject, deleteE2eWritingDocument, setProjectKeyForPage } from './helpers/project-fixtures'

const PROJECT_KEY = buildE2eProjectKey('e2e_topology_writing')
const documentIds = new Set<number>()
type Envelope<T> = { status: string; data: T }

test.describe('information topology in writing workbench', () => {
  test.describe.configure({ mode: 'serial' })
  test.beforeAll(async ({ request }) => { await createE2eProject(request, PROJECT_KEY) })
  test.afterEach(async ({ request }) => {
    for (const id of documentIds) {
      await deleteE2eWritingDocument(request, PROJECT_KEY, id)
      documentIds.delete(id)
    }
  })
  test.afterAll(async ({ request }) => { await deleteE2eProject(request, PROJECT_KEY) })

  test('creates and reads back an outline without changing the writing body', async ({ page, request }) => {
    const body = '# Topology writing fixture\n\n正文由 writing 模块持有。'
    const createResponse = await request.post(`/api/v1/writing/documents?project_key=${PROJECT_KEY}`, {
      headers: { 'X-Project-Key': PROJECT_KEY },
      data: { title: 'Topology writing fixture', body_md: body, status: 'draft' },
    })
    expect(createResponse.ok()).toBeTruthy()
    const document = (await createResponse.json() as Envelope<{ id: number }>).data
    documentIds.add(document.id)

    await setProjectKeyForPage(page, PROJECT_KEY)
    await page.goto('/#writing-workbench.html')
    await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
    await page.getByTestId('writing-panel-documents').click()
    await page.locator(`[data-testid="writing-document-card"][data-document-id="${document.id}"]`).click()
    const panel = page.getByTestId('writing-report-topology')
    await expect(panel).toBeVisible()
    await expect(panel.getByText('尚无此文档的大纲')).toBeVisible()
    await panel.getByRole('button', { name: '创建大纲' }).click()
    await expect(panel.getByRole('status')).toContainText('已保存并读回')

    await panel.getByLabel('新增章节标题').fill('研究问题')
    await panel.getByRole('button', { name: '保存大纲' }).click()
    await expect(panel.getByLabel('第 1 节标题')).toHaveValue('研究问题')
    await expect(panel.getByRole('status')).toContainText('已保存并读回')

    const savedBody = await request.get(`/api/v1/writing/documents/${document.id}?project_key=${PROJECT_KEY}`, {
      headers: { 'X-Project-Key': PROJECT_KEY },
    })
    expect(savedBody.ok()).toBeTruthy()
    const persisted = (await savedBody.json() as Envelope<{ body_md: string }>).data
    expect(persisted.body_md).toBe(body)
    const outlineResponse = await request.post(`/api/v1/information-topology/topologies/read?project_key=${PROJECT_KEY}`, {
      headers: { 'X-Project-Key': PROJECT_KEY },
      data: { topology_ref: { module_id: 'report', namespace: 'outline', state_id: `writing-${document.id}` } },
    })
    expect(outlineResponse.ok()).toBeTruthy()
    const outline = (await outlineResponse.json() as Envelope<{ revision: number; topology: { elements: Array<{ ref: { ref: Record<string, string>; observed_revision: string }; attributes: Record<string, unknown>; endpoints: unknown[] }> } }>).data
    expect(outline.topology.elements.some((element) => element.attributes.title === '研究问题')).toBeTruthy()

    await panel.getByLabel('第 1 节标题').fill('过期编辑')
    const section = outline.topology.elements.find((element) => element.ref.ref.type_id === 'section')
    expect(section).toBeTruthy()
    const concurrent = await request.post(`/api/v1/information-topology/patches?project_key=${PROJECT_KEY}`, {
      headers: { 'X-Project-Key': PROJECT_KEY },
      data: { state_patches: [{
        target: { module_id: 'report', namespace: 'outline', state_id: `writing-${document.id}`, revision: outline.revision },
        base_revision: outline.revision,
        patch: [{ action: 'replace', ref: section!.ref, element: { ...section!, attributes: { ...section!.attributes, title: '并发编辑' } } }],
      }] },
    })
    expect(concurrent.ok()).toBeTruthy()
    await panel.getByRole('button', { name: '保存大纲' }).click()
    await expect(panel.getByRole('status')).toContainText('大纲版本冲突')
  })
})
