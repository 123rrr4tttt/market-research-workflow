"""Opaque public index for exact project/runtime values.

The index never stores value bytes.  It binds a content digest to exactly one
opaque location and advances through a small CAS lifecycle.  Project value
bytes remain owned by the project-scoped ``successor_values`` repository.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import require_digest
from app.successor_runtime.runtime.ports import RuntimeScope

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _project_values,
    _require_opaque_locator,
    _scope_key,
    _table,
    _utcnow,
)

RuntimeValueState = Literal["PREPARED", "AVAILABLE", "FAILED", "ORPHANED"]


@dataclass(frozen=True, slots=True)
class RuntimeValueBinding:
    value_id: str
    object_type: str
    codec_id: str
    content_digest: str
    byte_size: int
    storage_digest: str
    project_value_ref: str | None = None
    runtime_blob_ref: str | None = None
    canonical_ref: str | None = None
    temporary_storage_ref: str | None = None
    final_storage_ref: str | None = None
    write_intent_digest: str | None = None
    write_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.value_id or not self.object_type or not self.codec_id:
            raise ValueError("runtime value identity is incomplete")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.storage_digest, "storage_digest")
        if self.byte_size < 0:
            raise ValueError("byte_size must be non-negative")
        refs = (self.project_value_ref, self.runtime_blob_ref, self.canonical_ref)
        if sum(ref is not None for ref in refs) != 1:
            raise ValueError("runtime value requires exactly one opaque owner ref")
        for name, ref in (
            ("project_value_ref", self.project_value_ref),
            ("runtime_blob_ref", self.runtime_blob_ref),
            ("canonical_ref", self.canonical_ref),
        ):
            if ref is not None:
                _require_opaque_locator(ref, path=name)
        for name, digest in (
            ("write_intent_digest", self.write_intent_digest),
            ("write_receipt_digest", self.write_receipt_digest),
        ):
            if digest is not None:
                require_digest(digest, name)

    def values(self) -> dict[str, object]:
        return {
            "value_id": self.value_id,
            "object_type": self.object_type,
            "codec_id": self.codec_id,
            "content_digest": self.content_digest,
            "byte_size": self.byte_size,
            "project_value_ref": self.project_value_ref,
            "runtime_blob_ref": self.runtime_blob_ref,
            "canonical_ref": self.canonical_ref,
            "storage_digest": self.storage_digest,
            "temporary_storage_ref": self.temporary_storage_ref,
            "final_storage_ref": self.final_storage_ref,
            "write_intent_digest": self.write_intent_digest,
            "write_receipt_digest": self.write_receipt_digest,
        }


class RuntimeValueRepository:
    """Absent-or-exact public value-ref index enlisted in the caller UoW."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def put_exact(
        self,
        binding: RuntimeValueBinding,
        *,
        state: RuntimeValueState = "AVAILABLE",
    ) -> Mapping[str, object]:
        if state not in {"PREPARED", "AVAILABLE", "FAILED", "ORPHANED"}:
            raise ValueError("invalid runtime value state")
        table = _table("runtime_values")
        by_id = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.value_id == binding.value_id,
                )
            )
        )
        by_content = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.content_digest == binding.content_digest,
                    table.c.codec_id == binding.codec_id,
                )
            )
        )
        expected = _project_values(
            self.scope,
            {**binding.values(), "state": state},
        )
        exact_fields = tuple(binding.values()) + ("state",)
        for row in (by_id, by_content):
            if row is None:
                continue
            if row["value_id"] != binding.value_id or any(
                row[field] != expected[field] for field in exact_fields
            ):
                raise ExactBindingConflict(
                    "runtime value identity/content has a different exact ref binding"
                )
        if by_id is None:
            now = _utcnow()
            self.connection.execute(
                insert(table).values(
                    **expected,
                    revision=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.load_exact(binding)

    def load_exact(self, binding: RuntimeValueBinding) -> Mapping[str, object]:
        table = _table("runtime_values")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.value_id == binding.value_id,
                    table.c.content_digest == binding.content_digest,
                    table.c.codec_id == binding.codec_id,
                    table.c.storage_digest == binding.storage_digest,
                )
            )
        )
        if row is None:
            raise RecordNotFound(f"exact runtime value not found: {binding.value_id}")
        for field, expected in binding.values().items():
            if row[field] != expected:
                raise ExactBindingConflict(f"runtime value ref drift: {field}")
        return row

    def transition(
        self,
        value_id: str,
        *,
        expected_revision: int,
        expected_state: RuntimeValueState,
        target_state: RuntimeValueState,
        write_receipt_digest: str | None = None,
    ) -> Mapping[str, object]:
        allowed = {
            ("PREPARED", "AVAILABLE"),
            ("PREPARED", "FAILED"),
            ("PREPARED", "ORPHANED"),
            ("FAILED", "ORPHANED"),
        }
        if (expected_state, target_state) not in allowed:
            raise ValueError("invalid runtime value lifecycle transition")
        if write_receipt_digest is not None:
            require_digest(write_receipt_digest, "write_receipt_digest")
        table = _table("runtime_values")
        values: dict[str, object] = {
            "state": target_state,
            "revision": expected_revision + 1,
            "updated_at": _utcnow(),
        }
        if write_receipt_digest is not None:
            values["write_receipt_digest"] = write_receipt_digest
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.value_id == value_id,
                table.c.state == expected_state,
                table.c.revision == expected_revision,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("runtime value lifecycle CAS failed")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.value_id == value_id,
                )
            )
        )
        assert row is not None
        return row


__all__ = ["RuntimeValueBinding", "RuntimeValueRepository", "RuntimeValueState"]
