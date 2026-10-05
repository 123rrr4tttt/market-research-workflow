import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { getProcessTaskDetail } from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

export type TaskSubmissionReceipt = {
  taskId: string
  traceId?: string
  action: string
  projectKey: string
}

export function isTerminalTaskStatus(status?: string) {
  return ['SUCCESS', 'FAILURE', 'REVOKED', 'COMPLETED', 'FAILED', 'CANCELED', 'CANCELLED'].includes(String(status || '').toUpperCase())
}

export function useTaskSubmission({ projectKey, invalidateOnSettled }: {
  projectKey: string
  invalidateOnSettled: readonly QueryKey[]
}) {
  const queryClient = useQueryClient()
  const [lastReceipt, setLastReceipt] = useState<TaskSubmissionReceipt | null>(null)
  const receipt = lastReceipt?.projectKey === projectKey ? lastReceipt : null
  const settledTasks = useRef(new Set<string>())
  const consumerKeys = useRef(invalidateOnSettled)
  useEffect(() => { consumerKeys.current = invalidateOnSettled }, [invalidateOnSettled])

  const detail = useQuery({
    queryKey: queryKeys.process.detailByProject(receipt?.taskId || '', projectKey),
    queryFn: () => getProcessTaskDetail(String(receipt?.taskId)),
    enabled: Boolean(receipt),
    refetchInterval: (query) => isTerminalTaskStatus(query.state.data?.status) ? false : 3000,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (!receipt || !isTerminalTaskStatus(detail.data?.status)) return
    const identity = `${receipt.projectKey}/${receipt.taskId}`
    if (settledTasks.current.has(identity)) return
    settledTasks.current.add(identity)
    void queryClient.invalidateQueries({ queryKey: queryKeys.process.all() })
    for (const queryKey of consumerKeys.current) void queryClient.invalidateQueries({ queryKey })
  }, [receipt, detail.data?.status, queryClient])

  const track = (result: unknown, action: string) => {
    const payload = result && typeof result === 'object' ? result as Record<string, unknown> : {}
    const taskId = typeof payload.task_id === 'string' ? payload.task_id.trim() : ''
    if (!taskId || payload.async === false) {
      setLastReceipt(null)
      return false
    }
    setLastReceipt({ taskId, action, projectKey, traceId: typeof payload.trace_id === 'string' ? payload.trace_id : undefined })
    void queryClient.invalidateQueries({ queryKey: queryKeys.process.all() })
    return true
  }

  return {
    receipt,
    taskDetail: receipt ? detail.data : undefined,
    readbackError: receipt && detail.isError ? detail.error.message : '',
    isReading: Boolean(receipt && detail.isFetching),
    track,
    refresh: async () => { await detail.refetch() },
  }
}

export type TaskSubmissionState = ReturnType<typeof useTaskSubmission>
