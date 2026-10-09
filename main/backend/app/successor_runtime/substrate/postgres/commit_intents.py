"""Crash-safe canonical commit-intent repository."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from app.successor_runtime.runtime.ports import RuntimeScope

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    one_mapping,
    project_values,
    runtime_scope_key,
    runtime_table,
    utc_now,
)


class CommitIntentStatus(StrEnum):
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    UNKNOWN = "OUTCOME_UNKNOWN"


@dataclass(frozen=True, slots=True)
class CommitIntentBinding:
    commit_intent_id: str
    run_id: str
    step_id: str
    capability_id: str
    canonical_owner_ref: str
    object_identity_ref: str
    expected_base_revision: int
    expected_base_incarnation: str
    content_digest: str
    event_digest: str
    verification_digest: str
    authority_digest: str
    idempotency_key: str

    def values(self) -> dict[str, Any]:
        return dict((name, getattr(self, name)) for name in self.__dataclass_fields__)


_BINDING_FIELDS = tuple(CommitIntentBinding.__dataclass_fields__)


class CommitIntentRepository:
    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection, self.scope = connection, scope

    def prepare(self, binding: CommitIntentBinding) -> RowMapping:
        table = runtime_table("runtime_commit_intents")
        # Lock by scoped idempotency identity before deciding whether a new exact
        # binding may be inserted. The DB unique constraint is the final guard.
        existing = one_mapping(self.connection.execute(select(table).where(
            table.c.project_key == runtime_scope_key(self.scope),
            table.c.capability_id == binding.capability_id,
            table.c.idempotency_key == binding.idempotency_key,
        ).with_for_update()))
        if existing is not None:
            if any(existing[field] != getattr(binding, field) for field in _BINDING_FIELDS):
                raise ExactBindingConflict("commit idempotency key has a different exact binding")
            return existing
        now = utc_now()
        values = project_values(self.scope, binding.values())
        values.update(state=CommitIntentStatus.PREPARED.value, revision=0, canonical_commit_ref=None, receipt_digest=None, created_at=now, updated_at=now)
        self.connection.execute(insert(table).values(**values))
        return self.load(binding.commit_intent_id)

    def load(self, commit_intent_id: str, *, for_update: bool = False) -> RowMapping:
        table = runtime_table("runtime_commit_intents")
        statement = select(table).where(table.c.project_key == runtime_scope_key(self.scope), table.c.commit_intent_id == commit_intent_id)
        if for_update:
            statement = statement.with_for_update()
        row = one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"commit intent not found: {commit_intent_id}")
        return row

    def record_result(self, commit_intent_id: str, *, expected_revision: int, status: CommitIntentStatus, canonical_commit_ref: str | None = None, receipt_digest: str | None = None) -> RowMapping:
        if status is CommitIntentStatus.PREPARED:
            raise ValueError("record_result requires a terminal or unknown status")
        if status is CommitIntentStatus.COMMITTED and (not canonical_commit_ref or not receipt_digest):
            raise ValueError("COMMITTED requires canonical readback ref and receipt digest")
        table = runtime_table("runtime_commit_intents")
        result = self.connection.execute(update(table).where(
            table.c.project_key == runtime_scope_key(self.scope), table.c.commit_intent_id == commit_intent_id,
            table.c.revision == expected_revision, table.c.state.in_((CommitIntentStatus.PREPARED.value, CommitIntentStatus.UNKNOWN.value)),
        ).values(state=status.value, revision=expected_revision + 1, canonical_commit_ref=canonical_commit_ref, receipt_digest=receipt_digest, updated_at=utc_now()))
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("commit intent result CAS failed")
        return self.load(commit_intent_id)

    def find_for_readback(self, capability_id: str, idempotency_key: str) -> RowMapping:
        table = runtime_table("runtime_commit_intents")
        row = one_mapping(self.connection.execute(select(table).where(
            table.c.project_key == runtime_scope_key(self.scope), table.c.capability_id == capability_id,
            table.c.idempotency_key == idempotency_key,
        )))
        if row is None:
            raise RecordNotFound("commit intent readback binding not found")
        return row


__all__ = ["CommitIntentBinding", "CommitIntentRepository", "CommitIntentStatus"]
