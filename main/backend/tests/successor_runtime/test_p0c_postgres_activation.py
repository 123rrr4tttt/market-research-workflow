from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.successor_runtime.language.program import (
    DecisionBranch,
    decide_node,
    pure_node,
    then_node,
)
from app.successor_runtime.runtime.activation import BoundStepValue, activate_plan
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    InterpreterBinding,
    RecoveryBinding,
)
from app.successor_runtime.runtime.qualification import (
    AuthoritySourceBinding,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    ActivationCatalogEntry,
    FirstSpecimenActivationCatalog,
    _assignment,
    _bind_materializations_to_project,
    _require_exact_existing,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
)
from tests.successor_runtime.test_p0c_activation import (
    INPUT,
    MID,
    OUTPUT,
    _claim_or_gap,
    _compile,
    _digest,
    _empty_registries,
    _operation,
    _program,
    _value,
)

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


def test_project_rebind_preserves_dynamic_prefix_static_suffix_and_descriptor_digest() -> None:
    transforms, merges, discriminators = _empty_registries()
    first, first_contract = _operation("pg-first", INPUT, MID)
    second, second_contract = _operation("pg-second", MID, OUTPUT)
    program = _program(then_node(first, then_node(pure_node(MID, MID, {"seed": 1}, "json-v1"), second)))
    plan = _compile(
        program,
        (first_contract, second_contract),
        transforms,
        merges,
        discriminators,
    )
    first_step = next(step for step in plan.ordered_steps if step.operation_id == "pg-first")
    second_step = next(step for step in plan.ordered_steps if step.operation_id == "pg-second")
    dynamic = _value("pg-first-result", MID, value={"effect": 1})
    raw = activate_plan(
        run_id="run-pg-order",
        program=program,
        plan=plan,
        completed_outputs=(BoundStepValue(first_step.step_id, dynamic, {"effect": 1}),),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({first_step.step_id}),
    )
    rebound = _bind_materializations_to_project(raw, plan)

    descriptor = next(item for item in rebound.activations if item.step_id == second_step.step_id)
    assert descriptor.ordered_dependency_refs[0].storage_kind == "project_value_ref"
    assert descriptor.ordered_dependency_refs[0].storage_ref.startswith("project-value:")
    assert descriptor.ordered_input_refs == (
        *descriptor.ordered_dependency_refs,
        *second.operation.input_refs,
    )
    assert descriptor.input_closure_digest != raw.activations[0].input_closure_digest
    assert len(descriptor.activation_digest) == 64


def test_dependency_unmet_does_not_fabricate_downstream_activation() -> None:
    transforms, merges, discriminators = _empty_registries()
    first, first_contract = _operation("pg-dependency-first", INPUT, MID)
    second, second_contract = _operation("pg-dependency-second", MID, OUTPUT)
    program = _program(then_node(first, second))
    plan = _compile(
        program,
        (first_contract, second_contract),
        transforms,
        merges,
        discriminators,
    )
    result = activate_plan(
        run_id="run-pg-dependency",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
    assert tuple(item.operation_id for item in result.activations) == (
        "pg-dependency-first",
    )


def test_branch_releases_only_selected_effect_and_duplicate_pair_is_absent_or_exact() -> None:
    transforms, merges, discriminators = _empty_registries()
    discriminator = discriminators.register_discriminator(
        name="activation.pg.branch",
        version="1",
        input_type=MID,
        branch_ids=("claim", "gap"),
        func=_claim_or_gap,
    )
    claim, claim_contract = _operation("pg-claim", MID, OUTPUT)
    gap, gap_contract = _operation("pg-gap", MID, OUTPUT)
    program = _program(
        then_node(
            pure_node(INPUT, MID, {"kind": "claim"}, "json-v1"),
            decide_node(
                discriminator,
                (
                    DecisionBranch("claim", "kind == 'claim'", claim),
                    DecisionBranch("gap", "kind == 'gap'", gap),
                ),
            ),
        ),
        transform_refs=(discriminator,),
    )
    plan = _compile(
        program,
        (claim_contract, gap_contract),
        transforms,
        merges,
        discriminators,
    )
    result = _bind_materializations_to_project(
        activate_plan(
            run_id="run-pg-branch",
            program=program,
            plan=plan,
            transform_registry=transforms,
            merge_registry=merges,
            discriminator_registry=discriminators,
        ),
        plan,
    )
    assert tuple(item.operation_id for item in result.activations) == ("pg-claim",)
    expected = {"work_item_id": "work:1", "assignment_digest": _digest("assignment")}
    _require_exact_existing(dict(expected), expected, "runtime work item")
    with pytest.raises(ExactBindingConflict, match="assignment_digest"):
        _require_exact_existing(
            {**expected, "assignment_digest": _digest("other")},
            expected,
            "runtime work item",
        )


def _entry(contract_digest: str, *, handler_digest_override: str | None = None):
    deployment = _digest("deployment")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=_digest("profile"),
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=_digest("project-scope"),
        resource_policy_epoch=3,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="p0c-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=interpreter.interpreter_profile_digest,
        authoritative_readback_profile_ref="project-value-readback",
    )
    eligibility = QueueEligibility(
        project_key="activation-project",
        capability_id="activation-test",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=3,
        policy_digest=_digest("resource-policy"),
        concurrency_key="activation-project:p0c",
    )
    entry = ActivationCatalogEntry(
        operation_contract_digest=contract_digest,
        interpreter_binding=interpreter,
        recovery_binding=recovery,
        queue_eligibility=eligibility,
        required_node_profile_selector="node-profile:p0c",
        resource_policy_digest=eligibility.policy_digest,
        fairness_key="activation-project",
        effect_class="CPU_LIGHT",
    )
    return entry, interpreter, handler_digest_override or interpreter.binding_digest


def _authorization(step, interpreter: InterpreterBinding, payload_digest: str):
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="project-scope:activation-project:1",
        source_digest=_digest("project-scope"),
        source_epoch=1,
    )
    eligibility = _entry(step.operation_contract_ref.contract_digest)[0].queue_eligibility
    return StepAuthorizationBinding.from_content(
        run_id="run-admission",
        step_id=step.step_id,
        operation_kind=step.operation_contract_ref.kind,
        operation_contract_digest=step.operation_contract_ref.contract_digest,
        capability_id="activation-test",
        claim_owner="successor",
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        payload_digest=payload_digest,
        actor_id="actor:p0c",
        project_key="activation-project",
        project_registry_revision=1,
        project_scope_digest=_digest("project-scope"),
        interpreter_binding_digest=interpreter.binding_digest,
        deployment_catalog_digest=interpreter.deployment_catalog_digest,
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        resource_ceiling_digest=_digest("ceiling"),
        resource_policy_epoch=3,
        queue_eligibility_digest=eligibility.eligibility_digest,
        grant_epoch=1,
        expires_at=NOW + timedelta(hours=1),
        canonical_base_revision=0,
        canonical_incarnation="activation-project-incarnation",
    )


def test_admission_assignment_binds_staged_effect_pair_and_catalog_rejects_handler_drift() -> None:
    transforms, merges, discriminators = _empty_registries()
    atom, contract = _operation("pg-admitted", INPUT, OUTPUT, admission=True)
    program = _program(atom)
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    effect = next(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    admission = next(step for step in plan.ordered_steps if step.step_kind == "ADMISSION")
    dynamic = _value("pg-staged", OUTPUT, value={"candidate": 1})
    result = activate_plan(
        run_id="run-admission",
        program=program,
        plan=plan,
        completed_outputs=(BoundStepValue(effect.step_id, dynamic, {"candidate": 1}),),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({effect.step_id}),
    )
    descriptor = result.activations[0]
    entry, interpreter, _ = _entry(contract.ref.contract_digest)
    authorization = _authorization(admission, interpreter, descriptor.payload_ref.content_digest)
    assignment = _assignment(
        run={
            "project_key": "activation-project",
            "run_id": "run-admission",
            "program_digest": program.program_digest,
            "execution_epoch": 2,
            "incarnation": "run-incarnation",
        },
        plan=plan,
        step=admission,
        descriptor=descriptor,
        authorization=authorization,
        entry=entry,
        trace_id="trace:p0c",
    )
    assert assignment.assignment_kind is AssignmentKind.VERIFY_ADMIT
    assert assignment.compiled_admission_binding is not None
    assert assignment.compiled_admission_binding.effect_step_id == effect.step_id
    assert assignment.input_refs == (
        dynamic.storage_ref,
        *tuple(ref.storage_ref for ref in atom.operation.input_refs),
    )
    assert assignment.payload_ref == atom.operation.payload_ref.storage_ref

    other, _, _ = _entry(_digest("other-contract"))
    with pytest.raises(ValueError, match="interpreter/operation"):
        ActivationCatalogEntry(
            operation_contract_digest=contract.ref.contract_digest,
            interpreter_binding=other.interpreter_binding,
            recovery_binding=other.recovery_binding,
            queue_eligibility=other.queue_eligibility,
            required_node_profile_selector="node-profile:p0c",
            resource_policy_digest=other.resource_policy_digest,
            fairness_key="activation-project",
            effect_class="CPU_LIGHT",
        )

    FirstSpecimenActivationCatalog(
        entries=(entry,),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
