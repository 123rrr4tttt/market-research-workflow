/** Public wire types for the information topology API (snake_case matches the backend). */

export type ElementRef = {
  project_key: string
  module_id: string
  namespace: string
  type_id: string
  local_id: string
}

export type BoundRef = {
  ref: ElementRef
  observed_revision: string
  content_digest?: string | null
}

export type Endpoint = {
  role: string
  target: BoundRef
  position?: number | null
}

export type TopologyElement = {
  ref: BoundRef
  attributes: Record<string, unknown>
  endpoints: Endpoint[]
}

export type TopologyState = {
  profile_id: string
  profile_version: string
  elements: TopologyElement[]
}

export type TopologyView = {
  definition_id: string
  definition_version: string
  input_revisions: Record<string, string>
  members: BoundRef[]
  relations: BoundRef[]
  organization: Record<string, unknown>
}

export type TopologyRef = {
  module_id: string
  namespace: string
  state_id: string
  revision?: number | null
}

export type MappingCorrespondence = {
  source: BoundRef
  targets: BoundRef[]
}

export type MappingPreview = {
  mapping_id: string
  output: TopologyState
  correspondences: MappingCorrespondence[]
  unmapped: BoundRef[]
  coverage: 'total' | 'partial'
  fidelity: 'lossless' | 'lossy' | 'unverified'
}

export type TopologyList<T> = { items: T[]; total: number }
export type TopologyProfileDescription = {
  profile_id: string
  version: string
  types: string[]
  relation_types: string[]
}
export type TopologyReadResult = { topology: TopologyState; revision: number; digest: string }
export type CurrentTopologyItem = {
  topology_ref: Omit<TopologyRef, 'revision'>
  profile_id: string
  profile_version: string
  revision: number
  digest: string
  element_count: number
  topology: TopologyState
}
export type TopologyRelation = {
  link_id: string
  revision: number
  relation_type: string
  endpoints: Array<Record<string, unknown>>
  payload: Record<string, unknown>
  provenance: Record<string, unknown>
}
export type TopologyImportResult = { import_result: Record<string, unknown> }
export type TopologyExportResult = { export_result: Record<string, unknown> }

export type TopologyFailureCode =
  | 'INVALID_STRUCTURE' | 'INVALID_PATCH' | 'VERSION_CONFLICT' | 'NOT_FOUND'
  | 'STALE_REFERENCE' | 'UNRESOLVABLE_REFERENCE' | 'UNKNOWN_PROFILE'
  | 'MAPPING_NOT_APPLICABLE' | 'SOURCE_CHANGED' | 'IDENTITY_CONFLICT'
  | 'INVALID_WIRE_FORMAT'

export type TopologyApiFailure = {
  code: TopologyFailureCode | string
  message: string
  details?: Record<string, unknown>
}

export type TopologyPatchOperation =
  | { action: 'remove'; ref: BoundRef }
  | { action: 'add' | 'replace'; ref: BoundRef; element: TopologyElement }

export type TopologyStatePatchRequest =
  | {
      target: TopologyRef
      base_revision: null
      initial_state: TopologyState
      patch?: TopologyPatchOperation[]
    }
  | {
      target: TopologyRef
      base_revision: number
      initial_state?: never
      patch: TopologyPatchOperation[]
    }

type TopologyPatchBatchShared = {
  link_writes?: Array<{
    link_id: string
    record_kind: 'relation' | 'mapping'
    type_or_rule_ref: string
    endpoints: Array<Record<string, unknown>>
    payload?: Record<string, unknown>
    base_revision?: number | null
    provenance?: Record<string, unknown>
  }>
  read_set?: Array<{ target: TopologyRef; base_revision: number }>
  link_read_set?: Array<{ link_id: string; base_revision: number }>
}

export type TopologyPatchBatchRequest = TopologyPatchBatchShared & (
  | {
      state_patches: TopologyStatePatchRequest[]
      target?: never
      base_revision?: never
      patch?: never
    }
  | {
      // Legacy single-state update form. Creates use state_patches so that
      // base_revision=null is paired with the required initial_state.
      state_patches?: never
      target: TopologyRef
      base_revision: number
      patch: TopologyPatchOperation[]
    }
  | {
      state_patches?: never
      target?: never
      base_revision?: never
      patch?: never
    }
)

export type TopologyPatchResult = {
  state_revisions: Array<{ target: TopologyRef; revision: number; topology: TopologyState }>
  link_revisions: Array<{ link_id: string; revision: number }>
}
