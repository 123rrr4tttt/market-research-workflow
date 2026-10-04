"""C8.3 native report-stage contribution tests."""

from __future__ import annotations

import dataclasses

import pytest
from functorial_kit.contributions import compose_contributions
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import BindingRejected

from app.successor_runtime.capabilities import knowledge_common
from app.successor_runtime.capabilities.knowledge_native_contribution import (
    KnowledgeNativeAssemblyContext,
    validate_knowledge_native_binding,
)
from app.successor_runtime.capabilities.knowledge_program import (
    KnowledgeReportStageInput as LegacyC8ReportStageInput,
)
from app.successor_runtime.capabilities.knowledge_program import (
    build_knowledge_bundle,
    build_knowledge_catalog,
    build_knowledge_program,
)
from app.successor_runtime.capabilities.knowledge_report import (
    build_report_admission_intent,
    build_report_artifact,
    build_report_stage,
    verify_report_stage,
)
from app.successor_runtime.capabilities.knowledge_report_contribution import (
    KNOWLEDGE_REPORT_CONTRIBUTION_ID,
    KNOWLEDGE_REPORT_KIND,
    KNOWLEDGE_REPORT_OPERATION_ID,
    KNOWLEDGE_REPORT_OWNER,
    KNOWLEDGE_REPORT_PAYLOAD_CODEC_ID,
    KNOWLEDGE_REPORT_ROLLBACK_REF,
    KnowledgeReportStageInput,
    KNOWLEDGE_REPORT_STAGE_AUTHOR_SOURCE,
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
    knowledge_report_native_contribution,
)
from app.successor_runtime.capabilities.typed_knowledge import demand_read
from app.successor_runtime.capabilities.checksum import content_digest
from mrw_functorial_kit.core.knowledge_semantics import knowledge_report_export_contract_failures, knowledge_report_export_token_failures, knowledge_report_export_token_state_failures
from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)

from .p4_c8_fixture import PROJECT_KEY, TOPIC, captured_item, new_registry


def _payload() -> KnowledgeReportStageInput:
    return KnowledgeReportStageInput(
        project_key=PROJECT_KEY,
        report_id="report:c8-3-native",
        topic=TOPIC,
        source_keys=("ki:robot-evidence",),
    )


def test_compiled_projection_preserves_report_stage_identity() -> None:
    native = knowledge_report_native_contribution
    assert not isinstance(native, Failure)
    assert native.projection.id == KNOWLEDGE_REPORT_CONTRIBUTION_ID
    assert native.projection.owner == KNOWLEDGE_REPORT_OWNER
    assert [obj.id for obj in native.projection.objects] == [
        "KnowledgeReportSourceReads.v2",
        "StagedKnowledgeReport.v2",
        KNOWLEDGE_REPORT_KIND,
        KNOWLEDGE_REPORT_PAYLOAD_CODEC_ID,
    ]
    assert native.projection.failures == (
        KNOWLEDGE_REPORT_STAGE_AUTHOR_SOURCE.failure_family,
        knowledge_report_export_contract_failures,
        knowledge_report_export_token_failures,
        knowledge_report_export_token_state_failures,
        successor_capability_contract_failures,
    )
    composition = compose_contributions((native.projection,))
    assert not isinstance(composition, Failure)
    assert composition.contributions == (native.projection,)
    assert all(contribution.factory is None for contribution in composition.contributions)


def test_contract_codec_atom_and_metadata_match_existing_stage() -> None:
    definition = knowledge_report_native_contribution.definition
    operation = definition.operations[0]
    bundle = build_knowledge_bundle()
    legacy_operation = bundle.codec_by_kind(KNOWLEDGE_REPORT_KIND).contract_ref
    assert operation.operation_contract == next(
        contract for contract in bundle.operations if contract.ref.kind == KNOWLEDGE_REPORT_KIND
    )
    assert legacy_operation == operation.operation_contract.ref

    legacy_payload = LegacyC8ReportStageInput(
        project_key=PROJECT_KEY,
        report_id="report:c8-3-native",
        topic=TOPIC,
        source_keys=("ki:robot-evidence",),
    )
    payload = _payload()
    assert dataclasses.asdict(payload) == dataclasses.asdict(legacy_payload)
    assert payload.payload_digest == legacy_payload.payload_digest
    assert operation.program_atom == type(operation.program_atom)(
        operation_id=KNOWLEDGE_REPORT_OPERATION_ID,
        operation_kind=KNOWLEDGE_REPORT_KIND,
        payload_codec_id=KNOWLEDGE_REPORT_PAYLOAD_CODEC_ID,
        input_type=operation.source.input_type,
        output_type=operation.source.output_type,
        return_contract_ref=operation.source.return_contract_ref,
        value_suffix="knowledge-report-stage",
    )
    assert dict(definition.profiles) == dict(bundle.profiles["knowledge.report.v2"])
    assert dict(definition.extra_program_metadata) == {
        "admission_interface_digest": knowledge_common.KNOWLEDGE_REPORT_ADMISSION_INTERFACE_DIGEST,
        "delivery_interface_digest": knowledge_common.KNOWLEDGE_REPORT_DELIVERY_INTERFACE_DIGEST,
    }

    legacy_codec = bundle.codec_by_kind(KNOWLEDGE_REPORT_KIND)
    native_codec = operation.payload_codec
    assert native_codec is not None
    assert native_codec.codec_id == legacy_codec.codec_id
    assert native_codec.payload_type_id == legacy_codec.payload_type_id
    assert native_codec.codec_digest == legacy_codec.codec_digest
    wire = native_codec.encode_payload(payload)
    assert wire == legacy_codec.encode_payload(legacy_payload)
    assert dataclasses.asdict(native_codec.decode_payload(wire)) == dataclasses.asdict(
        payload
    )

    program = build_knowledge_program(
        cell_id="knowledge.report.v2",
        payload=legacy_payload,
        catalog=build_knowledge_catalog(bundle),
        program_id="program:c8-3-native",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest="0" * 64,
    )
    assert dict(program.metadata)["operation_kinds"] == (KNOWLEDGE_REPORT_KIND,)
    assert dict(program.metadata)["canonical_owner"] == KNOWLEDGE_REPORT_OWNER
    assert dict(program.metadata)["admission_interface_digest"] == (
        knowledge_common.KNOWLEDGE_REPORT_ADMISSION_INTERFACE_DIGEST
    )
    assert dict(program.metadata)["delivery_interface_digest"] == (
        knowledge_common.KNOWLEDGE_REPORT_DELIVERY_INTERFACE_DIGEST
    )


def test_payload_digest_binds_body_and_rejects_drift() -> None:
    payload = _payload()
    expected = content_digest(
        {
            "project_key": PROJECT_KEY,
            "report_id": "report:c8-3-native",
            "topic": TOPIC,
            "source_keys": ("ki:robot-evidence",),
        }
    )
    assert payload.payload_digest == expected
    with pytest.raises(ValueError, match="does not match recomputed body digest"):
        KnowledgeReportStageInput(
            project_key=PROJECT_KEY,
            report_id="report:c8-3-native",
            topic=TOPIC,
            source_keys=("ki:other",),
            payload_digest=expected,
        )


def test_rollback_and_declared_cell_preserve_unwired_boundary() -> None:
    binding = knowledge_report_native_contribution.assemble(KnowledgeNativeAssemblyContext())
    assert not isinstance(binding, Failure)
    rollback = binding.assembly_rollback_binding()
    assert rollback.cell_id == "knowledge.report.v2"
    assert rollback.status == "PRESENT"
    assert rollback.binding_refs == (KNOWLEDGE_REPORT_ROLLBACK_REF,)
    declared = binding.declared_cell()
    assert declared.status == "UNWIRED_DECLARED"
    assert declared.handler_binding_digest is None
    assert declared.recovery_binding_ref == (
        "knowledge.report.admission.recovery.v2#verification-and-receipt-readback-only;"
        "no-repeat-export"
    )
    assert declared.operation_contract_refs == (
        "knowledge.report.stage.v2",
        "knowledge.report.admission.v2",
        "knowledge.report.delivery.v2",
    )


def test_binding_drift_and_invalid_source_fail_closed() -> None:
    definition = knowledge_report_native_contribution.definition
    binding = knowledge_report_native_contribution.assemble(KnowledgeNativeAssemblyContext())
    assert not isinstance(binding, Failure)
    accepted = validate_knowledge_native_binding(definition, binding)
    assert not isinstance(accepted, BindingRejected)

    drifted = dataclasses.replace(binding, cell_id="C8.3-drift")
    rejected = validate_knowledge_native_binding(definition, drifted)
    assert isinstance(rejected, BindingRejected)
    assert "$.binding.cell_id" in {issue.path for issue in rejected.issues}

    invalid_source = dataclasses.replace(
        KNOWLEDGE_REPORT_STAGE_AUTHOR_SOURCE,
        owner="",
    )
    invalid = compile_native_contribution(invalid_source, KNOWLEDGE_NATIVE_CONTRIBUTION_RULE)
    assert isinstance(invalid, Failure)
    assert invalid.code == "CONTRIBUTION_INVALID"
    assert {
        (issue["path"], issue["message"])
        for issue in invalid.context["issues"]
    } == {("$.definition.owner", "owner is empty")}


def _legacy_artifact_reads():
    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    return (read,)


def test_report_semantics_witnesses_readonly_stage_and_admission_intent() -> None:
    artifact = build_report_artifact(
        report_id="report:c8-3-witness",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=_legacy_artifact_reads(),
    )
    assert artifact.artifact_digest
    assert artifact.rows[0].status == "ready"
    assert artifact.source_identities

    admission = build_report_admission_intent(artifact)
    assert admission.admitted is False
    assert admission.reason == "interface_contract_only; admission is not called"

    source = knowledge_common.ProvenanceClosureEntry(
        identity=artifact.source_identities[0],
        digest="1" * 64,
        revision=1,
        incarnation="knowledge-generation-1",
        handle_id=artifact.rows[0].handle.handle_id,
        fields_digest="2" * 64,
    )
    citation = knowledge_common.CitationRef(
        citation_id="citation:1",
        source_identity=source.identity,
        source_digest=source.digest,
        position=1,
        source_revision=source.revision,
        source_incarnation=source.incarnation,
        handle_id=source.handle_id,
        fields_digest=source.fields_digest,
    )
    draft = knowledge_common.ResearchDraftArtifact(
        artifact_id="draft:c8-3-witness",
        project_key=PROJECT_KEY,
        markdown_bytes=b"# report witness",
        base_revision=1,
        base_incarnation="knowledge-generation-1",
        provenance_closure=(source,),
        citation_closure=knowledge_common.CitationClosure((citation,)),
        declared_legacy_metadata_loss=(),
        artifact_digest="",
    )
    draft = dataclasses.replace(
        draft,
        artifact_digest=knowledge_common.research_draft_artifact_digest(draft),
    )
    stage = build_report_stage(
        stage_id="stage:c8-3-witness",
        project_key=PROJECT_KEY,
        artifact=draft,
        citation_closure=draft.citation_closure,
    )
    verification = verify_report_stage(
        stage,
        citation_closure=draft.citation_closure,
        artifact=draft,
    )
    assert verification.state == "VERIFIED"
