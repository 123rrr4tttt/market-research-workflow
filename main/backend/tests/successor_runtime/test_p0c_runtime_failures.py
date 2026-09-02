from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
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
    RuntimeFailureBindingError,
    RuntimeFailureRepository,
)

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
    assert (
        connection.scalar(
            sa.select(sa.func.count()).select_from(tables.successor_values)
        )
        == 1
    )


def test_runtime_failure_rejects_mutation_digest_drift_and_aba(failure_db) -> None:
    connection, tables = failure_db
    scope = _scope()
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)
    record = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
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


def test_runtime_failure_rejects_wrong_scope_attempt_and_ref(failure_db) -> None:
    connection, tables = failure_db
    scope = _scope()
    assignment, claim = _assignment_and_claim()
    repository = RuntimeFailureRepository(connection, tables)
    record = repository.put_exact(
        scope,
        assignment=assignment,
        claim=claim,
        failure_code="PROVIDER_REJECTED",
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
