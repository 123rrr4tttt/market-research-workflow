/**
 * C9.2 successor runtime client (frontend projection package).
 *
 * Mirrors the backend v2 transport contracts in
 * `main/backend/app/contracts/successor_runtime.py` and
 * `main/backend/app/api/successor_runtime.py`:
 * - external command/query carry only locator + discriminated typed intent;
 * - envelope preserves status/data/error/meta plus control_feedback=false;
 * - browser storage holds only a project preference and pending command
 *   id/fingerprint, never actor, resolved scope, approval or authority;
 * - successor fetches never inject `X-Project-Key` or a `project_key` query;
 * - explicit retry requires the same command id and payload fingerprint;
 * - concurrent duplicate submits share one in-flight request;
 * - query refetch is read-only and never dispatches commands or control;
 * - decode is fail-closed for malformed status, variant and meta shapes.
 */

export const SUCCESSOR_V2_API_PATH = '/api/v1/successor-runtime/v2'
export const SUCCESSOR_V2_COMMAND_URL = `${SUCCESSOR_V2_API_PATH}/commands`
export const SUCCESSOR_V2_QUERY_URL = `${SUCCESSOR_V2_API_PATH}/queries`

export const SUCCESSOR_ENVELOPE_STATUSES = [
  'ok',
  'waiting',
  'blocked',
  'unavailable',
  'conflict',
  'error',
] as const
export type SuccessorEnvelopeStatus = (typeof SUCCESSOR_ENVELOPE_STATUSES)[number]

/**
 * C9.2 frontend six-state observation vocabulary.
 *
 * The UI derives exactly one observation from the command lifecycle and the
 * server envelope. The observation is a disposable read-model projection and
 * never claims runtime completion, approval or authority.
 */
export const SUCCESSOR_UI_OBSERVATION_STATES = [
  'NOT_STARTED',
  'IN_FLIGHT',
  'SUCCEEDED',
  'FAILED',
  'OUTCOME_UNKNOWN',
  'REJECTED_TYPED',
] as const
export type SuccessorUiObservationState = (typeof SUCCESSOR_UI_OBSERVATION_STATES)[number]

export type SuccessorEnvelopeError = {
  code: string
  message: string
  details?: Record<string, unknown>
}

/**
 * Typed command rejection reasons accepted by the frontend observation layer.
 *
 * The list mirrors the C9.1 typed failure family that the facade can return
 * for a refused command. Codes outside this set are deliberately not decoded
 * as typed rejections so the UI fails closed instead of inventing a reason.
 */
export const SUCCESSOR_TYPED_REJECTION_CODES = [
  'INVALID_INPUT',
  'NOT_FOUND',
  'CONFLICT',
  'UNAUTHORIZED',
  'FORBIDDEN',
  'RATE_LIMITED',
  'SCOPE_RESOLUTION_FAILED',
] as const
export type SuccessorTypedRejectionCode = (typeof SUCCESSOR_TYPED_REJECTION_CODES)[number]

export type SuccessorTypedRejectionReason = {
  code: SuccessorTypedRejectionCode
  message: string
  details: Record<string, unknown>
  meta: SuccessorEnvelopeMeta
}

export type SuccessorProjectScopeRef = {
  project_key: string
  resolved_schema: string
  project_registry_revision: number
  incarnation: string
  scope_digest: string
}

export type SuccessorCommandMeta = {
  project_key: string
  trace_id: string
  command_id: string
  project_scope_ref: SuccessorProjectScopeRef
}

export type SuccessorQueryMeta = {
  project_key: string
  trace_id: string
  query_id: string
  project_scope_ref: SuccessorProjectScopeRef
}

export type SuccessorProjectionMeta = {
  project_key: string
  trace_id: string
  projection_id: string
  project_scope_ref: SuccessorProjectScopeRef
  projector_id: string
  projector_version: string
  source_kind: string
  source_ref: string
  source_incarnation: string
  projection_generation: number
  offset_revision: number
  projection_revision: number
  source_digest: string
  cursor: number
}

export type SuccessorProjectionCandidateValue = {
  value_id: string
  value_ref: string
  content_digest: string
  byte_size: number
  sink: string
  payload: Record<string, unknown>
}

export type SuccessorProjectionSnapshotData = {
  projection_id: string
  projector_id: string
  projector_version: string
  source_kind: string
  source_ref: string
  source_incarnation: string
  projection_generation: number
  offset_revision: number
  projection_revision: number
  source_digest: string
  cursor: number
  offset_ref: string
  candidate_values: SuccessorProjectionCandidateValue[]
  rollback_transition?: SuccessorRollbackTransitionReceipt | null
}

export type SuccessorEnvelopeMeta =
  | SuccessorCommandMeta
  | SuccessorQueryMeta
  | SuccessorProjectionMeta
  | SuccessorUnresolvedMeta

export type SuccessorUnresolvedMeta = {
  project_key: string
  trace_id: string
  request_id: string
  resolution_state: 'UNRESOLVED'
}

export type SuccessorProjectSourceKey = {
  projector_id: string
  projector_version: string
  source_kind: string
  source_ref: string
  source_incarnation: string
}

export type SuccessorEnvelope = {
  status: SuccessorEnvelopeStatus
  data: Record<string, unknown> | null
  error: SuccessorEnvelopeError | null
  meta: SuccessorEnvelopeMeta
  control_feedback: false
}

export type SuccessorRebuildProjectionPayload = SuccessorProjectSourceKey & {
  payload_kind: 'rebuild_projection'
  projection_id: string
  mode?: 'FULL' | 'INCREMENTAL'
}

export type SuccessorInvalidateProjectionPayload = SuccessorProjectSourceKey & {
  payload_kind: 'invalidate_projection'
  projection_id: string
}

export type SuccessorRollbackProjectionPayload = SuccessorProjectSourceKey & {
  payload_kind: 'rollback_projection'
  projection_id: string
  target_generation: number
  expected_active_generation: number
  expected_offset_revision: number
}

export type SuccessorCommandPayload =
  | SuccessorRebuildProjectionPayload
  | SuccessorInvalidateProjectionPayload
  | SuccessorRollbackProjectionPayload

export type SuccessorCommandKind = SuccessorCommandPayload['payload_kind']

export type SuccessorProjectionSnapshotParams = SuccessorProjectSourceKey & {
  params_kind: 'projection_snapshot'
  projection_id: string
  page_size?: number
}

export type SuccessorQueryParams = SuccessorProjectionSnapshotParams

export type SuccessorQueryKind = SuccessorQueryParams['params_kind']

export type SuccessorCommandBinding = {
  expectedBaseToken?: string | null
  approvalLocator?: string | null
}

export type SuccessorRollbackTransitionPosition = {
  projection_generation: number
  offset_revision: number
  projection_revision: number
  source_digest: string
  cursor: number
  offset_ref: string
}

export type SuccessorRollbackTransitionReceipt = {
  contract: 'C9RollbackTransitionReceipt.v1'
  ref: string
  digest: string
  projection_id: string
  projector_id: string
  projector_version: string
  source_kind: string
  source_ref: string
  source_incarnation: string
  from: SuccessorRollbackTransitionPosition
  to: SuccessorRollbackTransitionPosition
  generation_completeness_digest: string
}

export const SUCCESSOR_ROLLBACK_RECEIPT_CONTRACT = 'C9RollbackTransitionReceipt.v1'

export type SuccessorCommandOptions = {
  commandId: string
  commandKind: SuccessorCommandKind
  projectLocator: string
  /**
   * Client-identified requesting actor for the typed submit contract.
   *
   * The wire request must never carry the actor: the server injects the
   * authoritative actor and server-resolved scope. The UI may identify the
   * requesting actor but cannot self-authorize.
   */
  actorRef: string
  payload: SuccessorCommandPayload
  traceId?: string
  expectedBaseToken?: string | null
  approvalLocator?: string | null
}

export type SuccessorQueryOptions = {
  queryId: string
  queryKind: SuccessorQueryKind
  projectLocator: string
  params: SuccessorQueryParams
  traceId?: string
}

export type SuccessorPendingCommand = {
  command_id: string
  command_kind: SuccessorCommandKind
  project_locator: string
  endpoint: string
  payload_digest: string
}

export class SuccessorRuntimeError extends Error {
  readonly code: string
  readonly details?: Record<string, unknown>

  constructor(code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'SuccessorRuntimeError'
    this.code = code
    this.details = details
  }
}

export class SuccessorDecodeError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('envelope_decode_failed', message, details)
    this.name = 'SuccessorDecodeError'
  }
}

export class SuccessorRequestError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('request_invalid', message, details)
    this.name = 'SuccessorRequestError'
  }
}

export class SuccessorConflictError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('command_body_conflict', message, details)
    this.name = 'SuccessorConflictError'
  }
}

export class SuccessorStaleError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('stale_response_suppressed', message, details)
    this.name = 'SuccessorStaleError'
  }
}

export class SuccessorScopeError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('scope_mismatch', message, details)
    this.name = 'SuccessorScopeError'
  }
}

export class SuccessorBindingError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('response_binding_mismatch', message, details)
    this.name = 'SuccessorBindingError'
  }
}

export class SuccessorTransportError extends SuccessorRuntimeError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('transport_failed', message, details)
    this.name = 'SuccessorTransportError'
  }
}

const SUCCESSOR_STORAGE_PREFIX = 'mrw.successor_runtime'
export const SUCCESSOR_PROJECT_PREFERENCE_KEY = `${SUCCESSOR_STORAGE_PREFIX}:project_preference`
export const SUCCESSOR_PENDING_COMMANDS_KEY = `${SUCCESSOR_STORAGE_PREFIX}:pending_commands`

const HEX64 = /^[0-9a-f]{64}$/
const SUCCESSOR_COMMAND_KINDS: ReadonlySet<string> = new Set([
  'rebuild_projection',
  'invalidate_projection',
  'rollback_projection',
])
const SUCCESSOR_ENVELOPE_TOP_FIELDS: ReadonlySet<string> = new Set([
  'status',
  'data',
  'error',
  'meta',
  'control_feedback',
])
const SUCCESSOR_ERROR_FIELDS: ReadonlySet<string> = new Set(['code', 'message', 'details'])
const SUCCESSOR_SCOPE_REF_FIELDS: ReadonlySet<string> = new Set([
  'project_key',
  'resolved_schema',
  'project_registry_revision',
  'incarnation',
  'scope_digest',
])
const SUCCESSOR_COMMAND_META_FIELDS: ReadonlySet<string> = new Set([
  'project_key',
  'trace_id',
  'command_id',
  'project_scope_ref',
])
const SUCCESSOR_QUERY_META_FIELDS: ReadonlySet<string> = new Set([
  'project_key',
  'trace_id',
  'query_id',
  'project_scope_ref',
])
const SUCCESSOR_PROJECTION_META_FIELDS: ReadonlySet<string> = new Set([
  'project_key',
  'trace_id',
  'projection_id',
  'project_scope_ref',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
  'projection_generation',
  'offset_revision',
  'projection_revision',
  'source_digest',
  'cursor',
])
const SUCCESSOR_UNRESOLVED_META_FIELDS: ReadonlySet<string> = new Set([
  'project_key',
  'trace_id',
  'request_id',
  'resolution_state',
])
const SUCCESSOR_CONTROL_DATA_FIELDS: ReadonlySet<string> = new Set([
  'actor',
  'authority',
  'execute',
  'control',
  'control_feedback',
  'completion',
  'approval',
  'scope',
  'schema',
])

function assertKnownKeys(record: Record<string, unknown>, allowed: ReadonlySet<string>, name: string): void {
  const unknown = Object.keys(record).filter((key) => !allowed.has(key))
  if (unknown.length > 0) {
    throw new SuccessorDecodeError(`${name} carries unknown fields: ${unknown.join(', ')}`)
  }
}

function getStorage(): Storage {
  const windowStorage = typeof window !== 'undefined' && window.localStorage ? window.localStorage : null
  const globalStorage = (globalThis as { localStorage?: Storage }).localStorage
  const storage = windowStorage || globalStorage || null
  if (!storage) {
    throw new SuccessorRuntimeError('localStorage_unavailable', 'Successor runtime requires localStorage')
  }
  return storage
}

export function getSuccessorProjectPreference(): string | null {
  const raw = getStorage().getItem(SUCCESSOR_PROJECT_PREFERENCE_KEY)
  return raw ? String(raw) : null
}

export function setSuccessorProjectPreference(projectLocator: string): void {
  const next = String(projectLocator || '').trim()
  if (!next) {
    throw new SuccessorRequestError('Project preference must not be empty')
  }
  getStorage().setItem(SUCCESSOR_PROJECT_PREFERENCE_KEY, next)
}

export function clearSuccessorProjectPreference(): void {
  getStorage().removeItem(SUCCESSOR_PROJECT_PREFERENCE_KEY)
}

export function readSuccessorPendingCommands(): Record<string, SuccessorPendingCommand> {
  const raw = getStorage().getItem(SUCCESSOR_PENDING_COMMANDS_KEY)
  if (!raw) return {}

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new SuccessorRuntimeError('pending_store_malformed', 'Successor pending command store is malformed')
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new SuccessorRuntimeError('pending_store_malformed', 'Successor pending command store is malformed')
  }

  const result: Record<string, SuccessorPendingCommand> = {}
  for (const [key, value] of Object.entries(parsed)) {
    const record = value as Partial<SuccessorPendingCommand>
    const knownFields = ['command_id', 'command_kind', 'project_locator', 'endpoint', 'payload_digest']
    const unknownFields = Object.keys(value as object).filter((name) => !knownFields.includes(name))
    if (
      unknownFields.length > 0 ||
      typeof record?.command_id !== 'string' ||
      typeof record.command_kind !== 'string' ||
      !SUCCESSOR_COMMAND_KINDS.has(record.command_kind) ||
      typeof record.project_locator !== 'string' ||
      typeof record.endpoint !== 'string' ||
      record.endpoint !== SUCCESSOR_V2_COMMAND_URL ||
      typeof record.payload_digest !== 'string' ||
      !HEX64.test(record.payload_digest) ||
      key !== pendingCommandKey(record.project_locator, record.command_id)
    ) {
      throw new SuccessorRuntimeError('pending_record_malformed', 'Successor pending command record is malformed')
    }
    result[key] = {
      command_id: record.command_id,
      command_kind: record.command_kind as SuccessorCommandKind,
      project_locator: record.project_locator,
      endpoint: record.endpoint,
      payload_digest: record.payload_digest,
    }
  }
  return result
}

function writeSuccessorPendingCommands(commands: Record<string, SuccessorPendingCommand>): void {
  getStorage().setItem(SUCCESSOR_PENDING_COMMANDS_KEY, JSON.stringify(commands))
}

function upsertSuccessorPendingCommand(record: SuccessorPendingCommand): void {
  const commands = readSuccessorPendingCommands()
  const key = pendingCommandKey(record.project_locator, record.command_id)
  if (!commands[key]) {
    commands[key] = record
    writeSuccessorPendingCommands(commands)
  }
}

function removeSuccessorPendingCommand(projectLocator: string, commandId: string): void {
  const commands = readSuccessorPendingCommands()
  const key = pendingCommandKey(projectLocator, commandId)
  if (!(key in commands)) return
  delete commands[key]
  writeSuccessorPendingCommands(commands)
}

function canonicalJson(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new SuccessorRequestError('Command payload must contain only finite numbers')
    }
    return Object.is(value, -0) ? '0' : String(value)
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, child]) => `${JSON.stringify(key)}:${canonicalJson(child)}`)
    return `{${entries.join(',')}}`
  }
  throw new SuccessorRequestError('Command payload must be JSON-serializable')
}

const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

function rotr(value: number, shift: number): number {
  return (value >>> shift) | (value << (32 - shift))
}

export function sha256Hex(input: string): string {
  const message = new TextEncoder().encode(input)
  const bitLength = message.length * 8
  const paddedLength = (((message.length + 8) >> 6) + 1) << 6
  const padded = new Uint8Array(paddedLength)
  padded.set(message)
  padded[message.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000))
  view.setUint32(paddedLength - 4, bitLength >>> 0)

  let h0 = 0x6a09e667
  let h1 = 0xbb67ae85
  let h2 = 0x3c6ef372
  let h3 = 0xa54ff53a
  let h4 = 0x510e527f
  let h5 = 0x9b05688c
  let h6 = 0x1f83d9ab
  let h7 = 0x5be0cd19

  for (let offset = 0; offset < paddedLength; offset += 64) {
    const words = new Uint32Array(64)
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4)
    }
    for (let index = 16; index < 64; index += 1) {
      const sigma0 = rotr(words[index - 15], 7) ^ rotr(words[index - 15], 18) ^ (words[index - 15] >>> 3)
      const sigma1 = rotr(words[index - 2], 17) ^ rotr(words[index - 2], 19) ^ (words[index - 2] >>> 10)
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0
    }

    let a = h0
    let b = h1
    let c = h2
    let d = h3
    let e = h4
    let f = h5
    let g = h6
    let h = h7

    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
      const choose = (e & f) ^ (~e & g)
      const temp1 = (h + sum1 + choose + SHA256_K[index] + words[index]) >>> 0
      const sum0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
      const majority = (a & b) ^ (a & c) ^ (b & c)
      const temp2 = (sum0 + majority) >>> 0
      h = g
      g = f
      f = e
      e = (d + temp1) >>> 0
      d = c
      c = b
      b = a
      a = (temp1 + temp2) >>> 0
    }

    h0 = (h0 + a) >>> 0
    h1 = (h1 + b) >>> 0
    h2 = (h2 + c) >>> 0
    h3 = (h3 + d) >>> 0
    h4 = (h4 + e) >>> 0
    h5 = (h5 + f) >>> 0
    h6 = (h6 + g) >>> 0
    h7 = (h7 + h) >>> 0
  }

  return [h0, h1, h2, h3, h4, h5, h6, h7]
    .map((value) => value.toString(16).padStart(8, '0'))
    .join('')
}

export function computeSuccessorCommandFingerprint(
  endpoint: string,
  projectLocator: string,
  commandId: string,
  commandKind: SuccessorCommandKind,
  payload: SuccessorCommandPayload,
  binding?: SuccessorCommandBinding,
): string {
  return sha256Hex(
    canonicalJson({
      contract: 'C9FrontendCommandIdentity.v1',
      endpoint,
      project_locator: projectLocator,
      command_id: commandId,
      command_kind: commandKind,
      payload,
      expected_base_token: binding?.expectedBaseToken ?? null,
      approval_locator: binding?.approvalLocator ?? null,
    }),
  )
}

function assertRequestNonEmpty(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new SuccessorRequestError(`${name} must be a non-empty string`)
  }
  return value
}

function assertSourceKeyFields(value: SuccessorProjectSourceKey, name: string): void {
  for (const field of [
    'projector_id',
    'projector_version',
    'source_kind',
    'source_ref',
    'source_incarnation',
  ] as const) {
    assertRequestNonEmpty(value[field], `${name}.${field}`)
  }
}

function assertRequestNonNegativeInteger(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new SuccessorRequestError(`${name} must be a non-negative integer`)
  }
  return value
}

const SUCCESSOR_REBUILD_PAYLOAD_FIELDS: ReadonlySet<string> = new Set([
  'payload_kind',
  'projection_id',
  'mode',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
])
const SUCCESSOR_INVALIDATE_PAYLOAD_FIELDS: ReadonlySet<string> = new Set([
  'payload_kind',
  'projection_id',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
])
const SUCCESSOR_ROLLBACK_PAYLOAD_FIELDS: ReadonlySet<string> = new Set([
  'payload_kind',
  'projection_id',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
  'target_generation',
  'expected_active_generation',
  'expected_offset_revision',
])
const SUCCESSOR_SNAPSHOT_PARAMS_FIELDS: ReadonlySet<string> = new Set([
  'params_kind',
  'projection_id',
  'page_size',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
])
const SUCCESSOR_QUERY_KINDS: ReadonlySet<string> = new Set([
  'projection_snapshot',
])

function pendingCommandKey(projectLocator: string, commandId: string): string {
  return JSON.stringify([projectLocator, commandId])
}

function assertNoSmuggledOptions(options: object, kind: string): void {
  const record = options as Record<string, unknown>
  if (record.url !== undefined) {
    throw new SuccessorRequestError(`${kind} custom url is not allowed; endpoint is fixed by the module`)
  }
  if (record.headers !== undefined) {
    throw new SuccessorRequestError(`${kind} custom headers are not allowed`)
  }
}

function assertDecodedNonEmpty(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new SuccessorDecodeError(`${name} must be a non-empty string`)
  }
  return value
}

function assertDecodedNonNegativeInteger(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new SuccessorDecodeError(`${name} must be a non-negative integer`)
  }
  return value
}

function createTraceId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch {
    // fall through to the deterministic local trace id
  }
  return `trace-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function resolveUrl(rawUrl: string): string {
  try {
    const base =
      typeof window !== 'undefined' && window.location?.href ? window.location.href : 'http://localhost/'
    return new URL(rawUrl, base).toString()
  } catch {
    throw new SuccessorTransportError(`Invalid successor endpoint URL: ${rawUrl}`)
  }
}

async function requestJson(url: string, init: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    throw new SuccessorTransportError(`Successor fetch failed for ${url}`, {
      cause: error instanceof Error ? error.message : String(error),
    })
  }

  let text: string
  try {
    text = await response.text()
  } catch (error) {
    throw new SuccessorTransportError(`Successor response unreadable for ${url}`, {
      status: response.status,
      cause: error instanceof Error ? error.message : String(error),
    })
  }

  if (!response.ok) {
    throw new SuccessorTransportError(`Successor endpoint returned HTTP ${response.status}`, {
      status: response.status,
    })
  }

  let parsed: unknown
  try {
    parsed = text.trim() ? JSON.parse(text) : null
  } catch {
    throw new SuccessorDecodeError(`Successor response is not valid JSON for ${url}`)
  }
  return parsed
}

function decodeProjectScopeRef(raw: unknown): SuccessorProjectScopeRef {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new SuccessorDecodeError('Envelope meta requires project_scope_ref')
  }
  const scope = raw as Record<string, unknown>
  assertKnownKeys(scope, SUCCESSOR_SCOPE_REF_FIELDS, 'project_scope_ref')
  return {
    project_key: assertDecodedNonEmpty(scope.project_key, 'project_scope_ref.project_key'),
    resolved_schema: assertDecodedNonEmpty(scope.resolved_schema, 'project_scope_ref.resolved_schema'),
    project_registry_revision: assertDecodedNonNegativeInteger(
      scope.project_registry_revision,
      'project_scope_ref.project_registry_revision',
    ),
    incarnation: assertDecodedNonEmpty(scope.incarnation, 'project_scope_ref.incarnation'),
    scope_digest: assertHex64(scope.scope_digest, 'project_scope_ref.scope_digest'),
  }
}

function assertHex64(value: unknown, name: string): string {
  if (typeof value !== 'string' || !HEX64.test(value)) {
    throw new SuccessorDecodeError(`${name} must be canonical SHA-256 hex`)
  }
  return value
}

function decodeSuccessorMeta(raw: unknown): SuccessorEnvelopeMeta {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new SuccessorDecodeError('Envelope must carry a meta object')
  }
  const meta = raw as Record<string, unknown>
  const project_key = assertDecodedNonEmpty(meta.project_key, 'meta.project_key')
  const trace_id = assertDecodedNonEmpty(meta.trace_id, 'meta.trace_id')
  if (meta.resolution_state !== undefined && meta.resolution_state !== null) {
    assertKnownKeys(meta, SUCCESSOR_UNRESOLVED_META_FIELDS, 'meta')
    if (meta.resolution_state !== 'UNRESOLVED') {
      throw new SuccessorDecodeError('Envelope meta resolution_state must be UNRESOLVED')
    }
    const request_id = assertDecodedNonEmpty(meta.request_id, 'meta.request_id')
    return {
      project_key,
      trace_id,
      request_id,
      resolution_state: 'UNRESOLVED',
    }
  }
  const project_scope_ref = decodeProjectScopeRef(meta.project_scope_ref)

  const presentDiscriminators = ['command_id', 'query_id', 'projection_id'].filter(
    (name) => meta[name] !== undefined && meta[name] !== null,
  )
  if (presentDiscriminators.length !== 1) {
    throw new SuccessorDecodeError(
      'Envelope meta must carry exactly one of command_id, query_id or projection_id',
    )
  }

  if (meta.command_id !== undefined && meta.command_id !== null) {
    assertKnownKeys(meta, SUCCESSOR_COMMAND_META_FIELDS, 'meta')
    return {
      project_key,
      trace_id,
      command_id: assertDecodedNonEmpty(meta.command_id, 'meta.command_id'),
      project_scope_ref,
    }
  }
  if (meta.query_id !== undefined && meta.query_id !== null) {
    assertKnownKeys(meta, SUCCESSOR_QUERY_META_FIELDS, 'meta')
    return {
      project_key,
      trace_id,
      query_id: assertDecodedNonEmpty(meta.query_id, 'meta.query_id'),
      project_scope_ref,
    }
  }
  assertKnownKeys(meta, SUCCESSOR_PROJECTION_META_FIELDS, 'meta')
  return {
    project_key,
    trace_id,
    projection_id: assertDecodedNonEmpty(meta.projection_id, 'meta.projection_id'),
    project_scope_ref,
    projector_id: assertDecodedNonEmpty(meta.projector_id, 'meta.projector_id'),
    projector_version: assertDecodedNonEmpty(meta.projector_version, 'meta.projector_version'),
    source_kind: assertDecodedNonEmpty(meta.source_kind, 'meta.source_kind'),
    source_ref: assertDecodedNonEmpty(meta.source_ref, 'meta.source_ref'),
    source_incarnation: assertDecodedNonEmpty(meta.source_incarnation, 'meta.source_incarnation'),
    projection_generation: assertDecodedNonNegativeInteger(
      meta.projection_generation,
      'meta.projection_generation',
    ),
    offset_revision: assertDecodedNonNegativeInteger(meta.offset_revision, 'meta.offset_revision'),
    projection_revision: assertDecodedNonNegativeInteger(
      meta.projection_revision,
      'meta.projection_revision',
    ),
    source_digest: assertHex64(meta.source_digest, 'meta.source_digest'),
    cursor: assertDecodedNonNegativeInteger(meta.cursor, 'meta.cursor'),
  }
}

export function decodeSuccessorEnvelope(raw: unknown): SuccessorEnvelope {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new SuccessorDecodeError('Successor envelope must be a JSON object')
  }
  const record = raw as Record<string, unknown>
  assertKnownKeys(record, SUCCESSOR_ENVELOPE_TOP_FIELDS, 'envelope')
  for (const field of ['status', 'data', 'error', 'meta', 'control_feedback']) {
    if (!Object.prototype.hasOwnProperty.call(record, field)) {
      throw new SuccessorDecodeError(`Successor envelope must carry ${field}`)
    }
  }
  const status = record.status
  if (typeof status !== 'string' || !SUCCESSOR_ENVELOPE_STATUSES.includes(status as SuccessorEnvelopeStatus)) {
    throw new SuccessorDecodeError('Successor envelope status must be one of the six v2 variants')
  }

  const data = record.data
  const error = record.error
  const dataRequired = status === 'ok' || status === 'waiting'
  const errorRequired =
    status === 'blocked' || status === 'unavailable' || status === 'conflict' || status === 'error'

  if (data !== null && data !== undefined && (typeof data !== 'object' || Array.isArray(data))) {
    throw new SuccessorDecodeError('Successor envelope data must be a JSON object or null')
  }
  if (data !== null && data !== undefined && typeof data === 'object') {
    const controlKeys = Object.keys(data).filter((key) => SUCCESSOR_CONTROL_DATA_FIELDS.has(key))
    if (controlKeys.length > 0) {
      throw new SuccessorDecodeError(`Successor envelope data carries control fields: ${controlKeys.join(', ')}`)
    }
  }
  if (error !== null && error !== undefined) {
    if (typeof error !== 'object' || Array.isArray(error)) {
      throw new SuccessorDecodeError('Successor envelope error must be an object or null')
    }
    const errorRecord = error as Record<string, unknown>
    assertKnownKeys(errorRecord, SUCCESSOR_ERROR_FIELDS, 'error')
    if (
      typeof errorRecord.code !== 'string' ||
      errorRecord.code.trim() === '' ||
      typeof errorRecord.message !== 'string' ||
      errorRecord.message.trim() === ''
    ) {
      throw new SuccessorDecodeError('Successor envelope error requires non-empty code and message')
    }
    if (
      typeof errorRecord.details !== 'object' ||
      errorRecord.details === null ||
      Array.isArray(errorRecord.details)
    ) {
      throw new SuccessorDecodeError('Successor envelope error requires a details object')
    }
  }

  if (dataRequired && data == null) {
    throw new SuccessorDecodeError('ok/waiting envelope requires data')
  }
  if (dataRequired && error != null) {
    throw new SuccessorDecodeError('ok/waiting envelope must not carry error details')
  }
  if (errorRequired && error == null) {
    throw new SuccessorDecodeError('error-family envelope requires typed error details')
  }
  if (errorRequired && data != null) {
    throw new SuccessorDecodeError('error-family envelope must not carry data')
  }

  if (record.control_feedback !== false) {
    throw new SuccessorDecodeError('Successor envelope control_feedback must be false')
  }

  const decodedMeta = decodeSuccessorMeta(record.meta)
  if ('resolution_state' in decodedMeta && status !== 'error') {
    throw new SuccessorDecodeError('UNRESOLVED transport meta requires an error status')
  }

  return {
    status: status as SuccessorEnvelopeStatus,
    data: data == null ? null : (data as Record<string, unknown>),
    error: error == null ? null : (error as SuccessorEnvelopeError),
    meta: decodedMeta,
    control_feedback: false,
  }
}

const successorInFlightCommands = new Map<
  string,
  { traceId: string; promise: Promise<SuccessorEnvelope> }
>()
const successorProjectionClocks = new Map<
  string,
  {
    scope_digest: string
    projection_generation: number
    offset_revision: number
    offset_ref: string
    projection_revision: number
    source_digest: string
    cursor: number
  }
>()

export function resetSuccessorProjectionClock(): void {
  successorProjectionClocks.clear()
}

const SUCCESSOR_PROJECTION_DATA_FIELDS: ReadonlySet<string> = new Set([
  'projection_id',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
  'projection_generation',
  'offset_revision',
  'projection_revision',
  'source_digest',
  'cursor',
  'offset_ref',
  'candidate_values',
  'rollback_transition',
])
const SUCCESSOR_CANDIDATE_VALUE_FIELDS: ReadonlySet<string> = new Set([
  'value_id',
  'value_ref',
  'content_digest',
  'byte_size',
  'sink',
  'payload',
])
const SUCCESSOR_ROLLBACK_RECEIPT_FIELDS: ReadonlySet<string> = new Set([
  'contract',
  'ref',
  'digest',
  'projection_id',
  'projector_id',
  'projector_version',
  'source_kind',
  'source_ref',
  'source_incarnation',
  'from',
  'to',
  'generation_completeness_digest',
])
const SUCCESSOR_ROLLBACK_POSITION_FIELDS: ReadonlySet<string> = new Set([
  'projection_generation',
  'offset_revision',
  'projection_revision',
  'source_digest',
  'cursor',
  'offset_ref',
])

function decodeCandidateValue(raw: unknown): SuccessorProjectionCandidateValue {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new SuccessorDecodeError('candidate value must be a JSON object')
  }
  const record = raw as Record<string, unknown>
  assertKnownKeys(record, SUCCESSOR_CANDIDATE_VALUE_FIELDS, 'candidate value')
  const payload = record.payload
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new SuccessorDecodeError('candidate value payload must be a JSON object')
  }
  const controlKeys = Object.keys(payload).filter((key) => SUCCESSOR_CONTROL_DATA_FIELDS.has(key))
  if (controlKeys.length > 0) {
    throw new SuccessorDecodeError(`candidate value payload carries control fields: ${controlKeys.join(', ')}`)
  }
  return {
    value_id: assertDecodedNonEmpty(record.value_id, 'candidate value.value_id'),
    value_ref: assertDecodedNonEmpty(record.value_ref, 'candidate value.value_ref'),
    content_digest: assertHex64(record.content_digest, 'candidate value.content_digest'),
    byte_size: assertDecodedNonNegativeInteger(record.byte_size, 'candidate value.byte_size'),
    sink: assertDecodedNonEmpty(record.sink, 'candidate value.sink'),
    payload: payload as Record<string, unknown>,
  }
}

export function assertSuccessorProjectionSnapshotData(
  meta: SuccessorProjectionMeta,
  data: Record<string, unknown> | null,
): SuccessorProjectionSnapshotData {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new SuccessorDecodeError('Projection snapshot data must be a JSON object')
  }
  assertKnownKeys(data, SUCCESSOR_PROJECTION_DATA_FIELDS, 'data')
  const fields = [
    'projection_id',
    'projector_id',
    'projector_version',
    'source_kind',
    'source_ref',
    'source_incarnation',
    'projection_generation',
    'offset_revision',
    'projection_revision',
    'source_digest',
    'cursor',
  ] as const
  for (const field of fields) {
    if (data[field] !== meta[field]) {
      throw new SuccessorDecodeError(`Projection snapshot data ${field} does not match meta`, {
        field,
        expected: meta[field],
        actual: data[field],
      })
    }
  }
  const offset_ref = assertDecodedNonEmpty(data.offset_ref, 'data.offset_ref')
  if (!Array.isArray(data.candidate_values)) {
    throw new SuccessorDecodeError('Projection snapshot data candidate_values must be an array')
  }
  const candidate_values = data.candidate_values.map(decodeCandidateValue)
  let rollback_transition: SuccessorRollbackTransitionReceipt | null = null
  if (data.rollback_transition !== undefined && data.rollback_transition !== null) {
    rollback_transition = decodeSuccessorRollbackTransitionReceipt(data.rollback_transition)
    const sourceKeyFields = [
      'projection_id',
      'projector_id',
      'projector_version',
      'source_kind',
      'source_ref',
      'source_incarnation',
    ] as const
    for (const field of sourceKeyFields) {
      if (rollback_transition[field] !== data[field]) {
        throw new SuccessorDecodeError(`rollback receipt ${field} does not match snapshot data`, {
          field,
          expected: data[field],
          actual: rollback_transition[field],
        })
      }
    }
  }
  return {
    ...(data as unknown as SuccessorProjectionSnapshotData),
    offset_ref,
    candidate_values,
    rollback_transition,
  }
}

export function decodeSuccessorTypedRejection(
  envelope: SuccessorEnvelope,
): SuccessorTypedRejectionReason | null {
  if (envelope.status !== 'conflict' && envelope.status !== 'error') {
    return null
  }
  if (!envelope.error) {
    return null
  }
  if (!SUCCESSOR_TYPED_REJECTION_CODES.includes(envelope.error.code as SuccessorTypedRejectionCode)) {
    return null
  }
  return {
    code: envelope.error.code as SuccessorTypedRejectionCode,
    message: envelope.error.message,
    details: envelope.error.details ?? {},
    meta: envelope.meta,
  }
}

export type SuccessorObservationInput = {
  phase: 'not_started' | 'in_flight' | 'settled'
  envelope?: SuccessorEnvelope | null
  clientError?: SuccessorRuntimeError | null
}

export function deriveSuccessorUiObservation(
  input: SuccessorObservationInput,
): SuccessorUiObservationState {
  if (input.phase !== 'not_started' && input.phase !== 'in_flight' && input.phase !== 'settled') {
    throw new SuccessorDecodeError(`Unknown successor observation phase: ${String(input.phase)}`)
  }
  if (input.phase === 'not_started' && !input.clientError) {
    return 'NOT_STARTED'
  }
  if (input.phase === 'in_flight') {
    return 'IN_FLIGHT'
  }
  if (input.clientError) {
    return 'FAILED'
  }
  if (!input.envelope) {
    throw new SuccessorDecodeError('Settled observation requires an envelope or a client error')
  }
  if (input.envelope.status === 'waiting') {
    return 'IN_FLIGHT'
  }
  if (input.envelope.status === 'ok') {
    return 'SUCCEEDED'
  }
  if (decodeSuccessorTypedRejection(input.envelope)) {
    return 'REJECTED_TYPED'
  }
  return 'OUTCOME_UNKNOWN'
}

export function resolveSuccessorServerResolvedScope(
  projectLocator: string,
  envelope: SuccessorEnvelope,
): SuccessorProjectScopeRef {
  if ('resolution_state' in envelope.meta) {
    throw new SuccessorScopeError(
      `Server scope is unresolved for ${projectLocator}`,
      { projectLocator, request_id: envelope.meta.request_id },
    )
  }
  const scope = envelope.meta.project_scope_ref
  if (envelope.meta.project_key !== projectLocator || scope.project_key !== projectLocator) {
    throw new SuccessorScopeError(
      `Server scope does not exact-bind ${projectLocator}`,
      {
        projectLocator,
        meta_project_key: envelope.meta.project_key,
        scope_project_key: scope.project_key,
      },
    )
  }
  return scope
}

export type SuccessorServerResolvedProjection = {
  scope: SuccessorProjectScopeRef
  envelope: SuccessorEnvelope
  snapshot: SuccessorProjectionSnapshotData
}

export function projectSuccessorServerScope(
  projectLocator: string,
  envelope: SuccessorEnvelope,
): SuccessorServerResolvedProjection {
  const scope = resolveSuccessorServerResolvedScope(projectLocator, envelope)
  if ('resolution_state' in envelope.meta) {
    throw new SuccessorDecodeError('Projection observation requires a resolved server scope')
  }
  if (!('projection_id' in envelope.meta)) {
    throw new SuccessorDecodeError('Projection observation requires projection meta')
  }
  const snapshot = assertSuccessorProjectionSnapshotData(envelope.meta, envelope.data)
  return { scope, envelope, snapshot }
}

function decodeRollbackPosition(raw: unknown): SuccessorRollbackTransitionPosition {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new SuccessorDecodeError('rollback transition position must be a JSON object')
  }
  const record = raw as Record<string, unknown>
  assertKnownKeys(record, SUCCESSOR_ROLLBACK_POSITION_FIELDS, 'rollback position')
  return {
    projection_generation: assertDecodedNonNegativeInteger(
      record.projection_generation,
      'rollback position.projection_generation',
    ),
    offset_revision: assertDecodedNonNegativeInteger(record.offset_revision, 'rollback position.offset_revision'),
    projection_revision: assertDecodedNonNegativeInteger(
      record.projection_revision,
      'rollback position.projection_revision',
    ),
    source_digest: assertHex64(record.source_digest, 'rollback position.source_digest'),
    cursor: assertDecodedNonNegativeInteger(record.cursor, 'rollback position.cursor'),
    offset_ref: assertDecodedNonEmpty(record.offset_ref, 'rollback position.offset_ref'),
  }
}

export function decodeSuccessorRollbackTransitionReceipt(
  raw: unknown,
): SuccessorRollbackTransitionReceipt {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new SuccessorDecodeError('rollback transition receipt must be a JSON object')
  }
  const record = raw as Record<string, unknown>
  assertKnownKeys(record, SUCCESSOR_ROLLBACK_RECEIPT_FIELDS, 'rollback receipt')
  if (record.contract !== SUCCESSOR_ROLLBACK_RECEIPT_CONTRACT) {
    throw new SuccessorDecodeError(
      `rollback receipt contract must be ${SUCCESSOR_ROLLBACK_RECEIPT_CONTRACT}`,
    )
  }
  return {
    contract: SUCCESSOR_ROLLBACK_RECEIPT_CONTRACT,
    ref: assertDecodedNonEmpty(record.ref, 'rollback receipt.ref'),
    digest: assertHex64(record.digest, 'rollback receipt.digest'),
    projection_id: assertDecodedNonEmpty(record.projection_id, 'rollback receipt.projection_id'),
    projector_id: assertDecodedNonEmpty(record.projector_id, 'rollback receipt.projector_id'),
    projector_version: assertDecodedNonEmpty(
      record.projector_version,
      'rollback receipt.projector_version',
    ),
    source_kind: assertDecodedNonEmpty(record.source_kind, 'rollback receipt.source_kind'),
    source_ref: assertDecodedNonEmpty(record.source_ref, 'rollback receipt.source_ref'),
    source_incarnation: assertDecodedNonEmpty(
      record.source_incarnation,
      'rollback receipt.source_incarnation',
    ),
    from: decodeRollbackPosition(record.from),
    to: decodeRollbackPosition(record.to),
    generation_completeness_digest: assertHex64(
      record.generation_completeness_digest,
      'rollback receipt.generation_completeness_digest',
    ),
  }
}

export function computeSuccessorRollbackReceiptDigest(
  receipt: SuccessorRollbackTransitionReceipt,
): string {
  return sha256Hex(
    canonicalJson({
      contract: receipt.contract,
      ref: receipt.ref,
      projection_id: receipt.projection_id,
      projector_id: receipt.projector_id,
      projector_version: receipt.projector_version,
      source_kind: receipt.source_kind,
      source_ref: receipt.source_ref,
      source_incarnation: receipt.source_incarnation,
      from: receipt.from,
      to: receipt.to,
      generation_completeness_digest: receipt.generation_completeness_digest,
    }),
  )
}

function positionsEqual(
  left: SuccessorRollbackTransitionPosition,
  right: SuccessorRollbackTransitionPosition,
): boolean {
  return (
    left.projection_generation === right.projection_generation &&
    left.offset_revision === right.offset_revision &&
    left.projection_revision === right.projection_revision &&
    left.source_digest === right.source_digest &&
    left.cursor === right.cursor &&
    left.offset_ref === right.offset_ref
  )
}

export function applySuccessorRollbackTransition(
  projectLocator: string,
  envelope: SuccessorEnvelope,
  receipt: SuccessorRollbackTransitionReceipt,
): SuccessorEnvelope {
  if (!('projection_id' in envelope.meta)) {
    throw new SuccessorDecodeError('Rollback transition requires projection meta')
  }
  const meta = envelope.meta
  const key = JSON.stringify([
    projectLocator,
    meta.projection_id,
    meta.projector_id,
    meta.projector_version,
    meta.source_kind,
    meta.source_ref,
    meta.source_incarnation,
  ])
  const prior = successorProjectionClocks.get(key)
  if (!prior) {
    throw new SuccessorStaleError('Sanctioned rollback requires a previous projection clock', {
      projectLocator,
      projection_id: meta.projection_id,
    })
  }
  if (meta.project_scope_ref.scope_digest !== prior.scope_digest) {
    throw new SuccessorScopeError(
      `Rollback scope digest changed for ${meta.projection_id}`,
      { projectLocator, projection_id: meta.projection_id },
    )
  }
  const sourceKeyFields = [
    'projection_id',
    'projector_id',
    'projector_version',
    'source_kind',
    'source_ref',
    'source_incarnation',
  ] as const
  for (const field of sourceKeyFields) {
    if (receipt[field] !== meta[field]) {
      throw new SuccessorStaleError(`Rollback receipt ${field} does not match incoming meta`, {
        field,
        expected: meta[field],
        actual: receipt[field],
      })
    }
  }
  const recomputed = computeSuccessorRollbackReceiptDigest(receipt)
  if (recomputed !== receipt.digest) {
    throw new SuccessorStaleError('Rollback receipt canonical digest mismatch', {
      ref: receipt.ref,
      expected: receipt.digest,
      actual: recomputed,
    })
  }
  const incoming: SuccessorRollbackTransitionPosition = {
    projection_generation: meta.projection_generation,
    offset_revision: meta.offset_revision,
    projection_revision: meta.projection_revision,
    source_digest: meta.source_digest,
    cursor: meta.cursor,
    offset_ref: receipt.to.offset_ref,
  }
  const priorPosition: SuccessorRollbackTransitionPosition = {
    projection_generation: prior.projection_generation,
    offset_revision: prior.offset_revision,
    projection_revision: prior.projection_revision,
    source_digest: prior.source_digest,
    cursor: prior.cursor,
    offset_ref: prior.offset_ref,
  }
  if (
    envelope.data !== null &&
    typeof envelope.data === 'object' &&
    'offset_ref' in envelope.data &&
    envelope.data.offset_ref !== receipt.to.offset_ref
  ) {
    throw new SuccessorStaleError('Rollback incoming data offset_ref conflicts with receipt to.offset_ref', {
      ref: receipt.ref,
      receiptOffsetRef: receipt.to.offset_ref,
      dataOffsetRef: envelope.data.offset_ref,
    })
  }
  const fromMatches = positionsEqual(receipt.from, priorPosition)
  const toMatches = positionsEqual(receipt.to, incoming)
  const alreadyApplied = positionsEqual(incoming, priorPosition) && positionsEqual(receipt.to, priorPosition)
  if (!alreadyApplied) {
    if (!fromMatches || !toMatches) {
      throw new SuccessorStaleError('Rollback receipt from/to do not match clock and incoming position', {
        ref: receipt.ref,
      })
    }
    if (receipt.to.offset_revision !== receipt.from.offset_revision + 1) {
      throw new SuccessorStaleError(
        'Rollback requires to.offset_revision = from.offset_revision + 1',
        {
          ref: receipt.ref,
          from_offset_revision: receipt.from.offset_revision,
          to_offset_revision: receipt.to.offset_revision,
        },
      )
    }
  }
  successorProjectionClocks.set(key, {
    scope_digest: prior.scope_digest,
    projection_generation: receipt.to.projection_generation,
    offset_revision: receipt.to.offset_revision,
    offset_ref: receipt.to.offset_ref,
    projection_revision: receipt.to.projection_revision,
    source_digest: receipt.to.source_digest,
    cursor: receipt.to.cursor,
  })
  return envelope
}

export function assertSuccessorProjectionFresh(
  projectLocator: string,
  envelope: SuccessorEnvelope,
  offsetRef: string,
): SuccessorEnvelope {
  if (!('projection_id' in envelope.meta)) {
    throw new SuccessorDecodeError('Query response requires projection meta')
  }
  const meta = envelope.meta
  const key = JSON.stringify([
    projectLocator,
    meta.projection_id,
    meta.projector_id,
    meta.projector_version,
    meta.source_kind,
    meta.source_ref,
    meta.source_incarnation,
  ])
  const incoming = {
    scope_digest: meta.project_scope_ref.scope_digest,
    projection_generation: meta.projection_generation,
    offset_revision: meta.offset_revision,
    offset_ref: offsetRef,
    projection_revision: meta.projection_revision,
    source_digest: meta.source_digest,
    cursor: meta.cursor,
  }
  const prior = successorProjectionClocks.get(key)
  if (prior) {
    if (incoming.scope_digest !== prior.scope_digest) {
      throw new SuccessorScopeError(
        `Projection scope digest changed for ${meta.projection_id}`,
        { projectLocator, projection_id: meta.projection_id },
      )
    }
    const identical =
      incoming.projection_generation === prior.projection_generation &&
      incoming.offset_revision === prior.offset_revision &&
      incoming.offset_ref === prior.offset_ref &&
      incoming.projection_revision === prior.projection_revision &&
      incoming.source_digest === prior.source_digest &&
      incoming.cursor === prior.cursor
    const positionChanged =
      incoming.projection_generation !== prior.projection_generation ||
      incoming.projection_revision !== prior.projection_revision ||
      incoming.source_digest !== prior.source_digest ||
      incoming.cursor !== prior.cursor ||
      incoming.offset_ref !== prior.offset_ref
    const stale =
      incoming.cursor < prior.cursor ||
      (incoming.cursor === prior.cursor && incoming.source_digest !== prior.source_digest) ||
      incoming.projection_generation < prior.projection_generation ||
      incoming.projection_revision < prior.projection_revision ||
      incoming.offset_revision < prior.offset_revision ||
      (positionChanged && !identical && incoming.offset_revision <= prior.offset_revision)
    if (stale) {
      throw new SuccessorStaleError(
        `Rejected stale successor projection ${meta.projection_id}`,
        {
          projectLocator,
          projection_id: meta.projection_id,
          projection_revision: incoming.projection_revision,
          source_digest: incoming.source_digest,
          cursor: incoming.cursor,
        },
      )
    }
  }
  successorProjectionClocks.set(key, incoming)
  return envelope
}

function commandPayloadAllowlist(payload: SuccessorCommandPayload): ReadonlySet<string> {
  if (payload.payload_kind === 'rebuild_projection') return SUCCESSOR_REBUILD_PAYLOAD_FIELDS
  if (payload.payload_kind === 'invalidate_projection') return SUCCESSOR_INVALIDATE_PAYLOAD_FIELDS
  return SUCCESSOR_ROLLBACK_PAYLOAD_FIELDS
}

function assertPayloadAllowlist(payload: SuccessorCommandPayload): void {
  const allowed = commandPayloadAllowlist(payload)
  const unknown = Object.keys(payload).filter((key) => !allowed.has(key))
  if (unknown.length > 0) {
    throw new SuccessorRequestError(`payload carries unknown fields: ${unknown.join(', ')}`)
  }
}

function assertParamsAllowlist(params: SuccessorQueryParams): void {
  const unknown = Object.keys(params).filter((key) => !SUCCESSOR_SNAPSHOT_PARAMS_FIELDS.has(key))
  if (unknown.length > 0) {
    throw new SuccessorRequestError(`params carries unknown fields: ${unknown.join(', ')}`)
  }
}

function validateCommandOptions(options: SuccessorCommandOptions): void {
  assertNoSmuggledOptions(options, 'command')
  assertRequestNonEmpty(options.commandId, 'commandId')
  assertRequestNonEmpty(options.projectLocator, 'projectLocator')
  assertRequestNonEmpty(options.actorRef, 'actorRef')
  if (options.traceId !== undefined && (typeof options.traceId !== 'string' || options.traceId.trim() === '')) {
    throw new SuccessorRequestError('traceId must be a non-empty string')
  }
  if (!SUCCESSOR_COMMAND_KINDS.has(options.commandKind)) {
    throw new SuccessorRequestError(`unknown commandKind discriminator: ${String(options.commandKind)}`)
  }
  if (!SUCCESSOR_COMMAND_KINDS.has(options.payload.payload_kind)) {
    throw new SuccessorRequestError(`unknown payload_kind discriminator: ${String(options.payload.payload_kind)}`)
  }
  if (options.commandKind !== options.payload.payload_kind) {
    throw new SuccessorRequestError('commandKind must match the typed payload payload_kind')
  }
  assertPayloadAllowlist(options.payload)
  assertRequestNonEmpty(options.payload.projection_id, 'payload.projection_id')
  assertSourceKeyFields(options.payload, 'payload')
  if (options.payload.payload_kind === 'rollback_projection') {
    assertRequestNonNegativeInteger(options.payload.target_generation, 'payload.target_generation')
    assertRequestNonNegativeInteger(
      options.payload.expected_active_generation,
      'payload.expected_active_generation',
    )
    assertRequestNonNegativeInteger(
      options.payload.expected_offset_revision,
      'payload.expected_offset_revision',
    )
  }
  if (options.payload.payload_kind === 'rebuild_projection' && options.payload.mode !== undefined) {
    if (options.payload.mode !== 'FULL' && options.payload.mode !== 'INCREMENTAL') {
      throw new SuccessorRequestError('rebuild mode must be FULL or INCREMENTAL')
    }
  }
  if (options.expectedBaseToken != null) {
    assertRequestNonEmpty(options.expectedBaseToken, 'expectedBaseToken')
  }
  if (options.approvalLocator != null) {
    assertRequestNonEmpty(options.approvalLocator, 'approvalLocator')
  }
}

function validateQueryOptions(options: SuccessorQueryOptions): void {
  assertNoSmuggledOptions(options, 'query')
  assertRequestNonEmpty(options.queryId, 'queryId')
  assertRequestNonEmpty(options.projectLocator, 'projectLocator')
  if (options.traceId !== undefined && (typeof options.traceId !== 'string' || options.traceId.trim() === '')) {
    throw new SuccessorRequestError('traceId must be a non-empty string')
  }
  if (!SUCCESSOR_QUERY_KINDS.has(options.queryKind) || options.queryKind !== options.params.params_kind) {
    throw new SuccessorRequestError('unknown query/params discriminator')
  }
  assertParamsAllowlist(options.params)
  assertRequestNonEmpty(options.params.projection_id, 'params.projection_id')
  assertSourceKeyFields(options.params, 'params')
  if (options.params.params_kind === 'projection_snapshot' && options.params.page_size !== undefined) {
    if (!Number.isInteger(options.params.page_size) || options.params.page_size < 1 || options.params.page_size > 100) {
      throw new SuccessorRequestError('page_size must be an integer from 1 to 100')
    }
  }
}

function buildCommandPayload(payload: SuccessorCommandPayload): Record<string, unknown> {
  const allowed = commandPayloadAllowlist(payload)
  return Object.fromEntries(Object.entries(payload).filter(([key]) => allowed.has(key)))
}

function buildCommandRequest(options: SuccessorCommandOptions, traceId: string): Record<string, unknown> {
  const request: Record<string, unknown> = {
    command_id: options.commandId,
    command_kind: options.commandKind,
    project_locator: options.projectLocator,
    trace_id: traceId,
    payload: buildCommandPayload(options.payload),
  }
  if (options.expectedBaseToken != null) {
    request.expected_base_token = options.expectedBaseToken
  }
  if (options.approvalLocator != null) {
    request.approval_locator = options.approvalLocator
  }
  return request
}

function buildQueryRequest(options: SuccessorQueryOptions, traceId: string): Record<string, unknown> {
  return {
    query_id: options.queryId,
    query_kind: options.queryKind,
    project_locator: options.projectLocator,
    trace_id: traceId,
    params: Object.fromEntries(
      Object.entries(options.params).filter(([key]) => SUCCESSOR_SNAPSHOT_PARAMS_FIELDS.has(key)),
    ),
  }
}

function bindCommandEnvelope(
  options: SuccessorCommandOptions,
  envelope: SuccessorEnvelope,
  traceId: string,
): void {
  if ('resolution_state' in envelope.meta) {
    const meta = envelope.meta
    if (
      meta.project_key !== options.projectLocator ||
      meta.trace_id !== traceId ||
      meta.request_id !== options.commandId
    ) {
      throw new SuccessorBindingError(
        'UNRESOLVED meta does not exact-bind projectLocator, trace or command id',
        { commandId: options.commandId, projectLocator: options.projectLocator, traceId },
      )
    }
    return
  }
  if (!('command_id' in envelope.meta)) {
    throw new SuccessorBindingError('Command response must carry command meta')
  }
  const meta = envelope.meta
  if (meta.command_id !== options.commandId) {
    throw new SuccessorBindingError('Command response command_id does not match the request', {
      expected: options.commandId,
      actual: meta.command_id,
    })
  }
  if (meta.project_key !== options.projectLocator || meta.project_scope_ref.project_key !== options.projectLocator) {
    throw new SuccessorBindingError('Command response project key does not match the request projectLocator', {
      expected: options.projectLocator,
      actual: meta.project_key,
    })
  }
  if (meta.trace_id !== traceId) {
    throw new SuccessorBindingError('Command response trace_id does not match the request trace', {
      expected: traceId,
      actual: meta.trace_id,
    })
  }
}

function bindQueryEnvelope(
  options: SuccessorQueryOptions,
  envelope: SuccessorEnvelope,
  traceId: string,
): void {
  if ('resolution_state' in envelope.meta) {
    const meta = envelope.meta
    if (
      meta.project_key !== options.projectLocator ||
      meta.trace_id !== traceId ||
      meta.request_id !== options.queryId
    ) {
      throw new SuccessorBindingError(
        'UNRESOLVED meta does not exact-bind projectLocator, trace or query id',
        { queryId: options.queryId, projectLocator: options.projectLocator, traceId },
      )
    }
    return
  }
  if ('query_id' in envelope.meta) {
    const meta = envelope.meta
    if (meta.query_id !== options.queryId) {
      throw new SuccessorBindingError('Query response query_id does not match the request', {
        expected: options.queryId,
        actual: meta.query_id,
      })
    }
    if (meta.project_key !== options.projectLocator || meta.project_scope_ref.project_key !== options.projectLocator) {
      throw new SuccessorBindingError('Query response project key does not match the request projectLocator', {
        expected: options.projectLocator,
        actual: meta.project_key,
      })
    }
    if (meta.trace_id !== traceId) {
      throw new SuccessorBindingError('Query response trace_id does not match the request trace', {
        expected: traceId,
        actual: meta.trace_id,
      })
    }
    return
  }
  if (!('projection_id' in envelope.meta)) {
    throw new SuccessorBindingError('Query response must carry projection, query or unresolved meta')
  }
  const meta = envelope.meta
  if (meta.project_key !== options.projectLocator || meta.project_scope_ref.project_key !== options.projectLocator) {
    throw new SuccessorBindingError('Query response project key does not match the request projectLocator', {
      expected: options.projectLocator,
      actual: meta.project_key,
    })
  }
  if (meta.projection_id !== options.params.projection_id) {
    throw new SuccessorBindingError('Query response projection_id does not match the request', {
      expected: options.params.projection_id,
      actual: meta.projection_id,
    })
  }
  const sourceKeyFields = [
    'projector_id',
    'projector_version',
    'source_kind',
    'source_ref',
    'source_incarnation',
  ] as const
  for (const field of sourceKeyFields) {
    if (meta[field] !== options.params[field]) {
      throw new SuccessorBindingError(`Query response ${field} does not match the request source key`, {
        expected: options.params[field],
        actual: meta[field],
      })
    }
  }
  if (meta.trace_id !== traceId) {
    throw new SuccessorBindingError('Query response trace_id does not match the request trace', {
      expected: traceId,
      actual: meta.trace_id,
    })
  }
}

async function dispatchSuccessorCommand(
  options: SuccessorCommandOptions,
  traceId: string,
): Promise<SuccessorEnvelope> {
  const payloadDigest = computeSuccessorCommandFingerprint(
    SUCCESSOR_V2_COMMAND_URL,
    options.projectLocator,
    options.commandId,
    options.commandKind,
    options.payload,
    { expectedBaseToken: options.expectedBaseToken, approvalLocator: options.approvalLocator },
  )
  upsertSuccessorPendingCommand({
    command_id: options.commandId,
    command_kind: options.commandKind,
    project_locator: options.projectLocator,
    endpoint: SUCCESSOR_V2_COMMAND_URL,
    payload_digest: payloadDigest,
  })
  const raw = await requestJson(resolveUrl(SUCCESSOR_V2_COMMAND_URL), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(buildCommandRequest(options, traceId)),
  })
  const envelope = decodeSuccessorEnvelope(raw)
  bindCommandEnvelope(options, envelope, traceId)
  return envelope
}

export async function submitSuccessorCommand(options: SuccessorCommandOptions): Promise<SuccessorEnvelope> {
  validateCommandOptions(options)
  const traceId = options.traceId === undefined ? createTraceId() : options.traceId.trim()
  const payloadDigest = computeSuccessorCommandFingerprint(
    SUCCESSOR_V2_COMMAND_URL,
    options.projectLocator,
    options.commandId,
    options.commandKind,
    options.payload,
    { expectedBaseToken: options.expectedBaseToken, approvalLocator: options.approvalLocator },
  )
  const dedupeKey = JSON.stringify([
    SUCCESSOR_V2_COMMAND_URL,
    options.projectLocator,
    options.commandId,
    payloadDigest,
  ])
  const inFlight = successorInFlightCommands.get(dedupeKey)
  if (inFlight) {
    if (options.traceId !== undefined && options.traceId.trim() !== inFlight.traceId) {
      throw new SuccessorConflictError(
        `Command ${options.commandId} is already in flight with a different explicit trace`,
        {
          commandId: options.commandId,
          projectLocator: options.projectLocator,
          firstTrace: inFlight.traceId,
          secondTrace: options.traceId.trim(),
        },
      )
    }
    return inFlight.promise
  }

  const pending = readSuccessorPendingCommands()
  const prior = pending[pendingCommandKey(options.projectLocator, options.commandId)]
  if (prior && (prior.command_kind !== options.commandKind || prior.payload_digest !== payloadDigest)) {
    throw new SuccessorConflictError(
      `Command ${options.commandId} already has a different payload; use a new command id`,
      { commandId: options.commandId, projectLocator: options.projectLocator },
    )
  }

  const request = dispatchSuccessorCommand(options, traceId)
  successorInFlightCommands.set(dedupeKey, { traceId, promise: request })
  try {
    const envelope = await request
    if (envelope.status !== 'waiting') {
      removeSuccessorPendingCommand(options.projectLocator, options.commandId)
    }
    return envelope
  } finally {
    successorInFlightCommands.delete(dedupeKey)
  }
}

export async function fetchSuccessorQuery(options: SuccessorQueryOptions): Promise<SuccessorEnvelope> {
  validateQueryOptions(options)
  const traceId = options.traceId === undefined ? createTraceId() : options.traceId.trim()
  const raw = await requestJson(resolveUrl(SUCCESSOR_V2_QUERY_URL), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(buildQueryRequest(options, traceId)),
  })
  const envelope = decodeSuccessorEnvelope(raw)
  bindQueryEnvelope(options, envelope, traceId)
  if ('resolution_state' in envelope.meta) {
    return envelope
  }
  if ('query_id' in envelope.meta) {
    if (envelope.status === 'ok' || envelope.status === 'waiting') {
      throw new SuccessorDecodeError('query meta is only allowed for error-family query envelopes')
    }
    return envelope
  }
  if (!('projection_id' in envelope.meta)) {
    throw new SuccessorDecodeError('Query response must carry projection, query or unresolved meta')
  }
  if (envelope.status === 'ok' || envelope.status === 'waiting') {
    const snapshot = assertSuccessorProjectionSnapshotData(envelope.meta, envelope.data)
    if (snapshot.rollback_transition) {
      return applySuccessorRollbackTransition(
        options.projectLocator,
        envelope,
        snapshot.rollback_transition,
      )
    }
    return assertSuccessorProjectionFresh(options.projectLocator, envelope, snapshot.offset_ref)
  }
  return envelope
}

export function createSuccessorQueryRefetcher(
  options: SuccessorQueryOptions,
): () => Promise<SuccessorEnvelope> {
  return () => fetchSuccessorQuery(options)
}
