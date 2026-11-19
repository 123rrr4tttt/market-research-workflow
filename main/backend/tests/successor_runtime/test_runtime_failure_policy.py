from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.language.plan import (
    CompiledControlNode,
    CompiledStep,
    CompletionPolicy,
    ExecutionPlan,
    FrozenDependencyIndex,
    PlanReturnPolicy,
    ProgramPlanSourceMap,
    with_plan_digest,
)
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.research.object_types import INQUIRY_TYPE
from app.successor_runtime.runtime.failure_policy import (
    FailureContinuation,
    FailurePolicyDerivationError,
    RunFailureDecision,
    derive_failure_policy,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.qualification import (
    AuthorityContext,
    AuthoritySourceBinding,
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.substrate.postgres.failure_policy import (
    PersistedFailurePolicyError,
    PostgresFailurePolicyLoader,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactQualificationBinding,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


PROJECT_KEY = "p0c-failure-policy"
PROJECT_SCHEMA = "mrw_p0c_failure_policy"
RUN_ID = "run:failure-policy"
SCOPE_DIGEST = _digest("scope")
SCOPE = RuntimeScope(
    project_scope=ProjectScopeRef(
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        project_registry_revision=7,
        incarnation="project-incarnation-7",
        scope_digest=SCOPE_DIGEST,
    ),
    actor_id="runtime:failure-policy",
)


@dataclass(frozen=True, slots=True)
class _Fixture:
    plan: ExecutionPlan
    qualified: QualifiedPlan
    qualification: ExactQualificationBinding


def _step(
    step_id: str,
    *,
    contract_ref: OperationContractRef,
    failure_modes: tuple[str, ...] = ("FAILED",),
    failure_profile_ref: str | None = "failure:test:v1",
) -> CompiledStep:
    return CompiledStep(
        step_id=step_id,
        step_kind="EFFECT",
        source_path=("root", step_id),
        input_type=INQUIRY_TYPE,
        output_type=INQUIRY_TYPE,
        dependencies=(),
        operation_id=f"operation:{step_id}",
        operation_contract_ref=contract_ref,
        transform_ref=None,
        effect_profile_ref="effect:test:v1",
        resource_profile_ref="resource:test:v1",
        failure_profile_ref=failure_profile_ref,
        authority_profile_ref="authority:test:v1",
        return_contract=ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=failure_modes,
            admission_required=False,
            wait_modes=("WAIT",),
            cancel_modes=("CANCELED",),
        ),
        semantic_return_barrier=step_id == "required",
        staged_output_only=False,
        return_contract_ref="return:test:v1",
    )


def _authorization(step: CompiledStep) -> StepAuthorizationBinding:
    assert step.operation_contract_ref is not None
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="scope:failure-policy",
        source_digest=SCOPE_DIGEST,
        source_epoch=7,
    )
    return StepAuthorizationBinding.from_content(
        run_id=RUN_ID,
        step_id=step.step_id,
        operation_kind=step.operation_contract_ref.kind,
        operation_contract_digest=step.operation_contract_ref.contract_digest,
        capability_id=f"capability:{step.step_id}",
        claim_owner="successor",
        claim_authority_epoch=3,
        claim_policy_digest=_digest(f"claim:{step.step_id}"),
        payload_digest=_digest(f"payload:{step.step_id}"),
        actor_id=SCOPE.actor_id,
        project_key=PROJECT_KEY,
        project_registry_revision=SCOPE.project_scope.project_registry_revision,
        project_scope_digest=SCOPE_DIGEST,
        interpreter_binding_digest=_digest(f"interpreter:{step.step_id}"),
        deployment_catalog_digest=_digest("deployment"),
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        resource_ceiling_digest=_digest("ceiling"),
        resource_policy_epoch=5,
        queue_eligibility_digest=_digest(f"queue:{step.step_id}"),
        grant_epoch=2,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        canonical_base_revision=0,
        canonical_incarnation="canonical-incarnation-1",
    )


def _fixture(
    *,
    required_failure_modes: tuple[str, ...] = ("FAILED",),
    plan_failure_modes: tuple[str, ...] = ("FAILED",),
    failure_profile_ref: str | None = "failure:test:v1",
) -> _Fixture:
    optional_ref = OperationContractRef(
        "test.optional.v1", "1.0.0", _digest("optional-contract")
    )
    required_ref = OperationContractRef(
        "test.required.v1", "1.0.0", _digest("required-contract")
    )
    optional = _step("optional", contract_ref=optional_ref)
    required = _step(
        "required",
        contract_ref=required_ref,
        failure_modes=required_failure_modes,
        failure_profile_ref=failure_profile_ref,
    )
    source_digest = _digest("failure-policy-control")
    control = CompiledControlNode(
        control_id="control:failure-policy",
        node_kind="zip_ordered",
        source_path=("root",),
        input_type=INQUIRY_TYPE,
        output_type=INQUIRY_TYPE,
        children=(),
        step_ids=(optional.step_id, required.step_id),
        semantic_return_step_ids=(required.step_id,),
        source_digest=source_digest,
    )
    plan = with_plan_digest(
        ExecutionPlan(
            plan_id="plan:failure-policy",
            program_id="program:failure-policy",
            program_digest=_digest("program"),
            input_type=INQUIRY_TYPE,
            output_type=INQUIRY_TYPE,
            compiler_id="compiler:test",
            compiler_version="1.0.0",
            control_root=control,
            ordered_steps=(optional, required),
            dependency_index=FrozenDependencyIndex(
                ((optional.step_id, ()), (required.step_id, ()))
            ),
            ready_order=(optional.step_id, required.step_id),
            source_map=(
                ProgramPlanSourceMap(
                    source_path=("root",),
                    source_kind="zip_ordered",
                    source_digest=source_digest,
                    control_id=control.control_id,
                    step_ids=(optional.step_id, required.step_id),
                    semantic_return_step_ids=(required.step_id,),
                ),
            ),
            return_policy=PlanReturnPolicy(
                success_modes=("SUCCEEDED",),
                failure_modes=plan_failure_modes,
                wait_modes=("WAIT",),
                cancel_modes=("CANCELED",),
                exported_barrier_step_ids=(required.step_id,),
            ),
            completion_policy=CompletionPolicy(),
            effect_closure_digest=_digest("effects"),
            authority_closure_digest=_digest("authority"),
            resource_closure_digest=_digest("resources"),
            plan_digest="",
        )
    )
    authorizations = tuple(_authorization(step) for step in plan.ordered_steps)
    source = authorizations[0].authority_source_bindings[0]
    context = AuthorityContext.from_content(
        actor_id=SCOPE.actor_id,
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        project_registry_revision=SCOPE.project_scope.project_registry_revision,
        project_scope_digest=SCOPE_DIGEST,
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        grant_epoch=2,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        operation_scope_digest=_digest("operation-scope"),
        resource_ceiling_digest=_digest("ceiling"),
        canonical_base_revision=0,
        canonical_incarnation="canonical-incarnation-1",
    )
    qualified = QualifiedPlan.from_content(
        plan_digest=plan.plan_digest,
        authority_context_digest=context.context_digest,
        step_bindings=authorizations,
    )
    qualification = ExactQualificationBinding.from_content(
        qualification_id="qualification:failure-policy",
        project_key=PROJECT_KEY,
        run_id=RUN_ID,
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        authority_context=context,
        authority_context_digest=context.context_digest,
        qualified_plan=qualified,
        decision="QUALIFIED",
    )
    return _Fixture(plan, qualified, qualification)


def test_required_failure_is_fatal_from_exact_barrier_closure() -> None:
    fixture = _fixture()
    decision = derive_failure_policy(fixture.plan, fixture.qualified, "required")

    assert decision.qualified is True
    assert decision.required is True
    assert decision.fatal is True
    assert decision.may_continue is False
    assert decision.continuation is FailureContinuation.NONE
    assert decision.run_decision is RunFailureDecision.REQUIRED_STEP_FAILED
    assert decision.emit_required_step_failed is True
    assert decision.required_step_ids == ("required",)
    assert len(decision.decision_digest) == 64


def test_qualified_optional_failure_continues_without_run_failure() -> None:
    fixture = _fixture()
    decision = derive_failure_policy(fixture.plan, fixture.qualified, "optional")

    assert decision.qualified is True
    assert decision.required is False
    assert decision.fatal is False
    assert decision.may_continue is True
    assert decision.continuation is FailureContinuation.NONE
    assert decision.run_decision is RunFailureDecision.CONTINUE
    assert decision.emit_required_step_failed is False


def test_exported_barrier_dependency_is_required() -> None:
    fixture = _fixture()
    optional, required = fixture.plan.ordered_steps
    required = replace(required, dependencies=(optional.step_id,))
    plan = with_plan_digest(
        replace(
            fixture.plan,
            ordered_steps=(optional, required),
            dependency_index=FrozenDependencyIndex(
                ((optional.step_id, ()), (required.step_id, (optional.step_id,)))
            ),
            plan_digest="",
        )
    )
    qualified = QualifiedPlan.from_content(
        plan_digest=plan.plan_digest,
        authority_context_digest=fixture.qualified.authority_context_digest,
        step_bindings=fixture.qualified.step_bindings,
    )

    decision = derive_failure_policy(plan, qualified, "optional")

    assert decision.required_step_ids == ("optional", "required")
    assert decision.required is True
    assert decision.emit_required_step_failed is True


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("RETRY", FailureContinuation.RETRY),
        ("FALLBACK", FailureContinuation.FALLBACK),
        ("PARTIAL_RESULT", FailureContinuation.PARTIAL_RESULT),
        ("ERROR_ACCUMULATION", FailureContinuation.ERROR_ACCUMULATION),
        (
            "SUCCESSOR_MATERIALIZATION",
            FailureContinuation.SUCCESSOR_MATERIALIZATION,
        ),
    ),
)
def test_required_continuation_policy_never_auto_fails_run(
    mode: str, expected: FailureContinuation
) -> None:
    fixture = _fixture(required_failure_modes=("FAILED", mode))
    decision = derive_failure_policy(fixture.plan, fixture.qualified, "required")

    assert decision.required is True
    assert decision.fatal is False
    assert decision.may_continue is True
    assert decision.continuation is expected
    assert decision.requires_explicit_control is True
    assert decision.run_decision is RunFailureDecision.CONTINUE


def test_missing_or_drifted_policy_evidence_fails_closed() -> None:
    fixture = _fixture()
    missing = QualifiedPlan.from_content(
        plan_digest=fixture.plan.plan_digest,
        authority_context_digest=fixture.qualified.authority_context_digest,
        step_bindings=(fixture.qualified.step_bindings[0],),
    )
    with pytest.raises(
        FailurePolicyDerivationError,
        match="membership differs",
    ):
        derive_failure_policy(fixture.plan, missing, "required")

    drifted = replace(fixture.plan, plan_digest="0" * 64)
    with pytest.raises(FailurePolicyDerivationError, match="structural digest drift"):
        derive_failure_policy(drifted, fixture.qualified, "required")

    unsupported_policy = with_plan_digest(
        replace(
            fixture.plan,
            completion_policy=CompletionPolicy(mode="CALLER_BOOLEAN"),
            plan_digest="",
        )
    )
    unsupported_qualification = QualifiedPlan.from_content(
        plan_digest=unsupported_policy.plan_digest,
        authority_context_digest=fixture.qualified.authority_context_digest,
        step_bindings=fixture.qualified.step_bindings,
    )
    with pytest.raises(FailurePolicyDerivationError, match="CompletionPolicy"):
        derive_failure_policy(
            unsupported_policy,
            unsupported_qualification,
            "required",
        )


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[list[dict[str, Any]]]) -> None:
        self._rows = list(rows)

    def execute(self, _statement: object) -> _Rows:
        if not self._rows:
            raise AssertionError("unexpected loader query")
        return _Rows(self._rows.pop(0))


def _loader_rows(
    fixture: _Fixture,
    *,
    project_plan_drift: bool = False,
) -> list[list[dict[str, Any]]]:
    scope = SCOPE.project_scope
    registry = {
        "project_key": PROJECT_KEY,
        "registry_revision": scope.project_registry_revision,
        "resolved_schema": scope.resolved_schema,
        "scope_digest": scope.scope_digest,
        "incarnation": scope.incarnation,
        "state": "ACTIVE",
    }
    run = {
        "run_id": RUN_ID,
        "project_key": PROJECT_KEY,
        "project_registry_revision": scope.project_registry_revision,
        "project_scope_digest": scope.scope_digest,
        "resolved_schema": scope.resolved_schema,
        "program_id": fixture.plan.program_id,
        "program_digest": fixture.plan.program_digest,
        "plan_id": fixture.plan.plan_id,
        "plan_digest": fixture.plan.plan_digest,
        "qualification_digest": fixture.qualified.qualification_digest,
    }
    common_plan = {
        "project_key": PROJECT_KEY,
        "plan_id": fixture.plan.plan_id,
        "plan_digest": fixture.plan.plan_digest,
        "program_id": fixture.plan.program_id,
        "program_digest": fixture.plan.program_digest,
        "compiler_id": fixture.plan.compiler_id,
        "compiler_version": fixture.plan.compiler_version,
        "operation_catalog_id": "catalog:test",
        "catalog_version": "1.0.0",
        "catalog_digest": _digest("catalog"),
        "effect_closure_digest": fixture.plan.effect_closure_digest,
        "authority_closure_digest": fixture.plan.authority_closure_digest,
        "resource_closure_digest": fixture.plan.resource_closure_digest,
    }
    public_plan = {**common_plan, "project_storage_ref": "plan:failure-policy"}
    project_plan = {
        **common_plan,
        "plan_json": json.loads(canonical_bytes(fixture.plan)),
    }
    if project_plan_drift:
        project_plan["catalog_digest"] = _digest("drifted-catalog")
    binding = fixture.qualification
    qualification = {
        "qualification_id": binding.qualification_id,
        "project_key": binding.project_key,
        "run_id": binding.run_id,
        "plan_id": binding.plan_id,
        "plan_digest": binding.plan_digest,
        "authority_context_digest": binding.authority_context_digest,
        "decision": binding.decision,
        "qualification_digest": binding.qualified_plan.qualification_digest,
        "qualification_binding_digest": binding.qualification_binding_digest,
        "qualified_plan_json": binding.qualified_plan.model_dump(mode="json"),
        "qualification_binding_json": binding.model_dump(mode="json"),
    }
    return [[registry], [run], [public_plan], [project_plan], [qualification]]


def test_postgres_loader_proves_exact_scope_plan_and_qualification() -> None:
    fixture = _fixture()
    node_scope = RuntimeScope(
        project_scope=SCOPE.project_scope,
        actor_id="runtime-node:failure-policy",
    )
    loader = PostgresFailurePolicyLoader(
        _Connection(_loader_rows(fixture)),  # type: ignore[arg-type]
        node_scope,
    )

    decision = loader.load(RUN_ID, "required")

    assert decision.emit_required_step_failed is True
    assert decision.plan_digest == fixture.plan.plan_digest
    assert decision.qualification_digest == fixture.qualified.qualification_digest


def test_postgres_loader_missing_or_cross_store_drift_fails_closed() -> None:
    fixture = _fixture()
    missing_run = _loader_rows(fixture)[:1] + [[]]
    with pytest.raises(PersistedFailurePolicyError, match="runtime run"):
        PostgresFailurePolicyLoader(
            _Connection(missing_run),  # type: ignore[arg-type]
            SCOPE,
        ).load(RUN_ID, "required")

    with pytest.raises(
        PersistedFailurePolicyError,
        match="public/project ExecutionPlan ref drift",
    ):
        PostgresFailurePolicyLoader(
            _Connection(_loader_rows(fixture, project_plan_drift=True)),  # type: ignore[arg-type]
            SCOPE,
        ).load(RUN_ID, "required")
