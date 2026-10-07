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

import type { KernelModuleKey } from './moduleManifest'

export type {
  KernelModuleKey,
  ModuleContract,
  ModuleManifestEntry,
  NavMode,
} from './moduleManifest'

export type TitleMessageKey<ModuleKey extends string = string> = `shell.title.${ModuleKey}`
export type NavMessageKey<ModuleKey extends string = string> = `navigation.item.${ModuleKey}`

export type RouteManifest<ModuleKey extends string = string> = {
  layerId: LayerId
  surfaceKind: SurfaceKind
  routePath: `/${string}`
  legacyHashes: readonly string[]
  moduleKey: ModuleKey
}

export type ModuleContractDefinition<ModuleKey extends string = string> = {
  moduleKey: ModuleKey
  layerId: LayerId
  surfaceKind: SurfaceKind
  entryRoute: `/${string}`
  legacyHashes: readonly string[]
  titleKey: TitleMessageKey<ModuleKey>
  navLabelKey: NavMessageKey<ModuleKey>
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

export type ModuleManifestEntryDefinition<ModuleKey extends string = string> = {
  moduleKey: ModuleKey
  layerId: LayerId
  surfaceKind: SurfaceKind
  entryRoute: `/${string}`
  legacyHashes: readonly string[]
  titleKey: TitleMessageKey<ModuleKey>
  navLabelKey: NavMessageKey<ModuleKey>
  navGroupKey: ModuleNavGroupKey
  storybookGroup: StorybookGroup
  requiredContext: readonly string[]
  keepLoops: readonly string[]
  supportsInfoCard: boolean
  visibleInNav: boolean
  enabled: boolean
  designSourceRefs: readonly string[]
}

export type RouteSource = 'default' | 'layered' | 'legacy' | 'retired' | 'unknown'

export type KernelRouteState = {
  source: RouteSource
  moduleKey: KernelModuleKey
  layerId: LayerId
  surfaceKind: SurfaceKind
  routePath: `/${string}`
  routeHash: `#/${string}`
}
