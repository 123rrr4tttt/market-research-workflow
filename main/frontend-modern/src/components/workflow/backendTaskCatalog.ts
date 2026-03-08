export type BackendTaskValueType = 'string' | 'number' | 'boolean' | 'json' | 'array'
export type BackendTaskNodeType = 'vector_search' | 'llm_call' | 'join'

export type BackendTaskField = {
  name: string
  valueType: BackendTaskValueType
  required: boolean
  defaultValue?: string
}

export type BackendTaskSpec = {
  taskKey: string
  label: string
  moduleGroup: string
  description: string
  suggestedNodeType: BackendTaskNodeType
  inputs: BackendTaskField[]
  outputs: BackendTaskField[]
}

const COMMON_OUTPUT: BackendTaskField[] = [
  { name: 'status', valueType: 'string', required: false },
  { name: 'inserted', valueType: 'number', required: false },
  { name: 'updated', valueType: 'number', required: false },
  { name: 'skipped', valueType: 'number', required: false },
]

export const BACKEND_TASK_CATALOG: BackendTaskSpec[] = [
  {
    taskKey: 'task_ingest_policy',
    label: 'Policy Ingest',
    moduleGroup: 'ingest',
    description: 'Ingest policy documents by state.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'state', valueType: 'string', required: true },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: COMMON_OUTPUT,
  },
  {
    taskKey: 'task_ingest_market',
    label: 'Market Ingest',
    moduleGroup: 'ingest',
    description: 'Collect market items from query terms.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'query_terms', valueType: 'array', required: true },
      { name: 'max_items', valueType: 'number', required: false, defaultValue: '20' },
      { name: 'enable_extraction', valueType: 'boolean', required: false, defaultValue: 'true' },
      { name: 'project_key', valueType: 'string', required: false },
      { name: 'start_offset', valueType: 'number', required: false },
      { name: 'days_back', valueType: 'number', required: false },
      { name: 'language', valueType: 'string', required: false },
      { name: 'provider', valueType: 'string', required: false },
    ],
    outputs: COMMON_OUTPUT,
  },
  {
    taskKey: 'task_ingest_single_url',
    label: 'Single URL Ingest',
    moduleGroup: 'ingest',
    description: 'Ingest one URL with optional search fallback.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'url', valueType: 'string', required: true },
      { name: 'query_terms', valueType: 'array', required: false },
      { name: 'strict_mode', valueType: 'boolean', required: false, defaultValue: 'false' },
      { name: 'project_key', valueType: 'string', required: false },
      { name: 'search_options', valueType: 'json', required: false },
    ],
    outputs: [
      { name: 'task_result_status', valueType: 'string', required: false },
      { name: 'quality_score', valueType: 'number', required: false },
      ...COMMON_OUTPUT,
    ],
  },
  {
    taskKey: 'task_collect_social_sentiment',
    label: 'Social Sentiment Collect',
    moduleGroup: 'collect',
    description: 'Collect social sentiment by keywords.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'keywords', valueType: 'array', required: true },
      { name: 'platforms', valueType: 'array', required: false },
      { name: 'limit', valueType: 'number', required: false, defaultValue: '20' },
      { name: 'enable_extraction', valueType: 'boolean', required: false, defaultValue: 'true' },
      { name: 'enable_subreddit_discovery', valueType: 'boolean', required: false, defaultValue: 'true' },
      { name: 'base_subreddits', valueType: 'array', required: false },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: COMMON_OUTPUT,
  },
  {
    taskKey: 'task_collect_policy_regulation',
    label: 'Policy Regulation Collect',
    moduleGroup: 'collect',
    description: 'Collect policy/regulation records by keywords.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'keywords', valueType: 'array', required: true },
      { name: 'limit', valueType: 'number', required: false, defaultValue: '20' },
      { name: 'enable_extraction', valueType: 'boolean', required: false, defaultValue: 'true' },
      { name: 'project_key', valueType: 'string', required: false },
      { name: 'start_offset', valueType: 'number', required: false },
      { name: 'days_back', valueType: 'number', required: false },
      { name: 'language', valueType: 'string', required: false },
      { name: 'provider', valueType: 'string', required: false },
    ],
    outputs: COMMON_OUTPUT,
  },
  {
    taskKey: 'task_ingest_commodity_metrics',
    label: 'Commodity Metrics Ingest',
    moduleGroup: 'ingest',
    description: 'Ingest commodity metrics.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'limit', valueType: 'number', required: false, defaultValue: '30' },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: COMMON_OUTPUT,
  },
  {
    taskKey: 'task_collect_ecom_prices',
    label: 'Ecom Price Collect',
    moduleGroup: 'collect',
    description: 'Collect e-commerce price observations.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'limit', valueType: 'number', required: false, defaultValue: '100' },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: COMMON_OUTPUT,
  },
  {
    taskKey: 'task_index_policy',
    label: 'Policy Index',
    moduleGroup: 'index',
    description: 'Build vector index for policy documents.',
    suggestedNodeType: 'vector_search',
    inputs: [
      { name: 'document_ids', valueType: 'array', required: true },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: [
      { name: 'indexed', valueType: 'number', required: false },
      { name: 'status', valueType: 'string', required: false },
    ],
  },
  {
    taskKey: 'task_extract_resource_pool_from_documents',
    label: 'Extract Resource From Documents',
    moduleGroup: 'extract',
    description: 'Extract URLs from documents into resource pool.',
    suggestedNodeType: 'join',
    inputs: [
      { name: 'project_key', valueType: 'string', required: true },
      { name: 'scope', valueType: 'string', required: false, defaultValue: 'project' },
      { name: 'doc_type', valueType: 'array', required: false },
      { name: 'state', valueType: 'array', required: false },
      { name: 'document_ids', valueType: 'array', required: false },
      { name: 'limit', valueType: 'number', required: false, defaultValue: '500' },
    ],
    outputs: [
      { name: 'upserted', valueType: 'number', required: false },
      { name: 'skipped', valueType: 'number', required: false },
      { name: 'status', valueType: 'string', required: false },
    ],
  },
  {
    taskKey: 'task_extract_resource_pool_from_tasks',
    label: 'Extract Resource From Tasks',
    moduleGroup: 'extract',
    description: 'Extract URLs from etl_job_runs into resource pool.',
    suggestedNodeType: 'join',
    inputs: [
      { name: 'project_key', valueType: 'string', required: true },
      { name: 'scope', valueType: 'string', required: false, defaultValue: 'project' },
      { name: 'task_ids', valueType: 'array', required: false },
      { name: 'job_type', valueType: 'string', required: false },
      { name: 'since', valueType: 'string', required: false },
      { name: 'limit', valueType: 'number', required: false, defaultValue: '100' },
    ],
    outputs: [
      { name: 'upserted', valueType: 'number', required: false },
      { name: 'skipped', valueType: 'number', required: false },
      { name: 'status', valueType: 'string', required: false },
    ],
  },
  {
    taskKey: 'task_collect_weekly_reports',
    label: 'Collect Weekly Reports',
    moduleGroup: 'report',
    description: 'Generate weekly market reports.',
    suggestedNodeType: 'llm_call',
    inputs: [
      { name: 'limit', valueType: 'number', required: false, defaultValue: '10' },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: [
      { name: 'reports', valueType: 'array', required: false },
      { name: 'status', valueType: 'string', required: false },
    ],
  },
  {
    taskKey: 'task_collect_monthly_reports',
    label: 'Collect Monthly Reports',
    moduleGroup: 'report',
    description: 'Generate monthly financial reports.',
    suggestedNodeType: 'llm_call',
    inputs: [
      { name: 'limit', valueType: 'number', required: false, defaultValue: '8' },
      { name: 'project_key', valueType: 'string', required: false },
    ],
    outputs: [
      { name: 'reports', valueType: 'array', required: false },
      { name: 'status', valueType: 'string', required: false },
    ],
  },
]

export const BACKEND_TASK_BY_KEY: Record<string, BackendTaskSpec> = Object.fromEntries(
  BACKEND_TASK_CATALOG.map((item) => [item.taskKey, item]),
) as Record<string, BackendTaskSpec>
