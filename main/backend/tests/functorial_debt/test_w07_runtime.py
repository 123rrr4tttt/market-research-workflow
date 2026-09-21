"""Focused witnesses for the W07 runtime Failure family and ABI lifts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from functorial_kit import Failure

from app.successor_runtime.runtime.failure_policy import (
    raise_runtime_failure,
    runtime_failure,
)
from app.successor_runtime.runtime.recovery import (
    NonStartProof,
    authorize_successor_attempt,
)
from app.successor_runtime.runtime.transitions import (
    IllegalTransition,
    RunEvent,
    RunState,
    transition_run,
    transition_run_result,
)


def test_w07_runtime_failure_lift_context() -> None:
    failure = runtime_failure(
        "ILLEGAL_RUN_TRANSITION",
        "illegal run transition",
        IllegalTransition,
        site="test.runtime",
    )
    assert isinstance(failure, Failure)
    assert failure.family == "successor.runtime.failure"
    assert failure.context == {
        "public_exception": "IllegalTransition",
        "public_argument": "illegal run transition",
        "public_message": "illegal run transition",
        "site": "test.runtime",
        "witness": "test:test_w07_runtime_failure_lift_context",
    }
    with pytest.raises(IllegalTransition, match="illegal run transition"):
        raise_runtime_failure(failure, IllegalTransition)


def test_w07_runtime_transition_result_is_closed_failure() -> None:
    result = transition_run_result(
        RunState.SUBMITTED,
        RunEvent.RUN_COMPLETION_DERIVED,
        RunState.COMPLETED,
        guard=True,
    )
    assert isinstance(result, Failure)
    assert result.code == "ILLEGAL_RUN_TRANSITION"
    with pytest.raises(IllegalTransition, match="illegal run transition"):
        transition_run(
            RunState.SUBMITTED,
            RunEvent.RUN_COMPLETION_DERIVED,
            RunState.COMPLETED,
            guard=True,
        )


def test_w07_runtime_non_start_proof_negative() -> None:
    # Pydantic validation remains the existing contract ABI; this witness keeps
    # malformed proof rejection explicit while no total consumer exists.
    with pytest.raises(Exception):
        NonStartProof(
            attempt_id="0" * 64,
            interpreter_id="i",
            interpreter_version="v",
            provider_id="p",
            provider_version="v",
            external_idempotency_key="k",
            authoritative_readback_locator="r",
            authoritative_observation_digest="1" * 64,
            observed_at="2026-01-01T00:00:00Z",
            proof_digest="2" * 64,
        )


def test_w07_runtime_authorize_successor_attempt_abi() -> None:
    proof = SimpleNamespace(attempt_id="0" * 64)
    with pytest.raises(ValueError, match="NonStartProof is bound to a different attempt"):
        authorize_successor_attempt(prior_attempt_id="1" * 64, proof=proof)
