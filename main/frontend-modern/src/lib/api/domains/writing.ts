import { endpoints } from '../endpoints'
import { apiClient, asList, httpDelete as del, httpGet as get, httpPatch as patch, httpPost as post, unwrapEnvelope } from '../client'

export type WritingDocumentStatus = 'draft' | 'published' | 'archived' | string

export type WritingDocument = {
  id: number
  project_key: string
  title: string
  body_md: string
  status: WritingDocumentStatus
  version: number
  etag: string
  updated_by_user_id?: string | null
  updated_at?: string | null
  created_at?: string | null
  metadata_json: Record<string, unknown>
}

export type WritingDraft = {
  id: number
  doc_id: number
  project_key: string
  draft_body_md: string
  selection_snapshot?: Record<string, unknown> | null
  base_version: number
  autosave_token: string
  request_id?: string | null
  updated_at?: string | null
  created_at?: string | null
}

export type WritingCitation = {
  id?: number
  doc_id?: number
  project_key?: string
  source_doc_id?: number | null
  source_uri?: string | null
  source_title?: string | null
  quote_text?: string | null
  position_anchor?: string | null
  card_id?: string | null
  metadata_json?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export type WritingTemplate = {
  template_key: string
  label: string
  description?: string | null
  template_content: string
}

export type WritingTemplateValidation = {
  valid: boolean
  errors: string[]
  warnings: string[]
  normalized_template: Record<string, unknown>
  rules: Record<string, unknown>
  observability: Record<string, unknown>
}

export type TypedKnowledgeWritingHandoff = {
  contract_version: 'typed_knowledge.writing_handoff.v1'
  knowledge_item_key: string
  project_key: string
  canonical_statement: string
  primary_type_node_key: string
  topic_cluster_keys: string[]
  booklet_keys: string[]
  review_state: string
  quality_grade?: string | null
  locale?: string | null
  evidence_refs: string[]
  visibility_scope: string
  selection_hash?: string | null
  selection_text?: string | null
  facets: Record<string, unknown>
}

export type TypedKnowledgeWritingContext = {
  contract_version: 'writing.typed_knowledge_context.v1'
  source: 'typed_knowledge'
  consumer: 'writing.keyword_card'
  handoffs: TypedKnowledgeWritingHandoff[]
  boundary: Record<string, unknown>
}

export type WritingContextEnvelope = {
  contract_version?: string
  selection_context?: Record<string, unknown>
  evidence_context?: Record<string, unknown>
  accepted_citation_context?: Record<string, unknown>
  graph_context?: Record<string, unknown> | null
  typed_knowledge_context?: TypedKnowledgeWritingContext | null
}

export type WritingKeywordCardSource = 'document' | 'resource' | 'graph'

export type WritingKeywordCard = {
  card_id: string
  source_type: WritingKeywordCardSource
  title: string
  snippet: string
  url?: string | null
  score: number
  publisher?: string | null
  published_at?: string | null
  retrieved_at?: string | null
  evidence?: string | null
  relevance_tags: string[]
  credibility?: number | null
  quick_actions: string[]
  extra: Record<string, unknown>
}

export type WritingKeywordCardListResponse = {
  cards: WritingKeywordCard[]
  selection_hash: string
  suggested_queries: string[]
  search_backends_used: string[]
  source_count: Record<string, number>
  dedupe_count: number
  score_snapshot: Record<string, unknown>
  context_boundary: Record<string, unknown>
  dependency_gate: Record<string, unknown>
  cache_hit: boolean
  cache_ttl_ms?: number | null
}

export type WritingKeywordCardPreview = {
  card_id: string
  title: string
  url?: string | null
  publisher?: string | null
  snippet: string
  score: number
  source_type: WritingKeywordCardSource
  quick_actions: string[]
}

export type WritingKeywordCardDetail = {
  card_id: string
  title: string
  url?: string | null
  score: number
  evidence?: string | null
  publisher?: string | null
  published_at?: string | null
  retrieved_at?: string | null
  normalized_query?: string | null
  dedupe_trace: Array<Record<string, unknown>>
  provenance: Record<string, unknown>
  selection_matches: Record<string, unknown>
  source_type: WritingKeywordCardSource
}

export type WritingSuggestMode = 'keyword' | 'template' | 'material' | 'command'

export type WritingSuggestItem = {
  kind: WritingSuggestMode
  id: string
  label: string
  snippet?: string | null
  score?: number | null
  extra: Record<string, unknown>
}

export type WritingSuggestResponse = {
  items: WritingSuggestItem[]
  suggest_type: string
  query: string
  source: string[]
  query_rewrite: string
  selection_hash?: string | null
}

export type WritingLlmActionId = 'outline_generate' | 'section_expand' | 'selection_rewrite' | 'evidence_summary'

export type WritingLlmActionResponse = {
  content: string
  sources: Array<Record<string, unknown>>
  mode: string
  warnings: string[]
  trace_id?: string | null
  job_id?: number | null
  status: string
  capability_truth: Record<string, unknown>
  observability: Record<string, unknown>
  action_boundary: Record<string, unknown>
  dependency_gate: Record<string, unknown>
}

export type WritingLlmActionHistoryItem = {
  job_id: number
  job_type: string
  status: string
  project_key?: string | null
  action_id?: string | null
  template_key?: string | null
  template_version?: string | null
  request_meta: Record<string, unknown>
  actor_id?: string | null
  trace_id?: string | null
  created_at?: string | null
  duration_ms?: number | null
  result_summary: Record<string, unknown>
}

export type CreateWritingDocumentPayload = {
  project_key?: string
  title: string
  body_md?: string
  updated_by_user_id?: string | null
  metadata_json?: Record<string, unknown>
}

export type UpdateWritingDocumentPayload = {
  project_key?: string
  title?: string
  body_md: string
  base_version?: number | null
  updated_by_user_id?: string | null
  metadata_json?: Record<string, unknown> | null
}

export type AutosaveWritingDraftPayload = {
  project_key?: string
  draft_body_md: string
  base_version?: number | null
  autosave_token: string
  request_id?: string | null
  selection_snapshot?: Record<string, unknown>
}

export type ValidateWritingTemplatePayload = {
  project_key?: string
  template_key?: string | null
  template_content?: string | null
  template_id?: string | null
  sample_payload?: Record<string, unknown>
  strict?: boolean
}

export type WritingKeywordCardRequest = {
  project_key?: string
  trace_id?: string | null
  request_id?: string | null
  query: string
  selection_hash?: string | null
  limit?: number
  sources?: WritingKeywordCardSource[]
  timeout_ms?: number | null
  context?: WritingContextEnvelope | null
  graph_context?: Record<string, unknown> | null
}

export type WritingKeywordCardPreviewRequest = {
  project_key?: string
  trace_id?: string | null
  request_id?: string | null
  card_id: string
  query?: string | null
}

export type WritingCardDetailParams = {
  project_key?: string
  include_provenance?: boolean
  max_provenance_items?: number
}

export type WritingSuggestParams = {
  mode?: WritingSuggestMode
  project_key?: string
  limit?: number
}

export type WritingLlmActionPayload = {
  project_key?: string
  trace_id?: string | null
  request_id?: string | null
  action_id: WritingLlmActionId
  template_key?: string | null
  template_version?: string | null
  document_id?: string | null
  input_markdown?: string
  selection_text?: string | null
  target_scope?: 'selection' | 'document' | null
  async?: boolean
  gate_mode?: string | null
}

export const WRITING_CONTEXT_BOUNDARY_CONTRACT_VERSION = 'writing.context_boundary.e3.v1' as const
export const WRITING_TYPED_KNOWLEDGE_CONTEXT_VERSION = 'writing.typed_knowledge_context.v1' as const
export const WRITING_TYPED_KNOWLEDGE_HANDOFF_CONTRACT_VERSION = 'typed_knowledge.writing_handoff.v1' as const
export const WRITING_TYPED_KNOWLEDGE_CONSUMER = 'writing.keyword_card' as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function stringValue(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function stringList(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.map((item) => stringValue(item)).filter(Boolean)
}

function typedKnowledgeContextCandidate(value: unknown): unknown {
  if (!isRecord(value)) return null
  if (value.contract_version === WRITING_TYPED_KNOWLEDGE_CONTEXT_VERSION) return value
  for (const key of ['typed_knowledge_context', 'writing_typed_knowledge_context']) {
    if (key in value) return value[key]
  }
  for (const key of ['writing_context', 'context', 'metadata_json']) {
    const nested = value[key]
    if (isRecord(nested)) {
      const candidate = typedKnowledgeContextCandidate(nested)
      if (candidate) return candidate
    }
  }
  return null
}

function normalizeTypedKnowledgeWritingHandoff(value: unknown): TypedKnowledgeWritingHandoff | null {
  if (!isRecord(value) || value.contract_version !== WRITING_TYPED_KNOWLEDGE_HANDOFF_CONTRACT_VERSION) return null
  const knowledge_item_key = stringValue(value.knowledge_item_key)
  const project_key = stringValue(value.project_key)
  const canonical_statement = stringValue(value.canonical_statement)
  const primary_type_node_key = stringValue(value.primary_type_node_key)
  const evidence_refs = stringList(value.evidence_refs)
  const review_state = stringValue(value.review_state)
  const visibility_scope = stringValue(value.visibility_scope)
  if (!knowledge_item_key || !project_key || !canonical_statement || !primary_type_node_key || !review_state || !visibility_scope || !evidence_refs.length) {
    return null
  }
  return {
    contract_version: WRITING_TYPED_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
    knowledge_item_key,
    project_key,
    canonical_statement,
    primary_type_node_key,
    topic_cluster_keys: stringList(value.topic_cluster_keys),
    booklet_keys: stringList(value.booklet_keys),
    review_state,
    quality_grade: stringValue(value.quality_grade) || null,
    locale: stringValue(value.locale) || null,
    evidence_refs,
    visibility_scope,
    selection_hash: stringValue(value.selection_hash) || null,
    selection_text: stringValue(value.selection_text) || null,
    facets: isRecord(value.facets) ? value.facets : {},
  }
}

export function readTypedKnowledgeWritingContext(value: unknown): TypedKnowledgeWritingContext | null {
  const candidate = typedKnowledgeContextCandidate(value)
  if (!isRecord(candidate)) return null
  if (candidate.contract_version !== WRITING_TYPED_KNOWLEDGE_CONTEXT_VERSION) return null
  if (candidate.source !== 'typed_knowledge' || candidate.consumer !== WRITING_TYPED_KNOWLEDGE_CONSUMER) return null
  const handoffs = Array.isArray(candidate.handoffs)
    ? candidate.handoffs.map((item) => normalizeTypedKnowledgeWritingHandoff(item)).filter((item): item is TypedKnowledgeWritingHandoff => Boolean(item))
    : []
  if (!handoffs.length) return null
  return {
    contract_version: WRITING_TYPED_KNOWLEDGE_CONTEXT_VERSION,
    source: 'typed_knowledge',
    consumer: WRITING_TYPED_KNOWLEDGE_CONSUMER,
    handoffs,
    boundary: isRecord(candidate.boundary) ? candidate.boundary : {},
  }
}

export function readTypedKnowledgeWritingContextFromDocument(document: Pick<WritingDocument, 'metadata_json'> | null | undefined) {
  return readTypedKnowledgeWritingContext(document?.metadata_json)
}

export function writingTypedKnowledgeContextKey(context: TypedKnowledgeWritingContext | null | undefined) {
  if (!context) return 'typed_knowledge:none'
  const handoffKeys = context.handoffs.map((handoff) => [
    handoff.knowledge_item_key,
    handoff.selection_hash || '',
    handoff.visibility_scope,
  ].join(':'))
  return `typed_knowledge:${handoffKeys.join('|')}`
}

export function withTypedKnowledgeWritingContext(
  payload: WritingKeywordCardRequest,
  context: TypedKnowledgeWritingContext | null | undefined,
): WritingKeywordCardRequest {
  if (!context) return payload
  const existingContext: WritingContextEnvelope = isRecord(payload.context) ? (payload.context as WritingContextEnvelope) : {}
  return {
    ...payload,
    context: {
      ...existingContext,
      contract_version: existingContext.contract_version || WRITING_CONTEXT_BOUNDARY_CONTRACT_VERSION,
      typed_knowledge_context: context,
    },
  }
}

export function buildPersistedTypedKnowledgeKeywordCardRequest({
  projectKey,
  query,
  selectionHash,
  document,
  limit,
  sources = ['document', 'resource', 'graph'],
}: {
  projectKey: string
  query: string
  selectionHash?: string | null
  document: Pick<WritingDocument, 'metadata_json'> | null | undefined
  limit?: number
  sources?: WritingKeywordCardSource[]
}): WritingKeywordCardRequest {
  const typedContext = readTypedKnowledgeWritingContextFromDocument(document)
  return withTypedKnowledgeWritingContext(
    {
      project_key: projectKey,
      query,
      selection_hash: selectionHash || undefined,
      limit,
      sources,
    },
    typedContext,
  )
}

function withQuery(path: string, params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === '') return
    query.set(key, String(value))
  })
  const suffix = query.toString()
  return suffix ? `${path}?${suffix}` : path
}

function listResponse<T>(value: T[] | { items?: T[] }) {
  return asList<T>(value)
}

export async function listWritingDocuments(limit = 50) {
  const data = await get<WritingDocument[] | { items?: WritingDocument[] }>(withQuery(endpoints.writing.documents, { limit }))
  return listResponse<WritingDocument>(data)
}

export async function createWritingDocument(payload: CreateWritingDocumentPayload) {
  return post<WritingDocument>(endpoints.writing.documents, {
    body_md: '',
    metadata_json: {},
    ...payload,
  })
}

export async function getWritingDocument(docId: number) {
  return get<WritingDocument>(endpoints.writing.documentById(docId))
}

export async function deleteWritingDocument(docId: number, projectKey?: string) {
  return del<{ deleted: boolean; document: WritingDocument }>(
    withQuery(endpoints.writing.documentById(docId), { project_key: projectKey }),
  )
}

export async function updateWritingDocument(
  docId: number,
  payload: UpdateWritingDocumentPayload,
  options?: { ifMatch?: string | null },
) {
  if (!options?.ifMatch) {
    return patch<WritingDocument>(endpoints.writing.documentById(docId), payload)
  }

  const response = await apiClient.patch(endpoints.writing.documentById(docId), payload, {
    headers: { 'If-Match': options.ifMatch },
  })
  return unwrapEnvelope<WritingDocument>(response.data)
}

export async function autosaveWritingDraft(docId: number, payload: AutosaveWritingDraftPayload) {
  return post<WritingDraft>(endpoints.writing.documentDraft(docId), payload)
}

export async function listWritingCitations(docId: number) {
  const data = await get<WritingCitation[] | { items?: WritingCitation[] }>(endpoints.writing.documentCitations(docId))
  return listResponse<WritingCitation>(data)
}

export async function upsertWritingCitations(docId: number, citations: WritingCitation[], projectKey?: string) {
  const data = await post<{ items?: WritingCitation[] }>(endpoints.writing.documentCitations(docId), {
    project_key: projectKey,
    citations,
  })
  return listResponse<WritingCitation>(data)
}

export async function listWritingTemplates() {
  const data = await get<WritingTemplate[] | { items?: WritingTemplate[] }>(endpoints.writing.templates)
  return listResponse<WritingTemplate>(data)
}

export async function validateWritingTemplate(payload: ValidateWritingTemplatePayload) {
  return post<WritingTemplateValidation>(endpoints.writing.templateValidate, {
    sample_payload: {},
    strict: false,
    ...payload,
  })
}

export async function getWritingKeywordCards(payload: WritingKeywordCardRequest) {
  return post<WritingKeywordCardListResponse>(endpoints.writing.keywordCards, payload)
}

export async function previewWritingKeywordCard(payload: WritingKeywordCardPreviewRequest) {
  return post<WritingKeywordCardPreview>(endpoints.writing.keywordCardPreview, payload)
}

export async function getWritingCardDetail(cardId: string, params: WritingCardDetailParams = {}) {
  return get<WritingKeywordCardDetail>(
    withQuery(endpoints.writing.cardById(cardId), {
      project_key: params.project_key,
      include_provenance: params.include_provenance ?? true,
      max_provenance_items: params.max_provenance_items ?? 20,
    }),
  )
}

export async function getWritingSuggest(query: string, params: WritingSuggestParams = {}) {
  return get<WritingSuggestResponse>(
    withQuery(endpoints.writing.suggest, {
      query,
      mode: params.mode ?? 'keyword',
      project_key: params.project_key,
      limit: params.limit ?? 20,
    }),
  )
}

export async function runWritingLlmAction(payload: WritingLlmActionPayload) {
  return post<WritingLlmActionResponse>(endpoints.writing.llmActions, payload)
}

export async function listWritingLlmActionHistory(limit = 20) {
  const data = await get<WritingLlmActionHistoryItem[] | { items?: WritingLlmActionHistoryItem[] }>(
    withQuery(endpoints.writing.llmActionHistory, { limit }),
  )
  return listResponse<WritingLlmActionHistoryItem>(data)
}

export async function getWritingLlmActionDetail(jobId: number) {
  return get<WritingLlmActionHistoryItem>(endpoints.writing.llmActionById(jobId))
}

export async function exportWritingMarkdown(docId: number, projectKey?: string) {
  const response = await apiClient.post<string>(
    endpoints.writing.exportMarkdown,
    {
      doc_id: docId,
      project_key: projectKey,
    },
    {
      responseType: 'text',
    },
  )
  const contentDisposition = String(response.headers['content-disposition'] || '')
  const match = contentDisposition.match(/filename=([^;]+)/i)
  return {
    filename: match?.[1]?.replace(/^"+|"+$/g, '') || `writing-document-${docId}.md`,
    markdown: typeof response.data === 'string' ? response.data : '',
  }
}
