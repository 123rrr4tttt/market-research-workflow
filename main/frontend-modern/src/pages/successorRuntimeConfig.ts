import type { SuccessorProjectSourceKey, SuccessorQueryOptions } from '../lib/api/domains/successor-runtime'

/**
 * Read-only projection identity for the successor runtime kernel module.
 *
 * The values mirror the C9 local-offline projector contract in
 * `main/backend/app/successor_runtime/assembly/c9_assembly.py` so the page can
 * be exercised against the closed LOCAL_ONLY mount before any per-run
 * projection key is supplied by the backend registry.  The page never
 * constructs a v2 URL itself and never submits a command; it only passes this
 * projection locator through the successor query client.
 */
export const SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID =
  'projection.sys-successor-runtime.v1'

export const SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY: SuccessorProjectSourceKey = {
  projector_id: 'c9.local-offline.validation.projector.v1',
  projector_version: '1.0.0',
  source_kind: 'CANONICAL_OWNER',
  source_ref: 'local-offline:facade-validation',
  source_incarnation: 'local-offline:facade-validation-inc-1',
}

export function buildSuccessorRuntimeObservationQueryOptions(
  projectLocator: string,
): SuccessorQueryOptions {
  return {
    queryId: SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID,
    queryKind: 'projection_snapshot',
    projectLocator,
    params: {
      params_kind: 'projection_snapshot',
      projection_id: SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID,
      ...SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY,
      page_size: 25,
    },
  }
}
