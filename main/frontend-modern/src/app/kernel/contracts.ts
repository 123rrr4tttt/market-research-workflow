import { moduleManifest, moduleManifestByKey } from './moduleManifest'
import type { DesignSourceRecord, KernelModuleKey, LayerId, ModuleContract, RouteManifest, SurfaceKind } from './types'

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
      designSourceRefs: entry.designSourceRefs,
    },
  ]),
) as Record<KernelModuleKey, ModuleContract>

export const routeManifest: readonly RouteManifest[] = moduleManifest.map((entry) => ({
  layerId: entry.layerId,
  surfaceKind: entry.surfaceKind,
  routePath: entry.entryRoute,
  legacyHashes: entry.legacyHashes,
  moduleKey: entry.moduleKey,
}))

const DESIGN_SOURCE_CATALOG: Record<string, DesignSourceRecord> = {
  'development/latest-dev-docs/ops-frontend/F_PLAN/frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md': {
    sourceType: 'figma',
    sourceRef: 'development/latest-dev-docs/ops-frontend/F_PLAN/frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md',
    targetLayers: ['A', 'B', 'C'],
    reuseTarget: 'structure',
    validationMethod: 'verify file id, root node, pulled node ids, and token intent before implementation',
  },
  'main/frontend-modern/src/pages/ConceptQuietPage.tsx': {
    sourceType: 'demo',
    sourceRef: 'main/frontend-modern/src/pages/ConceptQuietPage.tsx',
    targetLayers: ['A'],
    reuseTarget: 'visual_semantics',
    validationMethod: 'preserve quiet editorial rhythm and continuous workbench context',
  },
  'main/frontend-modern/src/pages/ConceptOrbitalPage.tsx': {
    sourceType: 'demo',
    sourceRef: 'main/frontend-modern/src/pages/ConceptOrbitalPage.tsx',
    targetLayers: ['B'],
    reuseTarget: 'visual_semantics',
    validationMethod: 'preserve spatial analysis feel and object-observation emphasis',
  },
  'main/frontend-modern/src/pages/ConceptMonolithPage.tsx': {
    sourceType: 'demo',
    sourceRef: 'main/frontend-modern/src/pages/ConceptMonolithPage.tsx',
    targetLayers: ['C'],
    reuseTarget: 'visual_semantics',
    validationMethod: 'preserve governance-oriented density and hard-edge operational rhythm',
  },
  'reference-pool/oss/outline/app/components/Sidebar': {
    sourceType: 'reference_pool',
    sourceRef: 'reference-pool/oss/outline/app/components/Sidebar',
    targetLayers: ['A', 'C'],
    reuseTarget: 'interaction',
    validationMethod: 'reuse navigation and side-panel structure without copying brand styling',
  },
  'reference-pool/oss/silverbullet-ai/src/chat-panel.ts': {
    sourceType: 'reference_pool',
    sourceRef: 'reference-pool/oss/silverbullet-ai/src/chat-panel.ts',
    targetLayers: ['A'],
    reuseTarget: 'interaction',
    validationMethod: 'reuse assistant panel organization only when it serves the writing/workbench loop',
  },
  'reference-pool/oss/codemirror-view/src/tooltip.ts': {
    sourceType: 'reference_pool',
    sourceRef: 'reference-pool/oss/codemirror-view/src/tooltip.ts',
    targetLayers: ['A', 'B'],
    reuseTarget: 'interaction',
    validationMethod: 'reuse tooltip/panel interaction to support info cards and object details',
  },
}

export const designSourceRecords: readonly DesignSourceRecord[] = Array.from(
  new Set(moduleManifest.flatMap((entry) => entry.designSourceRefs)),
)
  .map((sourceRef) => DESIGN_SOURCE_CATALOG[sourceRef])
  .filter(Boolean)

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
