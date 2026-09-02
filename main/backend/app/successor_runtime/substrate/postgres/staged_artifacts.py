"""CAS repository for non-canonical staged artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import insert, select, update
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

StagedArtifactState = Literal["STAGED", "VERIFIED", "ADMITTED", "REJECTED", "ORPHANED"]


@dataclass(frozen=True, slots=True)
class StagedArtifactBinding:
    artifact_id: str
    run_id: str
    step_id: str
    value_id: str
    qualifier_ref: str
    attempt_id: str | None = None
    receipt_ref: str | None = None
    loss_profile_ref: str | None = None

    def __post_init__(self) -> None:
        if not all(
            (
                self.artifact_id,
                self.run_id,
                self.step_id,
                self.value_id,
                self.qualifier_ref,
            )
        ):
            raise ValueError("staged artifact exact binding is incomplete")

    def values(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
            "value_id": self.value_id,
            "receipt_ref": self.receipt_ref,
            "qualifier_ref": self.qualifier_ref,
            "loss_profile_ref": self.loss_profile_ref,
        }


class StagedArtifactRepository:
    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def stage(self, binding: StagedArtifactBinding) -> Mapping[str, object]:
        table = _table("runtime_staged_artifacts")
        current = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.artifact_id == binding.artifact_id,
                )
            )
        )
        values = _project_values(self.scope, binding.values())
        if current is not None:
            if current["state"] != "STAGED" or any(
                current[field] != expected for field, expected in values.items()
            ):
                raise ExactBindingConflict("staged artifact identity was rebound")
            return current
        now = _utcnow()
        self.connection.execute(
            insert(table).values(
                **values,
                state="STAGED",
                revision=0,
                created_at=now,
                updated_at=now,
            )
        )
        return self.load(binding.artifact_id)

    def load(
        self, artifact_id: str, *, for_update: bool = False
    ) -> Mapping[str, object]:
        table = _table("runtime_staged_artifacts")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.artifact_id == artifact_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"staged artifact not found: {artifact_id}")
        return row

    def transition(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        expected_state: StagedArtifactState,
        target_state: StagedArtifactState,
        receipt_ref: str | None = None,
    ) -> Mapping[str, object]:
        allowed = {
            ("STAGED", "VERIFIED"),
            ("STAGED", "REJECTED"),
            ("STAGED", "ORPHANED"),
            ("VERIFIED", "ADMITTED"),
            ("VERIFIED", "REJECTED"),
            ("VERIFIED", "ORPHANED"),
        }
        if (expected_state, target_state) not in allowed:
            raise ValueError("invalid staged artifact lifecycle transition")
        table = _table("runtime_staged_artifacts")
        values: dict[str, object] = {
            "state": target_state,
            "revision": expected_revision + 1,
            "updated_at": _utcnow(),
        }
        if receipt_ref is not None:
            values["receipt_ref"] = receipt_ref
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.artifact_id == artifact_id,
                table.c.state == expected_state,
                table.c.revision == expected_revision,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("staged artifact lifecycle CAS failed")
        return self.load(artifact_id)


__all__ = ["StagedArtifactBinding", "StagedArtifactRepository", "StagedArtifactState"]
