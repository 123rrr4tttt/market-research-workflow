"""CW08 recovery from an exact staged artifact.

This boundary intentionally has no upstream interpreter callback.  Recovery may
read the already-staged value, decode and verify those exact bytes, and enter
the ordinary readback-first admission coordinator.  It cannot re-run compose,
network, model, process, filesystem, or other producing effects.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, NoReturn, Protocol, TypeVar

from functorial_kit import Failure

from .admission import CommitIntent, VerificationBinding
from .admission_coordinator import (
    AdmissionBindingError,
    AdmissionCoordinator,
    AdmissionResult,
    PreparedAdmission,
)
from .assignments import AssignmentKind, RuntimeAssignment
from .ports import RuntimeScope
from .failure_policy import raise_runtime_failure, runtime_failure


_SITE = "successor_runtime.runtime.staged_recovery.resume"
_T = TypeVar("_T")


class StagedArtifactRecoveryError(AdmissionBindingError):
    """The durable staged value no longer has its exact recovery binding."""


def _staged_failure(
    code: str,
    message: object,
    exception_type: type[Exception] = StagedArtifactRecoveryError,
) -> Failure:
    return runtime_failure(code, message, exception_type, site=_SITE)


def _legacy_lift(failure: Failure, exception_type: type[Exception]) -> NoReturn:
    """Restore the exception ABI at the small public compatibility surface."""

    raise_runtime_failure(failure, exception_type)


def _capture(call: Callable[[], _T]) -> _T | Failure:
    """Turn expected adapter/coordinator validation errors into closed values."""

    try:
        return call()
    except (StagedArtifactRecoveryError, AdmissionBindingError) as exc:
        return _staged_failure("STAGED_RECOVERY_BINDING_REJECTED", str(exc))
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return _staged_failure("STAGED_RECOVERY_READBACK_INVALID", str(exc))


class RecoverableStagedState(StrEnum):
    STAGED = "STAGED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True, slots=True)
class ExactStagedArtifact:
    """Process-local exact readback of public metadata plus project bytes."""

    artifact_id: str
    project_key: str
    run_id: str
    effect_step_id: str
    effect_attempt_id: str
    effect_receipt_ref: str
    value_id: str
    object_type: str
    codec_id: str
    content_digest: str
    byte_size: int
    value_revision: int
    value_incarnation: str
    qualifier_ref: str
    loss_profile_ref: str | None
    state: RecoverableStagedState
    staged_revision: int
    exact_bytes: bytes


@dataclass(frozen=True, slots=True)
class StagedRecoveryRequest:
    """Frozen expectations needed to reopen one staged admission input."""

    artifact_id: str
    value_id: str
    effect_attempt_id: str
    effect_receipt_ref: str
    object_type: str
    codec_id: str
    value_revision: int
    value_incarnation: str
    qualifier_ref: str
    loss_profile_ref: str | None

    def __post_init__(self) -> None:
        failure = self.validation_result()
        if isinstance(failure, Failure):
            _legacy_lift(failure, ValueError)

    def validation_result(self) -> None | Failure:
        """Validate the frozen request as a typed runtime result."""

        required = (
            self.artifact_id,
            self.value_id,
            self.effect_attempt_id,
            self.effect_receipt_ref,
            self.object_type,
            self.codec_id,
            self.value_incarnation,
            self.qualifier_ref,
        )
        if not all(isinstance(value, str) and value for value in required):
            return _staged_failure(
                "STAGED_RECOVERY_REQUEST_INVALID",
                "staged recovery request has an incomplete exact binding",
                ValueError,
            )
        if not isinstance(self.value_revision, int) or isinstance(self.value_revision, bool):
            return _staged_failure(
                "STAGED_RECOVERY_REQUEST_INVALID",
                "staged recovery requires a persisted value revision",
                ValueError,
            )
        if self.value_revision < 1:
            return _staged_failure(
                "STAGED_RECOVERY_REQUEST_INVALID",
                "staged recovery requires a persisted value revision",
                ValueError,
            )
        return None


class StagedArtifactRecoveryPort(Protocol):
    """Read/verify lifecycle only; it has no producing-effect operation."""

    def load_exact(
        self,
        *,
        request: StagedRecoveryRequest,
        assignment: RuntimeAssignment,
        expected_content_digest: str,
    ) -> ExactStagedArtifact | Failure: ...

    def mark_verified(
        self, staged: ExactStagedArtifact
    ) -> ExactStagedArtifact | Failure: ...


class ExactStagedCandidateDecoder(Protocol):
    """Pure decoder/verifier for bytes that were already durably staged."""

    def decode_exact(self, staged: ExactStagedArtifact) -> object | Failure: ...


@dataclass(frozen=True, slots=True)
class StagedAdmissionRecoveryResult:
    staged: ExactStagedArtifact
    prepared: PreparedAdmission
    admission: AdmissionResult


class StagedAdmissionRecoveryCoordinator:
    """Resume CW08 without obtaining a path back to the upstream effect."""

    def __init__(
        self,
        *,
        staged_artifacts: StagedArtifactRecoveryPort,
        admission: AdmissionCoordinator,
        decoder: ExactStagedCandidateDecoder,
    ) -> None:
        self.staged_artifacts = staged_artifacts
        self.admission = admission
        self.decoder = decoder

    def _resume_impl(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        intent: CommitIntent,
        binding: VerificationBinding,
        request: StagedRecoveryRequest,
        current_authority_digest: str,
        current_base_revision: int,
        current_incarnation: str,
        ordered_event_payloads: tuple[object, ...] | list[object],
    ) -> StagedAdmissionRecoveryResult | Failure:
        request_failure = request.validation_result()
        if isinstance(request_failure, Failure):
            return request_failure
        compiled = assignment.compiled_admission_binding
        if (
            assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT
            or compiled is None
            or assignment.step_id != compiled.admission_step_id
        ):
            return _staged_failure(
                "STAGED_RECOVERY_BINDING_REJECTED",
                "staged recovery requires the exact compiled admission assignment"
            )
        if assignment.payload_digest != intent.content_digest:
            return _staged_failure(
                "STAGED_RECOVERY_BINDING_REJECTED",
                "admission assignment payload differs from staged intent content"
            )
        if binding.output_content_digest != intent.content_digest:
            return _staged_failure(
                "STAGED_RECOVERY_BINDING_REJECTED",
                "verification output differs from staged intent content"
            )
        if (
            binding.authority_digest != current_authority_digest
            or binding.canonical_base_revision != current_base_revision
            or binding.canonical_incarnation != current_incarnation
        ):
            return _staged_failure(
                "STAGED_RECOVERY_BINDING_REJECTED",
                "authority/base/incarnation drift before staged recovery"
            )

        staged = _capture(
            lambda: self.staged_artifacts.load_exact(
                request=request,
                assignment=assignment,
                expected_content_digest=intent.content_digest,
            )
        )
        if isinstance(staged, Failure):
            return staged
        snapshot = self._require_exact_snapshot(
            staged=staged,
            request=request,
            assignment=assignment,
            expected_content_digest=intent.content_digest,
        )
        if isinstance(snapshot, Failure):
            return snapshot
        candidate = _capture(lambda: self.decoder.decode_exact(staged))
        if isinstance(candidate, Failure):
            return candidate
        prepared = _capture(
            lambda: self.admission.prepare(
                scope=scope,
                assignment=assignment,
                intent=intent,
                candidate=candidate,
                binding=binding,
                current_authority_digest=current_authority_digest,
                current_base_revision=current_base_revision,
                current_incarnation=current_incarnation,
                ordered_event_payloads=ordered_event_payloads,
            )
        )
        if isinstance(prepared, Failure):
            return prepared
        if staged.state is RecoverableStagedState.STAGED:
            verified = _capture(lambda: self.staged_artifacts.mark_verified(staged))
            if isinstance(verified, Failure):
                return verified
            staged = verified
            if staged.state is not RecoverableStagedState.VERIFIED:
                return _staged_failure(
                    "STAGED_RECOVERY_BINDING_REJECTED",
                    "staged artifact did not enter VERIFIED by exact CAS"
                )
        admission = _capture(lambda: self.admission.commit_prepared(prepared))
        if isinstance(admission, Failure):
            return admission
        return StagedAdmissionRecoveryResult(
            staged=staged,
            prepared=prepared,
            admission=admission,
        )

    def resume_result(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        intent: CommitIntent,
        binding: VerificationBinding,
        request: StagedRecoveryRequest,
        current_authority_digest: str,
        current_base_revision: int,
        current_incarnation: str,
        ordered_event_payloads: tuple[object, ...] | list[object],
    ) -> StagedAdmissionRecoveryResult | Failure:
        """Resume staged admission as a closed runtime result."""

        if not isinstance(request, StagedRecoveryRequest):
            return _staged_failure(
                "STAGED_RECOVERY_REQUEST_INVALID",
                "staged recovery request has an invalid runtime type",
                ValueError,
            )
        return _capture(
            lambda: self._resume_impl(
                scope=scope,
                assignment=assignment,
                intent=intent,
                binding=binding,
                request=request,
                current_authority_digest=current_authority_digest,
                current_base_revision=current_base_revision,
                current_incarnation=current_incarnation,
                ordered_event_payloads=ordered_event_payloads,
            )
        )

    def resume(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        intent: CommitIntent,
        binding: VerificationBinding,
        request: StagedRecoveryRequest,
        current_authority_digest: str,
        current_base_revision: int,
        current_incarnation: str,
        ordered_event_payloads: tuple[object, ...] | list[object],
    ) -> StagedAdmissionRecoveryResult:
        """Legacy exception ABI over :meth:`resume_result`."""

        result = self.resume_result(
            scope=scope,
            assignment=assignment,
            intent=intent,
            binding=binding,
            request=request,
            current_authority_digest=current_authority_digest,
            current_base_revision=current_base_revision,
            current_incarnation=current_incarnation,
            ordered_event_payloads=ordered_event_payloads,
        )
        if isinstance(result, Failure):
            _legacy_lift(
                result,
                ValueError
                if result.code == "STAGED_RECOVERY_REQUEST_INVALID"
                else StagedArtifactRecoveryError,
            )
        return result

    @staticmethod
    def _require_exact_snapshot(
        *,
        staged: ExactStagedArtifact,
        request: StagedRecoveryRequest,
        assignment: RuntimeAssignment,
        expected_content_digest: str,
    ) -> None | Failure:
        try:
            compiled = assignment.compiled_admission_binding
            if compiled is None:
                return _staged_failure(
                    "STAGED_RECOVERY_BINDING_REJECTED",
                    "staged recovery assignment lacks compiled admission binding",
                )
            expected = {
                "artifact_id": request.artifact_id,
                "project_key": assignment.project_key,
                "run_id": assignment.run_id,
                "effect_step_id": compiled.effect_step_id,
                "effect_attempt_id": request.effect_attempt_id,
                "effect_receipt_ref": request.effect_receipt_ref,
                "value_id": request.value_id,
                "object_type": request.object_type,
                "codec_id": request.codec_id,
                "content_digest": expected_content_digest,
                "value_revision": request.value_revision,
                "value_incarnation": request.value_incarnation,
                "qualifier_ref": request.qualifier_ref,
                "loss_profile_ref": request.loss_profile_ref,
            }
            actual = {name: getattr(staged, name) for name in expected}
            drift = tuple(
                name for name, value in expected.items() if actual[name] != value
            )
            if drift:
                return _staged_failure(
                    "STAGED_RECOVERY_BINDING_REJECTED",
                    "staged artifact exact binding drift: " + ", ".join(drift),
                )
            if staged.state not in {
                RecoverableStagedState.STAGED,
                RecoverableStagedState.VERIFIED,
            }:
                return _staged_failure(
                    "STAGED_RECOVERY_BINDING_REJECTED",
                    "staged artifact is not recoverable before admission",
                )
            if staged.byte_size != len(staged.exact_bytes):
                return _staged_failure(
                    "STAGED_RECOVERY_BINDING_REJECTED",
                    "staged artifact byte size drift",
                )
            observed = hashlib.sha256(staged.exact_bytes).hexdigest()
            if observed != staged.content_digest:
                return _staged_failure(
                    "STAGED_RECOVERY_BINDING_REJECTED",
                    "staged artifact content digest drift",
                )
            return None
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
            return _staged_failure("STAGED_RECOVERY_READBACK_INVALID", str(exc))


__all__ = [
    "ExactStagedArtifact",
    "ExactStagedCandidateDecoder",
    "RecoverableStagedState",
    "StagedAdmissionRecoveryCoordinator",
    "StagedAdmissionRecoveryResult",
    "StagedArtifactRecoveryError",
    "StagedArtifactRecoveryPort",
    "StagedRecoveryRequest",
]
