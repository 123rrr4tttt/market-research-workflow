import type { NavMode } from '../kernel/types'
import { classifyByRubric, hasMixedSignals, type RubricSignalProfile } from './classificationRubric'
import type { InteractionSurface } from './surfaces'

export type PagePlacementRecord = {
  page: string
  navModes: readonly NavMode[]
  phase1Surface: InteractionSurface
  reason: string
  revisit: boolean
  rubricSignals: RubricSignalProfile
}

const PAGE_PLACEMENT_BASELINE: readonly PagePlacementRecord[] = [
  {
    page: 'GraphPage',
    navModes: ['graphMarket', 'graphPolicy', 'graphSocial', 'graphCompany', 'graphProduct', 'graphOperation', 'graphDeep', 'graphBuilder'],
    phase1Surface: 'workbench',
    reason: 'Dense canvas/panel interaction and iterative graph exploration.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'workbench',
      contextContinuity: 'workbench',
      panelCoordination: 'workbench',
      stateCoupling: 'workbench',
      primaryOutcome: 'workbench',
    },
  },
  {
    page: 'WritingWorkbenchPage',
    navModes: ['flowWriting'],
    phase1Surface: 'workbench',
    reason: 'Drafting loop with editor/preview side-by-side context.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'workbench',
      contextContinuity: 'workbench',
      panelCoordination: 'workbench',
      stateCoupling: 'workbench',
      primaryOutcome: 'workbench',
    },
  },
  {
    page: 'AgentChatPage',
    navModes: ['flowAgentChat'],
    phase1Surface: 'workbench',
    reason: 'Continuous agent conversation with staged execution feedback and session context.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'workbench',
      contextContinuity: 'workbench',
      panelCoordination: 'workbench',
      stateCoupling: 'workbench',
      primaryOutcome: 'workbench',
    },
  },
  {
    page: 'LlmDesignerPage',
    navModes: ['flowLlmNodeDesign'],
    phase1Surface: 'workbench',
    reason: 'Node design workspace; already launched as immersive standalone.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'workbench',
      contextContinuity: 'workbench',
      panelCoordination: 'workbench',
      stateCoupling: 'workbench',
      primaryOutcome: 'workbench',
    },
  },
  {
    page: 'ProjectsPage',
    navModes: ['sysProjects'],
    phase1Surface: 'management',
    reason: 'Project lifecycle management and governance actions.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'ResourcePage',
    navModes: ['sysResource', 'flowExtract'],
    phase1Surface: 'management',
    reason: 'Resource inventory/extraction operations with moderate complexity.',
    revisit: true,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'workbench',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'CrawlerManagePage',
    navModes: ['sysCrawler'],
    phase1Surface: 'management',
    reason: 'Connector setup, run controls, and operational governance.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'SettingsPage',
    navModes: ['sysSettings', 'sysLlm'],
    phase1Surface: 'management',
    reason: 'Configuration and policy management remain admin-first.',
    revisit: true,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'workbench',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'DashboardPage',
    navModes: ['dataDashboard', 'dataMarket', 'dataSocial', 'flowAnalysis', 'flowBoard'],
    phase1Surface: 'management',
    reason: 'Read-heavy KPI/analysis views with managed drill-down.',
    revisit: true,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'workbench',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'ProcessPage',
    navModes: ['overviewTasks', 'flowProcessing'],
    phase1Surface: 'management',
    reason: 'Task/process orchestration with standard admin interactions.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'OpsPage',
    navModes: ['overviewData', 'sysBackend'],
    phase1Surface: 'management',
    reason: 'Operational oversight and backend status review.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'IngestPage',
    navModes: ['flowIngest', 'flowSpecialized'],
    phase1Surface: 'management',
    reason: 'Pipeline setup and trigger control remain admin-owned.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'RawDataPage',
    navModes: ['flowRawData'],
    phase1Surface: 'management',
    reason: 'Raw data handling and processing controls are operational flows.',
    revisit: false,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'management',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'PolicyPage',
    navModes: ['dataPolicy'],
    phase1Surface: 'management',
    reason: 'Policy view is mainly decision support and reporting.',
    revisit: true,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'workbench',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
  {
    page: 'CatalogPage',
    navModes: ['dataCatalog'],
    phase1Surface: 'management',
    reason: 'Catalog browsing and filter operations are admin-style interactions.',
    revisit: true,
    rubricSignals: {
      interactionDensity: 'management',
      contextContinuity: 'management',
      panelCoordination: 'workbench',
      stateCoupling: 'management',
      primaryOutcome: 'management',
    },
  },
] as const

export const PAGE_PLACEMENT_MATRIX = PAGE_PLACEMENT_BASELINE.map((record) => ({
  ...record,
  rubricResult: classifyByRubric(record.rubricSignals),
  mixedSignals: hasMixedSignals(record.rubricSignals),
}))

export const PAGE_PLACEMENT_REVISIT_LIST = PAGE_PLACEMENT_MATRIX.filter((record) => record.revisit)

const modeSurfaceMapEntries = PAGE_PLACEMENT_MATRIX.flatMap((record) =>
  record.navModes.map((mode) => [mode, record.phase1Surface] as const),
)

export const MODE_SURFACE_MAP = Object.fromEntries(modeSurfaceMapEntries) as Record<NavMode, InteractionSurface>

export function resolvePlacedSurface(mode: NavMode): InteractionSurface {
  return MODE_SURFACE_MAP[mode] || 'management'
}

export function getSurfaceModes(surface: InteractionSurface): NavMode[] {
  return Object.keys(MODE_SURFACE_MAP).filter((mode) => MODE_SURFACE_MAP[mode as NavMode] === surface) as NavMode[]
}
