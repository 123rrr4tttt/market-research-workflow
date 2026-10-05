import type { BoundRef } from './types'
import { normalizeMaterialRef } from './materialIdentity'

export type ReferenceStatus = {
  ref: BoundRef
  status: 'resolved' | 'stale' | 'unresolvable'
  current_revision?: string
}

function identity(ref: BoundRef['ref']) {
  const canonical = normalizeMaterialRef(ref)
  return [canonical.project_key, canonical.module_id, canonical.namespace, canonical.type_id, canonical.local_id].join('\u0000')
}

/** Compare version-bound references with the current refs returned by resolve(). */
export function classifyReference(ref: BoundRef, currentRefs: BoundRef[]): ReferenceStatus {
  const current = currentRefs.find((candidate) => identity(candidate.ref) === identity(ref.ref))
  if (!current) return { ref, status: 'unresolvable' }
  const digestChanged = ref.content_digest != null && current.content_digest != null
    && ref.content_digest !== current.content_digest
  if (current.observed_revision !== ref.observed_revision || digestChanged) {
    return { ref, status: 'stale', current_revision: current.observed_revision }
  }
  return { ref, status: 'resolved', current_revision: current.observed_revision }
}
