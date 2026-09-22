import { useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { useAppLocale, translate } from '../app/platform/i18n'
import SuccessorRuntimeObservation from '../components/SuccessorRuntimeObservation'
import SuccessorRuntimeStatus from '../components/SuccessorRuntimeStatus'
import {
  SuccessorRuntimeError,
  decodeSuccessorTypedRejection,
  deriveSuccessorUiObservation,
  fetchSuccessorQuery,
  projectSuccessorServerScope,
  type SuccessorProjectionSnapshotData,
  type SuccessorTypedRejectionReason,
  type SuccessorUiObservationState,
} from '../lib/api/domains/successor-runtime'
import { queryKeys } from '../lib/queryKeys'
import { buildSuccessorRuntimeObservationQueryOptions } from './successorRuntimeConfig'

type SuccessorRuntimePageProps = {
  projectKey: string
}

function useSuccessorRuntimeObservation(projectKey: string) {
  return useQuery({
    queryKey: queryKeys.successorRuntime.snapshot(projectKey),
    queryFn: () => fetchSuccessorQuery(buildSuccessorRuntimeObservationQueryOptions(projectKey)),
    enabled: Boolean(projectKey.trim()),
  })
}

function truncateJson(value: Record<string, unknown>, maxLength = 160): string {
  const raw = JSON.stringify(value)
  if (raw.length <= maxLength) return raw
  return `${raw.slice(0, maxLength)}...`
}

export default function SuccessorRuntimePage({ projectKey }: SuccessorRuntimePageProps) {
  const locale = useAppLocale()
  const query = useSuccessorRuntimeObservation(projectKey)

  const clientError = query.error
    ? query.error instanceof SuccessorRuntimeError
      ? query.error
      : new SuccessorRuntimeError(
          'query_failed',
          query.error instanceof Error ? query.error.message : String(query.error),
        )
    : null

  const phase: 'not_started' | 'in_flight' | 'settled' =
    query.isPending && !query.data
      ? 'in_flight'
      : query.data || clientError
        ? 'settled'
        : 'not_started'

  const observation: SuccessorUiObservationState = deriveSuccessorUiObservation({
    phase,
    envelope: query.data ?? null,
    clientError,
  })
  const typedRejection: SuccessorTypedRejectionReason | null = query.data
    ? decodeSuccessorTypedRejection(query.data)
    : null

  let snapshot: SuccessorProjectionSnapshotData | null = null
  if (query.data && (query.data.status === 'ok' || query.data.status === 'waiting')) {
    try {
      snapshot = projectSuccessorServerScope(projectKey, query.data).snapshot
    } catch {
      snapshot = null
    }
  }

  const envelopeError = query.data?.error
    ? `${query.data.error.code}: ${query.data.error.message}`
    : null
  const errorLabel = envelopeError
    ? envelopeError
    : clientError
      ? `${clientError.code}: ${clientError.message}`
      : null
  const candidateValues = snapshot?.candidate_values ?? []

  return (
    <section className="content-stack successor-runtime-page" data-module="sysSuccessorRuntime">
      <section className="panel">
        <div className="panel-header">
          <h2>{translate(locale, 'shell.title.sysSuccessorRuntime')}</h2>
          <div className="inline-actions">
            <span data-read-only-boundary="true">read-only</span>
            <button
              type="button"
              className="chip"
              disabled={query.isFetching}
              onClick={() => {
                void query.refetch()
              }}
            >
              <RefreshCw size={13} />
              {translate(locale, 'shell.action.refresh')}
            </button>
          </div>
        </div>

        <div className="successor-runtime-page__status" data-testid="successor-runtime-page-status">
          <SuccessorRuntimeObservation observation={observation} reason={typedRejection} />
          <SuccessorRuntimeStatus envelope={query.data ?? null} />
          {errorLabel ? (
            <span className="successor-runtime-page__error" data-testid="successor-runtime-error">
              {errorLabel}
            </span>
          ) : null}
        </div>

        {snapshot ? (
          <section className="successor-runtime-page__snapshot">
            <p>
              {snapshot.projection_id} / revision {snapshot.projection_revision} / generation{' '}
              {snapshot.projection_generation} / cursor {snapshot.cursor}
            </p>
            {candidateValues.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>value_id</th>
                      <th>value_ref</th>
                      <th>sink</th>
                      <th>byte_size</th>
                      <th>payload</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidateValues.map((value) => (
                      <tr key={value.value_id}>
                        <td>{value.value_id}</td>
                        <td>{value.value_ref}</td>
                        <td>{value.sink}</td>
                        <td>{value.byte_size}</td>
                        <td>{truncateJson(value.payload)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-cell">{translate(locale, 'shared.empty')}</p>
            )}
          </section>
        ) : null}
      </section>
    </section>
  )
}
