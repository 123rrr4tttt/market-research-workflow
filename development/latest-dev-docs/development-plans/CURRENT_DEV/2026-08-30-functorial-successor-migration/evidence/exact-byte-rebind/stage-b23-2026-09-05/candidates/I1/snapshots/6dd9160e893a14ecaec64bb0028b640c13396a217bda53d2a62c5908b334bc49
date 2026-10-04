"""P4 C8 shared Program/Plan, HandlerBinding and lifecycle fixture tests."""

from __future__ import annotations

import dataclasses

import pytest

from app.successor_migration.legacy_c8_interpreter import (
    LegacyC8DemandReadDonor,
    LegacyC8DonorRegistry,
    LegacyC8ProgramInterpreter,
    LegacyC8WritingComposeDonor,
    LegacyC8WritingStageDonor,
)
from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.capabilities import c8_common as c8common
from app.successor_runtime.capabilities import c8_program as c8p
from app.successor_runtime.capabilities.c8_report import build_report_artifact
from app.successor_runtime.capabilities.c8_typed_knowledge import demand_read
from app.successor_runtime.capabilities.c8_writing import (
    compose_writing_handoff,
    project_writing_card,
    stage_writing_artifact,
)
from app.successor_runtime.capabilities.checksum import (
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import (
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
)
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    ObjectType,
)
from app.successor_runtime.runtime.assignments import (
    HandlerBindingKind,
    InterpreterBinding,
)
from app.successor_runtime.substrate.projections.c8_handler_bindings import (
    C8RecoveryReadbackHandler,
    build_c8_interpreter_binding,
    build_c8_recovery_binding,
    handler_binding_ref,
)

from .p4_c8_fixture import (
    PROJECT_KEY,
    captured_item,
    legacy_item,
    new_registry,
)

PROGRAM_ID = "program:p4-c8-test"
PROJECT_REGISTRY_REVISION = 1
PROJECT_SCOPE_DIGEST = content_digest(
    {"project": PROJECT_KEY, "incarnation": "scope-inc-c8-test"}
)


def _bundle() -> tuple:
    bundle = c8p.build_c8_bundle()
    catalog = c8p.build_c8_catalog(bundle)
    registry = c8p.build_c8_registry(bundle)
    return bundle, catalog, registry


def _payload(cell_id: str):
    if cell_id == "C8.1":
        return c8p.C8DemandReadInput(
            project_key=PROJECT_KEY,
            item_key="ki:robotics",
            fields=("canonical_statement", "evidence_refs"),
        )
    if cell_id == "C8.2":
        return c8p.C8WritingComposeInput(
            project_key=PROJECT_KEY,
            knowledge_item_key="ki:robotics",
            selection_hash="selection:robotics",
            selection_text="robotics investment",
            demand_fields=("canonical_statement", "evidence_refs"),
        )
    if cell_id == "C8.3":
        return c8p.C8ReportStageInput(
            project_key=PROJECT_KEY,
            report_id="report-1",
            topic="C8.knowledge-writing-report-graph",
            source_keys=("ki:robotics",),
        )
    return c8p.C8GraphProjectInput(
        project_key=PROJECT_KEY,
        graph_id="graph-1",
        node_keys=("ki:a", "ki:b"),
        node_types=("Topic",),
    )


def _compile(cell_id: str):
    bundle, catalog, registry = _bundle()
    program = c8p.build_c8_program(
        cell_id=cell_id,
        payload=_payload(cell_id),
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    return bundle, program, plan


def test_exact_operation_and_return_contracts() -> None:
    bundle, _, _ = _bundle()
    kinds = {operation.ref.kind for operation in bundle.operations}
    assert kinds == {
        c8p.C8_1_KIND,
        c8p.C8_2_COMPOSE_KIND,
        c8p.C8_2_STAGE_KIND,
        c8p.C8_3_KIND,
        c8p.C8_4_KIND,
    }
    by_kind = {operation.ref.kind: operation for operation in bundle.operations}
    assert by_kind[c8p.C8_1_KIND].return_contract_ref == (
        READ_CANONICAL_REF_RETURN_CONTRACT_REF
    )
    assert by_kind[c8p.C8_2_COMPOSE_KIND].return_contract_ref == (
        SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF
    )
    assert by_kind[c8p.C8_2_STAGE_KIND].return_contract_ref == (
        SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF
    )
    assert by_kind[c8p.C8_3_KIND].return_contract_ref == (
        RUNTIME_VALUE_RETURN_CONTRACT_REF
    )
    assert by_kind[c8p.C8_4_KIND].return_contract_ref == (
        READ_CANONICAL_REF_RETURN_CONTRACT_REF
    )
    expected_owner_by_kind = {
        c8p.C8_1_KIND: c8p.C8_1_OWNER,
        c8p.C8_2_COMPOSE_KIND: c8p.C8_2_OWNER,
        c8p.C8_2_STAGE_KIND: c8p.C8_2_OWNER,
        c8p.C8_3_KIND: c8p.C8_3_OWNER,
        c8p.C8_4_KIND: c8p.C8_4_OWNER,
    }
    assert all(
        operation.owner_capability_id == expected_owner_by_kind[operation.ref.kind]
        for operation in bundle.operations
    )


def test_ordered_shared_program_and_plan_are_deterministic() -> None:
    _, program, plan = _compile("C8.2")
    assert program.root.node_kind == "then"
    assert len(plan.ordered_steps) == 2
    assert plan.program_id == PROGRAM_ID
    assert plan.program_digest == program.program_digest
    _, second_program, second_plan = _compile("C8.2")
    assert second_program.canonical_json() == program.canonical_json()
    assert second_plan.plan_digest == plan.plan_digest

    for cell_id in ("C8.1", "C8.3", "C8.4"):
        _, program_1, plan_1 = _compile(cell_id)
        assert program_1.root.node_kind == "atom"
        assert len(plan_1.ordered_steps) == 1


def test_exact_handler_binding() -> None:
    bundle, program, _ = _compile("C8.1")
    contract = next(
        operation
        for operation in bundle.operations
        if operation.ref.kind == c8p.C8_1_KIND
    )
    binding = build_c8_interpreter_binding(
        c8p.handler_binding_payload(
            operation_contract_digest=contract.ref.contract_digest,
            interpreter_profile_digest=bundle.profiles["C8.1"][
                "interpreter"
            ].profile_digest,
            deployment_catalog_digest=content_digest({"catalog": "deployment.c8.v1"}),
            project_scope_digest=PROJECT_SCOPE_DIGEST,
            authority_requirement_digest=content_digest({"authority": False}),
        )
    )
    assert isinstance(binding, InterpreterBinding)
    assert binding.binding_kind == HandlerBindingKind.INTERPRETER
    assert binding.operation_contract_digest == contract.ref.contract_digest
    assert handler_binding_ref(binding) == (
        f"handler-binding:sha256:{binding.binding_digest}"
    )
    assert program.program_digest


def test_legacy_and_successor_share_same_ast() -> None:
    legacy_bundle, legacy_program, legacy_plan = _compile("C8.1")
    successor_bundle, successor_program, successor_plan = _compile("C8.1")
    assert legacy_program.canonical_json() == successor_program.canonical_json()
    assert legacy_plan.plan_digest == successor_plan.plan_digest
    assert legacy_bundle is not successor_bundle
    payload = _payload("C8.1")
    donors = LegacyC8DonorRegistry()
    legacy_catalog = c8p.build_c8_catalog(legacy_bundle)
    donors.register(
        legacy_catalog.lookup(c8p.C8_1_KIND).contract_digest,
        LegacyC8DemandReadDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    legacy_trace = LegacyC8ProgramInterpreter().consume(
        legacy_program,
        legacy_plan,
        donors=donors,
        seed_inputs={
            legacy_plan.ordered_steps[0].step_id: (
                payload,
                payload.payload_digest,
            )
        },
    )
    successor_trace = [step.operation_id for step in successor_plan.ordered_steps]
    assert legacy_trace["ordered_step_trace"] == successor_trace
    assert legacy_trace["consumed_program_digest"] == legacy_program.program_digest
    assert legacy_trace["consumed_plan_digest"] == legacy_plan.plan_digest


def test_typed_lifecycle_algebra_is_production_contract() -> None:
    recovery = c8common.recover_unknown_outcome(
        cell_id="C8.1",
        binding_digest="0" * 64,
        attempt_digest="attempt:1",
        readback_profile_ref="c8.typed_knowledge.readback.v1",
        outcome_digest="0" * 64,
    )
    rollback = c8common.rollback_transition(
        cell_id="C8.2",
        retained_digests=("artifact-1", "report-1"),
    )
    failure = c8common.C8FailureResult(
        cell_id="C8.1",
        failure_kind="DEMAND_READ_UNAVAILABLE",
        reason="canonical fact unavailable",
    )
    assert isinstance(recovery, c8common.C8RecoveryResult)
    assert isinstance(rollback, c8common.C8RollbackResult)
    assert isinstance(failure, c8common.C8FailureResult)
    assert recovery.readback_required is True
    assert recovery.new_attempt_allowed is False
    assert rollback.admission_reverted is False
    for result in (recovery, rollback, failure):
        assert result.provider_calls == 0
        assert result.store_writes == 0
        assert result.export_calls == 0


def test_payload_digest_is_recomputed_and_stale_digest_rejected() -> None:
    payload = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:robotics",
        fields=("canonical_statement",),
    )
    assert payload.payload_digest == c8p.payload_body_digest(payload)
    with pytest.raises(ValueError, match="recomputed"):
        c8p.C8DemandReadInput(
            project_key=PROJECT_KEY,
            item_key="ki:other",
            fields=("canonical_statement",),
            payload_digest=payload.payload_digest,
        )


def test_per_cell_profiles_are_typed_and_distinct() -> None:
    bundle, _, _ = _bundle()
    expected_owners = {
        "C8.1": c8p.C8_1_OWNER,
        "C8.2": c8p.C8_2_OWNER,
        "C8.3": c8p.C8_3_OWNER,
        "C8.4": c8p.C8_4_OWNER,
    }
    expected_classes = {
        "C8.1": "EFFECTFUL",
        "C8.2": "PURE_TRANSFORM",
        "C8.3": "ADMISSION",
        "C8.4": "PROJECTION",
    }
    for cell_id, owner in expected_owners.items():
        profiles = bundle.profiles[cell_id]
        assert profiles["authority"].canonical_owner == owner
        assert profiles["effect"].execution_class == expected_classes[cell_id]
        assert profiles["failure"].readback_profile_ref
        assert profiles["failure"].typed_failures
    assert len(set(expected_owners.values())) == 4
    assert len(set(expected_classes.values())) == 4


def test_execution_plan_step_handler_binding_closure() -> None:
    bundle, _, plan = _compile("C8.2")
    entries = c8p.handler_binding_closure_payloads(
        plan,
        interpreter_profile_digest=bundle.profiles["C8.2"][
            "interpreter"
        ].profile_digest,
        deployment_catalog_digest=content_digest({"catalog": "deployment.c8.v1"}),
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        authority_requirement_digest=content_digest({"authority": False}),
    )
    assert len(entries) == 2
    assert [entry["operation_kind"] for entry in entries] == [
        c8p.C8_2_COMPOSE_KIND,
        c8p.C8_2_STAGE_KIND,
    ]
    bindings = [build_c8_interpreter_binding(entry["payload"]) for entry in entries]
    assert len({binding.binding_digest for binding in bindings}) == 2
    assert all(
        binding.binding_kind == HandlerBindingKind.INTERPRETER for binding in bindings
    )
    assert entries[0]["step_id"] != entries[1]["step_id"]


def test_unknown_path_recovery_binding_and_production_rollback() -> None:
    bundle, _, _ = _bundle()
    recovery = build_c8_recovery_binding(
        interpreter_profile_digest=bundle.profiles["C8.3"][
            "interpreter"
        ].profile_digest,
        authoritative_readback_profile_ref="c8.report.admission.readback.v1",
    )
    assert recovery.binding_kind == HandlerBindingKind.RECOVERY
    assert recovery.authoritative_readback_profile_ref == (
        "c8.report.admission.readback.v1"
    )

    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    artifact = stage_writing_artifact(
        project_writing_card(
            compose_writing_handoff(
                read,
                selection_hash="selection:robotics",
                selection_text="robotics investment",
            )
        )
    )
    report = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic="C8.knowledge-writing-report-graph",
        source_reads=(read,),
    )
    recovery_result = C8RecoveryReadbackHandler().handle_unknown(
        recovery,
        cell_id="C8.3",
        attempt_digest=report.artifact_digest,
    )
    rollback = c8common.rollback_transition(
        cell_id="C8.2",
        retained_digests=(artifact.artifact_id, report.artifact_digest),
    )
    assert rollback.admission_reverted is False
    assert isinstance(recovery_result, c8common.C8RecoveryResult)
    assert recovery_result.binding_digest == recovery.binding_digest
    assert recovery_result.attempt_digest == report.artifact_digest
    assert recovery_result.readback_profile_ref == ("c8.report.admission.readback.v1")
    assert recovery_result.outcome_digest
    assert recovery_result.new_attempt_allowed is False
    assert artifact.artifact_id
    assert report.artifact_digest
    assert rollback.provider_calls == 0
    assert rollback.store_writes == 0
    with pytest.raises(ValueError, match="override"):
        C8RecoveryReadbackHandler().handle_unknown(
            recovery,
            cell_id="C8.3",
            attempt_digest=report.artifact_digest,
            readback_profile_ref="attacker.readback.profile.v1",
        )
    with pytest.raises(c8common.C8ProjectionError, match="non-empty"):
        c8common.rollback_transition(cell_id="C8.2", retained_digests=())
    with pytest.raises(c8common.C8ProjectionError, match="authority"):
        c8common.rollback_transition(
            cell_id="C8.2",
            retained_digests=(artifact.artifact_id,),
            authority_reversed=True,
        )


def test_legacy_interpreter_dispatches_real_donors_by_exact_digest() -> None:
    bundle, catalog, _ = _bundle()
    payload = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:robotics",
        fields=("canonical_statement", "evidence_refs"),
    )
    program = c8p.build_c8_program(
        cell_id="C8.1",
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    donors = LegacyC8DonorRegistry()
    donors.register(
        catalog.lookup(c8p.C8_1_KIND).contract_digest,
        LegacyC8DemandReadDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    trace = LegacyC8ProgramInterpreter().consume(
        program,
        plan,
        donors=donors,
        seed_inputs={plan.ordered_steps[0].step_id: (payload, payload.payload_digest)},
    )
    assert len(trace["step_executions"]) == 1
    execution = trace["step_executions"][0]
    assert execution["failure"] is None
    assert execution["output"]["knowledge_item_key"] == "ki:robotics"
    assert execution["output"]["canonical_statement"] == "机器人产品市场证据"

    successor = demand_read(
        (captured_item(),),
        item_key="ki:robotics",
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    assert (
        execution["output"]["canonical_statement"]
        == (successor.fields["canonical_statement"])
    )
    assert trace["ordered_step_trace"] == [
        step.operation_id for step in plan.ordered_steps
    ]
    assert trace["consumed_program_digest"] == program.program_digest
    assert trace["consumed_plan_digest"] == plan.plan_digest
    assert donors.resolve("0" * 64) is None


def test_interpreter_rejects_mixed_program_and_plan_pair() -> None:
    bundle, catalog, _ = _bundle()
    payload_a = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:robotics",
        fields=("canonical_statement",),
    )
    program_a = c8p.build_c8_program(
        cell_id="C8.1",
        payload=payload_a,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    payload_b = c8p.C8GraphProjectInput(
        project_key=PROJECT_KEY,
        graph_id="graph-1",
        node_keys=("ki:a",),
        node_types=("Topic",),
    )
    program_b = c8p.build_c8_program(
        cell_id="C8.4",
        payload=payload_b,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan_a = c8p.compile_c8_program(
        program_a,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    donors = LegacyC8DonorRegistry()
    donors.register(
        catalog.lookup(c8p.C8_1_KIND).contract_digest,
        LegacyC8DemandReadDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    with pytest.raises(ValueError, match="mixed Program/Plan"):
        LegacyC8ProgramInterpreter().consume(
            program_b,
            plan_a,
            donors=donors,
            seed_inputs={
                plan_a.ordered_steps[0].step_id: (
                    payload_a,
                    payload_a.payload_digest,
                )
            },
        )


def test_c8_2_dataflow_feeds_compose_output_into_stage() -> None:
    bundle, catalog, _ = _bundle()
    payload = c8p.C8WritingComposeInput(
        project_key=PROJECT_KEY,
        knowledge_item_key="ki:robotics",
        selection_hash="selection:robotics",
        selection_text="robotics investment",
        demand_fields=("canonical_statement", "evidence_refs"),
    )
    program = c8p.build_c8_program(
        cell_id="C8.2",
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    donors = LegacyC8DonorRegistry()
    donors.register(
        catalog.lookup(c8p.C8_2_COMPOSE_KIND).contract_digest,
        LegacyC8WritingComposeDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    donors.register(
        catalog.lookup(c8p.C8_2_STAGE_KIND).contract_digest,
        LegacyC8WritingStageDonor(normalized_query="robotics investment").run,
    )
    trace = LegacyC8ProgramInterpreter().consume(
        program,
        plan,
        donors=donors,
        seed_inputs={plan.ordered_steps[0].step_id: (payload, payload.payload_digest)},
    )
    executions = trace["step_executions"]
    assert len(executions) == 2
    compose_output = executions[0]["output"]
    stage_execution = executions[1]
    assert stage_execution["input_digest"] == content_digest(compose_output)
    assert stage_execution["output"]["source_type"] == "resource"
    assert stage_execution["output"]["publisher"] == "typed_knowledge"

    read = demand_read(
        (captured_item(),),
        item_key="ki:robotics",
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    successor_handoff = compose_writing_handoff(
        read,
        selection_hash="selection:robotics",
        selection_text="robotics investment",
    )
    assert compose_output["canonical_statement"] == (
        successor_handoff.canonical_statement
    )
    successor_card = project_writing_card(successor_handoff)
    assert stage_execution["output"]["evidence"] == (successor_card.canonical_statement)


def test_interpreter_rejects_tampered_program_and_plan() -> None:
    bundle, catalog, _ = _bundle()
    payload = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:robotics",
        fields=("canonical_statement",),
    )
    program = c8p.build_c8_program(
        cell_id="C8.1",
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    donors = LegacyC8DonorRegistry()
    donors.register(
        catalog.lookup(c8p.C8_1_KIND).contract_digest,
        LegacyC8DemandReadDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    seed_inputs = {plan.ordered_steps[0].step_id: (payload, payload.payload_digest)}
    tampered_program = dataclasses.replace(
        program,
        semantic_identity="tampered-identity",
    )
    with pytest.raises(ValueError, match="tampered ProgramSpec"):
        LegacyC8ProgramInterpreter().consume(
            tampered_program,
            plan,
            donors=donors,
            seed_inputs=seed_inputs,
        )
    tampered_plan = dataclasses.replace(plan, ordered_steps=())
    with pytest.raises(ValueError, match="tampered ExecutionPlan"):
        LegacyC8ProgramInterpreter().consume(
            program,
            tampered_plan,
            donors=donors,
            seed_inputs=seed_inputs,
        )


def test_interpreter_recomputes_seed_input_digest_and_rejects_mismatch() -> None:
    bundle, catalog, _ = _bundle()
    payload = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:robotics",
        fields=("canonical_statement",),
    )
    program = c8p.build_c8_program(
        cell_id="C8.1",
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    donors = LegacyC8DonorRegistry()
    donors.register(
        catalog.lookup(c8p.C8_1_KIND).contract_digest,
        LegacyC8DemandReadDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    with pytest.raises(ValueError, match="seed input digest"):
        LegacyC8ProgramInterpreter().consume(
            program,
            plan,
            donors=donors,
            seed_inputs={plan.ordered_steps[0].step_id: (payload, "0" * 64)},
        )


def _bridge_candidate() -> c8common.C8ResearchArtifactCandidate:
    return c8common.C8ResearchArtifactCandidate(
        candidate_id="artifact:001",
        project_key=PROJECT_KEY,
        canonical_metadata_bytes=b"{}",
        canonical_metadata_digest="0" * 64,
        markdown_ref="project-value:markdown:001",
        markdown_digest="0" * 64,
        source_draft_digest="0" * 64,
        verification_digest="0" * 64,
        provenance_digest="0" * 64,
        claim_closure=(),
        evidence_relation_closure=(),
        citation_closure=("ev:1",),
        source_base_revision=1,
        source_base_incarnation="value-1",
    )


def test_c8_report_bridge_program_orders_stage_verify_admission() -> None:
    bridge = c8p.build_c8_bridge_bundle()
    catalog = c8p.build_c8_catalog(bridge)
    registry = c8p.build_c8_registry(bridge)
    stage_payload = c8p.C8ReportStageInput(
        project_key=PROJECT_KEY,
        report_id="report-1",
        topic="C8.knowledge-writing-report-graph",
        source_keys=("ki:robotics",),
    )
    program = c8p.build_c8_report_bridge_program(
        stage_payload=stage_payload,
        catalog=catalog,
        program_id="program:p4-c8-bridge",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_report_bridge_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    assert len(plan.ordered_steps) == 4
    kinds = [step.operation_contract_ref.kind for step in plan.ordered_steps]
    assert kinds[:3] == [
        c8p.C8_3_KIND,
        c8p.C8_VERIFY_KIND,
        c8p.C8_ADMISSION_KIND,
    ]
    barrier_steps = [
        step for step in plan.ordered_steps if step.step_kind == "ADMISSION"
    ]
    assert barrier_steps
    assert barrier_steps[0].return_contract.admission_required is True
    second = c8p.build_c8_report_bridge_program(
        stage_payload=stage_payload,
        catalog=catalog,
        program_id="program:p4-c8-bridge",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    assert second.program_digest == program.program_digest
    other_program = c8p.build_c8_report_bridge_program(
        stage_payload=c8p.C8ReportStageInput(
            project_key=PROJECT_KEY,
            report_id="report-2",
            topic="C8.knowledge-writing-report-graph",
            source_keys=("ki:robotics",),
        ),
        catalog=catalog,
        program_id="program:p4-c8-bridge",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    assert other_program.program_digest != program.program_digest


def _delivery_operation() -> object:
    return build_first_specimen_bundle()


def _delivery_contract_and_codec() -> tuple:
    bundle = build_first_specimen_bundle()
    operation = next(
        operation
        for operation in bundle.operations
        if operation.ref.kind == c8p.DELIVERY_INTERNAL_EXPORT_KIND
    )
    codec = bundle.codec_by_kind(operation.ref.kind)
    return operation, codec


def _seed_ref(
    *,
    type_id: str,
    codec_id: str,
    suffix: str,
) -> ValueRef:
    full_bytes = f"seed-bytes:{suffix}".encode()
    full_digest = sha256_hex(full_bytes)
    return ValueRef(
        value_id=f"seed:{suffix}",
        project_key=PROJECT_KEY,
        object_type=ObjectType(type_id),
        codec_id=codec_id,
        content_digest=full_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:seed:{suffix}",
        byte_size=len(full_bytes),
        provenance_digest=content_digest(
            {
                "seed": suffix,
                "artifact_content_digest": full_digest,
            }
        ),
    )


def _delivery_refs(delivery_codec: object) -> tuple[ValueRef, ValueRef, ValueRef]:
    return (
        _seed_ref(
            type_id="InternalExportInput.v1",
            codec_id=delivery_codec.codec_id,
            suffix="delivery-payload",
        ),
        _seed_ref(
            type_id="ResearchArtifact.v1",
            codec_id=CANONICAL_CODEC_ID,
            suffix="artifact-input",
        ),
        _seed_ref(
            type_id="DeliveryIntent.v1",
            codec_id=CANONICAL_CODEC_ID,
            suffix="intent-input",
        ),
    )


def test_c8_delivery_bridge_program_orders_and_barrier() -> None:
    delivery_operation, delivery_codec = _delivery_contract_and_codec()
    assert (
        c8p.validate_delivery_operation_contract(delivery_operation)
        is delivery_operation
    )
    assert (
        c8p.validate_delivery_payload_codec(delivery_codec, delivery_operation)
        is delivery_codec
    )
    assert delivery_codec.payload_type_id == "InternalExportInput.v1"
    delivery_payload_ref, artifact_input_ref, intent_input_ref = _delivery_refs(
        delivery_codec
    )
    assert artifact_input_ref.object_type.type_id == "ResearchArtifact.v1"
    assert intent_input_ref.object_type.type_id == "DeliveryIntent.v1"
    bridge = c8p.build_c8_delivery_bridge_bundle(
        delivery_operation,
        delivery_codec,
    )
    catalog = c8p.build_c8_catalog(bridge)
    registry = c8p.build_c8_registry(bridge)
    stage_payload = c8p.C8ReportStageInput(
        project_key=PROJECT_KEY,
        report_id="report-1",
        topic="C8.knowledge-writing-report-graph",
        source_keys=("ki:robotics",),
    )
    program = c8p.build_c8_delivery_bridge_program(
        delivery_operation=delivery_operation,
        delivery_codec=delivery_codec,
        delivery_payload_ref=delivery_payload_ref,
        artifact_input_ref=artifact_input_ref,
        intent_input_ref=intent_input_ref,
        stage_payload=stage_payload,
        catalog=catalog,
        program_id="program:p4-c8-delivery-bridge",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_delivery_bridge_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    kinds = [step.operation_contract_ref.kind for step in plan.ordered_steps]
    assert kinds[:3] == [
        c8p.C8_3_KIND,
        c8p.C8_VERIFY_KIND,
        c8p.C8_ADMISSION_KIND,
    ]
    assert kinds.count(c8p.C8_ADMISSION_KIND) == 2
    assert kinds[-3:] == [
        c8p.C8_DELIVERY_INTENT_PREPARE_KIND,
        c8p.DELIVERY_INTERNAL_EXPORT_KIND,
        c8p.DELIVERY_INTERNAL_EXPORT_KIND,
    ]
    barrier_steps = [
        step for step in plan.ordered_steps if step.step_kind == "ADMISSION"
    ]
    assert barrier_steps
    assert barrier_steps[0].return_contract.admission_required is True
    second = c8p.build_c8_delivery_bridge_program(
        delivery_operation=delivery_operation,
        delivery_codec=delivery_codec,
        delivery_payload_ref=delivery_payload_ref,
        artifact_input_ref=artifact_input_ref,
        intent_input_ref=intent_input_ref,
        stage_payload=stage_payload,
        catalog=catalog,
        program_id="program:p4-c8-delivery-bridge",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    assert second.program_digest == program.program_digest


def test_c8_delivery_bridge_rejects_wrong_contract_and_digest_drift() -> None:
    bundle = build_first_specimen_bundle()
    compose_operation = next(
        operation
        for operation in bundle.operations
        if operation.ref.kind == "artifact.compose_markdown.v1"
    )
    with pytest.raises(c8common.C8ProjectionError, match="kind"):
        c8p.validate_delivery_operation_contract(compose_operation)
    delivery_operation, delivery_codec = _delivery_contract_and_codec()
    with pytest.raises(ValueError, match="digest"):
        dataclasses.replace(
            delivery_operation,
            ref=dataclasses.replace(
                delivery_operation.ref,
                contract_digest="1" * 64,
            ),
        )
    payload_ref, artifact_ref, intent_ref = _delivery_refs(delivery_codec)
    wrong_codec_ref = _seed_ref(
        type_id="InternalExportInput.v1",
        codec_id=CANONICAL_CODEC_ID,
        suffix="wrong-codec",
    )
    with pytest.raises(c8common.C8ProjectionError, match="codec"):
        c8p.build_c8_delivery_bridge_program(
            delivery_operation=delivery_operation,
            delivery_codec=delivery_codec,
            delivery_payload_ref=wrong_codec_ref,
            artifact_input_ref=artifact_ref,
            intent_input_ref=intent_ref,
            stage_payload=c8p.C8ReportStageInput(
                project_key=PROJECT_KEY,
                report_id="report-1",
                topic="t",
                source_keys=("k",),
            ),
            catalog=c8p.build_c8_catalog(
                c8p.build_c8_delivery_bridge_bundle(
                    delivery_operation,
                    delivery_codec,
                )
            ),
            program_id="program:p4-c8-delivery-bridge",
            project_key=PROJECT_KEY,
            project_registry_revision=1,
            project_scope_digest=PROJECT_SCOPE_DIGEST,
        )
    shared = dataclasses.replace(payload_ref, storage_ref=artifact_ref.storage_ref)
    with pytest.raises(c8common.C8ProjectionError, match="storage_ref"):
        c8p.build_c8_delivery_bridge_program(
            delivery_operation=delivery_operation,
            delivery_codec=delivery_codec,
            delivery_payload_ref=shared,
            artifact_input_ref=artifact_ref,
            intent_input_ref=intent_ref,
            stage_payload=c8p.C8ReportStageInput(
                project_key=PROJECT_KEY,
                report_id="report-1",
                topic="t",
                source_keys=("k",),
            ),
            catalog=c8p.build_c8_catalog(
                c8p.build_c8_delivery_bridge_bundle(
                    delivery_operation,
                    delivery_codec,
                )
            ),
            program_id="program:p4-c8-delivery-bridge",
            project_key=PROJECT_KEY,
            project_registry_revision=1,
            project_scope_digest=PROJECT_SCOPE_DIGEST,
        )


def test_payload_value_ref_exact_full_byte_identity() -> None:
    payload = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:robotics",
        fields=("canonical_statement",),
    )
    ref = c8p.payload_value_ref(
        payload,
        program_id="program:p4-c8-byte",
        project_key=PROJECT_KEY,
        codec_id=c8p.C8_1_PAYLOAD_CODEC_ID,
        object_type=c8p.C8_1_INPUT_TYPE,
        value_suffix="c8-1",
    )
    full_bytes = c8p.canonical_json(dataclasses.asdict(payload)).encode("utf-8")
    assert ref.byte_size == len(full_bytes)
    assert ref.content_digest == sha256_hex(full_bytes)
    assert ref.content_digest != payload.payload_digest
    assert payload.payload_digest == c8p.payload_body_digest(payload)
    expected_provenance = content_digest(
        {
            "schema": "mrw.successor.c8.c8-1.payload-provenance.v1",
            "program_id": "program:p4-c8-byte",
            "project_key": PROJECT_KEY,
            "semantic_payload_digest": payload.payload_digest,
            "artifact_content_digest": ref.content_digest,
        }
    )
    assert ref.provenance_digest == expected_provenance
    mutated = c8p.C8DemandReadInput(
        project_key=PROJECT_KEY,
        item_key="ki:other",
        fields=("canonical_statement",),
    )
    mutated_ref = c8p.payload_value_ref(
        mutated,
        program_id="program:p4-c8-byte",
        project_key=PROJECT_KEY,
        codec_id=c8p.C8_1_PAYLOAD_CODEC_ID,
        object_type=c8p.C8_1_INPUT_TYPE,
        value_suffix="c8-1",
    )
    assert mutated_ref.content_digest != ref.content_digest
    assert mutated_ref.provenance_digest != ref.provenance_digest
