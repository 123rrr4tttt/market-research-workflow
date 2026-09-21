from __future__ import annotations

import hashlib

import pytest

from app.successor_runtime.capabilities.first_specimen_interpreters import (
    InterpreterFailure,
)
from app.successor_runtime.runtime.node import DefiniteInterpreterFailure
from app.successor_runtime.substrate.postgres.first_specimen_handlers import (
    FirstSpecimenActivationBindingInvalid,
    FirstSpecimenHandlerBindingInvalid,
    FirstSpecimenHandlerError,
    FirstSpecimenInterpreterFailure,
    FirstSpecimenOperationUnsupported,
    FirstSpecimenOutputDrift,
    FirstSpecimenOutputReadbackInvalid,
    FirstSpecimenOutputWriteInvalid,
    FirstSpecimenReplayDrift,
    FirstSpecimenSemanticProductInvalid,
    InstalledFirstSpecimenEffectHandler,
    PostgresFirstSpecimenEffectHandler,
    _require_success,
)
import app.successor_runtime.substrate.postgres.first_specimen_handlers as handlers

pytestmark = pytest.mark.unit


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _installed_handler() -> InstalledFirstSpecimenEffectHandler:
    return InstalledFirstSpecimenEffectHandler.bind(
        operation_kind="evidence.qualify.v1",
        handler_binding_digest=_digest("handler-binding"),
        interpreter_profile_digest=_digest("interpreter-profile"),
    )


@pytest.mark.parametrize(
    ("error", "failure_code"),
    [
        (
            FirstSpecimenHandlerError("handler contract drift"),
            "first_specimen_handler_contract_invalid",
        ),
        (
            FirstSpecimenHandlerBindingInvalid("exact binding drift"),
            "first_specimen_handler_binding_invalid",
        ),
        (
            FirstSpecimenReplayDrift("replay projection drift"),
            "first_specimen_replay_projection_invalid",
        ),
        (
            FirstSpecimenActivationBindingInvalid("activation drift"),
            "first_specimen_activation_binding_invalid",
        ),
        (
            FirstSpecimenOutputReadbackInvalid("output readback drift"),
            "first_specimen_output_readback_invalid",
        ),
        (
            FirstSpecimenOutputDrift("output write drift"),
            "first_specimen_output_write_invalid",
        ),
        (
            FirstSpecimenOutputWriteInvalid("output write drift"),
            "first_specimen_output_write_invalid",
        ),
        (
            FirstSpecimenSemanticProductInvalid("semantic product drift"),
            "first_specimen_semantic_product_invalid",
        ),
        (
            FirstSpecimenOperationUnsupported("unsupported operation"),
            "first_specimen_operation_unsupported",
        ),
    ],
)
def test_first_specimen_runtime_failure_codes_are_stable(
    error: Exception,
    failure_code: str,
) -> None:
    assert error.failure_code == failure_code


def test_narrow_failures_preserve_existing_exception_hierarchy() -> None:
    assert isinstance(
        FirstSpecimenHandlerBindingInvalid("exact binding drift"),
        FirstSpecimenReplayDrift,
    )
    assert isinstance(
        FirstSpecimenActivationBindingInvalid("activation drift"),
        FirstSpecimenReplayDrift,
    )
    assert isinstance(
        FirstSpecimenOutputReadbackInvalid("output readback drift"),
        FirstSpecimenOutputDrift,
    )
    assert isinstance(
        FirstSpecimenOutputWriteInvalid("output write drift"),
        FirstSpecimenOutputDrift,
    )


@pytest.mark.parametrize(
    ("capability_code", "message"),
    [
        ("DOCUMENT_OBSERVATION_MISMATCH", "captured document identity drift"),
        ("INVALID_EVIDENCE_QUALIFICATION", "qualification identity drift"),
        ("INVALID_CLAIM_OR_GAP", "claim closure drift"),
        ("INVALID_ARTIFACT_CLOSURE", "artifact closure drift"),
    ],
)
def test_capability_interpreter_failure_is_passed_through(
    capability_code: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Effects:
        def execute_exact(self, *_args: object, **_kwargs: object) -> object:
            raise FirstSpecimenInterpreterFailure(
                code=capability_code,
                message=message,
            )

    monkeypatch.setattr(handlers, "_require_exact_handler", lambda *_args: None)
    handler = PostgresFirstSpecimenEffectHandler(_installed_handler(), Effects())

    with pytest.raises(DefiniteInterpreterFailure) as exc_info:
        handler.execute(object(), object(), object())  # type: ignore[arg-type]

    assert exc_info.value.failure_code == capability_code
    assert str(exc_info.value) == capability_code
    assert str(exc_info.value.__cause__) == message


def test_capability_failure_wrapper_preserves_code_and_message() -> None:
    outcome = InterpreterFailure(
        code="INVALID_CLAIM_OR_GAP",
        message="claim closure drift",
    )

    with pytest.raises(FirstSpecimenInterpreterFailure) as exc_info:
        _require_success(outcome)

    assert exc_info.value.failure_code == "INVALID_CLAIM_OR_GAP"
    assert str(exc_info.value) == "claim closure drift"


def test_runtime_handler_does_not_rewrite_message_into_failure_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Effects:
        def execute_exact(self, *_args: object, **_kwargs: object) -> object:
            raise FirstSpecimenReplayDrift(
                "an arbitrary message that should not become a slug"
            )

    monkeypatch.setattr(handlers, "_require_exact_handler", lambda *_args: None)
    handler = PostgresFirstSpecimenEffectHandler(_installed_handler(), Effects())

    with pytest.raises(DefiniteInterpreterFailure) as exc_info:
        handler.execute(object(), object(), object())  # type: ignore[arg-type]

    assert exc_info.value.failure_code == (
        "first_specimen_replay_projection_invalid"
    )


def test_unknown_runtime_exception_remains_outside_definite_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Effects:
        def execute_exact(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("database connection reset")

    monkeypatch.setattr(handlers, "_require_exact_handler", lambda *_args: None)
    handler = PostgresFirstSpecimenEffectHandler(_installed_handler(), Effects())

    with pytest.raises(RuntimeError, match="database connection reset") as exc_info:
        handler.execute(object(), object(), object())  # type: ignore[arg-type]

    assert not isinstance(exc_info.value, DefiniteInterpreterFailure)


def test_installation_guard_value_error_is_not_runtime_failure() -> None:
    with pytest.raises(ValueError, match="unsupported first-specimen semantic operation"):
        InstalledFirstSpecimenEffectHandler(
            operation_kind="unsupported.operation.v1",
            handler_binding_digest=_digest("handler-binding"),
            interpreter_profile_digest=_digest("interpreter-profile"),
            operation_contract_digest=_digest("operation-contract"),
            payload_codec_id="unsupported.codec.v1",
            payload_codec_digest=_digest("payload-codec"),
            admission_required=False,
        )
