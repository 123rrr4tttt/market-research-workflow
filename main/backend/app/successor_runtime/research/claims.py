"""Canonical claim and gap research objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codec import _failure, _raise_failure, finalize_digest

__all__ = ["CLAIM_LIFECYCLE_STATES", "Claim", "Gap"]

CLAIM_LIFECYCLE_STATES: tuple[str, ...] = (
    "DRAFT",
    "ADMITTED",
    "SUPERSEDED",
    "RETRACTED",
)


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    statement_ref: str
    support_relation_refs: tuple[str, ...]
    contradiction_relation_refs: tuple[str, ...]
    uncertainty_profile_ref: str
    lifecycle_state: str
    scope: dict[str, Any]
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if self.lifecycle_state not in CLAIM_LIFECYCLE_STATES:
            _raise_failure(
                _failure(
                    "CLAIM_INVALID",
                    f"invalid claim lifecycle state: {self.lifecycle_state}",
                    ValueError,
                    site="Claim.lifecycle_state",
                ),
                ValueError,
            )
        if not self.scope:
            _raise_failure(
                _failure(
                    "CLAIM_INVALID",
                    "claim scope is required",
                    ValueError,
                    site="Claim.scope",
                ),
                ValueError,
            )
        finalize_digest(self, "content_digest")


@dataclass(frozen=True, slots=True)
class Gap:
    gap_id: str
    inquiry_ref: str
    requirement: str
    reason: str
    closure_condition: str
    reopen_policy: dict[str, Any]
    missing_evidence_or_decision: str
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.reopen_policy:
            _raise_failure(
                _failure(
                    "GAP_INVALID",
                    "gap reopen_policy is required",
                    ValueError,
                    site="Gap.reopen_policy",
                ),
                ValueError,
            )
        if not self.missing_evidence_or_decision:
            _raise_failure(
                _failure(
                    "GAP_INVALID",
                    "gap missing_evidence_or_decision is required",
                    ValueError,
                    site="Gap.missing_evidence_or_decision",
                ),
                ValueError,
            )
        finalize_digest(self, "content_digest")
