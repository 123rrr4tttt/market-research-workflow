"""Native C8.2 writing contribution projection and binding tests."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from app.successor_runtime.assembly.knowledge_assembly import (
    KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
    KnowledgeWritingComposeStageRouteHandler,
    KNOWLEDGE_WRITING_STAGE_FAILURE_CODE,
)
from app.successor_runtime.capabilities import knowledge_common as c8
from app.successor_runtime.capabilities.knowledge_native_contribution import (
    KnowledgeNativeAssemblyContext,
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
)
from app.successor_runtime.capabilities.knowledge_program import (
    KNOWLEDGE_WRITING_COMPOSE_KIND,
    KNOWLEDGE_WRITING_STAGE_KIND,
    build_knowledge_bundle,
)
from app.successor_runtime.capabilities.typed_knowledge import demand_read
from app.successor_runtime.capabilities.knowledge_writing import (
    compose_writing_handoff,
    project_writing_card,
    stage_writing_artifact,
)
from app.successor_runtime.capabilities.knowledge_writing_contribution import (
    KNOWLEDGE_WRITING_AUTHOR_SOURCE,
    KNOWLEDGE_WRITING_NATIVE_DEFINITION,
    KnowledgeWritingComposeInput,
    knowledge_writing_native_contribution,
)
from functorial_kit.contributions import compose_contributions
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import BindingRejected
from app.successor_runtime.runtime.node import DefiniteInterpreterFailure

from .p4_c8_fixture import (
    PROJECT_KEY,
    SELECTION_HASH,
    SELECTION_TEXT,
    captured_item,
    new_registry,
)


def _payload() -> KnowledgeWritingComposeInput:
    return KnowledgeWritingComposeInput(
        project_key=PROJECT_KEY,
        knowledge_item_key=captured_item().key,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
        demand_fields=("canonical_statement", "evidence_refs"),
    )


def test_projection_preserves_two_ordered_native_contracts() -> None:
    definition = KNOWLEDGE_WRITING_NATIVE_DEFINITION
    projection = knowledge_writing_native_contribution.projection

    assert definition.cell_id == "knowledge.writing.v2"
    assert definition.owner == "knowledge.writing.v2"
    assert definition.execution_class == "PURE_TRANSFORM"
    assert definition.ordered_operation_ids == ("knowledge.writing.compose", "knowledge.writing.stage")
    assert [operation.source.operation_id for operation in definition.operations] == [
        "knowledge.writing.compose",
        "knowledge.writing.stage",
    ]
    assert projection.id == "mrw.knowledge.writing.native.v2"
    assert projection.owner == definition.owner
    assert projection.factory is None
    assert projection.failures == (definition.failure_family,)
    object_ids = [obj.id for obj in projection.objects]
    assert len(object_ids) == len(set(object_ids))
    composed = compose_contributions((projection,))
    assert not isinstance(composed, Failure)
    assert "KnowledgeWritingComposeInput.v2" in object_ids
    assert "StagedKnowledgeWritingArtifact.v2" in object_ids
    assert "knowledge.writing.compose.v2" in object_ids
    assert "knowledge.writing.stage.v2" in object_ids


def test_native_contracts_match_both_existing_bundle_contracts() -> None:
    bundle = build_knowledge_bundle()
    existing = {
        operation.ref.kind: operation
        for operation in bundle.operations
        if operation.ref.kind in {KNOWLEDGE_WRITING_COMPOSE_KIND, KNOWLEDGE_WRITING_STAGE_KIND}
    }
    assert set(existing) == {KNOWLEDGE_WRITING_COMPOSE_KIND, KNOWLEDGE_WRITING_STAGE_KIND}

    native_contracts = {
        operation.operation_contract.ref.kind: operation.operation_contract
        for operation in KNOWLEDGE_WRITING_NATIVE_DEFINITION.operations
    }
    assert set(native_contracts) == set(existing)
    for kind, expected in existing.items():
        assert native_contracts[kind] == expected

    profile_by_name = {
        name: profile
        for name, profile in bundle.profiles["knowledge.writing.v2"].items()
    }
    for name, profile in profile_by_name.items():
        assert KNOWLEDGE_WRITING_NATIVE_DEFINITION.profiles[name] == profile


def test_compose_payload_codec_identity_and_stage_dataflow_are_preserved() -> None:
    compose, stage = KNOWLEDGE_WRITING_NATIVE_DEFINITION.operations

    assert compose.source.payload_codec_id is not None
    assert compose.payload_codec is not None
    assert compose.payload_codec.payload_type_id == "KnowledgeWritingComposeInput.v2"
    assert compose.source.payload_type is KnowledgeWritingComposeInput
    assert stage.source.payload_codec_id is None
    assert stage.source.payload_type is None
    assert stage.payload_codec is None
    assert stage.source.input_type == compose.source.output_type
    assert stage.program_atom.payload_codec_id is None

    payload = _payload()
    wire = compose.payload_codec.encode_payload(payload)
    decoded = compose.payload_codec.decode_payload(wire)
    assert isinstance(decoded, KnowledgeWritingComposeInput)
    assert dataclasses.asdict(decoded) == dataclasses.asdict(payload)

    legacy_codec = build_knowledge_bundle().codec_by_kind(KNOWLEDGE_WRITING_COMPOSE_KIND)
    assert compose.payload_codec.codec_id == legacy_codec.codec_id
    assert compose.payload_codec.codec_version == legacy_codec.codec_version
    assert compose.payload_codec.payload_type_id == legacy_codec.payload_type_id
    assert compose.payload_codec.codec_digest == legacy_codec.codec_digest
    assert compose.payload_codec.contract_ref == legacy_codec.contract_ref


def test_program_atoms_preserve_compose_before_stage() -> None:
    definition = KNOWLEDGE_WRITING_NATIVE_DEFINITION
    compose, stage = definition.operations

    assert [op.program_atom.operation_id for op in definition.operations] == [
        "knowledge.writing.compose",
        "knowledge.writing.stage",
    ]
    assert compose.program_atom.operation_kind == KNOWLEDGE_WRITING_COMPOSE_KIND
    assert compose.program_atom.input_type.type_id == "KnowledgeWritingComposeInput.v2"
    assert compose.program_atom.output_type.type_id == "KnowledgeWritingHandoff.v2"
    assert compose.program_atom.value_suffix == "knowledge-writing-compose"
    assert stage.program_atom.operation_kind == KNOWLEDGE_WRITING_STAGE_KIND
    assert stage.program_atom.input_type == compose.program_atom.output_type
    assert stage.program_atom.output_type.type_id == "StagedKnowledgeWritingArtifact.v2"
    assert stage.program_atom.value_suffix == "knowledge-writing-stage"


def test_rollback_and_exact_cell_texts_are_preserved() -> None:
    binding = knowledge_writing_native_contribution.assemble(KnowledgeNativeAssemblyContext())
    assert not isinstance(binding, Failure)

    rollback = binding.assembly_rollback_binding()
    assert rollback.cell_id == "knowledge.writing.v2"
    assert rollback.status == "PRESENT"
    assert rollback.binding_refs == (
        "main/backend/app/successor_migration/legacy_c8_writing.py",
        "main/backend/app/successor_runtime/assembly/c8_assembly.py",
    )

    unwired = binding.declared_cell()
    assert unwired.to_dict() == {
        "cell_id": "knowledge.writing.v2",
        "family_id": "mrw.knowledge",
        "status": "UNWIRED_DECLARED",
        "operation_contract_refs": ["knowledge.writing.compose.v2", "knowledge.writing.stage.v2"],
        "handler_binding_digest": None,
        "recovery_binding_ref": (
            "knowledge.writing.recovery.v2#retained-staged-values-no-authority-reversal"
        ),
        "rollback_binding_refs": [],
        "required_wiring": [
            "c82_payload compose+stage 纯 route closure",
            "admission_not_called/export_not_executed 保持",
        ],
        "note": (
            "缺 c82_payload 的 compose_writing_handoff + stage_writing_artifact "
            "纯 route closure（read/handoff 输入）；"
            "admission/export authority closed"
        ),
    }

    installed = binding.installed_cell(handler_binding_digest="0" * 64)
    assert installed.status == "INSTALLED"
    assert installed.handler_binding_digest == "0" * 64
    assert installed.required_wiring == ("admission_not_called/export_not_executed 保持",)
    assert installed.note == (
        "LOCAL_OFFLINE knowledge.writing.v2 compose+stage pure route handler installed; "
        "no PostgreSQL write adopted"
    )


def test_swapped_operations_are_rejected_as_definition_drift() -> None:
    swapped = dataclasses.replace(
        KNOWLEDGE_WRITING_AUTHOR_SOURCE,
        operations=(KNOWLEDGE_WRITING_AUTHOR_SOURCE.operations[1], KNOWLEDGE_WRITING_AUTHOR_SOURCE.operations[0]),
    )
    result = compile_native_contribution(swapped, KNOWLEDGE_NATIVE_CONTRIBUTION_RULE)

    assert isinstance(result, Failure)
    assert result.code == "CONTRIBUTION_INVALID"
    assert any(
        issue.get("path") == "$.definition.ordered_operation_ids"
        for issue in result.context.get("issues", ())
    )


def test_binding_cell_and_assembly_drift_are_rejected() -> None:
    binding = knowledge_writing_native_contribution.assemble(KnowledgeNativeAssemblyContext())
    assert not isinstance(binding, Failure)

    drift = dataclasses.replace(
        binding,
        cell_id="C8.test",
        assembly=dataclasses.replace(
            binding.assembly,
            note="changed cell note",
            rollback_refs=("changed:rollback",),
        ),
    )
    decision = KNOWLEDGE_NATIVE_CONTRIBUTION_RULE.validate_binding(
        KNOWLEDGE_WRITING_NATIVE_DEFINITION,
        drift,
    )
    assert isinstance(decision, BindingRejected)
    messages = {issue.message for issue in decision.issues}
    assert "cell id drift" in messages
    assert "assembly declaration drift" in messages


def test_payload_and_operations_witness_existing_writing_semantics() -> None:
    payload = _payload()
    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=payload.demand_fields,
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    handoff = compose_writing_handoff(
        read,
        selection_hash=payload.selection_hash,
        selection_text=payload.selection_text,
    )
    artifact = stage_writing_artifact(project_writing_card(handoff))

    assert handoff.project_key == payload.project_key
    assert handoff.knowledge_item_key == payload.knowledge_item_key
    assert artifact.stage_sequence == (
        "demand_read",
        "writing_handoff",
        "writing_card",
        "staged_artifact",
    )
    assert artifact.provenance_chain == (
        "demand_read",
        "writing_handoff",
        "writing_card",
        "staged_artifact",
    )
    assert artifact.provenance.canonical_identity == f"knowledge:{PROJECT_KEY}:{item.key}"


def test_payload_digest_rejects_body_drift() -> None:
    payload = _payload()
    with pytest.raises(Exception, match="payload_digest does not match"):
        KnowledgeWritingComposeInput(
            project_key=payload.project_key,
            knowledge_item_key=payload.knowledge_item_key,
            selection_hash=payload.selection_hash,
            selection_text="changed selection",
            demand_fields=payload.demand_fields,
            payload_digest=payload.payload_digest,
        )


def test_route_failure_records_current_knowledge_writing_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    binding = SimpleNamespace(
        binding_digest="1" * 64,
        interpreter_profile_digest="2" * 64,
        operation_contract_digest="3" * 64,
    )
    handler = KnowledgeWritingComposeStageRouteHandler(
        payload={
            "read": read,
            "selection_hash": SELECTION_HASH,
            "selection_text": SELECTION_TEXT,
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
        "app.successor_runtime.assembly.knowledge_assembly.stage_writing_artifact",
        unavailable,
    )
    with pytest.raises(DefiniteInterpreterFailure) as captured:
        handler.execute(assignment, claim, None)  # type: ignore[arg-type]
    assert captured.value.failure_code == KNOWLEDGE_WRITING_STAGE_FAILURE_CODE
    assert captured.value.failure_code in KNOWLEDGE_WRITING_NATIVE_DEFINITION.failure_codes
