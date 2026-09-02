"""Declared-loss graph projection scaffold bound to canonical DocumentRef.

The projector derives a graph-node view from a canonical ``DocumentRef`` and
reports which fields it drops.  Rebuild is deterministic and pure; the
projector never writes to a graph and never claims projection truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.successor_runtime.capabilities.ingest_c7_common import (
    ProjectionDiff,
    content_digest,
)

from .document_repository_c7 import (
    CanonicalDocumentReadPort,
    DocumentRef,
)
from .projection_common_c7 import (
    INGEST_CANONICAL_SOURCE_KIND,
    C7ProjectionOffset,
    C7ProjectionSource,
    named_observation_digest,
    projection_offset_from_document,
)

__all__ = [
    "GRAPH_PROJECTION_KIND",
    "GRAPH_PROJECTOR_ID",
    "GRAPH_PROJECTOR_VERSION",
    "GraphProjection",
    "build_graph_projection",
    "delete_graph_observation_digest",
    "graph_named_observation_digest",
    "project_graph_via_port",
    "rebuild_graph_projection",
]


GRAPH_PROJECTION_KIND = "graph_projection"
GRAPH_PROJECTOR_ID = "successor.ingest_index.graph.projector"
GRAPH_PROJECTOR_VERSION = "1.0.0"
GRAPH_SOURCE_KIND = INGEST_CANONICAL_SOURCE_KIND


class GraphProjection:
    def __init__(
        self,
        *,
        document_ref: DocumentRef,
        projection: Mapping[str, Any],
        projection_digest: str,
        declared_loss: tuple[tuple[str, str], ...],
    ) -> None:
        self.document_ref = document_ref
        self.projection = dict(projection)
        self.projection_digest = projection_digest
        self.declared_loss = declared_loss

    @property
    def projection_kind(self) -> str:
        return GRAPH_PROJECTION_KIND

    @property
    def source(self) -> C7ProjectionSource:
        return C7ProjectionSource(
            projector_id=GRAPH_PROJECTOR_ID,
            projector_version=GRAPH_PROJECTOR_VERSION,
            source_kind=GRAPH_SOURCE_KIND,
            source_ref=f"document:{self.document_ref.object_id}",
            source_incarnation=self.document_ref.incarnation,
        )

    def diff(self) -> ProjectionDiff:
        return ProjectionDiff(
            source_identity=self.document_ref.object_id,
            projection_kind=self.projection_kind,
            source_digest=self.document_ref.content_digest,
            projection_digest=self.projection_digest,
            declared_loss=self.declared_loss,
        )


def _graph_projection_body(
    document_ref: DocumentRef, source_locator: str
) -> dict[str, Any]:
    return {
        "node_key": f"ingest:{document_ref.project_key}:{document_ref.object_id}",
        "project_key": document_ref.project_key,
        "object_id": document_ref.object_id,
        "revision": document_ref.revision,
        "incarnation": document_ref.incarnation,
        "content_digest": document_ref.content_digest,
        "source_locator": source_locator,
    }


def build_graph_projection(
    document_ref: DocumentRef,
    *,
    source_locator: str,
) -> GraphProjection:
    projection = _graph_projection_body(document_ref, source_locator)
    return GraphProjection(
        document_ref=document_ref,
        projection=projection,
        projection_digest=content_digest(projection),
        declared_loss=(
            ("text", "graph projection drops the full text"),
            ("raw_payload", "raw ingress payload is not projected"),
        ),
    )


def rebuild_graph_projection(document_ref: DocumentRef) -> GraphProjection:
    """Deterministic rebuild from the canonical ref; no graph write."""

    projection = _graph_projection_body(document_ref, "")
    return GraphProjection(
        document_ref=document_ref,
        projection=projection,
        projection_digest=content_digest(projection),
        declared_loss=(
            ("source_locator_text", "rebuild without source text drops locator"),
            ("raw_payload", "raw ingress payload is not projected"),
        ),
    )


def graph_named_observation_digest(document_ref: DocumentRef) -> str:
    return named_observation_digest(
        projector_id=GRAPH_PROJECTOR_ID,
        projection_kind=GRAPH_PROJECTION_KIND,
        object_id=document_ref.object_id,
        revision=document_ref.revision,
        incarnation=document_ref.incarnation,
        content_digest_hex=document_ref.content_digest,
    )


def delete_graph_observation_digest(document_ref: DocumentRef) -> str:
    """Deleted observation keeps the same named digest as rebuild parity."""

    return graph_named_observation_digest(document_ref)


def project_graph_via_port(
    port: CanonicalDocumentReadPort,
    object_id: str,
) -> tuple[GraphProjection | None, C7ProjectionOffset | None]:
    """Read canonical Document through the port and project without effects."""

    document = port.read_document(object_id)
    if document is None:
        return None, None
    from .document_repository_c7 import DOCUMENT_CANONICAL_OWNER

    document_ref = DocumentRef.from_content(
        project_key=document.project_key,
        object_id=document.object_id,
        revision=document.revision,
        incarnation=document.incarnation,
        content_digest=document.content_digest,
        canonical_owner=DOCUMENT_CANONICAL_OWNER,
    )
    source = C7ProjectionSource(
        projector_id=GRAPH_PROJECTOR_ID,
        projector_version=GRAPH_PROJECTOR_VERSION,
        source_kind=GRAPH_SOURCE_KIND,
        source_ref=f"document:{document.object_id}",
        source_incarnation=document.incarnation,
    )
    projection = GraphProjection(
        document_ref=document_ref,
        projection=_graph_projection_body(document_ref, ""),
        projection_digest=content_digest(_graph_projection_body(document_ref, "")),
        declared_loss=(
            ("source_locator_text", "port rebuild without source text drops locator"),
            ("raw_payload", "raw ingress payload is not projected"),
        ),
    )
    return projection, projection_offset_from_document(source, document)
