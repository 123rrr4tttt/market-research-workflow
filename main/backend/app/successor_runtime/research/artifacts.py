"""Product and effect objects: artifacts, delivery intent/attempt/receipt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .codec import finalize_digest, is_sha256_hex

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
            raise ValueError(f"artifact format must be {DELIVERY_FORMAT!r}")
        if self.revision < 1:
            raise ValueError("artifact revision must be >= 1")
        if self.lifecycle_state not in ARTIFACT_LIFECYCLE_STATES:
            raise ValueError(f"invalid artifact lifecycle state: {self.lifecycle_state}")
        finalize_digest(self, "content_digest")


def artifact_identity_ref(
    artifact_id: str,
    revision: int,
    content_digest: str | None,
) -> str:
    """Bind artifact identity, revision, and exact canonical content digest."""

    if not artifact_id or revision < 1:
        raise ValueError("artifact identity and revision are required")
    if content_digest is None or not is_sha256_hex(content_digest):
        raise ValueError("artifact content digest is required")
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
            raise ValueError(f"channel must be {DELIVERY_CHANNEL!r}")
        if self.format != DELIVERY_FORMAT:
            raise ValueError(f"format must be {DELIVERY_FORMAT!r}")
        if self.irreversibility_profile != DELIVERY_IRREVERSIBILITY_PROFILE:
            raise ValueError(
                f"irreversibility profile must be {DELIVERY_IRREVERSIBILITY_PROFILE!r}"
            )
        if not self.approval_refs:
            raise ValueError("delivery intent requires at least one approval ref")
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
            raise ValueError(f"invalid effect disposition: {self.effect_disposition}")
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
