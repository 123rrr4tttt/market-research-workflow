"""Build the canonical catalog index from capability-published contracts."""

from __future__ import annotations

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
) -> CapabilityCatalogSnapshot:
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
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_first_specimen_catalog(first_specimen_contracts),
        first_specimen_contracts,
    )
