"""Shared typed failure helpers for capability-owned contract modules."""

from __future__ import annotations

from typing import NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w06_semantics import first_specimen_capability_failures


def capability_failure(code: str, message: str, **context: object) -> Failure:
    """Construct the closed W06 failure value shared by capability modules."""

    return first_specimen_capability_failures.fail(
        code,
        message,
        {
            "owner": "first_specimen.capabilities",
            "effect_boundary": "first_specimen.capability.contract_core",
            "failure_family": first_specimen_capability_failures.name,
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "witness": "test:test_w06_first_specimen_failure_lifts",
            **context,
        },
    )


def raise_capability_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
    *exception_args: object,
) -> NoReturn:
    """Lift a typed core failure only at the compatibility ABI boundary."""

    # kit:boundary owner=first_specimen.capabilities class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=first_specimen.capability.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(*(exception_args or (failure.message,)))


__all__ = ["capability_failure", "raise_capability_failure"]
