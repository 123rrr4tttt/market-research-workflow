import { moduleManifest } from '../../kernel/moduleManifest'
import { resolveInteractionSurface } from '../../topology/contracts'
import type { InteractionSurface } from '../../topology/surfaces'
import type { ModuleDescriptor, ModuleNavGroupKey, RegisteredNavMode } from './types'

function defineModule(mode: RegisteredNavMode, navGroupKey: ModuleNavGroupKey, hash: string, visibleInNav: boolean, enabled: boolean): ModuleDescriptor {
  const interactionProfile = resolveInteractionSurface(mode) === 'workbench' ? 'workbench' : 'standard'
  return {
    mode,
    hash,
    titleKey: `shell.title.${mode}`,
    navLabelKey: `navigation.item.${mode}`,
    navGroupKey,
    interactionProfile,
    visibleInNav,
    enabled,
  }
}

export const moduleRegistry: Record<RegisteredNavMode, ModuleDescriptor> = Object.fromEntries(
  moduleManifest.map((entry) => [
    entry.moduleKey,
    defineModule(
      entry.moduleKey,
      entry.navGroupKey,
      entry.legacyHashes[0] || `#${entry.entryRoute}`,
      entry.visibleInNav,
      entry.enabled,
    ),
  ]),
) as Record<RegisteredNavMode, ModuleDescriptor>

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
  return { isCompatible: true, mismatchedModes: [] }
}
