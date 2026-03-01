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

export type EnvSettings = Record<string, string>

export type SourceLibraryItem = {
  item_key: string
  name?: string
  description?: string
  tags?: string[]
  params?: Record<string, unknown>
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
    started_at?: string
    finished_at?: string
    duration_seconds?: number | null
    error?: string | null
    source?: string | null
    worker?: string | null
    display_meta?: ProcessTaskMeta | null
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
  enabled?: boolean
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

export type GraphNodeRef = {
  type: string
  id: string | number
}

export type GraphNodeItem = {
  id: string | number
  type: string
  title?: string
  name?: string
  text?: string
  canonical_name?: string
  [key: string]: unknown
}

export type GraphEdgeItem = {
  type?: string
  predicate?: string
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
  graph_field_labels?: Record<string, string>
  graph_edge_types?: Record<string, string[]>
  graph_relation_labels?: Record<string, string>
}
