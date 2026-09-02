"""Immutable external source references."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .codec import finalize_digest

__all__ = ["SourceRef"]


@dataclass(frozen=True, slots=True)
class SourceRef:
    source_ref_id: str
    owner_id: str
    locator: str
    source_class: str
    observed_at: datetime
    access_profile_ref: str
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.access_profile_ref, str):
            raise ValueError("SourceRef access_profile_ref is required")
        finalize_digest(self, "content_digest")
