import { expect, type APIRequestContext, type Page } from '@playwright/test'

export function buildE2eProjectKey(prefix: string) {
  const worker = process.env.TEST_WORKER_INDEX || '0'
  return `${prefix}_${worker}_${Date.now().toString(36)}`.slice(0, 60)
}

export async function createE2eProject(request: APIRequestContext, projectKey: string) {
  const response = await request.post('/api/v1/projects', {
    data: {
      project_key: projectKey,
      name: `E2E ${projectKey}`,
      enabled: true,
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
}

export async function deleteE2eProject(request: APIRequestContext, projectKey: string) {
  const response = await request.delete(`/api/v1/projects/${encodeURIComponent(projectKey)}?hard=true`)
  if (![200, 404].includes(response.status())) {
    expect(response.ok(), await response.text()).toBeTruthy()
  }
}

export async function deleteE2eWritingDocument(request: APIRequestContext, projectKey: string, docId: number) {
  const response = await request.delete(`/api/v1/writing/documents/${docId}?project_key=${encodeURIComponent(projectKey)}`, {
    headers: { 'X-Project-Key': projectKey },
  })
  if (![200, 404].includes(response.status())) {
    expect(response.ok(), await response.text()).toBeTruthy()
  }
}

export async function setProjectKeyForPage(page: Page, projectKey: string) {
  await page.addInitScript((key) => {
    window.localStorage.clear()
    window.localStorage.setItem('market_project_key', key)
  }, projectKey)
}
