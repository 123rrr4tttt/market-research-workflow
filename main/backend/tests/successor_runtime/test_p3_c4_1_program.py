"""C4 Program/compiler locality and the integrated STATIC_SHAPE traversal."""

from __future__ import annotations

import dataclasses

import pytest

from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities.agent_batch_c4 import (
    build_agent_batch_c4_bundle,
)
from app.successor_runtime.capabilities.agent_batch_c4_program import (
    build_agent_batch_c4_1_program,
    build_agent_batch_c4_1_traversal_program,
    traversal_shape_binding,
)
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.compile import CompileFailure, compile_program
from app.successor_runtime.language.program import ProgramSpec, traverse_ordered_node

from .p3_c4_fixture import (
    PROJECT_KEY,
    REGISTRY_REVISION,
    SCOPE_DIGEST,
    catalog,
    plan_payload,
    plan_program_and_plan,
    registry,
)


def test_c4_1_program_compiles_to_one_effect_step() -> None:
    payload = plan_payload()
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    assert program.program_digest == program.digest()
    assert plan.program_digest == program.program_digest
    assert plan.input_type.type_id == c4.BATCH_PLAN_PAYLOAD_TYPE.type_id
    assert plan.output_type.type_id == c4.BATCH_PLAN_RESULT_TYPE.type_id
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    assert effect_steps[0].operation_contract_ref.contract_digest == ref.contract_digest
    assert payload_ref.content_digest
    assert payload_ref.project_key == PROJECT_KEY
    assert payload_ref.codec_id == c4.BATCH_PLAN_PAYLOAD_CODEC_ID


def test_c4_2_program_compiles_to_one_effect_step() -> None:
    from .p3_c4_fixture import retry_payload, retry_program_and_plan

    payload = retry_payload()
    program, plan, ref, _payload_ref = retry_program_and_plan(payload)
    assert plan.program_digest == program.program_digest
    assert plan.input_type.type_id == c4.RETRY_REDUCER_PAYLOAD_TYPE.type_id
    assert plan.output_type.type_id == c4.RETRY_TRANSITION_TYPE.type_id
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    assert effect_steps[0].operation_contract_ref.contract_digest == ref.contract_digest


def test_c4_1_static_shape_traversal_program_compiles_with_exact_metadata() -> None:
    payload = plan_payload()
    binding = traversal_shape_binding([payload])
    assert binding["traversal_element_count"] == 1
    assert len(binding["traversal_shape_digest"]) == 64

    program = build_agent_batch_c4_1_traversal_program(
        payloads=[payload],
        catalog=catalog(),
        program_id="program:p3-c4-traverse",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    metadata = dict(program.metadata)
    from app.successor_runtime.language.plan import (
        traversal_shape_digest as shared_digest,
    )

    assert metadata["traversal_shape_digest"] == binding["traversal_shape_digest"]
    assert metadata["traversal_element_count"] == binding["traversal_element_count"]
    assert binding["traversal_shape_digest"] == shared_digest(
        (dataclasses.asdict(payload),)
    )
    assert program.root.node_kind == "traverse_ordered"
    assert program.root.traversal_policy == "STATIC_SHAPE"

    plan = compile_program(program, catalog(), operation_contracts=registry())
    transform_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "TRANSFORM" and step.transform_ref is not None
    ]
    assert len(transform_steps) == 1
    assert transform_steps[0].transform_ref.label() == (
        "mrw.traverse_ordered.materialize@1.0.0"
    )
    assert transform_steps[0].effect_profile_ref == "PURE_TRANSFORM"
    assert plan.plan_digest
    assert plan.control_root.node_kind == "traverse_ordered"
    attrs = dict(plan.control_root.attributes)
    assert attrs["traversal_policy"] == "STATIC_SHAPE"
    assert attrs["static_shape_digest"] == binding["traversal_shape_digest"]
    assert attrs["static_element_count"] == str(binding["traversal_element_count"])


def test_static_shape_traversal_without_exact_metadata_fails_closed() -> None:
    payload = plan_payload()
    atom_program = build_agent_batch_c4_1_program(
        payload=payload,
        catalog=catalog(),
        program_id="program:p3-c4-traverse-no-binding",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    traverse = traverse_ordered_node(
        element_program=atom_program.root,
        traversal_policy="STATIC_SHAPE",
    )
    blocked = ProgramSpec(
        program_id="program:p3-c4-traverse-no-binding",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        semantic_identity="agent-batch.build-batch-plan-traverse",
        input_type=traverse.input_type,
        output_type=traverse.output_type,
        root=traverse,
        algebra_refs=atom_program.algebra_refs,
        transform_refs=(),
        observation_profile="mrw.successor.agent-batch.c4-1.observation.v1",
        metadata=freeze_json_object({}),
        program_digest="",
    ).with_digest()
    with pytest.raises(CompileFailure) as excinfo:
        compile_program(blocked, catalog(), operation_contracts=registry())
    assert excinfo.value.code == "TRAVERSAL_SHAPE_BINDING_REQUIRED"


def test_bundle_has_three_c4_operations_and_submission_codec() -> None:
    bundle = build_agent_batch_c4_bundle()
    kinds = tuple(operation.ref.kind for operation in bundle.operations)
    assert kinds == (
        c4.BATCH_PLAN_KIND,
        c4.RETRY_REDUCE_KIND,
        c4.SUBMISSION_KIND,
    )
    assert bundle.codec_by_kind(c4.BATCH_PLAN_KIND)
    assert bundle.codec_by_kind(c4.RETRY_REDUCE_KIND)
    assert bundle.codec_by_kind(c4.SUBMISSION_KIND).payload_type_id == (
        c4.SUBMISSION_TYPE.type_id
    )
