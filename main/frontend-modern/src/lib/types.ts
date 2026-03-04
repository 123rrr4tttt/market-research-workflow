export type ApiEnvelope<T> = {
  status: 'ok' | 'error'
  data: T | null
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  } | null
  meta?: {
    trace_id?: string | null
    project_key?: string | null
    pagination?: {
      page: number
      page_size: number
      total: number
      total_pages: number
    } | null
  }
}

export type HealthResponse = {
  status: string
  provider: string
  env: string
}

export type DeepHealthResponse = {
  status: string
  database?: string
  elasticsearch?: string
}

export type ProjectItem = {
  id?: number
  project_key: string
  name?: string
  schema_name?: string
  enabled?: boolean
  is_active?: boolean
}

export type CrawlerProjectItem = {
  id?: number
  project_key: string
  name?: string
  description?: string | null
  source_type?: string
  source_uri?: string | null
  provider?: string
  status?: string
  current_version?: string | null
  deployed_version?: string | null
  previous_version?: string | null
  import_payload?: Record<string, unknown> | null
  analysis_plan?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export type CrawlerDeployRunItem = {
  id?: number
  crawler_project_id?: number
  crawler_project_key?: string
  action?: 'deploy' | 'rollback' | string
  status?: string
  requested_version?: string | null
  from_version?: string | null
  to_version?: string | null
  planner_mode?: string
  plan?: Record<string, unknown> | null
  external_provider?: string | null
  external_job_id?: string | null
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
}

export type CrawlerProjectImportPayload = {
  project_key?: string | null
  name?: string | null
  repo_url: string
  branch?: string | null
  provider_hint?: string | null
  description?: string | null
  enable_now?: boolean
}

export type CrawlerProjectDeployPayload = {
  requested_version?: string | null
  planner_mode?: string | null
  async_mode?: boolean
}

export type CrawlerProjectRollbackPayload = {
  to_version?: string | null
  planner_mode?: string | null
  async_mode?: boolean
}

export type AutoCreateProjectPayload = {
  project_name: string
  project_key?: string | null
  template_project_key?: string
  activate?: boolean
  copy_initial_data?: boolean
  llm_configs?: Array<{
    service_name: string
    user_prompt_template?: string
    description?: string
    system_prompt?: string
    model?: string
    temperature?: number
    max_tokens?: number
    top_p?: number
    presence_penalty?: number
    frequency_penalty?: number
    enabled?: boolean
  }>
}

export type InjectInitialProjectPayload = {
  project_key?: string | null
  name?: string | null
  source_project_key?: string
  overwrite?: boolean
  activate?: boolean
}

export type InjectInitialProjectResult = {
  project_key: string
  name?: string
  schema_name?: string
  source_project_key?: string
  activated?: boolean
  copied_counts?: Record<string, number>
}

export type AutoCreateProjectResult = {
  project_key: string
  name?: string
  schema_name?: string
  activated?: boolean
  template_project_key?: string
  created_mode?: 'inject_initial' | 'create_empty'
  llm_configs_applied?: number
}

export type EnvSettings = Record<string, string>

export type SourceLibraryScope = 'effective' | 'shared' | 'project'

export type SourceLibraryItem = {
  id?: number
  item_key: string
  name?: string
  channel_key?: string
  description?: string | null
  params?: Record<string, unknown>
  tags?: string[]
  schedule?: string | null
  extends_item_key?: string | null
  enabled?: boolean
  extra?: Record<string, unknown>
  project_key?: string | null
  scope?: SourceLibraryScope
}

export type SourceLibraryChannel = {
  channel_key: string
  name?: string
  provider?: string
  kind?: string
  description?: string | null
  enabled?: boolean
  params_schema?: Record<string, unknown>
  extra?: Record<string, unknown>
}

export type SourceLibraryItemsGroupedResponse = {
  by_handler?: Record<string, SourceLibraryItem[]>
  scope?: SourceLibraryScope
  project_key?: string | null
}

export type SourceLibraryItemUpsertPayload = {
  item_key: string
  name: string
  channel_key: string
  description?: string
  params?: Record<string, unknown>
  tags?: string[]
  schedule?: string
  extends_item_key?: string
  enabled?: boolean
  extra?: Record<string, unknown>
}

export type SourceLibraryItemRefreshPayload = {
  incremental?: boolean
  max_site_entries?: number
}

export type SourceLibraryHandlerSyncPayload = {
  handlers?: string[]
  incremental?: boolean
  max_site_entries?: number
}

export type SourceLibraryHandlerSyncResult = {
  handler_key?: string
  item_key?: string
  expected_entry_type?: string
  incremental?: boolean
  domains?: string[]
  site_entry_tags?: string[]
  site_entries_before?: number
  site_entries_after?: number
  added?: number
}

export type SourceLibraryHandlerSyncResponse = {
  ok?: boolean
  project_key?: string
  handler_count?: number
  results?: SourceLibraryHandlerSyncResult[]
}

export type SiteEntryGroupedResponse = {
  by_entry_type?: Record<string, { count?: number; sample_urls?: string[] }>
}

export type IngestJobRow = {
  id?: string | number
  task_id?: string
  task_name?: string
  job_type?: string
  status?: string
  created_at?: string
  updated_at?: string
  started_at?: string
  finished_at?: string
  url?: string | null
  doc_id?: string | number | null
  document_id?: string | number | null
  extraction_status?: string | null
  inserted?: number | null
  inserted_valid?: number | null
  skipped?: number | null
  rejected_count?: number | null
  rejection_breakdown?: Record<string, number> | null
  degradation_flags?: string[] | null
  quality_score?: number | null
  error?: string | null
  params?: Record<string, unknown> | null
}

export type IngestSingleUrlResult = {
  task_id?: string
  status?: string
  async?: boolean
  params?: Record<string, unknown> | null
  effective_payload?: Record<string, unknown> | null
  url?: string | null
  doc_id?: string | number | null
  document_id?: string | number | null
  extraction_status?: 'success' | 'failed' | 'degraded' | string
  structured_extraction_status?: string | null
  inserted?: number | null
  inserted_valid?: number | null
  skipped?: number | null
  rejected_count?: number | null
  rejection_breakdown?: Record<string, number> | null
  degradation_flags?: string[] | null
  quality_score?: number | null
  filter_reason_code?: string | null
  light_filter?: Record<string, unknown> | null
  error?: string | null
}

export type ProcessTaskItem = {
  task_id: string
  name: string
  status: string
  worker?: string | null
  started_at?: string | null
  updated_at?: string | null
  source?: string | null
  args?: unknown[]
  kwargs?: Record<string, unknown>
  progress?: Record<string, unknown> | null
  traceback?: string | null
  display_meta?: ProcessTaskMeta | null
}

export type ProcessTaskList = {
  tasks: ProcessTaskItem[]
  stats: {
    total_tasks?: number
    active_tasks?: number
    pending_tasks?: number
    workers?: number
  }
}

export type ProcessTaskStats = {
  active_tasks?: number
  scheduled_tasks?: number
  reserved_tasks?: number
  total_running?: number
  workers?: number
  worker_names?: string[]
}

export type ProcessHistoryResponse = {
  history?: Array<{
    id: number
    task_id?: string | null
    task_name?: string | null
    job_type?: string
    status?: string
    params?: Record<string, unknown>
    started_at?: string
    finished_at?: string
    duration_seconds?: number | null
    error?: string | null
    source?: string | null
    worker?: string | null
    display_meta?: ProcessTaskMeta | null
    inserted_valid?: number | null
    rejected_count?: number | null
    rejection_breakdown?: Record<string, number> | null
  }>
  total?: number
  status_stats?: Record<string, number>
}

export type DashboardStats = {
  documents?: {
    total?: number
    recent_today?: number
    recent_7d?: number
    extraction_rate?: number
    type_distribution?: Record<string, number>
  }
  sources?: {
    total?: number
    enabled?: number
  }
  market_stats?: {
    total?: number
    states_count?: number
  }
  tasks?: {
    total?: number
    running?: number
    completed?: number
    failed?: number
  }
}

export type IngestFormState = {
  queryTerms: string
  topicFocus: '' | 'company' | 'product' | 'operation'
  languages: Array<'zh' | 'en'>
  provider: '' | 'serper' | 'google' | 'ddg' | 'serpstack' | 'serpapi' | 'auto'
  maxItems: number
  startOffset: string
  daysBack: string
  enableExtraction: boolean
  asyncMode: boolean
  socialPlatform: string
  baseSubreddits: string
  enableSubredditDiscovery: boolean
  commodityLimit: number
  ecomLimit: number
  sourceItemKey: string
  sourceHandlerKey: string
  policyState: string
  singleUrl: string
  singleUrlStrictMode: boolean
  singleUrlSearchExpand: boolean
  singleUrlSearchExpandLimit: number
  singleUrlSearchProvider: 'auto' | 'google' | 'ddg_html'
  singleUrlSearchFallbackProvider: 'ddg_html'
  singleUrlFallbackOnInsufficient: boolean
  singleUrlAllowSearchSummaryWrite: boolean
  singleUrlMinResultsRequired: number
  singleUrlTargetCandidates: number
  singleUrlDecodeRedirectWrappers: boolean
  singleUrlFilterLowValueCandidates: boolean
  singleUrlLightFilterEnabled: boolean
  singleUrlLightFilterMinScore: number
  singleUrlLightFilterRejectStaticAssets: boolean
  singleUrlLightFilterRejectSearchNoiseDomain: boolean
}

export type RouteToken =
  | 'overviewTasks'
  | 'process-management'
  | 'overviewData'
  | 'admin'
  | 'dashboard'
  | 'dashboard-analysis'
  | 'dashboard-board'
  | 'data-dashboard'
  | 'market-data-visualization'
  | 'social-media-visualization'
  | 'policy-visualization'
  | 'graph'
  | 'graph-market'
  | 'graph-policy'
  | 'graph-social'
  | 'graph-company'
  | 'graph-product'
  | 'graph-operation'
  | 'graph-market-deep'
  | 'ingest'
  | 'ingest-specialized'
  | 'raw-data-processing'
  | 'resource-pool-management'
  | 'crawler-management'
  | 'project-management'
  | 'settings'
  | 'settings-llm-config'
  | 'backend-dashboard'
  | 'topic-dashboard'
  | 'topic-company'
  | 'topic-product'
  | 'topic-operation'

export type RouteHint = {
  mode: 'flowWorkflow' | 'flowProcessing'
  variant?: 'workflow' | 'rawData'
}

export type TaskPayload = {
  project_key?: string | null
  query_terms?: string[]
  keywords?: string[]
  base_keywords?: string[]
  max_items?: number
  max_results?: number
  url_count?: number
  limit?: number
  provider?: string
  search_provider?: string
  scope?: string
  state?: string
  item_key?: string | null
  resource_id?: string | null
  channel_key?: string | null
  platform?: string
  topic?: string
}

export type ProcessTaskMeta = {
  project_key?: string | null
  summary?: string | null
  chips?: string[]
  item_key?: string | null
  channel?: string | null
  query_terms_count?: number | null
  url_count?: number | null
  provider?: string | null
  limit?: number | null
  item?: string | null
  stage?: string | null
  state?: string | null
  [key: string]: unknown
}

export type ProcessTaskDetail = {
  task_id: string
  name: string
  status: string
  ready?: boolean | null
  successful?: boolean | null
  failed?: boolean | null
  result?: unknown
  progress?: Record<string, unknown> | null
  traceback?: string | null
  worker?: string | null
  started_at?: string | null
  args?: unknown[]
  kwargs?: Record<string, unknown>
  display_meta?: ProcessTaskMeta | null
  inserted_valid?: number | null
  rejected_count?: number | null
  rejection_breakdown?: Record<string, number> | null
}

export type ResourcePoolUrlItem = {
  id?: number
  url?: string
  domain?: string
  source?: string
  created_at?: string
}

export type SiteEntryItem = {
  id?: number
  site_url?: string
  domain?: string
  entry_type?: string
  source?: string
  enabled?: boolean
}

export type WorkflowNode = {
  id: string
  name?: string
  module_key?: string
  type?: string
  handler?: string
  params?: Record<string, unknown>
  title?: string
  data_type?: string
}

export type WorkflowEdge = {
  id?: string
  source: string
  target: string
  mapping?: Record<string, unknown>
}

export type WorkflowBoardLayout = {
  layout?: string
  graph?: {
    nodes?: WorkflowNode[]
    edges?: WorkflowEdge[]
    [key: string]: unknown
  }
  edge_mappings?: Array<Record<string, unknown>>
  auto_interface?: boolean
  design?: {
    global_data_type?: string
    node_overrides?: Record<string, unknown>
    llm_policy?: string
    visualization_module?: string
  }
  data_flow?: string[]
  adapter_nodes?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export type TopicItem = {
  id: number
  topic_name: string
  domains: string[]
  languages: string[]
  keywords_seed: string[]
  subreddits: string[]
  enabled: boolean
  description?: string | null
}

export type ProductItem = {
  id: number
  name: string
  category?: string | null
  source_name?: string | null
  source_uri?: string | null
  selector_hint?: string | null
  currency?: string | null
  enabled: boolean
}

export type PolicyItem = {
  id: number
  title?: string | null
  state?: string | null
  status?: string | null
  publish_date?: string | null
  policy_type?: string | null
  uri?: string | null
}

export type PolicyDetail = {
  id: number
  title?: string | null
  state?: string | null
  status?: string | null
  publish_date?: string | null
  effective_date?: string | null
  policy_type?: string | null
  key_points?: string[]
  summary?: string | null
  uri?: string | null
  content?: string | null
  source_id?: number | null
}

export type PolicyStats = {
  total_policies?: number
  state_distribution?: Array<{ state: string; count: number }>
  type_distribution?: Array<{ policy_type: string; count: number }>
  status_distribution?: Array<{ status: string; count: number }>
}

export type WorkflowTemplate = {
  workflow_name: string
  steps: Array<{
    handler: string
    params?: Record<string, unknown>
    enabled?: boolean
    name?: string | null
  }>
  board_layout?: Record<string, unknown>
  boardLayout?: WorkflowBoardLayout
  meta?: Record<string, unknown>
}

export type WorkflowTemplatePayload = {
  project_key?: string
  steps: Array<{
    handler: string
    params?: Record<string, unknown>
    enabled?: boolean
    name?: string | null
  }>
  board_layout?: WorkflowBoardLayout | Record<string, unknown>
}

export type WorkflowRunResult = {
  task_id?: string
  task_name?: string
  status?: string
  started_at?: string
  params?: Record<string, unknown>
  workflow_name?: string
}

export type WorkflowTemplateMeta = {
  source?: 'builtin' | 'custom'
  [key: string]: unknown
}

export type WorkflowTemplateResponse = WorkflowTemplate & {
  project_key?: string
  meta?: WorkflowTemplateMeta
  board_layout?: WorkflowBoardLayout
}

export type ResourcePoolAction = {
  name?: string
  status?: string
  task_id?: string
  project_key?: string
  total?: number
  upserted?: number
  skipped?: number
  errors?: number
}

export type SettingTemplateConfig = {
  id?: number
  project_key?: string
  service_name: string
  description?: string | null
  system_prompt?: string | null
  user_prompt_template?: string | null
  model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  top_p?: number | null
  presence_penalty?: number | null
  frequency_penalty?: number | null
  enabled: boolean
  updated_at?: string | null
}

export type LlmTemplatePayload = Omit<SettingTemplateConfig, 'id' | 'updated_at' | 'project_key'>

export type RawImportPayload = {
  items: Array<{
    title?: string
    uri?: string | null
    uris?: string[]
    text: string
    summary?: string | null
    doc_type?: string | null
    publish_date?: string | null
    state?: string | null
  }>
  source_name: string
  source_kind?: string
  infer_from_links: boolean
  enable_extraction: boolean
  default_doc_type: 'market_info' | 'policy' | 'social_sentiment' | 'news' | 'raw_note'
  extraction_mode: 'auto' | 'market' | 'policy' | 'social'
  overwrite_on_uri: boolean
  chunk_size: number
  chunk_overlap: number
  max_chunks: number
}

export type RawImportResult = {
  inserted?: number
  updated?: number
  skipped?: number
  error_count?: number
  errors?: Array<Record<string, unknown>>
  items?: Array<Record<string, unknown>>
}

export type SourceLibraryItemPayload = {
  item_key: string
  name?: string
  channel_key?: string
  description?: string
  params?: Record<string, unknown>
  tags?: string[]
  schedule?: string
  extends_item_key?: string
  enabled?: boolean
  extra?: Record<string, unknown>
  project_key?: string
}

export type SourceLibraryRunResult = {
  task_id?: string
  async?: boolean
  item_key?: string
  project_key?: string
  ok?: boolean
}

export type ProcessTaskCancelResult = {
  success?: boolean
  message?: string
  task_id?: string
}

export type ProcessTaskLogsResponse = {
  task_id?: string
  tail?: number
  filtered?: boolean
  text?: string
  log_file?: string
}

export type AdminDocumentListPayload = {
  page?: number
  page_size?: number
  state?: string | null
  doc_type?: string | null
  has_extracted_data?: boolean | null
  search?: string | null
  sort_by?: 'created_at' | 'publish_date' | 'id'
  sort_order?: 'asc' | 'desc'
}

export type AdminDocumentItem = {
  id: number
  title?: string | null
  doc_type?: string | null
  state?: string | null
  source_id?: number
  created_at?: string | null
  updated_at?: string | null
  publish_date?: string | null
  has_extracted_data?: boolean
}

export type AdminDocumentListResponse = {
  items: AdminDocumentItem[]
  total: number
  page: number
  page_size: number
}

export type DocumentItem = {
  id: number
  title?: string | null
  doc_type?: string | null
  state?: string | null
  status?: string | null
  publish_date?: string | null
  content?: string | null
  summary?: string | null
  uri?: string | null
  source_id?: number | null
  created_at?: string | null
  updated_at?: string | null
  extracted_data?: Record<string, unknown> | null
}

export type DocumentExtractedPayload = {
  mode: 'replace' | 'merge'
  extracted_data: unknown
}

export type DocumentBulkExtractedPayload = {
  doc_ids: number[]
  mode: 'replace' | 'merge'
  extracted_data: unknown
}

export type AdminActionResponse = {
  requested?: number
  updated?: number
  skipped?: number
  missing?: number[]
  total?: number
  success?: number
  error?: number
  skipped_count?: number
}

export type AdminDeleteDocumentsPayload = {
  ids: number[]
}

export type AdminReExtractPayload = {
  doc_ids?: number[]
  force?: boolean
  fetch_missing_content?: boolean
  batch_size?: number
  limit?: number
  treat_empty_er_as_missing?: boolean
}

export type AdminTopicExtractPayload = {
  topics?: Array<'company' | 'product' | 'operation'>
  doc_ids?: number[]
  doc_types?: string[]
  force?: boolean
  fetch_missing_content?: boolean
  batch_size?: number
  limit?: number
  candidate_mode?: 'rules_then_llm' | string
}

export type AdminTopicExtractResponse = {
  total?: number
  success?: number
  error?: number
  skipped?: number
  topic_hits?: Partial<Record<'company' | 'product' | 'operation', number>> & Record<string, number>
  [key: string]: unknown
}

export type GraphExportResponse = {
  nodes?: Array<Record<string, unknown>>
  edges?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export type WorkflowTemplateMutationResponse = {
  project_key?: string
  workflow_name?: string
  saved?: boolean
  deleted?: boolean
  config_key?: string
  config?: Record<string, unknown>
}

export type ResourcePoolRecommendationPayload = {
  project_key?: string | null
  site_url: string
  entry_type?: string | null
  template?: string | null
  use_llm?: boolean
}

export type ResourcePoolRecommendationItem = {
  index?: number
  site_url?: string
  entry_type?: string | null
  channel_key?: string | null
  template?: string | null
  validated?: boolean
  source?: string
  capabilities?: Record<string, unknown>
  symbol_suggestion?: Record<string, unknown> | null
}

export type ResourcePoolRecommendationResponse = {
  channel_key?: string | null
  entry_type?: string | null
  template?: string | null
  validated?: boolean
  source?: string
  capabilities?: Record<string, unknown>
}

export type ResourcePoolBatchRecommendationPayload = {
  project_key?: string | null
  entries: Array<{
    site_url: string
    entry_type?: string | null
    template?: string | null
  }>
  use_llm?: boolean
  llm_batch_size?: number
}

export type ResourcePoolBatchRecommendationResponse = {
  items?: ResourcePoolRecommendationItem[]
  count?: number
}

export type ResourcePoolUpsertSiteEntryPayload = {
  project_key?: string
  scope?: 'project' | 'shared'
  site_url: string
  entry_type?: string
  template?: string | null
  name?: string | null
  domain?: string | null
  tags?: string[]
  enabled?: boolean
  capabilities?: Record<string, unknown>
  source?: string
  source_ref?: Record<string, unknown>
  extra?: Record<string, unknown>
}

export type ResourcePoolDiscoverPayload = {
  project_key?: string
  url_scope?: 'project' | 'shared' | 'effective' | string
  target_scope?: 'project' | 'shared'
  limit_domains?: number
  probe_timeout?: number
  dry_run?: boolean
  write?: boolean
  async_mode?: boolean
}

export type ResourcePoolDiscoverResponse = {
  task_id?: string
  candidates?: number
  written?: number
  inserted?: number
  updated?: number
  skipped?: number
  errors?: number
  [key: string]: unknown
}

export type LlmProjectTemplatesResponse = {
  project_key?: string
  items?: LlmServiceConfigItem[]
}

export type LlmTemplateUpdatePayload = {
  description?: string | null
  system_prompt?: string | null
  user_prompt_template?: string | null
  model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  top_p?: number | null
  presence_penalty?: number | null
  frequency_penalty?: number | null
  enabled?: boolean | null
}

export type LlmTemplateUpdateResponse = {
  project_key?: string
  item?: LlmServiceConfigItem
}

export type LlmTemplateCopyPayload = {
  source_project_key: string
  overwrite?: boolean
}

export type LlmTemplateCopyResponse = {
  source_project_key?: string
  target_project_key?: string
  copied?: number
  skipped?: number
  overwrite?: boolean
}

export type LlmServiceConfigItem = {
  id: number
  service_name: string
  description?: string | null
  model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  enabled: boolean
  updated_at?: string
}

export type AdminStats = {
  documents?: {
    total?: number
    recent_today?: number
  }
  social_data?: {
    total?: number
    recent_today?: number
  }
  sources?: {
    total?: number
  }
  market_stats?: {
    total?: number
  }
  search_history?: {
    total?: number
  }
}

export type SearchHistoryItem = {
  id: number
  topic?: string | null
  last_search_time?: string | null
}

export type SourceTimeWindowStatItem = {
  source_domain: string
  bucket_time: string
  total_docs: number
  with_source_time_docs: number
  fallback_ingested_docs: number
  source_time_coverage: number
}

export type SourceTimeWindowStatsResponse = {
  version: string
  time_window: string
  bucket: 'day' | 'week' | 'month'
  start_time: string
  end_time: string
  items: SourceTimeWindowStatItem[]
}

export type SourceNounDensityItem = {
  source_domain: string
  noun_group_id: string
  bucket_time: string
  effective_new_docs: number
  density: number
  norm_density: number
  dup_ratio: number
  baseline_density?: number
  collection_priority_score: number
  recommended_window_rank: number
}

export type SourceNounDensityResponse = {
  version: string
  time_window: string
  bucket: 'day' | 'week' | 'month'
  start_time: string
  end_time: string
  items: SourceNounDensityItem[]
}

export type CollectionWindowPriorityItem = {
  source_domain: string
  noun_group_id: string
  window: string
  density: number
  norm_density: number
  dup_ratio: number
  collection_priority_score: number
  rank: number
}

export type CollectionWindowPriorityResponse = {
  version: string
  prefer_low_density: boolean
  exclude_high_dup: boolean
  items: CollectionWindowPriorityItem[]
}

export type NounDensityDrilldownItem = {
  id: number
  title?: string | null
  doc_type?: string | null
  source_domain?: string | null
  source_time?: string | null
  effective_time?: string | null
  uri?: string | null
  noun_groups?: string[]
}

export type NounDensityDrilldownResponse = {
  version: string
  time_window: string
  bucket: 'day' | 'week' | 'month'
  start_time: string
  end_time: string
  source_domain?: string | null
  noun_group_id?: string | null
  total: number
  page: number
  page_size: number
  items: NounDensityDrilldownItem[]
}

export type GraphNodeRef = {
  type: string
  id: string | number
}

export type GraphNodeItem = {
  id: string | number
  type: string
  entry_id?: string | number
  title?: string
  name?: string
  text?: string
  canonical_name?: string
  [key: string]: unknown
}

export type GraphEdgeItem = {
  type?: string
  predicate?: string
  predicate_raw?: string
  relation_class?: string
  from: GraphNodeRef
  to: GraphNodeRef
  [key: string]: unknown
}

export type GraphResponse = {
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
}

export type GraphConfigResponse = {
  graph_doc_types?: Record<string, string[]>
  graph_type_labels?: Record<string, string>
  graph_node_types?: Record<string, string[]>
  graph_node_labels?: Record<string, string>
  graph_topic_scope_entities?: Record<string, string[]>
  graph_field_labels?: Record<string, string>
  graph_edge_types?: Record<string, string[]>
  graph_relation_labels?: Record<string, string>
}

export type GraphStructuredSelectedNode = {
  type: string
  id: string
  entry_id: string
  label: string
  topic_focus?: 'company' | 'product' | 'operation' | 'general'
}

export type GraphStructuredSelectedEdge = {
  source_entry_id?: string
  target_entry_id?: string
  relation?: string
  label?: string
}

export type GraphStructuredDashboardParams = {
  language: string
  provider: string
  max_items: number
  start_offset: number | null
  days_back: number | null
  enable_extraction: boolean
  async_mode: boolean
  platforms: string[]
  enable_subreddit_discovery: boolean
  base_subreddits: string[] | null
  source_item_keys?: string[]
  project_key?: string | null
}

export type GraphStructuredSearchRequest = {
  selected_nodes: GraphStructuredSelectedNode[]
  selected_edges?: GraphStructuredSelectedEdge[]
  dashboard: GraphStructuredDashboardParams
  llm_assist: boolean
  flow_type: 'collect' | 'source_collect'
  intent_mode: 'keyword' | 'keyword_llm'
}

export type GraphStructuredSearchBatch = {
  batch_name?: string
  task_id?: string
  type?: string
  [key: string]: unknown
}

export type GraphStructuredSearchResponse = {
  flow_type?: string
  intent_mode?: string
  batches?: GraphStructuredSearchBatch[]
  summary?: {
    accepted?: number
    queued?: number
    failed?: number
    [key: string]: unknown
  }
  [key: string]: unknown
}
