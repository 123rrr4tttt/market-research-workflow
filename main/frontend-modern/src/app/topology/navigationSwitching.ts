import type { NavMode } from '../kernel/types'
import { getSurfaceModes, resolvePlacedSurface } from './pagePlacementMatrix'
import type { InteractionSurface } from './surfaces'

export type SurfaceLastModeMap = Partial<Record<InteractionSurface, NavMode>>

export const SURFACE_DEFAULT_ENTRY_MODE: Record<InteractionSurface, NavMode> = {
  management: 'overviewTasks',
  workbench: 'flowWriting',
}

export function resolveSurfaceSwitchTarget(targetSurface: InteractionSurface, lastModeBySurface: SurfaceLastModeMap): NavMode {
  const remembered = lastModeBySurface[targetSurface]
  if (remembered && resolvePlacedSurface(remembered) === targetSurface) return remembered

  const candidates = getSurfaceModes(targetSurface)
  if (candidates.length > 0) return candidates[0]

  return SURFACE_DEFAULT_ENTRY_MODE[targetSurface]
}

export function updateLastModeBySurface(current: SurfaceLastModeMap, mode: NavMode): SurfaceLastModeMap {
  const surface = resolvePlacedSurface(mode)
  return {
    ...current,
    [surface]: mode,
  }
}
