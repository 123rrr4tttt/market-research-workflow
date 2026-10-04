export {
  buildRegistryHashMap,
  getModuleDescriptor,
  getModulesByGroup,
  getModulesBySurface,
  moduleRegistry,
  verifyRegistryHashCompatibility,
} from './registry'
export type { ModuleRenderer, ModuleRendererArgs, ModuleRendererBinding } from '../../kernel/moduleContributionRule'
export { getModuleRendererBinding } from '../../kernel/moduleContributionRule'
export {
  MODULE_NAV_GROUP_KEYS,
  type ModuleDescriptor,
  type ModuleInteractionProfile,
  type ModuleNavGroupKey,
  type ModuleNavLabelKey,
  type ModuleTitleKey,
  type RegisteredNavMode,
} from './types'
