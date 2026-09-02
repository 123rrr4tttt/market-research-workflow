"""Project/capability/logical-request idempotency repository."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.ports import RuntimeScope

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _project_values,
    _scope_key,
    _table,
    _utcnow,
)


@dataclass(frozen=True, slots=True)
class IdempotencyBinding:
    idempotency_id: str
    capability_id: str
    logical_request_id: str
    operation_kind: str
    request_digest: str
    run_id: str
    state: Literal["STARTED", "TERMINAL", "SUPERSEDED"] = "STARTED"
    terminal_observation_ref: str | None = None

    def values(self) -> dict[str, Any]:
        return {
            "idempotency_id": self.idempotency_id,
            "capability_id": self.capability_id,
            "logical_request_id": self.logical_request_id,
            "operation_kind": self.operation_kind,
            "request_digest": self.request_digest,
            "run_id": self.run_id,
            "state": self.state,
            "terminal_observation_ref": self.terminal_observation_ref,
        }


_EXACT_FIELDS = (
    "idempotency_id",
    "capability_id",
    "logical_request_id",
    "operation_kind",
    "request_digest",
    "run_id",
)


class IdempotencyRepository:
    """Idempotency is never global on a caller-provided bare key."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def reserve(self, binding: IdempotencyBinding) -> Mapping[str, Any]:
        table = _table("runtime_idempotency")
        values = _project_values(self.scope, binding.values())
        now = _utcnow()
        values.update(revision=0, created_at=now, updated_at=now)
        self.connection.execute(
            pg_insert(table)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=(
                    table.c.project_key,
                    table.c.capability_id,
                    table.c.logical_request_id,
                )
            )
        )
        current = self.load(
            binding.capability_id,
            binding.logical_request_id,
            for_update=True,
        )
        for field in _EXACT_FIELDS:
            if current[field] != values[field]:
                raise ExactBindingConflict(
                    "idempotency identity is already bound to a different request"
                )
        return current

    def load(
        self,
        capability_id: str,
        logical_request_id: str,
        *,
        for_update: bool = False,
    ) -> Mapping[str, Any]:
        table = _table("runtime_idempotency")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.capability_id == capability_id,
            table.c.logical_request_id == logical_request_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound("idempotency binding not found")
        return row

    def record_terminal(
        self,
        capability_id: str,
        logical_request_id: str,
        *,
        expected_revision: int,
        terminal_observation_ref: str,
    ) -> Mapping[str, Any]:
        if not terminal_observation_ref:
            raise ValueError("terminal_observation_ref is required")
        table = _table("runtime_idempotency")
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.capability_id == capability_id,
                table.c.logical_request_id == logical_request_id,
                table.c.revision == expected_revision,
                table.c.state == "STARTED",
            )
            .values(
                state="TERMINAL",
                terminal_observation_ref=terminal_observation_ref,
                revision=expected_revision + 1,
                updated_at=_utcnow(),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("idempotency terminal CAS failed")
        return self.load(capability_id, logical_request_id)


__all__ = ["IdempotencyBinding", "IdempotencyRepository"]
