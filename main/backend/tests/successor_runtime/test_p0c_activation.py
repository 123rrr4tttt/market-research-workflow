from __future__ import annotations

import hashlib

import pytest

from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.language.program import (
    DecisionBranch,
    ProgramSpec,
    atom_node,
    decide_node,
    identity_node,
    map_output_node,
    pure_node,
    then_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.activation import (
    ActivationError,
    BoundStepValue,
    activate_plan,
)
from app.successor_runtime.runtime.reducer import BranchDecisionUnresolved
from app.successor_runtime.runtime.transitions import StepState


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


INPUT = ObjectType("ActivationInput.v1")
LEFT = ObjectType("ActivationLeft.v1")
RIGHT = ObjectType("ActivationRight.v1")
PAIR = ObjectType("ActivationPair.v1")
MID = ObjectType("ActivationMid.v1")
OUTPUT = ObjectType("ActivationOutput.v1")
CLAIM_OR_GAP = ObjectType("ClaimOrGap.v1")
CLAIM = ObjectType("Claim.v1")


def _to_mid(value: object) -> dict[str, object]:
    return {"mid": value}


def _left_then_right(left: object, right: object) -> dict[str, object]:
    return {"ordered": [left, right]}


def _right_then_left(right: object, left: object) -> dict[str, object]:
    return {"ordered": [right, left]}


def _claim_or_gap(value: object) -> str:
    assert isinstance(value, dict)
    return str(value["kind"])


def _copy_claim_or_gap(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return dict(value)


def _change_claim_or_gap(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return {**value, "changed": True}


def _value(
    label: str, object_type: ObjectType, *, value: object | None = None
) -> ValueRef:
    content = label if value is None else repr(value)
    return ValueRef(
        value_id=label,
        project_key="activation-project",
        object_type=object_type,
        codec_id=object_type.codec_id,
        content_digest=_digest(content),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{label}",
        byte_size=max(1, len(content.encode("utf-8"))),
        provenance_digest=_digest(label + ":provenance"),
    )


def _operation(
    operation_id: str,
    input_type: ObjectType,
    output_type: ObjectType,
    *,
    admission: bool = False,
):
    kind = f"activation.{operation_id}.v1"
    contract = make_operation_contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=(
            CLAIM_OR_GAP_RETURN_CONTRACT_REF
            if admission
            else RUNTIME_VALUE_RETURN_CONTRACT_REF
        ),
        semantic_profile_ref=f"{kind}.semantic",
        effect_profile_ref=f"{kind}.effect",
        resource_profile_ref=f"{kind}.resource",
        failure_profile_ref=f"{kind}.failure",
        authority_profile_ref=f"{kind}.authority",
        interpreter_compatibility_ref=f"{kind}.interpreter",
        observation_profile_ref=f"{kind}.observation",
        allowed_override_schema_ref=f"{kind}.overrides",
        owner_capability_id="activation-test",
    )
    operation = OperationSpec(
        operation_id=operation_id,
        contract_ref=contract.ref,
        input_refs=(
            _value(f"{operation_id}:static:1", input_type),
            _value(f"{operation_id}:static:2", input_type),
        ),
        payload_ref=_value(f"{operation_id}:payload", input_type),
        allowed_overrides=freeze_json_object({}),
    )
    return atom_node(operation, input_type, output_type), contract


def _registry(*contracts):
    catalog = OperationContractCatalogSnapshot(
        catalog_id="activation-tests",
        catalog_version="1",
        entries=tuple(
            (
                contract.ref.kind,
                contract.ref.contract_version,
                contract.ref.contract_digest,
                contract.owner_capability_id,
            )
            for contract in contracts
        ),
        catalog_digest=None,
    )
    registry = OperationContractRegistry(catalog, tuple(contracts))
    return registry.catalog, registry


def _program(root, *, transform_refs=()) -> ProgramSpec:
    return ProgramSpec(
        program_id="activation-program",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key="activation-project",
        project_registry_revision=1,
        project_scope_digest=_digest("project-scope"),
        semantic_identity="activation-tests",
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(AlgebraRef("mrw.successor.language.algebra", "1"),),
        transform_refs=transform_refs,
        observation_profile="activation-test-observation",
        metadata=freeze_json_object({}),
        program_digest="",
    ).with_digest()


def _compile(program, contracts, transforms, merges, discriminators):
    catalog, registry = _registry(*contracts)
    return compile_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )


def _empty_registries():
    return (
        TransformRegistry(registry_id="activation-transforms"),
        TransformRegistry(registry_id="activation-merges"),
        TransformRegistry(registry_id="activation-discriminators"),
    )


def test_identity_has_no_synthetic_work_or_value() -> None:
    transforms, merges, discriminators = _empty_registries()
    program = _program(identity_node(INPUT))
    plan = _compile(program, (), transforms, merges, discriminators)

    result = activate_plan(
        run_id="run-identity",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )

    assert result.values == ()
    assert result.materializations == ()
    assert result.activations == ()
    assert result.branch_decisions == ()


def test_pure_reads_exact_embedded_value_ref_without_inventing_a_copy() -> None:
    transforms, merges, discriminators = _empty_registries()
    exact_ref = _value("literal:source", LEFT, value={"source": 101})
    effect, contract = _operation("literal-reader", LEFT, OUTPUT)
    program = _program(
        then_node(
            pure_node(
                INPUT,
                LEFT,
                {"source_value_ref": exact_ref.to_plain()},
                "mrw.functorial-successor.value-ref.literal.v1",
            ),
            effect,
        )
    )
    plan = _compile(program, (contract,), transforms, merges, discriminators)

    result = activate_plan(
        run_id="run-literal-ref",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )

    assert result.values[0].value_ref == exact_ref
    assert result.materializations == ()
    assert result.activations[0].ordered_dependency_refs == (exact_ref,)


def test_fixed_point_preserves_order_and_binds_dynamic_output_ref() -> None:
    transforms, merges, discriminators = _empty_registries()
    transform_ref = transforms.register_transform(
        name="activation.to-mid",
        version="1",
        input_type=MID,
        output_type=PAIR,
        func=_to_mid,
    )
    first, first_contract = _operation("first", LEFT, MID)
    second, second_contract = _operation("second", PAIR, OUTPUT)
    root = then_node(
        then_node(
            then_node(
                pure_node(INPUT, LEFT, {"seed": "left"}, "activation-json-v1"),
                first,
            ),
            map_output_node(identity_node(MID), transform_ref, PAIR),
        ),
        second,
    )
    program = _program(root, transform_refs=(transform_ref,))
    plan = _compile(
        program,
        (first_contract, second_contract),
        transforms,
        merges,
        discriminators,
    )
    first_step = next(
        step for step in plan.ordered_steps if step.operation_id == "first"
    )
    second_step = next(
        step for step in plan.ordered_steps if step.operation_id == "second"
    )

    initial = activate_plan(
        run_id="run-ordered",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
    assert [item.step_id for item in initial.activations] == [first_step.step_id]
    assert initial.activations[0].static_atom_input_refs == first.operation.input_refs
    assert initial.activations[0].payload_ref == first.operation.payload_ref

    dynamic_ref = _value("first:dynamic-output", MID, value={"effect": "one"})
    completed = BoundStepValue(first_step.step_id, dynamic_ref, {"effect": "one"})
    resumed = activate_plan(
        run_id="run-ordered",
        program=program,
        plan=plan,
        completed_outputs=(completed, completed),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({first_step.step_id}),
    )

    assert [item.step_id for item in resumed.activations] == [second_step.step_id]
    transform_value = next(
        value for value in resumed.values if value.step_id in second_step.dependencies
    )
    assert transform_value.value == {"mid": {"effect": "one"}}
    assert resumed.activations[0].ordered_dependency_refs == (
        transform_value.value_ref,
    )
    assert resumed.activations[0].ordered_input_refs == (
        transform_value.value_ref,
        *second.operation.input_refs,
    )
    assert resumed.activations[0].input_closure_digest != _digest("refs-only")


def test_union_typed_identity_transform_preserves_exact_variant_value_ref() -> None:
    transforms, merges, discriminators = _empty_registries()
    identity_ref = transforms.register_transform(
        name="activation.claim-or-gap-identity",
        version="1",
        input_type=CLAIM_OR_GAP,
        output_type=CLAIM_OR_GAP,
        func=_copy_claim_or_gap,
        preserves_value_ref=True,
    )
    claim_effect, claim_contract = _operation(
        "claim",
        INPUT,
        CLAIM_OR_GAP,
    )
    program = _program(
        then_node(
            claim_effect,
            map_output_node(
                identity_node(CLAIM_OR_GAP),
                identity_ref,
                CLAIM_OR_GAP,
            ),
        ),
        transform_refs=(identity_ref,),
    )
    plan = _compile(
        program,
        (claim_contract,),
        transforms,
        merges,
        discriminators,
    )
    claim_step = next(
        step for step in plan.ordered_steps if step.operation_id == "claim"
    )
    transform_step = next(
        step for step in plan.ordered_steps if step.step_kind == "TRANSFORM"
    )
    claim_value = {"kind": "claim", "claim_id": "claim-1"}
    exact_claim_ref = _value("claim:exact", CLAIM, value=claim_value)

    result = activate_plan(
        run_id="run-claim-identity",
        program=program,
        plan=plan,
        completed_outputs=(
            BoundStepValue(claim_step.step_id, exact_claim_ref, claim_value),
        ),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({claim_step.step_id}),
    )

    derived = next(
        value for value in result.values if value.step_id == transform_step.step_id
    )
    assert derived.value_ref == exact_claim_ref
    assert derived.value == claim_value
    assert result.materializations == ()


def test_same_bytes_transform_without_preservation_contract_gets_new_value_ref() -> (
    None
):
    transforms, merges, discriminators = _empty_registries()
    transform_ref = transforms.register_transform(
        name="activation.same-bytes-not-identity",
        version="1",
        input_type=CLAIM_OR_GAP,
        output_type=CLAIM_OR_GAP,
        func=_copy_claim_or_gap,
    )
    effect, contract = _operation("same-bytes-source", INPUT, CLAIM_OR_GAP)
    program = _program(
        then_node(
            effect,
            map_output_node(identity_node(CLAIM_OR_GAP), transform_ref, CLAIM_OR_GAP),
        ),
        transform_refs=(transform_ref,),
    )
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    effect_step = next(
        step for step in plan.ordered_steps if step.step_kind == "EFFECT"
    )
    input_value = {"kind": "claim", "claim_id": "claim-ordinary"}
    input_ref = _value("claim:ordinary", CLAIM, value=input_value)

    result = activate_plan(
        run_id="run-same-bytes-ordinary",
        program=program,
        plan=plan,
        completed_outputs=(
            BoundStepValue(effect_step.step_id, input_ref, input_value),
        ),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({effect_step.step_id}),
    )

    assert len(result.materializations) == 1
    assert result.materializations[0].value_ref != input_ref


def test_value_ref_preserving_transform_that_changes_bytes_fails_closed() -> None:
    transforms, merges, discriminators = _empty_registries()
    transform_ref = transforms.register_transform(
        name="activation.false-identity",
        version="1",
        input_type=CLAIM_OR_GAP,
        output_type=CLAIM_OR_GAP,
        func=_change_claim_or_gap,
        preserves_value_ref=True,
    )
    effect, contract = _operation("false-identity-source", INPUT, CLAIM_OR_GAP)
    program = _program(
        then_node(
            effect,
            map_output_node(identity_node(CLAIM_OR_GAP), transform_ref, CLAIM_OR_GAP),
        ),
        transform_refs=(transform_ref,),
    )
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    effect_step = next(
        step for step in plan.ordered_steps if step.step_kind == "EFFECT"
    )
    input_value = {"kind": "claim", "claim_id": "claim-false-identity"}
    input_ref = _value("claim:false-identity", CLAIM, value=input_value)

    with pytest.raises(ActivationError, match="changed bytes"):
        activate_plan(
            run_id="run-false-identity",
            program=program,
            plan=plan,
            completed_outputs=(
                BoundStepValue(effect_step.step_id, input_ref, input_value),
            ),
            transform_registry=transforms,
            merge_registry=merges,
            discriminator_registry=discriminators,
            already_activated_step_ids=frozenset({effect_step.step_id}),
        )


def test_zip_ordered_is_left_to_right_and_not_commutative() -> None:
    transforms, merges, discriminators = _empty_registries()
    forward_ref = merges.register_merge(
        name="activation.left-right",
        version="1",
        left_type=LEFT,
        right_type=RIGHT,
        output_type=PAIR,
        func=_left_then_right,
    )
    reverse_ref = merges.register_merge(
        name="activation.right-left",
        version="1",
        left_type=RIGHT,
        right_type=LEFT,
        output_type=PAIR,
        func=_right_then_left,
    )
    forward = _program(
        zip_ordered_node(
            pure_node(INPUT, LEFT, {"side": "left"}, "activation-json-v1"),
            pure_node(INPUT, RIGHT, {"side": "right"}, "activation-json-v1"),
            forward_ref,
            PAIR,
        ),
        transform_refs=(forward_ref,),
    )
    reverse = _program(
        zip_ordered_node(
            pure_node(INPUT, RIGHT, {"side": "right"}, "activation-json-v1"),
            pure_node(INPUT, LEFT, {"side": "left"}, "activation-json-v1"),
            reverse_ref,
            PAIR,
        ),
        transform_refs=(reverse_ref,),
    )
    forward_plan = _compile(forward, (), transforms, merges, discriminators)
    reverse_plan = _compile(reverse, (), transforms, merges, discriminators)

    forward_result = activate_plan(
        run_id="run-zip-forward",
        program=forward,
        plan=forward_plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
    reverse_result = activate_plan(
        run_id="run-zip-reverse",
        program=reverse,
        plan=reverse_plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )

    assert forward_result.values[-1].value == {
        "ordered": [{"side": "left"}, {"side": "right"}]
    }
    assert reverse_result.values[-1].value == {
        "ordered": [{"side": "right"}, {"side": "left"}]
    }
    assert forward_result.values[-1].value != reverse_result.values[-1].value


def test_decide_reuses_reducer_and_releases_only_selected_branch() -> None:
    transforms, merges, discriminators = _empty_registries()
    discriminator_ref = discriminators.register_discriminator(
        name="activation.claim-or-gap",
        version="1",
        input_type=MID,
        branch_ids=("claim", "gap"),
        func=_claim_or_gap,
    )
    claim, claim_contract = _operation("claim-branch", MID, OUTPUT)
    gap, gap_contract = _operation("gap-branch", MID, OUTPUT)
    decision = decide_node(
        discriminator_ref,
        (
            DecisionBranch("claim", "kind == 'claim'", claim),
            DecisionBranch("gap", "kind == 'gap'", gap),
        ),
    )
    root = then_node(
        pure_node(INPUT, MID, {"kind": "claim"}, "activation-json-v1"),
        decision,
    )
    program = _program(root, transform_refs=(discriminator_ref,))
    plan = _compile(
        program,
        (claim_contract, gap_contract),
        transforms,
        merges,
        discriminators,
    )

    result = activate_plan(
        run_id="run-decide",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )

    assert [item.operation_id for item in result.activations] == ["claim-branch"]
    assert len(result.branch_decisions) == 1
    reduction = result.branch_decisions[0].reduction
    assert reduction.selected_branch_id == "claim"
    states = {step.step_id: step.state for step in reduction.steps}
    claim_step = next(
        step for step in plan.ordered_steps if step.operation_id == "claim-branch"
    )
    gap_step = next(
        step for step in plan.ordered_steps if step.operation_id == "gap-branch"
    )
    assert states[claim_step.step_id] is StepState.READY
    assert states[gap_step.step_id] is StepState.NOT_SELECTED


def test_unresolved_decide_does_not_release_static_join_after_all_branches() -> None:
    transforms, merges, discriminators = _empty_registries()
    discriminator_ref = discriminators.register_discriminator(
        name="activation.unresolved-claim-or-gap",
        version="1",
        input_type=MID,
        branch_ids=("claim", "gap"),
        func=_claim_or_gap,
    )
    claim, claim_contract = _operation("unresolved-claim", MID, OUTPUT)
    gap, gap_contract = _operation("unresolved-gap", MID, OUTPUT)
    terminal, terminal_contract = _operation("must-not-run", OUTPUT, OUTPUT)
    decision = decide_node(
        discriminator_ref,
        (
            DecisionBranch("claim", "kind == 'claim'", claim),
            DecisionBranch("gap", "kind == 'gap'", gap),
        ),
    )
    program = _program(
        then_node(
            pure_node(INPUT, MID, {"not_a_variant": True}, "activation-json-v1"),
            then_node(decision, terminal),
        ),
        transform_refs=(discriminator_ref,),
    )
    plan = _compile(
        program,
        (claim_contract, gap_contract, terminal_contract),
        transforms,
        merges,
        discriminators,
    )

    with pytest.raises(BranchDecisionUnresolved):
        activate_plan(
            run_id="run-unresolved-decide",
            program=program,
            plan=plan,
            transform_registry=transforms,
            merge_registry=merges,
            discriminator_registry=discriminators,
        )


def test_admission_uses_effect_dynamic_ref_and_duplicate_input_is_idempotent() -> None:
    transforms, merges, discriminators = _empty_registries()
    atom, contract = _operation("admitted", INPUT, OUTPUT, admission=True)
    program = _program(atom)
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    effect = next(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    admission = next(
        step for step in plan.ordered_steps if step.step_kind == "ADMISSION"
    )

    dynamic_ref = _value("admitted:dynamic", OUTPUT, value={"candidate": 1})
    completed = BoundStepValue(effect.step_id, dynamic_ref, {"candidate": 1})
    first = activate_plan(
        run_id="run-admission",
        program=program,
        plan=plan,
        completed_outputs=(completed, completed),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({effect.step_id}),
    )
    replay = activate_plan(
        run_id="run-admission",
        program=program,
        plan=plan,
        completed_outputs=(completed, completed),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({effect.step_id}),
    )

    assert first == replay
    assert [item.step_id for item in first.activations] == [admission.step_id]
    descriptor = first.activations[0]
    assert descriptor.ordered_dependency_refs == (dynamic_ref,)
    assert descriptor.static_atom_input_refs == atom.operation.input_refs
    assert descriptor.payload_ref == atom.operation.payload_ref
    assert descriptor.input_closure_digest == replay.activations[0].input_closure_digest
    assert descriptor.activation_digest == replay.activations[0].activation_digest
