"""Successor-native interpreters for the bounded first specimen.

The module owns capability semantics only.  It deliberately has no database,
queue, legacy workflow, provider, or runtime-orchestration dependency.  The
delivery effect is expressed by injected ports:

* ``InternalExportPort`` performs an internal, content-addressed, write-once
  export with authoritative readback.

Document read authority exists only in the submission service.  At runtime,
capture receives exact bytes replayed from the project value store and validates
them against the submission-frozen snapshot.  Admission and persistence remain
the responsibility of the runtime UoW.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import (
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from app.successor_runtime.research import (
    CapturedMaterialSnapshot,
    Claim,
    DeliveryIntent,
    DeliveryReceiptRef,
    EvidenceQualification,
    Gap,
    MaterialRef,
    ResearchArtifact,
)
from app.successor_runtime.research.artifacts import artifact_exact_ref
from app.successor_runtime.research.codec import digest_dataclass
from app.successor_runtime.research.evidence import Validity

from .checksum import content_digest, require_hex64

__all__ = [
    "CapturedDocumentValue",
    "ClaimOrGapOutput",
    "ComposedMarkdownArtifact",
    "DeliveryApprovalAuthorityPort",
    "FirstSpecimenInterpreters",
    "InternalExportObservation",
    "InternalExportOutcomeUncertain",
    "InternalExportPort",
    "InternalExportRejected",
    "InterpreterFailure",
    "InterpreterOutcome",
    "InterpreterOutcomeUnknown",
    "InterpreterSuccess",
    "VerifiedDeliveryBinding",
    "artifact_exact_ref",
    "derive_material_ref",
]


T = TypeVar("T")
EffectDisposition: TypeAlias = Literal[
    "NOT_STARTED",
    "IN_FLIGHT",
    "SUCCEEDED",
    "FAILED",
    "OUTCOME_UNKNOWN",
]
ClaimOrGap: TypeAlias = Claim | Gap


def derive_material_ref(
    *,
    source_ref: str,
    snapshot: CapturedMaterialSnapshot,
    owner_id: str,
    locator: str,
    observed_at: str,
) -> MaterialRef:
    """Construct the one content-bound MaterialRef identity used at every seam."""

    material_identity = content_digest(
        {
            "source_ref": source_ref,
            "snapshot_digest": snapshot.content_digest,
            "owner_id": owner_id,
            "locator": locator,
            "observed_at": observed_at,
        }
    )
    return MaterialRef(
        material_ref_id=f"material:sha256:{material_identity}",
        source_ref=source_ref,
        snapshot=snapshot,
    )


class ProjectScopeView(Protocol):
    scope_digest: str


class RuntimeScopeView(Protocol):
    project_scope: ProjectScopeView
    actor_id: str


class CaptureDocumentSnapshotInputView(Protocol):
    source_ref: str
    document_id: int
    content_sha256_hex: str
    observed_updated_at: str
    byte_size: int
    payload_digest: str


class CanonicalReadInputView(Protocol):
    source_ref: str
    locator: str
    owner_id: str
    observed_at: str
    payload_digest: str


class EvidenceQualificationInputView(Protocol):
    qualification_id: str
    material_ref: str
    inquiry_ref: str
    direction: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT", "INSUFFICIENT"]
    scope_statement_ref: str
    uncertainty_profile_ref: str
    verifier_profile_ref: str
    payload_digest: str


class ClaimOrGapInputView(Protocol):
    claim_or_gap_id: str
    statement_ref: str
    inquiry_ref: str
    support_relation_refs: tuple[str, ...]
    contradiction_relation_refs: tuple[str, ...]
    uncertainty_profile_ref: str
    requirement: str
    reason: str
    missing_evidence_or_decision: str
    reopen_policy: Mapping[str, str]
    closure_condition: str
    payload_digest: str


class MarkdownComposeInputView(Protocol):
    artifact_id: str
    claim_closure: tuple[str, ...]
    evidence_relation_closure: tuple[str, ...]
    citation_closure: tuple[str, ...]
    payload_digest: str


class InternalExportInputView(Protocol):
    delivery_intent_id: str
    artifact_ref: str
    audience: str
    approval_refs: tuple[str, ...]
    idempotency_key: str
    payload_digest: str


@dataclass(frozen=True, slots=True)
class InterpreterSuccess(Generic[T]):
    """A typed, observed successor-native result."""

    value: T
    disposition: EffectDisposition = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class InterpreterFailure:
    """A definite failure whose requested effect did not succeed."""

    code: str
    message: str
    retryable: bool = False
    disposition: EffectDisposition = "FAILED"


@dataclass(frozen=True, slots=True)
class InterpreterOutcomeUnknown:
    """An effect may have happened and must be reconciled before retry."""

    attempt_ref: str
    readback_locator: str
    message: str
    disposition: EffectDisposition = "OUTCOME_UNKNOWN"


InterpreterOutcome: TypeAlias = (
    InterpreterSuccess[T] | InterpreterFailure | InterpreterOutcomeUnknown
)


@dataclass(frozen=True, slots=True)
class CapturedDocumentValue:
    """Submission-time runtime input; never a Research Ledger object."""

    exact_bytes: bytes
    snapshot: CapturedMaterialSnapshot
    exact_bytes_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.exact_bytes, bytes):
            raise TypeError("CapturedDocumentValue.exact_bytes must be bytes")
        require_hex64(
            self.exact_bytes_digest,
            "CapturedDocumentValue.exact_bytes_digest",
        )
        if _bytes_digest(self.exact_bytes) != self.exact_bytes_digest:
            raise ValueError("CapturedDocumentValue exact bytes digest mismatch")


@dataclass(frozen=True, slots=True)
class ClaimOrGapOutput:
    """Keep evidence and provenance visible for both branch outcomes."""

    value: ClaimOrGap
    support_relation_refs: tuple[str, ...]
    contradiction_relation_refs: tuple[str, ...]
    uncertainty_profile_ref: str
    provenance_closure_digest: str

    def __post_init__(self) -> None:
        require_hex64(
            self.provenance_closure_digest,
            "ClaimOrGapOutput.provenance_closure_digest",
        )


@dataclass(frozen=True, slots=True)
class ComposedMarkdownArtifact:
    exact_bytes: bytes
    exact_bytes_digest: str
    artifact: ResearchArtifact

    def __post_init__(self) -> None:
        if not isinstance(self.exact_bytes, bytes):
            raise TypeError("ComposedMarkdownArtifact.exact_bytes must be bytes")
        require_hex64(
            self.exact_bytes_digest,
            "ComposedMarkdownArtifact.exact_bytes_digest",
        )
        if _bytes_digest(self.exact_bytes) != self.exact_bytes_digest:
            raise ValueError("ComposedMarkdownArtifact exact bytes digest mismatch")
        if self.artifact.content_ref != f"sha256:{self.exact_bytes_digest}":
            raise ValueError("ResearchArtifact content_ref does not bind exact bytes")


@dataclass(frozen=True, slots=True)
class VerifiedDeliveryBinding:
    """Exact result of current approval and authority validation.

    The interpreter does not construct this value from caller claims.  A
    ``DeliveryApprovalAuthorityPort`` must return it after reading the current
    approval and authority owners.
    """

    delivery_intent_digest: str
    approved_payload_digest: str
    approval_refs: tuple[str, ...]
    approval_epoch: int
    authority_digest: str
    authority_epoch: int
    validated_at: datetime
    expires_at: datetime
    binding_digest: str

    def __post_init__(self) -> None:
        for field_name in (
            "delivery_intent_digest",
            "approved_payload_digest",
            "authority_digest",
            "binding_digest",
        ):
            require_hex64(getattr(self, field_name), field_name)
        if _all_zero_digest(self.authority_digest):
            raise ValueError("verified delivery authority must not be all-zero")
        if self.approval_epoch < 0 or self.authority_epoch < 0:
            raise ValueError("approval and authority epochs must be non-negative")
        if not self.approval_refs:
            raise ValueError("verified delivery requires approval refs")
        if self.validated_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("delivery validation timestamps must be timezone-aware")
        if self.expires_at <= self.validated_at:
            raise ValueError("verified delivery binding is already expired")
        expected = digest_dataclass(self, ("binding_digest",))
        if self.binding_digest != expected:
            raise ValueError("verified delivery binding digest mismatch")

    @classmethod
    def from_content(cls, **values: object) -> VerifiedDeliveryBinding:
        provisional = cls.__new__(cls)
        for field_name, value in values.items():
            object.__setattr__(provisional, field_name, value)
        object.__setattr__(provisional, "binding_digest", "0" * 64)
        return cls(
            **values,
            binding_digest=digest_dataclass(provisional, ("binding_digest",)),
        )


@runtime_checkable
class DeliveryApprovalAuthorityPort(Protocol):
    """Validate current, exact DeliveryIntent, approval, and authority owners."""

    def require_current(
        self,
        scope: RuntimeScopeView,
        payload: InternalExportInputView,
        intent: DeliveryIntent,
        artifact: ResearchArtifact,
        *,
        now: datetime,
    ) -> VerifiedDeliveryBinding: ...


@dataclass(frozen=True, slots=True)
class InternalExportObservation:
    """Authoritative readback from the project-scoped internal receipt store."""

    idempotency_key: str
    delivery_intent_digest: str
    artifact_bytes_digest: str
    attempt_ref: str
    provider_locator: str
    outcome_time: datetime
    receipt_digest: str

    def __post_init__(self) -> None:
        require_hex64(
            self.delivery_intent_digest,
            "InternalExportObservation.delivery_intent_digest",
        )
        require_hex64(
            self.artifact_bytes_digest,
            "InternalExportObservation.artifact_bytes_digest",
        )
        require_hex64(
            self.receipt_digest,
            "InternalExportObservation.receipt_digest",
        )
        if self.outcome_time.tzinfo is None:
            raise ValueError("internal export outcome_time must be timezone-aware")
        expected_locator = f"internal://export/sha256/{self.artifact_bytes_digest}"
        if self.provider_locator != expected_locator:
            raise ValueError("internal export locator is not content-addressed")
        expected_receipt = digest_dataclass(self, ("receipt_digest",))
        if self.receipt_digest != expected_receipt:
            raise ValueError("internal export receipt digest mismatch")

    @classmethod
    def from_content(cls, **values: object) -> InternalExportObservation:
        provisional = cls.__new__(cls)
        for field_name, value in values.items():
            object.__setattr__(provisional, field_name, value)
        object.__setattr__(provisional, "receipt_digest", "0" * 64)
        return cls(
            **values,
            receipt_digest=digest_dataclass(provisional, ("receipt_digest",)),
        )


class InternalExportRejected(RuntimeError):
    """The internal export definitely did not start."""


class InternalExportOutcomeUncertain(RuntimeError):
    """The export may have happened; callers must reconcile by readback."""

    def __init__(self, message: str, *, readback_locator: str) -> None:
        super().__init__(message)
        self.readback_locator = readback_locator


@runtime_checkable
class InternalExportPort(Protocol):
    """Atomic write-once internal export plus authoritative readback."""

    def readback(
        self,
        scope: RuntimeScopeView,
        *,
        idempotency_key: str,
        delivery_intent_digest: str,
        artifact_bytes_digest: str,
    ) -> InternalExportObservation | None: ...

    def write_once(
        self,
        scope: RuntimeScopeView,
        *,
        idempotency_key: str,
        delivery_intent_digest: str,
        artifact_bytes_digest: str,
        exact_bytes: bytes,
        attempt_ref: str,
    ) -> InternalExportObservation: ...


class FirstSpecimenInterpreters:
    """Capability-local realization of the six frozen specimen operations."""

    def __init__(
        self,
        *,
        delivery_validator: DeliveryApprovalAuthorityPort | None = None,
        internal_export: InternalExportPort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._delivery_validator = delivery_validator
        self._internal_export = internal_export
        self._clock = clock or (lambda: datetime.now(UTC))

    def capture_document_snapshot(
        self,
        payload: CaptureDocumentSnapshotInputView,
        captured: CapturedDocumentValue,
    ) -> InterpreterOutcome[CapturedDocumentValue]:
        """Validate submission-captured bytes without re-reading Document."""

        try:
            snapshot = captured.snapshot
            if snapshot.document_id != payload.document_id:
                raise ValueError("captured document identity drift")
            if not isinstance(captured.exact_bytes, bytes):
                raise TypeError("captured value replay returned non-bytes")
            exact_bytes = bytes(captured.exact_bytes)
            raw_digest = _bytes_digest(exact_bytes)
            if raw_digest != payload.content_sha256_hex or (
                raw_digest != captured.exact_bytes_digest
            ):
                raise ValueError("captured exact bytes digest drift")
            if len(exact_bytes) != payload.byte_size:
                raise ValueError("captured exact byte size drift")
            expected_updated_at = _parse_datetime(payload.observed_updated_at)
            if snapshot.observed_updated_at != expected_updated_at:
                raise ValueError("captured updated_at drift")
            if snapshot.byte_size != len(exact_bytes):
                raise ValueError("captured snapshot byte size drift")
            if (
                snapshot.observed_text_hash is not None
                and snapshot.observed_text_hash != payload.content_sha256_hex
            ):
                raise ValueError("captured text_hash drift")
            return InterpreterSuccess(
                CapturedDocumentValue(
                    exact_bytes=exact_bytes,
                    snapshot=snapshot,
                    exact_bytes_digest=raw_digest,
                )
            )
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="DOCUMENT_OBSERVATION_MISMATCH",
                message=str(exc),
                retryable=False,
            )

    def read_canonical_ref(
        self,
        payload: CanonicalReadInputView,
        captured: CapturedDocumentValue,
    ) -> InterpreterOutcome[MaterialRef]:
        """Turn a captured runtime input into an immutable MaterialRef."""

        try:
            if not payload.source_ref:
                raise ValueError("source_ref is required")
            return InterpreterSuccess(
                derive_material_ref(
                    source_ref=payload.source_ref,
                    snapshot=captured.snapshot,
                    owner_id=payload.owner_id,
                    locator=payload.locator,
                    observed_at=payload.observed_at,
                )
            )
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="INVALID_CAPTURED_MATERIAL",
                message=str(exc),
            )

    def qualify_evidence(
        self,
        payload: EvidenceQualificationInputView,
        *,
        project_key: str,
        provenance_closure_digest: str,
        validity: Validity,
        claim_ref: str | None = None,
        source_time: datetime | None = None,
        observed_at: datetime | None = None,
    ) -> InterpreterOutcome[EvidenceQualification]:
        """Construct the single canonical relation; never an object duplicate."""

        try:
            require_hex64(
                provenance_closure_digest,
                "EvidenceQualification.provenance_closure_digest",
            )
            qualification = EvidenceQualification(
                qualification_id=payload.qualification_id,
                project_key=project_key,
                material_ref=payload.material_ref,
                inquiry_ref=payload.inquiry_ref,
                claim_ref=claim_ref,
                direction=payload.direction,
                scope_statement_ref=payload.scope_statement_ref,
                uncertainty_profile_ref=payload.uncertainty_profile_ref,
                verifier_profile_ref=payload.verifier_profile_ref,
                provenance_closure_digest=provenance_closure_digest,
                validity=validity,
                source_time=source_time,
                observed_at=observed_at,
            )
            if qualification.RELATION_STORAGE != "research_relations_only":
                raise ValueError("qualification must remain relation-only")
            return InterpreterSuccess(qualification)
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="INVALID_EVIDENCE_QUALIFICATION",
                message=str(exc),
            )

    def form_claim_or_open_gap(
        self,
        payload: ClaimOrGapInputView,
        *,
        provenance_closure_digest: str,
    ) -> InterpreterOutcome[ClaimOrGapOutput]:
        """Form one claim or one explicit gap without hiding evidence context."""

        try:
            require_hex64(
                provenance_closure_digest,
                "ClaimOrGapOutput.provenance_closure_digest",
            )
            gap_requested = bool(
                payload.requirement
                or payload.reason
                or payload.missing_evidence_or_decision
                or payload.reopen_policy
                or payload.closure_condition
            )
            if gap_requested:
                required = {
                    "requirement": payload.requirement,
                    "reason": payload.reason,
                    "missing_evidence_or_decision": (
                        payload.missing_evidence_or_decision
                    ),
                    "reopen_policy": payload.reopen_policy,
                    "closure_condition": payload.closure_condition,
                }
                missing = [name for name, value in required.items() if not value]
                if missing:
                    raise ValueError("gap fields are incomplete: " + ", ".join(missing))
                value: ClaimOrGap = Gap(
                    gap_id=payload.claim_or_gap_id,
                    inquiry_ref=payload.inquiry_ref,
                    requirement=payload.requirement,
                    reason=payload.reason,
                    closure_condition=payload.closure_condition,
                    reopen_policy={
                        **dict(payload.reopen_policy),
                        "support_relation_refs": list(payload.support_relation_refs),
                        "contradiction_relation_refs": list(
                            payload.contradiction_relation_refs
                        ),
                        "uncertainty_profile_ref": (payload.uncertainty_profile_ref),
                        "provenance_closure_digest": (provenance_closure_digest),
                    },
                    missing_evidence_or_decision=(payload.missing_evidence_or_decision),
                )
            else:
                if not payload.statement_ref:
                    raise ValueError("claim statement_ref is required")
                if not payload.uncertainty_profile_ref:
                    raise ValueError("claim uncertainty_profile_ref is required")
                if not (
                    payload.support_relation_refs or payload.contradiction_relation_refs
                ):
                    raise ValueError("claim requires an evidence relation")
                value = Claim(
                    claim_id=payload.claim_or_gap_id,
                    statement_ref=payload.statement_ref,
                    support_relation_refs=payload.support_relation_refs,
                    contradiction_relation_refs=(payload.contradiction_relation_refs),
                    uncertainty_profile_ref=payload.uncertainty_profile_ref,
                    lifecycle_state="DRAFT",
                    scope={
                        "inquiry_ref": payload.inquiry_ref,
                        "provenance_closure_digest": (provenance_closure_digest),
                    },
                )
            return InterpreterSuccess(
                ClaimOrGapOutput(
                    value=value,
                    support_relation_refs=payload.support_relation_refs,
                    contradiction_relation_refs=(payload.contradiction_relation_refs),
                    uncertainty_profile_ref=payload.uncertainty_profile_ref,
                    provenance_closure_digest=provenance_closure_digest,
                )
            )
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="INVALID_CLAIM_OR_GAP",
                message=str(exc),
            )

    def compose_markdown(
        self,
        payload: MarkdownComposeInputView,
        outcome: ClaimOrGapOutput,
        *,
        qualifications: tuple[EvidenceQualification, ...],
        materials: tuple[MaterialRef, ...],
    ) -> InterpreterOutcome[ComposedMarkdownArtifact]:
        """Generate deterministic Markdown and bind its exact citation closure."""

        try:
            expected_outcome_ref = _claim_or_gap_ref(outcome.value)
            if payload.claim_closure != (expected_outcome_ref,):
                raise ValueError("artifact outcome closure is not exact")
            qualification_refs = tuple(
                qualification.qualification_id for qualification in qualifications
            )
            if payload.evidence_relation_closure != qualification_refs:
                raise ValueError("artifact qualification closure is not exact")
            material_refs = tuple(material.material_ref_id for material in materials)
            if payload.citation_closure != material_refs:
                raise ValueError("artifact citation closure is not exact")
            if not material_refs:
                raise ValueError("artifact citation closure must not be empty")
            material_ref_set = set(material_refs)
            if any(
                qualification.material_ref not in material_ref_set
                for qualification in qualifications
            ):
                raise ValueError(
                    "qualification refers outside artifact citation closure"
                )

            exact_bytes = _render_markdown(
                payload,
                outcome,
                qualifications,
                materials,
            )
            raw_digest = _bytes_digest(exact_bytes)
            artifact = ResearchArtifact(
                artifact_id=payload.artifact_id,
                content_ref=f"sha256:{raw_digest}",
                content_digest=None,
                claim_closure=payload.claim_closure,
                evidence_relation_closure=(payload.evidence_relation_closure),
                citation_closure=payload.citation_closure,
                format="markdown",
                revision=1,
                lifecycle_state="DRAFT",
            )
            return InterpreterSuccess(
                ComposedMarkdownArtifact(
                    exact_bytes=exact_bytes,
                    exact_bytes_digest=raw_digest,
                    artifact=artifact,
                )
            )
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="INVALID_ARTIFACT_CLOSURE",
                message=str(exc),
            )

    def internal_export(
        self,
        scope: RuntimeScopeView,
        payload: InternalExportInputView,
        *,
        delivery_intent: DeliveryIntent,
        artifact: ResearchArtifact,
        artifact_bytes: bytes,
        attempt_ref: str,
    ) -> InterpreterOutcome[DeliveryReceiptRef]:
        """Perform one approval-gated internal export with readback-first replay."""

        if self._delivery_validator is None or self._internal_export is None:
            return InterpreterFailure(
                code="INTERPRETER_UNAVAILABLE",
                message="delivery validator and internal export ports are required",
                retryable=False,
            )

        now = self._clock()
        try:
            _require_delivery_input(
                payload,
                delivery_intent,
                artifact,
                artifact_bytes,
            )
            verified = self._delivery_validator.require_current(
                scope,
                payload,
                delivery_intent,
                artifact,
                now=now,
            )
            _require_verified_delivery(
                payload,
                delivery_intent,
                verified,
                now=now,
            )
        except (TypeError, ValueError, PermissionError) as exc:
            return InterpreterFailure(
                code="DELIVERY_AUTHORITY_OR_APPROVAL_INVALID",
                message=str(exc),
                retryable=False,
            )

        intent_digest = delivery_intent.content_digest
        assert intent_digest is not None  # DeliveryIntent finalizes it
        artifact_bytes_digest = _bytes_digest(artifact_bytes)
        readback_locator = (
            f"internal-readback://{scope.project_scope.scope_digest}/"
            f"{payload.idempotency_key}"
        )

        try:
            observed = self._internal_export.readback(
                scope,
                idempotency_key=payload.idempotency_key,
                delivery_intent_digest=intent_digest,
                artifact_bytes_digest=artifact_bytes_digest,
            )
        # Any readback transport/backend exception leaves existence unknown;
        # dispatch is therefore forbidden until reconciliation.
        except Exception as exc:  # noqa: BLE001
            return InterpreterOutcomeUnknown(
                attempt_ref=attempt_ref,
                readback_locator=readback_locator,
                message=f"authoritative pre-effect readback unavailable: {exc}",
            )

        if observed is not None:
            return _receipt_from_observation(
                observed,
                payload=payload,
                delivery_intent=delivery_intent,
                artifact_bytes_digest=artifact_bytes_digest,
                attempt_ref=attempt_ref,
            )

        try:
            emitted = self._internal_export.write_once(
                scope,
                idempotency_key=payload.idempotency_key,
                delivery_intent_digest=intent_digest,
                artifact_bytes_digest=artifact_bytes_digest,
                exact_bytes=bytes(artifact_bytes),
                attempt_ref=attempt_ref,
            )
        except InternalExportRejected as exc:
            return InterpreterFailure(
                code="INTERNAL_EXPORT_REJECTED",
                message=str(exc),
                retryable=False,
            )
        except InternalExportOutcomeUncertain as exc:
            return InterpreterOutcomeUnknown(
                attempt_ref=attempt_ref,
                readback_locator=exc.readback_locator,
                message=str(exc),
            )
        # An unclassified exception after crossing the write boundary may have
        # happened after the effect and is conservatively outcome-unknown.
        except Exception as exc:  # noqa: BLE001
            return InterpreterOutcomeUnknown(
                attempt_ref=attempt_ref,
                readback_locator=readback_locator,
                message=f"internal export raised after dispatch boundary: {exc}",
            )

        try:
            authoritative = self._internal_export.readback(
                scope,
                idempotency_key=payload.idempotency_key,
                delivery_intent_digest=intent_digest,
                artifact_bytes_digest=artifact_bytes_digest,
            )
        # Post-effect readback errors cannot be downgraded to definite failure.
        except Exception as exc:  # noqa: BLE001
            return InterpreterOutcomeUnknown(
                attempt_ref=attempt_ref,
                readback_locator=readback_locator,
                message=f"post-export authoritative readback unavailable: {exc}",
            )
        if authoritative is None:
            return InterpreterOutcomeUnknown(
                attempt_ref=attempt_ref,
                readback_locator=readback_locator,
                message="internal export returned without authoritative readback",
            )
        if authoritative != emitted:
            return InterpreterOutcomeUnknown(
                attempt_ref=attempt_ref,
                readback_locator=readback_locator,
                message="internal export result and authoritative readback differ",
            )
        return _receipt_from_observation(
            authoritative,
            payload=payload,
            delivery_intent=delivery_intent,
            artifact_bytes_digest=artifact_bytes_digest,
            attempt_ref=attempt_ref,
        )


def _require_delivery_input(
    payload: InternalExportInputView,
    intent: DeliveryIntent,
    artifact: ResearchArtifact,
    artifact_bytes: bytes,
) -> None:
    if not isinstance(artifact_bytes, bytes):
        raise TypeError("artifact_bytes must be exact bytes")
    if artifact.lifecycle_state != "ADMITTED":
        raise ValueError("delivery requires an admitted artifact")
    expected_content_ref = f"sha256:{_bytes_digest(artifact_bytes)}"
    if artifact.content_ref != expected_content_ref:
        raise ValueError("artifact bytes do not match content_ref")
    exact_ref = artifact_exact_ref(artifact)
    expected = (
        (payload.delivery_intent_id, intent.delivery_intent_id, "intent id"),
        (payload.artifact_ref, intent.artifact_ref, "artifact ref"),
        (payload.artifact_ref, exact_ref, "exact artifact ref"),
        (payload.audience, intent.audience, "audience"),
        (payload.approval_refs, intent.approval_refs, "approval refs"),
        (payload.idempotency_key, intent.idempotency_key, "idempotency key"),
    )
    drift = [label for left, right, label in expected if left != right]
    if drift:
        raise ValueError("delivery intent drift: " + ", ".join(drift))
    if intent.content_digest is None:
        raise ValueError("delivery intent content digest is required")
    require_hex64(intent.authority_digest, "DeliveryIntent.authority_digest")
    if _all_zero_digest(intent.authority_digest):
        raise ValueError("all-zero delivery authority is forbidden")


def _require_verified_delivery(
    payload: InternalExportInputView,
    intent: DeliveryIntent,
    verified: VerifiedDeliveryBinding,
    *,
    now: datetime,
) -> None:
    if intent.content_digest is None:
        raise ValueError("delivery intent content digest is required")
    if verified.delivery_intent_digest != intent.content_digest:
        raise PermissionError("validated delivery intent digest drift")
    if verified.approved_payload_digest != intent.content_digest:
        raise PermissionError("approval payload digest drift")
    if verified.approval_refs != payload.approval_refs:
        raise PermissionError("approval ref drift")
    if verified.authority_digest != intent.authority_digest:
        raise PermissionError("authority digest drift")
    if verified.expires_at <= now:
        raise PermissionError("approval or authority expired")


def _receipt_from_observation(
    observation: InternalExportObservation,
    *,
    payload: InternalExportInputView,
    delivery_intent: DeliveryIntent,
    artifact_bytes_digest: str,
    attempt_ref: str,
) -> InterpreterOutcome[DeliveryReceiptRef]:
    intent_digest = delivery_intent.content_digest
    assert intent_digest is not None
    expected = (
        (observation.idempotency_key, payload.idempotency_key, "idempotency key"),
        (
            observation.delivery_intent_digest,
            intent_digest,
            "delivery intent digest",
        ),
        (
            observation.artifact_bytes_digest,
            artifact_bytes_digest,
            "artifact bytes digest",
        ),
    )
    drift = [label for left, right, label in expected if left != right]
    if drift:
        return InterpreterFailure(
            code="INTERNAL_EXPORT_READBACK_CONFLICT",
            message="authoritative readback drift: " + ", ".join(drift),
            retryable=False,
        )
    return InterpreterSuccess(
        DeliveryReceiptRef(
            receipt_ref=f"receipt:sha256:{observation.receipt_digest}",
            delivery_intent_ref=delivery_intent.delivery_intent_id,
            attempt_ref=observation.attempt_ref,
            provider_locator=observation.provider_locator,
            receipt_digest=observation.receipt_digest,
            outcome_time=observation.outcome_time,
        )
    )


def _render_markdown(
    payload: MarkdownComposeInputView,
    outcome: ClaimOrGapOutput,
    qualifications: tuple[EvidenceQualification, ...],
    materials: tuple[MaterialRef, ...],
) -> bytes:
    value = outcome.value
    value_kind = "Claim" if isinstance(value, Claim) else "Gap"
    lines = [
        f"# Research Artifact `{payload.artifact_id}`",
        "",
        "## Research outcome",
        "",
        f"- Kind: `{value_kind}`",
        f"- Reference: `{_claim_or_gap_ref(value)}`",
        f"- Provenance closure: `{outcome.provenance_closure_digest}`",
        f"- Uncertainty profile: `{outcome.uncertainty_profile_ref}`",
        "",
        "## Evidence qualifications",
        "",
    ]
    for qualification in qualifications:
        lines.append(
            "- "
            f"`{qualification.qualification_id}` "
            f"{qualification.direction} material "
            f"`{qualification.material_ref}`; provenance "
            f"`{qualification.provenance_closure_digest}`"
        )
    lines.extend(["", "## Citation closure", ""])
    for material in materials:
        lines.append(
            "- "
            f"`{material.material_ref_id}` from `{material.source_ref}` at "
            f"`{material.snapshot.value_ref}`; provenance "
            f"`{material.provenance_digest}`"
        )
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _claim_or_gap_ref(value: ClaimOrGap) -> str:
    if isinstance(value, Claim):
        return value.claim_id
    if isinstance(value, Gap):
        return value.gap_id
    raise TypeError("outcome must contain Claim or Gap")


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _all_zero_digest(value: str) -> bool:
    return value == "0" * 64


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("observed_updated_at must be timezone-aware")
    return parsed
