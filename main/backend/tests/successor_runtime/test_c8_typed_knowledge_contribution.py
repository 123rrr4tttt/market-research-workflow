"""C8.1 native typed-knowledge contribution declaration tests."""

from __future__ import annotations

import dataclasses

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.successor_runtime.assembly.base import (
    C8AssemblyOptions,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c8_assembly import (
    C8_1DemandReadRouteHandler,
    build_c8_assembly,
    build_deterministic_c8_payloads,
)
from app.successor_runtime.capabilities.c8_program import (
    C8DemandReadInput as LegacyC8DemandReadInput,
    build_c8_bundle,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import demand_read
from app.successor_runtime.capabilities.c8_typed_knowledge_contribution import (
    C8_1_INPUT_TYPE,
    C8_1_KIND,
    C8_1_OPERATION_ID,
    C8_1_OWNER,
    C8_1_PAYLOAD_CODEC_ID,
    C8_1_RESULT_TYPE,
    C8_1_RETURN_CONTRACT_REF,
    C8_1_ROLLBACK_REFS,
    C8_TYPED_KNOWLEDGE_AUTHOR_SOURCE,
    C8_TYPED_KNOWLEDGE_NATIVE,
    C8DemandReadInput,
)
from app.successor_runtime.capabilities.c8_native_contribution import (
    C8NativeAssemblyContext,
    C8NativeDefinition,
    C8NativeRuntimeBinding,
    C8_NATIVE_CONTRIBUTION_RULE,
    validate_c8_native_binding,
)
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import BindingRejected, NativeContribution
from mrw_functorial_kit.core.c8_semantics import (
    c8_operation_kinds,
    c8_typed_knowledge_failures,
)

from .p4_c8_fixture import PROJECT_KEY, captured_item, new_registry


def _engine() -> Engine:
    return create_engine("sqlite:///:memory:")


def _native() -> NativeContribution[
    C8NativeDefinition,
    C8NativeAssemblyContext,
    C8NativeRuntimeBinding,
]:
    native = compile_native_contribution(
        C8_TYPED_KNOWLEDGE_AUTHOR_SOURCE,
        C8_NATIVE_CONTRIBUTION_RULE,
    )
    assert not isinstance(native, Failure)
    return native


def test_projection_publishes_one_factory_free_native_declaration() -> None:
    native = _native()
    projection = native.projection

    assert projection.id == "mrw.successor.c8.typed-knowledge.v1"
    assert projection.owner == C8_1_OWNER
    assert projection.factory is None
    assert [(obj.id, obj.kind, obj.references) for obj in projection.objects] == [
        ("C8DemandReadInput.v1", "ObjectType", ()),
        ("C8DemandReadResult.v1", "ObjectType", ("C8DemandReadInput.v1",)),
        (
            "c8.typed_knowledge.demand_read",
            "Capability",
            ("C8DemandReadInput.v1", "C8DemandReadResult.v1"),
        ),
        (
            "mrw.successor.c8.c8-1.payload.codec.v1",
            "PayloadCodec",
            ("c8.typed_knowledge.demand_read", "C8DemandReadInput.v1"),
        ),
    ]
    assert projection.vocabularies == (c8_operation_kinds,)
    assert projection.failures == (c8_typed_knowledge_failures,)


def test_native_contract_profiles_codec_and_atom_match_legacy_c8_1() -> None:
    native = _native()
    definition = native.definition
    operation = definition.operations[0]
    bundle = build_c8_bundle()
    legacy_contract = next(
        contract for contract in bundle.operations if contract.ref.kind == C8_1_KIND
    )
    legacy_codec = bundle.codec_by_kind(C8_1_KIND)

    assert definition.execution_class == "EFFECTFUL"
    assert definition.ordered_operation_ids == (C8_1_OPERATION_ID,)
    assert operation.source.operation_id == C8_1_OPERATION_ID
    assert operation.source.kind == C8_1_KIND
    assert operation.source.input_type == C8_1_INPUT_TYPE
    assert operation.source.output_type == C8_1_RESULT_TYPE
    assert operation.source.return_contract_ref == C8_1_RETURN_CONTRACT_REF
    assert operation.source.value_suffix == "c8-1"
    assert operation.operation_contract == legacy_contract
    assert dict(definition.profiles) == dict(bundle.profiles["C8.1"])
    assert definition.failure_codes == (
        "DEMAND_READ_UNAVAILABLE",
        "DEMAND_READ_AMBIGUOUS",
        "CANONICAL_REF_VALIDATION_FAILED",
    )

    codec = operation.payload_codec
    assert codec is not None
    assert codec.codec_id == C8_1_PAYLOAD_CODEC_ID == legacy_codec.codec_id
    assert codec.codec_version == legacy_codec.codec_version
    assert codec.payload_type_id == C8_1_INPUT_TYPE.type_id
    assert codec.codec_digest == legacy_codec.codec_digest
    assert codec.contract_ref == legacy_contract.ref == legacy_codec.contract_ref
    payload = C8DemandReadInput(
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
        C8_1_OPERATION_ID,
        C8_1_KIND,
        C8_1_PAYLOAD_CODEC_ID,
    )
    assert (atom.input_type, atom.output_type, atom.return_contract_ref) == (
        C8_1_INPUT_TYPE,
        C8_1_RESULT_TYPE,
        C8_1_RETURN_CONTRACT_REF,
    )
    assert atom.value_suffix == "c8-1"


def test_binding_assembly_and_drift_rejection_preserve_c8_1_declarations() -> None:
    native = _native()
    binding = native.assemble(C8NativeAssemblyContext())
    assert not isinstance(binding, Failure)

    accepted = validate_c8_native_binding(native.definition, binding)
    assert not isinstance(accepted, BindingRejected)

    drifted = dataclasses.replace(binding, cell_id="C8.1.drift")
    rejected = validate_c8_native_binding(native.definition, drifted)
    assert isinstance(rejected, BindingRejected)
    assert [(issue.path, issue.message) for issue in rejected.issues] == [
        ("$.binding.cell_id", "cell id drift")
    ]

    rollback = binding.assembly_rollback_binding()
    assert rollback.cell_id == "C8.1"
    assert rollback.status == "PRESENT"
    assert rollback.binding_refs == C8_1_ROLLBACK_REFS


def test_declared_and_installed_cells_match_existing_assembly_path() -> None:
    native = _native()
    binding = native.assemble(C8NativeAssemblyContext())
    assert not isinstance(binding, Failure)
    scope = local_assembly_scope_digest()

    unbound = build_c8_assembly(
        engine=_engine(),
        project_scope_digest=scope,
    )
    assert unbound.cell("C8.1") == binding.declared_cell()

    payloads = build_deterministic_c8_payloads(scope)
    installed = build_c8_assembly(
        engine=_engine(),
        project_scope_digest=scope,
        options=C8AssemblyOptions(c81_payload=payloads["c81_payload"]),
    )
    handler = next(
        handler
        for handler in installed.handlers
        if isinstance(handler, C8_1DemandReadRouteHandler)
    )
    assert installed.cell("C8.1") == binding.installed_cell(
        handler.handler_binding_digest
    )
    assert installed.cell("C8.1").status == "INSTALLED"
    assert installed.cell("C8.1").required_wiring == (
        "admission_not_called/export_not_executed 保持",
    )

    rollback = next(
        declaration
        for declaration in installed.rollback_bindings
        if declaration.cell_id == "C8.1"
    )
    assert rollback == binding.assembly_rollback_binding()
    assert rollback.binding_refs == C8_1_ROLLBACK_REFS


def test_payload_and_original_demand_read_semantics_remain_compatible() -> None:
    payload = C8DemandReadInput(
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
    assert not isinstance(C8_TYPED_KNOWLEDGE_NATIVE, Failure)

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
