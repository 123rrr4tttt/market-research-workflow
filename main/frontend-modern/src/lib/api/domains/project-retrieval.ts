import { endpoints } from '../endpoints'
import { httpGet, httpPost } from '../client'

export type RetrievalLimits = {
  max_queries: number
  max_materials: number
  max_followups: number
}

export type RetrievalRoute = {
  route_id: string
  label: string
  query_ids: string[]
}

export type ProjectRetrievalMode = {
  project_key: string
  mode_id: string
  version: string | number
  source_revision: string | number
  routes: RetrievalRoute[]
  queries: Array<{ query_id: string; route_id: string; expression: string }>
  evidence_contract: string
  source_registry_count: number
  outline_summary: Record<string, unknown>
  domain_vocabulary: Record<string, unknown>
  limits: RetrievalLimits
}

export type RetrievalPreviewRequest = {
  route_id: string
  query_ids: string[]
  limits: RetrievalLimits
}

export type RetrievalPlan = {
  plan_id: string
  route_id: string
  query_ids: string[]
  limits: RetrievalLimits
  steps: Array<string | Record<string, unknown>>
  channels?: Array<{ capability: string; registration: string; connectivity: string }>
  diagnostics: Array<string | Record<string, unknown>>
}

export type RetrievalRun = {
  run_id: string
  status: string
  phase?: string | null
  counts?: Record<string, number>
  errors?: Array<string | Record<string, unknown>>
}

export function getCurrentRetrievalMode() {
  return httpGet<ProjectRetrievalMode>(endpoints.projectRetrieval.currentMode)
}

export function previewRetrievalPlan(payload: RetrievalPreviewRequest) {
  return httpPost<RetrievalPlan>(endpoints.projectRetrieval.preview, payload)
}

export function startRetrievalRun(planId: string, idempotencyKey: string) {
  return httpPost<RetrievalRun>(endpoints.projectRetrieval.runs, {
    plan_id: planId,
    idempotency_key: idempotencyKey,
  })
}

export function getRetrievalRun(runId: string) {
  return httpGet<RetrievalRun>(endpoints.projectRetrieval.runById(runId))
}
