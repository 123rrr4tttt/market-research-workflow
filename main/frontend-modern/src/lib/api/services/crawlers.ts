import { asList, httpGet, httpPost } from '../client'
import { endpoints } from '../endpoints'
import type {
  CrawlerDeployRunItem,
  CrawlerProjectDeployPayload,
  CrawlerProjectImportPayload,
  CrawlerProjectItem,
} from '../../types'

export type CrawlerAgentModule = {
  id: string
  title: string
  status: 'registered' | 'unavailable'
  available: boolean
  reason?: string | null
  cell_ref: string
  targets: Array<{ id: string; label: string }>
  methods: Array<{ id: string; title: string }>
  operations: Array<{ id: string; title: string; effect: string }>
}

export async function fetchCrawlerAgentModules(projectKey: string) {
  const query = new URLSearchParams({ project_key: projectKey })
  const data = await httpGet<{ items?: CrawlerAgentModule[] }>(`${endpoints.crawler.agentModules}?${query}`)
  return asList<CrawlerAgentModule>(data)
}

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
    CrawlerDeployRunItem & { task_id?: string; async?: boolean; trace_id?: string; run?: CrawlerDeployRunItem }
  >(endpoints.crawler.deploy(crawlerProjectKey), {
    requested_version: payload.requested_version ?? null,
    planner_mode: payload.planner_mode ?? 'heuristic',
    async_mode: payload.async_mode ?? true,
  })
  if (data && typeof data === 'object' && 'run' in data && data.run && typeof data.run === 'object') {
    return { ...data.run, task_id: data.task_id, async: data.async, trace_id: data.trace_id }
  }
  return data
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
