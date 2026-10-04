"""Shared C7 projection source/offset DTOs.

Both the search and graph projectors consume one source identity and one
offset shape so the disposable PostgreSQL offset repository and the family
fragment observe exactly the same synchronization contract.  Offset
revision/digest are derived from the canonical Document, never from a runtime
intent self-assertion.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.successor_runtime.capabilities.ingest_c7_common import content_digest

from .document_repository_c7 import CanonicalDocumentState

__all__ = [
    "INGEST_CANONICAL_SOURCE_KIND",
    "C7ProjectionOffset",
    "C7ProjectionSource",
    "projection_offset_from_document",
]


INGEST_CANONICAL_SOURCE_KIND = "ingest_canonical"


@dataclass(frozen=True, slots=True)
class C7ProjectionSource:
    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str

    def to_offset_key(self) -> dict[str, str]:
        return {
            "projector_id": self.projector_id,
            "projector_version": self.projector_version,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "source_incarnation": self.source_incarnation,
        }


@dataclass(frozen=True, slots=True)
class C7ProjectionOffset:
    source: C7ProjectionSource
    source_revision: int
    source_digest: str
    offset_ref: str

    def to_repository_values(self) -> dict[str, object]:
        return {
            **self.source.to_offset_key(),
            "source_revision": self.source_revision,
            "source_digest": self.source_digest,
            "offset_ref": self.offset_ref,
        }


def projection_offset_from_document(
    source: C7ProjectionSource,
    document: CanonicalDocumentState,
) -> C7ProjectionOffset:
    """Synchronize the offset revision/digest with the canonical Document."""

    return C7ProjectionOffset(
        source=source,
        source_revision=document.revision,
        source_digest=document.content_digest,
        offset_ref=f"document-revision:{document.revision}",
    )


def named_observation_digest(
    *,
    projector_id: str,
    projection_kind: str,
    object_id: str,
    revision: int,
    incarnation: str,
    content_digest_hex: str,
) -> str:
    """One deterministic named-observation identity for delete/rebuild parity."""

    return content_digest(
        {
            "projector_id": projector_id,
            "projection_kind": projection_kind,
            "object_id": object_id,
            "revision": revision,
            "incarnation": incarnation,
            "content_digest": content_digest_hex,
        }
    )
