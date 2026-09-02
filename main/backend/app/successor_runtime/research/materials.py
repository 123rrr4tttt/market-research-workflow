"""Captured material snapshots and material references."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .codec import digest_dataclass, finalize_digest, sha256_hex

__all__ = ["CapturedMaterialSnapshot", "MaterialRef"]


@dataclass(frozen=True, slots=True)
class CapturedMaterialSnapshot:
    value_ref: str
    document_id: int
    observed_text_hash: str | None
    observed_updated_at: datetime
    byte_size: int
    content_digest: str | None = None

    def __post_init__(self) -> None:
        finalize_digest(self, "content_digest")


@dataclass(frozen=True, slots=True)
class MaterialRef:
    material_ref_id: str
    source_ref: str
    snapshot: CapturedMaterialSnapshot
    content_digest: str | None = None
    provenance_digest: str | None = None

    def __post_init__(self) -> None:
        expected_content = digest_dataclass(self, ("content_digest", "provenance_digest"))
        if self.content_digest is None:
            object.__setattr__(self, "content_digest", expected_content)
        elif self.content_digest != expected_content:
            raise ValueError("MaterialRef content digest mismatch")
        expected_provenance = sha256_hex(
            {
                "source_ref": self.source_ref,
                "snapshot_value_ref": self.snapshot.value_ref,
                "snapshot_digest": self.snapshot.content_digest,
                "content_digest": self.content_digest,
                "source_observed_hash": self.snapshot.observed_text_hash,
                "source_observed_updated_at": self.snapshot.observed_updated_at,
            }
        )
        if self.provenance_digest is None:
            object.__setattr__(self, "provenance_digest", expected_provenance)
        elif self.provenance_digest != expected_provenance:
            raise ValueError("MaterialRef provenance digest mismatch")
