"""Verification and idempotent canonical admission contracts."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.successor_runtime.research.codec import canonical_bytes

from .assignments import (
    ContentAddressedBinding,
    Digest,
    FrozenContract,
    canonical_digest,
)


class VerificationBinding(ContentAddressedBinding):
    """Exact, content-addressed proof of what may be admitted.

    ``binding_digest`` is derived from every other field by
    :class:`ContentAddressedBinding`.  A caller therefore cannot retain a
    trusted binding identity while changing candidate bytes, event order,
    authority, or canonical-base identity.
    """

    schema_version: Literal["mrw.runtime.verification_binding.v1"] = (
        "mrw.runtime.verification_binding.v1"
    )
    program_digest: Digest
    plan_digest: Digest
    step_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    input_closure_digest: Digest
    output_content_digest: Digest
    ordered_event_payload_digests: tuple[Digest, ...] = Field(min_length=1)
    ordered_event_payload_closure_digest: Digest
    schema_digest: Digest
    compiler_identity: str = Field(min_length=1)
    interpreter_identity: str = Field(min_length=1)
    verifier_identity: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    authority_digest: Digest
    project_registry_revision: int = Field(ge=0)
    project_scope_digest: Digest
    resolved_schema: str = Field(min_length=1)
    canonical_owner: str = Field(min_length=1)
    canonical_object_id: str = Field(min_length=1)
    canonical_base_revision: int = Field(ge=0)
    canonical_incarnation: str = Field(min_length=1)
    evidence_digest: Digest
    receipt_digest: Digest
    provenance_digest: Digest
    declared_loss_profile_ref: str | None = None
    qualifier: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ordered_event_closure(self) -> "VerificationBinding":
        expected = ordered_event_closure_digest(self.ordered_event_payload_digests)
        if self.ordered_event_payload_closure_digest != expected:
            raise ValueError("ordered event payload closure digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> "VerificationBinding":
        """Derive event identities from the exact ordered payloads.

        Byte payloads are hashed byte-for-byte.  Canonical payload objects are
        first encoded by the strict successor canonical codec.  Neither the
        per-event digests nor their ordered closure are caller-authoritative.
        """

        payloads = content.pop("ordered_event_payloads", None)
        if payloads is None:
            payloads = content.pop("ordered_event_records", None)
        if payloads is None:
            raise ValueError("ordered_event_payloads are required")
        if "ordered_event_payload_digests" in content or (
            "ordered_event_payload_closure_digest" in content
        ):
            raise ValueError("ordered event digests are derived from payloads")
        if not isinstance(payloads, (tuple, list)) or not payloads:
            raise ValueError("ordered_event_payloads must be a non-empty sequence")
        digests = tuple(event_payload_digest(payload) for payload in payloads)
        return super().from_content(
            **content,
            ordered_event_payload_digests=digests,
            ordered_event_payload_closure_digest=ordered_event_closure_digest(digests),
        )

    def require_exact_ordered_event_payloads(
        self, ordered_event_payloads: tuple[object, ...] | list[object]
    ) -> None:
        actual = tuple(event_payload_digest(payload) for payload in ordered_event_payloads)
        if actual != self.ordered_event_payload_digests:
            raise ValueError("ordered event payload bytes drift")
        if ordered_event_closure_digest(actual) != self.ordered_event_payload_closure_digest:
            raise ValueError("ordered event closure drift")


def event_payload_digest(payload: object) -> str:
    """Digest exact bytes or the strict canonical bytes of one event record."""

    if isinstance(payload, bytes):
        encoded = payload
    elif isinstance(payload, bytearray):
        encoded = bytes(payload)
    elif isinstance(payload, BaseModel):
        encoded = canonical_bytes(payload.model_dump(mode="json", exclude_none=False))
    else:
        encoded = canonical_bytes(payload)
    return hashlib.sha256(encoded).hexdigest()


def ordered_event_closure_digest(event_digests: tuple[str, ...]) -> str:
    """Bind event count, position, and exact per-event payload identity."""

    return canonical_digest(
        {
            "schema_version": "mrw.runtime.ordered-event-closure.v1",
            "event_count": len(event_digests),
            "ordered_event_payload_digests": event_digests,
        }
    )


class CommitIntentState(StrEnum):
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class CommitIntent(FrozenContract):
    schema_version: str = "mrw.runtime.commit_intent.v1"
    commit_intent_id: str = Field(min_length=1)
    canonical_owner: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    project_registry_revision: int = Field(ge=0)
    project_scope_digest: str = Field(min_length=1)
    expected_base_revision: int = Field(ge=0)
    expected_incarnation: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    ordered_event_closure_digest: str = Field(min_length=1)
    verification_binding_digest: str = Field(min_length=1)
    authority_digest: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    state: CommitIntentState = CommitIntentState.PREPARED


def require_admission_binding(
    binding: VerificationBinding,
    intent: CommitIntent,
    *,
    current_authority_digest: str,
    current_base_revision: int,
    current_incarnation: str,
    ordered_event_payloads: tuple[object, ...] | list[object],
) -> None:
    """Fail closed unless the prepared intent is the binding's exact commit.

    The comparison deliberately covers the candidate, ordered event closure,
    authority closure, project scope, and canonical base.  Checking only the
    binding digest carried by the intent would allow a partially-populated or
    substituted ``CommitIntent`` to cross the admission boundary.
    """

    if intent.state is not CommitIntentState.PREPARED:
        raise ValueError("commit intent is not prepared")
    binding.require_exact_ordered_event_payloads(ordered_event_payloads)
    if binding.binding_digest != intent.verification_binding_digest:
        raise ValueError("verification binding drift")
    if (
        binding.canonical_owner != intent.canonical_owner
        or binding.project_key != intent.project_key
        or binding.canonical_object_id != intent.object_id
    ):
        raise ValueError("canonical identity drift")
    if (
        binding.project_registry_revision != intent.project_registry_revision
        or binding.project_scope_digest != intent.project_scope_digest
    ):
        raise ValueError("project scope drift")
    if (
        binding.authority_digest != intent.authority_digest
        or binding.authority_digest != current_authority_digest
    ):
        raise ValueError("authority drift before canonical commit")
    if (
        binding.canonical_base_revision != intent.expected_base_revision
        or binding.canonical_base_revision != current_base_revision
    ):
        raise ValueError("canonical base revision drift")
    if (
        binding.canonical_incarnation != intent.expected_incarnation
        or binding.canonical_incarnation != current_incarnation
    ):
        raise ValueError("canonical incarnation drift")
    if binding.output_content_digest != intent.content_digest:
        raise ValueError("candidate content drift")
    if (
        binding.ordered_event_payload_closure_digest
        != intent.ordered_event_closure_digest
    ):
        raise ValueError("ordered event closure drift")
