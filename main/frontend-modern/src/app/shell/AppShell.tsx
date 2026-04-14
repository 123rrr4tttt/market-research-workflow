import { Suspense, useEffect, useState, type KeyboardEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import FigmaSideNav from '../../components/FigmaSideNav'
import { activateProject, getDeepHealth, getEnvSettings, getHealth, getProjectKey, injectInitialProject, listProjects } from '../../lib/api'
import { getLocalJson, setLocalJson } from '../../lib/localStore'
import { queryKeys } from '../../lib/queryKeys'
import type { NavMode } from '../kernel/types'
import { defaultNavMode, hashByMode } from '../navigation'
import { translate, useAppLocale } from '../platform/i18n'
import { getModuleDescriptor, verifyRegistryHashCompatibility } from '../platform/modules'
import { applyThemeTokens, useAppTheme } from '../platform/theme'
import { renderKernelModuleContent } from '../kernel/renderKernelModuleContent'
import { resolveKernelRoute } from '../kernel/routes'
import { resolveInteractionSurface } from '../topology/contracts'
import { resolveSurfaceSwitchTarget, updateLastModeBySurface, type SurfaceLastModeMap } from '../topology/navigationSwitching'
import { SHARED_CONTRACT_NOTE, SURFACE_SWITCH_RULES } from '../topology/sharedPlatformContract'
import type { InteractionSurface } from '../topology/surfaces'
type StatusIntentMode = 'sysSettings' | 'sysLlm' | 'sysCrawler' | 'sysBackend'
type StatusIntentGuide = 'llm' | 'search' | 'news' | 'db' | 'es'
type StatusNavIntent = {
  mode: StatusIntentMode
  focusField?: string
  guide?: StatusIntentGuide
  ts: number
}

const SHELL_PREFS_KEY = 'app_shell_prefs_v1'
const STATUS_NAV_INTENT_KEY = 'app_status_nav_intent_v1'

function resolveShellModeFromHash(rawHash: string, fallbackMode: NavMode): NavMode {
  const route = resolveKernelRoute(rawHash)
  if (route.source === 'unknown') return fallbackMode
  return route.moduleKey
}

export default function AppShell() {
  const shellPrefs = getLocalJson<{ lastMode?: NavMode; pendingProjectKey?: string; lastModeBySurface?: SurfaceLastModeMap }>(SHELL_PREFS_KEY, {})
  const defaultMode = resolveShellModeFromHash(window.location.hash, shellPrefs.lastMode || defaultNavMode)
  const defaultSurface = resolveInteractionSurface(defaultMode)
  const queryClient = useQueryClient()
  const [viewMode, setViewMode] = useState<NavMode>(defaultMode)
  const [activeSurface, setActiveSurface] = useState<InteractionSurface>(defaultSurface)
  const [lastModeBySurface, setLastModeBySurface] = useState<SurfaceLastModeMap>(() =>
    updateLastModeBySurface(shellPrefs.lastModeBySurface || {}, defaultMode),
  )
  const locale = useAppLocale()
  const appTheme = useAppTheme()
  const [projectKey, setProjectKeyState] = useState(getProjectKey())
  const [pendingProjectKey, setPendingProjectKey] = useState(() => shellPrefs.pendingProjectKey || projectKey)
  const [switchMessage, setSwitchMessage] = useState('')

  const health = useQuery({ queryKey: queryKeys.health.all, queryFn: getHealth })
  const deepHealth = useQuery({
    queryKey: queryKeys.health.deep(),
    queryFn: getDeepHealth,
    refetchInterval: 60000,
    refetchIntervalInBackground: true,
  })
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
      setProjectKeyState(next)
      setPendingProjectKey(next)
      setSwitchMessage(`已切换到项目: ${next}`)
    },
    onError: (error) => {
      setSwitchMessage(`切换失败: ${error instanceof Error ? error.message : '未知错误'}`)
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
        setProjectKeyState(next)
        setPendingProjectKey(next)
      }
      setSwitchMessage(`初始化注入完成: ${next || pendingProjectKey}`)
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() })
    },
    onError: (error) => {
      setSwitchMessage(`初始化注入失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const pageTitle = translate(locale, getModuleDescriptor(viewMode).titleKey, viewMode)
  const isLlmDesignerMode = viewMode === 'flowLlmNodeDesign'

  const keyReady = (key: string) => Boolean(String(envSettings.data?.[key] || '').trim())
  const llmKeyReady = keyReady('OPENAI_API_KEY') || keyReady('AZURE_API_KEY')
  const searchKeyReady = keyReady('SERPAPI_KEY') || keyReady('GOOGLE_SEARCH_API_KEY') || keyReady('SERPSTACK_KEY')
  const newsKeyReady = keyReady('NEWS_API_KEY')
  const dbConfigReady = keyReady('DATABASE_URL')

  const statusChipClass = (value?: string) => {
    const normalized = String(value || '').toLowerCase()
    if (!normalized) return 'chip chip-warn'
    if (normalized.includes('ok')) return 'chip chip-ok'
    if (normalized.includes('degraded') || normalized.includes('loading')) return 'chip chip-warn'
    return 'chip chip-danger'
  }

  const openIntentPage = ({
    mode,
    focusField,
    guide,
  }: {
    mode: StatusIntentMode
    focusField?: string
    guide?: StatusIntentGuide
  }) => {
    setLocalJson<StatusNavIntent>(STATUS_NAV_INTENT_KEY, {
      mode,
      focusField,
      guide,
      ts: 0,
    })
    handleModeChange(mode)
  }

  const onChipKeyDown = (
    event: KeyboardEvent<HTMLSpanElement>,
    action: () => void,
  ) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    action()
  }

  const persistShellPrefs = (mode: NavMode, pending: string, lastBySurface: SurfaceLastModeMap) => {
    setLocalJson(SHELL_PREFS_KEY, {
      lastMode: mode,
      pendingProjectKey: pending,
      lastModeBySurface: lastBySurface,
    })
  }

  const modernContent = renderKernelModuleContent({
    moduleKey: viewMode,
    projectKey,
    onProjectChange: setProjectKeyState,
    shellMode: 'legacy-shell',
  })

  useEffect(() => {
    const syncModeFromHash = () => {
      const nextMode = resolveShellModeFromHash(window.location.hash, defaultNavMode)
      setViewMode((prev) => (prev === nextMode ? prev : nextMode))
      setActiveSurface(resolveInteractionSurface(nextMode))
      setLastModeBySurface((prev) => updateLastModeBySurface(prev, nextMode))
    }

    window.addEventListener('hashchange', syncModeFromHash)
    syncModeFromHash()
    return () => window.removeEventListener('hashchange', syncModeFromHash)
  }, [])

  useEffect(() => {
    setPendingProjectKey(projectKey)
  }, [projectKey])

  useEffect(() => {
    const result = verifyRegistryHashCompatibility()
    if (!result.isCompatible) {
      console.warn('module registry hash compatibility mismatch', result.mismatchedModes)
    }
  }, [])

  useEffect(() => {
    applyThemeTokens(appTheme)
  }, [appTheme])

  const handleModeChange = (mode: NavMode) => {
    const nextLastModeBySurface = updateLastModeBySurface(lastModeBySurface, mode)
    setLastModeBySurface(nextLastModeBySurface)
    setActiveSurface(resolveInteractionSurface(mode))
    if (mode === 'flowLlmNodeDesign') {
      persistShellPrefs(mode, pendingProjectKey, nextLastModeBySurface)
      const nextHash = hashByMode.flowLlmNodeDesign
      const basePath = String(import.meta.env.BASE_URL || '/').trim() || '/'
      const nextUrl = new URL(basePath.startsWith('/') ? basePath : `/${basePath}`, window.location.origin)
      nextUrl.hash = nextHash
      const opened = window.open(nextUrl.toString(), '_blank', 'noopener,noreferrer')
      if (!opened) window.location.assign(nextUrl.toString())
      return
    }
    setViewMode(mode)
    persistShellPrefs(mode, pendingProjectKey, nextLastModeBySurface)
    const nextHash = hashByMode[mode]
    if (nextHash && window.location.hash !== nextHash) window.location.hash = nextHash
  }

  const handleSurfaceChange = (surface: InteractionSurface) => {
    if (surface === activeSurface) return
    const nextMode = resolveSurfaceSwitchTarget(surface, lastModeBySurface)
    const surfaceLabel = surface === 'workbench' ? 'Workbench' : 'Management'
    const retainNote = SURFACE_SWITCH_RULES[surface].retain.join(' / ')
    const resetNote = SURFACE_SWITCH_RULES[surface].reset.join(' / ')
    setSwitchMessage(`切换到 ${surfaceLabel}；保留: ${retainNote}；重置: ${resetNote}`)
    handleModeChange(nextMode)
  }

  useEffect(() => {
    persistShellPrefs(viewMode, pendingProjectKey, lastModeBySurface)
  }, [viewMode, pendingProjectKey, lastModeBySurface])

  return (
    <div className={`layout-root ${isLlmDesignerMode ? 'layout-root--immersive' : ''}`}>
      <section className={`panel app-status-bar app-global-status is-${appTheme}`}>
        <div className="app-status-bar__top">
          <span className="status-line app-status-bar__current">当前项目: {projectKey}</span>
          <label className="app-status-bar__project">
            <span>切换项目</span>
            <select
              value={pendingProjectKey}
              onChange={(e) => {
                setPendingProjectKey(e.target.value)
                setSwitchMessage('')
              }}
              disabled={activateMutation.isPending}
            >
              {!projects.data?.find((item) => item.project_key === projectKey) ? <option value={projectKey}>{projectKey}</option> : null}
              {(projects.data || []).map((item) => (
                <option key={item.project_key} value={item.project_key}>{item.project_key}</option>
              ))}
            </select>
          </label>
          <button
            onClick={() => activateMutation.mutate(pendingProjectKey)}
            disabled={activateMutation.isPending || !pendingProjectKey || pendingProjectKey === projectKey}
          >
            {activateMutation.isPending ? '切换中...' : '确认切换项目'}
          </button>
          <button
            onClick={() => {
              const target = String(pendingProjectKey || '').trim()
              if (!target) return
              const ok = window.confirm(`将从 demo_proj 注入初始化到项目 ${target}（覆盖模式）并激活，是否继续？`)
              if (!ok) return
              injectInitialMutation.mutate(target)
            }}
            disabled={injectInitialMutation.isPending || !pendingProjectKey}
            title="从内置存档模板（demo_proj）注入初始化到当前目标项目；缺失时后端会自动引导模板"
          >
            {injectInitialMutation.isPending ? '注入中...' : '注入初始化项目'}
          </button>
          <button
            onClick={() => handleModeChange('sysProjects')}
            title="跳转到项目管理页面创建新项目"
          >
            创建新项目
          </button>
          {switchMessage ? <span className="status-line app-status-bar__message">{switchMessage}</span> : null}
        </div>
        <div className="app-status-bar__chips">
          <span
            className={statusChipClass(health.data?.status)}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysBackend' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysBackend' }))}
            title="查看后端健康与错误状态"
          >
            API {health.data?.status || 'loading'}
          </span>
          <span
            className={statusChipClass(deepHealth.data?.database)}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysSettings', focusField: 'DATABASE_URL', guide: 'db' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysSettings', focusField: 'DATABASE_URL', guide: 'db' }))}
            title="跳转数据库连接配置"
          >
            DB {deepHealth.data?.database || 'loading'}
          </span>
          <span
            className={statusChipClass(deepHealth.data?.elasticsearch)}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysSettings', focusField: 'ES_URL', guide: 'es' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysSettings', focusField: 'ES_URL', guide: 'es' }))}
            title="跳转 Elasticsearch 配置"
          >
            ES {deepHealth.data?.elasticsearch || 'loading'}
          </span>
          <span
            className={llmKeyReady ? 'chip chip-ok' : 'chip chip-danger'}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysLlm', focusField: 'OPENAI_API_KEY', guide: 'llm' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysLlm', focusField: 'OPENAI_API_KEY', guide: 'llm' }))}
            title="跳转 LLM Key 设置与指引"
          >
            LLM key {llmKeyReady ? 'ready' : 'missing'}
          </span>
          <span
            className={searchKeyReady ? 'chip chip-ok' : 'chip chip-warn'}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysSettings', focusField: 'SERPAPI_KEY', guide: 'search' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysSettings', focusField: 'SERPAPI_KEY', guide: 'search' }))}
            title="跳转搜索 API Key 设置与安装指引"
          >
            Search key {searchKeyReady ? 'ready' : 'missing'}
          </span>
          <span
            className={newsKeyReady ? 'chip chip-ok' : 'chip chip-warn'}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysSettings', focusField: 'NEWS_API_KEY', guide: 'news' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysSettings', focusField: 'NEWS_API_KEY', guide: 'news' }))}
            title="跳转新闻 API Key 设置与安装指引"
          >
            News key {newsKeyReady ? 'ready' : 'missing'}
          </span>
          <span
            className={dbConfigReady ? 'chip chip-ok' : 'chip chip-warn'}
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysSettings', focusField: 'DATABASE_URL', guide: 'db' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysSettings', focusField: 'DATABASE_URL', guide: 'db' }))}
            title="跳转数据库 URL 设置"
          >
            DB url {dbConfigReady ? 'ready' : 'missing'}
          </span>
          <span
            className="chip chip-warn"
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysLlm', focusField: 'LLM_PROVIDER', guide: 'llm' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysLlm', focusField: 'LLM_PROVIDER', guide: 'llm' }))}
            title="跳转 LLM 提供商配置"
          >
            LLM {health.data?.provider || '-'}
          </span>
          <span
            className="chip chip-warn"
            role="button"
            tabIndex={0}
            onClick={() => openIntentPage({ mode: 'sysSettings' })}
            onKeyDown={(event) => onChipKeyDown(event, () => openIntentPage({ mode: 'sysSettings' }))}
            title="跳转系统设置页"
          >
            ENV {health.data?.env || '-'}
          </span>
        </div>
      </section>

      {!isLlmDesignerMode ? (
        <FigmaSideNav
          mode={viewMode}
          onModeChange={handleModeChange}
          surface={activeSurface}
          onSurfaceChange={handleSurfaceChange}
          theme={appTheme}
        />
      ) : null}
      <main className={`main-area is-${appTheme} ${isLlmDesignerMode ? 'main-area--immersive' : ''}`}>
        {!isLlmDesignerMode ? (
          <section className="panel app-page-title">
            <div className="panel-header">
              <h2>{pageTitle}</h2>
              <span className="status-line app-surface-badge">{activeSurface === 'workbench' ? 'Workbench' : 'Management'}</span>
            </div>
            <p className="status-line app-surface-note">{SHARED_CONTRACT_NOTE}</p>
          </section>
        ) : null}

        <Suspense fallback={<section className="panel"><p className="status-line">页面加载中...</p></section>}>
          <div className={`content-stack ${isLlmDesignerMode ? 'content-stack--immersive' : ''}`}>
            {modernContent}
          </div>
        </Suspense>
      </main>
    </div>
  )
}
