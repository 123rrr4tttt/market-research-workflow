"""Source-library terminal projection store with offset and delete/rebuild.

The projector materializes the pure C2.4 read models under a caller-owned
transaction.  It never writes runtime events, attempts, receipts, work items
or canonical facts, and it owns only its own projection row and offset.

The in-memory store is the deterministic reference implementation.  The
PostgreSQL store is family-local: it uses one caller-owned table (created by
the test in the disposable ``mrw_p3_c2_worker_test`` database) and never
modifies shared migration/catalog state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_4_projection import (
    SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
    SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
    ProjectedWithLoss,
    ProjectionRejected,
    ProjectionResult,
    ProjectionStale,
    SourceCollectionProjectionSource,
    project_source_collection,
)

__all__ = [
    "InMemorySourceLibraryTerminalProjector",
    "PostgresSourceLibraryTerminalProjector",
    "ProjectionStaleError",
    "ReadRoutingRollback",
    "SourceLibraryProjectionNotFound",
    "SourceLibraryTerminalMaterialization",
    "build_source_library_terminal_table",
    "rollback_read_routing",
]


DEFAULT_PROJECTION_TABLE = "mrw_p3_c2_source_library_terminal"


class ProjectionStaleError(RuntimeError):
    """Projection source revision/incarnation/digest is stale."""


class SourceLibraryProjectionNotFound(KeyError):
    """No materialized source-library terminal projection exists."""


@dataclass(frozen=True, slots=True)
class SourceLibraryTerminalMaterialization:
    source_ref: str
    source_incarnation: str
    source_revision: int
    source_digest: str
    generation: int
    terminal: dict[str, Any]
    compat: dict[str, Any]
    summary: dict[str, Any]
    materialization_digest: str

    def to_plain(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "source_incarnation": self.source_incarnation,
            "source_revision": self.source_revision,
            "source_digest": self.source_digest,
            "generation": self.generation,
            "terminal": self.terminal,
            "compat": self.compat,
            "summary": self.summary,
            "materialization_digest": self.materialization_digest,
        }


@dataclass(frozen=True, slots=True)
class ReadRoutingRollback:
    claim_owner: Literal["legacy"]
    projection_rows_retained: bool
    reason: str
    rollback_digest: str


def rollback_read_routing() -> ReadRoutingRollback:
    """Switch future read routing only; never deletes successor rows/offsets."""

    values = {
        "schema": "mrw.successor.source-library.c2-4.read-routing-rollback.v1",
        "claim_owner": "legacy",
        "projection_rows_retained": True,
        "reason": (
            "future query/read routing returns to legacy; successor journal, "
            "offsets and projections are retained and no provider effect reruns"
        ),
    }
    return ReadRoutingRollback(
        claim_owner="legacy",
        projection_rows_retained=True,
        reason=values["reason"],
        rollback_digest=content_digest(values),
    )


def _project(source: SourceCollectionProjectionSource) -> ProjectedWithLoss:
    result: ProjectionResult = project_source_collection(source)
    if isinstance(result, ProjectionRejected):
        raise ProjectionStaleError(f"{result.code}: {result.message}")
    if isinstance(result, ProjectionStale):
        raise ProjectionStaleError(result.message)
    return result


def _materialization_digest(
    *,
    source_ref: str,
    source_digest: str,
    generation: int,
    projected: ProjectedWithLoss,
) -> str:
    return content_digest(
        {
            "projector_id": SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
            "projector_version": SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
            "source_ref": source_ref,
            "source_digest": source_digest,
            "generation": generation,
            "terminal_digest": projected.terminal.projection_digest,
            "compat_digest": projected.compat.compat_digest,
            "summary_digest": projected.summary.projection_digest,
        }
    )


class InMemorySourceLibraryTerminalProjector:
    """Deterministic reference projector with offset and delete/rebuild."""

    projector_id = SOURCE_LIBRARY_C2_4_PROJECTOR_ID
    projector_version = SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION
    source_kind = "RUNTIME_JOURNAL"

    def __init__(self, *, failpoint: Any = None) -> None:
        self._rows: dict[str, SourceLibraryTerminalMaterialization] = {}
        self._offsets: dict[str, dict[str, Any]] = {}
        self._failpoint = failpoint or (lambda point: None)

    def apply(
        self, source: SourceCollectionProjectionSource
    ) -> SourceLibraryTerminalMaterialization:
        self._require_source(source)
        key = source.source_ref
        offset = self._offsets.get(key)
        if offset is not None and (
            offset["project_key"] != source.project_key
            or offset["source_incarnation"] != source.source_incarnation
            or offset["source_revision"] != source.source_revision
            or offset["source_digest"] != source.source_digest
        ):
            raise ProjectionStaleError(
                "projection source project/revision/incarnation/digest is stale"
            )
        projected = _project(source)
        generation = 0 if offset is None else int(offset["generation"])
        materialization = self._materialize(source, projected, generation)
        self._rows[key] = materialization
        self._failpoint("after_projection_write_before_offset")
        self._offsets[key] = {
            "project_key": source.project_key,
            "source_incarnation": source.source_incarnation,
            "source_revision": source.source_revision,
            "source_digest": source.source_digest,
            "generation": generation,
            "materialization_digest": materialization.materialization_digest,
        }
        return materialization

    def rebuild(
        self, source: SourceCollectionProjectionSource
    ) -> SourceLibraryTerminalMaterialization:
        self._require_source(source)
        key = source.source_ref
        offset = self._offsets.get(key)
        generation = 0 if offset is None else int(offset["generation"]) + 1
        self.delete(source)
        projected = _project(source)
        materialization = self._materialize(source, projected, generation)
        self._rows[key] = materialization
        self._failpoint("after_projection_write_before_offset")
        self._offsets[key] = {
            "project_key": source.project_key,
            "source_incarnation": source.source_incarnation,
            "source_revision": source.source_revision,
            "source_digest": source.source_digest,
            "generation": generation,
            "materialization_digest": materialization.materialization_digest,
        }
        return materialization

    def load(
        self, source: SourceCollectionProjectionSource
    ) -> SourceLibraryTerminalMaterialization:
        self._require_source(source)
        row = self._rows.get(source.source_ref)
        if row is None:
            raise SourceLibraryProjectionNotFound(source.source_ref)
        offset = self._offsets[source.source_ref]
        if (
            offset["project_key"] != source.project_key
            or offset["source_revision"] != source.source_revision
            or offset["source_incarnation"] != source.source_incarnation
            or offset["source_digest"] != source.source_digest
            or offset["source_digest"] != row.source_digest
            or offset["materialization_digest"] != row.materialization_digest
        ):
            raise ProjectionStaleError(
                "projection source or offset drifted from materialization; "
                "rebuild required, stale row never returned"
            )
        return row

    def delete(self, source: SourceCollectionProjectionSource) -> None:
        self._require_source(source)
        self._rows.pop(source.source_ref, None)
        self._offsets.pop(source.source_ref, None)

    def _materialize(
        self,
        source: SourceCollectionProjectionSource,
        projected: ProjectedWithLoss,
        generation: int,
    ) -> SourceLibraryTerminalMaterialization:
        digest = _materialization_digest(
            source_ref=source.source_ref,
            source_digest=source.source_digest,
            generation=generation,
            projected=projected,
        )
        return SourceLibraryTerminalMaterialization(
            source_ref=source.source_ref,
            source_incarnation=source.source_incarnation,
            source_revision=source.source_revision,
            source_digest=source.source_digest,
            generation=generation,
            terminal=projected.terminal.to_plain(),
            compat=projected.compat.to_plain(),
            summary=projected.summary.to_plain(),
            materialization_digest=digest,
        )

    @staticmethod
    def _require_source(source: SourceCollectionProjectionSource) -> None:
        if source.source_kind != "RUNTIME_JOURNAL":
            raise ProjectionStaleError("projector source kind mismatch")


def build_source_library_terminal_table(
    metadata: sa.MetaData,
    *,
    name: str = DEFAULT_PROJECTION_TABLE,
) -> sa.Table:
    return sa.Table(
        name,
        metadata,
        sa.Column("project_key", sa.String(128), primary_key=True),
        sa.Column("source_ref", sa.String(256), primary_key=True),
        sa.Column("source_incarnation", sa.String(128), nullable=False),
        sa.Column("source_revision", sa.Integer, nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
        sa.Column("terminal_json", JSONB, nullable=False),
        sa.Column("compat_json", JSONB, nullable=False),
        sa.Column("summary_json", JSONB, nullable=False),
        sa.Column("materialization_digest", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
    )


class PostgresSourceLibraryTerminalProjector:
    """Family-local PostgreSQL projection store.

    The caller owns the table and the connection/transaction.  The test
    creates the table in the disposable ``mrw_p3_c2_worker_test`` database and
    drops it on teardown; no shared migration or catalog is modified.
    """

    projector_id = SOURCE_LIBRARY_C2_4_PROJECTOR_ID
    projector_version = SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION
    source_kind = "RUNTIME_JOURNAL"

    def __init__(
        self,
        connection: Connection,
        *,
        project_key: str,
        table: sa.Table | None = None,
        create_table: bool = False,
        failpoint: Any = None,
    ) -> None:
        self.connection = connection
        self.project_key = project_key
        if table is None:
            metadata = sa.MetaData()
            table = build_source_library_terminal_table(metadata)
        self.table = table
        if create_table:
            table.create(connection, checkfirst=True)
        self._failpoint = failpoint or (lambda point: None)

    def apply(
        self, source: SourceCollectionProjectionSource
    ) -> SourceLibraryTerminalMaterialization:
        self._require_source(source)
        projected = _project(source)
        row = self._load_row(source, for_update=True)
        if row is not None and (
            row["source_incarnation"] != source.source_incarnation
            or row["source_digest"] != source.source_digest
        ):
            raise ProjectionStaleError(
                "projection source revision/incarnation/digest is stale"
            )
        generation = 0 if row is None else int(row["generation"])
        materialization = self._materialize(source, projected, generation)
        statement = pg_insert(self.table).values(
            project_key=self.project_key,
            source_ref=source.source_ref,
            source_incarnation=source.source_incarnation,
            source_revision=source.source_revision,
            source_digest=source.source_digest,
            generation=generation,
            terminal_json=materialization.terminal,
            compat_json=materialization.compat,
            summary_json=materialization.summary,
            materialization_digest=materialization.materialization_digest,
            updated_at=source.observed_at,
        )
        update_columns = {
            "source_incarnation": statement.excluded.source_incarnation,
            "source_revision": statement.excluded.source_revision,
            "source_digest": statement.excluded.source_digest,
            "generation": statement.excluded.generation,
            "terminal_json": statement.excluded.terminal_json,
            "compat_json": statement.excluded.compat_json,
            "summary_json": statement.excluded.summary_json,
            "materialization_digest": statement.excluded.materialization_digest,
            "updated_at": statement.excluded.updated_at,
        }
        self.connection.execute(
            statement.on_conflict_do_update(
                index_elements=[self.table.c.project_key, self.table.c.source_ref],
                set_=update_columns,
            )
        )
        self._failpoint("after_projection_write_before_offset")
        return materialization

    def rebuild(
        self, source: SourceCollectionProjectionSource
    ) -> SourceLibraryTerminalMaterialization:
        self._require_source(source)
        row = self._load_row(source, for_update=True)
        generation = 0 if row is None else int(row["generation"]) + 1
        self.delete(source)
        projected = _project(source)
        materialization = self._materialize(source, projected, generation)
        self.connection.execute(
            insert(self.table).values(
                project_key=self.project_key,
                source_ref=source.source_ref,
                source_incarnation=source.source_incarnation,
                source_revision=source.source_revision,
                source_digest=source.source_digest,
                generation=generation,
                terminal_json=materialization.terminal,
                compat_json=materialization.compat,
                summary_json=materialization.summary,
                materialization_digest=materialization.materialization_digest,
                updated_at=source.observed_at,
            )
        )
        self._failpoint("after_projection_write_before_offset")
        return materialization

    def load(
        self, source: SourceCollectionProjectionSource
    ) -> SourceLibraryTerminalMaterialization:
        self._require_source(source)
        row = self._load_row(source)
        if row is None:
            raise SourceLibraryProjectionNotFound(source.source_ref)
        if (
            row["source_incarnation"] != source.source_incarnation
            or int(row["source_revision"]) != source.source_revision
            or row["source_digest"] != source.source_digest
        ):
            raise ProjectionStaleError(
                "changed source requires rebuild; stale projection row never returned"
            )
        return self._row_to_materialization(row)

    def delete(self, source: SourceCollectionProjectionSource) -> None:
        self._require_source(source)
        self.connection.execute(
            delete(self.table).where(
                self.table.c.project_key == self.project_key,
                self.table.c.source_ref == source.source_ref,
            )
        )

    def _load_row(
        self, source: SourceCollectionProjectionSource, *, for_update: bool = False
    ) -> Any | None:
        statement = select(self.table).where(
            self.table.c.project_key == self.project_key,
            self.table.c.source_ref == source.source_ref,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.connection.execute(statement).mappings().first()
        return row

    def _materialize(
        self,
        source: SourceCollectionProjectionSource,
        projected: ProjectedWithLoss,
        generation: int,
    ) -> SourceLibraryTerminalMaterialization:
        digest = _materialization_digest(
            source_ref=source.source_ref,
            source_digest=source.source_digest,
            generation=generation,
            projected=projected,
        )
        return SourceLibraryTerminalMaterialization(
            source_ref=source.source_ref,
            source_incarnation=source.source_incarnation,
            source_revision=source.source_revision,
            source_digest=source.source_digest,
            generation=generation,
            terminal=projected.terminal.to_plain(),
            compat=projected.compat.to_plain(),
            summary=projected.summary.to_plain(),
            materialization_digest=digest,
        )

    @staticmethod
    def _row_to_materialization(row: Any) -> SourceLibraryTerminalMaterialization:
        return SourceLibraryTerminalMaterialization(
            source_ref=row["source_ref"],
            source_incarnation=row["source_incarnation"],
            source_revision=int(row["source_revision"]),
            source_digest=row["source_digest"],
            generation=int(row["generation"]),
            terminal=dict(row["terminal_json"]),
            compat=dict(row["compat_json"]),
            summary=dict(row["summary_json"]),
            materialization_digest=row["materialization_digest"],
        )

    def _require_source(self, source: SourceCollectionProjectionSource) -> None:
        if source.source_kind != "RUNTIME_JOURNAL":
            raise ProjectionStaleError("projector source kind mismatch")
        if source.project_key != self.project_key:
            raise ProjectionStaleError("projector project key does not match source")
