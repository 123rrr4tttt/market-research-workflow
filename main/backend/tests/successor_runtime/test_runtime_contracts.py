from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.language.plan import (
    CompiledControlNode,
    CompiledDecisionBranch,
)
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.admission import (
    CommitIntent,
    VerificationBinding,
    require_admission_binding,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledAdmissionBinding,
    CompiledStepRole,
    CompilerBinding,
    HandlerBindingKind,
    InterpreterBinding,
    MaterializerBinding,
    ProjectorBinding,
    QualificationBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    CanonicalDocumentRead,
    ControlPlaneScope,
    DocumentCanonicalReadPort,
    ProjectScopeRef,
    RuntimeScope,
    WorkItemPort,
)
from app.successor_runtime.runtime.reducer import (
    BranchDecisionUnresolved,
    CompletionPolicy,
    RunSnapshot,
    StepSnapshot,
    reduce_branch_decision,
    reduce_run_completion,
    reduce_run_event,
    reduce_step,
)
from app.successor_runtime.runtime.transitions import (
    RUN_TRANSITIONS,
    STEP_TRANSITIONS,
    BranchEvent,
    EffectDisposition,
    IllegalTransition,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
)
from app.successor_runtime.runtime.work_items import (
    WORK_ITEM_KIND_INDEX,
    WorkItemRootUnion,
    WorkItemState,
    WorkItemWaitReason,
)

_WORK_ITEM_ROOT_ADAPTER = TypeAdapter(WorkItemRootUnion)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def test_control_plane_scope_permission_is_runtime_checked_and_fail_closed() -> None:
    scope = ControlPlaneScope(
        system_actor_id="runtime-node-1",
        permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
        authority_epoch=7,
    )

    scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)

    with pytest.raises(ValueError, match="allowed control-plane permission"):
        ControlPlaneScope(
            system_actor_id="runtime-node-1",
            permission="not-authorized",  # type: ignore[arg-type]
            authority_epoch=7,
        )

    # Frozen dataclasses are not a security boundary by themselves.  The
    # interpreter-side guard must still reject a corrupted or deserialized
    # scope before any cross-project effect occurs.
    object.__setattr__(scope, "permission", "not-authorized")
    with pytest.raises(PermissionError, match="runtime.cross_project_claim"):
        scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)


def test_work_item_port_heartbeat_exposes_expected_revision_cas() -> None:
    parameters = inspect.signature(WorkItemPort.heartbeat).parameters
    assert tuple(parameters) == (
        "self",
        "control_scope",
        "work_item_id",
        "lease_token",
        "expected_revision",
        "new_expiry",
    )


def _test_discriminator(value: object) -> object:
    assert isinstance(value, dict)
    return value.get("matches", value.get("kind"))


def _interpret_assignment(**changes: object) -> RuntimeAssignment:
    operation_contract_digest = _digest("operation-contract")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation_contract_digest,
        interpreter_profile_digest=_digest("interpreter-profile"),
        deployment_catalog_digest=_digest("deployment-catalog"),
        runtime_protocol_version="1",
        project_scope_digest=_digest("project-scope"),
        resource_policy_epoch=3,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return_contract_binding = ReturnContractBinding.from_contract(
        "mrw.return.runtime-value.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=False,
            wait_modes=("WAIT",),
            cancel_modes=("CANCELED",),
        ),
    )
    values: dict[str, object] = {
        "runtime_protocol_version": "1",
        "work_item_id": "work-1",
        "assignment_kind": AssignmentKind.INTERPRET,
        "project_key": "project-1",
        "run_id": "run-1",
        "step_id": "step-1",
        "step_role": CompiledStepRole.EFFECT,
        "capability_id": "cap-1",
        "operation_contract_ref": OperationContractRef(
            kind="fixture.operation.v1",
            contract_version="1.0.0",
            contract_digest=operation_contract_digest,
        ),
        "operation_contract_digest": operation_contract_digest,
        "return_contract_binding": return_contract_binding,
        "handler_binding_kind": HandlerBindingKind.INTERPRETER,
        "handler_binding_ref": f"handler-binding:sha256:{binding.binding_digest}",
        "handler_binding_digest": binding.binding_digest,
        "handler_binding": binding,
        "program_digest": _digest("program"),
        "plan_digest": _digest("plan"),
        "deployment_catalog_digest": _digest("deployment-catalog"),
        "execution_epoch": 1,
        "incarnation": "inc-1",
        "input_refs": ("value:1",),
        "input_closure_digest": _digest("input-closure"),
        "queue_eligibility_digest": _digest("queue-eligibility"),
        "resource_policy_epoch": 3,
        "claim_authority_epoch": 4,
        "claim_policy_digest": _digest("claim-policy"),
        "expected_step_revision": 0,
        "trace_id": "trace-1",
    }
    values.update(changes)
    return RuntimeAssignment(**values)


def test_assignment_kind_requires_exact_handler_binding() -> None:
    with pytest.raises(ValidationError, match="requires exact QUALIFICATION"):
        _interpret_assignment(assignment_kind=AssignmentKind.QUALIFY)


def test_assignment_state_dependent_fields_fail_closed() -> None:
    with pytest.raises(ValidationError, match="expected_step_revision"):
        _interpret_assignment(expected_step_revision=None)


def test_verify_admit_closes_operation_role_and_admission_return_contract() -> None:
    admission_contract = ReturnContractBinding.from_contract(
        "mrw.return.admission.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=True,
        ),
    )
    compiled_admission = CompiledAdmissionBinding.from_content(
        plan_digest=_digest("plan"),
        effect_step_id="effect-1",
        admission_step_id="admission-1",
        operation_contract_digest=_digest("operation-contract"),
        return_contract_ref=admission_contract.return_contract_ref,
        return_contract_digest=admission_contract.binding_digest,
        source_map_digest=_digest("source-map"),
        control_digest=_digest("control"),
    )
    assignment = _interpret_assignment(
        assignment_kind=AssignmentKind.VERIFY_ADMIT,
        step_id="admission-1",
        step_role=CompiledStepRole.ADMISSION,
        return_contract_binding=admission_contract,
        compiled_admission_binding=compiled_admission,
    )
    assert assignment.operation_contract_ref is not None
    assert assignment.return_contract_binding == admission_contract

    with pytest.raises(ValidationError, match="operation_contract_ref"):
        _interpret_assignment(
            assignment_kind=AssignmentKind.VERIFY_ADMIT,
            step_id="admission-1",
            step_role=CompiledStepRole.ADMISSION,
            return_contract_binding=admission_contract,
            compiled_admission_binding=compiled_admission,
            operation_contract_ref=None,
        )
    with pytest.raises(ValidationError, match="compiled step role ADMISSION"):
        _interpret_assignment(
            assignment_kind=AssignmentKind.VERIFY_ADMIT,
            step_id="admission-1",
            return_contract_binding=admission_contract,
            compiled_admission_binding=compiled_admission,
        )
    with pytest.raises(ValidationError, match="admission_required"):
        _interpret_assignment(
            assignment_kind=AssignmentKind.VERIFY_ADMIT,
            step_id="admission-1",
            step_role=CompiledStepRole.ADMISSION,
            compiled_admission_binding=compiled_admission,
        )

    with pytest.raises(
        ValidationError, match="compiled admission operation contract drift"
    ):
        substituted = CompiledAdmissionBinding.from_content(
            plan_digest=_digest("plan"),
            effect_step_id="effect-1",
            admission_step_id="admission-1",
            operation_contract_digest=_digest("substituted-operation-contract"),
            return_contract_ref=admission_contract.return_contract_ref,
            return_contract_digest=admission_contract.binding_digest,
            source_map_digest=_digest("source-map"),
            control_digest=_digest("control"),
        )
        _interpret_assignment(
            assignment_kind=AssignmentKind.VERIFY_ADMIT,
            step_id="admission-1",
            step_role=CompiledStepRole.ADMISSION,
            return_contract_binding=admission_contract,
            compiled_admission_binding=substituted,
        )

    replacement_return = ReturnContractBinding.from_contract(
        "mrw.return.replacement.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=True,
        ),
    )
    with pytest.raises(
        ValidationError, match="compiled admission return contract ref drift"
    ):
        _interpret_assignment(
            assignment_kind=AssignmentKind.VERIFY_ADMIT,
            step_id="admission-1",
            step_role=CompiledStepRole.ADMISSION,
            return_contract_binding=replacement_return,
            compiled_admission_binding=compiled_admission,
        )


def test_handler_binding_ref_is_an_exact_content_addressed_locator() -> None:
    with pytest.raises(ValidationError, match="canonical locator"):
        _interpret_assignment(handler_binding_ref="profile-1")


def test_claim_and_attempt_bind_assignment_and_handler_realization() -> None:
    assignment = _interpret_assignment()
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease-1",
        lease_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        node_id="node-1",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=_digest("interpreter-profile"),
        authority_digest=_digest("authority"),
    )
    claim.validate_against(assignment)
    changed = _interpret_assignment(execution_epoch=2)
    with pytest.raises(ValueError, match="assignment content drift"):
        claim.validate_against(changed)


@pytest.mark.parametrize(
    ("binding", "mutated_field"),
    [
        (
            CompilerBinding.from_content(
                compiler_id="compiler",
                compiler_version="1",
                compiler_digest=_digest("compiler"),
                operation_catalog_digest=_digest("operation-catalog"),
                domain_contract_snapshot_digest=_digest("domain-snapshot"),
            ),
            "compiler_version",
        ),
        (
            QualificationBinding.from_content(
                authority_reader_id="authority-reader",
                authority_reader_version="1",
                authority_reader_digest=_digest("authority-reader"),
                deployment_catalog_digest=_digest("deployment-catalog"),
                resource_policy_epoch=3,
            ),
            "authority_reader_version",
        ),
        (
            InterpreterBinding.from_content(
                operation_contract_digest=_digest("operation-contract"),
                interpreter_profile_digest=_digest("interpreter-profile"),
                deployment_catalog_digest=_digest("deployment-catalog"),
                runtime_protocol_version="1",
                project_scope_digest=_digest("project-scope"),
                resource_policy_epoch=3,
                authority_requirement_digest=_digest("authority-requirement"),
            ),
            "runtime_protocol_version",
        ),
        (
            ProjectorBinding.from_content(
                projector_id="projector",
                projector_version="1",
                source_kind="RESEARCH_LEDGER",
                source_ref="ledger:1",
                source_digest=_digest("source"),
                projection_schema_ref="schema:1",
                declared_loss_profile_ref="loss:none",
            ),
            "projector_version",
        ),
        (
            MaterializerBinding.from_content(
                materializer_id="materializer",
                materializer_version="1",
                predecessor_plan_digest=_digest("predecessor-plan"),
                source_value_digest=_digest("source-value"),
                target_domain_contract_snapshot_digest=_digest("target-snapshot"),
            ),
            "materializer_version",
        ),
        (
            RecoveryBinding.from_content(
                recovery_handler_id="recovery",
                recovery_handler_version="1",
                interpreter_profile_digest=_digest("interpreter-profile"),
                authoritative_readback_profile_ref="readback:1",
            ),
            "recovery_handler_version",
        ),
    ],
)
def test_all_handler_bindings_reject_digest_preserving_content_mutation(
    binding: object,
    mutated_field: str,
) -> None:
    assert isinstance(
        binding,
        (
            CompilerBinding,
            QualificationBinding,
            InterpreterBinding,
            ProjectorBinding,
            MaterializerBinding,
            RecoveryBinding,
        ),
    )
    assert len(binding.binding_digest) == 64
    payload = binding.model_dump(mode="json")
    payload[mutated_field] = "mutated"
    with pytest.raises(ValidationError, match="canonical binding content"):
        type(binding)(**payload)


def test_claim_rejects_arbitrary_and_digest_preserving_attempt_identity() -> None:
    assignment = _interpret_assignment()
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease-1",
        lease_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        node_id="node-1",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=_digest("interpreter-profile"),
        authority_digest=_digest("authority"),
    )
    payload = claim.model_dump(mode="json")
    payload["attempt_id"] = _digest("substituted-attempt")
    with pytest.raises(ValidationError, match="canonical claim content"):
        ClaimBinding(**payload)

    payload["attempt_id"] = "arbitrary-attempt"
    with pytest.raises(ValidationError, match="64"):
        ClaimBinding(**payload)


def test_run_step_and_effect_states_remain_separate() -> None:
    claimed = StepSnapshot("step-1", StepState.CLAIMED)
    running = reduce_step(
        claimed,
        StepEvent.EFFECT_STARTED,
        StepState.RUNNING,
        guard=True,
    )
    assert running.state is StepState.RUNNING
    assert running.effect_disposition is EffectDisposition.IN_FLIGHT
    unknown = reduce_step(
        running,
        StepEvent.EFFECT_RECEIPT_LOST,
        StepState.RECONCILING,
        guard=True,
    )
    assert unknown.state is StepState.RECONCILING
    assert unknown.effect_disposition is EffectDisposition.OUTCOME_UNKNOWN

    failed = reduce_step(
        running,
        StepEvent.EFFECT_FAILED,
        StepState.FAILED,
        guard=True,
    )
    assert failed.state is StepState.FAILED
    assert failed.effect_disposition is EffectDisposition.FAILED


def test_commit_and_readback_events_converge_effect_disposition() -> None:
    committing = reduce_step(
        StepSnapshot("admission", StepState.RUNNING, EffectDisposition.IN_FLIGHT),
        StepEvent.COMMIT_PREPARED,
        StepState.COMMITTING,
        guard=True,
    )
    assert committing.effect_disposition is EffectDisposition.IN_FLIGHT
    committed = reduce_step(
        committing,
        StepEvent.COMMIT_READBACK_CONFIRMED,
        StepState.SUCCEEDED,
        guard=True,
    )
    assert committed.effect_disposition is EffectDisposition.SUCCEEDED

    waiting = reduce_step(
        StepSnapshot(
            "recovery", StepState.RECONCILING, EffectDisposition.OUTCOME_UNKNOWN
        ),
        StepEvent.READBACK_UNAVAILABLE,
        StepState.WAITING_EXTERNAL,
        guard=True,
    )
    assert waiting.effect_disposition is EffectDisposition.OUTCOME_UNKNOWN


def test_branch_dispositions_are_reachable_only_through_frozen_edges() -> None:
    not_selected = reduce_step(
        StepSnapshot("branch-a", StepState.PENDING),
        StepEvent.BRANCH_NOT_SELECTED,
        StepState.NOT_SELECTED,
        guard=True,
    )
    skipped = reduce_step(
        StepSnapshot("branch-b", StepState.PENDING),
        StepEvent.BRANCH_SKIPPED,
        StepState.SKIPPED_BY_DECISION,
        guard=True,
    )
    assert not_selected.state is StepState.NOT_SELECTED
    assert skipped.state is StepState.SKIPPED_BY_DECISION
    with pytest.raises(IllegalTransition):
        reduce_step(
            StepSnapshot("branch-c", StepState.READY),
            StepEvent.BRANCH_NOT_SELECTED,
            StepState.NOT_SELECTED,
            guard=True,
        )


def test_transition_tables_cover_frozen_events_and_reachable_states() -> None:
    run_events = {event for _, event in RUN_TRANSITIONS}
    step_events = {event for _, event in STEP_TRANSITIONS}
    run_targets = {target for targets in RUN_TRANSITIONS.values() for target in targets}
    step_targets = {
        target for targets in STEP_TRANSITIONS.values() for target in targets
    }

    assert run_events == set(RunEvent) - {RunEvent.BRANCH_UNRESOLVED}
    assert step_events == set(StepEvent) - {
        StepEvent.BRANCH_SELECTED,
        StepEvent.BRANCH_UNRESOLVED,
    }
    assert set(RunState) - {RunState.SUBMITTED} <= run_targets
    # SUPERSEDED is a preserved snapshot disposition; the frozen Step event
    # table intentionally defines no successor-adoption edge for it.
    assert set(StepState) - {StepState.PENDING, StepState.SUPERSEDED} <= step_targets


def test_illegal_transition_fails_closed() -> None:
    with pytest.raises(IllegalTransition):
        reduce_step(
            StepSnapshot("step-1", StepState.READY),
            StepEvent.RUNTIME_VALUE_PRODUCED,
            StepState.SUCCEEDED,
            guard=True,
        )


def test_completion_only_derives_from_required_steps_and_policy() -> None:
    run = RunSnapshot("run-1", RunState.RUNNING)
    policy = CompletionPolicy(required_step_ids=frozenset({"required"}))
    with pytest.raises(IllegalTransition):
        reduce_run_completion(
            run,
            (StepSnapshot("required", StepState.SUCCEEDED, qualifier="DEGRADED"),),
            policy,
        )
    completed = reduce_run_completion(
        run,
        (StepSnapshot("required", StepState.SUCCEEDED),),
        policy,
    )
    assert completed.state is RunState.COMPLETED
    with pytest.raises(ValueError, match="requires required steps"):
        reduce_run_event(
            run,
            RunEvent.RUN_COMPLETION_DERIVED,
            RunState.COMPLETED,
            guard=True,
        )


def _verification_binding() -> VerificationBinding:
    return VerificationBinding.from_content(
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        step_id="admission-step",
        attempt_id="attempt-1",
        input_closure_digest=_digest("inputs"),
        output_content_digest=_digest("candidate"),
        ordered_event_payloads=(b"event-1", b"event-2"),
        schema_digest=_digest("schema"),
        compiler_identity="compiler@1",
        interpreter_identity="interpreter@1",
        verifier_identity="verifier@1",
        actor_id="actor-1",
        project_key="project-1",
        authority_digest=_digest("authority"),
        project_registry_revision=3,
        project_scope_digest=_digest("project-scope"),
        resolved_schema="project_1",
        canonical_owner="research-ledger",
        canonical_object_id="object-1",
        canonical_base_revision=7,
        canonical_incarnation="incarnation-1",
        evidence_digest=_digest("evidence"),
        receipt_digest=_digest("receipt"),
        provenance_digest=_digest("provenance"),
        qualifier="STANDARD",
    )


def test_verification_binding_self_validates_and_binds_ordered_commit_closure() -> None:
    binding = _verification_binding()
    intent = CommitIntent(
        commit_intent_id="intent-1",
        canonical_owner=binding.canonical_owner,
        project_key=binding.project_key,
        object_id=binding.canonical_object_id,
        project_registry_revision=binding.project_registry_revision,
        project_scope_digest=binding.project_scope_digest,
        expected_base_revision=binding.canonical_base_revision,
        expected_incarnation=binding.canonical_incarnation,
        content_digest=binding.output_content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=binding.authority_digest,
        idempotency_key="intent-1",
    )
    require_admission_binding(
        binding,
        intent,
        ordered_event_payloads=(b"event-1", b"event-2"),
        current_authority_digest=binding.authority_digest,
        current_base_revision=7,
        current_incarnation="incarnation-1",
    )

    mutated = binding.model_dump(mode="json")
    mutated["receipt_digest"] = _digest("substituted-receipt")
    with pytest.raises(ValidationError, match="canonical binding content"):
        VerificationBinding(**mutated)

    reordered = intent.model_copy(
        update={"ordered_event_closure_digest": _digest("event-2,event-1")}
    )
    with pytest.raises(ValueError, match="ordered event closure drift"):
        require_admission_binding(
            binding,
            reordered,
            ordered_event_payloads=(b"event-1", b"event-2"),
            current_authority_digest=binding.authority_digest,
            current_base_revision=7,
            current_incarnation="incarnation-1",
        )

    with pytest.raises(ValueError, match="payload bytes drift"):
        require_admission_binding(
            binding,
            intent,
            current_authority_digest=binding.authority_digest,
            current_base_revision=7,
            current_incarnation="incarnation-1",
            ordered_event_payloads=(b"event-1", b"mutated-event-2"),
        )


def test_decide_uniquely_releases_selected_branch_and_preserves_other_terminal_states() -> (
    None
):
    input_type = ObjectType("DecisionInput.v1")
    registry = TransformRegistry(registry_id="test-decisions", registry_version="1")
    discriminator_ref = registry.register_discriminator(
        name="claim-or-gap",
        version="1",
        input_type=input_type,
        branch_ids=("claim", "gap", "blocked"),
        func=_test_discriminator,
    )
    control = CompiledControlNode(
        control_id="decide-1",
        node_kind="decide",
        source_path=("root",),
        input_type=input_type,
        output_type=input_type,
        children=(),
        step_ids=("selector",),
        semantic_return_step_ids=("claim-tail", "gap-entry", "blocked-entry"),
        source_digest=_digest("decision-source"),
        discriminator_ref=discriminator_ref,
        decision_branches=(
            CompiledDecisionBranch(
                "claim",
                "kind == 'claim'",
                ("claim-entry", "claim-tail"),
                ("claim-entry",),
            ),
            CompiledDecisionBranch(
                "gap", "kind == 'claim'", ("gap-entry",), ("gap-entry",)
            ),
            CompiledDecisionBranch(
                "blocked", "kind == 'blocked'", ("blocked-entry",), ("blocked-entry",)
            ),
        ),
    )
    steps = tuple(
        StepSnapshot(step_id, StepState.PENDING)
        for step_id in ("claim-entry", "claim-tail", "gap-entry", "blocked-entry")
    )
    result = reduce_branch_decision(
        RunSnapshot("run-1", RunState.RUNNING),
        steps,
        control,
        discriminator_registry=registry,
        input_value={"kind": "claim"},
        skipped_branch_ids=frozenset({"blocked"}),
    )
    by_id = {step.step_id: step for step in result.steps}
    assert result.selected_branch_id == "claim"
    assert by_id["claim-entry"].state is StepState.READY
    assert by_id["claim-tail"].state is StepState.PENDING
    assert by_id["gap-entry"].state is StepState.NOT_SELECTED
    assert by_id["blocked-entry"].state is StepState.SKIPPED_BY_DECISION
    assert tuple(event.event for event in result.events) == (
        BranchEvent.BRANCH_SELECTED,
        BranchEvent.BRANCH_NOT_SELECTED,
        BranchEvent.BRANCH_SKIPPED,
    )

    with pytest.raises(BranchDecisionUnresolved):
        reduce_branch_decision(
            RunSnapshot("run-2", RunState.RUNNING),
            steps,
            control,
            discriminator_registry=registry,
            input_value={"kind": "claim", "matches": ["claim", "gap"]},
        )

    assert (StepState.PENDING, StepEvent.BRANCH_SELECTED) not in STEP_TRANSITIONS
    assert (StepState.RUNNING, StepEvent.BRANCH_UNRESOLVED) not in STEP_TRANSITIONS
    assert (RunState.RUNNING, RunEvent.BRANCH_UNRESOLVED) not in RUN_TRANSITIONS


def _assignment_for(kind: AssignmentKind) -> RuntimeAssignment:
    if kind is AssignmentKind.COMPILE:
        binding = CompilerBinding.from_content(
            compiler_id="compiler",
            compiler_version="1",
            compiler_digest=_digest("compiler"),
            operation_catalog_digest=_digest("operation-catalog"),
            domain_contract_snapshot_digest=_digest("domain-snapshot"),
        )
        return _interpret_assignment(
            assignment_kind=kind,
            handler_binding_kind=HandlerBindingKind.COMPILER,
            handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
            handler_binding_digest=binding.binding_digest,
            handler_binding=binding,
            step_id=None,
            step_role=None,
            expected_step_revision=None,
            operation_contract_ref=None,
            operation_contract_digest=None,
            return_contract_binding=None,
            compiled_admission_binding=None,
            plan_digest=None,
        )
    if kind is AssignmentKind.QUALIFY:
        binding = QualificationBinding.from_content(
            authority_reader_id="authority-reader",
            authority_reader_version="1",
            authority_reader_digest=_digest("authority-reader"),
            deployment_catalog_digest=_digest("deployment-catalog"),
            resource_policy_epoch=3,
        )
        return _interpret_assignment(
            assignment_kind=kind,
            handler_binding_kind=HandlerBindingKind.QUALIFICATION,
            handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
            handler_binding_digest=binding.binding_digest,
            handler_binding=binding,
            step_id=None,
            step_role=None,
            expected_step_revision=None,
            operation_contract_ref=None,
            operation_contract_digest=None,
            return_contract_binding=None,
            compiled_admission_binding=None,
        )
    if kind is AssignmentKind.INTERPRET:
        return _interpret_assignment()
    if kind is AssignmentKind.VERIFY_ADMIT:
        admission_contract = ReturnContractBinding.from_contract(
            "mrw.return.admission.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=True,
            ),
        )
        compiled_admission = CompiledAdmissionBinding.from_content(
            plan_digest=_digest("plan"),
            effect_step_id="effect-1",
            admission_step_id="step-1",
            operation_contract_digest=_digest("operation-contract"),
            return_contract_ref=admission_contract.return_contract_ref,
            return_contract_digest=admission_contract.binding_digest,
            source_map_digest=_digest("source-map"),
            control_digest=_digest("control"),
        )
        return _interpret_assignment(
            assignment_kind=kind,
            step_role=CompiledStepRole.ADMISSION,
            return_contract_binding=admission_contract,
            compiled_admission_binding=compiled_admission,
        )
    if kind is AssignmentKind.PROJECT:
        binding = ProjectorBinding.from_content(
            projector_id="projector",
            projector_version="1",
            source_kind="RESEARCH_LEDGER",
            source_ref="ledger:1",
            source_digest=_digest("source"),
            projection_schema_ref="schema:1",
            declared_loss_profile_ref="loss:none",
        )
        return _interpret_assignment(
            assignment_kind=kind,
            handler_binding_kind=HandlerBindingKind.PROJECTOR,
            handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
            handler_binding_digest=binding.binding_digest,
            handler_binding=binding,
            step_id=None,
            step_role=None,
            expected_step_revision=None,
            operation_contract_ref=None,
            operation_contract_digest=None,
            return_contract_binding=None,
            compiled_admission_binding=None,
            plan_digest=None,
        )
    if kind is AssignmentKind.RECONCILE:
        binding = RecoveryBinding.from_content(
            recovery_handler_id="recovery",
            recovery_handler_version="1",
            interpreter_profile_digest=_digest("interpreter-profile"),
            authoritative_readback_profile_ref="readback:1",
        )
        return _interpret_assignment(
            assignment_kind=kind,
            handler_binding_kind=HandlerBindingKind.RECOVERY,
            handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
            handler_binding_digest=binding.binding_digest,
            handler_binding=binding,
            step_role=None,
            reconciliation_attempt_id=_digest("attempt"),
            return_contract_binding=None,
            compiled_admission_binding=None,
            plan_digest=None,
        )
    if kind is AssignmentKind.MATERIALIZE_SUCCESSOR:
        binding = MaterializerBinding.from_content(
            materializer_id="materializer",
            materializer_version="1",
            predecessor_plan_digest=_digest("predecessor-plan"),
            source_value_digest=_digest("source-value"),
            target_domain_contract_snapshot_digest=_digest("target-snapshot"),
        )
        source_value_ref = "project-value:source-value"
        return _interpret_assignment(
            assignment_kind=kind,
            handler_binding_kind=HandlerBindingKind.MATERIALIZER,
            handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
            handler_binding_digest=binding.binding_digest,
            handler_binding=binding,
            step_id=None,
            step_role=None,
            expected_step_revision=None,
            operation_contract_ref=None,
            operation_contract_digest=None,
            return_contract_binding=None,
            compiled_admission_binding=None,
            plan_digest=binding.predecessor_plan_digest,
            input_refs=(source_value_ref, "value-1"),
            payload_ref=source_value_ref,
            payload_digest=binding.source_value_digest,
        )
    raise ValueError(f"unsupported assignment kind {kind}")


def _work_item_payload(assignment: RuntimeAssignment) -> dict[str, object]:
    return {
        "schema_version": "mrw.runtime.work_item.v1",
        "work_item_id": assignment.work_item_id,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "assignment_kind": assignment.assignment_kind,
        "assignment": assignment.model_dump(mode="json"),
        "state": WorkItemState.READY,
        "required_node_profile_selector": "any",
        "fairness_key": "project",
        "declared_priority": 0,
        "enqueue_seq": 1,
        "enqueued_at": "2026-08-30T00:00:00Z",
        "due_at": "2026-08-30T00:01:00Z",
        "attempt_count": 0,
    }


def test_document_canonical_read_port_requires_validated_runtime_scope() -> None:
    with pytest.raises(ValueError, match="scope_digest"):
        ProjectScopeRef(
            project_key="p0",
            resolved_schema="project_1",
            project_registry_revision=3,
            incarnation="scope-incarnation-p0-v3",
            scope_digest="not-hex",
        )

    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="p0",
            resolved_schema="project_1",
            project_registry_revision=3,
            incarnation="scope-incarnation-p0-v3",
            scope_digest=_digest("project-scope"),
        ),
        actor_id="actor-1",
    )

    class FakeDocumentReader:
        def read_document(
            self, port_scope: RuntimeScope, document_id: int
        ) -> CanonicalDocumentRead:
            assert port_scope == scope
            return CanonicalDocumentRead(
                document_id=document_id,
                text_hash="a" * 64,
                updated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
                exact_bytes=b"exact document bytes",
            )

    reader = FakeDocumentReader()
    assert isinstance(reader, DocumentCanonicalReadPort)
    observed = reader.read_document(scope, 101)
    assert observed.document_id == 101
    assert observed.text_hash == "a" * 64
    assert observed.exact_bytes == b"exact document bytes"


def test_work_item_root_union_keeps_generic_assignment_kinds() -> None:
    assert set(WORK_ITEM_KIND_INDEX) == set(AssignmentKind)
    for kind, member in WORK_ITEM_KIND_INDEX.items():
        assignment = _assignment_for(kind)
        root = _WORK_ITEM_ROOT_ADAPTER.validate_python(_work_item_payload(assignment))
        assert type(root) is member
        assert root.assignment_kind is kind
        assert root.assignment.assignment_kind is kind
        assert root.work_item_id == assignment.work_item_id
        assert root.project_key == assignment.project_key
        assert root.run_id == assignment.run_id
        assert root.step_id == assignment.step_id
        assert root.assignment_digest == assignment.assignment_digest

    # The union discriminates only on the closed generic assignment kinds; a
    # capability switch keyed on capability/operation identity is forbidden.
    payload = _work_item_payload(_assignment_for(AssignmentKind.INTERPRET))
    payload["assignment_kind"] = "CUSTOM_OPERATION"
    with pytest.raises(ValidationError):
        _WORK_ITEM_ROOT_ADAPTER.validate_python(payload)


def test_work_item_root_rejects_assignment_kind_drift() -> None:
    payload = _work_item_payload(_assignment_for(AssignmentKind.INTERPRET))
    payload["assignment_kind"] = AssignmentKind.QUALIFY
    with pytest.raises(ValidationError, match="kind does not match assignment"):
        _WORK_ITEM_ROOT_ADAPTER.validate_python(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_refs", ("project-value:different-source",)),
        ("payload_digest", _digest("different-source-value")),
    ],
)
def test_materializer_assignment_rejects_exact_source_pair_drift(
    field: str,
    value: object,
) -> None:
    assignment = _assignment_for(AssignmentKind.MATERIALIZE_SUCCESSOR)
    payload = assignment.model_dump(mode="json")
    payload[field] = value
    with pytest.raises(
        ValidationError,
        match="materializer source locator/digest pair is absent from exact inputs",
    ):
        RuntimeAssignment(**payload)


def test_work_item_waiting_requires_wait_reason() -> None:
    payload = _work_item_payload(_assignment_for(AssignmentKind.INTERPRET))
    payload["state"] = WorkItemState.WAITING
    with pytest.raises(ValidationError, match="wait_reason"):
        _WORK_ITEM_ROOT_ADAPTER.validate_python(payload)
    payload["wait_reason"] = WorkItemWaitReason.INTERPRETER_UNAVAILABLE
    root = _WORK_ITEM_ROOT_ADAPTER.validate_python(payload)
    assert root.state is WorkItemState.WAITING
    assert root.wait_reason is WorkItemWaitReason.INTERPRETER_UNAVAILABLE
