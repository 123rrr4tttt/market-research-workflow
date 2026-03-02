export const API_BASE = '/api/v1'

const withQuery = (path: string, query: URLSearchParams | string) => `${path}?${query.toString()}`

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
    injectInitial: `${API_BASE}/projects/inject-initial`,
    autoCreate: `${API_BASE}/projects/auto-create`,
    activate: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}/activate`,
    archive: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}/archive`,
    restore: (projectKey: string) => `${API_BASE}/projects/${encodeURIComponent(projectKey)}/restore`,
  },
  crawler: {
    projects: `${API_BASE}/crawler/projects`,
    projectByKey: (crawlerProjectKey: string) => `${API_BASE}/crawler/projects/${encodeURIComponent(crawlerProjectKey)}`,
    importProject: `${API_BASE}/crawler/projects/import`,
    deploy: (crawlerProjectKey: string) => `${API_BASE}/crawler/projects/${encodeURIComponent(crawlerProjectKey)}/deploy`,
    rollback: (crawlerProjectKey: string) => `${API_BASE}/crawler/projects/${encodeURIComponent(crawlerProjectKey)}/rollback`,
    deployRuns: `${API_BASE}/crawler/deploy-runs`,
    deployRunById: (runId: string | number) => `${API_BASE}/crawler/deploy-runs/${encodeURIComponent(String(runId))}`,
    deployRunsByProject: (crawlerProjectKey: string) =>
      `${API_BASE}/crawler/projects/${encodeURIComponent(crawlerProjectKey)}/deploy-runs`,
  },
  sourceLibrary: {
    channels: `${API_BASE}/source_library/channels`,
    channelsQuery: (query: URLSearchParams | string) => withQuery(`${API_BASE}/source_library/channels`, query),
    channelsGrouped: `${API_BASE}/source_library/channels/grouped`,
    channelsGroupedQuery: (query: URLSearchParams | string) =>
      withQuery(`${API_BASE}/source_library/channels/grouped`, query),
    items: `${API_BASE}/source_library/items`,
    itemsQuery: (query: URLSearchParams | string) => withQuery(`${API_BASE}/source_library/items`, query),
    itemsGrouped: `${API_BASE}/source_library/items/grouped`,
    itemsGroupedQuery: (query: URLSearchParams | string) => withQuery(`${API_BASE}/source_library/items/grouped`, query),
    itemRefresh: (itemKey: string) => `${API_BASE}/source_library/items/${encodeURIComponent(itemKey)}/refresh`,
    handlerClustersSync: `${API_BASE}/source_library/handler_clusters/sync`,
  },
  resourcePool: {
    urls: `${API_BASE}/resource_pool/urls`,
    urlsQuery: (query: URLSearchParams | string) => withQuery(`${API_BASE}/resource_pool/urls`, query),
    siteEntries: `${API_BASE}/resource_pool/site_entries`,
    siteEntriesQuery: (query: URLSearchParams | string) => withQuery(`${API_BASE}/resource_pool/site_entries`, query),
    siteEntriesRecommend: `${API_BASE}/resource_pool/site_entries/recommend`,
    siteEntriesRecommendBatch: `${API_BASE}/resource_pool/site_entries/recommend-batch`,
    siteEntriesSimplify: `${API_BASE}/resource_pool/site_entries/simplify`,
    siteEntriesGrouped: `${API_BASE}/resource_pool/site_entries/grouped`,
    siteEntriesGroupedQuery: (query: URLSearchParams | string) =>
      withQuery(`${API_BASE}/resource_pool/site_entries/grouped`, query),
    extractFromDocuments: `${API_BASE}/resource_pool/extract/from-documents`,
    discoverSiteEntries: `${API_BASE}/resource_pool/discover/site-entries`,
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
  discovery: {
    generateKeywords: `${API_BASE}/discovery/generate-keywords`,
  },
  ingest: {
    history: `${API_BASE}/ingest/history`,
    urlSingle: `${API_BASE}/ingest/url/single`,
    policy: `${API_BASE}/ingest/policy`,
    policyRegulation: `${API_BASE}/ingest/policy/regulation`,
    market: `${API_BASE}/ingest/market`,
    socialSentiment: `${API_BASE}/ingest/social/sentiment`,
    commodityMetrics: `${API_BASE}/ingest/commodity/metrics`,
    ecomPrices: `${API_BASE}/ingest/ecom/prices`,
    sourceLibrarySync: `${API_BASE}/ingest/source-library/sync`,
    sourceLibraryRun: `${API_BASE}/ingest/source-library/run`,
    graphStructuredSearch: `${API_BASE}/ingest/graph/structured-search`,
  },
  topics: {
    root: `${API_BASE}/topics`,
    byId: (topicId: number) => `${API_BASE}/topics/${topicId}`,
  },
  products: {
    root: `${API_BASE}/products`,
    byId: (productId: number) => `${API_BASE}/products/${productId}`,
  },
  policies: {
    root: `${API_BASE}/policies`,
    stats: `${API_BASE}/policies/stats`,
    byId: (policyId: number) => `${API_BASE}/policies/${policyId}`,
  },
  workflow: {
    root: `${API_BASE}/project-customization/workflows`,
    template: (workflowName: string) =>
      `${API_BASE}/project-customization/workflows/${encodeURIComponent(workflowName)}/template`,
    run: (workflowName: string) =>
      `${API_BASE}/project-customization/workflows/${encodeURIComponent(workflowName)}/run`,
  },
  llm: {
    root: `${API_BASE}/llm-config`,
    project: (projectKey: string) => `${API_BASE}/llm-config/projects/${encodeURIComponent(projectKey)}`,
    projectService: (projectKey: string, serviceName: string) =>
      `${API_BASE}/llm-config/projects/${encodeURIComponent(projectKey)}/${encodeURIComponent(serviceName)}`,
    copyFrom: (projectKey: string) => `${API_BASE}/llm-config/projects/${encodeURIComponent(projectKey)}/copy-from`,
  },
  admin: {
    stats: `${API_BASE}/admin/stats`,
    searchHistory: `${API_BASE}/admin/search-history`,
    documentList: `${API_BASE}/admin/documents/list`,
    documentById: (docId: number) => `${API_BASE}/admin/documents/${docId}`,
    documentExtractedData: (docId: number) => `${API_BASE}/admin/documents/${docId}/extracted-data`,
    documentsBulkExtractedData: `${API_BASE}/admin/documents/bulk/extracted-data`,
    documentsDelete: `${API_BASE}/admin/documents/delete`,
    documentsReExtract: `${API_BASE}/admin/documents/re-extract`,
    documentsTopicExtract: `${API_BASE}/admin/documents/topic-extract`,
    documentsRawImport: `${API_BASE}/admin/documents/raw-import`,
    exportGraph: `${API_BASE}/admin/export-graph`,
    policyGraph: `${API_BASE}/admin/policy-graph`,
    contentGraph: `${API_BASE}/admin/content-graph`,
    marketGraph: `${API_BASE}/admin/market-graph`,
  },
  governance: {
    cleanup: `${API_BASE}/governance/cleanup`,
    aggregatorSync: `${API_BASE}/governance/aggregator/sync`,
  },
  graph: {
    config: `${API_BASE}/project-customization/graph-config`,
  },
} as const
