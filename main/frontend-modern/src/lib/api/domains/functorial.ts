import { endpoints } from '../endpoints'
import { asList, httpGet, httpPost } from '../client'

export type OperatorSpec = {
  operator_id: string
  name?: string
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  impl_ref?: string
  risk?: string
}

export type MotifSpec = {
  motif_id: string
  name?: string
  composition?: string[]
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
}

export type WorkflowStep = {
  ref: string
}

export type WorkflowSpec = {
  workflow_id: string
  name?: string
  steps?: WorkflowStep[]
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  laws?: string[]
  version?: number
}

export type WorkflowRunResponse = {
  workflow_id?: string
  run_id?: string
  status?: string
  result?: unknown
  output?: unknown
}

export async function listFunctorialOperators(): Promise<OperatorSpec[]> {
  const data = await httpGet<unknown>(endpoints.functorial.operators)
  return asList<OperatorSpec>(data)
}

export async function listFunctorialMotifs(): Promise<MotifSpec[]> {
  const data = await httpGet<unknown>(endpoints.functorial.motifs)
  return asList<MotifSpec>(data)
}

export async function listFunctorialWorkflows(): Promise<WorkflowSpec[]> {
  const data = await httpGet<unknown>(endpoints.functorial.workflows)
  return asList<WorkflowSpec>(data)
}

export async function createFunctorialOperator(payload: OperatorSpec): Promise<OperatorSpec> {
  return httpPost<OperatorSpec>(endpoints.functorial.operators, payload)
}

export async function createFunctorialMotif(payload: MotifSpec): Promise<MotifSpec> {
  return httpPost<MotifSpec>(endpoints.functorial.motifs, payload)
}

export async function createFunctorialWorkflow(payload: WorkflowSpec): Promise<WorkflowSpec> {
  return httpPost<WorkflowSpec>(endpoints.functorial.workflows, payload)
}

export async function runFunctorialWorkflow(
  workflowId: string,
  inputs: Record<string, unknown>,
): Promise<WorkflowRunResponse> {
  return httpPost<WorkflowRunResponse>(endpoints.functorial.workflowRun(workflowId), { inputs })
}
