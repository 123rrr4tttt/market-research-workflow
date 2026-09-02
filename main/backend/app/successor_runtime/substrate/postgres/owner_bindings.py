"""Owner-matrix persistence with epoch/incarnation CAS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

from .research_ledger import (
    ProjectCASConflict,
    ProjectRecordNotFound,
    assert_first_slice_owner_binding,
    assert_table_scope,
    one_mapping,
    project_table,
    utcnow,
)


@dataclass(frozen=True, slots=True)
class OwnerBindingRecord:
    object_type: str
    owner_mode: str
    owner_id: str
    owner_epoch: int
    readback_profile_ref: str
    base_incarnation: str
    rollback_evidence_ref: str
    effective_at: datetime
    approval_ref: str
    superseded_at: datetime | None = None


def _record(row: Any) -> OwnerBindingRecord:
    return OwnerBindingRecord(
        object_type=row["object_type"],
        owner_mode=row["owner_mode"],
        owner_id=row["owner_id"],
        owner_epoch=row["owner_epoch"],
        readback_profile_ref=row["readback_profile_ref"],
        base_incarnation=row["base_incarnation"],
        rollback_evidence_ref=row["rollback_evidence_ref"],
        effective_at=row["effective_at"],
        approval_ref=row["approval_ref"],
        superseded_at=row["superseded_at"],
    )


class OwnerBindingRepository:
    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def put_exact(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        binding: OwnerBindingRecord,
        *,
        expected_owner_epoch: int,
        expected_base_incarnation: str,
    ) -> OwnerBindingRecord:
        table = project_table(self.tables, "research_owner_bindings")
        project_key = assert_table_scope(table, scope)
        assert_first_slice_owner_binding(
            binding.object_type,
            binding.owner_mode,
            binding.owner_id,
        )
        current = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.object_type == binding.object_type,
                    table.c.superseded_at.is_(None),
                )
                .order_by(table.c.owner_epoch.desc())
                .limit(1)
            )
        )
        if current is None:
            if expected_owner_epoch != 0 or binding.owner_epoch != 1:
                raise ProjectCASConflict("first owner binding requires epoch 1 from expected 0")
            if binding.base_incarnation != expected_base_incarnation:
                raise ProjectCASConflict("owner base incarnation mismatch")
        else:
            if int(current["owner_epoch"]) != expected_owner_epoch:
                raise ProjectCASConflict("stale owner epoch")
            if current["base_incarnation"] != expected_base_incarnation:
                raise ProjectCASConflict("stale owner base incarnation")
            if binding.owner_epoch != expected_owner_epoch + 1:
                raise ProjectCASConflict("successor owner epoch is not monotone")
            if binding.base_incarnation != expected_base_incarnation:
                raise ProjectCASConflict("successor owner base incarnation drift")
            changed = self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.object_type == binding.object_type,
                    table.c.owner_epoch == expected_owner_epoch,
                    table.c.base_incarnation == expected_base_incarnation,
                    table.c.superseded_at.is_(None),
                )
                .values(superseded_at=binding.effective_at, updated_at=utcnow())
            )
            if changed.rowcount != 1:
                raise ProjectCASConflict("owner binding CAS update affected no row")

        now = utcnow()
        self.connection.execute(
            insert(table).values(
                project_key=project_key,
                object_type=binding.object_type,
                owner_mode=binding.owner_mode,
                owner_id=binding.owner_id,
                owner_epoch=binding.owner_epoch,
                readback_profile_ref=binding.readback_profile_ref,
                base_incarnation=binding.base_incarnation,
                rollback_evidence_ref=binding.rollback_evidence_ref,
                effective_at=binding.effective_at,
                superseded_at=binding.superseded_at,
                approval_ref=binding.approval_ref,
                created_at=now,
                updated_at=now,
            )
        )
        return binding

    def load_current(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        object_type: str,
        *,
        expected_owner_epoch: int,
        expected_base_incarnation: str,
    ) -> OwnerBindingRecord:
        table = project_table(self.tables, "research_owner_bindings")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.object_type == object_type,
                    table.c.owner_epoch == expected_owner_epoch,
                    table.c.base_incarnation == expected_base_incarnation,
                    table.c.superseded_at.is_(None),
                )
            )
        )
        if row is None:
            raise ProjectRecordNotFound(f"active owner binding not found: {object_type}")
        return _record(row)


__all__ = ["OwnerBindingRecord", "OwnerBindingRepository"]
