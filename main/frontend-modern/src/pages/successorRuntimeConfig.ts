import type { SuccessorProjectSourceKey, SuccessorQueryOptions } from '../lib/api/domains/successor-runtime'

/**
 * Read-only projection identity for the successor runtime kernel module.
 *
 * The source key names the active project material source.  The
 * production-registry HTTP read facade resolves that business identity to an
 * exact project-scoped revision/incarnation/digest before returning data.  If
 * the project has no committed material source the query remains honestly
 * unavailable; the UI never substitutes a historical acceptance document.
 */
export const SUCCESSOR_RUNTIME_OBSERVATION_PROJECTION_ID =
  'projection.project-material.v2'

export function buildSuccessorRuntimeObservationSourceKey(
  projectLocator: string,
): SuccessorProjectSourceKey {
  const projectKey = projectLocator.trim()
  return {
    projector_id: 'projection.project-material.v2',
    projector_version: '2.0.0',
    source_kind: 'material',
    source_ref: `material:${projectKey}`,
    source_incarnation: `active-project:${projectKey}`,
  }
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
      ...buildSuccessorRuntimeObservationSourceKey(projectLocator),
      page_size: 25,
    },
  }
}
