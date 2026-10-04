"""Readback-only effect reconciliation.

The reconciler intentionally has no execution callback.  It may observe the
original interpreter/provider and validate a ``NonStartProof``; it cannot
redispatch the original effect or manufacture success from lease expiry.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from functorial_kit import Failure

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
from .failure_policy import raise_runtime_failure, runtime_failure


class ReconciliationError(RuntimeError):
    """An exact recovery binding or authoritative observation is invalid."""


def _reconciliation_failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    """Create one closed reconciliation failure before ABI lifting."""

    return runtime_failure(code, message, exception_type, site=site)


def _raise_reconciliation_failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
    cause: BaseException | None = None,
) -> None:
    """Lift typed reconciliation evidence to the existing exception ABI."""

    raise_runtime_failure(
        _reconciliation_failure(code, message, exception_type, site=site),
        exception_type,
        cause=cause,
    )


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
            _raise_reconciliation_failure(
                "RECONCILIATION_READBACK_INVALID",
                "SUCCEEDED readback requires provider locator and receipt",
                ValueError,
                site="runtime.reconciliation.readback.success",
            )
        if self.disposition is EffectDisposition.FAILED and not self.failure_digest:
            _raise_reconciliation_failure(
                "RECONCILIATION_READBACK_INVALID",
                "FAILED readback requires failure digest",
                ValueError,
                site="runtime.reconciliation.readback.failure",
            )
        if self.disposition is EffectDisposition.NOT_STARTED:
            _raise_reconciliation_failure(
                "RECONCILIATION_READBACK_INVALID",
                "NOT_STARTED requires a separate NonStartProof",
                ValueError,
                site="runtime.reconciliation.readback.not_started",
            )
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
                _raise_reconciliation_failure(
                    "RECONCILIATION_RESULT_INVALID",
                    "RESOLVED reconciliation requires exact terminal readback",
                    ValueError,
                    site="runtime.reconciliation.result.resolved",
                )
        elif self.state is ReconciliationState.NOT_STARTED_PROVEN:
            if (
                self.disposition is not EffectDisposition.NOT_STARTED
                or self.non_start_proof is None
                or self.non_start_proof.attempt_id != self.attempt_id
                or self.readback is not None
                or self.wait_reason is not None
            ):
                _raise_reconciliation_failure(
                    "RECONCILIATION_RESULT_INVALID",
                    "NOT_STARTED_PROVEN requires exact proof",
                    ValueError,
                    site="runtime.reconciliation.result.not_started",
                )
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
            _raise_reconciliation_failure(
                "RECONCILIATION_RESULT_INVALID",
                "WAITING reconciliation requires exact OUTCOME_UNKNOWN evidence",
                ValueError,
                site="runtime.reconciliation.result.waiting",
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
            _raise_reconciliation_failure(
                "RECONCILIATION_RESULT_INVALID",
                "resolved successful reconciliation requires output_digest",
                ValueError,
                site="runtime.reconciliation.handler_output.success",
            )
        if not resolved_success and (
            self.output_digest is not None or self.receipt_ref is not None
        ):
            _raise_reconciliation_failure(
                "RECONCILIATION_RESULT_INVALID",
                "only resolved successful reconciliation may bind output or receipt",
                ValueError,
                site="runtime.reconciliation.handler_output.binding",
            )
        return self


class EffectReconciler:
    """Resolve only through authoritative readback or exact non-start proof."""

    def _reconcile_impl(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult:
        self._require_exact_recovery_binding(assignment, attempt, interpreter)
        readback = interpreter.readback(attempt)
        if not isinstance(readback, AuthoritativeEffectReadback):
            _raise_reconciliation_failure(
                "RECONCILIATION_READBACK_INVALID",
                "interpreter readback did not return authoritative typed evidence",
                ReconciliationError,
                site="runtime.reconciliation.readback.type",
            )
        if readback.attempt_id != attempt.attempt_id:
            _raise_reconciliation_failure(
                "RECONCILIATION_READBACK_INVALID",
                "readback is bound to a different attempt",
                ReconciliationError,
                site="runtime.reconciliation.readback.attempt",
            )
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

    def reconcile_result(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult | Failure:
        """Return authoritative reconciliation evidence or a typed failure."""

        try:
            return self._reconcile_impl(
                assignment=assignment,
                attempt=attempt,
                interpreter=interpreter,
            )
        except ReconciliationError as exc:
            return _reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                str(exc),
                ReconciliationError,
                site="runtime.reconciliation.reconcile",
            )
        except Exception as exc:  # noqa: BLE001 - malformed readback is typed
            return _reconciliation_failure(
                "RECONCILIATION_READBACK_INVALID",
                str(exc),
                type(exc) if isinstance(exc, Exception) else RuntimeError,
                site="runtime.reconciliation.reconcile.readback",
            )

    def reconcile(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult:
        """Legacy exception ABI over :meth:`reconcile_result`."""

        result = self.reconcile_result(
            assignment=assignment,
            attempt=attempt,
            interpreter=interpreter,
        )
        if isinstance(result, Failure):
            exception_type: type[Exception] = (
                ReconciliationError
                if result.code == "RECONCILIATION_BINDING_REJECTED"
                else ValueError
            )
            raise_runtime_failure(result, exception_type)
        return result

    def _prove_non_start_impl(
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
            _raise_reconciliation_failure(
                "NON_START_PROOF_INVALID",
                str(exc),
                ReconciliationError,
                site="runtime.reconciliation.non_start.authorize",
                cause=exc,
            )
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
            _raise_reconciliation_failure(
                "NON_START_PROOF_INVALID",
                "NonStartProof identity drift: " + ", ".join(drift),
                ReconciliationError,
                site="runtime.reconciliation.non_start.identity",
            )
        return ReconciliationResult(
            state=ReconciliationState.NOT_STARTED_PROVEN,
            attempt_id=attempt.attempt_id,
            disposition=EffectDisposition.NOT_STARTED,
            non_start_proof=proof,
        )

    def prove_non_start_result(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult | Failure:
        """Return an exact non-start proof or a typed failure."""

        try:
            return self._prove_non_start_impl(
                assignment=assignment,
                attempt=attempt,
                interpreter=interpreter,
            )
        except ReconciliationError as exc:
            return _reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                str(exc),
                ReconciliationError,
                site="runtime.reconciliation.prove_non_start",
            )
        except Exception as exc:  # noqa: BLE001 - proof validation is typed
            return _reconciliation_failure(
                "NON_START_PROOF_INVALID",
                str(exc),
                type(exc) if isinstance(exc, Exception) else RuntimeError,
                site="runtime.reconciliation.prove_non_start.proof",
            )

    def prove_non_start(
        self,
        *,
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> ReconciliationResult:
        """Legacy exception ABI over :meth:`prove_non_start_result`."""

        result = self.prove_non_start_result(
            assignment=assignment,
            attempt=attempt,
            interpreter=interpreter,
        )
        if isinstance(result, Failure):
            exception_type: type[Exception] = (
                ReconciliationError
                if result.code == "RECONCILIATION_BINDING_REJECTED"
                else ValueError
            )
            raise_runtime_failure(result, exception_type)
        return result

    @staticmethod
    def _require_exact_recovery_binding(
        assignment: RuntimeAssignment,
        attempt: EffectAttemptObservation,
        interpreter: ReadbackInterpreter,
    ) -> None:
        if assignment.assignment_kind is not AssignmentKind.RECONCILE:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "reconciler requires RECONCILE assignment",
                ReconciliationError,
                site="runtime.reconciliation.binding.assignment_kind",
            )
        if assignment.reconciliation_attempt_id != attempt.attempt_id:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "assignment targets a different attempt",
                ReconciliationError,
                site="runtime.reconciliation.binding.attempt",
            )
        binding = assignment.handler_binding
        if not isinstance(binding, RecoveryBinding):
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "assignment lacks exact RecoveryBinding",
                ReconciliationError,
                site="runtime.reconciliation.binding.recovery",
            )
        if binding.interpreter_profile_digest != attempt.interpreter_profile_digest:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "original interpreter profile drift",
                ReconciliationError,
                site="runtime.reconciliation.binding.interpreter_profile",
            )
        if interpreter.interpreter_id != attempt.interpreter_id:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "readback interpreter identity drift",
                ReconciliationError,
                site="runtime.reconciliation.binding.interpreter_id",
            )
        if interpreter.interpreter_version != attempt.interpreter_version:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "readback interpreter version drift",
                ReconciliationError,
                site="runtime.reconciliation.binding.interpreter_version",
            )
        if interpreter.provider_id != attempt.provider_id:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "readback provider identity drift",
                ReconciliationError,
                site="runtime.reconciliation.binding.provider_id",
            )
        if interpreter.provider_version != attempt.provider_version:
            _raise_reconciliation_failure(
                "RECONCILIATION_BINDING_REJECTED",
                "readback provider version drift",
                ReconciliationError,
                site="runtime.reconciliation.binding.provider_version",
            )


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
