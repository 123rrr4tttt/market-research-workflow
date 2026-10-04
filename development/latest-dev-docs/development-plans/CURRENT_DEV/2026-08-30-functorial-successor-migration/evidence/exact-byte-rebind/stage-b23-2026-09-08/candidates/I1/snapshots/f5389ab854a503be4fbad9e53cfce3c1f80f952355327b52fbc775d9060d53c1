"""Exact CAS repository for rebuildable, source-bound projection offsets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.language.checksum import is_sha256_hex
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
class ProjectionOffsetKey:
    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.projector_id,
                self.projector_version,
                self.source_kind,
                self.source_ref,
                self.source_incarnation,
            )
        ):
            raise ValueError("projection source identity is incomplete")


class ProjectionOffsetRepository:
    """Own offsets only; a projector owns projection-write ordering."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection, self.scope = connection, scope

    def create(
        self,
        *,
        projection_offset_id: str,
        key: ProjectionOffsetKey,
        projection_generation: int,
        source_revision: int,
        source_digest: str,
        offset_ref: str,
    ) -> Mapping[str, object]:
        _validate_position(projection_generation, source_revision, source_digest)
        table = _table("runtime_projection_offsets")
        now = _utcnow()
        self.connection.execute(
            insert(table).values(
                **_project_values(
                    self.scope,
                    {
                        "projection_offset_id": projection_offset_id,
                        "projector_id": key.projector_id,
                        "projector_version": key.projector_version,
                        "source_kind": key.source_kind,
                        "source_ref": key.source_ref,
                        "source_incarnation": key.source_incarnation,
                        "projection_generation": projection_generation,
                        "source_revision": source_revision,
                        "source_digest": source_digest,
                        "offset_ref": offset_ref,
                        "revision": 0,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            )
        )
        return self.load(projection_offset_id)

    def load(
        self, projection_offset_id: str, *, for_update: bool = False
    ) -> Mapping[str, object]:
        table = _table("runtime_projection_offsets")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.projection_offset_id == projection_offset_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"projection offset not found: {projection_offset_id}")
        return row

    def load_source(
        self, key: ProjectionOffsetKey, *, for_update: bool = False
    ) -> Mapping[str, object] | None:
        table = _table("runtime_projection_offsets")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.projector_id == key.projector_id,
            table.c.projector_version == key.projector_version,
            table.c.source_ref == key.source_ref,
            table.c.source_incarnation == key.source_incarnation,
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is not None and row["source_kind"] != key.source_kind:
            raise ExactBindingConflict("projection source kind was rebound")
        return row

    def advance(
        self,
        projection_offset_id: str,
        *,
        key: ProjectionOffsetKey,
        expected_revision: int,
        expected_generation: int,
        expected_source_revision: int,
        expected_source_digest: str,
        source_revision: int,
        source_digest: str,
        offset_ref: str,
    ) -> Mapping[str, object]:
        _validate_position(expected_generation, source_revision, source_digest)
        if source_revision < expected_source_revision:
            raise StaleRevisionError("projection source revision regressed")
        table = _table("runtime_projection_offsets")
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.projection_offset_id == projection_offset_id,
                table.c.projector_id == key.projector_id,
                table.c.projector_version == key.projector_version,
                table.c.source_kind == key.source_kind,
                table.c.source_ref == key.source_ref,
                table.c.source_incarnation == key.source_incarnation,
                table.c.projection_generation == expected_generation,
                table.c.revision == expected_revision,
                table.c.source_revision == expected_source_revision,
                table.c.source_digest == expected_source_digest,
            )
            .values(
                source_revision=source_revision,
                source_digest=source_digest,
                offset_ref=offset_ref,
                revision=expected_revision + 1,
                updated_at=_utcnow(),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("projection offset exact CAS failed")
        return self.load(projection_offset_id)

    def delete_source(
        self,
        key: ProjectionOffsetKey,
        *,
        expected_revision: int,
        expected_generation: int,
    ) -> None:
        table = _table("runtime_projection_offsets")
        result = self.connection.execute(
            delete(table).where(
                table.c.project_key == _scope_key(self.scope),
                table.c.projector_id == key.projector_id,
                table.c.projector_version == key.projector_version,
                table.c.source_kind == key.source_kind,
                table.c.source_ref == key.source_ref,
                table.c.source_incarnation == key.source_incarnation,
                table.c.projection_generation == expected_generation,
                table.c.revision == expected_revision,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("projection offset delete CAS failed")


def _validate_position(
    projection_generation: int, source_revision: int, source_digest: str
) -> None:
    if projection_generation < 0 or source_revision < 0:
        raise ValueError("projection generation/revision must be non-negative")
    if not is_sha256_hex(source_digest):
        raise ValueError("projection source digest must be canonical SHA-256")


__all__ = ["ProjectionOffsetKey", "ProjectionOffsetRepository"]
