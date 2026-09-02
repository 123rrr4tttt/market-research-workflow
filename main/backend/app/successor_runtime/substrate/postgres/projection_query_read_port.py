"""Registry-backed read-only projection query ports (HTTP read facade).

This module is the effect boundary that lets the production-registry HTTP
composition root answer ``projection_snapshot`` queries from real successor
PostgreSQL data instead of the deterministic in-memory facade closure.

Read dispatch is intentionally small and additive:

- C7 canonical document projections (``successor.ingest_index.search.projector``
  or ``successor.ingest_index.graph.projector`` with
  ``source_kind=ingest_canonical``) are answered through
  :class:`C7ProjectorDriver.read_document` and the deterministic C7 search/
  graph rebuild functions.  Nothing is written and no projection offset is
  advanced; the response is a direct read of the committed canonical document
  with ``read_only/no_postgres_write`` markers.
- Every other query is delegated to the existing
  :class:`PostgresC9QueryRepository`, which already owns the exact
  offset/value readback contract and fails closed.

No new Manager/Layer is introduced: each read opens one short-lived
connection, binds one ``RuntimeScope`` from the server-resolved query and
reuses the repository/projector adapters owned by the effect layer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.engine import Connection, Engine

from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.facade_contracts import (
    C9CommandBlocked,
    C9Unavailable,
    FacadeQueryV2,
    ProjectionCandidateValueV2,
    ProjectionResponseMetaV2,
    ProjectionSnapshotDataV2,
    QueryReadPort,
    QueryResult,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.authority import (
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    C7ProjectorDriver,
    C7_CANONICAL_SOURCE_KIND,
    C7_GRAPH_PROJECTOR_ID,
    C7_GRAPH_PROJECTOR_VERSION,
    C7_SEARCH_PROJECTOR_ID,
    C7_SEARCH_PROJECTOR_VERSION,
    C7ProjectorUnavailableError,
    rebuild_c7_graph_projection,
    rebuild_c7_search_projection,
)
from app.successor_runtime.substrate.postgres.facade_commands import (
    PostgresC9QueryRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
)

__all__ = [
    "C7_DIRECT_PROJECTION_SCHEMA",
    "C7_DOCUMENT_SOURCE_PREFIX",
    "EngineBackedProjectionQueryReadPort",
    "PostgresProjectionQueryReadPort",
]

C7_DOCUMENT_SOURCE_PREFIX = "document:"
C7_DIRECT_PROJECTION_SCHEMA = "mrw.successor.c7.document-projection.v1"

_C7_PROJECTOR_ROUTES: dict[str, tuple[str, str, Callable[[Any], Any]]] = {
    C7_SEARCH_PROJECTOR_ID: (
        "search",
        C7_SEARCH_PROJECTOR_VERSION,
        rebuild_c7_search_projection,
    ),
    C7_GRAPH_PROJECTOR_ID: (
        "graph",
        C7_GRAPH_PROJECTOR_VERSION,
        rebuild_c7_graph_projection,
    ),
}


def _object_id_from_source_ref(source_ref: str) -> str:
    """Extract the canonical document object id from the wire source ref."""

    value = str(source_ref or "").strip()
    if not value:
        raise C9Unavailable(
            "C7 projection snapshot query requires a non-empty source_ref"
        )
    if value.startswith(C7_DOCUMENT_SOURCE_PREFIX):
        value = value[len(C7_DOCUMENT_SOURCE_PREFIX) :].strip()
    if not value:
        raise C9Unavailable(
            "C7 projection snapshot source_ref does not name a document"
        )
    return value


class PostgresProjectionQueryReadPort:
    """Read-only projection dispatch over one caller-owned connection."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
    ) -> None:
        self.connection = connection
        self.scope = scope

    def read(self, query: FacadeQueryV2) -> QueryResult:
        params = dict(query.params)
        projector_id = params.get("projector_id")
        if projector_id in _C7_PROJECTOR_ROUTES:
            return self._read_c7_document(query, params)
        return PostgresC9QueryRepository(
            self.connection,
            self.scope,
        ).read(query)

    def _require_current_scope(self) -> None:
        try:
            ProjectScopeRegistryRepository(
                self.connection,
                self.scope,
            ).require_current()
        except (RecordNotFound, ExactBindingConflict) as exc:
            raise C9CommandBlocked(
                "project scope binding is stale or absent for the C7 read"
            ) from exc

    def _read_c7_document(
        self,
        query: FacadeQueryV2,
        params: dict[str, Any],
    ) -> QueryResult:
        if query.project_scope_ref != self.scope.project_scope:
            raise C9CommandBlocked(
                "query scope does not exactly match the repository RuntimeScope"
            )
        if query.actor_ref != self.scope.actor_id:
            raise C9CommandBlocked(
                "query actor does not match the server-resolved actor"
            )
        self._require_current_scope()
        if query.query_kind != "projection_snapshot":
            raise C9Unavailable(
                "C7 projection read supports projection_snapshot only"
            )
        if params.get("source_kind") != C7_CANONICAL_SOURCE_KIND:
            raise C9Unavailable(
                "C7 projection snapshot requires source_kind=ingest_canonical"
            )
        route = _C7_PROJECTOR_ROUTES.get(params.get("projector_id"))
        if route is None:
            raise C9Unavailable(
                "C7 projection projector id is not a registered C7 projector"
            )
        projection_kind, projector_version, rebuild = route
        requested_version = params.get("projector_version")
        if requested_version != projector_version:
            raise C9Unavailable(
                "C7 projection projector_version does not match the registered "
                f"version {projector_version}"
            )
        projection_id = params.get("projection_id")
        if not projection_id:
            raise C9Unavailable(
                "C7 projection snapshot query requires projection_id"
            )
        source_ref = str(params.get("source_ref") or "")
        object_id = _object_id_from_source_ref(source_ref)
        driver = C7ProjectorDriver(self.connection, self.scope)
        try:
            document_ref = driver.read_document(object_id)
        except C7ProjectorUnavailableError as exc:
            raise C9Unavailable(str(exc)) from exc
        requested_incarnation = str(params.get("source_incarnation") or "")
        if (
            requested_incarnation
            and requested_incarnation != document_ref.incarnation
        ):
            raise C9Unavailable(
                "C7 projection source_incarnation does not match the committed "
                "document incarnation"
            )
        projected = rebuild(document_ref)
        canonical_source_ref = (
            f"{C7_DOCUMENT_SOURCE_PREFIX}{document_ref.object_id}"
        )
        position = {
            "projection_generation": document_ref.revision,
            "offset_revision": 0,
            "projection_revision": document_ref.revision,
            "cursor": document_ref.revision,
        }
        meta = ProjectionResponseMetaV2(
            project_key=query.meta.project_key,
            trace_id=query.meta.trace_id,
            projection_id=str(projection_id),
            project_scope_ref=self.scope.project_scope,
            projector_id=str(params["projector_id"]),
            projector_version=projector_version,
            source_kind=C7_CANONICAL_SOURCE_KIND,
            source_ref=canonical_source_ref,
            source_incarnation=document_ref.incarnation,
            source_digest=document_ref.content_digest,
            **position,
        )
        value_id = (
            "c7:document-projection:"
            f"{document_ref.object_id}:rev-{document_ref.revision}"
        )
        payload = {
            "schema_version": C7_DIRECT_PROJECTION_SCHEMA,
            "document_ref": {
                "schema_version": document_ref.schema_version,
                "project_key": document_ref.project_key,
                "object_id": document_ref.object_id,
                "revision": document_ref.revision,
                "incarnation": document_ref.incarnation,
                "content_digest": document_ref.content_digest,
                "canonical_owner": document_ref.canonical_owner,
            },
            "projection_kind": projection_kind,
            "projection_digest": projected.projection_digest,
            "body": dict(projected.body),
            "declared_loss": [tuple(item) for item in projected.declared_loss],
            "read_only": True,
            "no_postgres_write": True,
        }
        payload_bytes = canonical_bytes(payload)
        candidate = ProjectionCandidateValueV2(
            value_id=value_id,
            value_ref=(
                "value:"
                f"{self.scope.project_scope.resolved_schema}:{value_id}"
            ),
            content_digest=document_ref.content_digest,
            byte_size=len(payload_bytes),
            sink=projection_kind,
            payload=payload,
        )
        data = ProjectionSnapshotDataV2(
            projection_id=str(projection_id),
            projector_id=str(params["projector_id"]),
            projector_version=projector_version,
            source_kind=C7_CANONICAL_SOURCE_KIND,
            source_ref=canonical_source_ref,
            source_incarnation=document_ref.incarnation,
            offset_ref=canonical_source_ref,
            source_digest=document_ref.content_digest,
            candidate_values=(candidate,),
            **position,
        )
        return QueryResult(data=data, meta=meta)


class EngineBackedProjectionQueryReadPort:
    """Open one short-lived read-only connection per projection query.

    The port never owns a connection at assembly/import time and never writes.
    It mirrors the connection policy of
    :class:`RegistryBackedProjectScopeResolver` so the HTTP composition root
    stays connection-free until a request actually needs a read.
    """

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        engine_factory: Callable[[], Engine] | None = None,
    ) -> None:
        if (engine is None) == (engine_factory is None):
            raise ValueError(
                "EngineBackedProjectionQueryReadPort requires exactly one of "
                "engine or engine_factory"
            )
        self._engine = engine
        self._engine_factory = engine_factory

    def _connect(self) -> Connection:
        engine = (
            self._engine
            if self._engine is not None
            else self._engine_factory()
        )
        return engine.connect()

    def read(self, query: FacadeQueryV2) -> QueryResult:
        scope = RuntimeScope(
            project_scope=query.project_scope_ref,
            actor_id=query.actor_ref,
        )
        with self._connect() as connection:
            return PostgresProjectionQueryReadPort(
                connection,
                scope,
            ).read(query)
