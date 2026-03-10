import type { NavMode } from '../../components/FigmaSideNav'
import { resolvePlacedSurface } from './pagePlacementMatrix'
import type { InteractionSurface } from './surfaces'

export type TopologyScope = {
  topic: 'dual-interaction-frontend-topology'
  baseline: 'modern-only'
  interpretation: 'two-interaction-surfaces'
  nonGoals: readonly string[]
}

export const TOPOLOGY_SCOPE: TopologyScope = {
  topic: 'dual-interaction-frontend-topology',
  baseline: 'modern-only',
  interpretation: 'two-interaction-surfaces',
  nonGoals: [
    'legacy-frontend-coexistence',
    'dual-codebase-migration',
    'multi-app-deployment-split',
  ] as const,
}

export function resolveInteractionSurface(mode: NavMode): InteractionSurface {
  return resolvePlacedSurface(mode)
}
