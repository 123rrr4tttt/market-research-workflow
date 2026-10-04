"""C8.1 native typed-knowledge contribution declaration tests."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.successor_runtime.assembly.base import (
    KnowledgeAssemblyOptions,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.knowledge_assembly import (
    KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
    KnowledgeDemandReadRouteHandler,
    KNOWLEDGE_DEMAND_READ_FAILURE_CODE,
    build_knowledge_assembly,
    build_deterministic_knowledge_payloads,
)
from app.successor_runtime.capabilities import knowledge_common as c8
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
from app.successor_runtime.runtime.node import DefiniteInterpreterFailure

from .p4_c8_fixture import PROJECT_KEY, captured_item, new_registry


def _engine() -> Engine:
    return create_engine("sqlite:///:memory:")


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


def test_declared_and_installed_cells_match_existing_assembly_path() -> None:
    native = _native()
    binding = native.assemble(KnowledgeNativeAssemblyContext())
    assert not isinstance(binding, Failure)
    scope = local_assembly_scope_digest()

    unbound = build_knowledge_assembly(
        engine=_engine(),
        project_scope_digest=scope,
    )
    assert unbound.cell("knowledge.read.v2") == binding.declared_cell()

    payloads = build_deterministic_knowledge_payloads(scope)
    installed = build_knowledge_assembly(
        engine=_engine(),
        project_scope_digest=scope,
        options=KnowledgeAssemblyOptions(c81_payload=payloads["c81_payload"]),
    )
    handler = next(
        handler
        for handler in installed.handlers
        if isinstance(handler, KnowledgeDemandReadRouteHandler)
    )
    assert installed.cell("knowledge.read.v2") == binding.installed_cell(
        handler.handler_binding_digest
    )
    assert installed.cell("knowledge.read.v2").status == "INSTALLED"
    assert installed.cell("knowledge.read.v2").required_wiring == (
        "admission_not_called/export_not_executed 保持",
    )

    rollback = next(
        declaration
        for declaration in installed.rollback_bindings
        if declaration.cell_id == "knowledge.read.v2"
    )
    assert rollback == binding.assembly_rollback_binding()
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


def test_route_failure_records_current_knowledge_read_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = SimpleNamespace(
        binding_digest="1" * 64,
        interpreter_profile_digest="2" * 64,
        operation_contract_digest="3" * 64,
    )
    handler = KnowledgeDemandReadRouteHandler(
        payload={
            "items": (captured_item(),),
            "item_key": captured_item().key,
            "fields": ("canonical_statement",),
            "project_key": PROJECT_KEY,
            "registry": new_registry(),
        },
        binding=binding,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
    )
    assignment = SimpleNamespace(
        assignment_digest="4" * 64,
        claim_authority_epoch=1,
        handler_binding_digest=binding.binding_digest,
        operation_contract_digest=binding.operation_contract_digest,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
    )
    claim = SimpleNamespace(
        assignment_digest=assignment.assignment_digest,
        claim_authority_epoch=assignment.claim_authority_epoch,
    )

    def unavailable(*args: object, **kwargs: object) -> object:
        raise c8.UnavailableProjection("unavailable")

    monkeypatch.setattr(
        "app.successor_runtime.assembly.knowledge_assembly.demand_read",
        unavailable,
    )
    with pytest.raises(DefiniteInterpreterFailure) as captured:
        handler.execute(assignment, claim, None)  # type: ignore[arg-type]
    assert captured.value.failure_code == KNOWLEDGE_DEMAND_READ_FAILURE_CODE
    assert captured.value.failure_code in KNOWLEDGE_TYPED_KNOWLEDGE_AUTHOR_SOURCE.failure_codes
