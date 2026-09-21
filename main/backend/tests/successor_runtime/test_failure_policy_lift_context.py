"""Focused contract for exact exception identity in runtime failure lifts."""

from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.successor_runtime.runtime.failure_policy import (
    RuntimeFailure,
    canonical_digest,
    raise_runtime_failure,
    runtime_failure,
)


class StaleBindingConflict(RuntimeError):
    pass


def _same_named_conflict(value_error_name: str) -> type[Exception]:
    return type(value_error_name, (ValueError,), {})


def test_canonical_digest_rejects_exclude_fields_for_non_mapping() -> None:
    with pytest.raises(TypeError, match="exclude_fields is only valid"):
        canonical_digest(("not", "a", "mapping"), exclude_fields={"field"})


def test_runtime_failure_preserves_exact_exception_under_generic_lift() -> None:
    failure = runtime_failure(
        "NODE_PORT_RESULT_INVALID",
        "capability claim authority is stale",
        StaleBindingConflict,
        site="runtime.node.run_once.port",
    )

    assert isinstance(failure, Failure)
    assert failure.context == {
        "public_exception": "StaleBindingConflict",
        "public_argument": "capability claim authority is stale",
        "public_message": "capability claim authority is stale",
        "site": "runtime.node.run_once.port",
        "witness": "test:test_w07_runtime_failure_lift_context",
    }
    with pytest.raises(StaleBindingConflict, match="capability claim authority"):
        raise_runtime_failure(failure, RuntimeError)


def test_runtime_failure_rejects_mismatched_exact_exception_identity() -> None:
    failure = runtime_failure(
        "NODE_PORT_RESULT_INVALID",
        "bound exception identity drifted",
        StaleBindingConflict,
        site="runtime.node.run_once.port",
    )
    assert isinstance(failure, RuntimeFailure)
    tampered = RuntimeFailure(
        family=failure.family,
        code=failure.code,
        message=failure.message,
        context=failure.context,
        exception_type=ValueError,
    )

    with pytest.raises(TypeError, match="lift context is incomplete"):
        raise_runtime_failure(tampered, RuntimeError)


def test_runtime_failure_discriminates_same_exception_names() -> None:
    first = runtime_failure(
        "NODE_PORT_RESULT_INVALID",
        "first exact identity",
        StaleBindingConflict,
        site="runtime.first",
    )
    second_type = _same_named_conflict("StaleBindingConflict")
    second = runtime_failure(
        "NODE_PORT_RESULT_INVALID",
        "second exact identity",
        second_type,
        site="runtime.second",
    )

    with pytest.raises(StaleBindingConflict, match="first exact identity"):
        raise_runtime_failure(first, RuntimeError)
    with pytest.raises(second_type, match="second exact identity"):
        raise_runtime_failure(second, RuntimeError)
