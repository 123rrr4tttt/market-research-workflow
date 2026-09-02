"""PostgreSQL runtime-journal projector with atomic offset ownership.

Both the materialized read-model write and its offset execute on the supplied
connection.  The projector never updates runtime runs, steps, attempts, work
items, approvals, or canonical research facts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    RuntimeReplayError,
    RuntimeReplayProjection,
    projection_digest,
    replay_runtime_events,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _mapping_rows,
    _one_mapping,
    _scope_key,
    _table,
    _utcnow,
)


class RuntimeProjectionError(ExactBindingConflict):
    """Projection source/read-model/offset closure is not exact."""


class ProjectionFailpoint(Protocol):
    def __call__(self, point: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeJournalSource:
    run_id: str
    run_incarnation: str
    source_ref: str
    source_kind: str = "runtime_journal"

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_incarnation:
            raise ValueError("runtime projection source identity is incomplete")
        if self.source_ref != f"runtime-run:{self.run_id}":
            raise ValueError("runtime projection source_ref does not bind run_id")


class PostgresRuntimeRunProjector:
    projector_id = "successor-runtime-run-projector"
    # v1.1 binds the real first-specimen CompileSucceeded/StepActivated stream
    # and strict activation/attempt replay semantics.  Reusing v1.0 offsets
    # would silently reinterpret an older projection shape.
    projector_version = "1.1.0"
    source_kind = "runtime_journal"

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        failpoint: ProjectionFailpoint | None = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        self._offsets = ProjectionOffsetRepository(connection, scope)
        self._failpoint = failpoint or _no_failpoint

    def apply(self, source: RuntimeJournalSource) -> Mapping[str, object]:
        """Project every committed event after the exact durable offset."""

        key = self._key(source)
        self._require_source_identity(source)
        offset = self._offsets.load_source(key, for_update=True)
        current_row = self._load_projection(source, for_update=True)
        current = self._decode_current(source, offset, current_row)
        if current is not None:
            try:
                prefix = replay_runtime_events(
                    self._load_events(source, after_seq=0, through_seq=current.last_seq)
                )
            except RuntimeReplayError as exc:
                raise RuntimeProjectionError(
                    "projected runtime journal prefix failed replay"
                ) from exc
            if prefix != current:
                raise RuntimeProjectionError(
                    "projected runtime journal prefix digest/state drift"
                )
        after_seq = 0 if current is None else current.last_seq
        events = self._load_events(source, after_seq=after_seq)
        if not events:
            if current_row is None:
                raise RuntimeProjectionError(
                    "runtime journal has no projectable events"
                )
            return current_row
        try:
            projected = replay_runtime_events(events, initial=current)
        except RuntimeReplayError as exc:
            raise RuntimeProjectionError(
                "runtime journal replay failed closed"
            ) from exc
        generation = 0 if offset is None else int(offset["projection_generation"])
        written = self._write_projection(
            source,
            projected,
            current_row=current_row,
            generation=generation,
        )
        self._failpoint("after_projection_write_before_offset")
        self._write_offset(source, key, projected, offset, generation=generation)
        return written

    def rebuild(self, source: RuntimeJournalSource) -> Mapping[str, object]:
        """Delete and replay the read model inside the caller's one UoW."""

        key = self._key(source)
        self._require_source_identity(source)
        offset = self._offsets.load_source(key, for_update=True)
        current_row = self._load_projection(source, for_update=True)
        self._decode_current(source, offset, current_row)
        generation = 0 if offset is None else int(offset["projection_generation"]) + 1
        if current_row is not None:
            self._delete_projection_row(source, current_row)
        if offset is not None:
            self._offsets.delete_source(
                key,
                expected_revision=int(offset["revision"]),
                expected_generation=int(offset["projection_generation"]),
            )
        events = self._load_events(source, after_seq=0)
        try:
            projected = replay_runtime_events(events)
        except RuntimeReplayError as exc:
            raise RuntimeProjectionError(
                "runtime journal rebuild failed closed"
            ) from exc
        written = self._write_projection(
            source,
            projected,
            current_row=None,
            generation=generation,
        )
        self._failpoint("after_projection_write_before_offset")
        self._write_offset(source, key, projected, None, generation=generation)
        return written

    def load(self, source: RuntimeJournalSource) -> Mapping[str, object]:
        row = self._load_projection(source, for_update=False)
        if row is None:
            raise RecordNotFound(f"runtime projection not found: {source.source_ref}")
        offset = self._offsets.load_source(self._key(source))
        self._decode_current(source, offset, row)
        return row

    def _key(self, source: RuntimeJournalSource) -> ProjectionOffsetKey:
        if source.source_kind != self.source_kind:
            raise RuntimeProjectionError("projector source kind mismatch")
        return ProjectionOffsetKey(
            projector_id=self.projector_id,
            projector_version=self.projector_version,
            source_kind=source.source_kind,
            source_ref=source.source_ref,
            source_incarnation=source.run_incarnation,
        )

    def _require_source_identity(self, source: RuntimeJournalSource) -> None:
        runs = _table("runtime_runs")
        row = _one_mapping(
            self.connection.execute(
                select(
                    runs.c.project_key,
                    runs.c.run_id,
                    runs.c.incarnation,
                ).where(
                    runs.c.project_key == _scope_key(self.scope),
                    runs.c.run_id == source.run_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound(
                f"runtime projection source not found: {source.run_id}"
            )
        if row["incarnation"] != source.run_incarnation:
            raise RuntimeProjectionError(
                "runtime projection source incarnation is stale"
            )

    def _load_events(
        self,
        source: RuntimeJournalSource,
        *,
        after_seq: int,
        through_seq: int | None = None,
    ) -> tuple[ReplayEvent, ...]:
        table = _table("runtime_events")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.run_id == source.run_id,
            table.c.seq > after_seq,
        )
        if through_seq is not None:
            statement = statement.where(table.c.seq <= through_seq)
        rows = _mapping_rows(self.connection.execute(statement.order_by(table.c.seq)))
        return tuple(
            ReplayEvent.from_content(
                project_key=str(row["project_key"]),
                run_id=str(row["run_id"]),
                run_incarnation=source.run_incarnation,
                seq=int(row["seq"]),
                event_type=str(row["event_type"]),
                schema_version=str(row["schema_version"]),
                step_id=None if row["step_id"] is None else str(row["step_id"]),
                attempt_id=(
                    None if row["attempt_id"] is None else str(row["attempt_id"])
                ),
                metadata=dict(row["event_metadata_json"]),
                payload_ref=(
                    None if row["payload_ref"] is None else str(row["payload_ref"])
                ),
                payload_digest=(
                    None
                    if row["payload_digest"] is None
                    else str(row["payload_digest"])
                ),
                authority_digest=str(row["authority_digest"]),
            )
            for row in rows
        )

    def _load_projection(
        self, source: RuntimeJournalSource, *, for_update: bool
    ) -> Mapping[str, object] | None:
        table = _table("runtime_run_projections")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.projector_id == self.projector_id,
            table.c.projector_version == self.projector_version,
            table.c.source_ref == source.source_ref,
            table.c.source_incarnation == source.run_incarnation,
            table.c.run_id == source.run_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return _one_mapping(self.connection.execute(statement))

    def _decode_current(
        self,
        source: RuntimeJournalSource,
        offset: Mapping[str, object] | None,
        row: Mapping[str, object] | None,
    ) -> RuntimeReplayProjection | None:
        if (offset is None) != (row is None):
            raise RuntimeProjectionError(
                "projection materialization and offset must exist together"
            )
        if row is None or offset is None:
            return None
        for name, expected in (
            ("project_key", _scope_key(self.scope)),
            ("projector_id", self.projector_id),
            ("projector_version", self.projector_version),
            ("source_ref", source.source_ref),
            ("source_incarnation", source.run_incarnation),
            ("run_id", source.run_id),
        ):
            if row[name] != expected:
                raise RuntimeProjectionError(f"projection {name} binding drift")
        if (
            row["projection_generation"] != offset["projection_generation"]
            or row["source_revision"] != offset["source_revision"]
            or row["source_digest"] != offset["source_digest"]
        ):
            raise RuntimeProjectionError("projection and offset closure drift")
        state = row["state_json"]
        if not isinstance(state, Mapping):
            raise RuntimeProjectionError("projection state_json is not an object")
        try:
            decoded = RuntimeReplayProjection.from_json(state)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeProjectionError("projection state_json is invalid") from exc
        digest = projection_digest(decoded)
        if row["projection_digest"] != digest:
            raise RuntimeProjectionError("projection state digest mismatch")
        if (
            decoded.last_seq != int(row["source_revision"])
            or decoded.event_chain_digest != row["source_digest"]
            or decoded.project_key != _scope_key(self.scope)
            or decoded.run_id != source.run_id
            or decoded.run_incarnation != source.run_incarnation
        ):
            raise RuntimeProjectionError("projection state/source binding drift")
        return decoded

    def _write_projection(
        self,
        source: RuntimeJournalSource,
        projection: RuntimeReplayProjection,
        *,
        current_row: Mapping[str, object] | None,
        generation: int,
    ) -> Mapping[str, object]:
        table = _table("runtime_run_projections")
        now = _utcnow()
        values = {
            "projection_generation": generation,
            "source_revision": projection.last_seq,
            "source_digest": projection.event_chain_digest,
            "state_json": projection.to_json(),
            "projection_digest": projection_digest(projection),
            "updated_at": now,
        }
        if current_row is None:
            self.connection.execute(
                insert(table).values(
                    project_key=_scope_key(self.scope),
                    projector_id=self.projector_id,
                    projector_version=self.projector_version,
                    source_ref=source.source_ref,
                    source_incarnation=source.run_incarnation,
                    run_id=source.run_id,
                    revision=0,
                    created_at=now,
                    **values,
                )
            )
        else:
            result = self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.projector_id == self.projector_id,
                    table.c.projector_version == self.projector_version,
                    table.c.source_ref == source.source_ref,
                    table.c.source_incarnation == source.run_incarnation,
                    table.c.run_id == source.run_id,
                    table.c.projection_generation == generation,
                    table.c.source_revision == current_row["source_revision"],
                    table.c.source_digest == current_row["source_digest"],
                    table.c.revision == current_row["revision"],
                )
                .values(revision=int(current_row["revision"]) + 1, **values)
            )
            if getattr(result, "rowcount", None) != 1:
                raise StaleRevisionError("runtime projection exact CAS failed")
        row = self._load_projection(source, for_update=False)
        assert row is not None
        return row

    def _write_offset(
        self,
        source: RuntimeJournalSource,
        key: ProjectionOffsetKey,
        projection: RuntimeReplayProjection,
        offset: Mapping[str, object] | None,
        *,
        generation: int,
    ) -> None:
        offset_ref = f"runtime-event-seq:{projection.last_seq}"
        if offset is None:
            identity_digest = sha256_hex(
                {
                    "schema": "mrw.runtime.projection-offset-identity.v1",
                    "project_key": _scope_key(self.scope),
                    "projector_id": self.projector_id,
                    "projector_version": self.projector_version,
                    "source_ref": source.source_ref,
                    "source_incarnation": source.run_incarnation,
                }
            )
            self._offsets.create(
                projection_offset_id=f"projection-offset:sha256:{identity_digest}",
                key=key,
                projection_generation=generation,
                source_revision=projection.last_seq,
                source_digest=projection.event_chain_digest,
                offset_ref=offset_ref,
            )
            return
        self._offsets.advance(
            str(offset["projection_offset_id"]),
            key=key,
            expected_revision=int(offset["revision"]),
            expected_generation=generation,
            expected_source_revision=int(offset["source_revision"]),
            expected_source_digest=str(offset["source_digest"]),
            source_revision=projection.last_seq,
            source_digest=projection.event_chain_digest,
            offset_ref=offset_ref,
        )

    def _delete_projection_row(
        self, source: RuntimeJournalSource, row: Mapping[str, object]
    ) -> None:
        table = _table("runtime_run_projections")
        result = self.connection.execute(
            delete(table).where(
                table.c.project_key == _scope_key(self.scope),
                table.c.projector_id == self.projector_id,
                table.c.projector_version == self.projector_version,
                table.c.source_ref == source.source_ref,
                table.c.source_incarnation == source.run_incarnation,
                table.c.run_id == source.run_id,
                table.c.projection_generation == row["projection_generation"],
                table.c.revision == row["revision"],
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("runtime projection delete CAS failed")


def _no_failpoint(_point: str) -> None:
    return None


__all__ = [
    "PostgresRuntimeRunProjector",
    "ProjectionFailpoint",
    "RuntimeJournalSource",
    "RuntimeProjectionError",
]
