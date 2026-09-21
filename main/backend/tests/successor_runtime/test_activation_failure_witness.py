from __future__ import annotations

from dataclasses import replace

import pytest

from functorial_kit import Failure

from app.successor_runtime.runtime.activation import (
    ActivationError,
    activate_plan,
    activate_plan_result,
)

from .test_p0c_activation import _compile, _empty_registries, _program, identity_node, INPUT


def test_activate_plan_result_closes_input_validation() -> None:
    transforms, merges, discriminators = _empty_registries()
    program = _program(identity_node(INPUT))
    # An empty run_id is rejected before any plan or registry lookup is
    # observable.
    result = activate_plan_result(
        run_id="",
        program=program,
        plan=replace(
            _compile(program, (), transforms, merges, discriminators),
            plan_digest="0" * 64,
        ),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
    assert isinstance(result, Failure)
    assert result.family == "successor.runtime.failure"
    assert result.code == "ACTIVATION_INVALID"


def test_invalid_plan_is_typed_and_lifted_at_legacy_boundary() -> None:
    transforms, merges, discriminators = _empty_registries()
    program = _program(identity_node(INPUT))
    plan = replace(
        _compile(program, (), transforms, merges, discriminators),
        plan_digest="0" * 64,
    )
    result = activate_plan_result(
        run_id="run-invalid-plan",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
    assert isinstance(result, Failure)
    assert result.code == "ACTIVATION_INVALID"
    with pytest.raises(ActivationError):
        activate_plan(
            run_id="run-invalid-plan",
            program=program,
            plan=plan,
            transform_registry=transforms,
            merge_registry=merges,
            discriminator_registry=discriminators,
        )
