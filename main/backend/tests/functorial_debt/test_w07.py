"""W07 semantic-core authority metadata and exact scan witnesses."""

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
    DOCUMENT_ADMISSION_RETURN_CONTRACT_REF,
    build_c7_document_admission_return_contract_extension,
    build_first_specimen_return_contract_registry,
    build_frozen_base_return_contract_registry,
)
from app.successor_runtime.language.plan import plans_structurally_equivalent


W07_DERIVED_EXACT_KEYS = {
    "derived-marked|main/backend/app/successor_runtime/language/algebra.py|"
    "build_catalog_snapshot returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/language/catalog.py|"
    "build_first_specimen_domain_snapshot returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/language/catalog.py|"
    "build_first_specimen_object_contracts returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/language/object_contracts.py|"
    "build_c7_document_admission_return_contract_extension returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/language/object_contracts.py|"
    "build_first_specimen_return_contract_registry returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/language/object_contracts.py|"
    "build_frozen_base_return_contract_registry returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/language/plan.py|"
    "plans_structurally_equivalent returns an unmarked derived value",
}

_WITNESS = "test:test_w07_derived_metadata_is_exact_and_non_authoritative"
_W07_VIEWS: tuple[tuple[Callable[..., object], str, str], ...] = (
    (
        build_catalog_snapshot,
        "successor_runtime.language.object_contracts.OperationContract",
        "derived-marked|main/backend/app/successor_runtime/language/algebra.py|"
        "build_catalog_snapshot returns an unmarked derived value",
    ),
    (
        build_first_specimen_domain_snapshot,
        "successor_runtime.language.catalog.first_specimen_frozen_refs",
        "derived-marked|main/backend/app/successor_runtime/language/catalog.py|"
        "build_first_specimen_domain_snapshot returns an unmarked derived value",
    ),
    (
        build_first_specimen_object_contracts,
        "successor_runtime.language.catalog._OBJECT_CONTRACT_SPEC",
        "derived-marked|main/backend/app/successor_runtime/language/catalog.py|"
        "build_first_specimen_object_contracts returns an unmarked derived value",
    ),
    (
        build_c7_document_admission_return_contract_extension,
        "successor_runtime.language.object_contracts.DOCUMENT_ADMISSION_RETURN_CONTRACT_REF",
        "derived-marked|main/backend/app/successor_runtime/language/object_contracts.py|"
        "build_c7_document_admission_return_contract_extension returns an unmarked derived value",
    ),
    (
        build_first_specimen_return_contract_registry,
        "successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS",
        "derived-marked|main/backend/app/successor_runtime/language/object_contracts.py|"
        "build_first_specimen_return_contract_registry returns an unmarked derived value",
    ),
    (
        build_frozen_base_return_contract_registry,
        "successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS",
        "derived-marked|main/backend/app/successor_runtime/language/object_contracts.py|"
        "build_frozen_base_return_contract_registry returns an unmarked derived value",
    ),
    (
        plans_structurally_equivalent,
        "successor_runtime.language.plan.ExecutionPlan",
        "derived-marked|main/backend/app/successor_runtime/language/plan.py|"
        "plans_structurally_equivalent returns an unmarked derived value",
    ),
)


def test_w07_derived_metadata_is_exact_and_non_authoritative() -> None:
    assert len(W07_DERIVED_EXACT_KEYS) == 7
    observed_keys: set[str] = set()

    for function, fact_source, exact_key in _W07_VIEWS:
        observed_keys.add(exact_key)
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

    assert observed_keys == W07_DERIVED_EXACT_KEYS


def test_w07_frozen_return_registry_preserves_additive_abi() -> None:
    base = build_frozen_base_return_contract_registry()
    extension = build_c7_document_admission_return_contract_extension()
    combined = build_first_specimen_return_contract_registry()

    assert len(extension) == 1
    assert extension[0][0] == DOCUMENT_ADMISSION_RETURN_CONTRACT_REF
    assert combined.entries == base.entries + extension


def test_w07_first_specimen_contract_projection_is_frozen() -> None:
    contracts = build_first_specimen_object_contracts()
    snapshot = build_first_specimen_domain_snapshot()

    assert tuple(contract.object_type.type_id for contract in contracts) == (FIRST_SPECIMEN_OBJECT_CONTRACT_REFS)
    assert snapshot.object_contract_refs == FIRST_SPECIMEN_OBJECT_CONTRACT_REFS
