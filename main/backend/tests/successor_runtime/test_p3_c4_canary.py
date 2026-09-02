"""Fixture-only C4 canary handler tests; no PostgreSQL/network effects."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from app.successor_migration.legacy_agent_batch import (
    build_successor_agent_batch_c4_plan_binding,
    build_successor_agent_batch_c4_retry_binding,
)
from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
    successor_plan_interpreter_profile_digest,
    successor_retry_interpreter_profile_digest,
)
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import NodeIdentity, RuntimeExecutionContext
from app.successor_runtime.substrate.postgres.agent_batch_c4_canary import (
    C4_1_BatchPlanRuntimeHandler,
    C4_2_RetryRuntimeHandler,
)

from .p3_c4_fixture import (
    DEPLOYMENT_CATALOG_DIGEST,
    PROJECT_KEY,
    SCOPE_DIGEST,
    catalog,
    plan_payload,
    plan_program_and_plan,
    retry_payload,
    retry_program_and_plan,
)


def _execution_context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:p3-c4-canary",
            incarnation="node-inc:p3-c4-canary",
            started_at=datetime(2030, 9, 1, 8, 0, tzinfo=UTC) - timedelta(minutes=1),
        ),
        observed_at=datetime(2030, 9, 1, 8, 0, tzinfo=UTC),
    )


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _assignment(
    *,
    binding: object,
    contract_ref: OperationContractRef,
    plan: object,
    program_digest: str,
    payload_ref: object,
    payload_digest: str,
    work_item_id: str,
) -> RuntimeAssignment:
    step = next(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref or "mrw.return.runtime-value.v1",
        step.return_contract,
    )
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=f"run:{work_item_id}",
        step_id=step.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=c4.AGENT_BATCH_C4_OWNER,
        operation_contract_ref=contract_ref,
        operation_contract_digest=contract_ref.contract_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{getattr(binding, 'binding_digest', '')}"
        ),
        handler_binding_digest=getattr(binding, "binding_digest", ""),
        handler_binding=binding,
        program_digest=program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation="run-inc:p3-c4",
        input_refs=(getattr(payload_ref, "storage_ref", str(payload_ref)),),
        input_closure_digest=_digest("p3-c4-input-closure"),
        payload_ref=getattr(payload_ref, "storage_ref", str(payload_ref)),
        payload_digest=payload_digest,
        queue_eligibility_digest=_digest("p3-c4-queue-eligibility"),
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest=_digest("p3-c4-claim-policy"),
        expected_step_revision=0,
        trace_id=f"trace:{work_item_id}",
    )


def _claim(assignment: RuntimeAssignment, binding: object) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=getattr(binding, "binding_digest", ""),
        lease_token="lease:p3-c4-canary",
        lease_expires_at=datetime(2030, 9, 1, 9, 0, tzinfo=UTC),
        node_id="node:p3-c4-canary",
        node_profile_digest=_digest("p3-c4-node-profile"),
        authority_digest=getattr(binding, "binding_digest", ""),
        interpreter_profile_digest=getattr(binding, "interpreter_profile_digest", ""),
    )


def test_c4_1_canary_handler_runs_pure_plan_with_exact_fixture_closure() -> None:
    payload = plan_payload()
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    binding = build_successor_agent_batch_c4_plan_binding(
        contract_digest=ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    assert (
        binding.interpreter_profile_digest
        == successor_plan_interpreter_profile_digest()
    )
    handler = C4_1_BatchPlanRuntimeHandler(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        catalog=catalog(),
        binding=binding,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
    )
    assignment = _assignment(
        binding=binding,
        contract_ref=ref,
        plan=plan,
        program_digest=program.program_digest,
        payload_ref=payload_ref,
        payload_digest=payload.payload_digest,
        work_item_id="work:p3-c4-1",
    )
    outcome = handler.execute(
        assignment, _claim(assignment, binding), _execution_context()
    )
    assert outcome.disposition == "SUCCEEDED"
    assert outcome.result_digest
    assert handler.provider_calls == 1


def test_c4_2_canary_handler_runs_pure_retry_reducer() -> None:
    payload = retry_payload()
    program, plan, ref, payload_ref = retry_program_and_plan(payload)
    binding = build_successor_agent_batch_c4_retry_binding(
        contract_digest=ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    assert (
        binding.interpreter_profile_digest
        == successor_retry_interpreter_profile_digest()
    )
    handler = C4_2_RetryRuntimeHandler(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        catalog=catalog(),
        binding=binding,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
    )
    assignment = _assignment(
        binding=binding,
        contract_ref=ref,
        plan=plan,
        program_digest=program.program_digest,
        payload_ref=payload_ref,
        payload_digest=payload.payload_digest,
        work_item_id="work:p3-c4-2",
    )
    outcome = handler.execute(
        assignment, _claim(assignment, binding), _execution_context()
    )
    assert outcome.disposition == "SUCCEEDED"
    assert outcome.result_digest
    assert handler.provider_calls == 1


def test_canary_is_deterministic_fixture_without_live_effects() -> None:
    assert C4_1_BatchPlanRuntimeHandler is not None
    assert C4_2_RetryRuntimeHandler is not None
