import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getAgentBatchEvents,
  getAgentBatchJob,
  ingestCommodity,
  ingestEcom,
  ingestMarket,
  ingestPolicyRegulation,
  ingestSingleUrl,
  ingestDataApi,
  listAgentBatchItems,
  retryAgentBatchJob,
  runSourceLibrary,
  submitAgentBatchJob,
  syncSourceLibrary,
  validateAgentBatchRuleSet,
} from '../lib/api'
import { isApiClientError } from '../lib/api/client'
import { queryKeys } from '../lib/queryKeys'

type SourceLibraryRunPayload = {
  item_key?: string | null
  handler_key?: string | null
  source_mode?: string | null
  async_mode: boolean
  override_params: Record<string, unknown>
}

type AgentBatchSubmitPayload = Parameters<typeof submitAgentBatchJob>[0]
type AgentBatchRetryPayload = Parameters<typeof retryAgentBatchJob>[1]
type AgentBatchRuleSetValidatePayload = Parameters<typeof validateAgentBatchRuleSet>[0]
export type IngestActionStatusState = {
  phase: 'idle' | 'running' | 'submitted' | 'completed' | 'failed'
  name: string
  source?: string
  message: string
  status?: string
  submissionId?: string
  taskId?: string
  errorCode?: string
  reason?: string
  degradationFlags: string[]
  traceId?: string
  traceChain?: {
    contractVersion?: string
    traceId?: string
    submissionId?: string
    taskId?: string
    retrievalRunId?: string
    provider?: string
    fallbackUsed?: string
    indexBackend?: string
    knownLimitations: string[]
  }
}

const defaultActionStatus: IngestActionStatusState = {
  phase: 'idle',
  name: '等待操作',
  message: '等待操作',
  degradationFlags: [],
}

function getTraceId(meta: unknown): string {
  if (!meta || typeof meta !== 'object') return ''
  const traceId = (meta as { trace_id?: unknown; traceId?: unknown }).trace_id ?? (meta as { traceId?: unknown }).traceId
  return typeof traceId === 'string' && traceId.trim() ? traceId.trim() : ''
}

function getStringField(value: unknown, field: string): string {
  if (!value || typeof value !== 'object') return ''
  const raw = (value as Record<string, unknown>)[field]
  return typeof raw === 'string' && raw.trim() ? raw.trim() : ''
}

function getNumberField(value: unknown, field: string): number | null {
  if (!value || typeof value !== 'object') return null
  const raw = (value as Record<string, unknown>)[field]
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function getStringListField(value: unknown, field: string): string[] {
  if (!value || typeof value !== 'object') return []
  const raw = (value as Record<string, unknown>)[field]
  if (!Array.isArray(raw)) return []
  return raw.map((item) => String(item || '').trim()).filter(Boolean)
}

function getRecordField(value: unknown, field: string): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') return null
  const raw = (value as Record<string, unknown>)[field]
  return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw as Record<string, unknown> : null
}

function buildTraceChain(value: unknown): IngestActionStatusState['traceChain'] | undefined {
  const traceChain = getRecordField(value, 'trace_chain')
  if (!traceChain) return undefined
  const providerTrace = getRecordField(traceChain, 'provider_trace')
  const fallback = getRecordField(traceChain, 'fallback')
  const indexFreshness = getRecordField(traceChain, 'index_freshness')
  const knownLimitations = getStringListField(traceChain, 'known_limitations')
  const fallbackUsedRaw = fallback && 'used' in fallback ? fallback.used : undefined
  const fallbackUsed = typeof fallbackUsedRaw === 'boolean' ? String(fallbackUsedRaw) : String(fallbackUsedRaw || '').trim()

  return {
    contractVersion: getStringField(traceChain, 'contract_version'),
    traceId: getStringField(traceChain, 'trace_id'),
    submissionId: getStringField(traceChain, 'submission_id'),
    taskId: getStringField(traceChain, 'task_id'),
    retrievalRunId: getStringField(traceChain, 'retrieval_run_id'),
    provider: providerTrace ? getStringField(providerTrace, 'provider') : '',
    fallbackUsed,
    indexBackend: indexFreshness ? getStringField(indexFreshness, 'backend') : '',
    knownLimitations,
  }
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
  const [actionStatus, setActionStatus] = useState<IngestActionStatusState>(defaultActionStatus)

  const runAction = async <T>(name: string, fn: () => Promise<T>): Promise<T | null> => {
    setActionPending(true)
    setActionMessage(`${name} 执行中...`)
    setActionStatus({
      phase: 'running',
      name,
      source: name,
      message: `${name} 执行中...`,
      degradationFlags: [],
    })
    try {
      const result = await fn()
      const resultStatus = getStringField(result, 'status')
      const errorCode = getStringField(result, 'error_code')
      const reason = getStringField(result, 'reason')
      const traceChain = buildTraceChain(result)
      const submissionId = getStringField(result, 'submission_id') || traceChain?.submissionId || ''
      const taskId = getStringField(result, 'task_id') || getStringField(result, 'process_id') || traceChain?.taskId || ''
      const traceId = getStringField(result, 'trace_id') || traceChain?.traceId || ''
      const rejectedCount = getNumberField(result, 'rejected_count')
      const degradationFlags = getStringListField(result, 'degradation_flags')
      const submittedId = taskId || submissionId
      const phase: IngestActionStatusState['phase'] = submittedId ? 'submitted' : 'completed'

      let nextMessage = `${name} 执行完成`
      if (submittedId) {
        const idParts = [
          taskId ? `任务 ID: ${taskId}` : '',
          submissionId ? `submission_id: ${submissionId}` : '',
        ].filter(Boolean)
        nextMessage = `${name} 已提交，${idParts.join('，')}`
      } else if (resultStatus) {
        const extras: string[] = [`状态: ${resultStatus}`]
        if (rejectedCount != null) extras.push(`拒绝: ${rejectedCount}`)
        if (degradationFlags.length) extras.push(`降级: ${degradationFlags.slice(0, 2).join('/')}`)
        nextMessage = `${name} 执行完成（${extras.join('，')}）`
      }
      setActionMessage(nextMessage)
      setActionStatus({
        phase,
        name,
        source: name,
        message: nextMessage,
        status: resultStatus || (submittedId ? 'submitted' : 'completed'),
        submissionId: submissionId || undefined,
        taskId: taskId || undefined,
        errorCode: errorCode || undefined,
        reason: reason || undefined,
        degradationFlags,
        traceId: traceId || undefined,
        traceChain,
      })

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.items(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.siteEntryGrouped(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.ingest.historyByProject(projectKey, 12) }),
      ])

      return result as T
    } catch (error) {
      const message = `${name} 失败: ${formatActionError(error)}`
      setActionMessage(message)
      setActionStatus({
        phase: 'failed',
        name,
        source: name,
        message,
        status: 'failed',
        errorCode: isApiClientError(error) ? error.code : undefined,
        reason: isApiClientError(error) && typeof error.details?.reason === 'string' ? error.details.reason : undefined,
        degradationFlags:
          isApiClientError(error) && Array.isArray(error.details?.degradation_flags)
            ? error.details.degradation_flags.map((item) => String(item || '').trim()).filter(Boolean)
            : [],
        traceId: isApiClientError(error) ? getTraceId(error.meta) || undefined : undefined,
      })
      return null
    } finally {
      setActionPending(false)
    }
  }

  return {
    actionPending,
    actionMessage,
    actionStatus,
    runAction,
    syncSourceLibrary: () => runAction('同步来源库', syncSourceLibrary),
    runSourceLibrary: (payload: SourceLibraryRunPayload) => runAction('运行来源库', () => runSourceLibrary(payload)),
    ingestPolicyRegulation: (payload: Record<string, unknown>) => runAction('法规类型文档导入', () => ingestPolicyRegulation(payload)),
    ingestMarket: (payload: Record<string, unknown>) => runAction('市场采集', () => ingestMarket(payload)),
    ingestSingleUrl: (payload: Parameters<typeof ingestSingleUrl>[0]) => runAction('单 URL 采集', () => ingestSingleUrl(payload)),
    ingestDataApi: (payload: Record<string, unknown>) => runAction('数据API采集', () => ingestDataApi(payload)),
    ingestCommodity: (payload: { limit: number; async_mode: boolean }) => runAction('商品采集', () => ingestCommodity(payload)),
    ingestEcom: (payload: { limit: number; async_mode: boolean }) => runAction('电商采集', () => ingestEcom(payload)),
    submitAgentBatchJob: (payload: AgentBatchSubmitPayload) => runAction('提交批量采集任务', () => submitAgentBatchJob(payload)),
    getAgentBatchJob,
    listAgentBatchItems,
    getAgentBatchEvents,
    retryAgentBatchJob: (jobId: string, payload?: AgentBatchRetryPayload) =>
      runAction('重试批量采集任务', () => retryAgentBatchJob(jobId, payload || {})),
    validateAgentBatchRuleSet: (payload: AgentBatchRuleSetValidatePayload) =>
      runAction('校验规则集', () => validateAgentBatchRuleSet(payload)),
  }
}

export default useIngestActions
