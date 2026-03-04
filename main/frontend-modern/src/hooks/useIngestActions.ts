import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getProjectKey,
  ingestCommodity,
  ingestEcom,
  ingestMarket,
  ingestPolicy,
  ingestPolicyRegulation,
  ingestSingleUrl,
  ingestSocial,
  runSourceLibrary,
  syncSourceLibrary,
} from '../lib/api'
import { isApiClientError, normalizeProjectKey } from '../lib/api/client'
import { queryKeys } from '../lib/queryKeys'

type IngestActionFn = () => Promise<unknown>

type SourceLibraryRunPayload = {
  item_key?: string | null
  handler_key?: string | null
  project_key?: string | null
  schema_name?: string | null
  async_mode: boolean
  override_params: Record<string, unknown>
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function toFiniteNumber(value: unknown): number | null {
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  return num
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((v) => String(v || '').trim()).filter(Boolean)
}

function getTraceId(meta: unknown): string {
  if (!meta || typeof meta !== 'object') return ''
  const traceId = (meta as { trace_id?: unknown; traceId?: unknown }).trace_id ?? (meta as { traceId?: unknown }).traceId
  return typeof traceId === 'string' && traceId.trim() ? traceId.trim() : ''
}

function formatActionError(error: unknown) {
  if (isApiClientError(error)) {
    const details: string[] = []
    if (error.code) details.push(`代码: ${error.code}`)
    const reason = typeof error.details?.reason === 'string' ? error.details.reason : ''
    if (reason.trim()) details.push(`原因: ${reason.trim()}`)
    const degradation = error.details?.degradation_flags
    if (Array.isArray(degradation) && degradation.length) {
      details.push(`降级: ${degradation.map((v) => String(v || '').trim()).filter(Boolean).join('/')}`)
    }
    const traceId = getTraceId(error.meta)
    if (traceId) details.push(`追踪: ${traceId}`)
    return details.length ? `${error.message}（${details.join('，')}）` : error.message
  }
  if (error instanceof Error && error.message) return error.message
  return '未知错误'
}

export function useIngestActions(projectKey: string) {
  const queryClient = useQueryClient()
  const [actionPending, setActionPending] = useState(false)
  const [actionMessage, setActionMessage] = useState('等待操作')

  const runAction = async (name: string, fn: IngestActionFn) => {
    setActionPending(true)
    setActionMessage(`${name} 执行中...`)
    try {
      const result = await fn()
      const resultObj = toRecord(result)
      const taskId = typeof resultObj?.task_id === 'string' ? resultObj.task_id : null
      const resultStatus = typeof resultObj?.status === 'string' ? resultObj.status : ''
      const rejectedCount = toFiniteNumber(resultObj?.rejected_count)
      const insertedValid = toFiniteNumber(resultObj?.inserted_valid)
      const inserted = toFiniteNumber(resultObj?.inserted)
      const skipped = toFiniteNumber(resultObj?.skipped)
      const extractionStatus = typeof resultObj?.extraction_status === 'string' ? resultObj.extraction_status : ''
      const degradationFlags = toStringArray(resultObj?.degradation_flags)
      const docIdRaw = resultObj?.doc_id ?? resultObj?.document_id
      const docId = (typeof docIdRaw === 'string' || typeof docIdRaw === 'number') ? String(docIdRaw) : ''

      if (taskId) {
        setActionMessage(`${name} 已提交，任务 ID: ${taskId}`)
      } else if (resultStatus) {
        const extras: string[] = [`状态: ${resultStatus}`]
        if (extractionStatus) extras.push(`提取: ${extractionStatus}`)
        if (insertedValid != null) extras.push(`有效写入: ${insertedValid}`)
        if (inserted != null) extras.push(`写入: ${inserted}`)
        if (skipped != null) extras.push(`跳过: ${skipped}`)
        if (rejectedCount != null) extras.push(`拒绝: ${rejectedCount}`)
        if (docId) extras.push(`文档: ${docId}`)
        if (degradationFlags.length) extras.push(`降级: ${degradationFlags.slice(0, 2).join('/')}`)
        setActionMessage(`${name} 执行完成（${extras.join('，')}）`)
      } else {
        setActionMessage(`${name} 执行完成`)
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['source-items', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['site-entry-grouped', projectKey] }),
        queryClient.invalidateQueries({ queryKey: [...queryKeys.ingest.history(12), projectKey] }),
      ])

      return result
    } catch (error) {
      const message = `${name} 失败: ${formatActionError(error)}`
      setActionMessage(message)
      return null
    } finally {
      setActionPending(false)
    }
  }

  return {
    actionPending,
    actionMessage,
    runAction,
    syncSourceLibrary: () => runAction('同步来源库', syncSourceLibrary),
    runSourceLibrary: (payload: SourceLibraryRunPayload) =>
      runAction('运行来源库', () => {
        const activeProjectKey = getProjectKey()
        if (
          activeProjectKey &&
          projectKey &&
          normalizeProjectKey(activeProjectKey) !== normalizeProjectKey(projectKey)
        ) {
          throw new Error('project_key 不一致：当前激活项目与页面项目不匹配，请先切换项目。')
        }
        return runSourceLibrary({
          ...payload,
          project_key: payload.project_key ?? projectKey ?? activeProjectKey ?? null,
        })
      }),
    ingestPolicy: (payload: { state: string; source_hint?: string | null; async_mode: boolean }) =>
      runAction('政策采集', () => ingestPolicy(payload)),
    ingestPolicyRegulation: (payload: Record<string, unknown>) => runAction('政策法规采集', () => ingestPolicyRegulation(payload)),
    ingestMarket: (payload: Record<string, unknown>) => runAction('市场采集', () => ingestMarket(payload)),
    ingestSingleUrl: (payload: Parameters<typeof ingestSingleUrl>[0]) => runAction('单 URL 采集', () => ingestSingleUrl(payload)),
    ingestSocial: (payload: Record<string, unknown>) => runAction('舆情采集', () => ingestSocial(payload)),
    ingestCommodity: (payload: { limit: number; async_mode: boolean }) => runAction('商品采集', () => ingestCommodity(payload)),
    ingestEcom: (payload: { limit: number; async_mode: boolean }) => runAction('电商采集', () => ingestEcom(payload)),
  }
}

export default useIngestActions
