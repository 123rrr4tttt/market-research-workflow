import type { KernelModuleKey, ModuleNavGroupKey } from '../../kernel/types'
export { MODULE_NAV_GROUP_KEYS } from '../../kernel/types'
export type { ModuleNavGroupKey } from '../../kernel/types'

export type RegisteredNavMode = KernelModuleKey

export type ModuleInteractionProfile = 'standard' | 'workbench'
export type ModuleNavLabelKey = `navigation.item.${RegisteredNavMode}`
export type ModuleTitleKey = `shell.title.${RegisteredNavMode}`

export type ModuleDescriptor = {
  mode: RegisteredNavMode
  hash: string
  titleKey: ModuleTitleKey
  navLabelKey: ModuleNavLabelKey
  navGroupKey: ModuleNavGroupKey
  interactionProfile: ModuleInteractionProfile
  visibleInNav: boolean
  enabled: boolean
}
