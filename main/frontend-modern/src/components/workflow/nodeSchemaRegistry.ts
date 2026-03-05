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
    ],
  },
  vector_search: {
    nodeType: 'vector_search',
    fields: [
      { key: 'query_key', label: 'query_key', type: 'text', placeholder: 'query' },
      { key: 'top_k', label: 'top_k', type: 'number', placeholder: '5' },
      { key: 'source', label: 'source', type: 'text', placeholder: 'default_corpus' },
      { key: 'rerank', label: 'rerank', type: 'boolean' },
    ],
  },
  join: {
    nodeType: 'join',
    fields: [
      { key: 'strategy', label: 'strategy', type: 'select', options: ['concat', 'json_merge'] },
      { key: 'field', label: 'field', type: 'text', placeholder: 'optional field' },
      { key: 'delimiter', label: 'delimiter', type: 'text', placeholder: '\\n\\n' },
    ],
  },
}

export function getNodeSchema(nodeType: string): NodeSchema | null {
  const key = String(nodeType || '').trim().toLowerCase()
  return NODE_SCHEMA_REGISTRY[key] || null
}
