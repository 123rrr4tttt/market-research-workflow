"""Exact C8.3 export token-state runtime handler (store dispatch only).

Movement binding: ALL-SM-009 | C8.3 report delivery cluster.  The handler is
the successor S2 runtime realization for the export token-state port.  It
performs no DB or SQL itself: ``execute`` validates the exact claim/binding
digests and dispatches one typed command through the pure module-2 functions.
Token state is never claimed or revoked from process memory when the
configured backend is unavailable; degraded observations are not durable.
"""

from __future__ import annotations

from typing import Any

from app.successor_runtime.capabilities.c8_report_export_token_state import (
    ClaimExportTokenCommand,
    PruneExportTokenStatesCommand,
    ReadbackExportTokenCommand,
    ReportExportTokenStateStore,
    RevokeExportTokenCommand,
    TokenClaimRecord,
    TokenPruneRecord,
    TokenReadbackRecord,
    TokenRevokeRecord,
    claim_report_export_token_once,
    prune_report_export_token_states,
    readback_report_export_token,
    revoke_report_export_token,
)
from app.successor_runtime.runtime.assignments import (
    RuntimeAssignment,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)

__all__ = ["C8_3ExportTokenStateRuntimeHandler"]

_EXACT_HANDLER_BINDING_DRIFT = "EXACT_C8_3_EXPORT_TOKEN_STATE_HANDLER_BINDING_DRIFT"
_CLAIM_ASSIGNMENT_BINDING_DRIFT = "CLAIM_ASSIGNMENT_BINDING_DRIFT"
_UNSUPPORTED_COMMAND = "C8_3_EXPORT_TOKEN_STATE_COMMAND_UNSUPPORTED"

_TokenStateRecord = (
    TokenClaimRecord | TokenRevokeRecord | TokenReadbackRecord | TokenPruneRecord
)


class C8_3ExportTokenStateRuntimeHandler(RuntimeHandler):
    """Dispatch one typed token-state command under an exact binding."""

    def __init__(
        self,
        *,
        store: ReportExportTokenStateStore,
        command: (
            ClaimExportTokenCommand
            | RevokeExportTokenCommand
            | ReadbackExportTokenCommand
            | PruneExportTokenStatesCommand
        ),
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        if not isinstance(store, ReportExportTokenStateStore):
            raise TypeError("C8.3 export token state handler requires a typed store")
        self._require_supported_command(command)
        require_digest(
            handler_binding_digest,
            "C8.3 export token state handler binding digest",
        )
        require_digest(
            interpreter_profile_digest,
            "C8.3 export token state interpreter profile digest",
        )
        require_digest(
            operation_contract_digest,
            "C8.3 export token state operation contract digest",
        )
        require_digest(
            deployment_catalog_digest,
            "C8.3 export token state deployment catalog digest",
        )
        self.store = store
        self.command = command
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.execute_calls = 0
        self.last_record: Any = None

    @staticmethod
    def _require_supported_command(command: Any) -> None:
        if not isinstance(
            command,
            (
                ClaimExportTokenCommand,
                RevokeExportTokenCommand,
                ReadbackExportTokenCommand,
                PruneExportTokenStatesCommand,
            ),
        ):
            raise TypeError("C8.3 export token state handler requires a typed command")

    @staticmethod
    def _artifact_id_for_receipt(command: Any, assignment: RuntimeAssignment) -> str:
        artifact_id = getattr(command, "artifact_id", None)
        if artifact_id:
            return str(artifact_id)
        return assignment.work_item_id

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure(_CLAIM_ASSIGNMENT_BINDING_DRIFT)
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.deployment_catalog_digest != self.deployment_catalog_digest
        ):
            raise DefiniteInterpreterFailure(_EXACT_HANDLER_BINDING_DRIFT)
        self._require_supported_command(self.command)
        record = self._dispatch(self.store, self.command)
        self.last_record = record
        self.execute_calls += 1
        artifact_id = self._artifact_id_for_receipt(self.command, assignment)
        return InterpreterOutcome.succeeded(
            record.record_digest,
            receipt_ref=f"receipt:report-export-token-state:{artifact_id}",
        )

    def _dispatch(
        self,
        store: ReportExportTokenStateStore,
        command: Any,
    ) -> _TokenStateRecord:
        if isinstance(command, ClaimExportTokenCommand):
            return claim_report_export_token_once(store, command)
        if isinstance(command, RevokeExportTokenCommand):
            return revoke_report_export_token(store, command)
        if isinstance(command, ReadbackExportTokenCommand):
            return readback_report_export_token(store, command)
        if isinstance(command, PruneExportTokenStatesCommand):
            return prune_report_export_token_states(store, command)
        raise DefiniteInterpreterFailure(_UNSUPPORTED_COMMAND)
