"""C7.1 shared ProgramSpec/compiler locality and admission-step tests."""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.capabilities.ingest_c7_program import (
    build_ingest_c7_1_program,
)
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.assignments import ReturnContractBinding
from tests.successor_runtime.p4_c7_fixture import (
    PROJECT_KEY,
    REGISTRY_REVISION,
    SCOPE_DIGEST,
    catalog,
    compiled_admission_step,
    compiled_effect_step,
    interpreter_binding,
    program_and_plan,
    runtime_assignment,
    submission,
    verification_binding,
)


def test_c7_1_program_compiles_to_exact_effect_plus_admission_plan() -> None:
    payload = submission()
    program, plan, ref, payload_ref = program_and_plan(payload)
    assert isinstance(program, ProgramSpec)
    assert program.program_digest == program.digest()
    assert plan.program_digest == program.program_digest
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    admission_steps = [
        step for step in plan.ordered_steps if step.step_kind == "ADMISSION"
    ]
    assert len(effect_steps) == 1
    assert len(admission_steps) == 1
    assert effect_steps[0].admission is not None
    assert effect_steps[0].operation_contract_ref.contract_digest == ref.contract_digest
    assert admission_steps[0].admission is not None
    assert admission_steps[0].dependencies == (effect_steps[0].step_id,)
    assert payload_ref.content_digest
    assert payload_ref.project_key == PROJECT_KEY
    assert payload_ref.codec_id == c7.STAGE_CANDIDATE_PAYLOAD_CODEC_ID


def test_c7_1_program_return_contract_requires_admission() -> None:
    program, plan, _ref, _payload_ref = program_and_plan()
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert effect_steps[0].return_contract.admission_required is True
    assert dict(program.metadata)["admission_required"] is True
    assert dict(program.metadata)["return_contract_ref"] == (
        c7.C7_ADMISSION_RETURN_CONTRACT_REF
    )


def test_shadow_program_vocabulary_is_removed() -> None:
    module = __import__(
        "app.successor_runtime.capabilities.ingest_c7_program",
        fromlist=["*"],
    )
    for shadow_name in (
        "ProgramC7",
        "PlanC7",
        "OperationSpecC7",
        "ValueRefC7",
    ):
        assert not hasattr(module, shadow_name)


def test_bundle_has_one_c7_operation_and_payload_codec() -> None:
    bundle = c7.build_ingest_c7_bundle()
    kinds = tuple(operation.ref.kind for operation in bundle.operations)
    assert kinds == (c7.STAGE_CANDIDATE_KIND,)
    assert bundle.codec_by_kind(c7.STAGE_CANDIDATE_KIND)
    assert bundle.profiles["authority"].canonical_owner == c7.C7_INGEST_OWNER


def test_program_rejects_project_drift() -> None:
    payload = submission(project_key="other-project")
    with pytest.raises(ValueError, match="project_key"):
        build_ingest_c7_1_program(
            payload=payload,
            catalog=catalog(),
            program_id="program:p4-c7-drift",
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
        )


def test_runtime_assignment_binds_compiled_effect_step_exactly() -> None:
    program, plan, _ref, _payload_ref = program_and_plan()
    effect_step = compiled_effect_step(plan)
    binding = interpreter_binding(effect_step)
    assignment = runtime_assignment()
    assert assignment.program_digest == program.program_digest
    assert assignment.plan_digest == plan.plan_digest
    assert assignment.step_id == effect_step.step_id
    assert assignment.step_role.value == "EFFECT"
    assert assignment.operation_contract_digest == (
        effect_step.operation_contract_ref.contract_digest
    )
    assert assignment.return_contract_binding == ReturnContractBinding.from_contract(
        effect_step.return_contract_ref,
        effect_step.return_contract,
    )
    assert assignment.handler_binding_digest == binding.binding_digest
    assert assignment.handler_binding.interpreter_profile_digest == (
        c7.build_ingest_c7_bundle().profiles["interpreter"].profile_digest
    )


def test_verification_binding_derives_from_compiled_admission_step() -> None:
    program, plan, _ref, _payload_ref = program_and_plan()
    admission_step = compiled_admission_step(plan)
    binding = verification_binding()
    assert binding.program_digest == program.program_digest
    assert binding.plan_digest == plan.plan_digest
    assert binding.step_id == admission_step.step_id
    assert binding.compiler_identity == plan.compiler_id
    assert binding.interpreter_identity == (
        c7.build_ingest_c7_bundle().profiles["interpreter"].profile_id
    )
    assert binding.canonical_owner == c7.DOCUMENT_CANONICAL_OWNER


def test_c7_1_profile_is_effectful_and_document_owner_is_separate() -> None:
    bundle = c7.build_ingest_c7_bundle()
    profile = bundle.profiles["effect"]
    assert profile.execution_class == "EFFECTFUL"
    assert c7.C7_ADMISSION_RETURN_CONTRACT_REF == (
        "mrw.return.ingest.document-admission.v1"
    )
    assert c7.C7_INGEST_OWNER != c7.DOCUMENT_CANONICAL_OWNER
    assert c7.ADMISSION_WRITE_BOUNDARY
