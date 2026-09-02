from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    CompilerBinding,
    HandlerBindingKind,
    InterpreterBinding,
    QualificationBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.qualification import (
    AuthorityContext,
    AuthoritySourceBinding,
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.reducer import (
    RunSnapshot,
    StepSnapshot,
    reduce_run_event,
    reduce_step,
)
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    IllegalTransition,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.qualification_store import (
    QualificationStoreRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactQualificationBinding,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    ActivateQualification,
    AssignmentEnvelope,
    AttachPlan,
    ClaimedLifecycle,
    EffectTerminalKind,
    RuntimeLifecycleRepository,
    SubmitRun,
    TerminalOutcome,
    _assignment_values,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.staged_artifacts import (
    StagedArtifactBinding,
    StagedArtifactRepository,
)


def _digest(label: str) -> str:
    return canonical_digest((label,))


@pytest.fixture
def scope() -> RuntimeScope:
    return RuntimeScope(
        ProjectScopeRef(
            project_key="project-a",
            resolved_schema="project_a",
            project_registry_revision=3,
            incarnation="project-incarnation-3",
            scope_digest=_digest("scope"),
        ),
        actor_id="actor-a",
    )


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one_or_none(self):
        if len(self.rows) > 1:
            raise AssertionError("test result expected at most one row")
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Result:
    def __init__(
        self, rows: list[dict[str, Any]] | None = None, *, rowcount: int = 1
    ) -> None:
        self._rows = [] if rows is None else rows
        self.rowcount = rowcount

    def mappings(self):
        return _Mappings(self._rows)


def _insert_values(statement: Insert) -> dict[str, Any]:
    return {
        str(column): bind.value
        for column, bind in statement._values.items()  # type: ignore[attr-defined]
    }


class _StoreConnection:
    """Tiny deterministic repository unit boundary; no database is contacted."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.statements: list[Any] = []

    def execute(self, statement):
        self.statements.append(statement)
        table = (
            statement.get_final_froms()[0].name
            if isinstance(statement, Select)
            else statement.table.name
        )
        if isinstance(statement, Select):
            return _Result(self.rows.get(table, []))
        if isinstance(statement, Insert):
            self.rows.setdefault(table, []).append(_insert_values(statement))
            return _Result(rowcount=1)
        return _Result(rowcount=1)


class _AllowCurrentTerminalAuthority:
    def require_current(self, **_kwargs: object) -> None:
        return None


class _AllowTerminalFailures:
    def verify_exact(self, *_args: object, **_kwargs: object) -> object:
        return object()


@dataclass(frozen=True)
class _FailurePolicyDecision:
    emit_required_step_failed: bool
    decision_digest: str


class _StaticFailurePolicy:
    def __init__(self, *, required: bool) -> None:
        self.required = required

    def load_decision(self, _run_id: str, _step_id: str) -> _FailurePolicyDecision:
        return _FailurePolicyDecision(
            emit_required_step_failed=self.required,
            decision_digest=_digest(
                "required-failure-policy"
                if self.required
                else "optional-failure-policy"
            ),
        )


def test_runtime_value_index_and_staged_artifact_store_only_opaque_refs(scope) -> None:
    connection = _StoreConnection()
    value = RuntimeValueBinding(
        value_id="value-1",
        object_type="CapturedMaterialSnapshot.v1",
        codec_id="json.v1",
        content_digest=_digest("content"),
        byte_size=42,
        storage_digest=_digest("storage"),
        project_value_ref="project-value:value-1",
    )
    stored = RuntimeValueRepository(connection, scope).put_exact(value)
    assert stored["project_value_ref"] == "project-value:value-1"
    assert "content_bytes" not in stored and "content_json" not in stored

    artifact = StagedArtifactBinding(
        artifact_id="artifact-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        value_id="value-1",
        qualifier_ref="qualifier:standard",
    )
    staged = StagedArtifactRepository(connection, scope).stage(artifact)
    assert staged["state"] == "STAGED"
    assert staged["value_id"] == "value-1"

    with pytest.raises(ValueError, match="exactly one"):
        RuntimeValueBinding(
            value_id="bad",
            object_type="X",
            codec_id="json.v1",
            content_digest=_digest("bad"),
            byte_size=1,
            storage_digest=_digest("bad-storage"),
            project_value_ref="project-value:bad",
            runtime_blob_ref="runtime-blob:bad",
        )


def test_submit_and_attach_plan_are_caller_transaction_command_packets(scope) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    compiler = CompilerBinding.from_content(
        compiler_id="compiler",
        compiler_version="1",
        compiler_digest=_digest("compiler"),
        operation_catalog_digest=_digest("operation-catalog"),
        domain_contract_snapshot_digest=_digest("domain-contract"),
    )
    compile_assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="compile-work",
        assignment_kind=AssignmentKind.COMPILE,
        project_key="project-a",
        run_id="run-submit",
        capability_id="compile",
        handler_binding_kind=HandlerBindingKind.COMPILER,
        handler_binding_ref=f"handler-binding:sha256:{compiler.binding_digest}",
        handler_binding_digest=compiler.binding_digest,
        handler_binding=compiler,
        program_digest=_digest("submitted-program"),
        deployment_catalog_digest=_digest("catalog"),
        execution_epoch=0,
        incarnation="run-submit-incarnation",
        queue_eligibility_digest=_digest("compile-eligibility"),
        resource_policy_epoch=0,
        claim_authority_epoch=1,
        claim_policy_digest=_digest("compile-claim-policy"),
        trace_id="trace-submit",
    )
    connection = _StoreConnection()
    repository = RuntimeLifecycleRepository(connection, scope)
    submitted = repository.submit(
        SubmitRun(
            run_id="run-submit",
            incarnation="run-submit-incarnation",
            program_id="program-submit",
            program_digest=compile_assignment.program_digest,
            program_storage_ref="project-value:program-submit",
            contract_version="1",
            submission_authority_digest=_digest("submit-authority"),
            compile_work=AssignmentEnvelope(
                assignment=compile_assignment,
                required_node_profile_selector=_digest("node-profile"),
                authority_digest=_digest("submit-authority"),
                resource_policy_digest=_digest("compile-policy"),
                fairness_key="project-a",
            ),
            due_at=now,
        )
    )
    assert submitted["state"] == "SUBMITTED"
    assert set(connection.rows) >= {
        "runtime_program_refs",
        "runtime_runs",
        "runtime_events",
        "runtime_work_items",
    }

    run_row = connection.rows["runtime_runs"][0]
    run_row.update(state="COMPILING", revision=1, next_event_seq=2)
    qualification_handler = QualificationBinding.from_content(
        authority_reader_id="authority-reader",
        authority_reader_version="1",
        authority_reader_digest=_digest("authority-reader"),
        deployment_catalog_digest=_digest("catalog"),
        resource_policy_epoch=4,
    )
    qualify_assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="qualify-work",
        assignment_kind=AssignmentKind.QUALIFY,
        project_key="project-a",
        run_id="run-submit",
        capability_id="qualify",
        handler_binding_kind=HandlerBindingKind.QUALIFICATION,
        handler_binding_ref=(
            f"handler-binding:sha256:{qualification_handler.binding_digest}"
        ),
        handler_binding_digest=qualification_handler.binding_digest,
        handler_binding=qualification_handler,
        program_digest=compile_assignment.program_digest,
        plan_digest=_digest("submitted-plan"),
        deployment_catalog_digest=_digest("catalog"),
        execution_epoch=0,
        incarnation="run-submit-incarnation",
        queue_eligibility_digest=_digest("qualify-eligibility"),
        resource_policy_epoch=4,
        claim_authority_epoch=1,
        claim_policy_digest=_digest("qualify-claim-policy"),
        trace_id="trace-qualify",
    )
    attached = repository.attach_plan(
        AttachPlan(
            run_id="run-submit",
            expected_run_revision=1,
            plan_id="plan-submit",
            plan_digest=qualify_assignment.plan_digest or "",
            program_id="program-submit",
            program_digest=compile_assignment.program_digest,
            project_storage_ref="project-value:plan-submit",
            compiler_id="compiler",
            compiler_version="1",
            operation_catalog_id="operation-catalog",
            catalog_version="1",
            catalog_digest=_digest("operation-catalog"),
            effect_closure_digest=_digest("effect-closure"),
            authority_closure_digest=_digest("authority-closure"),
            resource_closure_digest=_digest("resource-closure"),
            qualify_work=AssignmentEnvelope(
                assignment=qualify_assignment,
                required_node_profile_selector=_digest("node-profile"),
                authority_digest=_digest("qualify-authority"),
                resource_policy_digest=_digest("qualify-policy"),
                fairness_key="project-a",
            ),
            due_at=now,
        )
    )
    assert attached["plan_id"] == "plan-submit"
    assert (
        connection.rows["runtime_plan_refs"][0]["plan_digest"]
        == qualify_assignment.plan_digest
    )
    assert not hasattr(connection, "commit")


def _authorization(scope: RuntimeScope, now: datetime) -> StepAuthorizationBinding:
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="project-scope:project-a:3",
        source_digest=_digest("scope-source"),
        source_epoch=3,
    )
    return StepAuthorizationBinding.from_content(
        run_id="run-1",
        step_id="step-1",
        operation_kind="specimen.effect.v1",
        operation_contract_digest=_digest("operation"),
        capability_id="cap-a",
        claim_owner="successor",
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        payload_digest=_digest("payload"),
        actor_id=scope.actor_id,
        project_key=scope.project_scope.project_key,
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
        interpreter_binding_digest=_digest("interpreter"),
        deployment_catalog_digest=_digest("catalog"),
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        approval_refs=(),
        resource_ceiling_digest=_digest("resource-ceiling"),
        resource_policy_epoch=4,
        queue_eligibility_digest=_digest("eligibility"),
        grant_epoch=5,
        expires_at=now.replace(year=now.year + 1),
        canonical_base_revision=2,
        canonical_incarnation="canonical-incarnation-2",
    )


def test_qualification_persists_exact_plan_and_step_binding(scope) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    authorization = _authorization(scope, now)
    context = AuthorityContext.from_content(
        actor_id=scope.actor_id,
        project_key=scope.project_scope.project_key,
        resolved_schema=scope.project_scope.resolved_schema,
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
        authority_source_bindings=authorization.authority_source_bindings,
        grants_digest=authorization.grants_digest,
        grant_epoch=authorization.grant_epoch,
        expires_at=authorization.expires_at,
        operation_scope_digest=_digest("operation-scope"),
        resource_ceiling_digest=authorization.resource_ceiling_digest,
        canonical_base_revision=authorization.canonical_base_revision,
        canonical_incarnation=authorization.canonical_incarnation,
    )
    plan = QualifiedPlan.from_content(
        plan_digest=_digest("plan"),
        authority_context_digest=context.context_digest,
        step_bindings=(authorization,),
    )
    binding = ExactQualificationBinding.from_content(
        qualification_id="qualification-1",
        project_key=scope.project_scope.project_key,
        run_id="run-1",
        plan_id="plan-1",
        plan_digest=plan.plan_digest,
        authority_context=context,
        authority_context_digest=context.context_digest,
        qualified_plan=plan,
        decision="QUALIFIED",
    )
    connection = _StoreConnection()
    row = QualificationStoreRepository(connection, scope).persist(binding)
    assert row["qualification_binding_digest"] == binding.qualification_binding_digest
    assert (
        connection.rows["runtime_step_authorizations"][0]["authorization_digest"]
        == authorization.binding_digest
    )
    connection.rows["runtime_runs"] = [
        {
            "project_key": "project-a",
            "run_id": "run-1",
            "state": "COMPILING",
            "revision": 4,
            "next_event_seq": 8,
            "plan_id": "plan-1",
            "plan_digest": plan.plan_digest,
            "qualification_digest": None,
        }
    ]
    activated = RuntimeLifecycleRepository(connection, scope).activate_qualification(
        ActivateQualification(run_id="run-1", expected_run_revision=4, binding=binding)
    )
    assert activated["state"] == "READY"
    assert activated["qualification_digest"] == plan.qualification_digest


def _assignment_and_claim(
    now: datetime,
) -> tuple[RuntimeAssignment, RecoveryBinding, ClaimBinding]:
    operation_digest = _digest("operation")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=_digest("interpreter-profile"),
        deployment_catalog_digest=_digest("catalog"),
        runtime_protocol_version="1",
        project_scope_digest=_digest("scope"),
        resource_policy_epoch=4,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="readback",
        recovery_handler_version="1",
        interpreter_profile_digest=interpreter.interpreter_profile_digest,
        authoritative_readback_profile_ref="readback:specimen.v1",
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-1",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="project-a",
        run_id="run-1",
        step_id="step-1",
        step_role=CompiledStepRole.EFFECT,
        capability_id="cap-a",
        operation_contract_ref=OperationContractRef(
            kind="specimen.effect.v1",
            contract_version="1.0.0",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "return:specimen.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED", "OUTCOME_UNKNOWN"),
                admission_required=False,
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{interpreter.binding_digest}",
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=_digest("catalog"),
        execution_epoch=2,
        incarnation="run-incarnation-2",
        input_refs=("value:input-1",),
        input_closure_digest=_digest("input"),
        queue_eligibility_digest=_digest("eligibility"),
        resource_policy_epoch=4,
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace-1",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease-1",
        lease_expires_at=now.replace(year=now.year + 1),
        node_id="node-1",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=interpreter.interpreter_profile_digest,
        authority_digest=_digest("authority"),
        execution_reservation_ref="reservation-1",
        execution_reservation_digest=_digest("reservation"),
    )
    return assignment, recovery, claim


class _LifecycleConnection:
    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[Any] = []
        self.work_selects = 0

    def execute(self, statement):
        self.statements.append(statement)
        if isinstance(statement, Select):
            table = statement.get_final_froms()[0].name
            if table == "runtime_work_items":
                self.work_selects += 1
                if self.work_selects > 1:
                    return _Result([self.rows["reconcile"]])
            return _Result([self.rows[table]])
        return _Result(rowcount=1)


def _claimed_fixture(now: datetime):
    assignment, recovery, claim = _assignment_and_claim(now)
    envelope = AssignmentEnvelope(
        assignment=assignment,
        required_node_profile_selector=_digest("node-profile"),
        authority_digest=_digest("authorization"),
        resource_policy_digest=_digest("policy"),
        fairness_key="project-a",
        qualification_digest=_digest("qualification"),
        resource_class="CPU_LIGHT",
        resource_units=1,
        recovery_binding=recovery,
        authoritative_readback_profile_ref=recovery.authoritative_readback_profile_ref,
    )
    work = _assignment_values(envelope, due_at=now)
    work.update(
        state="CLAIMED",
        revision=4,
        lease_token=claim.lease_token,
        lease_owner=claim.node_id,
        lease_expires_at=claim.lease_expires_at,
        claim_attempt_id=claim.attempt_id,
        claim_binding_json=claim.model_dump(mode="json"),
        claim_binding_digest=claim.binding_digest,
    )
    reconcile_assignment = RuntimeAssignment(
        runtime_protocol_version=assignment.runtime_protocol_version,
        work_item_id=f"reconcile:{claim.attempt_id}",
        assignment_kind=AssignmentKind.RECONCILE,
        project_key=assignment.project_key,
        run_id=assignment.run_id,
        step_id=assignment.step_id,
        step_role=assignment.step_role,
        capability_id=assignment.capability_id,
        operation_contract_ref=assignment.operation_contract_ref,
        operation_contract_digest=assignment.operation_contract_digest,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        program_digest=assignment.program_digest,
        plan_digest=assignment.plan_digest,
        deployment_catalog_digest=assignment.deployment_catalog_digest,
        execution_epoch=assignment.execution_epoch,
        incarnation=assignment.incarnation,
        input_refs=assignment.input_refs,
        input_closure_digest=assignment.input_closure_digest,
        payload_ref=assignment.payload_ref,
        payload_digest=assignment.payload_digest,
        queue_eligibility_digest=assignment.queue_eligibility_digest,
        resource_policy_epoch=assignment.resource_policy_epoch,
        claim_authority_epoch=assignment.claim_authority_epoch,
        claim_policy_digest=assignment.claim_policy_digest,
        expected_step_revision=4,
        reconciliation_attempt_id=claim.attempt_id,
        trace_id=assignment.trace_id,
    )
    reconcile = _assignment_values(
        AssignmentEnvelope(
            assignment=reconcile_assignment,
            required_node_profile_selector=_digest("node-profile"),
            authority_digest=_digest("authorization"),
            resource_policy_digest=_digest("policy"),
            fairness_key="project-a",
            qualification_digest=_digest("qualification"),
            authoritative_readback_profile_ref=(
                recovery.authoritative_readback_profile_ref
            ),
        ),
        due_at=now,
    )
    reconcile.update(state="PENDING", revision=0)
    rows = {
        "runtime_runs": {
            "project_key": "project-a",
            "run_id": "run-1",
            "incarnation": "run-incarnation",
            "state": "RUNNING",
            "revision": 5,
            "next_event_seq": 10,
        },
        "runtime_steps": {
            "project_key": "project-a",
            "run_id": "run-1",
            "step_id": "step-1",
            "state": "RUNNING",
            "revision": 3,
            "lease_token": claim.lease_token,
        },
        "runtime_work_items": work,
        "runtime_effect_attempts": {
            "project_key": "project-a",
            "attempt_id": claim.attempt_id,
            "run_id": "run-1",
            "step_id": "step-1",
            "disposition": "IN_FLIGHT",
            "revision": 2,
            "claim_binding_digest": claim.binding_digest,
            "authorization_digest": _digest("authorization"),
            "assignment_digest": assignment.assignment_digest,
            "handler_binding_digest": assignment.handler_binding_digest,
            "handler_realization_digest": assignment.handler_binding_digest,
        },
        "runtime_resource_reservations": {
            "project_key": "project-a",
            "reservation_id": "reservation-1",
            "work_item_id": "work-1",
            "run_id": "run-1",
            "step_id": "step-1",
            "attempt_id": claim.attempt_id,
            "state": "ACTIVE",
            "revision": 1,
            "lease_token": claim.lease_token,
            "reservation_digest": _digest("reservation"),
        },
        "reconcile": reconcile,
    }
    claimed = ClaimedLifecycle(
        claim=claim,
        run_id="run-1",
        step_id="step-1",
        work_item_id="work-1",
        attempt_id=claim.attempt_id,
        reservation_id="reservation-1",
        expected_run_revision=5,
        expected_step_revision=3,
        expected_work_revision=4,
        expected_attempt_revision=2,
        expected_reservation_revision=1,
    )
    return rows, claimed


@pytest.mark.parametrize(
    ("kind", "kwargs", "step_event", "step_state", "event_type", "run_state"),
    [
        (
            EffectTerminalKind.SUCCEEDED,
            {"output_digest": _digest("output")},
            StepEvent.RUNTIME_VALUE_PRODUCED,
            StepState.SUCCEEDED,
            "RuntimeValueProduced",
            "RUNNING",
        ),
        (
            EffectTerminalKind.FAILED,
            {"failure_digest": _digest("failure")},
            StepEvent.EFFECT_FAILED,
            StepState.FAILED,
            "EffectFailed",
            "FAILED",
        ),
        (
            EffectTerminalKind.OUTCOME_UNKNOWN,
            {},
            StepEvent.EFFECT_RECEIPT_LOST,
            StepState.RECONCILING,
            "EffectReceiptLost",
            "RECONCILING",
        ),
    ],
)
def test_terminal_outcome_updates_full_semantic_packet_atomically(
    scope, kind, kwargs, step_event, step_state, event_type, run_state
) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    rows, claimed = _claimed_fixture(now)
    connection = _LifecycleConnection(rows)
    terminal_kwargs = dict(kwargs)
    if kind is EffectTerminalKind.FAILED:
        terminal_kwargs["failure_ref"] = (
            f"project-value:runtime-failure:{claimed.attempt_id}"
        )
    RuntimeLifecycleRepository(
        connection,
        scope,
        terminal_authority=_AllowCurrentTerminalAuthority(),
        terminal_failures=_AllowTerminalFailures(),
        failure_policy=_StaticFailurePolicy(required=True),
    ).commit_outcome(
        TerminalOutcome(
            claimed=claimed,
            kind=kind,
            authority_digest=_digest("authorization"),
            observed_at=now,
            step_event=step_event,
            target_step_state=step_state,
            event_type=event_type,
            event_schema_version={
                EffectTerminalKind.SUCCEEDED: "mrw.runtime.event.effect_succeeded.v1",
                EffectTerminalKind.FAILED: "mrw.runtime.event.effect_failed.v1",
                EffectTerminalKind.OUTCOME_UNKNOWN: (
                    "mrw.runtime.event.outcome_unknown.v1"
                ),
            }[kind],
            **terminal_kwargs,
        )
    )

    sql = "\n".join(str(statement) for statement in connection.statements)
    for table in (
        "runtime_effect_attempts",
        "runtime_steps",
        "runtime_work_items",
        "runtime_resource_reservations",
        "runtime_events",
        "runtime_runs",
    ):
        assert table in sql
    event_insert = next(
        statement
        for statement in connection.statements
        if isinstance(statement, Insert) and statement.table.name == "runtime_events"
    )
    assert _insert_values(event_insert)["event_type"] == event_type
    run_update = next(
        statement
        for statement in connection.statements
        if isinstance(statement, Update) and statement.table.name == "runtime_runs"
    )
    assert _insert_values(run_update)["state"] == run_state
    reservation_update = next(
        statement
        for statement in connection.statements
        if isinstance(statement, Update)
        and statement.table.name == "runtime_resource_reservations"
    )
    assert str(_insert_values(reservation_update)["release_reason"]).startswith(
        "SEMANTIC_"
    )
    assert not hasattr(connection, "commit")


def test_caller_cannot_turn_optional_persisted_failure_into_required_run_failure(
    scope,
) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    rows, claimed = _claimed_fixture(now)
    connection = _LifecycleConnection(rows)
    RuntimeLifecycleRepository(
        connection,
        scope,
        terminal_authority=_AllowCurrentTerminalAuthority(),
        terminal_failures=_AllowTerminalFailures(),
        failure_policy=_StaticFailurePolicy(required=False),
    ).commit_outcome(
        TerminalOutcome(
            claimed=claimed,
            kind=EffectTerminalKind.FAILED,
            authority_digest=_digest("authorization"),
            failure_ref=f"project-value:runtime-failure:{claimed.attempt_id}",
            failure_digest=_digest("failure"),
            observed_at=now,
            step_event=StepEvent.EFFECT_FAILED,
            target_step_state=StepState.FAILED,
            event_type=StepEvent.EFFECT_FAILED.value,
            event_schema_version="mrw.runtime.event.effect_failed.v1",
        )
    )

    run_update = next(
        statement
        for statement in connection.statements
        if isinstance(statement, Update) and statement.table.name == "runtime_runs"
    )
    assert _insert_values(run_update)["state"] == "RUNNING"


def test_effect_failure_is_reducer_owned_and_run_failure_is_separate() -> None:
    step = StepSnapshot(
        "step-1", StepState.RUNNING, EffectDisposition.IN_FLIGHT, revision=3
    )
    reduced_step = reduce_step(
        step, StepEvent.EFFECT_FAILED, StepState.FAILED, guard=True
    )
    assert reduced_step.state is StepState.FAILED
    assert reduced_step.effect_disposition is EffectDisposition.FAILED
    assert reduced_step.revision == 4

    run = RunSnapshot("run-1", RunState.RUNNING, revision=5)
    reduced_run = reduce_run_event(
        run, RunEvent.REQUIRED_STEP_FAILED, RunState.FAILED, guard=True
    )
    assert reduced_run.state is RunState.FAILED and reduced_run.revision == 6
    # The step reducer cannot smuggle an illegal READY -> FAILED edge, and
    # reducing a step did not mutate the independent run snapshot.
    assert run.state is RunState.RUNNING and run.revision == 5
    with pytest.raises(IllegalTransition):
        reduce_step(
            StepSnapshot("step-1", StepState.READY),
            StepEvent.EFFECT_FAILED,
            StepState.FAILED,
            guard=True,
        )


def test_authority_provider_rehashes_current_scope_grant_and_capability(scope) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    rows = {
        "project_scope_registry": {
            "project_key": "project-a",
            "registry_revision": 3,
            "resolved_schema": "project_a",
            "scope_digest": scope.project_scope.scope_digest,
            "incarnation": scope.project_scope.incarnation,
            "state": "ACTIVE",
        },
        "runtime_capability_authority": {
            "project_key": "project-a",
            "capability_id": "cap-a",
            "mode": "canary",
            "authority_epoch": 7,
            "successor_claim_enabled": True,
            "legacy_claim_enabled": False,
            "allowlist_digest": _digest("allowlist"),
            "config_digest": _digest("config"),
            "approval_ref": "approval:cutover",
            "rollback_target_ref": "rollback:legacy",
            "revision": 2,
        },
        "runtime_authority_grants": {
            "grant_id": "grant-1",
            "actor_id": "actor-a",
            "capability_id": "cap-a",
            "operation_scope_json": {"operations": ["specimen.effect.v1"]},
            "resource_ceiling_json": {"units": 1},
            "credential_ref": None,
            "grant_epoch": 5,
            "expires_at": now.replace(year=now.year + 1),
            "revoked_at": None,
            "revision": 1,
        },
    }

    class _AuthorityConnection:
        def execute(self, statement):
            table = statement.get_final_froms()[0].name
            row = rows[table]
            return _Result([row])

    context = PostgresAuthorityProvider(_AuthorityConnection(), scope).current_context(
        "actor-a",
        capability_id="cap-a",
        canonical_base_revision=2,
        canonical_incarnation="canonical-incarnation-2",
        now=now,
    )
    assert context.context_digest == canonical_digest(
        context, exclude_fields={"context_digest"}
    )
    assert {source.source_kind for source in context.authority_source_bindings} == {
        "PROJECT_SCOPE",
        "GRANT",
        "CAPABILITY_AUTHORITY",
    }
    assert context.grant_epoch == 5
