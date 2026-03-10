import type { NavMode } from '../../components/FigmaSideNav'
import type { InteractionSurface } from './surfaces'

export type SharedCapabilityId =
  | 'project-context'
  | 'route-normalization'
  | 'api-query-convention'
  | 'theme-i18n'
  | 'global-feedback'

export type SharedCapability = {
  id: SharedCapabilityId
  description: string
  anchors: readonly string[]
}

export type SurfaceOwnedCapability = {
  id: 'container-density' | 'secondary-navigation' | 'panel-layout' | 'immersive-launch'
  description: string
}

export const SHARED_PLATFORM_CAPABILITIES: readonly SharedCapability[] = [
  {
    id: 'project-context',
    description: 'Project context is global and retained across both surfaces.',
    anchors: ['app-shell:projectKey', 'api:getProjectKey', 'shell-prefs:pendingProjectKey'],
  },
  {
    id: 'route-normalization',
    description: 'Nav mode/hash parsing stays unified for deep-link compatibility.',
    anchors: ['navigation:hashByMode', 'navigation:parseLegacyHashToMode'],
  },
  {
    id: 'api-query-convention',
    description: 'Query key and API client conventions are shared and surface-agnostic.',
    anchors: ['lib:queryKeys', 'lib:api-client', 'react-query-provider'],
  },
  {
    id: 'theme-i18n',
    description: 'Theme and locale remain shared platform concerns.',
    anchors: ['platform:theme', 'platform:i18n', 'app-storage:locale/theme'],
  },
  {
    id: 'global-feedback',
    description: 'Global loading/error/status notification style is shared.',
    anchors: ['app-shell:status-chips', 'shared:status-line/chip', 'suspense-fallback'],
  },
] as const

export const SURFACE_OWNED_CAPABILITIES: readonly SurfaceOwnedCapability[] = [
  {
    id: 'container-density',
    description: 'Container density and spacing are surface-specific by task style.',
  },
  {
    id: 'secondary-navigation',
    description: 'Secondary nav composition differs by surface and module depth.',
  },
  {
    id: 'panel-layout',
    description: 'Panel orchestration and panel persistence are surface-specific.',
  },
  {
    id: 'immersive-launch',
    description: 'Immersive/standalone launch behavior remains a surface-owned decision.',
  },
] as const

export const SHARED_CONTRACT_NOTE =
  'Shared platform contract defines capability reuse boundaries, not identical shell UX.'

export type SurfaceSwitchRule = {
  retain: readonly string[]
  reset: readonly string[]
}

export const SURFACE_SWITCH_RULES: Record<InteractionSurface, SurfaceSwitchRule> = {
  management: {
    retain: ['projectKey', 'theme', 'locale', 'deep-link-compatible route identity'],
    reset: ['page-local transient selection', 'panel expansion state', 'focus-only temporary filters'],
  },
  workbench: {
    retain: ['projectKey', 'theme', 'locale', 'deep-link-compatible route identity'],
    reset: ['page-local transient selection', 'panel expansion state', 'focus-only temporary filters'],
  },
}

export const IMMERSIVE_SURFACE_EXCEPTIONS: ReadonlyArray<{
  mode: NavMode
  behavior: string
}> = [
  {
    mode: 'flowLlmNodeDesign',
    behavior: 'launch-standalone-window-first-with-fallback-to-same-tab',
  },
]
