import { endpoints } from '../endpoints'
import { asList, httpGet as get, httpPost as post } from '../client'
import {
  activateProjectByKey,
  archiveProjectRecord,
  createProjectRecord,
  deleteProjectRecord,
  fetchProjects,
  restoreProjectRecord,
  updateProjectRecord,
} from '../services/projects'
import type {
  AdminActionResponse,
  AdminDeleteMaterialsPayload,
  AdminMaterialListPayload,
  AdminMaterialListResponse,
  AdminReExtractPayload,
  AdminStats,
  AdminTopicExtractPayload,
  AdminTopicExtractResponse,
  DashboardReportFromFilterPayload,
  DashboardReportFromFilterResponse,
  DashboardLlmReportDetailParams,
  DashboardLlmReportDetailResponse,
  DashboardGlobalStats,
  DashboardStats,
  MaterialBulkExtractedPayload,
  MaterialExtractedPayload,
  MaterialItem,
  RawImportPayload,
  RawImportResult,
  SearchHistoryItem,
} from '../../types'

export async function getDashboardStats() {
  return get<DashboardStats>(endpoints.dashboard.stats)
}

export async function getDashboardGlobalStats() {
  return get<DashboardGlobalStats>(endpoints.dashboard.globalStats)
}

export async function createDashboardReportFromFilter(payload: DashboardReportFromFilterPayload) {
  return post<DashboardReportFromFilterResponse>(endpoints.dashboard.reportFromFilter, payload)
}

export async function getDashboardLlmReportDetail({ traceId, projectKey }: DashboardLlmReportDetailParams) {
  const params = new URLSearchParams()
  params.set('trace_id', traceId)
  if (projectKey) params.set('project_key', projectKey)
  return get<DashboardLlmReportDetailResponse>(endpoints.dashboard.llmReportDetail(params))
}

export async function listProjects() {
  return fetchProjects()
}

export async function activateProject(projectKey: string) {
  return activateProjectByKey(projectKey)
}

export async function createProject(payload: { project_key: string; name: string; enabled?: boolean }) {
  return createProjectRecord(payload)
}

export async function updateProject(projectKey: string, payload: { name?: string; enabled?: boolean }) {
  return updateProjectRecord(projectKey, payload)
}

export async function archiveProject(projectKey: string) {
  return archiveProjectRecord(projectKey)
}

export async function restoreProject(projectKey: string) {
  return restoreProjectRecord(projectKey)
}

export async function deleteProject(projectKey: string, hard = false) {
  return deleteProjectRecord(projectKey, hard)
}

export async function getAdminStats() {
  return get<AdminStats>(endpoints.admin.stats)
}

export async function getSearchHistory(page = 1, pageSize = 50) {
  const data = await get<SearchHistoryItem[] | { items?: SearchHistoryItem[] }>(
    `${endpoints.admin.searchHistory}?page=${page}&page_size=${pageSize}`,
  )
  return asList<SearchHistoryItem>(data)
}

export async function listAdminMaterials(payload: AdminMaterialListPayload = {}) {
  return post<AdminMaterialListResponse>(endpoints.admin.materialList, {
    page: payload.page ?? 1,
    page_size: payload.page_size ?? 20,
    state: payload.state ?? null,
    material_type: payload.material_type ?? null,
    has_extracted_data: payload.has_extracted_data ?? null,
    search: payload.search ?? null,
    sort_by: payload.sort_by ?? 'created_at',
    sort_order: payload.sort_order ?? 'desc',
  })
}

export async function getAdminMaterial(materialId: number) {
  return get<MaterialItem>(endpoints.admin.materialById(materialId))
}

export async function updateMaterialExtractedData(materialId: number, payload: MaterialExtractedPayload) {
  return post<{ material_id?: number; extracted_data?: unknown }>(endpoints.admin.materialExtractedData(materialId), payload)
}

export async function bulkUpdateMaterialExtractedData(payload: MaterialBulkExtractedPayload) {
  return post<AdminActionResponse>(endpoints.admin.materialsBulkExtractedData, payload)
}

export async function clearMaterialExtractedData(materialIds: number[]) {
  return bulkUpdateMaterialExtractedData({
    material_ids: materialIds,
    mode: 'replace',
    extracted_data: null,
  })
}

export async function deleteAdminMaterials(payload: AdminDeleteMaterialsPayload) {
  return post<AdminActionResponse>(endpoints.admin.materialsDelete, payload)
}

export async function reExtractMaterials(payload: AdminReExtractPayload = {}) {
  return post<AdminActionResponse>(endpoints.admin.materialsReExtract, payload)
}

export async function topicExtractMaterials(payload: AdminTopicExtractPayload = {}) {
  return post<AdminTopicExtractResponse>(endpoints.admin.materialsTopicExtract, payload)
}

export async function rawImportMaterials(payload: RawImportPayload) {
  return post<RawImportResult>(endpoints.admin.materialsRawImport, payload)
}
