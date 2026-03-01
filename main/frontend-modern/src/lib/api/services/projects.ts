import { asList, httpDelete, httpGet, httpPatch, httpPost, normalizeProjectKey, setProjectKey } from '../client'
import { endpoints } from '../endpoints'
import type { ProjectItem } from '../../types'

export async function fetchProjects() {
  const data = await httpGet<ProjectItem[] | { items?: ProjectItem[] }>(endpoints.projects.root)
  return asList<ProjectItem>(data)
}

export async function activateProjectByKey(projectKey: string) {
  const key = normalizeProjectKey(projectKey)
  await httpPost(endpoints.projects.activate(key), null)
  setProjectKey(key)
  return key
}

export async function createProjectRecord(payload: { project_key: string; name: string; enabled?: boolean }) {
  return httpPost<{ id?: number; schema_name?: string }>(endpoints.projects.root, {
    ...payload,
    enabled: payload.enabled ?? true,
  })
}

export async function updateProjectRecord(projectKey: string, payload: { name?: string; enabled?: boolean }) {
  return httpPatch<{ project_key: string }>(endpoints.projects.byKey(projectKey), payload)
}

export async function archiveProjectRecord(projectKey: string) {
  return httpPost<{ archived: boolean }>(endpoints.projects.archive(projectKey), null)
}

export async function restoreProjectRecord(projectKey: string) {
  return httpPost<{ archived: boolean }>(endpoints.projects.restore(projectKey), null)
}

export async function deleteProjectRecord(projectKey: string, hard = false) {
  return httpDelete<{ deleted: boolean }>(`${endpoints.projects.byKey(projectKey)}?hard=${hard ? 'true' : 'false'}`)
}
