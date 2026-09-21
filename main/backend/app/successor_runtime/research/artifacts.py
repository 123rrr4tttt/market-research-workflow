"""Product and effect objects: artifacts, delivery intent/attempt/receipt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .codec import _failure, _raise_failure, finalize_digest, is_sha256_hex

__all__ = [
    "DELIVERY_CHANNEL",
    "DELIVERY_FORMAT",
    "DELIVERY_IRREVERSIBILITY_PROFILE",
    "EFFECT_DISPOSITIONS",
    "DeliveryAttempt",
    "DeliveryIntent",
    "DeliveryReceiptRef",
    "ResearchArtifact",
    "artifact_identity_ref",
    "artifact_exact_ref",
]

DELIVERY_CHANNEL = "internal_export"
DELIVERY_FORMAT = "markdown"
DELIVERY_IRREVERSIBILITY_PROFILE = "internal_content_addressed_export"

EFFECT_DISPOSITIONS: tuple[str, ...] = (
    "NOT_STARTED",
    "IN_FLIGHT",
    "SUCCEEDED",
    "FAILED",
    "OUTCOME_UNKNOWN",
)

ARTIFACT_LIFECYCLE_STATES: tuple[str, ...] = (
    "DRAFT",
    "ADMITTED",
    "SUPERSEDED",
    "RETRACTED",
)


@dataclass(frozen=True, slots=True)
class ResearchArtifact:
    artifact_id: str
    content_ref: str
    content_digest: str | None
    claim_closure: tuple[str, ...]
    evidence_relation_closure: tuple[str, ...]
    citation_closure: tuple[str, ...]
    format: str
    revision: int
    lifecycle_state: str

    def __post_init__(self) -> None:
        if self.format != DELIVERY_FORMAT:
            _raise_failure(
                _failure(
                    "ARTIFACT_INVALID",
                    f"artifact format must be {DELIVERY_FORMAT!r}",
                    ValueError,
                    site="ResearchArtifact.format",
                ),
                ValueError,
            )
        if self.revision < 1:
            _raise_failure(
                _failure(
                    "ARTIFACT_INVALID",
                    "artifact revision must be >= 1",
                    ValueError,
                    site="ResearchArtifact.revision",
                ),
                ValueError,
            )
        if self.lifecycle_state not in ARTIFACT_LIFECYCLE_STATES:
            _raise_failure(
                _failure(
                    "ARTIFACT_INVALID",
                    f"invalid artifact lifecycle state: {self.lifecycle_state}",
                    ValueError,
                    site="ResearchArtifact.lifecycle_state",
                ),
                ValueError,
            )
        finalize_digest(self, "content_digest")


def artifact_identity_ref(
    artifact_id: str,
    revision: int,
    content_digest: str | None,
) -> str:
    """Bind artifact identity, revision, and exact canonical content digest."""

    if not artifact_id or revision < 1:
        _raise_failure(
            _failure(
                "ARTIFACT_IDENTITY_INVALID",
                "artifact identity and revision are required",
                ValueError,
                site="artifact_identity_ref.identity",
            ),
            ValueError,
        )
    if content_digest is None or not is_sha256_hex(content_digest):
        _raise_failure(
            _failure(
                "ARTIFACT_IDENTITY_INVALID",
                "artifact content digest is required",
                ValueError,
                site="artifact_identity_ref.content_digest",
            ),
            ValueError,
        )
    return f"{artifact_id}@{revision}:sha256:{content_digest}"


def artifact_exact_ref(artifact: ResearchArtifact) -> str:
    return artifact_identity_ref(
        artifact.artifact_id,
        artifact.revision,
        artifact.content_digest,
    )


@dataclass(frozen=True, slots=True)
class DeliveryIntent:
    delivery_intent_id: str
    artifact_ref: str
    audience: str
    channel: str
    format: str
    approval_refs: tuple[str, ...]
    authority_digest: str
    idempotency_key: str
    irreversibility_profile: str
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if self.channel != DELIVERY_CHANNEL:
            _raise_failure(
                _failure(
                    "DELIVERY_INTENT_INVALID",
                    f"channel must be {DELIVERY_CHANNEL!r}",
                    ValueError,
                    site="DeliveryIntent.channel",
                ),
                ValueError,
            )
        if self.format != DELIVERY_FORMAT:
            _raise_failure(
                _failure(
                    "DELIVERY_INTENT_INVALID",
                    f"format must be {DELIVERY_FORMAT!r}",
                    ValueError,
                    site="DeliveryIntent.format",
                ),
                ValueError,
            )
        if self.irreversibility_profile != DELIVERY_IRREVERSIBILITY_PROFILE:
            _raise_failure(
                _failure(
                    "DELIVERY_INTENT_INVALID",
                    f"irreversibility profile must be {DELIVERY_IRREVERSIBILITY_PROFILE!r}",
                    ValueError,
                    site="DeliveryIntent.irreversibility_profile",
                ),
                ValueError,
            )
        if not self.approval_refs:
            _raise_failure(
                _failure(
                    "DELIVERY_INTENT_INVALID",
                    "delivery intent requires at least one approval ref",
                    ValueError,
                    site="DeliveryIntent.approval_refs",
                ),
                ValueError,
            )
        finalize_digest(self, "content_digest")


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """Runtime fact owned by the Execution Journal, not a research object."""

    attempt_id: str
    delivery_intent_ref: str
    assignment_digest: str
    handler_binding_digest: str
    effect_disposition: str
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if self.effect_disposition not in EFFECT_DISPOSITIONS:
            _raise_failure(
                _failure(
                    "DELIVERY_ATTEMPT_INVALID",
                    f"invalid effect disposition: {self.effect_disposition}",
                    ValueError,
                    site="DeliveryAttempt.effect_disposition",
                ),
                ValueError,
            )
        finalize_digest(self, "content_digest")


@dataclass(frozen=True, slots=True)
class DeliveryReceiptRef:
    """Immutable external ref owned by the project receipt store."""

    receipt_ref: str
    delivery_intent_ref: str
    attempt_ref: str
    provider_locator: str
    receipt_digest: str
    outcome_time: datetime
    content_digest: str | None = None

    def __post_init__(self) -> None:
        finalize_digest(self, "content_digest")
