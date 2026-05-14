import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  activateProject,
  CODEX_AUTH_REQUIRED_EVENT,
  getCodexAuthStatus,
  getEnvSettings,
  getHealth,
  getProjectKey,
  injectInitialProject,
  listProjects,
  setProjectKey as persistProjectKey,
} from '../../lib/api'
import { queryKeys } from '../../lib/queryKeys'
import { buildProjectOptions, hasProject, isReservedProjectKey, resolveBootstrapTarget, resolveEffectiveProjectKey } from './projectKeys'
import { buildLayerRouteHash } from './routes'
import type { KernelModuleKey } from './types'

export function useKernelRuntime() {
  const queryClient = useQueryClient()
  const [projectKey, setProjectKey] = useState(getProjectKey())
  const [pendingProjectKey, setPendingProjectKey] = useState(resolveBootstrapTarget(getProjectKey()))
  const [message, setMessage] = useState('')

  const health = useQuery({ queryKey: queryKeys.health.all, queryFn: getHealth })
  const envSettings = useQuery({
    queryKey: queryKeys.config.envStatus(),
    queryFn: getEnvSettings,
    refetchInterval: 120000,
    refetchIntervalInBackground: true,
  })
  const projects = useQuery({ queryKey: queryKeys.projects.all(), queryFn: listProjects })
  const codexAuth = useQuery({
    queryKey: queryKeys.auth.codex(),
    queryFn: getCodexAuthStatus,
    refetchInterval: 60000,
    refetchIntervalInBackground: true,
  })
  const projectOptions = buildProjectOptions({
    activeProjectKey: projectKey,
    pendingProjectKey,
    projects: projects.data,
  })
  const canActivatePendingProject = hasProject(projects.data, pendingProjectKey)

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
      const target = resolveBootstrapTarget(targetProjectKey)
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
    setPendingProjectKey(resolveBootstrapTarget(projectKey))
  }, [projectKey])

  useEffect(() => {
    if (!projects.data) return
    const effectiveProjectKey = resolveEffectiveProjectKey({
      projects: projects.data,
      currentProjectKey: projectKey,
      pendingProjectKey,
    })
    if (effectiveProjectKey && effectiveProjectKey !== projectKey) {
      const next = persistProjectKey(effectiveProjectKey)
      setProjectKey(next)
      setPendingProjectKey(next)
      return
    }
    if (!projects.data.length && isReservedProjectKey(pendingProjectKey)) {
      setPendingProjectKey(resolveBootstrapTarget(pendingProjectKey))
    }
  }, [pendingProjectKey, projectKey, projects.data])

  useEffect(() => {
    const handleCodexAuthRequired = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail : null
      const reasonCode = String(detail?.reasonCode || '').trim()
      setMessage(`Codex 认证失效${reasonCode ? ` (${reasonCode})` : ''}，请点击右上角 CODEX login`)
      void codexAuth.refetch()
    }

    window.addEventListener(CODEX_AUTH_REQUIRED_EVENT, handleCodexAuthRequired)
    return () => window.removeEventListener(CODEX_AUTH_REQUIRED_EVENT, handleCodexAuthRequired)
  }, [codexAuth])

  const status = useMemo(
    () => {
      const keyReady = (key: string) => Boolean(String(envSettings.data?.[key] || '').trim())

      return {
        api: health.data?.status || 'loading',
        llmReady: keyReady('OPENAI_API_KEY') || keyReady('AZURE_API_KEY'),
        searchReady: keyReady('SERPAPI_KEY') || keyReady('GOOGLE_SEARCH_API_KEY') || keyReady('SERPSTACK_KEY'),
        newsReady: keyReady('NEWS_API_KEY'),
        dbReady: keyReady('DATABASE_URL'),
        codexReady: Boolean(codexAuth.data?.authenticated || codexAuth.data?.token_sink_authenticated),
        codexOauthEnabled: codexAuth.data?.codex_oauth_enabled !== false,
      }
    },
    [codexAuth.data, envSettings.data, health.data?.status],
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
    codexAuth,
    projectOptions,
    canActivatePendingProject,
    health,
    envSettings,
    status,
    activateMutation,
    injectInitialMutation,
    navigateToModule,
  }
}

export type KernelRuntime = ReturnType<typeof useKernelRuntime>
