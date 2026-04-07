import { Suspense, lazy, type ReactNode } from 'react'
import type { KernelModuleKey } from './types'

const CatalogPage = lazy(() => import('../../pages/CatalogPage'))
const DashboardPage = lazy(() => import('../../pages/DashboardPage'))
const IngestPage = lazy(() => import('../../pages/IngestPage'))
const OpsPage = lazy(() => import('../../pages/OpsPage'))
const PolicyPage = lazy(() => import('../../pages/PolicyPage'))
const ProcessPage = lazy(() => import('../../pages/ProcessPage'))
const ProjectsPage = lazy(() => import('../../pages/ProjectsPage'))
const CrawlerManagePage = lazy(() => import('../../pages/CrawlerManagePage'))
const GraphPage = lazy(() => import('../../pages/GraphPage'))
const ResourcePage = lazy(() => import('../../pages/ResourcePage'))
const RawDataPage = lazy(() => import('../../pages/RawDataPage'))
const SettingsPage = lazy(() => import('../../pages/SettingsPage'))
const WritingWorkbenchPage = lazy(() => import('../../pages/WritingWorkbenchPage'))
const AgentChatPage = lazy(() => import('../../pages/AgentChatPage'))
const LlmDesignerPage = lazy(() => import('../../pages/LlmDesignerPage'))

export type KernelRenderShellMode = 'default' | 'workbench' | 'admin' | 'visualization' | 'legacy-shell'

type RenderKernelModuleContentArgs = {
  moduleKey: KernelModuleKey
  projectKey: string
  onProjectChange: (nextProjectKey: string) => void
  shellMode?: KernelRenderShellMode
}

function renderModuleNode({
  moduleKey,
  projectKey,
  onProjectChange,
  shellMode,
}: RenderKernelModuleContentArgs): ReactNode {
  if (moduleKey === 'overviewTasks') return <ProcessPage projectKey={projectKey} />
  if (moduleKey === 'flowProcessing') return <ProcessPage projectKey={projectKey} variant="processing" />
  if (moduleKey === 'overviewData') return <OpsPage projectKey={projectKey} />
  if (moduleKey === 'sysBackend') return <OpsPage projectKey={projectKey} variant="backend" />
  if (moduleKey === 'dataDashboard') return <DashboardPage projectKey={projectKey} variant="dashboard" />
  if (moduleKey === 'dataMarket') return <DashboardPage projectKey={projectKey} variant="market" />
  if (moduleKey === 'dataSocial') return <DashboardPage projectKey={projectKey} variant="social" />
  if (moduleKey === 'flowAnalysis') return <DashboardPage projectKey={projectKey} variant="analysis" />
  if (moduleKey === 'flowBoard') return <DashboardPage projectKey={projectKey} variant="board" />
  if (moduleKey === 'flowIngest') return <IngestPage key="ingest" projectKey={projectKey} variant="ingest" />
  if (moduleKey === 'flowSpecialized') return <IngestPage key="specialized" projectKey={projectKey} variant="specialized" />
  if (moduleKey === 'flowRawData') return <RawDataPage projectKey={projectKey} variant="rawData" />
  if (moduleKey === 'flowWriting') return <WritingWorkbenchPage projectKey={projectKey} standalone={shellMode !== 'workbench'} />
  if (moduleKey === 'flowAgentChat') return <AgentChatPage projectKey={projectKey} />
  if (moduleKey === 'dataPolicy') return <PolicyPage projectKey={projectKey} variant="policy" />
  if (moduleKey === 'dataCatalog') return <CatalogPage projectKey={projectKey} variant="catalog" />
  if (moduleKey === 'flowLlmNodeDesign') {
    if (shellMode === 'legacy-shell') return null
    return <LlmDesignerPage projectKey={projectKey} />
  }
  if (moduleKey === 'graphMarket') return <GraphPage projectKey={projectKey} variant="graphMarket" />
  if (moduleKey === 'graphPolicy') return <GraphPage projectKey={projectKey} variant="graphPolicy" />
  if (moduleKey === 'graphSocial') return <GraphPage projectKey={projectKey} variant="graphSocial" />
  if (moduleKey === 'graphCompany') return <GraphPage projectKey={projectKey} variant="graphCompany" />
  if (moduleKey === 'graphProduct') return <GraphPage projectKey={projectKey} variant="graphProduct" />
  if (moduleKey === 'graphOperation') return <GraphPage projectKey={projectKey} variant="graphOperation" />
  if (moduleKey === 'graphDeep') return <GraphPage projectKey={projectKey} variant="graphDeep" />
  if (moduleKey === 'graphBuilder') return <GraphPage projectKey={projectKey} variant="graphMarket" templateBuilder />
  if (moduleKey === 'sysProjects') return <ProjectsPage projectKey={projectKey} onProjectChange={onProjectChange} />
  if (moduleKey === 'sysCrawler') return <CrawlerManagePage projectKey={projectKey} />
  if (moduleKey === 'sysResource') return <ResourcePage projectKey={projectKey} variant="resource" />
  if (moduleKey === 'flowExtract') return <ResourcePage projectKey={projectKey} variant="extract" />
  if (moduleKey === 'sysSettings') return <SettingsPage projectKey={projectKey} variant="settings" />
  if (moduleKey === 'sysLlm') return <SettingsPage projectKey={projectKey} variant="llm" />
  return null
}

export function renderKernelModuleContent(args: RenderKernelModuleContentArgs): ReactNode {
  return (
    <Suspense fallback={<div className="kernel-loading">Loading module...</div>}>
      {renderModuleNode(args)}
    </Suspense>
  )
}
