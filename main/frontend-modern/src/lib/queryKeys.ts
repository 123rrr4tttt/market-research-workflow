export const queryKeys = {
  health: {
    all: ['health'] as const,
    deep: () => ['health-deep'] as const,
  },
  projects: {
    all: () => ['projects'] as const,
  },
  config: {
    envStatus: () => ['app-env-status'] as const,
  },
  process: {
    all: () => ['process'] as const,
    list: (limit = 50) => ['process', 'list', limit] as const,
    stats: () => ['process', 'stats'] as const,
    history: (limit = 50) => ['process', 'history', limit] as const,
    detail: (taskId: string) => ['process', 'detail', taskId] as const,
    logs: (taskId: string, tail = 200) => ['process', 'logs', taskId, tail] as const,
  },
  ingest: {
    all: () => ['ingest'] as const,
    history: (limit = 8) => ['ingest', 'history', limit] as const,
    historyByProject: (projectKey: string, limit = 8) => ['ingest', 'history', limit, projectKey] as const,
  },
  dashboard: {
    stats: (projectKey: string) => ['dashboard-stats', projectKey] as const,
  },
  policy: {
    stats: (projectKey: string) => ['policy-stats', projectKey] as const,
    list: (projectKey: string, stateFilter: string, page: number) => ['policy-list', projectKey, stateFilter, page] as const,
    listBase: (projectKey: string) => ['policy-list', projectKey] as const,
    detail: (projectKey: string, policyId: number | null) => ['policy-detail', projectKey, policyId] as const,
    detailBase: (projectKey: string) => ['policy-detail', projectKey] as const,
  },
  workflow: {
    all: (projectKey: string) => ['workflows', projectKey] as const,
    template: (projectKey: string, workflowName: string) => ['workflow-template', projectKey, workflowName] as const,
    runDetail: (projectKey: string, taskId: string | null) => ['workflow-run-detail', projectKey, taskId] as const,
    runLogs: (projectKey: string, taskId: string | null) => ['workflow-run-logs', projectKey, taskId] as const,
  },
  sourceLibrary: {
    items: (projectKey: string, scope?: string) => (scope == null ? ['source-items', projectKey] as const : ['source-items', projectKey, scope] as const),
    itemsBase: (projectKey: string) => ['source-items', projectKey] as const,
    itemsGrouped: (projectKey: string, scope?: string) => (scope == null ? ['source-items-grouped', projectKey] as const : ['source-items-grouped', projectKey, scope] as const),
    itemsGroupedBase: (projectKey: string) => ['source-items-grouped', projectKey] as const,
    channels: (projectKey: string, scope?: string) => (scope == null ? ['source-channels', projectKey] as const : ['source-channels', projectKey, scope] as const),
    channelsBase: (projectKey: string) => ['source-channels', projectKey] as const,
    siteEntryGrouped: (projectKey: string) => ['site-entry-grouped', projectKey] as const,
    itemsForGraph: (projectKey: string) => ['source-library-items', projectKey] as const,
  },
  resource: {
    urls: (projectKey: string, domain: string, source: string, page: number) => ['resource-urls', projectKey, domain, source, page] as const,
    urlsBase: (projectKey: string) => ['resource-urls', projectKey] as const,
    siteEntries: (projectKey: string, domain: string, entryType: string, page: number) => ['site-entries', projectKey, domain, entryType, page] as const,
    siteEntriesBase: (projectKey: string) => ['site-entries', projectKey] as const,
  },
  admin: {
    stats: (projectKey: string) => ['admin-stats', projectKey] as const,
    searchHistory: (projectKey: string) => ['search-history', projectKey] as const,
    documents: (projectKey: string, page: number, docType: string, docState: string, search: string) =>
      ['admin-documents', projectKey, page, docType, docState, search] as const,
    documentsBase: (projectKey: string) => ['admin-documents', projectKey] as const,
    documentDetail: (projectKey: string, docId: number | null) => ['admin-document-detail', projectKey, docId] as const,
  },
  crawler: {
    projects: (projectKey: string) => ['crawler-manage', 'projects', projectKey] as const,
    projectDetail: (projectKey: string, crawlerProjectKey: string) => ['crawler-manage', 'project-detail', projectKey, crawlerProjectKey] as const,
    projectDetailBase: (projectKey: string) => ['crawler-manage', 'project-detail', projectKey] as const,
    deployRuns: (projectKey: string, crawlerProjectKey: string) => ['crawler-manage', 'deploy-runs', projectKey, crawlerProjectKey] as const,
    deployRunsBase: (projectKey: string) => ['crawler-manage', 'deploy-runs', projectKey] as const,
  },
  catalog: {
    topics: (projectKey: string) => ['topics', projectKey] as const,
    products: (projectKey: string) => ['products', projectKey] as const,
  },
  settings: {
    env: () => ['env-settings'] as const,
    projectLlmTemplates: (projectKey: string) => ['project-llm-templates', projectKey] as const,
  },
  graph: {
    config: (projectKey: string) => ['graph-config', projectKey] as const,
    data: (
      projectKey: string,
      graphKind: string,
      startDate: string,
      endDate: string,
      state: string,
      policyType: string,
      platform: string,
      topic: string,
      game: string,
      limit: number,
    ) => ['graph', projectKey, graphKind, startDate, endDate, state, policyType, platform, topic, game, limit] as const,
  },
} as const
