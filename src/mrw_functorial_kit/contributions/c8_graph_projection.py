"""Explicit kit contribution catalog for the MRW C8.4 graph projection."""

from __future__ import annotations

from functorial_kit.contributions import ContributionCatalog
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import (
    LawWitness,
    define_law_witness,
    law_witness_reference,
)
from functorial_kit.native_contribution import (
    NativeContribution,
    NativeContributionSpec,
    define_native_contribution,
)
from app.successor_runtime.capabilities.c8_graph_projection_contribution import (
    C8_GRAPH_PROJECTION_DEFINITION,
    C8CellDefinition,
    C8GraphProjectionAssemblyContext,
    C8GraphProjectionRuntimeBinding,
    assemble_c8_graph_projection_definition,
    project_c8_graph_projection_definition,
    validate_c8_graph_projection_binding,
)


def _run_c8_graph_projection_native_catalog_law() -> None:
    """Exercise native definition, assembly, ordering and codec preservation."""

    from app.successor_runtime.capabilities.c8_program import (
        build_c8_bundle,
        validate_c8_graph_projection_contributions,
    )

    natives = validate_c8_graph_projection_contributions(c8_graph_projection_native_contributions)
    definitions = tuple(native.definition for native in natives)
    projected_ids = tuple(native.projection.id for native in natives)
    expected_ids = tuple(definition.contribution_id for definition in definitions)
    if projected_ids != expected_ids:
        raise AssertionError("native contribution order drifted from definition order")

    bindings: list[C8GraphProjectionRuntimeBinding] = []
    for native in natives:
        binding = native.assemble(C8GraphProjectionAssemblyContext())
        if isinstance(binding, Failure):
            raise AssertionError(binding.message)
        if binding.definition is not native.definition:
            raise AssertionError("native binding lost authoritative definition identity")
        codec = binding.payload_codec
        definition = native.definition
        sample = definition.payload_type(
            project_key="law-project",
            graph_id=f"law:{definition.cell_id}",
            node_keys=("ki:law",),
            node_types=("Topic",),
        )
        wire = codec.encode_payload(sample)
        decoded = codec.decode_payload(wire)
        if decoded != sample or codec.encode_payload(decoded) != wire:
            raise AssertionError(f"{definition.cell_id} payload codec round-trip drift")
        bindings.append(binding)

    bundle = build_c8_bundle(graph_projection_composition=natives)
    expected_operation_order = (
        "c8.typed_knowledge.demand_read.v1",
        "c8.writing.compose.v1",
        "c8.writing.stage.v1",
        "c8.report.stage.v1",
        *(definition.kind for definition in definitions),
    )
    actual_operation_order = tuple(operation.ref.kind for operation in bundle.operations)
    if actual_operation_order != expected_operation_order:
        raise AssertionError("C8 operation order drifted from native catalog order")
    for definition, binding in zip(definitions, bindings, strict=True):
        operation = next(operation for operation in bundle.operations if operation.ref.kind == definition.kind)
        if operation != binding.operation_contract:
            raise AssertionError(f"{definition.cell_id} operation contract drift")
        if bundle.codec_by_kind(definition.kind) is not binding.payload_codec:
            raise AssertionError(f"{definition.cell_id} payload codec identity drift")
        if bundle.profiles[definition.cell_id] != dict(binding.profiles):
            raise AssertionError(f"{definition.cell_id} profile binding drift")


_catalog_law = define_law_witness(
    "test_c8_graph_projection_native_catalog_law",
    _run_c8_graph_projection_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C8 graph catalog law: {_catalog_law.message}")

c8_graph_projection_law_witnesses: tuple[LawWitness, ...] = (_catalog_law,)
c8_graph_projection_law_witness_references = tuple(
    law_witness_reference(witness) for witness in c8_graph_projection_law_witnesses
)

_native = define_native_contribution(
    NativeContributionSpec(
        definition=C8_GRAPH_PROJECTION_DEFINITION,
        project=project_c8_graph_projection_definition,
        assemble=assemble_c8_graph_projection_definition,
        validate_binding=validate_c8_graph_projection_binding,
    )
)
if isinstance(_native, Failure):
    raise RuntimeError(f"invalid native C8 graph contribution: {_native.message}")

c8_graph_projection_native_contribution: NativeContribution[
    C8CellDefinition,
    C8GraphProjectionAssemblyContext,
    C8GraphProjectionRuntimeBinding,
] = _native

# This tuple is the sole native contribution catalog.  Both runtime consumers
# and the factory-free legacy catalog projection derive from it.
c8_graph_projection_native_contributions = (c8_graph_projection_native_contribution,)
c8_graph_projection_contribution = c8_graph_projection_native_contribution.projection

contribution_catalog = ContributionCatalog(
    contributions=tuple(native.projection for native in c8_graph_projection_native_contributions),
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "c8_graph_projection_contribution",
    "c8_graph_projection_law_witness_references",
    "c8_graph_projection_law_witnesses",
    "c8_graph_projection_native_contribution",
    "c8_graph_projection_native_contributions",
    "contribution_catalog",
]
