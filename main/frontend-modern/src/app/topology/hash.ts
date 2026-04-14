import { parseLegacyHashToMode } from '../navigation'
import { resolveInteractionSurface } from './contracts'
import type { InteractionSurface } from './surfaces'

type StandaloneView = 'llm-designer' | 'writing-workbench'

function decodeHashPath(hash: string): string {
  const decoded = decodeURIComponent((hash || '').replace(/^#/, '')).trim().toLowerCase()
  if (!decoded) return ''
  const [pathQuery] = decoded.split('#')
  const [path] = pathQuery.split('?')
  return path
}

export function resolveStandaloneView(hash: string): StandaloneView | null {
  const path = decodeHashPath(hash)
  if (!path) return null
  if (path.includes('llm-designer.html')) return 'llm-designer'
  if (path.includes('writing-workbench.html') || path.includes('writing.html')) return 'writing-workbench'

  const mode = parseLegacyHashToMode(hash)
  if (mode === 'flowLlmNodeDesign') return 'llm-designer'
  if (mode === 'flowWriting') return 'writing-workbench'
  return null
}

export function resolveSurfaceByHash(hash: string): InteractionSurface | null {
  const mode = parseLegacyHashToMode(hash)
  if (!mode) return null
  return resolveInteractionSurface(mode)
}
