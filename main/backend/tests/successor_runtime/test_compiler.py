from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from app.successor_runtime.capabilities.catalog import build_first_specimen_catalog
from app.successor_runtime.capabilities.first_specimen import (
    build_first_specimen_bundle,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    ObjectType,
    OperationSpec,
    ReturnContract,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.compile import CompileFailure, compile_program
from app.successor_runtime.language.laws import (
    failure_return_barrier_preservation,
    left_identity,
    map_output_preservation,
    normalization_associativity,
    right_identity,
    zip_ordered_noncommutativity,
)
from app.successor_runtime.language.object_contracts import (
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.language.plan import with_plan_digest
from app.successor_runtime.language.program import (
    DecisionBranch,
    ProgramSpec,
    atom_node,
    decide_node,
    map_output_node,
    then_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import (
    DiscriminatorRef,
    MergeRef,
    TransformRef,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


INPUT = ObjectType("ResearchIntent.v1", "1", "research-intent", "1")
MATERIAL = ObjectType("MaterialRef.v1", "1", "material-ref", "1")
EVIDENCE = ObjectType("EvidenceQualification.v1", "1", "evidence", "1")
OUTCOME = ObjectType("ClaimOrGap.v1", "1", "claim-gap", "1")


def _value(label: str, object_type: ObjectType) -> ValueRef:
    return ValueRef(
        value_id=label,
        project_key="specimen",
        object_type=object_type,
        codec_id=object_type.codec_id,
        content_digest=_digest(label + ":content"),
        storage_kind="project_value_ref",
        store_id="successor-values",
        store_version="1",
        storage_ref=label,
        byte_size=1,
        provenance_digest=_digest(label + ":provenance"),
    )


def _atom(
    kind: str,
    operation_id: str,
    input_type: ObjectType,
    output_type: ObjectType,
    *,
    admission: bool = False,
):
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
        semantic_profile_ref="semantic@1",
        effect_profile_ref="effect@1",
        resource_profile_ref="resource@1",
        failure_profile_ref="failure@1",
        authority_profile_ref="authority@1",
        interpreter_compatibility_ref="interpreter@1",
        observation_profile_ref="observation@1",
        allowed_override_schema_ref="overrides@1",
        owner_capability_id="first-specimen",
    )
    ref = contract.ref
    operation = OperationSpec(
        operation_id=operation_id,
        contract_ref=ref,
        input_refs=(_value(operation_id + ":input", input_type),),
        payload_ref=_value(operation_id + ":payload", input_type),
        allowed_overrides=freeze_json_object({}),
    )
    return atom_node(
        operation,
        input_type,
        output_type,
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=admission,
            wait_modes=("WAIT",),
            cancel_modes=("CANCELED",),
        ),
    )


READ = _atom("material.read_canonical_ref.v1", "read-material", INPUT, MATERIAL)
QUALIFY = _atom(
    "evidence.qualify.v1", "qualify-evidence", MATERIAL, EVIDENCE, admission=True
)
CLAIM = _atom(
    "claim.form_or_open_gap.v1", "form-claim-or-gap", EVIDENCE, OUTCOME, admission=True
)


def _registry(*nodes) -> OperationContractRegistry:
    contracts = []
    for node in nodes:
        ref = node.operation.contract_ref
        admission = node.return_contract.admission_required
        contracts.append(
            make_operation_contract(
                kind=ref.kind,
                contract_version=ref.contract_version,
                input_type=node.input_type,
                output_type=node.output_type,
                return_contract_ref=(
                    CLAIM_OR_GAP_RETURN_CONTRACT_REF
                    if admission
                    else RUNTIME_VALUE_RETURN_CONTRACT_REF
                ),
                semantic_profile_ref="semantic@1",
                effect_profile_ref="effect@1",
                resource_profile_ref="resource@1",
                failure_profile_ref="failure@1",
                authority_profile_ref="authority@1",
                interpreter_compatibility_ref="interpreter@1",
                observation_profile_ref="observation@1",
                allowed_override_schema_ref="overrides@1",
                owner_capability_id="first-specimen",
            )
        )
    unique = tuple({contract.ref.kind: contract for contract in contracts}.values())
    catalog = OperationContractCatalogSnapshot(
        catalog_id="first-specimen",
        catalog_version="1",
        entries=tuple(
            (
                c.ref.kind,
                c.ref.contract_version,
                c.ref.contract_digest,
                c.owner_capability_id,
            )
            for c in unique
        ),
        catalog_digest=None,
    )
    return OperationContractRegistry(catalog, unique)


REGISTRY = _registry(READ, QUALIFY, CLAIM)
CATALOG = REGISTRY.catalog


def _spec(root, name: str) -> ProgramSpec:
    return ProgramSpec(
        program_id=name,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key="specimen",
        project_registry_revision=1,
        project_scope_digest=_digest("scope"),
        semantic_identity=name,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(AlgebraRef("first-specimen", "1"),),
        transform_refs=(),
        observation_profile="first-specimen.observation.v1",
        metadata=freeze_json_object({}),
        program_digest="",
    ).with_digest()


def _compile(root, name: str):
    return compile_program(_spec(root, name), CATALOG, operation_contracts=REGISTRY)


def test_deterministic_step_ids_bind_normalized_ast_path_and_atom_content() -> None:
    program = _spec(then_node(READ, QUALIFY), "read-then-qualify")
    first = compile_program(program, CATALOG, operation_contracts=REGISTRY)
    second = compile_program(program, CATALOG, operation_contracts=REGISTRY)

    assert tuple(step.step_id for step in first.ordered_steps) == tuple(
        step.step_id for step in second.ordered_steps
    )
    assert first.plan_digest == second.plan_digest


def test_plan_digest_binds_persisted_completion_policy() -> None:
    plan = _compile(then_node(READ, QUALIFY), "completion-policy-binding")
    changed = replace(
        plan,
        completion_policy=replace(plan.completion_policy, ordered=False),
        plan_digest="",
    )

    assert with_plan_digest(changed).plan_digest != plan.plan_digest


def test_admission_required_atom_is_composite_and_downstream_uses_admission_barrier() -> (
    None
):
    plan = _compile(then_node(then_node(READ, QUALIFY), CLAIM), "first-specimen-path")
    qualify_steps = [
        step for step in plan.ordered_steps if step.operation_id == "qualify-evidence"
    ]
    effect, admission = qualify_steps

    assert (effect.step_kind, admission.step_kind) == ("EFFECT", "ADMISSION")
    assert effect.staged_output_only is True
    assert effect.semantic_return_barrier is False
    assert admission.dependencies == (effect.step_id,)
    assert admission.semantic_return_barrier is True

    claim_effect = next(
        step
        for step in plan.ordered_steps
        if step.operation_id == "form-claim-or-gap" and step.step_kind == "EFFECT"
    )
    assert admission.step_id in claim_effect.dependencies
    qualify_map = next(
        item
        for item in plan.source_map
        if item.source_kind == "atom"
        and item.step_ids == (effect.step_id, admission.step_id)
    )
    assert qualify_map.semantic_return_step_ids == (admission.step_id,)


def test_invalid_program_fails_typed_before_any_effect_boundary() -> None:
    empty = OperationContractCatalogSnapshot("empty", "1", (), None)
    program = _spec(READ, "invalid")

    with pytest.raises(CompileFailure) as caught:
        compile_program(program, empty, operation_contracts=REGISTRY)

    assert caught.value.code == "INVALID_PROGRAM"
    assert caught.value.failures[0].code == "UNKNOWN_OPERATION_CONTRACT"


def test_identity_composition_associativity_and_map_output_preservation() -> None:
    read = _compile(READ, "read")
    qualify = _compile(QUALIFY, "qualify")
    claim = _compile(CLAIM, "claim")
    assert left_identity(read).holds
    assert right_identity(read).holds
    assert normalization_associativity(read, qualify, claim).holds

    transform = TransformRef("material-as-material", "1", _digest("material-transform"))
    mapped = _compile(map_output_node(READ, transform, MATERIAL), "mapped-read")
    assert map_output_preservation(mapped, read, transform).holds


def test_real_specimen_zip_order_is_observable_and_not_commutative() -> None:
    left = _atom("material.read_canonical_ref.v1", "read-document-a", INPUT, MATERIAL)
    right = _atom("material.read_canonical_ref.v1", "read-document-b", INPUT, MATERIAL)
    merge = MergeRef("ordered-material-pair", "1", _digest("ordered-material-pair"))
    zip_registry = _registry(left, right)
    normal = compile_program(
        _spec(zip_ordered_node(left, right, merge), "documents-a-b"),
        zip_registry.catalog,
        operation_contracts=zip_registry,
    )
    reversed_plan = compile_program(
        _spec(zip_ordered_node(right, left, merge), "documents-b-a"),
        zip_registry.catalog,
        operation_contracts=zip_registry,
    )

    result = zip_ordered_noncommutativity(
        normal,
        reversed_plan,
        specimen="two existing project Document rows must retain SourceRef order",
    )
    assert result.holds
    right_effect = next(
        step for step in normal.ordered_steps if step.operation_id == "read-document-b"
    )
    left_terminal = next(
        step for step in normal.ordered_steps if step.operation_id == "read-document-a"
    )
    assert left_terminal.step_id in right_effect.dependencies
    assert ("realization", "SERIAL_FALLBACK") in normal.control_root.attributes


def test_decide_branch_steps_remain_unresolved_and_not_initially_ready() -> None:
    discriminator = DiscriminatorRef("claim-or-gap", "1", _digest("claim-or-gap"))
    left = _atom("material.read_canonical_ref.v1", "branch-claim", INPUT, MATERIAL)
    right = _atom("material.read_canonical_ref.v1", "branch-gap", INPUT, MATERIAL)
    registry = _registry(left, right)
    root = decide_node(
        discriminator,
        (
            DecisionBranch("claim", "kind == 'claim'", left),
            DecisionBranch("gap", "kind == 'gap'", right),
        ),
    )
    plan = compile_program(
        _spec(root, "decision"), registry.catalog, operation_contracts=registry
    )
    branch_steps = [step for step in plan.ordered_steps if step.branch_id]
    assert {
        (step.branch_id, step.guard, step.disposition) for step in branch_steps
    } == {
        ("claim", "kind == 'claim'", "BRANCH_UNRESOLVED"),
        ("gap", "kind == 'gap'", "BRANCH_UNRESOLVED"),
    }
    assert not ({step.step_id for step in branch_steps} & set(plan.ready_order))


def test_frozen_first_specimen_registry_compiles_all_real_contracts() -> None:
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    registry = OperationContractRegistry(catalog, bundle.operations)
    compiled_by_index = {}
    for index, contract in enumerate(registry.contracts):
        operation_id = f"first-specimen-{index}"
        operation = OperationSpec(
            operation_id=operation_id,
            contract_ref=contract.ref,
            input_refs=(_value(operation_id + ":input", contract.input_type),),
            payload_ref=_value(operation_id + ":payload", contract.input_type),
            allowed_overrides=freeze_json_object({}),
        )
        # The AST's false bit is not authoritative; the frozen contract is.
        node = atom_node(operation, contract.input_type, contract.output_type)
        compiled_by_index[index] = compile_program(
            _spec(node, operation_id),
            catalog,
            operation_contracts=registry,
        )
    assert {
        step.operation_contract_ref.kind
        for plan in compiled_by_index.values()
        for step in plan.ordered_steps
        if step.operation_contract_ref
    } == {contract.ref.kind for contract in registry.contracts}
    expected_step_kinds = {
        0: ("EFFECT",),
        1: ("EFFECT",),
        2: ("EFFECT", "ADMISSION"),
        3: ("EFFECT", "ADMISSION"),
        4: ("EFFECT", "ADMISSION"),
        5: ("EFFECT", "ADMISSION"),
    }
    assert {
        index: tuple(
            step.step_kind
            for step in compiled_by_index[index].ordered_steps
            if step.operation_id == f"first-specimen-{index}"
        )
        for index in range(len(registry.contracts))
    } == expected_step_kinds
    for index, contract in enumerate(registry.contracts):
        compiled_steps = tuple(
            step
            for step in compiled_by_index[index].ordered_steps
            if step.operation_id == f"first-specimen-{index}"
        )
        assert compiled_steps
        assert all(
            step.return_contract_ref == contract.return_contract_ref
            for step in compiled_steps
        )


def test_failure_and_return_barrier_survives_plan_composition() -> None:
    qualify = _compile(QUALIFY, "qualify")
    claim = _compile(CLAIM, "claim")
    result = failure_return_barrier_preservation(qualify, claim)
    assert result.holds, result.counterexample
