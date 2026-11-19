from __future__ import annotations

from dataclasses import fields
from typing import get_args

import pytest
from functorial_kit import Failure, FailureFamily

from mrw_functorial_kit.core.capability_contract_failure_semantics import (
    SuccessorCapabilityContractFailureCode,
    successor_capability_contract_failures,
)


CAPABILITY_CONTRACT_CODES = (
    "schema_contract_invalid",
    "digest_contract_invalid",
    "scope_contract_invalid",
    "catalog_contract_invalid",
    "program_binding_invalid",
    "codec_contract_invalid",
)


def test_INVARIANT__capability_contract_literal_alias_is_exact_and_shared() -> None:
    assert get_args(SuccessorCapabilityContractFailureCode) == CAPABILITY_CONTRACT_CODES


def test_INVARIANT__capability_contract_failure_family_has_exact_name_and_codes() -> None:
    family = successor_capability_contract_failures
    assert family.name == "successor.capability.contract_failure"
    assert family.codes == CAPABILITY_CONTRACT_CODES
    assert family.matches(family.fail(CAPABILITY_CONTRACT_CODES[0], "registered capability contract failure"))


def test_INVARIANT__capability_contract_failure_returns_closed_kit_failure() -> None:
    family: FailureFamily = successor_capability_contract_failures
    context = {"capability": "shared-successor-contract"}
    for code in CAPABILITY_CONTRACT_CODES:
        failure = family.fail(code, "capability contract rejected", context)
        assert isinstance(failure, Failure)
        assert (failure.family, failure.code, failure.message, failure.context) == (
            "successor.capability.contract_failure",
            code,
            "capability contract rejected",
            context,
        )
        assert family.matches(failure)


def test_INVARIANT__capability_contract_failure_family_rejects_unknown_codes() -> None:
    family: FailureFamily = successor_capability_contract_failures
    for code in ("unknown_contract_invalid", "schema_invalid", ""):
        with pytest.raises(
            ValueError,
            match="failure family successor.capability.contract_failure: unknown code",
        ):
            family.fail(code, "outside the capability contract")


def test_INVARIANT__capability_contract_kit_failure_shape_is_not_replaced() -> None:
    failure = successor_capability_contract_failures.fail("codec_contract_invalid", "shape")
    failure_field_names = {field.name for field in fields(Failure)}
    assert failure_field_names == {"family", "code", "message", "context"}
    assert failure.message == "shape"
