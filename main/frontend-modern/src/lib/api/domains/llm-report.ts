import { endpoints } from '../endpoints'
import { apiClient } from '../client'

export type LlmReportExportFormat = 'pdf' | 'docx'

export type LlmReportFileExportPayload = {
  markdown: string
  quality_gate?: Record<string, unknown>
  quality_gate_mode?: string | null
  filename?: string | null
  project_key?: string | null
  artifact_token?: string | null
  artifact_sha256?: string | null
  reset_telemetry_boundary_context?: Record<string, unknown> | null
}

export type LlmReportFileExportResult = {
  filename: string
  blob: Blob
  format: LlmReportExportFormat
  readiness?: string | null
}

function filenameFromContentDisposition(value: unknown, fallback: string) {
  const contentDisposition = String(value || '')
  const match = contentDisposition.match(/filename=([^;]+)/i)
  return match?.[1]?.replace(/^"+|"+$/g, '') || fallback
}

export async function exportLlmReportFile(
  format: LlmReportExportFormat,
  payload: LlmReportFileExportPayload,
): Promise<LlmReportFileExportResult> {
  const endpoint = format === 'pdf' ? endpoints.llmReport.exportPdf : endpoints.llmReport.exportDocx
  const response = await apiClient.post<Blob>(endpoint, payload, { responseType: 'blob' })
  return {
    filename: filenameFromContentDisposition(response.headers['content-disposition'], `llm-report.${format}`),
    blob: response.data,
    format,
    readiness: String(response.headers['x-llm-report-export-readiness'] || '') || null,
  }
}
