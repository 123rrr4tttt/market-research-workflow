import type { NavMode } from '../kernel/types'
import { resolveInteractionSurface } from './contracts'
import type { InteractionSurface } from './surfaces'

export type BaselinePageRecord = {
  page: string
  navModes: readonly NavMode[]
  defaultSurface: InteractionSurface
}

const BASELINE_MODE_CATALOG: readonly NavMode[] = [
  'overviewTasks',
  'overviewData',
  'dataDashboard',
  'dataMarket',
  'dataSocial',
  'dataPolicy',
  'dataCatalog',
  'graphMarket',
  'graphPolicy',
  'graphSocial',
  'graphCompany',
  'graphProduct',
  'graphOperation',
  'graphDeep',
  'graphBuilder',
  'flowIngest',
  'flowSpecialized',
  'flowProcessing',
  'flowRawData',
  'flowExtract',
  'flowAnalysis',
  'flowBoard',
  'flowWriting',
  'flowAgentChat',
  'flowLlmNodeDesign',
  'sysProjects',
  'sysCrawler',
  'sysResource',
  'sysBackend',
  'sysSettings',
  'sysLlm',
] as const

export const BASELINE_PAGE_INVENTORY: readonly BaselinePageRecord[] = [
  { page: 'ProcessPage', navModes: ['overviewTasks', 'flowProcessing'], defaultSurface: 'management' },
  { page: 'OpsPage', navModes: ['overviewData', 'sysBackend'], defaultSurface: 'management' },
  { page: 'DashboardPage', navModes: ['dataDashboard', 'flowAnalysis', 'flowBoard', 'dataMarket', 'dataSocial'], defaultSurface: 'management' },
  { page: 'IngestPage', navModes: ['flowIngest', 'flowSpecialized'], defaultSurface: 'management' },
  { page: 'RawDataPage', navModes: ['flowRawData'], defaultSurface: 'management' },
  { page: 'PolicyPage', navModes: ['dataPolicy'], defaultSurface: 'management' },
  { page: 'CatalogPage', navModes: ['dataCatalog'], defaultSurface: 'management' },
  {
    page: 'GraphPage',
    navModes: ['graphMarket', 'graphPolicy', 'graphSocial', 'graphCompany', 'graphProduct', 'graphOperation', 'graphDeep', 'graphBuilder'],
    defaultSurface: 'workbench',
  },
  { page: 'WritingWorkbenchPage', navModes: ['flowWriting'], defaultSurface: 'workbench' },
  { page: 'AgentChatPage', navModes: ['flowAgentChat'], defaultSurface: 'workbench' },
  { page: 'LlmDesignerPage', navModes: ['flowLlmNodeDesign'], defaultSurface: 'workbench' },
  { page: 'ProjectsPage', navModes: ['sysProjects'], defaultSurface: 'management' },
  { page: 'CrawlerManagePage', navModes: ['sysCrawler'], defaultSurface: 'management' },
  { page: 'ResourcePage', navModes: ['sysResource', 'flowExtract'], defaultSurface: 'management' },
  { page: 'SettingsPage', navModes: ['sysSettings', 'sysLlm'], defaultSurface: 'management' },
] as const

export function getBaselineModeCatalog(): readonly NavMode[] {
  return BASELINE_MODE_CATALOG
}

export function getBaselineInventoryMismatches(): readonly string[] {
  const mismatch: string[] = []
  for (const record of BASELINE_PAGE_INVENTORY) {
    for (const mode of record.navModes) {
      if (resolveInteractionSurface(mode) !== record.defaultSurface) {
        mismatch.push(`${record.page}:${mode}`)
      }
    }
  }
  return mismatch
}
