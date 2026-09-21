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

from functorial_kit import Failure

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
from .failure_policy import raise_runtime_failure, runtime_failure

__all__ = [
    "SuccessorRuntimeFacade",
    "FacadeContractError",
    "FacadeInputError",
    "FacadePortResultError",
    "error_envelope_v2",
    "success_envelope_v2",
]


class FacadeContractError(ValueError):
    """Raised by the legacy ABI when the facade builds an invalid envelope."""


class FacadeInputError(TypeError):
    """Raised by the legacy ABI when a facade input is not a typed request."""


class FacadePortResultError(TypeError):
    """Raised by the legacy ABI when a port returns an untyped result."""


def _facade_failure(
    code: str,
    message: str,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    return runtime_failure(code, message, exception_type, site=site)


def _raise_facade_failure(failure: Failure) -> None:
    exception_type: type[Exception]
    if failure.code == "FACADE_INPUT_INVALID":
        exception_type = FacadeInputError
    elif failure.code == "FACADE_PORT_RESULT_INVALID":
        exception_type = FacadePortResultError
    else:
        exception_type = FacadeContractError
    raise_runtime_failure(failure, exception_type)


def error_envelope_v2(
    *,
    status: str,
    meta: CommandMetaV2 | QueryMetaV2,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> ApiEnvelopeV2:
    result = _error_envelope_v2_result(
        status=status, meta=meta, code=code, message=message, details=details
    )
    if isinstance(result, Failure):
        _raise_facade_failure(result)
    return result


def _error_envelope_v2_result(
    *,
    status: str,
    meta: CommandMetaV2 | QueryMetaV2,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> ApiEnvelopeV2 | Failure:
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
    if not validate_api_envelope_v2(envelope).valid:
        return _facade_failure(
            "FACADE_CONTRACT_INVALID",
            "facade produced an invalid error envelope",
            FacadeContractError,
            site="successor_runtime.runtime.facade.error_envelope_v2",
        )
    return envelope


def success_envelope_v2(
    *,
    status: str,
    meta: CommandMetaV2 | QueryMetaV2,
    data: Mapping[str, Any],
) -> ApiEnvelopeV2:
    result = _success_envelope_v2_result(status=status, meta=meta, data=data)
    if isinstance(result, Failure):
        _raise_facade_failure(result)
    return result


def _success_envelope_v2_result(
    *,
    status: str,
    meta: CommandMetaV2 | QueryMetaV2,
    data: Mapping[str, Any],
) -> ApiEnvelopeV2 | Failure:
    envelope = ApiEnvelopeV2(
        status=status,  # type: ignore[arg-type]
        meta=meta,
        data=dict(data),
        error=None,
    )
    if not validate_api_envelope_v2(envelope).valid:
        return _facade_failure(
            "FACADE_CONTRACT_INVALID",
            "facade produced an invalid success envelope",
            FacadeContractError,
            site="successor_runtime.runtime.facade.success_envelope_v2",
        )
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
            _raise_facade_failure(
                _facade_failure(
                    "FACADE_INPUT_INVALID",
                    "facade requires a submission port and a query port",
                    FacadeInputError,
                    site="successor_runtime.runtime.facade.__init__",
                )
            )
        self._submission_port = submission_port
        self._query_port = query_port

    def submit_result(self, command: object) -> ApiEnvelopeV2 | Failure:
        from .facade_contracts import FacadeCommandV2

        if not isinstance(command, FacadeCommandV2):
            return _facade_failure(
                "FACADE_INPUT_INVALID",
                "facade submit requires FacadeCommandV2",
                FacadeInputError,
                site="successor_runtime.runtime.facade.submit",
            )
        violations = validate_command_v2(command).violations
        if violations:
            return _error_envelope_v2_result(
                status="error",
                meta=command.meta,
                code="COMMAND_CONTRACT_VIOLATION",
                message=violations[0].message,
                details={"violations": [violation.message for violation in violations]},
            )
        try:
            receipt = self._submission_port.submit(command)
        except C9TransactionFatal:
            # kit:boundary owner=successor_runtime.facade.submit class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_facade_transaction_fatal_submit_preserves_identity_and_cause
            raise
        except C9CommandConflict as exc:
            return _error_envelope_v2_result(
                status="conflict",
                meta=command.meta,
                code="COMMAND_CONFLICT",
                message=str(exc),
            )
        except C9CommandBaseConflict as exc:
            return _error_envelope_v2_result(
                status="conflict",
                meta=command.meta,
                code="COMMAND_BASE_CONFLICT",
                message=str(exc),
            )
        except C9CommandBlocked as exc:
            return _error_envelope_v2_result(
                status="blocked",
                meta=command.meta,
                code="COMMAND_BLOCKED",
                message=str(exc),
            )
        except C9Unavailable as exc:
            return _error_envelope_v2_result(
                status="unavailable",
                meta=command.meta,
                code="COMMAND_UNAVAILABLE",
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with typed error
            return _error_envelope_v2_result(
                status="error",
                meta=command.meta,
                code="COMMAND_FAILED",
                message=str(exc),
            )
        if not isinstance(receipt, CommandReceipt):
            return _facade_failure(
                "FACADE_PORT_RESULT_INVALID",
                "submission port must return CommandReceipt",
                FacadePortResultError,
                site="successor_runtime.runtime.facade.submit",
            )
        return _receipt_envelope_result(command.meta, receipt)

    def submit(self, command: object) -> ApiEnvelopeV2:
        """Legacy exception ABI over :meth:`submit_result`."""

        result = self.submit_result(command)
        if isinstance(result, Failure):
            _raise_facade_failure(result)
        return result

    def query_result(self, query: object) -> ApiEnvelopeV2 | Failure:
        from .facade_contracts import FacadeQueryV2

        if not isinstance(query, FacadeQueryV2):
            return _facade_failure(
                "FACADE_INPUT_INVALID",
                "facade query requires FacadeQueryV2",
                FacadeInputError,
                site="successor_runtime.runtime.facade.query",
            )
        violations = validate_query_v2(query).violations
        if violations:
            return _error_envelope_v2_result(
                status="error",
                meta=query.meta,
                code="QUERY_CONTRACT_VIOLATION",
                message=violations[0].message,
                details={"violations": [violation.message for violation in violations]},
            )
        try:
            result = self._query_port.read(query)
        except C9TransactionFatal:
            # kit:boundary owner=successor_runtime.facade.query class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_facade_transaction_fatal_query_preserves_identity_and_cause
            raise
        except C9CommandBlocked as exc:
            return _error_envelope_v2_result(
                status="blocked",
                meta=query.meta,
                code="QUERY_BLOCKED",
                message=str(exc),
            )
        except C9CommandConflict as exc:
            return _error_envelope_v2_result(
                status="conflict",
                meta=query.meta,
                code="QUERY_CONFLICT",
                message=str(exc),
            )
        except C9Unavailable as exc:
            return _error_envelope_v2_result(
                status="unavailable",
                meta=query.meta,
                code="QUERY_UNAVAILABLE",
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with typed error
            return _error_envelope_v2_result(
                status="error",
                meta=query.meta,
                code="QUERY_FAILED",
                message=str(exc),
            )
        if not isinstance(result, QueryResult):
            return _facade_failure(
                "FACADE_PORT_RESULT_INVALID",
                "query port must return QueryResult",
                FacadePortResultError,
                site="successor_runtime.runtime.facade.query",
            )
        data = result.data
        if isinstance(data, ProjectionSnapshotDataV2):
            violations = validate_projection_snapshot_data_v2(
                data, result.meta
            ).violations
            if violations:
                return _error_envelope_v2_result(
                    status="error",
                    meta=query.meta,
                    code="PROJECTION_META_DATA_MISMATCH",
                    message=violations[0].message,
                    details={
                        "violations": [violation.message for violation in violations]
                    },
                )
        elif not isinstance(data, Mapping):
            return _facade_failure(
                "FACADE_PORT_RESULT_INVALID",
                "query port must return mapping or typed snapshot data",
                FacadePortResultError,
                site="successor_runtime.runtime.facade.query",
            )
        envelope = ApiEnvelopeV2(
            status="ok",
            meta=result.meta,
            data=data if isinstance(data, ProjectionSnapshotDataV2) else dict(data),
            error=None,
        )
        if not validate_api_envelope_v2(envelope).valid:
            return _facade_failure(
                "FACADE_CONTRACT_INVALID",
                "query port produced an invalid envelope",
                FacadeContractError,
                site="successor_runtime.runtime.facade.query",
            )
        return envelope

    def query(self, query: object) -> ApiEnvelopeV2:
        """Legacy exception ABI over :meth:`query_result`."""

        result = self.query_result(query)
        if isinstance(result, Failure):
            _raise_facade_failure(result)
        return result


def _receipt_envelope(
    meta: CommandMetaV2,
    receipt: CommandReceipt,
) -> ApiEnvelopeV2:
    result = _receipt_envelope_result(meta, receipt)
    if isinstance(result, Failure):
        _raise_facade_failure(result)
    return result


def _receipt_envelope_result(
    meta: CommandMetaV2,
    receipt: CommandReceipt,
) -> ApiEnvelopeV2 | Failure:
    status = "ok" if receipt.state == "TERMINAL" else "waiting"
    return _success_envelope_v2_result(
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
