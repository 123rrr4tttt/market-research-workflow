export const MODULE_NAV_GROUP_KEYS = [
  'navigation.group.overview',
  'navigation.group.dataFacets',
  'navigation.group.graph',
  'navigation.group.flow',
  'navigation.group.system',
] as const

export type ModuleNavGroupKey = (typeof MODULE_NAV_GROUP_KEYS)[number]
export type LayerId = 'A' | 'B' | 'C'

export type SurfaceKind = 'workbench' | 'visualization' | 'management'
export type StorybookGroup = 'Workbench' | 'Visualization' | 'Management'

export const STORYBOOK_GROUP_BY_LAYER: Record<LayerId, StorybookGroup> = {
  A: 'Workbench',
  B: 'Visualization',
  C: 'Management',
}

export const KERNEL_RENDER_SHELL_MODE = {
  default: 'default',
  workbench: 'workbench',
  admin: 'admin',
  visualization: 'visualization',
  legacyShell: 'legacy-shell',
} as const

export type KernelRenderShellMode = (typeof KERNEL_RENDER_SHELL_MODE)[keyof typeof KERNEL_RENDER_SHELL_MODE]

export type KernelModuleKey =
  | 'overviewTasks'
  | 'overviewData'
  | 'dataDashboard'
  | 'dataMarket'
  | 'dataSocial'
  | 'dataPolicy'
  | 'dataCatalog'
  | 'graphMarket'
  | 'graphPolicy'
  | 'graphSocial'
  | 'graphCompany'
  | 'graphProduct'
  | 'graphOperation'
  | 'graphDeep'
  | 'graphBuilder'
  | 'flowIngest'
  | 'flowSpecialized'
  | 'flowProcessing'
  | 'flowRawData'
  | 'flowExtract'
  | 'flowAnalysis'
  | 'flowBoard'
  | 'flowWriting'
  | 'flowAgentChat'
  | 'flowLlmNodeDesign'
  | 'sysProjects'
  | 'sysCrawler'
  | 'sysResource'
  | 'sysBackend'
  | 'sysSettings'
  | 'sysLlm'

export type NavMode = KernelModuleKey

export type TitleMessageKey = `shell.title.${KernelModuleKey}`
export type NavMessageKey = `navigation.item.${KernelModuleKey}`

export type RouteManifest = {
  layerId: LayerId
  surfaceKind: SurfaceKind
  routePath: `/${string}`
  legacyHashes: readonly string[]
  moduleKey: KernelModuleKey
}

export type ModuleContract = {
  moduleKey: KernelModuleKey
  layerId: LayerId
  surfaceKind: SurfaceKind
  entryRoute: `/${string}`
  legacyHashes: readonly string[]
  titleKey: TitleMessageKey
  navLabelKey: NavMessageKey
  navGroupKey: ModuleNavGroupKey
  storybookGroup: StorybookGroup
  requiredContext: readonly string[]
  keepLoops: readonly string[]
  supportsInfoCard: boolean
  designSourceRefs: readonly string[]
}

export type DesignSourceRecord = {
  sourceType: 'figma' | 'demo' | 'reference_pool'
  sourceRef: string
  targetLayers: readonly LayerId[]
  reuseTarget: 'interaction' | 'structure' | 'visual_semantics'
  validationMethod: string
}

export type ModuleManifestEntry = {
  moduleKey: KernelModuleKey
  layerId: LayerId
  surfaceKind: SurfaceKind
  entryRoute: `/${string}`
  legacyHashes: readonly string[]
  titleKey: TitleMessageKey
  navLabelKey: NavMessageKey
  navGroupKey: ModuleNavGroupKey
  storybookGroup: StorybookGroup
  requiredContext: readonly string[]
  keepLoops: readonly string[]
  supportsInfoCard: boolean
  visibleInNav: boolean
  enabled: boolean
  designSourceRefs: readonly string[]
}

export type RouteSource = 'default' | 'layered' | 'legacy' | 'unknown'

export type KernelRouteState = {
  source: RouteSource
  moduleKey: KernelModuleKey
  layerId: LayerId
  surfaceKind: SurfaceKind
  routePath: `/${string}`
  routeHash: `#/${string}`
}
