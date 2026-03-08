import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelTask, getProcessStats, getProcessTaskDetail, getProcessTaskLogs, listProcessHistory, listProcessTasks } from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

type UseProcessDataParams = {
  projectKey: string
  selectedTaskId: string | null
  autoRefreshEnabled: boolean
  refreshIntervalSec: number
}

export function useProcessData({ projectKey, selectedTaskId, autoRefreshEnabled, refreshIntervalSec }: UseProcessDataParams) {
  const queryClient = useQueryClient()
  const refreshIntervalMs = autoRefreshEnabled ? Math.max(3, refreshIntervalSec) * 1000 : false

  const processStats = useQuery({
    queryKey: queryKeys.process.statsByProject(projectKey),
    queryFn: getProcessStats,
    enabled: Boolean(projectKey),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const processList = useQuery({
    queryKey: queryKeys.process.listByProject(projectKey, 40),
    queryFn: () => listProcessTasks(40),
    enabled: Boolean(projectKey),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const processHistory = useQuery({
    queryKey: queryKeys.process.historyByProject(projectKey, 50),
    queryFn: () => listProcessHistory(50),
    enabled: Boolean(projectKey),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const taskDetail = useQuery({
    queryKey: queryKeys.process.detailByProject(selectedTaskId || '', projectKey),
    queryFn: () => getProcessTaskDetail(String(selectedTaskId)),
    enabled: Boolean(projectKey && selectedTaskId),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const taskLogs = useQuery({
    queryKey: queryKeys.process.logsByProject(selectedTaskId || '', projectKey, 200),
    queryFn: () => getProcessTaskLogs(String(selectedTaskId), 200),
    enabled: Boolean(projectKey && selectedTaskId),
    refetchInterval: refreshIntervalMs,
    refetchIntervalInBackground: true,
  })

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.process.statsByProject(projectKey) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.process.listByProject(projectKey, 40) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.process.historyByProject(projectKey, 50) }),
      queryClient.invalidateQueries({ queryKey: [...queryKeys.process.all(), 'detail'] }),
      queryClient.invalidateQueries({ queryKey: [...queryKeys.process.all(), 'logs'] }),
    ])
  }

  const refreshSelectedTask = async (taskId: string | null) => {
    if (!taskId) return
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.process.detailByProject(taskId, projectKey) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.process.logsByProject(taskId, projectKey, 200) }),
    ])
  }

  const refreshHistory = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.process.historyByProject(projectKey, 50) })
  }

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => cancelTask(taskId, false),
    onSuccess: async () => {
      await refreshAll()
    },
  })

  const cancelTasks = async (taskIds: string[]) => {
    for (const taskId of taskIds) {
      try {
        await cancelTask(taskId, false)
      } catch {
        // continue cancelling remaining tasks
      }
    }
    await refreshAll()
  }

  const isRefreshing = processStats.isFetching || processList.isFetching || processHistory.isFetching || taskDetail.isFetching || taskLogs.isFetching

  return {
    processStats,
    processList,
    processHistory,
    taskDetail,
    taskLogs,
    cancelMutation,
    cancelTasks,
    refreshAll,
    refreshSelectedTask,
    refreshHistory,
    isRefreshing,
  }
}

export default useProcessData
