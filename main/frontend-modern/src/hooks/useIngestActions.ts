import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ingestCommodity,
  ingestEcom,
  ingestMarket,
  ingestPolicy,
  ingestPolicyRegulation,
  ingestSocial,
  runSourceLibrary,
  syncSourceLibrary,
} from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

type IngestActionFn = () => Promise<unknown>

type SourceLibraryRunPayload = {
  item_key?: string | null
  handler_key?: string | null
  async_mode: boolean
  override_params: Record<string, unknown>
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

      setActionMessage(taskId ? `${name} 已提交，任务 ID: ${taskId}` : `${name} 执行完成`)

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['source-items', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['site-entry-grouped', projectKey] }),
        queryClient.invalidateQueries({ queryKey: [...queryKeys.ingest.history(12), projectKey] }),
      ])

      return result
    } catch (error) {
      const message = `${name} 失败: ${error instanceof Error ? error.message : '未知错误'}`
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
    ingestSocial: (payload: Record<string, unknown>) => runAction('舆情采集', () => ingestSocial(payload)),
    ingestCommodity: (payload: { limit: number; async_mode: boolean }) => runAction('商品采集', () => ingestCommodity(payload)),
    ingestEcom: (payload: { limit: number; async_mode: boolean }) => runAction('电商采集', () => ingestEcom(payload)),
  }
}

export default useIngestActions
