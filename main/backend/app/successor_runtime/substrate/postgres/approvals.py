"""Exact-binding runtime approval repository."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.first_specimen_delivery_gate import (
    DeliveryApprovalSnapshot,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    _one_mapping,
    _project_values,
    _scope_key,
    _table,
    _utcnow,
)


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    approval_id: str
    actor_id: str
    run_id: str
    step_id: str
    payload_digest: str
    decision: str
    expires_at: datetime
    authority_digest: str

    def values(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "actor_id": self.actor_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "payload_digest": self.payload_digest,
            "decision": self.decision,
            "expires_at": self.expires_at,
            "authority_digest": self.authority_digest,
        }


_EXACT_FIELDS = (
    "approval_id",
    "actor_id",
    "run_id",
    "step_id",
    "payload_digest",
    "decision",
    "expires_at",
    "authority_digest",
)


class ApprovalRepository:
    """Insert an immutable decision bound to one exact operation payload."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def decide(self, binding: ApprovalBinding) -> Mapping[str, Any]:
        if binding.actor_id != self.scope.actor_id:
            raise ExactBindingConflict("approval actor does not match RuntimeScope actor")
        table = _table("runtime_approvals")
        values = _project_values(self.scope, binding.values())
        now = _utcnow()
        values.update(revision=0, created_at=now, updated_at=now)
        self.connection.execute(
            pg_insert(table)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=(table.c.project_key, table.c.approval_id)
            )
        )
        current = self.load(binding.approval_id, for_update=True)
        for field in _EXACT_FIELDS:
            if current[field] != values[field]:
                raise ExactBindingConflict(
                    f"approval {binding.approval_id} has a different exact binding"
                )
        return current

    def load(self, approval_id: str, *, for_update: bool = False) -> Mapping[str, Any]:
        table = _table("runtime_approvals")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.approval_id == approval_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"runtime approval not found: {approval_id}")
        return row

    def require_current(
        self,
        approval_id: str,
        *,
        run_id: str,
        step_id: str,
        payload_digest: str,
        authority_digest: str,
        now: datetime,
    ) -> Mapping[str, Any]:
        row = self.load(approval_id)
        expected = {
            "run_id": run_id,
            "step_id": step_id,
            "payload_digest": payload_digest,
            "authority_digest": authority_digest,
        }
        if any(row[field] != value for field, value in expected.items()):
            raise ExactBindingConflict("approval does not bind the requested operation")
        if row["decision"] != "APPROVED":
            raise ExactBindingConflict("approval decision is not APPROVED")
        if row["expires_at"] <= now:
            raise ExactBindingConflict("approval has expired")
        return row


class PostgresDeliveryApprovalPort:
    """Scope-explicit DeliveryGate adapter over the bound approval owner."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.scope = scope
        self.repository = ApprovalRepository(connection, scope)

    def require_current(
        self,
        scope: object,
        approval_id: str,
        *,
        run_id: str,
        step_id: str,
        payload_digest: str,
        authority_digest: str,
        now: datetime,
    ) -> DeliveryApprovalSnapshot:
        if scope != self.scope:
            raise ExactBindingConflict("delivery approval scope drift")
        row = self.repository.require_current(
            approval_id,
            run_id=run_id,
            step_id=step_id,
            payload_digest=payload_digest,
            authority_digest=authority_digest,
            now=now,
        )
        expires_at = row["expires_at"]
        if not isinstance(expires_at, datetime):
            raise ExactBindingConflict("delivery approval expiry is malformed")
        return DeliveryApprovalSnapshot(
            approval_id=str(row["approval_id"]),
            revision=int(row["revision"]),
            actor_id=str(row["actor_id"]),
            run_id=str(row["run_id"]),
            step_id=str(row["step_id"]),
            payload_digest=str(row["payload_digest"]),
            authority_digest=str(row["authority_digest"]),
            expires_at=expires_at,
        )

__all__ = [
    "ApprovalBinding",
    "ApprovalRepository",
    "PostgresDeliveryApprovalPort",
]
