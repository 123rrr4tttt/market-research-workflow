"""S2 C7.2 ingest submission registry runtime handler.

This handler binds one typed reserve/complete/forget command to its exact
successor port execution and returns the deterministic readback digest.  It
performs no SQL and starts no database transaction: the caller supplies a
successor-only store, and every authority/effect field stays false/zero.
"""

from __future__ import annotations

from typing import Any

from app.successor_runtime.capabilities.ingest_c7_registry import (
    IngestRegistryCompleteCommand,
    IngestRegistryForgetCommand,
    IngestRegistryForgetResult,
    IngestRegistryReadback,
    IngestRegistryReserveCommand,
    complete_submission,
    forget_submission,
    reserve_submission,
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


class C7IngestRegistryRuntimeHandler(RuntimeHandler):
    """Execute one exact C7 ingest registry command as a readback handler."""

    def __init__(
        self,
        *,
        store: Any,
        command: (
            IngestRegistryReserveCommand
            | IngestRegistryCompleteCommand
            | IngestRegistryForgetCommand
        ),
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        if not isinstance(
            command,
            (
                IngestRegistryReserveCommand,
                IngestRegistryCompleteCommand,
                IngestRegistryForgetCommand,
            ),
        ):
            raise TypeError("C7 ingest registry handler requires a typed command")
        require_digest(handler_binding_digest, "C7 handler binding digest")
        require_digest(
            interpreter_profile_digest,
            "C7 interpreter profile digest",
        )
        require_digest(
            operation_contract_digest,
            "C7 operation contract digest",
        )
        require_digest(
            deployment_catalog_digest,
            "C7 deployment catalog digest",
        )
        self.store = store
        self.command = command
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.execute_calls = 0
        self.last_readback: (
            IngestRegistryReadback | IngestRegistryForgetResult | None
        ) = None
        self.operation_reason: str | None = None

    def _registry_key(self) -> str:
        if isinstance(self.command, IngestRegistryReserveCommand):
            return self.command.identity.registry_key
        return self.command.registry_key

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        del context
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.deployment_catalog_digest != self.deployment_catalog_digest
        ):
            raise DefiniteInterpreterFailure(
                "EXACT_C7_INGEST_REGISTRY_HANDLER_BINDING_DRIFT"
            )

        if isinstance(self.command, IngestRegistryReserveCommand):
            result = reserve_submission(self.store, self.command)
            operation_reason = "INGEST_REGISTRY_RESERVE_READBACK_ONLY"
        elif isinstance(self.command, IngestRegistryCompleteCommand):
            result = complete_submission(self.store, self.command)
            operation_reason = "INGEST_REGISTRY_COMPLETE_READBACK_ONLY"
        elif isinstance(self.command, IngestRegistryForgetCommand):
            result = forget_submission(self.store, self.command)
            operation_reason = "INGEST_REGISTRY_FORGET_READBACK_ONLY"
        else:
            raise TypeError("C7 ingest registry handler command is unsupported")

        self.execute_calls += 1
        self.last_readback = result
        self.operation_reason = operation_reason
        if not result.readback_digest:
            raise DefiniteInterpreterFailure(
                "EXACT_C7_INGEST_REGISTRY_READBACK_DIGEST_MISSING"
            )
        registry_key = self._registry_key()
        return InterpreterOutcome.succeeded(
            result.readback_digest,
            receipt_ref=f"receipt:ingest-registry:{registry_key}",
        )


__all__ = ["C7IngestRegistryRuntimeHandler"]
