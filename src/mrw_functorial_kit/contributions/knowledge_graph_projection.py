"""Explicit kit contribution catalog for the MRW C8.4 graph projection."""

from __future__ import annotations

from functorial_kit.contributions import ContributionCatalog
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import (
    LawWitness,
    define_law_witness,
    law_witness_reference,
)
from app.successor_runtime.capabilities.knowledge_graph_projection_contribution import (
    KnowledgeGraphProjectionAssemblyContext,
    KnowledgeGraphProjectionRuntimeBinding,
    knowledge_graph_projection_native_contribution,
)


def _run_knowledge_graph_projection_native_catalog_law() -> None:
    """Exercise native definition, assembly, ordering and codec preservation."""

    from app.successor_runtime.capabilities.knowledge_program import (
        build_knowledge_bundle,
        validate_knowledge_graph_projection_contributions,
    )

    natives = validate_knowledge_graph_projection_contributions(knowledge_graph_projection_native_contributions)
    definitions = tuple(native.definition for native in natives)
    projected_ids = tuple(native.projection.id for native in natives)
    expected_ids = tuple(definition.contribution_id for definition in definitions)
    if projected_ids != expected_ids:
        raise AssertionError("native contribution order drifted from definition order")

    bindings: list[KnowledgeGraphProjectionRuntimeBinding] = []
    for native in natives:
        binding = native.assemble(KnowledgeGraphProjectionAssemblyContext())
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

    bundle = build_knowledge_bundle(graph_projection_composition=natives)
    expected_operation_order = (
        "knowledge.read.demand.v2",
        "knowledge.writing.compose.v2",
        "knowledge.writing.stage.v2",
        "knowledge.report.stage.v2",
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
    "test_knowledge_graph_projection_native_catalog_law",
    _run_knowledge_graph_projection_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C8 graph catalog law: {_catalog_law.message}")

knowledge_graph_projection_law_witnesses: tuple[LawWitness, ...] = (_catalog_law,)
knowledge_graph_projection_law_witness_references = tuple(
    law_witness_reference(witness) for witness in knowledge_graph_projection_law_witnesses
)

# This tuple is the sole native contribution catalog.  Both runtime consumers
# and the factory-free legacy catalog projection derive from it.
knowledge_graph_projection_native_contributions = (knowledge_graph_projection_native_contribution,)
knowledge_graph_projection_contribution = knowledge_graph_projection_native_contribution.projection

contribution_catalog = ContributionCatalog(
    contributions=tuple(native.projection for native in knowledge_graph_projection_native_contributions),
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "knowledge_graph_projection_contribution",
    "knowledge_graph_projection_law_witness_references",
    "knowledge_graph_projection_law_witnesses",
    "knowledge_graph_projection_native_contribution",
    "knowledge_graph_projection_native_contributions",
    "contribution_catalog",
]
