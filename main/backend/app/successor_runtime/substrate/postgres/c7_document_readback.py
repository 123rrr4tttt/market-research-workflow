"""Successor-owned C7 canonical document readback contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.successor_runtime.capabilities.ingest_c7_common import (
    DOCUMENT_CANONICAL_OWNER,
)
from app.successor_runtime.runtime.assignments import (
    ContentAddressedBinding,
    canonical_digest,
)

__all__ = [
    "CanonicalCommitReadback",
    "DocumentRef",
    "document_ref_from_readback",
]


class DocumentRef(ContentAddressedBinding):
    """Canonical content-addressed document identity for C7 projectors."""

    schema_version: Literal["mrw.runtime.document_ref.v1"] = (
        "mrw.runtime.document_ref.v1"
    )
    project_key: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    incarnation: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    canonical_owner: str = DOCUMENT_CANONICAL_OWNER


@dataclass(frozen=True, slots=True)
class CanonicalCommitReadback:
    """Committed canonical document state returned by the C7.2 read port."""

    commit_intent_id: str
    idempotency_key: str
    capability_id: str
    project_key: str
    object_id: str
    committed_revision: int
    committed_incarnation: str
    content_digest: str
    canonical_commit_ref: str
    readback_digest: str = ""

    def __post_init__(self) -> None:
        if self.readback_digest == "":
            object.__setattr__(
                self,
                "readback_digest",
                canonical_digest(
                    {
                        "commit_intent_id": self.commit_intent_id,
                        "idempotency_key": self.idempotency_key,
                        "capability_id": self.capability_id,
                        "project_key": self.project_key,
                        "object_id": self.object_id,
                        "committed_revision": self.committed_revision,
                        "committed_incarnation": self.committed_incarnation,
                        "content_digest": self.content_digest,
                        "canonical_commit_ref": self.canonical_commit_ref,
                    }
                ),
            )


def document_ref_from_readback(readback: CanonicalCommitReadback) -> DocumentRef:
    """Build DocumentRef from committed readback, never from runtime intent."""

    return DocumentRef.from_content(
        project_key=readback.project_key,
        object_id=readback.object_id,
        revision=readback.committed_revision,
        incarnation=readback.committed_incarnation,
        content_digest=readback.content_digest,
        canonical_owner=DOCUMENT_CANONICAL_OWNER,
    )
