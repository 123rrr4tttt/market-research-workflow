import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { activateProject, getEnvSettings, getHealth, getProjectKey, injectInitialProject, listProjects } from '../../lib/api'
import { queryKeys } from '../../lib/queryKeys'
import { buildLayerRouteHash } from './routes'
import type { KernelModuleKey } from './types'

export function useKernelRuntime() {
  const queryClient = useQueryClient()
  const [projectKey, setProjectKey] = useState(getProjectKey())
  const [pendingProjectKey, setPendingProjectKey] = useState(getProjectKey())
  const [message, setMessage] = useState('')

  const health = useQuery({ queryKey: queryKeys.health.all, queryFn: getHealth })
  const envSettings = useQuery({
    queryKey: queryKeys.config.envStatus(),
    queryFn: getEnvSettings,
    refetchInterval: 120000,
    refetchIntervalInBackground: true,
  })
  const projects = useQuery({ queryKey: queryKeys.projects.all(), queryFn: listProjects })

  const activateMutation = useMutation({
    mutationFn: activateProject,
    onSuccess: (next) => {
      setProjectKey(next)
      setPendingProjectKey(next)
      setMessage(`已切换到项目: ${next}`)
    },
    onError: (error) => {
      setMessage(`切换失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const injectInitialMutation = useMutation({
    mutationFn: async (targetProjectKey: string) => {
      const target = String(targetProjectKey || '').trim()
      if (!target) throw new Error('请选择目标项目')
      if (target === 'demo_proj') throw new Error('demo_proj 是模板项目，不允许作为注入目标')
      return injectInitialProject({
        source_project_key: 'demo_proj',
        project_key: target,
        overwrite: true,
        activate: true,
      })
    },
    onSuccess: async (result) => {
      const next = String(result?.project_key || '').trim()
      if (next) {
        setProjectKey(next)
        setPendingProjectKey(next)
      }
      setMessage(`初始化注入完成: ${next || pendingProjectKey}`)
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() })
    },
    onError: (error) => {
      setMessage(`初始化注入失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  useEffect(() => {
    setPendingProjectKey(projectKey)
  }, [projectKey])

  const status = useMemo(
    () => {
      const keyReady = (key: string) => Boolean(String(envSettings.data?.[key] || '').trim())

      return {
        api: health.data?.status || 'loading',
        llmReady: keyReady('OPENAI_API_KEY') || keyReady('AZURE_API_KEY'),
        searchReady: keyReady('SERPAPI_KEY') || keyReady('GOOGLE_SEARCH_API_KEY') || keyReady('SERPSTACK_KEY'),
        newsReady: keyReady('NEWS_API_KEY'),
        dbReady: keyReady('DATABASE_URL'),
      }
    },
    [envSettings.data, health.data?.status],
  )

  const navigateToModule = (moduleKey: KernelModuleKey) => {
    const nextHash = buildLayerRouteHash(moduleKey)
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash
    }
  }

  return {
    projectKey,
    setProjectKey,
    pendingProjectKey,
    setPendingProjectKey,
    message,
    setMessage,
    projects,
    health,
    envSettings,
    status,
    activateMutation,
    injectInitialMutation,
    navigateToModule,
  }
}

export type KernelRuntime = ReturnType<typeof useKernelRuntime>
