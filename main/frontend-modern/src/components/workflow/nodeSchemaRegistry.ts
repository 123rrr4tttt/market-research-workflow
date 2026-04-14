export type NodeSchemaFieldType = 'text' | 'number' | 'boolean' | 'textarea' | 'select'

export type NodeSchemaField = {
  key: string
  label: string
  type: NodeSchemaFieldType
  options?: string[]
  placeholder?: string
}

export type NodeSchema = {
  nodeType: string
  fields: NodeSchemaField[]
}

const TASK_MODULE_FIELDS: NodeSchemaField[] = [
  { key: 'module_type', label: 'module_type', type: 'text', placeholder: 'llm | retriever | processor' },
  { key: 'module_key', label: 'module_key', type: 'text', placeholder: 'unique_module_key' },
  { key: 'backend_task_key', label: 'backend_task_key', type: 'text', placeholder: 'task_ingest_market' },
  { key: 'backend_task_name', label: 'backend_task_name', type: 'text', placeholder: 'Market Ingest' },
  { key: 'module_group', label: 'module_group', type: 'text', placeholder: 'ingest | collect | report' },
  { key: 'executor_mode', label: 'executor_mode', type: 'select', options: ['sync', 'async', 'batch'] },
  { key: 'timeout_ms', label: 'timeout_ms', type: 'number', placeholder: '30000' },
  { key: 'retry_policy', label: 'retry_policy', type: 'textarea', placeholder: '{"max_retries":2,"backoff_ms":500}' },
  { key: 'fallback_policy', label: 'fallback_policy', type: 'textarea', placeholder: '{"on_error":"continue"}' },
  { key: 'input_vars', label: 'input_vars', type: 'textarea', placeholder: '["query","context"]' },
  { key: 'output_vars', label: 'output_vars', type: 'textarea', placeholder: '["answer","score"]' },
]

export const NODE_SCHEMA_REGISTRY: Record<string, NodeSchema> = {
  llm_call: {
    nodeType: 'llm_call',
    fields: [
      { key: 'provider', label: 'provider', type: 'select', options: ['openai', 'azure', 'litellm', 'ollama'] },
      { key: 'model', label: 'model', type: 'text', placeholder: 'gpt-4.1' },
      { key: 'temperature', label: 'temperature', type: 'number', placeholder: '0.2' },
      { key: 'top_p', label: 'top_p', type: 'number', placeholder: '1' },
      { key: 'max_tokens', label: 'max_tokens', type: 'number', placeholder: '1024' },
      { key: 'prompt_class', label: 'prompt_class', type: 'select', options: ['analyst', 'summarizer', 'rewriter', 'extractor'] },
      { key: 'prompt_template', label: 'prompt_template', type: 'textarea', placeholder: 'Prompt template...' },
      ...TASK_MODULE_FIELDS,
    ],
  },
  vector_search: {
    nodeType: 'vector_search',
    fields: [
      { key: 'query_key', label: 'query_key', type: 'text', placeholder: 'query' },
      { key: 'top_k', label: 'top_k', type: 'number', placeholder: '5' },
      { key: 'source', label: 'source', type: 'text', placeholder: 'default_corpus' },
      { key: 'rerank', label: 'rerank', type: 'boolean' },
      ...TASK_MODULE_FIELDS,
    ],
  },
  join: {
    nodeType: 'join',
    fields: [
      { key: 'strategy', label: 'strategy', type: 'select', options: ['concat', 'json_merge'] },
      { key: 'field', label: 'field', type: 'text', placeholder: 'optional field' },
      { key: 'delimiter', label: 'delimiter', type: 'text', placeholder: '\\n\\n' },
      ...TASK_MODULE_FIELDS,
    ],
  },
  filter: {
    nodeType: 'filter',
    fields: [
      { key: 'strategy', label: 'strategy', type: 'select', options: ['predicate', 'topk'] },
      { key: 'predicate_expr', label: 'predicate_expr', type: 'textarea', placeholder: '={{$node.prev.score}} > 0.8' },
      { key: 'predicate_mode', label: 'predicate_mode', type: 'select', options: ['keep', 'drop'] },
      { key: 'topk_k', label: 'topk_k', type: 'number', placeholder: '20' },
      { key: 'topk_score_field', label: 'topk_score_field', type: 'text', placeholder: 'score' },
      { key: 'topk_desc', label: 'topk_desc', type: 'boolean' },
      ...TASK_MODULE_FIELDS,
    ],
  },
  frontend_input: {
    nodeType: 'frontend_input',
    fields: [
      { key: 'query_key', label: 'query_key', type: 'text', placeholder: 'query' },
      { key: 'input_payload', label: 'input_payload', type: 'textarea', placeholder: '{"query":"..." }' },
      ...TASK_MODULE_FIELDS,
    ],
  },
  database_sink: {
    nodeType: 'database_sink',
    fields: [
      { key: 'store_uri', label: 'store_uri', type: 'text', placeholder: 'sqlite:///tmp/workflow.db' },
      { key: 'table', label: 'table', type: 'text', placeholder: 'workflow_results' },
      { key: 'upsert_key', label: 'upsert_key', type: 'text', placeholder: 'run_id' },
      ...TASK_MODULE_FIELDS,
    ],
  },
  task_module: {
    nodeType: 'task_module',
    fields: [...TASK_MODULE_FIELDS],
  },
}

export function getNodeSchema(nodeType: string): NodeSchema | null {
  const key = String(nodeType || '').trim().toLowerCase()
  return NODE_SCHEMA_REGISTRY[key] || null
}
