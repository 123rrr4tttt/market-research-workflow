"""Canonical evidence qualification relation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .codec import _failure, _raise_failure, finalize_digest

__all__ = ["QUALIFICATION_DIRECTIONS", "EvidenceQualification", "Validity"]

QUALIFICATION_DIRECTIONS: tuple[str, ...] = (
    "SUPPORTS",
    "CONTRADICTS",
    "CONTEXT",
    "INSUFFICIENT",
)


@dataclass(frozen=True, slots=True)
class Validity:
    """The bounded validity interval frozen by schema bundle v1.1."""

    valid_from: datetime | None
    valid_to: datetime | None

    def __post_init__(self) -> None:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from > self.valid_to
        ):
            _raise_failure(
                _failure(
                    "VALIDITY_INVALID",
                    "validity valid_from must not be after valid_to",
                    ValueError,
                    site="Validity.interval",
                ),
                ValueError,
            )


@dataclass(frozen=True, slots=True)
class EvidenceQualification:
    """Relation-only qualification of material against an inquiry or claim."""

    qualification_id: str
    project_key: str
    material_ref: str
    inquiry_ref: str
    claim_ref: str | None
    direction: str
    scope_statement_ref: str
    uncertainty_profile_ref: str
    verifier_profile_ref: str
    provenance_closure_digest: str
    validity: Validity
    source_time: datetime | None = None
    observed_at: datetime | None = None
    revision: int = 1
    incarnation: str = "inc-1"
    state: str = "ACTIVE"
    qualification_digest: str | None = None

    RELATION_STORAGE: ClassVar[str] = "research_relations_only"
    DUPLICATE_RESEARCH_OBJECT_FORBIDDEN: ClassVar[bool] = True

    def __post_init__(self) -> None:
        if not isinstance(self.material_ref, str) or not self.material_ref.strip():
            _raise_failure(
                _failure(
                    "MATERIAL_REF_INVALID",
                    "material_ref must be a non-empty reference string",
                    ValueError,
                    site="EvidenceQualification.material_ref",
                ),
                ValueError,
            )
        if self.claim_ref is not None and (
            not isinstance(self.claim_ref, str) or not self.claim_ref.strip()
        ):
            _raise_failure(
                _failure(
                    "EVIDENCE_QUALIFICATION_INVALID",
                    "claim_ref must be null or a non-empty reference string",
                    ValueError,
                    site="EvidenceQualification.claim_ref",
                ),
                ValueError,
            )
        if not isinstance(self.validity, Validity):
            _raise_failure(
                _failure(
                    "VALIDITY_INVALID",
                    "validity must be a Validity object",
                    TypeError,
                    site="EvidenceQualification.validity",
                ),
                TypeError,
            )
        if self.direction not in QUALIFICATION_DIRECTIONS:
            _raise_failure(
                _failure(
                    "EVIDENCE_QUALIFICATION_INVALID",
                    f"invalid qualification direction: {self.direction}",
                    ValueError,
                    site="EvidenceQualification.direction",
                ),
                ValueError,
            )
        finalize_digest(self, "qualification_digest")
