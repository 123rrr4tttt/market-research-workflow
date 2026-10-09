"""Immutable external source references."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from .codec import (
    finalize_digest,
    raise_research_failure as _raise_failure,
    research_failure as _failure,
    runtime_value,
)

__all__ = ["SourceRef", "material_locator_identity"]


def material_locator_identity(locator: str) -> tuple[str, str] | None:
    """Compare material locators without rewriting content-addressed sources."""

    try:
        parsed = urlsplit(locator)
    except ValueError:
        return None
    if (
        parsed.scheme not in {"material", "document"}
        or not parsed.netloc
        or any(char in parsed.netloc for char in "@:")
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        return None
    object_id = parsed.path[1:]
    if not object_id or object_id.startswith("/"):
        return None
    return parsed.netloc, object_id


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
        if not isinstance(runtime_value(self.access_profile_ref), str):
            _raise_failure(
                _failure(
                    "SOURCE_REF_INVALID",
                    "SourceRef access_profile_ref is required",
                    ValueError,
                    site="SourceRef.access_profile_ref",
                ),
                ValueError,
            )
        finalize_digest(self, "content_digest")
