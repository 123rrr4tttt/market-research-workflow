"""One shared W05 capability-contract failure representation."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


SuccessorCapabilityContractFailureCode = Literal[
    "schema_contract_invalid",
    "digest_contract_invalid",
    "scope_contract_invalid",
    "catalog_contract_invalid",
    "program_binding_invalid",
    "codec_contract_invalid",
]


successor_capability_contract_failures = define_failure_family(
    "successor.capability.contract_failure",
    get_args(SuccessorCapabilityContractFailureCode),
)


__all__ = [
    "SuccessorCapabilityContractFailureCode",
    "successor_capability_contract_failures",
]
