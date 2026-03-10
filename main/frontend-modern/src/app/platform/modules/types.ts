import { hashByMode } from '../../navigation'

export type RegisteredNavMode = keyof typeof hashByMode

export type ModuleInteractionProfile = 'standard' | 'workbench'

export const MODULE_NAV_GROUP_KEYS = [
  'navigation.group.overview',
  'navigation.group.dataFacets',
  'navigation.group.graph',
  'navigation.group.flow',
  'navigation.group.system',
] as const

export type ModuleNavGroupKey = (typeof MODULE_NAV_GROUP_KEYS)[number]
export type ModuleNavLabelKey = `navigation.item.${RegisteredNavMode}`
export type ModuleTitleKey = `shell.title.${RegisteredNavMode}`

export type ModuleDescriptor = {
  mode: RegisteredNavMode
  hash: (typeof hashByMode)[RegisteredNavMode]
  titleKey: ModuleTitleKey
  navLabelKey: ModuleNavLabelKey
  navGroupKey: ModuleNavGroupKey
  interactionProfile: ModuleInteractionProfile
  visibleInNav: boolean
  enabled: boolean
}

