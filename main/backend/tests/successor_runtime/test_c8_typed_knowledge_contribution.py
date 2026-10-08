"""C8.1 native typed-knowledge contribution declaration tests."""

from __future__ import annotations

import dataclasses
from app.successor_runtime.capabilities.knowledge_program import (
    KnowledgeDemandReadInput as LegacyC8DemandReadInput,
    build_knowledge_bundle,
)
from app.successor_runtime.capabilities.typed_knowledge import demand_read
from app.successor_runtime.capabilities.typed_knowledge_contribution import (
    KNOWLEDGE_READ_INPUT_TYPE,
    KNOWLEDGE_READ_KIND,
    KNOWLEDGE_READ_OPERATION_ID,
    KNOWLEDGE_READ_OWNER,
    KNOWLEDGE_READ_PAYLOAD_CODEC_ID,
    KNOWLEDGE_READ_RESULT_TYPE,
    KNOWLEDGE_READ_RETURN_CONTRACT_REF,
    KNOWLEDGE_READ_ROLLBACK_REFS,
    KNOWLEDGE_TYPED_KNOWLEDGE_AUTHOR_SOURCE,
    KNOWLEDGE_TYPED_KNOWLEDGE_NATIVE,
    KnowledgeDemandReadInput,
)
from app.successor_runtime.capabilities.knowledge_native_contribution import (
    KnowledgeNativeAssemblyContext,
    KnowledgeNativeDefinition,
    KnowledgeNativeRuntimeBinding,
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
    validate_knowledge_native_binding,
)
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import BindingRejected, NativeContribution
from mrw_functorial_kit.core.knowledge_semantics import knowledge_operation_kinds, knowledge_typed_knowledge_failures

from .p4_c8_fixture import PROJECT_KEY, captured_item, new_registry


def _native() -> NativeContribution[
    KnowledgeNativeDefinition,
    KnowledgeNativeAssemblyContext,
    KnowledgeNativeRuntimeBinding,
]:
    native = compile_native_contribution(
        KNOWLEDGE_TYPED_KNOWLEDGE_AUTHOR_SOURCE,
        KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
    )
    assert not isinstance(native, Failure)
    return native


def test_projection_publishes_one_factory_free_native_declaration() -> None:
    native = _native()
    projection = native.projection

    assert projection.id == "mrw.knowledge.read.native.v2"
    assert projection.owner == KNOWLEDGE_READ_OWNER
    assert projection.factory is None
    assert [(obj.id, obj.kind, obj.references) for obj in projection.objects] == [
        ("KnowledgeDemandReadInput.v2", "ObjectType", ()),
        ("KnowledgeDemandReadResult.v2", "ObjectType", ("KnowledgeDemandReadInput.v2",)),
        (
            "knowledge.read.demand.v2",
            "Capability",
            ("KnowledgeDemandReadInput.v2", "KnowledgeDemandReadResult.v2"),
        ),
        (
            "mrw.knowledge.demand-read.codec.v2",
            "PayloadCodec",
            ("knowledge.read.demand.v2", "KnowledgeDemandReadInput.v2"),
        ),
    ]
    assert projection.vocabularies == (knowledge_operation_kinds,)
    assert projection.failures == (knowledge_typed_knowledge_failures,)


def test_native_contract_profiles_codec_and_atom_match_legacy_c8_1() -> None:
    native = _native()
    definition = native.definition
    operation = definition.operations[0]
    bundle = build_knowledge_bundle()
    legacy_contract = next(
        contract for contract in bundle.operations if contract.ref.kind == KNOWLEDGE_READ_KIND
    )
    legacy_codec = bundle.codec_by_kind(KNOWLEDGE_READ_KIND)

    assert definition.execution_class == "EFFECTFUL"
    assert definition.ordered_operation_ids == (KNOWLEDGE_READ_OPERATION_ID,)
    assert operation.source.operation_id == KNOWLEDGE_READ_OPERATION_ID
    assert operation.source.kind == KNOWLEDGE_READ_KIND
    assert operation.source.input_type == KNOWLEDGE_READ_INPUT_TYPE
    assert operation.source.output_type == KNOWLEDGE_READ_RESULT_TYPE
    assert operation.source.return_contract_ref == KNOWLEDGE_READ_RETURN_CONTRACT_REF
    assert operation.source.value_suffix == "knowledge-read"
    assert operation.operation_contract == legacy_contract
    assert dict(definition.profiles) == dict(bundle.profiles["knowledge.read.v2"])
    assert definition.failure_codes == (
        "DEMAND_READ_UNAVAILABLE",
        "DEMAND_READ_AMBIGUOUS",
        "CANONICAL_REF_VALIDATION_FAILED",
    )

    codec = operation.payload_codec
    assert codec is not None
    assert codec.codec_id == KNOWLEDGE_READ_PAYLOAD_CODEC_ID == legacy_codec.codec_id
    assert codec.codec_version == legacy_codec.codec_version
    assert codec.payload_type_id == KNOWLEDGE_READ_INPUT_TYPE.type_id
    assert codec.codec_digest == legacy_codec.codec_digest
    assert codec.contract_ref == legacy_contract.ref == legacy_codec.contract_ref
    payload = KnowledgeDemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:contribution",
        fields=("canonical_statement", "evidence_refs"),
    )
    wire = codec.encode_payload(payload)
    expected_wire = dataclasses.asdict(payload)
    expected_wire["fields"] = list(expected_wire["fields"])
    assert wire == expected_wire
    decoded = codec.decode_payload(wire)
    assert decoded == payload
    assert decoded.payload_digest == payload.payload_digest

    atom = operation.program_atom
    assert (atom.operation_id, atom.operation_kind, atom.payload_codec_id) == (
        KNOWLEDGE_READ_OPERATION_ID,
        KNOWLEDGE_READ_KIND,
        KNOWLEDGE_READ_PAYLOAD_CODEC_ID,
    )
    assert (atom.input_type, atom.output_type, atom.return_contract_ref) == (
        KNOWLEDGE_READ_INPUT_TYPE,
        KNOWLEDGE_READ_RESULT_TYPE,
        KNOWLEDGE_READ_RETURN_CONTRACT_REF,
    )
    assert atom.value_suffix == "knowledge-read"


def test_binding_assembly_and_drift_rejection_preserve_c8_1_declarations() -> None:
    native = _native()
    binding = native.assemble(KnowledgeNativeAssemblyContext())
    assert not isinstance(binding, Failure)

    accepted = validate_knowledge_native_binding(native.definition, binding)
    assert not isinstance(accepted, BindingRejected)

    drifted = dataclasses.replace(binding, cell_id="C8.1.drift")
    rejected = validate_knowledge_native_binding(native.definition, drifted)
    assert isinstance(rejected, BindingRejected)
    assert [(issue.path, issue.message) for issue in rejected.issues] == [
        ("$.binding.cell_id", "cell id drift")
    ]

    rollback = binding.assembly_rollback_binding()
    assert rollback.cell_id == "knowledge.read.v2"
    assert rollback.status == "PRESENT"
    assert rollback.binding_refs == KNOWLEDGE_READ_ROLLBACK_REFS


def test_payload_and_original_demand_read_semantics_remain_compatible() -> None:
    payload = KnowledgeDemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:legacy-compatible",
        fields=("canonical_statement", "evidence_refs"),
    )
    legacy_payload = LegacyC8DemandReadInput(
        project_key=payload.project_key,
        item_key=payload.item_key,
        fields=payload.fields,
    )
    assert payload.payload_digest == legacy_payload.payload_digest
    assert len(payload.payload_digest) == 64
    assert not isinstance(KNOWLEDGE_TYPED_KNOWLEDGE_NATIVE, Failure)

    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    assert set(read.fields) == {"canonical_statement", "evidence_refs"}
    assert read.fields["canonical_statement"] == item.canonical_statement
