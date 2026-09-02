"""Declared-loss search projection scaffold bound to canonical DocumentRef.

The projector derives a bounded search-view projection from a canonical
``DocumentRef`` (project/id/revision/incarnation/digest) and reports exactly
which fields it drops.  Rebuild is deterministic and pure; the projector never
writes to an index and never manufactures adoption or provider facts.
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
    "SEARCH_PROJECTION_KIND",
    "SEARCH_PROJECTOR_ID",
    "SEARCH_PROJECTOR_VERSION",
    "C7ProjectionSource",
    "SearchProjection",
    "build_search_projection",
    "delete_search_observation_digest",
    "project_search_via_port",
    "rebuild_search_projection",
    "search_named_observation_digest",
]


SEARCH_PROJECTION_KIND = "search_projection"
SEARCH_PROJECTOR_ID = "successor.ingest_index.search.projector"
SEARCH_PROJECTOR_VERSION = "1.0.0"
SEARCH_SOURCE_KIND = INGEST_CANONICAL_SOURCE_KIND


class SearchProjection:
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
        return SEARCH_PROJECTION_KIND

    @property
    def source(self) -> C7ProjectionSource:
        return C7ProjectionSource(
            projector_id=SEARCH_PROJECTOR_ID,
            projector_version=SEARCH_PROJECTOR_VERSION,
            source_kind=SEARCH_SOURCE_KIND,
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


def _search_projection_body(
    document_ref: DocumentRef, title: str, text: str
) -> dict[str, Any]:
    return {
        "project_key": document_ref.project_key,
        "object_id": document_ref.object_id,
        "revision": document_ref.revision,
        "incarnation": document_ref.incarnation,
        "content_digest": document_ref.content_digest,
        "title": title,
        "text_snippet": text[:200],
    }


def build_search_projection(
    document_ref: DocumentRef,
    *,
    title: str,
    text: str,
) -> SearchProjection:
    """Pure projection: index-facing fields plus explicit dropped fields."""

    projection = _search_projection_body(document_ref, title, text)
    return SearchProjection(
        document_ref=document_ref,
        projection=projection,
        projection_digest=content_digest(projection),
        declared_loss=(
            ("full_text", "search projection keeps a bounded text snippet"),
            ("raw_payload", "raw ingress payload is not projected"),
        ),
    )


def rebuild_search_projection(document_ref: DocumentRef) -> SearchProjection:
    """Deterministic rebuild from the canonical ref; no index effect."""

    projection = _search_projection_body(document_ref, "", "")
    return SearchProjection(
        document_ref=document_ref,
        projection=projection,
        projection_digest=content_digest(projection),
        declared_loss=(
            ("title_text", "rebuild without source text drops title/text"),
            ("raw_payload", "raw ingress payload is not projected"),
        ),
    )


def search_named_observation_digest(document_ref: DocumentRef) -> str:
    return named_observation_digest(
        projector_id=SEARCH_PROJECTOR_ID,
        projection_kind=SEARCH_PROJECTION_KIND,
        object_id=document_ref.object_id,
        revision=document_ref.revision,
        incarnation=document_ref.incarnation,
        content_digest_hex=document_ref.content_digest,
    )


def delete_search_observation_digest(document_ref: DocumentRef) -> str:
    """Deleted observation keeps the same named digest as rebuild parity."""

    return search_named_observation_digest(document_ref)


def project_search_via_port(
    port: CanonicalDocumentReadPort,
    object_id: str,
) -> tuple[SearchProjection | None, C7ProjectionOffset | None]:
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
        projector_id=SEARCH_PROJECTOR_ID,
        projector_version=SEARCH_PROJECTOR_VERSION,
        source_kind=SEARCH_SOURCE_KIND,
        source_ref=f"document:{document.object_id}",
        source_incarnation=document.incarnation,
    )
    projection = SearchProjection(
        document_ref=document_ref,
        projection=_search_projection_body(document_ref, "", ""),
        projection_digest=content_digest(_search_projection_body(document_ref, "", "")),
        declared_loss=(
            ("title_text", "port rebuild without source text drops title/text"),
            ("raw_payload", "raw ingress payload is not projected"),
        ),
    )
    return projection, projection_offset_from_document(source, document)
