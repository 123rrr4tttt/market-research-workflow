"""Registry-backed read-only projection query ports (HTTP read facade).

This module is the effect boundary that lets the production-registry HTTP
composition root answer ``projection_snapshot`` queries from real successor
PostgreSQL data instead of the deterministic in-memory facade closure.

Read dispatch is intentionally small and additive:

- Material canonical document projections (``projection.material.search.v2``
  or ``projection.material.graph.v2`` with
  ``source_kind=material.canonical``) are answered through
  :class:`C7ProjectorDriver.read_document` and the deterministic C7 search/
  graph rebuild functions.  Nothing is written and no projection offset is
  advanced; the response is a direct read of the committed canonical document
  with ``read_only/no_postgres_write`` markers.
- Historical C7 projection values stay behind the explicit exact-value
  readback function in ``c7_projector_driver``; this current route never
  reconstructs historical bytes from current canonical material.
- Every other query is delegated to the existing
  :class:`PostgresC9QueryRepository`, which already owns the exact
  offset/value readback contract and fails closed.

No new Manager/Layer is introduced: each read opens one short-lived
connection, binds one ``RuntimeScope`` from the server-resolved query and
reuses the repository/projector adapters owned by the effect layer.
"""

from __future__ import annotations

import hashlib
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
    QueryResult,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.authority import (
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    MATERIAL_CANONICAL_SOURCE_KIND,
    MATERIAL_GRAPH_PROJECTION_ID,
    MATERIAL_GRAPH_PROJECTION_SCHEMA,
    MATERIAL_GRAPH_PROJECTOR_ID,
    MATERIAL_GRAPH_PROJECTOR_VERSION,
    MATERIAL_PROJECTION_VALUE_PREFIX,
    MATERIAL_SEARCH_PROJECTION_ID,
    MATERIAL_SEARCH_PROJECTION_SCHEMA,
    MATERIAL_SEARCH_PROJECTOR_ID,
    MATERIAL_SEARCH_PROJECTOR_VERSION,
    C7ProjectorDriver,
    C7ProjectorUnavailableError,
    rebuild_c7_graph_projection,
    rebuild_c7_search_projection,
)
from app.successor_runtime.substrate.postgres.projection_sources import (
    ProjectionSourceError,
    load_current_material_projection_source,
)
from app.successor_runtime.substrate.postgres.facade_commands import (
    PostgresC9QueryRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
)

__all__ = [
    "ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID",
    "ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION",
    "C7_DIRECT_PROJECTION_SCHEMA",
    "C7_DOCUMENT_SOURCE_PREFIX",
    "EngineBackedProjectionQueryReadPort",
    "MATERIAL_DIRECT_PROJECTION_SCHEMA",
    "MATERIAL_DOCUMENT_SOURCE_PREFIX",
    "PostgresProjectionQueryReadPort",
]

MATERIAL_DOCUMENT_SOURCE_PREFIX = "document:"
MATERIAL_DIRECT_PROJECTION_SCHEMA = "mrw.material.document-projection.v2"
# Import compatibility only; current response bytes use the material identity.
C7_DOCUMENT_SOURCE_PREFIX = MATERIAL_DOCUMENT_SOURCE_PREFIX
C7_DIRECT_PROJECTION_SCHEMA = MATERIAL_DIRECT_PROJECTION_SCHEMA
ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID = "projection.project-material.v2"
ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION = "2.0.0"

_MATERIAL_PROJECTOR_ROUTES: dict[
    str,
    tuple[str, str, str, str, Callable[[Any], Any]],
] = {
    MATERIAL_SEARCH_PROJECTOR_ID: (
        "search",
        MATERIAL_SEARCH_PROJECTOR_VERSION,
        MATERIAL_SEARCH_PROJECTION_ID,
        MATERIAL_SEARCH_PROJECTION_SCHEMA,
        rebuild_c7_search_projection,
    ),
    MATERIAL_GRAPH_PROJECTOR_ID: (
        "graph",
        MATERIAL_GRAPH_PROJECTOR_VERSION,
        MATERIAL_GRAPH_PROJECTION_ID,
        MATERIAL_GRAPH_PROJECTION_SCHEMA,
        rebuild_c7_graph_projection,
    ),
}


def _object_id_from_source_ref(source_ref: str) -> str:
    """Extract the canonical document object id from the wire source ref."""

    value = str(source_ref or "").strip()
    if not value:
        raise C9Unavailable(
            "material projection snapshot query requires a non-empty source_ref"
        )
    if value.startswith(MATERIAL_DOCUMENT_SOURCE_PREFIX):
        value = value[len(MATERIAL_DOCUMENT_SOURCE_PREFIX) :].strip()
    if not value:
        raise C9Unavailable(
            "material projection snapshot source_ref does not name a document"
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
        if projector_id == ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID:
            return self._read_active_project_material(query, params)
        if projector_id in _MATERIAL_PROJECTOR_ROUTES:
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
                "project scope binding is stale or absent for the projection read"
            ) from exc

    def _read_active_project_material(
        self,
        query: FacadeQueryV2,
        params: dict[str, Any],
    ) -> QueryResult:
        """Resolve one logical active-material selector to exact persisted facts."""

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
                "active project material read supports projection_snapshot only"
            )
        project_key = self.scope.project_scope.project_key
        expected_selector = {
            "projection_id": ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            "projector_version": ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION,
            "source_kind": "material",
            "source_ref": f"material:{project_key}",
            "source_incarnation": f"active-project:{project_key}",
        }
        for field, expected in expected_selector.items():
            if params.get(field) != expected:
                raise C9Unavailable(
                    "active project material selector does not match the current "
                    f"project: {field}"
                )
        try:
            resolved = load_current_material_projection_source(
                self.connection,
                self.scope,
            )
        except ProjectionSourceError as exc:
            raise C9Unavailable(
                f"active project material source is unavailable: {exc}"
            ) from exc

        position = {
            "projection_generation": resolved.projection_generation,
            "offset_revision": resolved.offset_revision,
            "projection_revision": resolved.source_revision,
            "cursor": resolved.source_revision,
        }
        meta = ProjectionResponseMetaV2(
            project_key=query.meta.project_key,
            trace_id=query.meta.trace_id,
            projection_id=ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            project_scope_ref=self.scope.project_scope,
            projector_id=resolved.projector_id,
            projector_version=resolved.projector_version,
            source_kind=resolved.source_kind,
            source_ref=resolved.source_ref,
            source_incarnation=resolved.source_incarnation,
            source_digest=resolved.source_digest,
            **position,
        )
        candidate = ProjectionCandidateValueV2(
            value_id=resolved.material_value_id,
            value_ref=resolved.material_value_ref,
            content_digest=resolved.material_content_digest,
            byte_size=resolved.material_byte_size,
            sink="material",
            payload=resolved.material_source.to_plain(),
        )
        data = ProjectionSnapshotDataV2(
            projection_id=ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            projector_id=resolved.projector_id,
            projector_version=resolved.projector_version,
            source_kind=resolved.source_kind,
            source_ref=resolved.source_ref,
            source_incarnation=resolved.source_incarnation,
            offset_ref=resolved.offset_ref,
            source_digest=resolved.source_digest,
            candidate_values=(candidate,),
            **position,
        )
        return QueryResult(data=data, meta=meta)

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
                "material projection read supports projection_snapshot only"
            )
        if params.get("source_kind") != MATERIAL_CANONICAL_SOURCE_KIND:
            raise C9Unavailable(
                "material projection snapshot requires "
                f"source_kind={MATERIAL_CANONICAL_SOURCE_KIND}"
            )
        route = _MATERIAL_PROJECTOR_ROUTES.get(params.get("projector_id"))
        if route is None:
            raise C9Unavailable(
                "material projection projector id is not registered"
            )
        (
            projection_kind,
            projector_version,
            expected_projection_id,
            projection_schema,
            rebuild,
        ) = route
        requested_version = params.get("projector_version")
        if requested_version != projector_version:
            raise C9Unavailable(
                "material projection projector_version does not match the registered "
                f"version {projector_version}"
            )
        projection_id = params.get("projection_id")
        if projection_id != expected_projection_id:
            raise C9Unavailable(
                "material projection_id does not match the registered projector"
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
                "material projection source_incarnation does not match the committed "
                "document incarnation"
            )
        projected = rebuild(document_ref)
        canonical_source_ref = (
            f"{MATERIAL_DOCUMENT_SOURCE_PREFIX}{document_ref.object_id}"
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
            source_kind=MATERIAL_CANONICAL_SOURCE_KIND,
            source_ref=canonical_source_ref,
            source_incarnation=document_ref.incarnation,
            source_digest=document_ref.content_digest,
            **position,
        )
        payload = {
            "schema_version": projection_schema,
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
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        value_id = (
            f"{MATERIAL_PROJECTION_VALUE_PREFIX}:{projection_kind}:"
            f"{document_ref.object_id}:rev-{document_ref.revision}:"
            f"{payload_digest[:12]}"
        )
        candidate = ProjectionCandidateValueV2(
            value_id=value_id,
            value_ref=(
                "value:"
                f"{self.scope.project_scope.resolved_schema}:{value_id}"
            ),
            content_digest=payload_digest,
            byte_size=len(payload_bytes),
            sink=projection_kind,
            payload=payload,
        )
        data = ProjectionSnapshotDataV2(
            projection_id=str(projection_id),
            projector_id=str(params["projector_id"]),
            projector_version=projector_version,
            source_kind=MATERIAL_CANONICAL_SOURCE_KIND,
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
