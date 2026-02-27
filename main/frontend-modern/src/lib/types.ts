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
    job_type?: string
    status?: string
    started_at?: string
    finished_at?: string
    duration_seconds?: number | null
    error?: string | null
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
  meta?: Record<string, unknown>
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
