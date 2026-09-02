import type { SuccessorProjectSourceKey, SuccessorQueryOptions } from '../lib/api/domains/successor-runtime'

/**
 * Read-only projection identity for the successor runtime kernel module.
 *
 * The source key names the real committed C7 canonical document that the
 * production-registry HTTP read facade answers from PostgreSQL
 * (c7_movement_canonical_documents) through the deterministic search
 * projector.  In a LOCAL_ONLY mount the query fails closed as unavailable,
 * which is the intended production semantics: the page only displays real
 * committed data once the registry-backed backend is serving it.  The page
 * never constructs a v2 URL itself and never submits a command.
 */
export const SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID =
  'projection.c7-production-document.v1'

export const SUCCESSOR_RUNTIME_OBSERVATION_SOURCE_KEY: SuccessorProjectSourceKey = {
  projector_id: 'successor.ingest_index.search.projector',
  projector_version: '1.0.0',
  source_kind: 'ingest_canonical',
  source_ref: 'document:ingest-doc:c7-production-cutover-acceptance-2026-09-03',
  source_incarnation: 'incarnation:production-go-live:v1',
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
