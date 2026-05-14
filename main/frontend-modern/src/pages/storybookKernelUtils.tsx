import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import AdminLayerShell from '../app/kernel/AdminLayerShell'
import { getKernelModuleContract } from '../app/kernel/contracts'
import { buildLayerRouteHash } from '../app/kernel/routes'
import type { KernelModuleKey } from '../app/kernel/types'
import { type KernelRuntime } from '../app/kernel/useKernelRuntime'
import VisualizationLayerShell from '../app/kernel/VisualizationLayerShell'
import WorkbenchLayerShell from '../app/kernel/WorkbenchLayerShell'
import { applyThemeTokens } from '../app/platform/theme'

type StorybookAppProvidersProps = {
  children: ReactNode
}

type StorybookKernelShellProps = {
  moduleKey: KernelModuleKey
  projectKey?: string
  projectOptions?: string[]
  message?: string
}

function createStorybookQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

function createMutationStub<T>(): T {
  return {
    isPending: false,
    mutate: () => undefined,
  } as unknown as T
}

function createQueryStub<T>(data: T): { data: T; isFetching: false } {
  return {
    data,
    isFetching: false,
  }
}

function createStorybookRuntime({
  projectKey,
  projectOptions,
  message,
}: Required<StorybookKernelShellProps>): KernelRuntime {
  const projects = projectOptions.map((key) => ({ project_key: key }))
  return {
    projectKey,
    setProjectKey: () => undefined,
    pendingProjectKey: projectKey,
    setPendingProjectKey: () => undefined,
    message,
    setMessage: () => undefined,
    projects: createQueryStub(projects) as unknown as KernelRuntime['projects'],
    codexAuth: createQueryStub({
      authenticated: true,
      token_sink_authenticated: true,
      codex_oauth_enabled: true,
    }) as unknown as KernelRuntime['codexAuth'],
    projectOptions: projects,
    canActivatePendingProject: true,
    health: createQueryStub({ status: 'ok' }) as unknown as KernelRuntime['health'],
    envSettings: createQueryStub({
      DATABASE_URL: 'postgres://storybook',
      OPENAI_API_KEY: 'storybook-openai-key',
      NEWS_API_KEY: 'storybook-news-key',
      SERPAPI_KEY: 'storybook-serp-key',
    }) as unknown as KernelRuntime['envSettings'],
    status: {
      api: 'ok',
      llmReady: true,
      searchReady: true,
      newsReady: true,
      dbReady: true,
      codexReady: true,
      codexOauthEnabled: true,
    },
    activateMutation: createMutationStub<KernelRuntime['activateMutation']>(),
    injectInitialMutation: createMutationStub<KernelRuntime['injectInitialMutation']>(),
    navigateToModule: () => undefined,
  }
}

export function StorybookAppProviders({ children }: StorybookAppProvidersProps) {
  const [queryClient] = useState(createStorybookQueryClient)

  useEffect(() => {
    applyThemeTokens('dark')
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <div style={{ minHeight: '100vh' }}>{children}</div>
    </QueryClientProvider>
  )
}

export function StorybookKernelShell({
  moduleKey,
  projectKey = 'demo-proj',
  projectOptions = ['demo-proj', 'alpha-lab', 'policy-hub'],
  message = '',
}: StorybookKernelShellProps) {
  const runtime = useMemo(
    () => createStorybookRuntime({ moduleKey, projectKey, projectOptions, message }),
    [message, moduleKey, projectKey, projectOptions],
  )
  const contract = getKernelModuleContract(moduleKey)

  useEffect(() => {
    const previousHash = window.location.hash
    const nextHash = buildLayerRouteHash(moduleKey)
    if (previousHash !== nextHash) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`)
    }
    return () => {
      window.history.replaceState(
        null,
        '',
        `${window.location.pathname}${window.location.search}${previousHash || ''}`,
      )
    }
  }, [moduleKey])

  const content = (() => {
    if (contract.layerId === 'A') return <WorkbenchLayerShell activeModule={moduleKey} runtime={runtime} />
    if (contract.layerId === 'B') return <VisualizationLayerShell activeModule={moduleKey} runtime={runtime} />
    return <AdminLayerShell activeModule={moduleKey} runtime={runtime} />
  })()

  return <StorybookAppProviders>{content}</StorybookAppProviders>
}
