"""Immutable provenance closures for research objects and relations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .codec import finalize_digest
from .identities import ResearchObjectRef

__all__ = ["ProvenanceClosure", "ProvenanceEntry"]


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    entry_id: str
    object_ref: ResearchObjectRef | None = None
    relation_id: str | None = None
    content_digest: str | None = None
    observed_at: datetime | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceClosure:
    closure_id: str
    project_key: str
    entries: tuple[ProvenanceEntry, ...]
    closure_digest: str | None = None

    def __post_init__(self) -> None:
        finalize_digest(self, "closure_digest")
