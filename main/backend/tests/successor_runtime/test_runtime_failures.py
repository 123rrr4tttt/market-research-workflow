from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from functorial_kit import Failure
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.runtime_failures import (
    FAILURE_CODEC_ID,
    FAILURE_OBJECT_TYPE,
    DOMAIN_FAILURE_OBJECT_TYPE,
    RuntimeFailureBindingError,
    RuntimeFailureRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 31, 13, 0, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _scope(
    *,
    project_key: str = "project-a",
    schema: str = "project_a",
    incarnation: str = "project-scope-incarnation-3",
) -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=project_key,
            resolved_schema=schema,
            project_registry_revision=3,
            incarnation=incarnation,
            scope_digest=_digest(f"scope:{project_key}:{schema}:3:{incarnation}"),
        ),
        actor_id="runtime-node-a",
    )


def _assignment_and_claim() -> tuple[RuntimeAssignment, ClaimBinding]:
    operation_digest = _digest("operation")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=_digest("interpreter-profile"),
        deployment_catalog_digest=_digest("deployment-catalog"),
        runtime_protocol_version="1",
        project_scope_digest=_scope().project_scope.scope_digest,
        resource_policy_epoch=4,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-1",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="project-a",
        run_id="run-1",
        step_id="step-1",
        step_role=CompiledStepRole.EFFECT,
        capability_id="capability-a",
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
        handler_binding_ref=(f"handler-binding:sha256:{interpreter.binding_digest}"),
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=_digest("deployment-catalog"),
        execution_epoch=2,
        incarnation="run-incarnation-2",
        input_refs=("project-value:input-1",),
        input_closure_digest=_digest("input-closure"),
        queue_eligibility_digest=_digest("queue-eligibility"),
        resource_policy_epoch=4,
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=3,
        trace_id="trace-1",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease-1",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=interpreter.interpreter_profile_digest,
        authority_digest=_digest("authority"),
        execution_reservation_ref="reservation-1",
        execution_reservation_digest=_digest("reservation"),
    )
    return assignment, claim


@pytest.fixture
def failure_db():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.connection.create_function(
        "num_nonnulls",
        -1,
        lambda *values: sum(value is not None for value in values),
    )
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS project_a")
    tables = project_tables(sa.MetaData(), "project_a")
    tables.successor_values.create(connection)
    connection.commit()
    try:
        yield connection, tables
    finally:
        connection.close()
        engine.dispose()


def test_runtime_failure_is_exact_idempotent_and_project_scoped(failure_db) -> None:
    connection, tables = failure_db
    scope = _scope()
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)

    first = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
    )
    replay = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
    )

    assert replay == first
    assert first.failure_ref == f"project-value:runtime-failure:{claim.attempt_id}"
    assert len(first.failure_ref) < 128
    assert first.failure_code == "PROVIDER_REJECTED"
    assert first.assignment_digest == assignment.assignment_digest
    assert first.claim_binding_digest == claim.binding_digest
    row = connection.execute(sa.select(tables.successor_values)).mappings().one()
    assert row["object_type"] == FAILURE_OBJECT_TYPE
    assert row["codec_id"] == FAILURE_CODEC_ID
    assert row["state"] == "FAILED"
    assert row["content_json"] is None
    assert b'"failure_code":"PROVIDER_REJECTED"' in bytes(row["content_bytes"])
    assert first.domain_failure is None
    assert len(bytes(row["content_bytes"])) == 898
    assert hashlib.sha256(bytes(row["content_bytes"])).hexdigest() == "1aa9d3014e039b3f0e7203e68ccd7e17120105b379bf6060abf1f5dc70fc872c"
    assert (
        connection.scalar(
            sa.select(sa.func.count()).select_from(tables.successor_values)
        )
        == 1
    )


@pytest.mark.parametrize("domain_failure", [None, Failure("workflow", "PROVIDER_REJECTED", "中文", {"nested": [1]})])
def test_runtime_failure_rejects_mutation_digest_drift_and_aba(failure_db, domain_failure) -> None:
    connection, tables = failure_db
    scope = _scope()
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)
    record = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
        domain_failure=domain_failure,
    )

    with pytest.raises(ProjectRecordNotFound, match="exact value not found"):
        repository.verify_exact(
            scope,
            assignment=assignment,
            claim=claim,
            failure_ref=record.failure_ref,
            failure_digest=_digest("drifted-failure-digest"),
        )

    connection.execute(
        sa.update(tables.successor_values).values(content_bytes=b'{"mutated":true}')
    )
    with pytest.raises(ExactContentConflict, match="fails digest readback"):
        repository.verify_exact(
            scope,
            assignment=assignment,
            claim=claim,
            failure_ref=record.failure_ref,
            failure_digest=record.failure_digest,
        )

    connection.rollback()
    record = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
        domain_failure=domain_failure,
    )
    connection.execute(
        sa.update(tables.successor_values).values(incarnation="reused-incarnation")
    )
    with pytest.raises(ProjectRecordNotFound, match="exact value not found"):
        repository.verify_exact(
            scope,
            assignment=assignment,
            claim=claim,
            failure_ref=record.failure_ref,
            failure_digest=record.failure_digest,
        )


@pytest.mark.parametrize("domain_failure", [None, Failure("workflow", "PROVIDER_REJECTED", "中文", {"nested": [1]})])
def test_runtime_failure_rejects_wrong_scope_attempt_and_ref(failure_db, domain_failure) -> None:
    connection, tables = failure_db
    scope = _scope()
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)
    record = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
        domain_failure=domain_failure,
    )

    with pytest.raises(RuntimeFailureBindingError, match="assignment project"):
        repository.verify_exact(
            _scope(project_key="project-b", schema="project_b"),
            assignment=assignment,
            claim=claim,
            failure_ref=record.failure_ref,
            failure_digest=record.failure_digest,
        )

    wrong_attempt = claim.model_copy(update={"attempt_id": _digest("wrong-attempt")})
    with pytest.raises(ValueError, match="binding_digest does not match"):
        repository.verify_exact(
            scope,
            assignment=assignment,
            claim=wrong_attempt,
            failure_ref=record.failure_ref,
            failure_digest=record.failure_digest,
        )

    with pytest.raises(RuntimeFailureBindingError, match="exact runtime attempt"):
        repository.verify_exact(
            scope,
            assignment=assignment,
            claim=claim,
            failure_ref="project-value:runtime-failure:wrong",
            failure_digest=record.failure_digest,
        )


def test_same_attempt_cannot_mutate_typed_failure_code(failure_db) -> None:
    connection, tables = failure_db
    scope = _scope()
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)
    repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
    )

    with pytest.raises(ExactContentConflict, match="different bytes"):
        repository.put_exact(
            scope,
            assignment=assignment,
            claim=claim,
            failure_code="PROVIDER_TIMEOUT",
        )


def test_failure_code_must_be_typed_and_canonical(failure_db) -> None:
    connection, tables = failure_db
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)

    with pytest.raises(ValueError, match="canonical string"):
        repository.put_exact(
            _scope(),
            assignment=assignment,
            claim=claim,
            failure_code="  ",
        )


def test_domain_failure_v2_preserves_chinese_nested_context_and_exact_identity(failure_db) -> None:
    connection, tables = failure_db
    assignment, claim = _assignment_and_claim()
    domain = Failure("workflow.graph.failure", "PROVIDER_REJECTED", "上游节点没有文本", {"node": "first", "nested": {"原因": [None, True, 2, "中文"]}})
    repository = RuntimeFailureRepository(connection, tables)
    record = repository.put_exact(_scope(), assignment=assignment, claim=claim,
                                  failure_code=domain.code, domain_failure=domain)
    assert record.domain_failure == domain
    assert repository.verify_exact(_scope(), assignment=assignment, claim=claim,
                                   failure_ref=record.failure_ref, failure_digest=record.failure_digest) == record
    row = connection.execute(sa.select(tables.successor_values)).mappings().one()
    assert row["object_type"] == DOMAIN_FAILURE_OBJECT_TYPE
    body = json.loads(bytes(row["content_bytes"]))
    assert body["schema_version"] == "mrw.runtime.failure.v2"
    assert body["domain_failure"] == {"family": domain.family, "code": domain.code, "message": domain.message, "context": domain.context}
    for changed in (replace(domain, message="不同说明"), replace(domain, context={"node": "second"})):
        with pytest.raises(ExactContentConflict, match="different bytes"):
            repository.put_exact(_scope(), assignment=assignment, claim=claim,
                                 failure_code=domain.code, domain_failure=changed)
    connection.execute(sa.update(tables.successor_values).values(object_type=FAILURE_OBJECT_TYPE))
    with pytest.raises(RuntimeFailureBindingError, match="object identity"):
        repository.verify_exact(_scope(), assignment=assignment, claim=claim,
                                failure_ref=record.failure_ref, failure_digest=record.failure_digest)


@pytest.mark.parametrize("invalid", [
    {"code": "PROVIDER_REJECTED"}, Failure("workflow", "OTHER", "message"),
    Failure("workflow", "PROVIDER_REJECTED", "message", {"bad": object()}),
    Failure("workflow", "PROVIDER_REJECTED", "message", {"bad": (1, 2)}),
    Failure("workflow", "PROVIDER_REJECTED", "message", {"bad": float("nan")}),
])
def test_domain_failure_invalid_body_is_rejected_before_write(failure_db, invalid) -> None:
    connection, tables = failure_db
    assignment, claim = _assignment_and_claim()
    with pytest.raises((TypeError, ValueError)):
        RuntimeFailureRepository(connection, tables).put_exact(
            _scope(), assignment=assignment, claim=claim, failure_code="PROVIDER_REJECTED", domain_failure=invalid,
        )
    assert connection.scalar(sa.select(sa.func.count()).select_from(tables.successor_values)) == 0


def test_domain_failure_write_uses_caller_rollback(failure_db) -> None:
    connection, tables = failure_db
    assignment, claim = _assignment_and_claim()
    with pytest.raises(RuntimeError, match="caller rollback"), connection.begin_nested():
        RuntimeFailureRepository(connection, tables).put_exact(
            _scope(), assignment=assignment, claim=claim, failure_code="PROVIDER_REJECTED",
            domain_failure=Failure("workflow", "PROVIDER_REJECTED", "中文失败", {"nested": {"a": 1}}),
        )
        raise RuntimeError("caller rollback")
    assert connection.scalar(sa.select(sa.func.count()).select_from(tables.successor_values)) == 0


@pytest.fixture
def failure_reader(failure_db, monkeypatch):
    from contextlib import nullcontext
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    from app.successor_runtime.substrate.postgres.runtime_journal import RuntimeJournalRepository
    from app.successor_runtime.substrate.postgres import runtime_journal
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    connection, tables = failure_db
    assignment, claim = _assignment_and_claim()
    record = RuntimeFailureRepository(connection, tables).put_exact(
        _scope(), assignment=assignment, claim=claim, failure_code="PROVIDER_REJECTED",
    )
    plan_step = SimpleNamespace(step_id=assignment.step_id, operation_id="workflow-node:0:first",
                                operation_contract_ref=assignment.operation_contract_ref)
    plan = SimpleNamespace(plan_id="plan-1", plan_digest=assignment.plan_digest, program_id="program-1",
                           program_digest=assignment.program_digest, ordered_steps=(plan_step,))
    run = dict(resolved_schema="project_a", plan_id=plan.plan_id, plan_digest=plan.plan_digest,
               program_id=plan.program_id, program_digest=plan.program_digest, execution_epoch=assignment.execution_epoch,
               incarnation=assignment.incarnation, project_registry_revision=3, project_scope_digest=_scope().project_scope.scope_digest)
    event = dict(seq=1, project_key=assignment.project_key, run_id=assignment.run_id, event_type="EffectFailed",
                 schema_version="mrw.runtime.event.effect_failed.v1", step_id=assignment.step_id, attempt_id=claim.attempt_id,
                 authority_digest=claim.authorization_digest, event_metadata_json={"work_item_id": assignment.work_item_id})
    work = dict(authority_digest=claim.authorization_digest, claim_attempt_id=claim.attempt_id,
                claim_binding_digest=claim.binding_digest, claim_binding_json=claim.model_dump(mode="json"))
    attempt = dict(run_id=assignment.run_id, step_id=assignment.step_id, attempt_id=claim.attempt_id,
                   incarnation=assignment.incarnation, execution_epoch=assignment.execution_epoch,
                   assignment_digest=assignment.assignment_digest, handler_binding_digest=assignment.handler_binding_digest,
                   handler_realization_digest=assignment.handler_binding_digest, claim_binding_json=claim.model_dump(mode="json"),
                   claim_binding_digest=claim.binding_digest, authorization_digest=claim.authorization_digest,
                   disposition="FAILED", input_digest=assignment.input_closure_digest,
                   failure_ref=record.failure_ref, failure_digest=record.failure_digest)
    step = dict(operation_id=plan_step.operation_id, operation_kind=assignment.operation_contract_ref.kind,
                operation_version=assignment.operation_contract_ref.contract_version, execution_epoch=assignment.execution_epoch,
                input_digest=assignment.input_closure_digest, step_id=assignment.step_id, state="FAILED")
    rows = {"runtime_work_items": work, "runtime_effect_attempts": attempt, "runtime_steps": step}

    class ReaderConnection:
        def execute(self, statement):
            name = statement.get_final_froms()[0].name
            if name == "successor_values":
                return connection.execute(statement)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: rows[name]))

    monkeypatch.setattr(ServerProjectScopeResolver, "resolve", lambda self, key: _scope().project_scope)
    monkeypatch.setattr(PlanRepository, "get", lambda self, scope, digest: plan)
    monkeypatch.setattr(RuntimeJournalRepository, "load_run", lambda self, run_id: run)
    monkeypatch.setattr(RuntimeJournalRepository, "load_events", lambda self, run_id: (event,))
    monkeypatch.setattr(runtime_journal, "validate_runtime_assignment_row", lambda row: assignment)
    return SimpleNamespace(engine=SimpleNamespace(connect=lambda: nullcontext(ReaderConnection())),
                           run=run, event=event, work=work, attempt=attempt, step=step, plan=plan, record=record)


def test_failure_reader_reads_v1_exact_bytes_from_event_bound_attempt(failure_reader) -> None:
    from app.composition.production import read_installed_program_failures

    assert read_installed_program_failures(engine=failure_reader.engine, project_key="project-a", actor_id="viewer", run_id="run-1") == (
        (1, failure_reader.record),
    )


@pytest.mark.parametrize("drift", [
    "scope", "registry_revision", "plan_digest", "event_run", "event_project", "event_work", "event_ref",
    "event_digest", "attempt_run", "handler", "work_claim", "work_claim_json", "work_attempt", "work_authority",
])
def test_failure_reader_rejects_scope_plan_event_and_claim_drift(failure_reader, drift) -> None:
    from app.composition.production import read_installed_program_failures

    if drift == "scope":
        failure_reader.run["project_scope_digest"] = _digest("wrong-scope")
    elif drift == "registry_revision":
        failure_reader.run["project_registry_revision"] = 4
    elif drift == "plan_digest":
        failure_reader.plan.plan_digest = _digest("wrong-plan")
    elif drift in {"event_run", "event_project"}:
        failure_reader.event["run_id" if drift == "event_run" else "project_key"] = "other"
    elif drift == "event_work":
        failure_reader.event["event_metadata_json"]["work_item_id"] = "other-work"
    elif drift == "event_ref":
        failure_reader.event["payload_ref"] = "project-value:wrong"
    elif drift == "event_digest":
        failure_reader.event.update(payload_ref=failure_reader.record.failure_ref, payload_digest=_digest("wrong-digest"))
    elif drift == "attempt_run":
        failure_reader.attempt["run_id"] = "other-run"
    elif drift == "handler":
        failure_reader.attempt["handler_binding_digest"] = _digest("wrong-handler")
    else:
        field = {"work_claim": "claim_binding_digest", "work_claim_json": "claim_binding_json",
                 "work_attempt": "claim_attempt_id", "work_authority": "authority_digest"}[drift]
        failure_reader.work[field] = {} if drift == "work_claim_json" else _digest("wrong-work-binding")
    with pytest.raises(ExactBindingConflict):
        read_installed_program_failures(engine=failure_reader.engine, project_key="project-a", actor_id="viewer", run_id="run-1")


@pytest.mark.parametrize("domain", [None, Failure("workflow", "PROVIDER_REJECTED", "中文错误", {"nested": [True, 2]})])
def test_facade_projects_verified_failure_v1_or_v2_without_inventing_fields(failure_reader, monkeypatch, domain) -> None:
    from app.composition import production
    from app.services.workflow_graph import WorkflowGraphRuntimeService

    service = WorkflowGraphRuntimeService()
    event = failure_reader.event
    required = {**event, "event_type": "RequiredStepFailed", "seq": 2, "event_metadata_json": {"required_step_failed": True}}
    record = replace(failure_reader.record, domain_failure=domain)
    monkeypatch.setattr(production, "read_installed_program_failures", lambda **kwargs: ((1, record),))
    monkeypatch.setattr(service, "_read_runtime", lambda **kwargs: (failure_reader.run, (failure_reader.step,), (event, required)))
    items = service.get_run_events("run-1", project_key="project-a", actor_id="viewer")["items"]
    expected = {"work_item_id": event["event_metadata_json"]["work_item_id"], "failure_ref": record.failure_ref,
                "failure_digest": record.failure_digest, "failure_code": record.failure_code}
    if domain is not None:
        expected.update(failure_family=domain.family, error=domain.message, context=domain.context)
    assert items[0]["payload"] == expected
    assert [item["event_type"] for item in items] == ["EffectFailed", "RequiredStepFailed"]
    assert items[1]["payload"] == {"required_step_failed": True}
