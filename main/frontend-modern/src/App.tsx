import { Suspense, lazy, useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import FigmaSideNav, { type NavMode } from './components/FigmaSideNav'
import { activateProject, getHealth, getProjectKey, listProjects, setProjectKey } from './lib/api'

const CatalogPage = lazy(() => import('./pages/CatalogPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const IngestPage = lazy(() => import('./pages/IngestPage'))
const OpsPage = lazy(() => import('./pages/OpsPage'))
const PolicyPage = lazy(() => import('./pages/PolicyPage'))
const ProcessPage = lazy(() => import('./pages/ProcessPage'))
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'))
const GraphPage = lazy(() => import('./pages/GraphPage'))
const ResourcePage = lazy(() => import('./pages/ResourcePage'))
const RawDataPage = lazy(() => import('./pages/RawDataPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const WorkflowPage = lazy(() => import('./pages/WorkflowPage'))

type FigmaTheme = 'light' | 'dark' | 'brand'
const defaultNavMode: NavMode = 'overviewTasks'

const hashByMode: Record<NavMode, string> = {
  overviewTasks: '#process-management.html',
  overviewData: '#admin.html',
  dataDashboard: '#dashboard.html',
  dataMarket: '#market-data-visualization.html',
  dataSocial: '#social-media-visualization.html',
  dataPolicy: '#policy-visualization.html',
  dataCatalog: '#topic-dashboard.html?topic=company',
  graphMarket: '#graph.html?type=market',
  graphPolicy: '#graph.html?type=policy',
  graphSocial: '#graph.html?type=social',
  graphCompany: '#topic-dashboard.html?topic=company',
  graphProduct: '#topic-dashboard.html?topic=product',
  graphOperation: '#topic-dashboard.html?topic=operation',
  graphDeep: '#graph.html?type=market_deep_entities',
  flowIngest: '#ingest.html',
  flowSpecialized: '#ingest.html?mode=specialized',
  flowProcessing: '#process-management.html?view=processing',
  flowRawData: '#raw-data-processing.html',
  flowExtract: '#admin.html#extracted',
  flowAnalysis: '#dashboard.html#analysis',
  flowBoard: '#dashboard.html#board',
  flowWorkflow: '#workflow-designer.html',
  sysProjects: '#project-management.html',
  sysResource: '#resource-pool-management.html',
  sysBackend: '#backend-dashboard.html',
  sysSettings: '#settings.html',
  sysLlm: '#settings.html#llm-config',
}

const navModes = new Set<NavMode>(Object.keys(hashByMode) as NavMode[])

function parseLegacyHashToMode(rawHash: string): NavMode | null {
  const decoded = decodeURIComponent((rawHash || '').replace(/^#/, '')).trim().toLowerCase()
  if (!decoded) return null
  if (navModes.has(decoded as NavMode)) return decoded as NavMode

  if (decoded.includes('raw-data-processing.html') || decoded === 'raw-data' || decoded.includes('/raw-data')) {
    return 'flowRawData'
  }

  const [pathQuery, hashFragment = ''] = decoded.split('#')
  const [path, rawQuery = ''] = pathQuery.split('?')
  const query = new URLSearchParams(rawQuery)
  const fragment = hashFragment.trim()

  if (path.includes('settings.html')) {
    if (fragment.includes('llm-config')) return 'sysLlm'
    return 'sysSettings'
  }

  if (path.includes('admin.html')) {
    if (fragment.includes('extracted') || fragment.includes('extract')) return 'flowExtract'
    return 'overviewData'
  }

  if (path.includes('process-management.html')) {
    if (query.get('view') === 'processing' || fragment.includes('processing')) return 'flowProcessing'
    return 'overviewTasks'
  }

  if (path.includes('dashboard.html')) {
    if (fragment.includes('analysis')) return 'flowAnalysis'
    if (fragment.includes('board')) return 'flowBoard'
    if (fragment.includes('market')) return 'dataMarket'
    if (fragment.includes('social')) return 'dataSocial'
    return 'dataDashboard'
  }

  if (path.includes('topic-dashboard.html')) {
    const topic = (query.get('topic') || '').toLowerCase()
    if (topic === 'company') return 'graphCompany'
    if (topic === 'product' || topic === 'commodity') return 'graphProduct'
    if (topic === 'operation' || topic === 'ecom') return 'graphOperation'
    if (topic === 'policy') return 'dataPolicy'
    if (topic === 'social' || topic === 'public-opinion') return 'dataSocial'
    if (topic === 'market') return 'dataMarket'
    return 'dataCatalog'
  }

  if (path.includes('graph.html')) {
    const graphType = (query.get('type') || '').toLowerCase()
    if (graphType === 'policy') return 'graphPolicy'
    if (graphType === 'social') return 'graphSocial'
    if (graphType === 'company') return 'graphCompany'
    if (graphType === 'product' || graphType === 'commodity') return 'graphProduct'
    if (graphType === 'operation' || graphType === 'ecom') return 'graphOperation'
    if (graphType === 'deep' || graphType === 'market_deep_entities') return 'graphDeep'
    return 'graphMarket'
  }

  if (path.includes('market-data-visualization.html')) return 'dataMarket'
  if (path.includes('social-media-visualization.html')) return 'dataSocial'
  if (path.includes('policy-visualization.html')) return 'dataPolicy'
  if (path.includes('raw-data-processing.html') || path.includes('raw-data.html')) return 'flowRawData'
  if (path.includes('workflow-designer.html')) return 'flowWorkflow'
  if (path.includes('project-management.html')) return 'sysProjects'
  if (path.includes('resource-pool-management.html')) return 'sysResource'
  if (path.includes('backend-dashboard.html')) return 'sysBackend'
  if (path.includes('ingest.html')) {
    if ((query.get('mode') || '').toLowerCase() === 'specialized') return 'flowSpecialized'
    return 'flowIngest'
  }

  return null
}

export default function App() {
  const [viewMode, setViewMode] = useState<NavMode>(() => parseLegacyHashToMode(window.location.hash) || defaultNavMode)
  const [figmaTheme] = useState<FigmaTheme>('dark')
  const [projectKey, setProjectKeyState] = useState(getProjectKey())

  const health = useQuery({ queryKey: ['health'], queryFn: getHealth })
  const projects = useQuery({ queryKey: ['projects'], queryFn: listProjects })

  const activateMutation = useMutation({
    mutationFn: activateProject,
    onSuccess: (next) => setProjectKeyState(next),
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

  const handleModeChange = (mode: NavMode) => {
    setViewMode(mode)
    const nextHash = hashByMode[mode]
    if (nextHash && window.location.hash !== nextHash) window.location.hash = nextHash
  }

  return (
    <div className="layout-root">
      <FigmaSideNav mode={viewMode} onModeChange={handleModeChange} theme={figmaTheme} />
      <main className={`main-area is-${figmaTheme}`}>
        <section className="panel page-head">
          <div className="panel-header">
            <h2>{pageTitle}</h2>
            <div className="inline-actions">
              <span className="chip chip-warn">{health.data?.status || 'loading'}</span>
              <select
                value={projectKey}
                onChange={(e) => {
                  const next = setProjectKey(e.target.value)
                  setProjectKeyState(next)
                  activateMutation.mutate(next)
                }}
                disabled={activateMutation.isPending}
              >
                <option value={projectKey}>{projectKey}</option>
                {(projects.data || []).map((item) => (
                  <option key={item.project_key} value={item.project_key}>{item.project_key}</option>
                ))}
              </select>
            </div>
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
