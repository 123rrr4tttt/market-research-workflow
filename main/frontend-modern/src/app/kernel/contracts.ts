import { moduleManifest, moduleManifestByKey } from './moduleManifest'
import type { KernelModuleKey, LayerId, ModuleContract, RouteManifest, SurfaceKind } from './types'

export const kernelModuleContracts: Record<KernelModuleKey, ModuleContract> = Object.fromEntries(
  moduleManifest.map((entry) => [
    entry.moduleKey,
    {
      moduleKey: entry.moduleKey,
      layerId: entry.layerId,
      surfaceKind: entry.surfaceKind,
      entryRoute: entry.entryRoute,
      legacyHashes: entry.legacyHashes,
      titleKey: entry.titleKey,
      navLabelKey: entry.navLabelKey,
      navGroupKey: entry.navGroupKey,
      storybookGroup: entry.storybookGroup,
      requiredContext: entry.requiredContext,
      keepLoops: entry.keepLoops,
      supportsInfoCard: entry.supportsInfoCard,
    },
  ]),
) as Record<KernelModuleKey, ModuleContract>

export const routeManifest: readonly RouteManifest<KernelModuleKey>[] = moduleManifest.map((entry) => ({
  layerId: entry.layerId,
  surfaceKind: entry.surfaceKind,
  routePath: entry.entryRoute,
  legacyHashes: entry.legacyHashes,
  moduleKey: entry.moduleKey,
}))

export function getKernelModuleContract(moduleKey: KernelModuleKey): ModuleContract {
  return kernelModuleContracts[moduleKey]
}

export function getModulesByLayer(layerId: LayerId): ModuleContract[] {
  return Object.values(kernelModuleContracts).filter((item) => item.layerId === layerId)
}

export function getModulesBySurfaceKind(surfaceKind: SurfaceKind): ModuleContract[] {
  return Object.values(kernelModuleContracts).filter((item) => item.surfaceKind === surfaceKind)
}

export function getKernelModuleManifest(moduleKey: KernelModuleKey) {
  return moduleManifestByKey[moduleKey]
}
