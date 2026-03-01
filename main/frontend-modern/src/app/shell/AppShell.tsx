import { Suspense, lazy, useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import FigmaSideNav, { type NavMode } from '../../components/FigmaSideNav'
import { activateProject, getDeepHealth, getEnvSettings, getHealth, getProjectKey, listProjects } from '../../lib/api'
import { queryKeys } from '../../lib/queryKeys'
import { defaultNavMode, hashByMode, parseLegacyHashToMode } from '../navigation'

const CatalogPage = lazy(() => import('../../pages/CatalogPage'))
const DashboardPage = lazy(() => import('../../pages/DashboardPage'))
const IngestPage = lazy(() => import('../../pages/IngestPage'))
const OpsPage = lazy(() => import('../../pages/OpsPage'))
const PolicyPage = lazy(() => import('../../pages/PolicyPage'))
const ProcessPage = lazy(() => import('../../pages/ProcessPage'))
const ProjectsPage = lazy(() => import('../../pages/ProjectsPage'))
const GraphPage = lazy(() => import('../../pages/GraphPage'))
const ResourcePage = lazy(() => import('../../pages/ResourcePage'))
const RawDataPage = lazy(() => import('../../pages/RawDataPage'))
const SettingsPage = lazy(() => import('../../pages/SettingsPage'))
const WorkflowPage = lazy(() => import('../../pages/WorkflowPage'))

type FigmaTheme = 'light' | 'dark' | 'brand'

export default function AppShell() {
  const [viewMode, setViewMode] = useState<NavMode>(() => parseLegacyHashToMode(window.location.hash) || defaultNavMode)
  const [figmaTheme] = useState<FigmaTheme>('dark')
  const [projectKey, setProjectKeyState] = useState(getProjectKey())
  const [pendingProjectKey, setPendingProjectKey] = useState(projectKey)
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

  const titleMap: Record<string, string> = {
    overviewTasks: '任务',
    overviewData: '数据',
    dataDashboard: '数据仪表盘',
    dataMarket: '市场',
    dataSocial: '舆情',
    dataPolicy: '政策',
    dataCatalog: '行业公司/商品/经营',
    graphMarket: '市场图谱',
    graphPolicy: '政策图谱',
    graphSocial: '社媒图谱',
    graphCompany: '公司图谱',
    graphProduct: '商品图谱',
    graphOperation: '电商/经营图谱',
    graphDeep: '市场实体加细图',
    flowIngest: '采集',
    flowSpecialized: '特化采集',
    flowProcessing: '数据处理',
    flowRawData: '原始数据处理',
    flowExtract: '提取',
    flowAnalysis: '分析',
    flowBoard: '看板',
    flowWorkflow: '工作流模板',
    sysProjects: '项目管理',
    sysResource: '信息资源库管理',
    sysBackend: '后端监控',
    sysSettings: '系统设置',
    sysLlm: 'LLM 配置',
  }
  const pageTitle = titleMap[viewMode] || viewMode

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

  const modernContent = (() => {
    if (viewMode === 'overviewTasks') return <ProcessPage projectKey={projectKey} />
    if (viewMode === 'flowProcessing') return <ProcessPage projectKey={projectKey} variant="processing" />
    if (viewMode === 'overviewData') return <OpsPage projectKey={projectKey} />
    if (viewMode === 'sysBackend') return <OpsPage projectKey={projectKey} variant="backend" />
    if (viewMode === 'dataDashboard' || viewMode === 'flowAnalysis' || viewMode === 'flowBoard' || viewMode === 'dataMarket' || viewMode === 'dataSocial') {
      if (viewMode === 'dataMarket') return <DashboardPage projectKey={projectKey} variant="market" />
      if (viewMode === 'dataSocial') return <DashboardPage projectKey={projectKey} variant="social" />
      if (viewMode === 'flowAnalysis') return <DashboardPage projectKey={projectKey} variant="analysis" />
      if (viewMode === 'flowBoard') return <DashboardPage projectKey={projectKey} variant="board" />
      return <DashboardPage projectKey={projectKey} variant="dashboard" />
    }
    if (viewMode === 'flowIngest') return <IngestPage projectKey={projectKey} variant="ingest" />
    if (viewMode === 'flowSpecialized') return <IngestPage projectKey={projectKey} variant="specialized" />
    if (viewMode === 'flowRawData') return <RawDataPage projectKey={projectKey} variant="rawData" />
    if (viewMode === 'dataPolicy') return <PolicyPage projectKey={projectKey} variant="policy" />
    if (viewMode === 'dataCatalog') return <CatalogPage projectKey={projectKey} variant="catalog" />
    if (viewMode === 'flowWorkflow') return <WorkflowPage projectKey={projectKey} variant="workflow" />
    if (viewMode === 'graphMarket') return <GraphPage projectKey={projectKey} variant="graphMarket" />
    if (viewMode === 'graphPolicy') return <GraphPage projectKey={projectKey} variant="graphPolicy" />
    if (viewMode === 'graphSocial') return <GraphPage projectKey={projectKey} variant="graphSocial" />
    if (viewMode === 'graphCompany') return <GraphPage projectKey={projectKey} variant="graphCompany" />
    if (viewMode === 'graphProduct') return <GraphPage projectKey={projectKey} variant="graphProduct" />
    if (viewMode === 'graphOperation') return <GraphPage projectKey={projectKey} variant="graphOperation" />
    if (viewMode === 'graphDeep') return <GraphPage projectKey={projectKey} variant="graphDeep" />
    if (viewMode === 'sysProjects') return <ProjectsPage projectKey={projectKey} onProjectChange={setProjectKeyState} />
    if (viewMode === 'sysResource') return <ResourcePage projectKey={projectKey} variant="resource" />
    if (viewMode === 'flowExtract') return <ResourcePage projectKey={projectKey} variant="extract" />
    if (viewMode === 'sysSettings') return <SettingsPage projectKey={projectKey} variant="settings" />
    if (viewMode === 'sysLlm') return <SettingsPage projectKey={projectKey} variant="llm" />
    return null
  })()

  useEffect(() => {
    const syncModeFromHash = () => {
      const nextMode = parseLegacyHashToMode(window.location.hash) || defaultNavMode
      setViewMode((prev) => (prev === nextMode ? prev : nextMode))
    }

    window.addEventListener('hashchange', syncModeFromHash)
    syncModeFromHash()
    return () => window.removeEventListener('hashchange', syncModeFromHash)
  }, [])

  useEffect(() => {
    setPendingProjectKey(projectKey)
  }, [projectKey])

  const handleModeChange = (mode: NavMode) => {
    setViewMode(mode)
    const nextHash = hashByMode[mode]
    if (nextHash && window.location.hash !== nextHash) window.location.hash = nextHash
  }

  return (
    <div className="layout-root">
      <FigmaSideNav mode={viewMode} onModeChange={handleModeChange} theme={figmaTheme} />
      <main className={`main-area is-${figmaTheme}`}>
        <section className="panel app-status-bar">
          <div className="app-status-bar__head">
            <h2>{pageTitle}</h2>
            <span className="status-line">当前项目: {projectKey}</span>
          </div>
          <div className="app-status-bar__controls">
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
          </div>
          <div className="app-status-bar__chips">
            <span className={statusChipClass(health.data?.status)}>API {health.data?.status || 'loading'}</span>
            <span className={statusChipClass(deepHealth.data?.database)}>DB {deepHealth.data?.database || 'loading'}</span>
            <span className={statusChipClass(deepHealth.data?.elasticsearch)}>ES {deepHealth.data?.elasticsearch || 'loading'}</span>
            <span className={llmKeyReady ? 'chip chip-ok' : 'chip chip-danger'}>LLM key {llmKeyReady ? 'ready' : 'missing'}</span>
            <span className={searchKeyReady ? 'chip chip-ok' : 'chip chip-warn'}>Search key {searchKeyReady ? 'ready' : 'missing'}</span>
            <span className={newsKeyReady ? 'chip chip-ok' : 'chip chip-warn'}>News key {newsKeyReady ? 'ready' : 'missing'}</span>
            <span className={dbConfigReady ? 'chip chip-ok' : 'chip chip-warn'}>DB url {dbConfigReady ? 'ready' : 'missing'}</span>
            <span className="chip chip-warn">LLM {health.data?.provider || '-'}</span>
            <span className="chip chip-warn">ENV {health.data?.env || '-'}</span>
          </div>
          {switchMessage ? <p className="status-line">{switchMessage}</p> : null}
        </section>

        <section className="panel page-head">
          <div className="panel-header">
            <h2>{pageTitle}</h2>
            <span className="status-line">页面视图: {viewMode}</span>
          </div>
        </section>

        <Suspense fallback={<section className="panel"><p className="status-line">页面加载中...</p></section>}>
          <div className="content-stack">
            {modernContent}
          </div>
        </Suspense>
      </main>
    </div>
  )
}
