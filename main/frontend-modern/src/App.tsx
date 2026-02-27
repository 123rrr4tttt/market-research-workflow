import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import FigmaSideNav, { type NavMode } from './components/FigmaSideNav'
import { activateProject, getHealth, getProjectKey, listProjects, setProjectKey } from './lib/api'
import CatalogPage from './pages/CatalogPage'
import DashboardPage from './pages/DashboardPage'
import IngestPage from './pages/IngestPage'
import OpsPage from './pages/OpsPage'
import PolicyPage from './pages/PolicyPage'
import ProcessPage from './pages/ProcessPage'
import ProjectsPage from './pages/ProjectsPage'
import GraphPage from './pages/GraphPage'
import ResourcePage from './pages/ResourcePage'
import SettingsPage from './pages/SettingsPage'
import WorkflowPage from './pages/WorkflowPage'

type FigmaTheme = 'light' | 'dark' | 'brand'

export default function App() {
  const [viewMode, setViewMode] = useState<NavMode>('overviewTasks')
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

  return (
    <div className="layout-root">
      <FigmaSideNav mode={viewMode} onModeChange={setViewMode} theme={figmaTheme} />
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

        <div className="content-stack">
          {modernContent}
        </div>
      </main>
    </div>
  )
}
