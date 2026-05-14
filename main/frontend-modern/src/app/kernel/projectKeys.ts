import { normalizeProjectKey } from '../../lib/api/client'
import type { ProjectItem } from '../../lib/types'

export const BOOTSTRAP_PROJECT_KEY = 'business_survey'

const RESERVED_PROJECT_KEYS = new Set(['default', 'public'])

function normalizeOptionalProjectKey(raw: string | null | undefined) {
  const value = String(raw || '').trim()
  return value ? normalizeProjectKey(value) : ''
}

export function isReservedProjectKey(raw: string | null | undefined) {
  const key = normalizeOptionalProjectKey(raw)
  return key ? RESERVED_PROJECT_KEYS.has(key) : false
}

export function resolveBootstrapTarget(raw: string | null | undefined) {
  const key = normalizeOptionalProjectKey(raw)
  if (!key || isReservedProjectKey(key)) return BOOTSTRAP_PROJECT_KEY
  return key
}

export function buildProjectOptions({
  activeProjectKey,
  pendingProjectKey,
  projects,
}: {
  activeProjectKey: string
  pendingProjectKey?: string
  projects?: ProjectItem[] | null
}) {
  const rows = projects || []
  const options: ProjectItem[] = []
  const seen = new Set<string>()

  const add = (key: string | null | undefined, fallbackName?: string) => {
    const normalized = normalizeOptionalProjectKey(key)
    if (!normalized || RESERVED_PROJECT_KEYS.has(normalized) || seen.has(normalized)) return
    const existing = rows.find((item) => item.project_key === normalized)
    options.push(existing || { project_key: normalized, name: fallbackName || normalized, enabled: true })
    seen.add(normalized)
  }

  for (const row of rows) add(row.project_key, row.name)
  add(activeProjectKey, activeProjectKey)

  if (!options.length) {
    add(resolveBootstrapTarget(pendingProjectKey), pendingProjectKey)
    add(BOOTSTRAP_PROJECT_KEY, 'Business Survey')
  }

  return options
}

export function hasProject(projects: ProjectItem[] | null | undefined, projectKey: string | null | undefined) {
  const normalized = normalizeOptionalProjectKey(projectKey)
  if (!normalized || isReservedProjectKey(normalized)) return false
  return Boolean((projects || []).some((item) => item.project_key === normalized))
}

export function resolveEffectiveProjectKey({
  projects,
  currentProjectKey,
  pendingProjectKey,
}: {
  projects: ProjectItem[] | null | undefined
  currentProjectKey?: string | null
  pendingProjectKey?: string | null
}) {
  const rows = projects || []
  const current = normalizeOptionalProjectKey(currentProjectKey)
  if (current && !RESERVED_PROJECT_KEYS.has(current) && rows.some((item) => item.project_key === current)) return current

  const active = rows.find((item) => item.enabled !== false && item.is_active)
  if (active?.project_key) return normalizeOptionalProjectKey(active.project_key)

  const firstEnabled = rows.find((item) => item.enabled !== false && !isReservedProjectKey(item.project_key))
  if (firstEnabled?.project_key) return normalizeOptionalProjectKey(firstEnabled.project_key)

  return resolveBootstrapTarget(pendingProjectKey || currentProjectKey)
}
