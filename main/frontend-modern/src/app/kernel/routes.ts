import { parseLegacyHashToMode } from '../navigation'
import { getKernelModuleContract, routeManifest } from './contracts'
import { DEFAULT_KERNEL_MODULE } from './moduleManifest'
import type { KernelModuleKey, KernelRouteState } from './types'

const routeByPath = new Map<string, (typeof routeManifest)[number]>(routeManifest.map((item) => [item.routePath, item]))

function normalizeHashPath(hash: string): string {
  const decoded = decodeURIComponent((hash || '').replace(/^#/, '')).trim()
  if (!decoded) return ''
  const [pathQuery] = decoded.split('#')
  const [path] = pathQuery.split('?')
  const normalized = path.startsWith('/') ? path : `/${path}`
  return normalized.toLowerCase()
}

export function buildLayerRouteHash(moduleKey: KernelModuleKey): `#/${string}` {
  return `#${getKernelModuleContract(moduleKey).entryRoute}` as `#/${string}`
}

export function resolveKernelRoute(hash: string): KernelRouteState {
  const normalizedPath = normalizeHashPath(hash)
  if (normalizedPath) {
    const layered = routeByPath.get(normalizedPath)
    if (layered) {
      return {
        source: 'layered',
        moduleKey: layered.moduleKey,
        layerId: layered.layerId,
        surfaceKind: layered.surfaceKind,
        routePath: layered.routePath,
        routeHash: `#${layered.routePath}` as `#/${string}`,
      }
    }
  }

  const legacyMode = parseLegacyHashToMode(hash)
  if (legacyMode) {
    const contract = getKernelModuleContract(legacyMode)
    return {
      source: 'legacy',
      moduleKey: legacyMode,
      layerId: contract.layerId,
      surfaceKind: contract.surfaceKind,
      routePath: contract.entryRoute,
      routeHash: buildLayerRouteHash(legacyMode),
    }
  }

  if (!normalizedPath) {
    const contract = getKernelModuleContract(DEFAULT_KERNEL_MODULE)
    return {
      source: 'default',
      moduleKey: DEFAULT_KERNEL_MODULE,
      layerId: contract.layerId,
      surfaceKind: contract.surfaceKind,
      routePath: contract.entryRoute,
      routeHash: buildLayerRouteHash(DEFAULT_KERNEL_MODULE),
    }
  }

  const contract = getKernelModuleContract(DEFAULT_KERNEL_MODULE)
  return {
    source: 'unknown',
    moduleKey: DEFAULT_KERNEL_MODULE,
    layerId: contract.layerId,
    surfaceKind: contract.surfaceKind,
    routePath: contract.entryRoute,
    routeHash: buildLayerRouteHash(DEFAULT_KERNEL_MODULE),
  }
}
