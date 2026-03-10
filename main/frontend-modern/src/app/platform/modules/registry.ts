import { hashByMode } from '../../navigation'
import { resolveInteractionSurface } from '../../topology/contracts'
import type { InteractionSurface } from '../../topology/surfaces'
import type { ModuleDescriptor, ModuleNavGroupKey, RegisteredNavMode } from './types'

const defaultVisibility = {
  visibleInNav: true,
  enabled: true,
} as const

function defineModule(mode: RegisteredNavMode, navGroupKey: ModuleNavGroupKey): ModuleDescriptor {
  const interactionProfile = resolveInteractionSurface(mode) === 'workbench' ? 'workbench' : 'standard'
  return {
    mode,
    hash: hashByMode[mode],
    titleKey: `shell.title.${mode}`,
    navLabelKey: `navigation.item.${mode}`,
    navGroupKey,
    interactionProfile,
    visibleInNav: defaultVisibility.visibleInNav,
    enabled: defaultVisibility.enabled,
  }
}

export const moduleRegistry: Record<RegisteredNavMode, ModuleDescriptor> = {
  overviewTasks: defineModule('overviewTasks', 'navigation.group.overview'),
  overviewData: defineModule('overviewData', 'navigation.group.overview'),
  dataDashboard: defineModule('dataDashboard', 'navigation.group.dataFacets'),
  dataMarket: defineModule('dataMarket', 'navigation.group.dataFacets'),
  dataSocial: defineModule('dataSocial', 'navigation.group.dataFacets'),
  dataPolicy: defineModule('dataPolicy', 'navigation.group.dataFacets'),
  dataCatalog: defineModule('dataCatalog', 'navigation.group.dataFacets'),
  graphMarket: defineModule('graphMarket', 'navigation.group.graph'),
  graphPolicy: defineModule('graphPolicy', 'navigation.group.graph'),
  graphSocial: defineModule('graphSocial', 'navigation.group.graph'),
  graphCompany: defineModule('graphCompany', 'navigation.group.graph'),
  graphProduct: defineModule('graphProduct', 'navigation.group.graph'),
  graphOperation: defineModule('graphOperation', 'navigation.group.graph'),
  graphDeep: defineModule('graphDeep', 'navigation.group.graph'),
  graphBuilder: defineModule('graphBuilder', 'navigation.group.graph'),
  flowIngest: defineModule('flowIngest', 'navigation.group.flow'),
  flowSpecialized: defineModule('flowSpecialized', 'navigation.group.flow'),
  flowProcessing: defineModule('flowProcessing', 'navigation.group.flow'),
  flowRawData: defineModule('flowRawData', 'navigation.group.flow'),
  flowExtract: defineModule('flowExtract', 'navigation.group.flow'),
  flowAnalysis: defineModule('flowAnalysis', 'navigation.group.flow'),
  flowBoard: defineModule('flowBoard', 'navigation.group.flow'),
  flowWriting: defineModule('flowWriting', 'navigation.group.flow'),
  flowLlmNodeDesign: defineModule('flowLlmNodeDesign', 'navigation.group.flow'),
  sysProjects: defineModule('sysProjects', 'navigation.group.system'),
  sysCrawler: defineModule('sysCrawler', 'navigation.group.system'),
  sysResource: defineModule('sysResource', 'navigation.group.system'),
  sysBackend: defineModule('sysBackend', 'navigation.group.system'),
  sysSettings: defineModule('sysSettings', 'navigation.group.system'),
  sysLlm: defineModule('sysLlm', 'navigation.group.system'),
}

export function getModuleDescriptor(mode: RegisteredNavMode): ModuleDescriptor {
  return moduleRegistry[mode]
}

export function getModulesByGroup(navGroupKey: ModuleNavGroupKey): ModuleDescriptor[] {
  return Object.values(moduleRegistry).filter((item) => item.navGroupKey === navGroupKey && item.visibleInNav && item.enabled)
}

export function getModulesBySurface(surface: InteractionSurface): ModuleDescriptor[] {
  return Object.values(moduleRegistry).filter((item) => {
    if (!item.visibleInNav || !item.enabled) return false
    return resolveInteractionSurface(item.mode) === surface
  })
}

export function buildRegistryHashMap(): Record<RegisteredNavMode, string> {
  return Object.fromEntries(
    (Object.keys(moduleRegistry) as RegisteredNavMode[]).map((mode) => [mode, moduleRegistry[mode].hash]),
  ) as Record<RegisteredNavMode, string>
}

export function verifyRegistryHashCompatibility(): { isCompatible: boolean; mismatchedModes: RegisteredNavMode[] } {
  const mismatchedModes = (Object.keys(moduleRegistry) as RegisteredNavMode[]).filter(
    (mode) => moduleRegistry[mode].hash !== hashByMode[mode],
  )
  return {
    isCompatible: mismatchedModes.length === 0,
    mismatchedModes,
  }
}
