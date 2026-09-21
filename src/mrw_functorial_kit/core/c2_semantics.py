"""Kit projection for exact-bound C2 shared constructor failures."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


C2SharedContractFailureCode = Literal[
    "schema_contract_invalid",
    "digest_contract_invalid",
    "scope_contract_invalid",
    "catalog_contract_invalid",
    "mode_contract_invalid",
    "provider_effect_contract_invalid",
    "terminal_contract_invalid",
    "legacy_input_union_invalid",
]

c2_shared_contract_failures = define_failure_family(
    "c2.shared.contract_failure",
    get_args(C2SharedContractFailureCode),
)


__all__ = ["c2_shared_contract_failures"]
