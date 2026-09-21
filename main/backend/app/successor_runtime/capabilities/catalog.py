"""Build the canonical catalog index from capability-published contracts."""

from __future__ import annotations
from typing import Annotated, Literal

from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.research.codec import sha256_hex

from .contracts import OperationContract

# Backward-compatible name only; there is one catalog snapshot class identity.
CapabilityCatalogSnapshot = OperationContractCatalogSnapshot


def catalog_digest(contracts: tuple[OperationContract, ...]) -> str:
    entries = tuple(
        (contract.ref.kind, contract.ref.contract_version, contract.ref.contract_digest)
        for contract in contracts
    )
    return sha256_hex({"entries": entries})


def build_first_specimen_catalog(
    first_specimen_contracts: tuple[OperationContract, ...],
    fixture_contract: OperationContract | None = None,
) -> Annotated[CapabilityCatalogSnapshot, Literal["kit:non-authoritative derived_as=view fact_source=FirstSpecimen_contracts witness=test:test_w06_successor_authority_metadata"]]:
    contracts = first_specimen_contracts
    if fixture_contract is not None:
        contracts = contracts + (fixture_contract,)
    entries = tuple(
        (
            contract.ref.kind,
            contract.ref.contract_version,
            contract.ref.contract_digest,
            contract.owner_capability_id,
        )
        for contract in contracts
    )
    return OperationContractCatalogSnapshot(
        catalog_id="mrw.functorial-successor.first-specimen.capabilities.v1",
        catalog_version="1.0.0",
        entries=entries,
    )


def build_first_specimen_registry(
    first_specimen_contracts: tuple[OperationContract, ...],
) -> Annotated[OperationContractRegistry, Literal["kit:non-authoritative derived_as=view fact_source=FirstSpecimen_contracts witness=test:test_w06_successor_authority_metadata"]]:
    return OperationContractRegistry(
        build_first_specimen_catalog(first_specimen_contracts),
        first_specimen_contracts,
    )
