import axios from 'axios'
import type { ApiEnvelope } from '../types'

const STORAGE_KEY = 'market_project_key'

export function normalizeProjectKey(raw: string) {
  return (
    String(raw || 'default')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_+|_+$/g, '') || 'default'
  )
}

export function getProjectKey() {
  return normalizeProjectKey(window.localStorage.getItem(STORAGE_KEY) || 'default')
}

export function setProjectKey(projectKey: string) {
  const next = normalizeProjectKey(projectKey)
  window.localStorage.setItem(STORAGE_KEY, next)
  return next
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const projectKey = getProjectKey()
  config.headers['X-Project-Key'] = projectKey

  const original = String(config.url || '')
  const isAbsolute = /^https?:\/\//i.test(original)
  const url = new URL(original || '/', isAbsolute ? undefined : window.location.origin)

  if (url.pathname.startsWith('/api/')) {
    url.searchParams.set('project_key', projectKey)
  }

  config.url = isAbsolute ? url.toString() : `${url.pathname}${url.search}${url.hash}`
  return config
})

export function unwrapEnvelope<T>(payload: ApiEnvelope<T> | T): T {
  if (payload && typeof payload === 'object' && 'status' in payload && 'data' in payload) {
    const envelope = payload as ApiEnvelope<T>
    if (envelope.status === 'error') {
      throw new Error(envelope.error?.message || 'Request failed')
    }
    return envelope.data as T
  }
  return payload as T
}

export async function httpGet<T>(url: string) {
  const { data } = await apiClient.get<ApiEnvelope<T> | T>(url)
  return unwrapEnvelope<T>(data)
}

export async function httpPost<T>(url: string, body: unknown) {
  const { data } = await apiClient.post<ApiEnvelope<T> | T>(url, body)
  return unwrapEnvelope<T>(data)
}

export async function httpPut<T>(url: string, body: unknown) {
  const { data } = await apiClient.put<ApiEnvelope<T> | T>(url, body)
  return unwrapEnvelope<T>(data)
}

export async function httpPatch<T>(url: string, body: unknown) {
  const { data } = await apiClient.patch<ApiEnvelope<T> | T>(url, body)
  return unwrapEnvelope<T>(data)
}

export async function httpDelete<T>(url: string) {
  const { data } = await apiClient.delete<ApiEnvelope<T> | T>(url)
  return unwrapEnvelope<T>(data)
}

export function asList<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object' && 'items' in value) {
    const items = (value as { items?: unknown }).items
    return Array.isArray(items) ? (items as T[]) : []
  }
  return []
}
