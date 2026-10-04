"""Kit projection for exact-bound C2 shared constructor failures."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family

SourceSharedContractFailureCode = Literal[
    "schema_contract_invalid",
    "digest_contract_invalid",
    "scope_contract_invalid",
    "catalog_contract_invalid",
    "mode_contract_invalid",
    "provider_effect_contract_invalid",
    "terminal_contract_invalid",
    "legacy_input_union_invalid",
]

source_contract_failures = define_failure_family(
    "source.contract.failure",
    get_args(SourceSharedContractFailureCode),
)


__all__ = ["source_contract_failures"]
