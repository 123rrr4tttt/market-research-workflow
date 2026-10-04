import { createElement as h, lazy, type ReactNode } from 'react'
import { moduleManifest } from './moduleManifest'
import { KERNEL_RENDER_SHELL_MODE, type KernelModuleKey, type KernelRenderShellMode } from './types'
import { GRAPH_PROJECTIONS, type GraphProjectionId } from '../../pages/graph/realizer/definitions'

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
const CodexAgentPage = lazy(() => import('../../pages/CodexAgentPage'))
const WorkflowManagerPage = lazy(() => import('../../pages/WorkflowManagerPage'))
const SuccessorRuntimePage = lazy(() => import('../../pages/SuccessorRuntimePage'))

export type ModuleRendererArgs = {
  moduleKey: KernelModuleKey
  projectKey: string
  onProjectChange: (nextProjectKey: string) => void
  shellMode?: KernelRenderShellMode
}

export type ModuleRenderer = (args: ModuleRendererArgs) => ReactNode

export type ModuleRendererBinding = {
  moduleKey: KernelModuleKey
  renderer: ModuleRenderer
}

const GRAPH_MODULE_RENDERERS = Object.fromEntries(
  (Object.keys(GRAPH_PROJECTIONS) as GraphProjectionId[]).map((projectionId) => [
    projectionId,
    ({ projectKey }: ModuleRendererArgs) => h(GraphPage, { projectKey, variant: projectionId }),
  ]),
) as Pick<Record<KernelModuleKey, ModuleRenderer>, GraphProjectionId>

/**
 * One renderer per manifest module. The record is typed over the full kernel
 * module union, so adding a manifest module without a renderer contribution
 * fails type checking; the exported bindings are derived from the manifest.
 */
const MODULE_RENDERERS: Record<KernelModuleKey, ModuleRenderer> = {
  overviewTasks: ({ projectKey }) => h(ProcessPage, { projectKey }),
  flowProcessing: ({ projectKey }) => h(ProcessPage, { projectKey, variant: 'processing' }),
  overviewData: ({ projectKey }) => h(OpsPage, { projectKey }),
  sysBackend: ({ projectKey }) => h(OpsPage, { projectKey, variant: 'backend' }),
  dataDashboard: ({ projectKey }) => h(DashboardPage, { projectKey, variant: 'dashboard' }),
  dataMarket: ({ projectKey }) => h(DashboardPage, { projectKey, variant: 'market' }),
  dataSocial: ({ projectKey }) => h(DashboardPage, { projectKey, variant: 'social' }),
  flowAnalysis: ({ projectKey }) => h(DashboardPage, { projectKey, variant: 'analysis' }),
  flowBoard: ({ projectKey }) => h(DashboardPage, { projectKey, variant: 'board' }),
  flowIngest: ({ projectKey }) => h(IngestPage, { key: 'ingest', projectKey, variant: 'ingest' }),
  flowSpecialized: ({ projectKey }) => h(IngestPage, { key: 'specialized', projectKey, variant: 'specialized' }),
  flowRawData: ({ projectKey }) => h(RawDataPage, { projectKey, variant: 'rawData' }),
  flowWriting: ({ projectKey, shellMode }) =>
    h(WritingWorkbenchPage, {
      projectKey,
      standalone: shellMode !== KERNEL_RENDER_SHELL_MODE.workbench,
    }),
  flowAgentChat: ({ projectKey }) => h(CodexAgentPage, { projectKey }),
  dataPolicy: ({ projectKey }) => h(PolicyPage, { projectKey, variant: 'policy' }),
  dataCatalog: ({ projectKey }) => h(CatalogPage, { projectKey, variant: 'catalog' }),
  flowLlmNodeDesign: ({ projectKey, shellMode }) =>
    shellMode === KERNEL_RENDER_SHELL_MODE.legacyShell
      ? null
      : h(WorkflowManagerPage, { projectKey }),
  ...GRAPH_MODULE_RENDERERS,
  graphBuilder: ({ projectKey }) => h(GraphPage, { projectKey, variant: 'graphMarket', templateBuilder: true }),
  sysProjects: ({ projectKey, onProjectChange }) =>
    h(ProjectsPage, { projectKey, onProjectChange }),
  sysCrawler: ({ projectKey }) => h(CrawlerManagePage, { projectKey }),
  sysResource: ({ projectKey }) => h(ResourcePage, { projectKey, variant: 'resource' }),
  flowExtract: ({ projectKey }) => h(ResourcePage, { projectKey, variant: 'extract' }),
  sysSettings: ({ projectKey }) => h(SettingsPage, { projectKey, variant: 'settings' }),
  sysLlm: ({ projectKey }) => h(SettingsPage, { projectKey, variant: 'llm' }),
  sysSuccessorRuntime: ({ projectKey, shellMode }) =>
    shellMode === KERNEL_RENDER_SHELL_MODE.admin
      ? h(SuccessorRuntimePage, { projectKey })
      : null,
}

export const moduleRendererBindings: Record<KernelModuleKey, ModuleRendererBinding> = Object.fromEntries(
  moduleManifest.map((entry) => [entry.moduleKey, { moduleKey: entry.moduleKey, renderer: MODULE_RENDERERS[entry.moduleKey] }]),
) as Record<KernelModuleKey, ModuleRendererBinding>

export function getModuleRendererBinding(moduleKey: KernelModuleKey): ModuleRendererBinding {
  return moduleRendererBindings[moduleKey]
}
