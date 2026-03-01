export const API_BASE = '/api/v1'

export const endpoints = {
  health: {
    root: `${API_BASE}/health`,
    deep: `${API_BASE}/health/deep`,
  },
  dashboard: {
    stats: `${API_BASE}/dashboard/stats`,
  },
  projects: {
    root: `${API_BASE}/projects`,
    byKey: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}`,
    activate: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}/activate`,
    archive: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}/archive`,
    restore: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}/restore`,
  },
  config: {
    env: `${API_BASE}/config/env`,
  },
  process: {
    list: `${API_BASE}/process/list`,
    stats: `${API_BASE}/process/stats`,
    history: `${API_BASE}/process/history`,
    task: (taskId: string) => `${API_BASE}/process/${encodeURIComponent(taskId)}`,
    logs: (taskId: string) => `${API_BASE}/process/${encodeURIComponent(taskId)}/logs`,
    cancel: (taskId: string) => `${API_BASE}/process/${encodeURIComponent(taskId)}/cancel`,
  },
  ingest: {
    history: `${API_BASE}/ingest/history`,
    policy: `${API_BASE}/ingest/policy`,
    policyRegulation: `${API_BASE}/ingest/policy/regulation`,
    market: `${API_BASE}/ingest/market`,
    socialSentiment: `${API_BASE}/ingest/social/sentiment`,
    commodityMetrics: `${API_BASE}/ingest/commodity/metrics`,
    ecomPrices: `${API_BASE}/ingest/ecom/prices`,
    sourceLibrarySync: `${API_BASE}/ingest/source-library/sync`,
    sourceLibraryRun: `${API_BASE}/ingest/source-library/run`,
  },
} as const
