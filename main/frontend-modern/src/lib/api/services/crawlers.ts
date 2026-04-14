import { asList, httpGet, httpPost } from '../client'
import { endpoints } from '../endpoints'
import type {
  CrawlerDeployRunItem,
  CrawlerProjectDeployPayload,
  CrawlerProjectImportPayload,
  CrawlerProjectItem,
  CrawlerProjectRollbackPayload,
} from '../../types'

export async function fetchCrawlerProjects() {
  const data = await httpGet<CrawlerProjectItem[] | { items?: CrawlerProjectItem[] }>(endpoints.crawler.projects)
  return asList<CrawlerProjectItem>(data)
}

export async function fetchCrawlerProjectDetail(crawlerProjectKey: string) {
  return httpGet<CrawlerProjectItem>(endpoints.crawler.projectByKey(crawlerProjectKey))
}

export async function importCrawlerProject(payload: CrawlerProjectImportPayload) {
  return httpPost<CrawlerProjectItem & { task_id?: string }>(endpoints.crawler.importProject, {
    project_key: payload.project_key ?? null,
    name: payload.name ?? null,
    repo_url: payload.repo_url,
    branch: payload.branch ?? null,
    provider_hint: payload.provider_hint ?? null,
    description: payload.description ?? null,
    enable_now: payload.enable_now ?? true,
  })
}

export async function deployCrawlerProject(crawlerProjectKey: string, payload: CrawlerProjectDeployPayload = {}) {
  const data = await httpPost<
    CrawlerDeployRunItem & { task_id?: string; run?: CrawlerDeployRunItem } & Record<string, unknown>
  >(endpoints.crawler.deploy(crawlerProjectKey), {
    requested_version: payload.requested_version ?? null,
    planner_mode: payload.planner_mode ?? 'heuristic',
    async_mode: payload.async_mode ?? true,
  })
  if (data && typeof data === 'object' && 'run' in data && data.run && typeof data.run === 'object') {
    return { ...(data.run as CrawlerDeployRunItem), task_id: (data as { task_id?: string }).task_id }
  }
  return data as CrawlerDeployRunItem & { task_id?: string }
}

export async function rollbackCrawlerProject(crawlerProjectKey: string, payload: CrawlerProjectRollbackPayload = {}) {
  const data = await httpPost<
    CrawlerDeployRunItem & { task_id?: string; run?: CrawlerDeployRunItem } & Record<string, unknown>
  >(endpoints.crawler.rollback(crawlerProjectKey), {
    to_version: payload.to_version ?? null,
    planner_mode: payload.planner_mode ?? 'heuristic',
    async_mode: payload.async_mode ?? true,
  })
  if (data && typeof data === 'object' && 'run' in data && data.run && typeof data.run === 'object') {
    return { ...(data.run as CrawlerDeployRunItem), task_id: (data as { task_id?: string }).task_id }
  }
  return data as CrawlerDeployRunItem & { task_id?: string }
}

export async function fetchCrawlerDeployRuns(params?: { crawlerProjectKey?: string; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.limit) query.set('limit', String(params.limit))
  const base = params?.crawlerProjectKey
    ? endpoints.crawler.deployRunsByProject(params.crawlerProjectKey)
    : endpoints.crawler.deployRuns
  const target = query.toString() ? `${base}?${query.toString()}` : base
  const data = await httpGet<CrawlerDeployRunItem[] | { items?: CrawlerDeployRunItem[] }>(target)
  return asList<CrawlerDeployRunItem>(data)
}

export async function fetchCrawlerDeployRunDetail(runId: string | number) {
  return httpGet<CrawlerDeployRunItem>(endpoints.crawler.deployRunById(runId))
}
