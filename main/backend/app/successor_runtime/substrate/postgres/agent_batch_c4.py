"""Family-local durable submission repository for C4.3.

The module uses the shared ``STARTED/TERMINAL/SUPERSEDED`` idempotency root
(``IdempotencyRepository``) with project/capability/logical-request scoping.
Family-specific acceptance status (accepted/partially accepted/rejected/
conflict) is a typed receipt field, never a database enum, so the shared
idempotency contract stays generic and the C4.3 contract stays typed.

The in-memory repository is a deterministic fixture.  The PostgreSQL repository
delegates reserve/replay/conflict/terminal to the shared substrate and is
exercised by a real family-local disposable database
(``mrw_p3_c4_worker_test``).  No Celery, provider or network dispatch exists
here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.agent_batch_c4 import (
    C4AcceptanceState,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyBinding as SharedIdempotencyBinding,
)
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
)

__all__ = [
    "C4SubmissionConflict",
    "C4SubmissionNotFound",
    "C4SubmissionRepository",
    "InMemoryC4SubmissionRepository",
    "PostgresC4SubmissionRepository",
]


class C4SubmissionConflict(ValueError):
    """Raised when a logical request id is bound to a different digest."""


class C4SubmissionNotFound(KeyError):
    """Raised when no binding/receipt exists for the requested identity."""


@runtime_checkable
class C4SubmissionRepository(Protocol):
    """Durable submission read/write port used by the C4.3 contract."""

    def reserve(
        self, binding: SharedIdempotencyBinding
    ) -> tuple[SharedIdempotencyBinding, str]:
        """Reserve the exact idempotency binding; return binding and state."""

        ...

    def record_terminal(
        self,
        *,
        capability_id: str,
        logical_request_id: str,
        acceptance_state: C4AcceptanceState,
        receipt_ref: str,
    ) -> SharedIdempotencyBinding:
        """Terminate one binding; acceptance status stays in the receipt."""

        ...

    def load(
        self, *, capability_id: str, logical_request_id: str
    ) -> SharedIdempotencyBinding: ...


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class InMemoryC4SubmissionRepository:
    """Deterministic fixture repository mirroring STARTED/TERMINAL semantics."""

    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str], SharedIdempotencyBinding] = {}
        self._receipts: dict[tuple[str, str], tuple[C4AcceptanceState, str]] = {}

    def reserve(
        self, binding: SharedIdempotencyBinding
    ) -> tuple[SharedIdempotencyBinding, str]:
        key = (binding.capability_id, binding.logical_request_id)
        current = self._bindings.get(key)
        if current is None:
            self._bindings[key] = binding
            return binding, binding.state
        if current.request_digest != binding.request_digest:
            raise C4SubmissionConflict(
                "logical request id is already bound to a different digest"
            )
        return current, current.state

    def record_terminal(
        self,
        *,
        capability_id: str,
        logical_request_id: str,
        acceptance_state: C4AcceptanceState,
        receipt_ref: str,
    ) -> SharedIdempotencyBinding:
        key = (capability_id, logical_request_id)
        binding = self._bindings.get(key)
        if binding is None:
            raise C4SubmissionNotFound(
                "no C4 submission binding for capability/logical_request_id"
            )
        if binding.state != "STARTED":
            raise C4SubmissionConflict(
                "only a STARTED binding may be recorded as TERMINAL"
            )
        updated = SharedIdempotencyBinding(
            idempotency_id=binding.idempotency_id,
            capability_id=binding.capability_id,
            logical_request_id=binding.logical_request_id,
            operation_kind=binding.operation_kind,
            request_digest=binding.request_digest,
            run_id=binding.run_id,
            state="TERMINAL",
            terminal_observation_ref=receipt_ref,
        )
        self._bindings[key] = updated
        self._receipts[key] = (acceptance_state, receipt_ref)
        return updated

    def load(
        self, *, capability_id: str, logical_request_id: str
    ) -> SharedIdempotencyBinding:
        binding = self._bindings.get((capability_id, logical_request_id))
        if binding is None:
            raise C4SubmissionNotFound("C4 submission binding not found")
        return binding

    def receipt(
        self, *, capability_id: str, logical_request_id: str
    ) -> tuple[C4AcceptanceState, str]:
        value = self._receipts.get((capability_id, logical_request_id))
        if value is None:
            raise C4SubmissionNotFound("C4 submission receipt not found")
        return value


class PostgresC4SubmissionRepository:
    """Real PostgreSQL adapter over the shared STARTED/TERMINAL idempotency root.

    The acceptance status is returned/recorded through the typed receipt only;
    the DB row carries the generic idempotency state.
    """

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope
        self._repository = IdempotencyRepository(connection, scope)

    def reserve(
        self, binding: SharedIdempotencyBinding
    ) -> tuple[SharedIdempotencyBinding, str]:
        try:
            row = self._repository.reserve(binding)
        except ExactBindingConflict as exc:
            raise C4SubmissionConflict(str(exc)) from exc
        return self._binding_from_row(row), str(row["state"])

    @staticmethod
    def _binding_from_row(row: Any) -> SharedIdempotencyBinding:
        return SharedIdempotencyBinding(
            idempotency_id=row["idempotency_id"],
            capability_id=row["capability_id"],
            logical_request_id=row["logical_request_id"],
            operation_kind=row["operation_kind"],
            request_digest=row["request_digest"],
            run_id=row["run_id"] or "",
            state=row["state"],
            terminal_observation_ref=row["terminal_observation_ref"],
        )

    def record_terminal(
        self,
        *,
        capability_id: str,
        logical_request_id: str,
        acceptance_state: C4AcceptanceState,
        receipt_ref: str,
    ) -> SharedIdempotencyBinding:
        if not receipt_ref:
            raise ValueError("receipt_ref is required")
        row = self._repository.record_terminal(
            capability_id,
            logical_request_id,
            expected_revision=self._revision_of(capability_id, logical_request_id),
            terminal_observation_ref=receipt_ref,
        )
        return self._binding_from_row(row)

    def _revision_of(self, capability_id: str, logical_request_id: str) -> int:
        row = self._repository.load(capability_id, logical_request_id)
        return int(row["revision"])

    def load(
        self, *, capability_id: str, logical_request_id: str
    ) -> SharedIdempotencyBinding:
        try:
            row = self._repository.load(capability_id, logical_request_id)
        except RecordNotFound as exc:
            raise C4SubmissionNotFound(str(exc)) from exc
        return self._binding_from_row(row)
