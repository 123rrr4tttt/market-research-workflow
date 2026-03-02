import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
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
import { isApiClientError } from '../lib/api/client'
import { queryKeys } from '../lib/queryKeys'

type IngestActionFn = () => Promise<unknown>

type SourceLibraryRunPayload = {
  item_key?: string | null
  handler_key?: string | null
  async_mode: boolean
  override_params: Record<string, unknown>
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
      const taskId =
        result &&
        typeof result === 'object' &&
        'task_id' in result &&
        typeof (result as { task_id?: unknown }).task_id === 'string'
          ? (result as { task_id?: string }).task_id
          : null

      const resultStatus =
        result &&
        typeof result === 'object' &&
        'status' in result &&
        typeof (result as { status?: unknown }).status === 'string'
          ? String((result as { status?: string }).status)
          : ''
      const rejectedCount =
        result &&
        typeof result === 'object' &&
        'rejected_count' in result &&
        Number.isFinite(Number((result as { rejected_count?: unknown }).rejected_count))
          ? Number((result as { rejected_count?: unknown }).rejected_count)
          : null
      const degradationRaw =
        result && typeof result === 'object' ? (result as { degradation_flags?: unknown }).degradation_flags : undefined
      const degradationFlags =
        Array.isArray(degradationRaw) ? degradationRaw.map((v) => String(v || '').trim()).filter(Boolean) : []

      if (taskId) {
        setActionMessage(`${name} 已提交，任务 ID: ${taskId}`)
      } else if (resultStatus) {
        const extras: string[] = [`状态: ${resultStatus}`]
        if (rejectedCount != null) extras.push(`拒绝: ${rejectedCount}`)
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
    runSourceLibrary: (payload: SourceLibraryRunPayload) => runAction('运行来源库', () => runSourceLibrary(payload)),
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
