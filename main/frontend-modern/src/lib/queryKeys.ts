import { normalizeGraphQueryParams, type GraphQueryParams } from './api/domains/graph-workflow'

export function buildGraphDataQueryKey(projectKey: string, graphKind: string, params: GraphQueryParams) {
  const normalized = normalizeGraphQueryParams(params)
  const baseKey = ['graph', projectKey, graphKind] as const

  if (graphKind === 'policy') {
    return [
      ...baseKey,
      normalized.start_date,
      normalized.end_date,
      normalized.state,
      normalized.policy_type,
      normalized.limit,
    ] as const
  }

  if (graphKind === 'social') {
    return [
      ...baseKey,
      normalized.start_date,
      normalized.end_date,
      normalized.platform,
      normalized.topic,
      normalized.limit,
    ] as const
  }

  if (graphKind === 'market' || graphKind === 'market_deep_entities' || graphKind === 'company' || graphKind === 'product' || graphKind === 'operation') {
    return [
      ...baseKey,
      normalized.start_date,
      normalized.end_date,
      normalized.state,
      normalized.game,
      normalized.limit,
    ] as const
  }

  return [
    ...baseKey,
    normalized.start_date,
    normalized.end_date,
    normalized.state,
    normalized.policy_type,
    normalized.platform,
    normalized.topic,
    normalized.game,
    normalized.limit,
  ] as const
}

export const queryKeys = {
  health: {
    all: ['health'] as const,
    deep: () => ['health-deep'] as const,
  },
  auth: {
    codex: () => ['auth', 'codex'] as const,
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
    listByProject: (projectKey: string, limit = 50) => ['process', 'list', limit, projectKey] as const,
    stats: () => ['process', 'stats'] as const,
    statsByProject: (projectKey: string) => ['process', 'stats', projectKey] as const,
    history: (limit = 50) => ['process', 'history', limit] as const,
    historyByProject: (projectKey: string, limit = 50) => ['process', 'history', limit, projectKey] as const,
    detail: (taskId: string) => ['process', 'detail', taskId] as const,
    detailByProject: (taskId: string, projectKey: string) => ['process', 'detail', taskId, projectKey] as const,
    logs: (taskId: string, tail = 200) => ['process', 'logs', taskId, tail] as const,
    logsByProject: (taskId: string, projectKey: string, tail = 200) => ['process', 'logs', taskId, tail, projectKey] as const,
  },
  agentSessions: {
    all: () => ['agent-sessions'] as const,
    list: () => ['agent-sessions', 'list'] as const,
    detail: (sessionId: string) => ['agent-sessions', 'detail', sessionId] as const,
    tasks: (sessionId: string) => ['agent-sessions', 'tasks', sessionId] as const,
    messages: (sessionId: string) => ['agent-sessions', 'messages', sessionId] as const,
    events: (sessionId: string) => ['agent-sessions', 'events', sessionId] as const,
    artifacts: (sessionId: string) => ['agent-sessions', 'artifacts', sessionId] as const,
    approvals: (sessionId: string) => ['agent-sessions', 'approvals', sessionId] as const,
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
    promptDensityPriority: (projectKey: string, promptGroupId: string, timeWindow: string) =>
      ['policy-prompt-density-priority', projectKey, promptGroupId, timeWindow] as const,
  },
  stats: {
    promptTimeDensity: (
      projectKey: string,
      timeWindow: string,
      promptGroupId: string,
      bucket: 'day' | 'week' | 'month',
    ) => ['stats', 'prompt-time-density', projectKey, timeWindow, promptGroupId, bucket] as const,
    promptTimeDensityPriority: (
      projectKey: string,
      timeWindow: string,
      promptGroupId: string,
      preferLowDensity: boolean,
    ) => ['stats', 'prompt-time-density-priority', projectKey, timeWindow, promptGroupId, preferLowDensity] as const,
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
  writing: {
    all: (projectKey: string) => ['writing', projectKey] as const,
    documents: (projectKey: string) => ['writing', projectKey, 'documents'] as const,
    documentDetail: (projectKey: string, docId: number | null) => ['writing', projectKey, 'document-detail', docId] as const,
    citations: (projectKey: string, docId: number | null) => ['writing', projectKey, 'citations', docId] as const,
    templates: (projectKey: string) => ['writing', projectKey, 'templates'] as const,
    templateValidation: (projectKey: string, templateKey: string) => ['writing', projectKey, 'template-validation', templateKey] as const,
    keywordCards: (projectKey: string, selectionHash: string, query: string) =>
      ['writing', projectKey, 'keyword-cards', selectionHash, query] as const,
    keywordCardPreview: (projectKey: string, cardId: string) => ['writing', projectKey, 'keyword-card-preview', cardId] as const,
    keywordCardDetail: (projectKey: string, cardId: string) => ['writing', projectKey, 'keyword-card-detail', cardId] as const,
    suggest: (projectKey: string, mode: string, query: string) => ['writing', projectKey, 'suggest', mode, query] as const,
    llmHistory: (projectKey: string) => ['writing', projectKey, 'llm-history'] as const,
    llmDetail: (projectKey: string, jobId: number | null) => ['writing', projectKey, 'llm-detail', jobId] as const,
  },
  typedKnowledge: {
    writingContext: (projectKey: string) => ['typed-knowledge', projectKey, 'writing-context'] as const,
    governance: (projectKey: string) => ['typed-knowledge', projectKey, 'governance'] as const,
  },
  graph: {
    config: (projectKey: string) => ['graph-config', projectKey] as const,
    templates: (projectKey: string) => ['graph-templates', projectKey] as const,
    templateDetail: (projectKey: string, templateId: string | null) =>
      ['graph-template-detail', projectKey, templateId] as const,
    templateVersions: (projectKey: string, templateId: string | null) =>
      ['graph-template-versions', projectKey, templateId] as const,
    versionDetail: (projectKey: string, templateId: string | null, versionId: string | null) =>
      ['graph-template-version-detail', projectKey, templateId, versionId] as const,
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
    ) =>
      buildGraphDataQueryKey(projectKey, graphKind, {
        start_date: startDate,
        end_date: endDate,
        state,
        policy_type: policyType,
        platform,
        topic,
        game,
        limit,
      }),
  },
} as const
