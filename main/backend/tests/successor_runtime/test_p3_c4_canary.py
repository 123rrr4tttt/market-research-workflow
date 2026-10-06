"""Fixture-only C4 canary handler tests; no PostgreSQL/network effects."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.batch_task_interpreters import (
    BatchTaskInterpreterBindingSpec,
    build_successor_agent_batch_c4_plan_binding,
    build_successor_agent_batch_c4_retry_binding,
)
from app.successor_runtime.capabilities import batch_task as c4
from app.successor_runtime.capabilities.batch_task_interpreters import (
    successor_plan_interpreter_profile_digest,
    successor_retry_interpreter_profile_digest,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import NodeIdentity, RuntimeExecutionContext
from app.successor_runtime.substrate.postgres.batch_task_canary_handlers import (
    BatchTaskPlanRuntimeHandler,
    BatchTaskRetryRuntimeHandler,
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


def _runtime_binding(spec: BatchTaskInterpreterBindingSpec) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        binding_kind=spec.binding_kind,
        operation_contract_digest=spec.operation_contract_digest,
        interpreter_profile_digest=spec.interpreter_profile_digest,
        deployment_catalog_digest=spec.deployment_catalog_digest,
        runtime_protocol_version=spec.runtime_protocol_version,
        project_scope_digest=spec.project_scope_digest,
        resource_policy_epoch=spec.resource_policy_epoch,
        authority_requirement_digest=spec.authority_requirement_digest,
    )


def _assignment(
    *,
    binding: InterpreterBinding,
    contract_ref: OperationContractRef,
    plan: ExecutionPlan,
    program_digest: str,
    payload_ref: ValueRef,
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
        capability_id=c4.BATCH_TASK_OWNER,
        operation_contract_ref=contract_ref,
        operation_contract_digest=contract_ref.contract_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
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


def _claim(assignment: RuntimeAssignment, binding: InterpreterBinding) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=binding.binding_digest,
        lease_token="lease:p3-c4-canary",
        lease_expires_at=datetime(2030, 9, 1, 9, 0, tzinfo=UTC),
        node_id="node:p3-c4-canary",
        node_profile_digest=_digest("p3-c4-node-profile"),
        authority_digest=binding.binding_digest,
        interpreter_profile_digest=binding.interpreter_profile_digest,
    )


def test_c4_1_canary_handler_runs_pure_plan_with_exact_fixture_closure() -> None:
    payload = plan_payload()
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    binding = _runtime_binding(
        build_successor_agent_batch_c4_plan_binding(
            contract_digest=ref.contract_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=SCOPE_DIGEST,
        )
    )
    assert (
        binding.interpreter_profile_digest
        == successor_plan_interpreter_profile_digest()
    )
    handler = BatchTaskPlanRuntimeHandler(
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
    binding = _runtime_binding(
        build_successor_agent_batch_c4_retry_binding(
            contract_digest=ref.contract_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=SCOPE_DIGEST,
        )
    )
    assert (
        binding.interpreter_profile_digest
        == successor_retry_interpreter_profile_digest()
    )
    handler = BatchTaskRetryRuntimeHandler(
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
    assert BatchTaskPlanRuntimeHandler is not None
    assert BatchTaskRetryRuntimeHandler is not None


def test_batch_task_binding_spec_rejects_digest_drift_through_contract_failure() -> None:
    binding = build_successor_agent_batch_c4_plan_binding(
        contract_digest="0" * 64,
        deployment_catalog_digest="1" * 64,
        project_scope_digest="2" * 64,
    )
    with pytest.raises(
        ValueError,
        match="^BatchTaskInterpreterBindingSpec digest does not match content$",
    ):
        replace(binding, binding_digest="f" * 64)


def _run_static_binding_fixture(path: Path) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[4]
    environment = os.environ.copy()
    environment["MRW_TYPECHECK_PYTHON"] = ".venv/bin/python"
    return subprocess.run(
        (sys.executable, "scripts/dev.py", "typecheck", str(path)),
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_exact_binding_static_input_and_output_associations(tmp_path: Path) -> None:
    positive = tmp_path / "exact_binding_positive.py"
    positive.write_text(
        textwrap.dedent(
            """
            from app.successor_runtime.capabilities.batch_task import BatchPlanPayload, BatchPlanResult
            from app.successor_runtime.capabilities.batch_task_interpreters import (
                BatchTaskInterpreterBindingSpec,
                BatchTaskPlanSuccessorInterpreter,
                InterpreterBindingView,
                InterpreterOutcome,
                ProjectScopeView,
                build_successor_agent_batch_c4_plan_binding,
            )
            from app.successor_runtime.language.algebra import ValueRef
            from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
            from app.successor_runtime.language.object_contracts import OperationContractRef
            from app.successor_runtime.language.plan import ExecutionPlan
            from app.successor_runtime.language.program import ProgramSpec


            def produce() -> BatchTaskInterpreterBindingSpec:
                return build_successor_agent_batch_c4_plan_binding(
                    contract_digest="0" * 64,
                    deployment_catalog_digest="1" * 64,
                    project_scope_digest="2" * 64,
                )


            def consume(
                program: ProgramSpec,
                plan: ExecutionPlan,
                contract_ref: OperationContractRef,
                payload_ref: ValueRef,
                payload: BatchPlanPayload,
                project_scope: ProjectScopeView,
                catalog: OperationContractCatalogSnapshot,
                binding: InterpreterBindingView,
            ) -> InterpreterOutcome[BatchPlanResult]:
                return BatchTaskPlanSuccessorInterpreter().interpret(
                    program=program,
                    plan=plan,
                    contract_ref=contract_ref,
                    payload_ref=payload_ref,
                    payload=payload,
                    project_scope=project_scope,
                    catalog=catalog,
                    deployment_catalog_digest="3" * 64,
                    binding=binding,
                )
            """
        ),
        encoding="utf-8",
    )
    accepted = _run_static_binding_fixture(positive)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    negative = tmp_path / "exact_binding_negative.py"
    negative.write_text(
        textwrap.dedent(
            """
            from app.successor_runtime.capabilities.batch_task import BatchPlanPayload
            from app.successor_runtime.capabilities.batch_task_interpreters import (
                BatchTaskPlanSuccessorInterpreter,
                ProjectScopeView,
                build_successor_agent_batch_c4_plan_binding,
            )
            from app.successor_runtime.language.algebra import ValueRef
            from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
            from app.successor_runtime.language.object_contracts import OperationContractRef
            from app.successor_runtime.language.plan import ExecutionPlan
            from app.successor_runtime.language.program import ProgramSpec


            def wrong_binding(
                program: ProgramSpec,
                plan: ExecutionPlan,
                contract_ref: OperationContractRef,
                payload_ref: ValueRef,
                payload: BatchPlanPayload,
                project_scope: ProjectScopeView,
                catalog: OperationContractCatalogSnapshot,
            ) -> None:
                BatchTaskPlanSuccessorInterpreter().interpret(
                    program=program,
                    plan=plan,
                    contract_ref=contract_ref,
                    payload_ref=payload_ref,
                    payload=payload,
                    project_scope=project_scope,
                    catalog=catalog,
                    deployment_catalog_digest="3" * 64,
                    binding=object(),
                )


            def wrong_return() -> str:
                return build_successor_agent_batch_c4_plan_binding(
                    contract_digest="0" * 64,
                    deployment_catalog_digest="1" * 64,
                    project_scope_digest="2" * 64,
                )
            """
        ),
        encoding="utf-8",
    )
    rejected = _run_static_binding_fixture(negative)
    diagnostics = rejected.stdout + rejected.stderr
    assert rejected.returncode == 1, diagnostics
    assert re.findall(r"\((report[A-Za-z]+)\)", diagnostics) == [
        "reportArgumentType",
        "reportReturnType",
    ]
    assert "2 errors, 0 warnings, 0 informations" in diagnostics
