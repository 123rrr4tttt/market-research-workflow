"""Read-only replay of legacy capability-call records into attempt evidence.

The replay builds exact ``EffectAttemptObservation`` values for the existing
reconciliation owner.  Attempt identity is never caller-chosen: it comes from
an ``ExactLegacyAttemptBinding`` that closes over the durable call id,
external idempotency key, provider-readback locator, capability, assignment,
and the durable attempt identity.  Replay, reconciler use, and
``PostgresReconciliationOwner`` adoption validate those fields, not
``attempt_id`` alone.  Missing or ambiguous legacy results project as
``OUTCOME_UNKNOWN`` and stay non-terminal until authoritative resolution.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    Digest,
    FrozenContract,
    RecoveryBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import (
    ClaimBinding,
    derive_attempt_id,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectAttemptObservation,
)
from app.successor_runtime.runtime.transitions import EffectDisposition


class LegacyEffectAttemptReplayError(RuntimeError):
    """Base class for fail-closed legacy attempt replay."""


class ContradictoryAttemptReplay(LegacyEffectAttemptReplayError):
    """The same attempt identity produced conflicting legacy dispositions."""


class IncompleteLegacyAttemptRecord(LegacyEffectAttemptReplayError):
    """A legacy record cannot form an exact attempt observation."""


class LegacyAttemptBindingMismatch(LegacyEffectAttemptReplayError):
    """Durable attempt binding fields disagree with the legacy observation."""


class LegacyInterpreterProfile(FrozenContract):
    schema_version: Literal["mrw.migration.legacy-interpreter-profile.v1"] = (
        "mrw.migration.legacy-interpreter-profile.v1"
    )
    interpreter_id: str = Field(min_length=1)
    interpreter_version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    profile_digest: Digest

    @model_validator(mode="after")
    def validate_profile(self) -> LegacyInterpreterProfile:
        expected = canonical_digest(self, exclude_fields={"profile_digest"})
        if self.profile_digest != expected:
            raise ValueError("legacy interpreter profile_digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacyInterpreterProfile:
        if "profile_digest" in content:
            raise ValueError("profile_digest is derived, not caller supplied")
        provisional = cls.model_construct(**content, profile_digest="0" * 64)
        return cls(
            **content,
            profile_digest=canonical_digest(
                provisional,
                exclude_fields={"profile_digest"},
            ),
        )


class ExactLegacyAttemptBinding(FrozenContract):
    """Durable identity closing call, capability, assignment, and attempt."""

    schema_version: Literal["mrw.migration.exact-legacy-attempt-binding.v1"] = (
        "mrw.migration.exact-legacy-attempt-binding.v1"
    )
    call_id: str = Field(min_length=1)
    external_idempotency_key: str = Field(min_length=1)
    authoritative_readback_locator: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    assignment_digest: Digest
    handler_binding_digest: Digest
    interpreter_profile_digest: Digest
    attempt_id: Digest
    binding_digest: Digest

    @model_validator(mode="after")
    def validate_binding(self) -> ExactLegacyAttemptBinding:
        expected = canonical_digest(self, exclude_fields={"binding_digest"})
        if self.binding_digest != expected:
            raise ValueError("exact legacy attempt binding_digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> ExactLegacyAttemptBinding:
        if "binding_digest" in content:
            raise ValueError("binding_digest is derived, not caller supplied")
        provisional = cls.model_construct(**content, binding_digest="0" * 64)
        return cls(
            **content,
            binding_digest=canonical_digest(
                provisional,
                exclude_fields={"binding_digest"},
            ),
        )

    @classmethod
    def from_claim(
        cls,
        claim: ClaimBinding,
        *,
        call_id: str,
        external_idempotency_key: str,
        authoritative_readback_locator: str,
        capability_id: str,
    ) -> ExactLegacyAttemptBinding:
        if claim.interpreter_profile_digest is None:
            raise LegacyAttemptBindingMismatch(
                "durable claim lacks the original interpreter profile digest"
            )
        return cls.from_content(
            call_id=call_id,
            external_idempotency_key=external_idempotency_key,
            authoritative_readback_locator=authoritative_readback_locator,
            capability_id=capability_id,
            assignment_digest=claim.assignment_digest,
            handler_binding_digest=claim.handler_binding_digest,
            interpreter_profile_digest=claim.interpreter_profile_digest,
            attempt_id=claim.attempt_id,
        )

    @classmethod
    def from_derived_attempt(
        cls,
        assignment: RuntimeAssignment,
        *,
        authorization_digest: str,
        call_id: str,
        external_idempotency_key: str,
        authoritative_readback_locator: str,
        capability_id: str,
    ) -> ExactLegacyAttemptBinding:
        attempt_id = derive_attempt_id(
            assignment,
            authorization_digest=authorization_digest,
            handler_realization_digest=assignment.handler_binding_digest,
        )
        binding = assignment.handler_binding
        return cls.from_content(
            call_id=call_id,
            external_idempotency_key=external_idempotency_key,
            authoritative_readback_locator=authoritative_readback_locator,
            capability_id=capability_id,
            assignment_digest=assignment.assignment_digest,
            handler_binding_digest=assignment.handler_binding_digest,
            interpreter_profile_digest=binding.interpreter_profile_digest,
            attempt_id=attempt_id,
        )

    def validate_against_claim(
        self,
        claim: ClaimBinding,
        assignment: RuntimeAssignment,
    ) -> None:
        claim.validate_against(assignment)
        if self.attempt_id != claim.attempt_id:
            raise LegacyAttemptBindingMismatch("exact binding attempt identity drift")
        if self.assignment_digest != claim.assignment_digest:
            raise LegacyAttemptBindingMismatch("exact binding assignment drift")
        if self.handler_binding_digest != claim.handler_binding_digest:
            raise LegacyAttemptBindingMismatch(
                "exact binding handler realization drift"
            )
        if (
            claim.interpreter_profile_digest is None
            or self.interpreter_profile_digest != claim.interpreter_profile_digest
        ):
            raise LegacyAttemptBindingMismatch(
                "exact binding interpreter profile drift"
            )
        if self.capability_id != assignment.capability_id:
            raise LegacyAttemptBindingMismatch("exact binding capability drift")

    def validate_against_assignment(
        self,
        assignment: RuntimeAssignment,
        recovery: RecoveryBinding,
    ) -> None:
        if self.assignment_digest != assignment.assignment_digest:
            raise LegacyAttemptBindingMismatch("exact binding assignment drift")
        if self.handler_binding_digest != assignment.handler_binding_digest:
            raise LegacyAttemptBindingMismatch(
                "exact binding handler realization drift"
            )
        if (
            recovery.interpreter_profile_digest is None
            or self.interpreter_profile_digest != recovery.interpreter_profile_digest
        ):
            raise LegacyAttemptBindingMismatch(
                "exact binding interpreter profile drift"
            )
        if self.capability_id != assignment.capability_id:
            raise LegacyAttemptBindingMismatch("exact binding capability drift")


class LegacyAttemptReplayEvidence(FrozenContract):
    """One replayed legacy observation bound to its durable attempt identity."""

    schema_version: Literal["mrw.migration.legacy-attempt-evidence.v1"] = (
        "mrw.migration.legacy-attempt-evidence.v1"
    )
    binding: ExactLegacyAttemptBinding
    observation: EffectAttemptObservation
    observed_at: datetime
    evidence_digest: Digest

    @model_validator(mode="after")
    def validate_evidence(self) -> LegacyAttemptReplayEvidence:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("legacy attempt evidence observed_at must be aware")
        observation = self.observation
        if observation.attempt_id != self.binding.attempt_id:
            raise LegacyAttemptBindingMismatch("evidence attempt identity drift")
        if observation.assignment_digest != self.binding.assignment_digest:
            raise LegacyAttemptBindingMismatch("evidence assignment drift")
        if observation.handler_binding_digest != self.binding.handler_binding_digest:
            raise LegacyAttemptBindingMismatch("evidence handler realization drift")
        if observation.interpreter_profile_digest != (
            self.binding.interpreter_profile_digest
        ):
            raise LegacyAttemptBindingMismatch("evidence interpreter profile drift")
        if observation.external_idempotency_key != (
            self.binding.external_idempotency_key
        ):
            raise LegacyAttemptBindingMismatch("evidence idempotency drift")
        if observation.authoritative_readback_locator != (
            self.binding.authoritative_readback_locator
        ):
            raise LegacyAttemptBindingMismatch("evidence readback locator drift")
        expected = canonical_digest(self, exclude_fields={"evidence_digest"})
        if self.evidence_digest != expected:
            raise ValueError("legacy attempt evidence_digest mismatch")
        return self


_SUCCEEDED_STATES = frozenset({"success", "succeeded", "completed", "finished", "done"})
_FAILED_STATES = frozenset(
    {"failed", "failure", "error", "cancelled", "canceled", "revoked"}
)


def _legacy_disposition(status: str | None) -> EffectDisposition:
    normalized = str(status or "").strip().lower()
    if normalized in _SUCCEEDED_STATES:
        return EffectDisposition.SUCCEEDED
    if normalized in _FAILED_STATES:
        return EffectDisposition.FAILED
    return EffectDisposition.OUTCOME_UNKNOWN


def _required_binding_field(legacy_record: Mapping[str, object], key: str) -> str:
    value = legacy_record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IncompleteLegacyAttemptRecord(
            f"legacy attempt record requires non-empty {key!r}"
        )
    return value.strip()


def replay_effect_attempt(
    legacy_record: Mapping[str, object],
    *,
    assignment: RuntimeAssignment,
    recovery: RecoveryBinding,
    profile: LegacyInterpreterProfile,
    binding: ExactLegacyAttemptBinding,
    observed_at: datetime,
) -> LegacyAttemptReplayEvidence:
    """Replay one legacy call and validate every durable binding field."""

    if not isinstance(legacy_record, Mapping):
        raise IncompleteLegacyAttemptRecord("legacy record must be a mapping")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("legacy attempt observed_at must be timezone-aware")
    if assignment.assignment_kind not in {
        AssignmentKind.INTERPRET,
        AssignmentKind.VERIFY_ADMIT,
    }:
        raise LegacyEffectAttemptReplayError(
            "legacy attempt replay requires an INTERPRET/VERIFY_ADMIT assignment"
        )
    if recovery.interpreter_profile_digest is None:
        raise LegacyEffectAttemptReplayError(
            "legacy attempt replay requires the original interpreter profile digest"
        )
    if recovery.interpreter_profile_digest != profile.profile_digest:
        raise LegacyEffectAttemptReplayError(
            "legacy attempt replay profile digest drift"
        )
    binding.validate_against_assignment(assignment, recovery)
    call_id = _required_binding_field(legacy_record, "call_id")
    external_idempotency_key = str(
        legacy_record.get("idempotency_key") or call_id
    ).strip()
    if not external_idempotency_key:
        raise IncompleteLegacyAttemptRecord(
            "legacy attempt record requires call_id or idempotency_key"
        )
    locator = str(
        legacy_record.get("authoritative_readback_locator")
        or legacy_record.get("provider_locator")
        or f"legacy:capability-call:{external_idempotency_key}"
    ).strip()
    capability_id = str(
        legacy_record.get("capability_id") or assignment.capability_id
    ).strip()
    if call_id != binding.call_id:
        raise LegacyAttemptBindingMismatch("legacy call_id is unrelated to the binding")
    if external_idempotency_key != binding.external_idempotency_key:
        raise LegacyAttemptBindingMismatch("legacy idempotency key binding drift")
    if locator != binding.authoritative_readback_locator:
        raise LegacyAttemptBindingMismatch("legacy readback locator binding drift")
    if capability_id != binding.capability_id:
        raise LegacyAttemptBindingMismatch("legacy capability binding drift")
    status = legacy_record.get("status")
    if status is not None and not isinstance(status, str):
        raise IncompleteLegacyAttemptRecord("legacy attempt status must be a string")
    observation = EffectAttemptObservation(
        attempt_id=binding.attempt_id,
        assignment_digest=binding.assignment_digest,
        handler_binding_digest=binding.handler_binding_digest,
        interpreter_profile_digest=binding.interpreter_profile_digest,
        interpreter_id=profile.interpreter_id,
        interpreter_version=profile.interpreter_version,
        provider_id=profile.provider_id,
        provider_version=profile.provider_version,
        external_idempotency_key=binding.external_idempotency_key,
        authoritative_readback_locator=binding.authoritative_readback_locator,
        disposition=_legacy_disposition(status),
    )
    provisional = LegacyAttemptReplayEvidence.model_construct(
        binding=binding,
        observation=observation,
        observed_at=observed_at,
        evidence_digest="0" * 64,
    )
    values = provisional.model_dump(mode="python")
    values.pop("evidence_digest")
    return LegacyAttemptReplayEvidence(
        **values,
        evidence_digest=canonical_digest(
            provisional,
            exclude_fields={"evidence_digest"},
        ),
    )


def require_exact_adoption(
    binding: ExactLegacyAttemptBinding,
    *,
    claim: ClaimBinding,
    assignment: RuntimeAssignment,
    readback: AuthoritativeEffectReadback,
) -> None:
    """Validate durable binding fields before the existing owner adopts."""

    binding.validate_against_claim(claim, assignment)
    if not isinstance(readback, AuthoritativeEffectReadback):
        raise LegacyAttemptBindingMismatch(
            "adoption requires typed authoritative readback"
        )
    if readback.attempt_id != binding.attempt_id:
        raise LegacyAttemptBindingMismatch("readback attempt identity drift")
    if (
        readback.provider_locator is not None
        and readback.provider_locator != binding.authoritative_readback_locator
    ):
        raise LegacyAttemptBindingMismatch(
            "readback provider locator does not match the exact binding"
        )


class LegacyAttemptReplayResult(FrozenContract):
    schema_version: Literal["mrw.migration.legacy-attempt-replay.v1"] = (
        "mrw.migration.legacy-attempt-replay.v1"
    )
    observed_at: datetime
    observations: tuple[EffectAttemptObservation, ...]
    replay_digest: Digest

    @model_validator(mode="after")
    def validate_result(self) -> LegacyAttemptReplayResult:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("legacy attempt replay observed_at must be timezone-aware")
        if tuple(sorted(self.observations, key=lambda item: item.attempt_id)) != (
            self.observations
        ):
            raise ValueError("legacy attempt observations are not canonically ordered")
        attempt_ids = [item.attempt_id for item in self.observations]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("legacy attempt replay contains duplicate attempt ids")
        expected = canonical_digest(self, exclude_fields={"replay_digest"})
        if self.replay_digest != expected:
            raise ValueError("legacy attempt replay_digest mismatch")
        return self


def replay_legacy_attempts(
    records: Iterable[Mapping[str, object]],
    bindings: Sequence[ExactLegacyAttemptBinding],
    *,
    assignment: RuntimeAssignment,
    recovery: RecoveryBinding,
    profile: LegacyInterpreterProfile,
    observed_at: datetime,
) -> LegacyAttemptReplayResult:
    """Replay an ordered record/binding batch and fail closed on contradictions."""

    record_list = tuple(records)
    binding_list = tuple(bindings)
    if len(record_list) != len(binding_list):
        raise IncompleteLegacyAttemptRecord(
            "legacy attempt records and bindings must be one-to-one"
        )
    observations: list[EffectAttemptObservation] = []
    for record, binding in zip(record_list, binding_list, strict=True):
        evidence = replay_effect_attempt(
            record,
            assignment=assignment,
            recovery=recovery,
            profile=profile,
            binding=binding,
            observed_at=observed_at,
        )
        attempt = evidence.observation
        previous = next(
            (item for item in observations if item.attempt_id == attempt.attempt_id),
            None,
        )
        if previous is not None and previous.disposition is not attempt.disposition:
            raise ContradictoryAttemptReplay(
                f"legacy attempt {attempt.attempt_id} has conflicting dispositions"
            )
        if previous is None:
            observations.append(attempt)
    observations.sort(key=lambda item: item.attempt_id)
    provisional = LegacyAttemptReplayResult.model_construct(
        observed_at=observed_at,
        observations=tuple(observations),
        replay_digest="0" * 64,
    )
    values = provisional.model_dump(mode="python")
    values.pop("replay_digest")
    return LegacyAttemptReplayResult(
        **values,
        replay_digest=canonical_digest(
            provisional,
            exclude_fields={"replay_digest"},
        ),
    )


__all__ = [
    "ContradictoryAttemptReplay",
    "ExactLegacyAttemptBinding",
    "IncompleteLegacyAttemptRecord",
    "LegacyAttemptBindingMismatch",
    "LegacyAttemptReplayEvidence",
    "LegacyAttemptReplayResult",
    "LegacyEffectAttemptReplayError",
    "LegacyInterpreterProfile",
    "replay_effect_attempt",
    "replay_legacy_attempts",
    "require_exact_adoption",
]
