import type {
  SuccessorEnvelope,
  SuccessorEnvelopeStatus,
} from '../lib/api/domains/successor-runtime'

export type SuccessorRuntimeStatusProps = {
  envelope: SuccessorEnvelope | null
  labels?: Partial<Record<SuccessorEnvelopeStatus, string>>
}

function metaTitle(envelope: SuccessorEnvelope): string {
  if ('resolution_state' in envelope.meta) {
    return `unresolved=${envelope.meta.request_id} project=${envelope.meta.project_key}`
  }
  const scope = envelope.meta.project_scope_ref
  if ('projection_id' in envelope.meta) {
    return [
      envelope.meta.projection_id,
      `revision=${envelope.meta.projection_revision}`,
      `source=${envelope.meta.source_digest}`,
      `cursor=${envelope.meta.cursor}`,
      `scope=${scope.scope_digest}`,
    ].join(' ')
  }
  if ('command_id' in envelope.meta) {
    return `command=${envelope.meta.command_id} scope=${scope.scope_digest}`
  }
  return `query=${envelope.meta.query_id} scope=${scope.scope_digest}`
}

export function SuccessorRuntimeStatus({ envelope, labels }: SuccessorRuntimeStatusProps) {
  if (!envelope) {
    return <span className="successor-runtime-status" data-status="none" />
  }
  const label = labels?.[envelope.status] ?? envelope.status
  return (
    <span
      className={`successor-runtime-status successor-runtime-status--${envelope.status}`}
      data-status={envelope.status}
      title={metaTitle(envelope)}
    >
      {label}
    </span>
  )
}

export default SuccessorRuntimeStatus
