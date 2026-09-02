"""Pure C9 successor runtime facade service (C9-M001).

The facade is intentionally infrastructure-free: it validates the
server-resolved command/query contract and calls the injected submission or
query port exactly once per request.  It never imports transport, API,
database, provider or execution modules, and every envelope keeps
``status/data/error/meta`` with ``control_feedback`` forced to ``False``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .facade_contracts import (
    ApiEnvelopeV2,
    ApiErrorV2,
    C9CommandBaseConflict,
    C9CommandBlocked,
    C9CommandConflict,
    C9TransactionFatal,
    C9Unavailable,
    CommandMetaV2,
    CommandReceipt,
    CommandSubmissionPort,
    ProjectionSnapshotDataV2,
    QueryMetaV2,
    QueryReadPort,
    QueryResult,
    validate_api_envelope_v2,
    validate_command_v2,
    validate_projection_snapshot_data_v2,
    validate_query_v2,
)

__all__ = [
    "SuccessorRuntimeFacade",
    "error_envelope_v2",
    "success_envelope_v2",
]


def error_envelope_v2(
    *,
    status: str,
    meta: CommandMetaV2 | QueryMetaV2,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> ApiEnvelopeV2:
    envelope = ApiEnvelopeV2(
        status=status,  # type: ignore[arg-type]
        meta=meta,
        data=None,
        error=ApiErrorV2(
            code=code,
            message=message,
            details=dict(details or {}),
        ),
    )
    if not validate_api_envelope_v2(envelope).valid:  # pragma: no cover - guard
        raise AssertionError("facade produced an invalid error envelope")
    return envelope


def success_envelope_v2(
    *,
    status: str,
    meta: CommandMetaV2 | QueryMetaV2,
    data: Mapping[str, Any],
) -> ApiEnvelopeV2:
    envelope = ApiEnvelopeV2(
        status=status,  # type: ignore[arg-type]
        meta=meta,
        data=dict(data),
        error=None,
    )
    if not validate_api_envelope_v2(envelope).valid:  # pragma: no cover - guard
        raise AssertionError("facade produced an invalid success envelope")
    return envelope


class SuccessorRuntimeFacade:
    """Pure service mapping one port call into a complete v2 envelope."""

    def __init__(
        self,
        *,
        submission_port: CommandSubmissionPort,
        query_port: QueryReadPort,
    ) -> None:
        if submission_port is None or query_port is None:
            raise ValueError("facade requires a submission port and a query port")
        self._submission_port = submission_port
        self._query_port = query_port

    def submit(self, command: object) -> ApiEnvelopeV2:
        from .facade_contracts import FacadeCommandV2

        if not isinstance(command, FacadeCommandV2):
            raise TypeError("facade submit requires FacadeCommandV2")
        violations = validate_command_v2(command).violations
        if violations:
            return error_envelope_v2(
                status="error",
                meta=command.meta,
                code="COMMAND_CONTRACT_VIOLATION",
                message=violations[0].message,
                details={"violations": [violation.message for violation in violations]},
            )
        try:
            receipt = self._submission_port.submit(command)
        except C9TransactionFatal:
            raise
        except C9CommandConflict as exc:
            return error_envelope_v2(
                status="conflict",
                meta=command.meta,
                code="COMMAND_CONFLICT",
                message=str(exc),
            )
        except C9CommandBaseConflict as exc:
            return error_envelope_v2(
                status="conflict",
                meta=command.meta,
                code="COMMAND_BASE_CONFLICT",
                message=str(exc),
            )
        except C9CommandBlocked as exc:
            return error_envelope_v2(
                status="blocked",
                meta=command.meta,
                code="COMMAND_BLOCKED",
                message=str(exc),
            )
        except C9Unavailable as exc:
            return error_envelope_v2(
                status="unavailable",
                meta=command.meta,
                code="COMMAND_UNAVAILABLE",
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with typed error
            return error_envelope_v2(
                status="error",
                meta=command.meta,
                code="COMMAND_FAILED",
                message=str(exc),
            )
        return _receipt_envelope(command.meta, receipt)

    def query(self, query: object) -> ApiEnvelopeV2:
        from .facade_contracts import FacadeQueryV2

        if not isinstance(query, FacadeQueryV2):
            raise TypeError("facade query requires FacadeQueryV2")
        violations = validate_query_v2(query).violations
        if violations:
            return error_envelope_v2(
                status="error",
                meta=query.meta,
                code="QUERY_CONTRACT_VIOLATION",
                message=violations[0].message,
                details={"violations": [violation.message for violation in violations]},
            )
        try:
            result = self._query_port.read(query)
        except C9TransactionFatal:
            raise
        except C9CommandBlocked as exc:
            return error_envelope_v2(
                status="blocked",
                meta=query.meta,
                code="QUERY_BLOCKED",
                message=str(exc),
            )
        except C9CommandConflict as exc:
            return error_envelope_v2(
                status="conflict",
                meta=query.meta,
                code="QUERY_CONFLICT",
                message=str(exc),
            )
        except C9Unavailable as exc:
            return error_envelope_v2(
                status="unavailable",
                meta=query.meta,
                code="QUERY_UNAVAILABLE",
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with typed error
            return error_envelope_v2(
                status="error",
                meta=query.meta,
                code="QUERY_FAILED",
                message=str(exc),
            )
        if not isinstance(result, QueryResult):
            raise TypeError("query port must return QueryResult")
        data = result.data
        if isinstance(data, ProjectionSnapshotDataV2):
            violations = validate_projection_snapshot_data_v2(
                data, result.meta
            ).violations
            if violations:
                return error_envelope_v2(
                    status="error",
                    meta=query.meta,
                    code="PROJECTION_META_DATA_MISMATCH",
                    message=violations[0].message,
                    details={
                        "violations": [violation.message for violation in violations]
                    },
                )
        elif not isinstance(data, Mapping):
            raise TypeError("query port must return mapping or typed snapshot data")
        envelope = ApiEnvelopeV2(
            status="ok",
            meta=result.meta,
            data=data if isinstance(data, ProjectionSnapshotDataV2) else dict(data),
            error=None,
        )
        if not validate_api_envelope_v2(envelope).valid:  # pragma: no cover - guard
            raise AssertionError("query port produced an invalid envelope")
        return envelope


def _receipt_envelope(
    meta: CommandMetaV2,
    receipt: CommandReceipt,
) -> ApiEnvelopeV2:
    status = "ok" if receipt.state == "TERMINAL" else "waiting"
    return success_envelope_v2(
        status=status,
        meta=meta,
        data={
            "receipt_ref": receipt.receipt_ref,
            "command_id": receipt.command_id,
            "request_digest": receipt.request_digest,
            "state": receipt.state,
            "idempotency_id": receipt.idempotency_id,
            "logical_request_id": receipt.logical_request_id,
            "run_id": receipt.run_id,
            "authority_context_digest": receipt.authority_context_digest,
            "grant_epoch": receipt.grant_epoch,
            "grants_digest": receipt.grants_digest,
            "observed_at": receipt.observed_at,
        },
    )
