"""Readback-only effect reconciliation.

The reconciler intentionally has no execution callback.  It may observe the
original interpreter/provider and validate a ``NonStartProof``; it cannot
redispatch the original effect or manufacture success from lease expiry.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from .assignments import (
    AssignmentKind,
    Digest,
    FrozenContract,
    RecoveryBinding,
    RuntimeAssignment,
)
from .recovery import NonStartProof, authorize_successor_attempt
from .transitions import EffectDisposition


class ReconciliationError(RuntimeError):
    """An exact recovery binding or authoritative observation is invalid."""


class ReconciliationState(StrEnum):
    RESOLVED = "RESOLVED"
    WAITING = "WAITING"
    NOT_STARTED_PROVEN = "NOT_STARTED_PROVEN"


class EffectAttemptObservation(FrozenContract):
    """Minimal exact original-attempt identity exposed to readback."""

    attempt_id: Digest
    assignment_digest: Digest
    handler_binding_digest: Digest
    interpreter_profile_digest: Digest
    interpreter_id: str = Field(min_length=1)
    interpreter_version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    external_idempotency_key: str = Field(min_length=1)
    authoritative_readback_locator: str = Field(min_length=1)
    disposition: EffectDisposition = EffectDisposition.OUTCOME_UNKNOWN


class AuthoritativeEffectReadback(FrozenContract):
    """One authoritative observation of the original effect attempt."""

    attempt_id: Digest
    disposition: EffectDisposition
    provider_locator: str | None = None
    receipt_digest: Digest | None = None
    failure_digest: Digest | None = None
    observation_digest: Digest
    reason: str | None = None

    @model_validator(mode="after")
    def validate_terminal_evidence(self) -> AuthoritativeEffectReadback:
        if self.disposition is EffectDisposition.SUCCEEDED and (
            not self.provider_locator or not self.receipt_digest
        ):
            raise ValueError("SUCCEEDED readback requires provider locator and receipt")
        if self.disposition is EffectDisposition.FAILED and not self.failure_digest:
            raise ValueError("FAILED readback requires failure digest")
        if self.disposition is EffectDisposition.NOT_STARTED:
            raise ValueError("NOT_STARTED requires a separate NonStartProof")
        return self


class ReadbackInterpreter(Protocol):
    interpreter_id: str
    interpreter_version: str
    provider_id: str
    provider_version: str

    def readback(
        self, attempt: EffectAttemptObservation
    ) -> AuthoritativeEffectReadback: ...

    def prove_not_started(self, attempt: EffectAttemptObservation) -> object: ...


class ReconciliationResult(FrozenContract):
    state: ReconciliationState
    attempt_id: Digest
    disposition: EffectDisposition
    readback: AuthoritativeEffectReadback | None = None
    non_start_proof: NonStartProof | None = None
    wait_reason: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> ReconciliationResult:
        if self.state is ReconciliationState.RESOLVED:
            if (
                self.disposition
                not in {EffectDisposition.SUCCEEDED, EffectDisposition.FAILED}
                or self.readback is None
                or self.readback.attempt_id != self.attempt_id
                or self.readback.disposition is not self.disposition
                or self.non_start_proof is not None
                or self.wait_reason is not None
            ):
                raise ValueError(
                    "RESOLVED reconciliation requires exact terminal readback"
                )
        elif self.state is ReconciliationState.NOT_STARTED_PROVEN:
            if (
                self.disposition is not EffectDisposition.NOT_STARTED
                or self.non_start_proof is None
                or self.non_start_proof.attempt_id != self.attempt_id
                or self.readback is not None
                or self.wait_reason is not None
            ):
                raise ValueError("NOT_STARTED_PROVEN requires exact proof")
        elif self.state is ReconciliationState.WAITING and (
            self.disposition is not EffectDisposition.OUTCOME_UNKNOWN
            or not self.wait_reason
            or self.non_start_proof is not None
            or (
                self.readback is not None
                and (
                    self.readback.attempt_id != self.attempt_id
                    or self.readback.disposition
                    is not EffectDisposition.OUTCOME_UNKNOWN
                )
            )
        ):
            raise ValueError(
                "WAITING reconciliation requires exact OUTCOME_UNKNOWN evidence"
            )
        return self


class ReconciliationHandlerOutcome(FrozenContract):
    """Typed RuntimeHandler result for one exact reconciliation target.

    The wrapper keeps readback/proof state distinct from an ordinary
    ``InterpreterOutcome``.  Only an authoritative resolved success may carry
    the output adopted by the runtime lifecycle; waiting, failed, and
    non-start observations cannot manufacture one.
    """

    result: ReconciliationResult
    output_digest: Digest | None = None
    receipt_ref: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_adopted_output(self) -> ReconciliationHandlerOutcome:
        resolved_success = (
            self.result.state is ReconciliationState.RESOLVED
            and self.result.disposition is EffectDisposition.SUCCEEDED
        )
        if resolved_success and self.output_digest is None:
            raise ValueError(
                "resolved successful reconciliation requires output_digest"
            )
        if not resolved_success and (
            self.output_digest is not None or self.receipt_ref is not None
        ):
            raise ValueError(
                "only resolved successful reconciliation may bind output or receipt"
            )
        return self


class EffectReconciler:
    """Resolve only through authoritative readback or exact non-start proof."""

    def reconcile(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult:
        self._require_exact_recovery_binding(assignment, attempt, interpreter)
        readback = interpreter.readback(attempt)
        if not isinstance(readback, AuthoritativeEffectReadback):
            raise ReconciliationError(
                "interpreter readback did not return authoritative typed evidence"
            )
        if readback.attempt_id != attempt.attempt_id:
            raise ReconciliationError("readback is bound to a different attempt")
        if readback.disposition in {
            EffectDisposition.SUCCEEDED,
            EffectDisposition.FAILED,
        }:
            return ReconciliationResult(
                state=ReconciliationState.RESOLVED,
                attempt_id=attempt.attempt_id,
                disposition=readback.disposition,
                readback=readback,
            )
        return ReconciliationResult(
            state=ReconciliationState.WAITING,
            attempt_id=attempt.attempt_id,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            readback=readback,
            wait_reason=readback.reason or "AUTHORITATIVE_OUTCOME_UNRESOLVED",
        )

    def prove_non_start(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult:
        """Validate proof for a *future* successor attempt; never create it."""

        self._require_exact_recovery_binding(assignment, attempt, interpreter)
        proof = interpreter.prove_not_started(attempt)
        if not isinstance(proof, NonStartProof):
            return ReconciliationResult(
                state=ReconciliationState.WAITING,
                attempt_id=attempt.attempt_id,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                wait_reason="NON_START_UNPROVABLE",
            )
        try:
            authorize_successor_attempt(
                prior_attempt_id=attempt.attempt_id,
                proof=proof,
            )
        except ValueError as exc:
            raise ReconciliationError(str(exc)) from exc
        expected = {
            "interpreter_id": attempt.interpreter_id,
            "interpreter_version": attempt.interpreter_version,
            "provider_id": attempt.provider_id,
            "provider_version": attempt.provider_version,
            "external_idempotency_key": attempt.external_idempotency_key,
            "authoritative_readback_locator": attempt.authoritative_readback_locator,
        }
        actual = proof.model_dump(mode="python")
        drift = tuple(key for key, value in expected.items() if actual[key] != value)
        if drift:
            raise ReconciliationError(
                "NonStartProof identity drift: " + ", ".join(drift)
            )
        return ReconciliationResult(
            state=ReconciliationState.NOT_STARTED_PROVEN,
            attempt_id=attempt.attempt_id,
            disposition=EffectDisposition.NOT_STARTED,
            non_start_proof=proof,
        )

    @staticmethod
    def _require_exact_recovery_binding(
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> None:
        if assignment.assignment_kind is not AssignmentKind.RECONCILE:
            raise ReconciliationError("reconciler requires RECONCILE assignment")
        if assignment.reconciliation_attempt_id != attempt.attempt_id:
            raise ReconciliationError("assignment targets a different attempt")
        binding = assignment.handler_binding
        if not isinstance(binding, RecoveryBinding):
            raise ReconciliationError("assignment lacks exact RecoveryBinding")
        if binding.interpreter_profile_digest != attempt.interpreter_profile_digest:
            raise ReconciliationError("original interpreter profile drift")
        if interpreter.interpreter_id != attempt.interpreter_id:
            raise ReconciliationError("readback interpreter identity drift")
        if interpreter.interpreter_version != attempt.interpreter_version:
            raise ReconciliationError("readback interpreter version drift")
        if interpreter.provider_id != attempt.provider_id:
            raise ReconciliationError("readback provider identity drift")
        if interpreter.provider_version != attempt.provider_version:
            raise ReconciliationError("readback provider version drift")


__all__ = [
    "AuthoritativeEffectReadback",
    "EffectAttemptObservation",
    "EffectReconciler",
    "ReadbackInterpreter",
    "ReconciliationError",
    "ReconciliationHandlerOutcome",
    "ReconciliationResult",
    "ReconciliationState",
]
