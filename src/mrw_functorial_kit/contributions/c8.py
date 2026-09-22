"""Explicit kit contribution catalog for the native MRW C8 cells."""

from __future__ import annotations

from functorial_kit.contributions import ContributionCatalog
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import (
    LawWitness,
    define_law_witness,
    law_witness_reference,
)
from app.successor_runtime.capabilities.c8_graph_projection_contribution import (
    C8GraphProjectionAssemblyContext,
)
from mrw_functorial_kit.contributions.c8_graph_projection import (
    c8_graph_projection_native_contributions,
)
from app.successor_runtime.capabilities.c8_native_contribution import C8NativeAssemblyContext
from app.successor_runtime.capabilities.c8_program import (
    build_c8_bundle,
    c8_native_contributions,
    validate_c8_graph_projection_contributions,
    validate_c8_native_contributions,
)


def _run_c8_native_catalog_law() -> None:
    """Exercise all native definitions, assembly order, and codec identity."""

    native_contributions = validate_c8_native_contributions(c8_native_contributions)
    graph_contributions = validate_c8_graph_projection_contributions(
        c8_graph_projection_native_contributions
    )
    natives = (*native_contributions, *graph_contributions)
    projected_ids = tuple(native.projection.id for native in natives)
    expected_ids = tuple(native.definition.contribution_id for native in natives)
    if projected_ids != expected_ids:
        raise AssertionError("native contribution order drifted from definition order")

    for native in native_contributions:
        binding = native.assemble(C8NativeAssemblyContext())
        if isinstance(binding, Failure):
            raise AssertionError(binding.message)
    for native in graph_contributions:
        binding = native.assemble(C8GraphProjectionAssemblyContext())
        if isinstance(binding, Failure):
            raise AssertionError(binding.message)

    bundle = build_c8_bundle(
        native_composition=native_contributions,
        graph_projection_composition=graph_contributions,
    )
    expected_kinds: tuple[str, ...] = ()
    for native in native_contributions:
        expected_kinds += tuple(
            operation.source.kind for operation in native.definition.operations
        )
    expected_kinds += tuple(
        native.definition.kind for native in graph_contributions
    )
    actual_kinds = tuple(operation.ref.kind for operation in bundle.operations)
    if actual_kinds != expected_kinds:
        raise AssertionError("C8 operation order drifted from native catalog order")
    for native in native_contributions:
        for operation in native.definition.operations:
            bundle_operation = next(
                candidate
                for candidate in bundle.operations
                if candidate.ref.kind == operation.source.kind
            )
            if bundle_operation != operation.operation_contract:
                raise AssertionError(
                    f"{native.definition.cell_id} operation contract drift"
                )
            if operation.payload_codec is not None:
                if bundle.codec_by_kind(operation.source.kind) is not operation.payload_codec:
                    raise AssertionError(
                        f"{native.definition.cell_id} payload codec identity drift"
                    )
            if bundle.profiles[native.definition.cell_id] != dict(native.definition.profiles):
                raise AssertionError(f"{native.definition.cell_id} profile binding drift")
    for native in graph_contributions:
        definition = native.definition
        bundle_operation = next(
            candidate
            for candidate in bundle.operations
            if candidate.ref.kind == definition.kind
        )
        if bundle_operation != definition.operation_contract:
            raise AssertionError(f"{definition.cell_id} operation contract drift")
        if bundle.codec_by_kind(definition.kind) is not definition.payload_codec:
            raise AssertionError(f"{definition.cell_id} payload codec identity drift")
        if bundle.profiles[definition.cell_id] != dict(definition.profiles):
            raise AssertionError(f"{definition.cell_id} profile binding drift")


_catalog_law = define_law_witness(
    "test_c8_native_catalog_law",
    _run_c8_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C8 native catalog law: {_catalog_law.message}")

c8_law_witnesses: tuple[LawWitness, ...] = (_catalog_law,)
c8_law_witness_references = tuple(
    law_witness_reference(witness) for witness in c8_law_witnesses
)

# This tuple is the sole native C8 contribution catalog. Runtime consumers and
# the factory-free generated projections both derive from it.
c8_native_catalog = (*c8_native_contributions, *c8_graph_projection_native_contributions)
c8_contribution_catalog = tuple(native.projection for native in c8_native_catalog)

contribution_catalog = ContributionCatalog(
    contributions=c8_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "c8_contribution_catalog",
    "c8_law_witness_references",
    "c8_law_witnesses",
    "c8_native_catalog",
    "contribution_catalog",
]
