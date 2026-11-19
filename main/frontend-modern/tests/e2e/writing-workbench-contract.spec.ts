import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { setProjectKeyForPage } from './helpers/project-fixtures'

type ApiEnvelope<T> = {
  status: 'ok'
  data: T
}

function documentPayload(docId: number, version: number) {
  return {
    doc_id: docId,
    project_key: 'demo-contract',
    title: docId === 501 ? 'Contract document' : 'Created document',
    body_md: '# Contract document\n\nCurrent body.',
    status: 'draft',
    version,
    etag: `etag-${docId}-${version}`,
    metadata_json: {},
  }
}

function fulfillJson(route: Route, status: number, payload: unknown) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
}

async function openWorkbench(page: Page) {
  await setProjectKeyForPage(page, 'demo-contract')
  const response = await page.goto('/#/workbench/writing')
  expect(response).toBeTruthy()
  await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
  await expect(page.getByTestId('writing-markdown-editor')).toBeVisible()
}

async function mockAdjacentWritingApis(page: Page) {
  await page.route('**/api/v1/writing/documents/*/citations*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { items: [] } }))
  await page.route('**/api/v1/writing/templates*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { items: [] } }))
}

test('create readback uses the persisted doc_id as the workbench document identity', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  await page.route('**/api/v1/writing/documents/502?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: documentPayload(502, 1) }))
  const createRoute = page.waitForRequest((request) =>
    request.method() === 'POST' && request.url().includes('/api/v1/writing/documents?'))
  await page.route('**/api/v1/writing/documents?*', async (route) => {
    if (route.request().method() !== 'POST') {
      await fulfillJson(route, 200, { status: 'ok', data: { items: [] } })
      return
    }
    await fulfillJson(route, 200, { status: 'ok', data: documentPayload(502, 1) })
  })

  await openWorkbench(page)
  await page.getByTestId('writing-new-draft').click()
  await page.getByTestId('writing-title-input').fill('Created document')
  await page.getByTestId('writing-markdown-editor').fill('# Created document\n\nNew body.')
  await page.getByTestId('writing-save').click()

  const request = await createRoute
  expect(request.postDataJSON()).toMatchObject({ title: 'Created document' })
  await expect(page.getByTestId('writing-conflict-panel')).toHaveCount(0)
  await expect(page.getByTestId('writing-workbench-toolbar')).toContainText('doc 502')
})

test('update sends both version locks and renders the 409 doc_id snapshot', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  await page.route('**/api/v1/writing/documents?*', (route) =>
    fulfillJson(route, 200, {
      status: 'ok',
      data: { items: [documentPayload(501, 4)] },
    }))
  const patchRoute = page.waitForRequest((request) =>
    request.method() === 'PATCH' && request.url().includes('/api/v1/writing/documents/501?'))
  await page.route('**/api/v1/writing/documents/501?*', async (route) => {
    if (route.request().method() !== 'PATCH') {
      await fulfillJson(route, 200, { status: 'ok', data: documentPayload(501, 4) })
      return
    }
    await fulfillJson(route, 409, {
      status: 'error',
      data: null,
      error: {
        code: 'INVALID_INPUT',
        message: 'writing document version conflict',
        details: {
          conflict_code: 'VERSION_CONFLICT',
          expected_version: 4,
          current_version: 5,
          server_snapshot: documentPayload(501, 5),
        },
      },
      meta: { project_key: 'demo-contract' },
    })
  })

  await openWorkbench(page)
  await page.getByTestId('writing-markdown-editor').fill('# Contract document\n\nLocal edit.')
  await page.getByTestId('writing-save').click()

  const request = await patchRoute
  expect(request.postDataJSON()).toMatchObject({ base_version: 4 })
  expect(request.headers()['if-match']).toBe('etag-501-4')
  const conflict = page.getByTestId('writing-conflict-panel')
  await expect(conflict).toBeVisible()
  await expect(conflict.getByTestId('writing-conflict-doc-id')).toHaveText('501')
  await expect(conflict.getByTestId('writing-conflict-version')).toHaveText('5')
})

test('dirty draft keeps its edit lock across a server-version poll and a 409', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  await page.route('**/api/v1/writing/documents?*', (route) =>
    fulfillJson(route, 200, {
      status: 'ok',
      data: { items: [documentPayload(501, 4)] },
    }))

  let serverDocument = documentPayload(501, 4)
  const autosaveBases: number[] = []
  await page.route('**/api/v1/writing/documents/501/draft?*', (route) => {
    const payload = route.request().postDataJSON() as { base_version?: number; draft_body_md?: string }
    autosaveBases.push(Number(payload.base_version))
    return fulfillJson(route, 200, {
      status: 'ok',
      data: {
        id: 601,
        doc_id: 501,
        project_key: 'demo-contract',
        draft_body_md: String(payload.draft_body_md || ''),
        base_version: payload.base_version ?? null,
        autosave_token: 'writing-501',
      },
    })
  })
  await page.route('**/api/v1/writing/documents/501?*', async (route) => {
    if (route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON() as { base_version?: number; draft_body_md?: string }
      expect(payload.base_version).toBe(4)
      expect(route.request().headers()['if-match']).toBe('etag-501-4')
      await fulfillJson(route, 409, {
        status: 'error',
        data: null,
        error: {
          code: 'INVALID_INPUT',
          message: 'writing document version conflict',
          details: {
            conflict_code: 'VERSION_CONFLICT',
            expected_version: 4,
            current_version: 5,
            server_snapshot: serverDocument,
          },
        },
      })
      return
    }
    await fulfillJson(route, 200, { status: 'ok', data: serverDocument })
  })

  await openWorkbench(page)
  const localBody = '# Contract document\n\nDirty body before external write.'
  await page.getByTestId('writing-markdown-editor').fill(localBody)
  serverDocument = documentPayload(501, 5)

  await page.waitForResponse(async (response) => {
    if (!response.url().includes('/api/v1/writing/documents/501?') || response.request().method() !== 'GET') {
      return false
    }
    try {
      const body = await response.json() as ApiEnvelope<{ version: number }>
      return body.data?.version === 5
    } catch {
      return false
    }
  }, { timeout: 7000 })

  await page.getByTestId('writing-save').click()
  const conflict = page.getByTestId('writing-conflict-panel')
  await expect(conflict).toBeVisible()
  await expect(conflict.getByTestId('writing-conflict-doc-id')).toHaveText('501')
  await expect(conflict.getByTestId('writing-conflict-version')).toHaveText('5')
  await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(localBody)

  await page.getByTestId('writing-markdown-editor').fill(`${localBody}\n\nStill local after conflict.`)
  await expect(page.getByTestId('writing-markdown-editor')).toHaveValue(
    /Dirty body before external write\.\n\nStill local after conflict\./,
  )
  expect(autosaveBases.length).toBeGreaterThanOrEqual(1)
  expect(autosaveBases.every((baseVersion) => baseVersion === 4)).toBe(true)
})

test('save response preserves edits made while the submitted snapshot was in flight', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  let serverDocument = documentPayload(501, 4)
  await page.route('**/api/v1/writing/documents?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { items: [serverDocument] } }))
  await page.route('**/api/v1/writing/documents/501/draft?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { id: 601, doc_id: 501 } }))
  let releaseSave: () => void = () => { throw new Error('save has not started') }
  const saveRelease = new Promise<void>((resolve) => { releaseSave = resolve })
  let patchCount = 0
  await page.route('**/api/v1/writing/documents/501?*', async (route) => {
    if (route.request().method() !== 'PATCH') {
      await fulfillJson(route, 200, { status: 'ok', data: serverDocument })
      return
    }
    const payload = route.request().postDataJSON() as { body_md: string; base_version: number }
    patchCount += 1
    expect(payload.base_version).toBe(patchCount === 1 ? 4 : 5)
    expect(route.request().headers()['if-match']).toBe(`etag-501-${patchCount === 1 ? 4 : 5}`)
    if (patchCount === 1) await saveRelease
    serverDocument = { ...documentPayload(501, patchCount + 4), body_md: payload.body_md }
    await fulfillJson(route, 200, { status: 'ok', data: serverDocument })
  })
  await openWorkbench(page)
  const editor = page.getByTestId('writing-markdown-editor')
  await editor.fill('Submitted snapshot')
  const started = page.waitForRequest((request) => request.method() === 'PATCH')
  await page.getByTestId('writing-save').click()
  await started
  await editor.fill('Later local edit')
  releaseSave()
  await expect(page.getByTestId('writing-save')).toBeEnabled()
  await expect(editor).toHaveValue('Later local edit')
  await page.getByTestId('writing-save').click()
  await expect.poll(() => patchCount).toBe(2)
  await expect.poll(() => serverDocument.body_md).toBe('Later local edit')
  await expect(page.getByTestId('writing-conflict-panel')).toHaveCount(0)
})

test('creation response transports later local edits to the persisted document identity', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  let releaseCreate: () => void = () => {}
  const release = new Promise<void>((resolve) => { releaseCreate = resolve })
  let saved = documentPayload(502, 1)
  let created = false
  await page.route('**/api/v1/writing/documents?*', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as { body_md: string }
      await release
      saved = { ...saved, body_md: payload.body_md }
      created = true
      await fulfillJson(route, 200, { status: 'ok', data: saved })
    } else {
      await fulfillJson(route, 200, { status: 'ok', data: { items: created ? [saved] : [] } })
    }
  })
  await page.route('**/api/v1/writing/documents/502?*', async (route) => {
    if (route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON() as { body_md: string; base_version: number }
      expect(payload.base_version).toBe(1)
      expect(route.request().headers()['if-match']).toBe('etag-502-1')
      saved = { ...saved, body_md: payload.body_md, version: 2 }
    }
    await fulfillJson(route, 200, { status: 'ok', data: saved })
  })
  await openWorkbench(page)
  await page.getByTestId('writing-new-draft').click()
  const editor = page.getByTestId('writing-markdown-editor')
  await editor.fill('Initial creation snapshot')
  const started = page.waitForRequest((request) => request.method() === 'POST' && request.url().includes('/writing/documents?'))
  await page.getByTestId('writing-save').click()
  await started
  await editor.fill('New edit during creation')
  releaseCreate()
  await expect(page.getByTestId('writing-workbench-toolbar')).toContainText('doc 502')
  await expect(editor).toHaveValue('New edit during creation')
  await page.getByTestId('writing-save').click()
  await expect.poll(() => saved.body_md).toBe('New edit during creation')
})

test('agent review response leaves concurrent local edits under their original conflict lock', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  const update = {
    id: 'review-race', call_id: 'review-call', tool_name: 'writing.document.insert_paragraph',
    actor: 'agent_core', operation: 'append', created_at: '2026-05-11T00:00:00Z',
    summary: 'Current body.', old_version: 3, new_version: 4, inserted_text: 'Current body.',
    review_status: 'pending', source_refs: [], provenance: {},
  }
  let saved = { ...documentPayload(501, 4), metadata_json: { agent_updates: [update] } }
  let releaseReview: () => void = () => {}
  const release = new Promise<void>((resolve) => { releaseReview = resolve })
  await page.route('**/api/v1/writing/documents?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { items: [saved] } }))
  await page.route('**/api/v1/writing/documents/501/draft?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { id: 601, doc_id: 501 } }))
  await page.route('**/api/v1/writing/documents/501?*', async (route) => {
    if (route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON() as { metadata_json?: typeof saved.metadata_json; base_version: number }
      if (payload.metadata_json) {
        await release
        saved = { ...saved, version: 5, etag: 'etag-501-5', metadata_json: payload.metadata_json }
      } else {
        expect(payload.base_version).toBe(4)
        expect(route.request().headers()['if-match']).toBe('etag-501-4')
        await fulfillJson(route, 409, { status: 'error', error: { code: 'INVALID_INPUT', message: 'conflict', details: {
          conflict_code: 'VERSION_CONFLICT', expected_version: 4, current_version: 5, server_snapshot: saved,
        } } })
        return
      }
    }
    await fulfillJson(route, 200, { status: 'ok', data: saved })
  })
  await openWorkbench(page)
  await page.getByTestId('writing-panel-agent-updates').click()
  const started = page.waitForRequest((request) => request.method() === 'PATCH')
  await page.getByTestId('writing-agent-update-accept').click()
  await started
  const editor = page.getByTestId('writing-markdown-editor')
  await editor.fill('Concurrent edit during review')
  releaseReview()
  await expect(page.getByTestId('writing-agent-update-card')).toContainText('已采纳')
  await expect(editor).toHaveValue('Concurrent edit during review')
  await page.getByTestId('writing-save').click()
  await expect(page.getByTestId('writing-conflict-panel')).toBeVisible()
  await expect(editor).toHaveValue('Concurrent edit during review')
})

test('switching projects replaces project-local drafts even when document ids coincide', async ({ page }) => {
  await mockAdjacentWritingApis(page)
  await page.route('**/api/v1/projects**', (route) => fulfillJson(route, 200, {
    status: 'ok', data: [
      { project_key: 'demo_contract', name: 'Project A', enabled: true },
      { project_key: 'other_project', name: 'Project B', enabled: true },
    ],
  }))
  const documentForRequest = (route: Route) => {
    const project = new URL(route.request().url()).searchParams.get('project_key')
    return { ...documentPayload(501, 4), project_key: project, body_md: `Persisted ${project}` }
  }
  await page.route('**/api/v1/writing/documents?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: { items: [documentForRequest(route)] } }))
  await page.route('**/api/v1/writing/documents/501?*', (route) =>
    fulfillJson(route, 200, { status: 'ok', data: documentForRequest(route) }))
  await openWorkbench(page)
  const editor = page.getByTestId('writing-markdown-editor')
  await expect(editor).toHaveValue('Persisted demo_contract')
  await editor.fill('Project A unsaved body')
  await page.getByRole('combobox', { name: '目标项目' }).selectOption('other_project')
  await page.getByRole('button', { name: '切换', exact: true }).click()
  await expect(editor).toHaveValue('Persisted other_project')
  await expect(page.getByTestId('writing-workbench-toolbar')).toContainText('doc 501')
})
