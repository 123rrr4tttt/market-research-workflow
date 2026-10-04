import type {
  BoundRef,
  ElementRef,
  Endpoint,
  TopologyElement,
  TopologyState,
} from './types'

export const TOPOLOGY_STRUCTURAL_FIELDS = [
  'content_name',
  'content_summary',
  'content_order',
  'structural_role',
  'source_uri',
  'source_status',
] as const

export type TopologyStructuralField = (typeof TOPOLOGY_STRUCTURAL_FIELDS)[number]
export type TopologyStructuralRole = 'member' | 'relation' | 'root' | 'annotation'

export type TopologyCreationContract = {
    structuralFields: readonly TopologyStructuralField[]
}

export function defineTopologyCreationContract(
    structuralFields: readonly TopologyStructuralField[],
): TopologyCreationContract {
    const invalid = structuralFields.find((field) => !(TOPOLOGY_STRUCTURAL_FIELDS as readonly string[]).includes(field))
    if (invalid) throw new Error(`Unknown topology structural field ${invalid}.`)
    return { structuralFields }
}

export type CreateTopologyElementInput = {
  projectKey: string
  moduleId: string
  namespace: string
  typeId: string
  localId: string
  observedRevision: string
  contentName?: string
  contentSummary?: string
  contentOrder?: number
  structuralRole?: TopologyStructuralRole
  sourceUri?: string
  sourceStatus?: string
  moduleAttributes?: Record<string, unknown>
  endpoints?: Endpoint[]
}

export type CreateTopologyStateInput = {
  profileId: string
  profileVersion: string
  elements: TopologyElement[]
}

function nonempty(value: string | undefined): string | undefined {
  const normalized = value?.trim()
  if (normalized) return normalized
  return undefined
}

export function createTopologyBoundRef(args: {
  projectKey: string
  moduleId: string
  namespace: string
  typeId: string
  localId: string
  observedRevision: string
  contentDigest?: string | null
}): BoundRef {
  const identity: ElementRef = {
    project_key: args.projectKey,
    module_id: args.moduleId,
    namespace: args.namespace,
    type_id: args.typeId,
    local_id: args.localId,
  }
  return {
    ref: identity,
    observed_revision: args.observedRevision,
    content_digest: args.contentDigest ?? null,
  }
}

export function createTopologyElement(
    contract: TopologyCreationContract,
    input: CreateTopologyElementInput,
): TopologyElement {
    const enabledStructuralFields = new Set<string>(contract.structuralFields)
    for (const [key, value] of Object.entries(input.moduleAttributes || {})) {
    if (enabledStructuralFields.has(key)) {
      throw new Error(`Module attributes cannot override structural field ${key}.`)
    }
    if (value === undefined) continue
  }
  if (!input.observedRevision.trim()) throw new Error('Topology elements require an observed revision.')

  const attributes: Record<string, unknown> = { ...(input.moduleAttributes || {}) }
  const contentName = nonempty(input.contentName)
  const contentSummary = nonempty(input.contentSummary)
  const sourceUri = nonempty(input.sourceUri)
  const sourceStatus = nonempty(input.sourceStatus)
  if (contentName && enabledStructuralFields.has('content_name')) attributes.content_name = contentName
  if (contentSummary && enabledStructuralFields.has('content_summary')) attributes.content_summary = contentSummary
  if (input.contentOrder != null) {
    if (!Number.isInteger(input.contentOrder) || input.contentOrder < 0) {
      throw new Error('contentOrder must be a nonnegative integer.')
    }
    if (enabledStructuralFields.has('content_order')) attributes.content_order = input.contentOrder
  }
  if (input.structuralRole && enabledStructuralFields.has('structural_role')) attributes.structural_role = input.structuralRole
  if (sourceUri && enabledStructuralFields.has('source_uri')) attributes.source_uri = sourceUri
  if (sourceStatus && enabledStructuralFields.has('source_status')) attributes.source_status = sourceStatus

  const endpoints = input.endpoints || []
  const invalidEndpoint = endpoints.find((endpoint) => !endpoint.role.trim() || !endpoint.target.observed_revision.trim())
  if (invalidEndpoint) throw new Error('Topology endpoints require a role and an observed target revision.')

  return {
    ref: createTopologyBoundRef(input),
    attributes,
    endpoints,
  }
}

export function createTopologyState(input: CreateTopologyStateInput): TopologyState {
  const identities = new Set(input.elements.map((element) => JSON.stringify(element.ref)))
  if (identities.size !== input.elements.length) throw new Error('Topology state contains duplicate bound elements.')
  return {
    profile_id: input.profileId,
    profile_version: input.profileVersion,
    elements: input.elements,
  }
}
