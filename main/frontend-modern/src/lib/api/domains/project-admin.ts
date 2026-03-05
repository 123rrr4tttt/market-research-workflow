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
  AdminDeleteDocumentsPayload,
  AdminDocumentListPayload,
  AdminDocumentListResponse,
  AdminReExtractPayload,
  AdminStats,
  AdminTopicExtractPayload,
  AdminTopicExtractResponse,
  DashboardStats,
  DocumentBulkExtractedPayload,
  DocumentExtractedPayload,
  DocumentItem,
  RawImportPayload,
  RawImportResult,
  SearchHistoryItem,
} from '../../types'

export async function getDashboardStats() {
  return get<DashboardStats>(endpoints.dashboard.stats)
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

export async function listAdminDocuments(payload: AdminDocumentListPayload = {}) {
  return post<AdminDocumentListResponse>(endpoints.admin.documentList, {
    page: payload.page ?? 1,
    page_size: payload.page_size ?? 20,
    state: payload.state ?? null,
    doc_type: payload.doc_type ?? null,
    has_extracted_data: payload.has_extracted_data ?? null,
    search: payload.search ?? null,
    sort_by: payload.sort_by ?? 'created_at',
    sort_order: payload.sort_order ?? 'desc',
  })
}

export async function getAdminDocument(docId: number) {
  return get<DocumentItem>(endpoints.admin.documentById(docId))
}

export async function updateDocumentExtractedData(docId: number, payload: DocumentExtractedPayload) {
  return post<{ id?: number; extracted_data?: unknown }>(endpoints.admin.documentExtractedData(docId), payload)
}

export async function bulkUpdateDocumentExtractedData(payload: DocumentBulkExtractedPayload) {
  return post<AdminActionResponse>(endpoints.admin.documentsBulkExtractedData, payload)
}

export async function clearDocumentExtractedData(docIds: number[]) {
  return bulkUpdateDocumentExtractedData({
    doc_ids: docIds,
    mode: 'replace',
    extracted_data: null,
  })
}

export async function deleteAdminDocuments(payload: AdminDeleteDocumentsPayload | number[]) {
  const ids = Array.isArray(payload) ? payload : payload.ids
  return post<{ deleted?: number }>(endpoints.admin.documentsDelete, { ids })
}

export async function reExtractDocuments(payload: AdminReExtractPayload = {}) {
  return post<AdminActionResponse>(endpoints.admin.documentsReExtract, payload)
}

export async function topicExtractDocuments(payload: AdminTopicExtractPayload = {}) {
  return post<AdminTopicExtractResponse>(endpoints.admin.documentsTopicExtract, payload)
}

export async function rawImportDocuments(payload: RawImportPayload) {
  return post<RawImportResult>(endpoints.admin.documentsRawImport, payload)
}
