import { moduleManifest } from '../../../app/kernel/moduleManifest'
import type { KernelModuleKey } from '../../../app/kernel/types'
import type { MessageKey } from '../../../app/platform/i18n'
import { GRAPH_PROJECTIONS, type GraphProjectionId } from './definitions'

/** Project-declared narrowing of the unified topology read model for one view. */
export type GraphTopologyFilter = {
  attribute: string
  containsAny: readonly string[]
}

/** One project-owned binding onto an existing graph entry point. */
export type GraphProjectionBinding = {
  id: string
  label?: string
  hidden?: boolean
  topologyFilter?: GraphTopologyFilter
}

export type GraphWorkspaceTab = {
  moduleKey: KernelModuleKey
  routePath: string
  labelKey: MessageKey
  projectionId?: GraphProjectionId
  isBuilder: boolean
  /** Project-authored label; falls back to the shared translation key. */
  label?: string
  topologyFilter?: GraphTopologyFilter
}

export const GRAPH_WORKSPACE_TABS: readonly GraphWorkspaceTab[] = moduleManifest
  .filter((entry) => entry.navGroupKey === 'navigation.group.graph')
  .map((entry) => {
    const projectionId = entry.moduleKey in GRAPH_PROJECTIONS
      ? entry.moduleKey as GraphProjectionId
      : undefined
    return {
      moduleKey: entry.moduleKey,
      routePath: entry.entryRoute,
      labelKey: entry.navLabelKey,
      projectionId,
      isBuilder: entry.moduleKey === 'graphBuilder',
    }
  })

export function getGraphWorkspaceRoute(moduleKey: KernelModuleKey): string {
  return moduleManifest.find((entry) => entry.moduleKey === moduleKey)?.entryRoute || '/visual/graph/market'
}

/** Coerce the project-declared projection bindings from the graph config payload. */
export function coerceGraphProjectionBindings(value: unknown): GraphProjectionBinding[] {
  if (!Array.isArray(value)) return []
  const bindings: GraphProjectionBinding[] = []
  for (const item of value) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    const raw = item as Record<string, unknown>
    const id = String(raw.id ?? '').trim()
    if (!id) continue
    const label = String(raw.label ?? '').trim()
    const filterRaw = raw.topology_filter
    let topologyFilter: GraphTopologyFilter | undefined
    if (filterRaw && typeof filterRaw === 'object' && !Array.isArray(filterRaw)) {
      const filter = filterRaw as Record<string, unknown>
      const attribute = String(filter.attribute ?? '').trim()
      const tokens = Array.isArray(filter.contains_any)
        ? filter.contains_any.map((token) => String(token ?? '').trim()).filter(Boolean)
        : []
      if (attribute && tokens.length) topologyFilter = { attribute, containsAny: tokens }
    }
    bindings.push({
      id,
      label: label || undefined,
      hidden: Boolean(raw.hidden),
      topologyFilter,
    })
  }
  return bindings
}

/**
 * Apply project bindings to the shared tab list: the project chooses what is
 * visible, its order and its labels. Entry points the project does not mention
 * stay available at the end, so a newly added module is never silently dropped.
 */
export function applyWorkspaceTabBindings(
  tabs: readonly GraphWorkspaceTab[],
  bindings: readonly GraphProjectionBinding[],
): GraphWorkspaceTab[] {
  if (!bindings.length) return [...tabs]
  const remaining = new Map(tabs.map((tab) => [tab.moduleKey, tab]))
  const ordered: GraphWorkspaceTab[] = []
  for (const binding of bindings) {
    const base = remaining.get(binding.id as KernelModuleKey)
    if (!base) continue
    remaining.delete(binding.id as KernelModuleKey)
    if (binding.hidden) continue
    ordered.push({
      ...base,
      label: binding.label ?? base.label,
      topologyFilter: binding.topologyFilter ?? base.topologyFilter,
    })
  }
  return [...ordered, ...tabs.filter((tab) => remaining.has(tab.moduleKey))]
}
