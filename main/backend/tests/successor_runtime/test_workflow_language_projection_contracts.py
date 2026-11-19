"""Workflow language projections describe their fact sources."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, get_args, get_origin, get_type_hints

from app.successor_runtime.language.algebra import build_catalog_snapshot
from app.successor_runtime.language.catalog import (
    FIRST_SPECIMEN_OBJECT_CONTRACT_REFS,
    build_first_specimen_domain_snapshot,
    build_first_specimen_object_contracts,
)
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
    build_frozen_base_return_contract_registry,
)
from app.successor_runtime.language.plan import plans_structurally_equivalent


_WITNESS = "test:test_workflow_language_projections_do_not_claim_authority"
_PROJECTIONS: tuple[tuple[Callable[..., object], str], ...] = (
    (
        build_catalog_snapshot,
        "successor_runtime.language.object_contracts.OperationContract",
    ),
    (
        build_first_specimen_domain_snapshot,
        "successor_runtime.language.catalog.first_specimen_frozen_refs",
    ),
    (
        build_first_specimen_object_contracts,
        "successor_runtime.language.catalog._OBJECT_CONTRACT_SPEC",
    ),
    (
        build_first_specimen_return_contract_registry,
        "successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS",
    ),
    (
        build_frozen_base_return_contract_registry,
        "successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS",
    ),
    (
        plans_structurally_equivalent,
        "successor_runtime.language.plan.ExecutionPlan",
    ),
)


def test_workflow_language_projections_do_not_claim_authority() -> None:
    for function, fact_source in _PROJECTIONS:
        return_hint = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_hint) is Annotated
        base_type, metadata = get_args(return_hint)
        assert isinstance(base_type, type) or get_origin(base_type) is not None
        assert metadata == (f"kit:non-authoritative derived_as=view fact_source={fact_source} witness={_WITNESS}")
        # The annotation is metadata only: calling a view still returns the
        # original domain value rather than a NonAuthoritative envelope.
        value = function() if function not in {build_catalog_snapshot, plans_structurally_equivalent} else None
        if function is build_frozen_base_return_contract_registry:
            assert value.__class__ is get_args(return_hint)[0]


def test_first_specimen_return_registry_is_the_frozen_abi() -> None:
    base = build_frozen_base_return_contract_registry()
    combined = build_first_specimen_return_contract_registry()

    assert combined.entries == base.entries


def test_first_specimen_contract_projection_is_frozen() -> None:
    contracts = build_first_specimen_object_contracts()
    snapshot = build_first_specimen_domain_snapshot()

    assert tuple(contract.object_type.type_id for contract in contracts) == (FIRST_SPECIMEN_OBJECT_CONTRACT_REFS)
    assert snapshot.object_contract_refs == FIRST_SPECIMEN_OBJECT_CONTRACT_REFS
