import type {
  SuccessorTypedRejectionReason,
  SuccessorUiObservationState,
} from '../lib/api/domains/successor-runtime'

export type SuccessorRuntimeObservationProps = {
  observation: SuccessorUiObservationState | null
  labels?: Partial<Record<SuccessorUiObservationState, string>>
  reason?: SuccessorTypedRejectionReason | null
}

export function SuccessorRuntimeObservation({
  observation,
  labels,
  reason,
}: SuccessorRuntimeObservationProps) {
  if (!observation) {
    return <span className="successor-runtime-observation" data-observation="none" />
  }
  const label = labels?.[observation] ?? observation
  const title = reason ? `${reason.code}: ${reason.message}` : undefined
  return (
    <span
      className={`successor-runtime-observation successor-runtime-observation--${observation}`}
      data-observation={observation}
      title={title}
    >
      {label}
    </span>
  )
}

export default SuccessorRuntimeObservation
