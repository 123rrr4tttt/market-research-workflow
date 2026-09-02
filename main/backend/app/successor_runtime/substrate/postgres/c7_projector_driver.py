"""C7.3 successor-only projector driver for the search and graph projections.

The driver reads one canonical document from the successor
``c7_movement_canonical_documents`` table, rebuilds the deterministic
declared-loss search/graph projection from the committed ``DocumentRef``,
persists the projection as an immutable project ``successor_values`` row and
advances the project-scoped ``runtime_projection_offsets`` pointer with an
exact CAS.  Rebuild is deterministic: retrying the same canonical document
reproduces the same value rows and leaves the active offset unchanged.
The driver never reads or writes legacy tables, never calls a provider,
never exports and never claims production canonical authority.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.c7_document_readback import (
    DOCUMENT_CANONICAL_OWNER,
    DocumentRef,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.projections.registry import (
    REBUILD_MODES,
    RebuildMode,
)

__all__ = [
    "C7_CANONICAL_SOURCE_KIND",
    "C7_GRAPH_PROJECTION_SCHEMA",
    "C7_GRAPH_PROJECTOR_ID",
    "C7_GRAPH_PROJECTOR_VERSION",
    "C7_GRAPH_VALUE_OBJECT_TYPE",
    "C7_PROJECTION_CODEC_ID",
    "C7_PROJECTION_VALUE_PREFIX",
    "C7_SEARCH_PROJECTION_SCHEMA",
    "C7_SEARCH_PROJECTOR_ID",
    "C7_SEARCH_PROJECTOR_VERSION",
    "C7_SEARCH_VALUE_OBJECT_TYPE",
    "C7ProjectedDocument",
    "C7ProjectorCasError",
    "C7ProjectorDriveResult",
    "C7ProjectorDriver",
    "C7ProjectorDriverError",
    "C7ProjectorIntegrityError",
    "C7ProjectorUnavailableError",
    "c7_graph_declared_loss",
    "c7_search_declared_loss",
    "projection_offset_key",
    "rebuild_c7_graph_projection",
    "rebuild_c7_search_projection",
    "verify_projection_value_readback",
]

C7_CANONICAL_SOURCE_KIND = "ingest_canonical"
C7_SEARCH_PROJECTOR_ID = "successor.ingest_index.search.projector"
C7_SEARCH_PROJECTOR_VERSION = "1.0.0"
C7_GRAPH_PROJECTOR_ID = "successor.ingest_index.graph.projector"
C7_GRAPH_PROJECTOR_VERSION = "1.0.0"
C7_PROJECTION_CODEC_ID = "mrw.successor.c7.projection.canonical-json.v1"
C7_PROJECTION_VALUE_PREFIX = "c7:projection"
C7_SEARCH_VALUE_OBJECT_TYPE = "C7SearchProjection.v1"
C7_GRAPH_VALUE_OBJECT_TYPE = "C7GraphProjection.v1"
C7_SEARCH_PROJECTION_SCHEMA = "mrw.successor.c7.search-projection.v1"
C7_GRAPH_PROJECTION_SCHEMA = "mrw.successor.c7.graph-projection.v1"


class C7ProjectorDriverError(RuntimeError):
    """Base fail-closed C7.3 projector driver error."""


class C7ProjectorUnavailableError(C7ProjectorDriverError):
    """No canonical successor document exists for the requested object id."""


class C7ProjectorIntegrityError(C7ProjectorDriverError):
    """Canonical document/source identity or stored bytes drift."""


class C7ProjectorCasError(C7ProjectorDriverError):
    """Projection offset exact CAS failed; the active offset is unchanged."""


@dataclass(frozen=True, slots=True)
class C7ProjectedDocument:
    """Deterministic declared-loss projection rebuilt from a DocumentRef."""

    projection_kind: Literal["search", "graph"]
    document_ref: DocumentRef
    body: Mapping[str, object]
    projection_digest: str
    declared_loss: tuple[tuple[str, str], ...]

    def diff_payload(self) -> dict[str, object]:
        return {
            "source_identity": self.document_ref.object_id,
            "projection_kind": self.projection_kind,
            "source_digest": self.document_ref.content_digest,
            "projection_digest": self.projection_digest,
            "declared_loss": list(self.declared_loss),
        }


@dataclass(frozen=True, slots=True)
class C7ProjectorDriveResult:
    """Observed offset/value closure for one driven C7.3 projection."""

    projection_kind: Literal["search", "graph"]
    rebuild_mode: RebuildMode
    document_ref: DocumentRef
    projection_digest: str
    projection_offset_id: str
    offset_ref: str
    source_revision: int
    source_digest: str
    value_ref: str
    store_writes: int
    provider_calls: Literal[0] = 0
    export_calls: Literal[0] = 0
    production_canonical_authority: Literal[False] = False
    live_provider: Literal[False] = False
    promotion: Literal[False] = False


def c7_search_declared_loss() -> tuple[tuple[str, str], ...]:
    return (
        ("title_text", "rebuild without source text drops title/text"),
        ("raw_payload", "raw ingress payload is not projected"),
    )


def c7_graph_declared_loss() -> tuple[tuple[str, str], ...]:
    return (
        ("source_locator_text", "rebuild without source text drops locator"),
        ("raw_payload", "raw ingress payload is not projected"),
    )


def _search_body(document_ref: DocumentRef) -> dict[str, object]:
    return {
        "project_key": document_ref.project_key,
        "object_id": document_ref.object_id,
        "revision": document_ref.revision,
        "incarnation": document_ref.incarnation,
        "content_digest": document_ref.content_digest,
        "title": "",
        "text_snippet": "",
    }


def _graph_body(document_ref: DocumentRef) -> dict[str, object]:
    return {
        "node_key": (f"ingest:{document_ref.project_key}:{document_ref.object_id}"),
        "project_key": document_ref.project_key,
        "object_id": document_ref.object_id,
        "revision": document_ref.revision,
        "incarnation": document_ref.incarnation,
        "content_digest": document_ref.content_digest,
        "source_locator": "",
    }


def rebuild_c7_search_projection(
    document_ref: DocumentRef,
) -> C7ProjectedDocument:
    """Deterministic search projection; never indexes or calls a provider."""

    body = _search_body(document_ref)
    return C7ProjectedDocument(
        projection_kind="search",
        document_ref=document_ref,
        body=body,
        projection_digest=content_digest(body),
        declared_loss=c7_search_declared_loss(),
    )


def rebuild_c7_graph_projection(
    document_ref: DocumentRef,
) -> C7ProjectedDocument:
    """Deterministic graph-node projection; never writes to a graph."""

    body = _graph_body(document_ref)
    return C7ProjectedDocument(
        projection_kind="graph",
        document_ref=document_ref,
        body=body,
        projection_digest=content_digest(body),
        declared_loss=c7_graph_declared_loss(),
    )


def projection_offset_key(
    projection_kind: Literal["search", "graph"],
    document_ref: DocumentRef,
) -> ProjectionOffsetKey:
    if projection_kind == "search":
        projector_id, projector_version = (
            C7_SEARCH_PROJECTOR_ID,
            C7_SEARCH_PROJECTOR_VERSION,
        )
    elif projection_kind == "graph":
        projector_id, projector_version = (
            C7_GRAPH_PROJECTOR_ID,
            C7_GRAPH_PROJECTOR_VERSION,
        )
    else:
        raise ValueError(f"unsupported C7 projection kind: {projection_kind}")
    return ProjectionOffsetKey(
        projector_id=projector_id,
        projector_version=projector_version,
        source_kind=C7_CANONICAL_SOURCE_KIND,
        source_ref=f"document:{document_ref.object_id}",
        source_incarnation=document_ref.incarnation,
    )


def _value_id(
    projection_kind: Literal["search", "graph"],
    document_ref: DocumentRef,
    projection_digest: str,
) -> str:
    return (
        f"{C7_PROJECTION_VALUE_PREFIX}:{projection_kind}:"
        f"{document_ref.object_id}:rev-{document_ref.revision}:"
        f"{projection_digest[:12]}"
    )


def _value_incarnation(
    projection_kind: Literal["search", "graph"],
    projection_digest: str,
) -> str:
    return f"c7:{projection_kind}:{projection_digest[:16]}"


def _value_ref(value_id: str) -> str:
    return "project-value:" + value_id


class C7ProjectorDriver:
    """Drive C7.3 offsets and rebuilds over one caller-owned connection."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def read_document(self, object_id: str) -> DocumentRef:
        row = (
            self.connection.execute(
                select(C7_MOVEMENT_CANONICAL_DOCUMENTS).where(
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key
                    == self.scope.project_scope.project_key,
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == object_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise C7ProjectorUnavailableError(
                f"canonical successor document not found: {object_id}"
            )
        return DocumentRef.from_content(
            project_key=str(row["project_key"]),
            object_id=str(row["object_id"]),
            revision=int(row["revision"]),
            incarnation=str(row["incarnation"]),
            content_digest=str(row["content_digest"]),
            canonical_owner=DOCUMENT_CANONICAL_OWNER,
        )

    def drive(
        self,
        object_id: str,
        projection_kind: Literal["search", "graph"],
        *,
        mode: RebuildMode = "INCREMENTAL",
        expected_source_incarnation: str | None = None,
    ) -> C7ProjectorDriveResult:
        if mode not in REBUILD_MODES:
            raise ValueError(f"unsupported rebuild mode: {mode}")
        document_ref = self.read_document(object_id)
        if (
            expected_source_incarnation is not None
            and document_ref.incarnation != expected_source_incarnation
        ):
            raise C7ProjectorIntegrityError(
                "canonical document incarnation drifted from the registered "
                "projector source incarnation"
            )
        projected = (
            rebuild_c7_search_projection(document_ref)
            if projection_kind == "search"
            else rebuild_c7_graph_projection(document_ref)
        )
        key = projection_offset_key(projection_kind, document_ref)
        projection_offset_id = f"c7:{projection_kind}:{document_ref.object_id}:offset"
        value_id = _value_id(
            projection_kind,
            document_ref,
            projected.projection_digest,
        )
        value_ref = _value_ref(value_id)
        tables = project_tables(MetaData(), self.scope.project_scope.resolved_schema)
        existing_value = (
            self.connection.execute(
                select(tables.successor_values).where(
                    tables.successor_values.c.project_key
                    == self.scope.project_scope.project_key,
                    tables.successor_values.c.value_id == value_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        provenance = {
            "contract_ref": "mrw.successor.c7.projector-driver.v1",
            "project_key": document_ref.project_key,
            "projection_kind": projection_kind,
            "source_ref": key.source_ref,
            "source_incarnation": document_ref.incarnation,
            "projection_digest": projected.projection_digest,
        }
        provenance_digest = content_digest(provenance)
        ValueRepository(self.connection, tables).put_exact(
            self.scope,
            value_id=value_id,
            object_type=(
                C7_SEARCH_VALUE_OBJECT_TYPE
                if projection_kind == "search"
                else C7_GRAPH_VALUE_OBJECT_TYPE
            ),
            codec_id=C7_PROJECTION_CODEC_ID,
            content=dict(projected.body),
            expected_digest=projected.projection_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=_value_incarnation(
                projection_kind,
                projected.projection_digest,
            ),
            source_ref=key.source_ref,
            provenance=provenance,
            state="AVAILABLE",
        )
        offsets = ProjectionOffsetRepository(self.connection, self.scope)
        current = offsets.load_source(key)
        offset_written = False
        if current is None:
            offsets.create(
                projection_offset_id=projection_offset_id,
                key=key,
                projection_generation=0,
                source_revision=document_ref.revision,
                source_digest=document_ref.content_digest,
                offset_ref=value_ref,
            )
            offset_written = True
        else:
            if (
                int(current["source_revision"]) == document_ref.revision
                and str(current["source_digest"]) == document_ref.content_digest
                and str(current["offset_ref"]) == value_ref
            ):
                offset_written = False
            else:
                try:
                    offsets.advance(
                        str(current["projection_offset_id"]),
                        key=key,
                        expected_revision=int(current["revision"]),
                        expected_generation=int(current["projection_generation"]),
                        expected_source_revision=int(current["source_revision"]),
                        expected_source_digest=str(current["source_digest"]),
                        source_revision=document_ref.revision,
                        source_digest=document_ref.content_digest,
                        offset_ref=value_ref,
                    )
                except StaleRevisionError as exc:
                    raise C7ProjectorCasError(
                        "projection offset exact CAS failed"
                    ) from exc
                offset_written = True
        active = offsets.load_source(key)
        assert active is not None
        return C7ProjectorDriveResult(
            projection_kind=projection_kind,
            rebuild_mode=mode,
            document_ref=document_ref,
            projection_digest=projected.projection_digest,
            projection_offset_id=projection_offset_id,
            offset_ref=str(active["offset_ref"]),
            source_revision=int(active["source_revision"]),
            source_digest=str(active["source_digest"]),
            value_ref=value_ref,
            store_writes=int(existing_value is None) + int(offset_written),
        )

    def rebuild_document(
        self,
        object_id: str,
        *,
        mode: RebuildMode = "FULL",
        expected_source_incarnation: str | None = None,
    ) -> tuple[C7ProjectorDriveResult, C7ProjectorDriveResult]:
        """Drive both registered C7 projections for one canonical document."""

        if mode not in REBUILD_MODES:
            raise ValueError(f"unsupported rebuild mode: {mode}")
        return (
            self.drive(
                object_id,
                "search",
                mode=mode,
                expected_source_incarnation=expected_source_incarnation,
            ),
            self.drive(
                object_id,
                "graph",
                mode=mode,
                expected_source_incarnation=expected_source_incarnation,
            ),
        )


def verify_projection_value_readback(
    connection: Connection,
    scope: RuntimeScope,
    *,
    value_ref: str,
    projection_digest: str,
) -> None:
    """Re-read one persisted projection row and require exact byte readback."""

    prefix = "project-value:"
    if not value_ref.startswith(prefix):
        raise C7ProjectorIntegrityError("projection offset ref is not a value ref")
    value_id = value_ref[len(prefix) :]
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    row = (
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise C7ProjectorUnavailableError(
            f"projected successor value not found: {value_id}"
        )
    if str(row["content_digest"]) != projection_digest:
        raise C7ProjectorIntegrityError("projection value digest drift")
    content = row["content_json"]
    if not isinstance(content, dict):
        raise C7ProjectorIntegrityError("projection value is not content_json")
    if hashlib.sha256(canonical_bytes(content)).hexdigest() != projection_digest:
        raise C7ProjectorIntegrityError("projection value bytes fail digest readback")
