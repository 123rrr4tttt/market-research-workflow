from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompilerBinding,
    HandlerBindingKind,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.qualification import (
    AuthorityContext,
    AuthoritySourceBinding,
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    ExactQualificationBinding,
    PublicPayloadViolation,
    RuntimeJournalRepository,
    StaleRevisionError,
    validate_authorization_row,
    validate_qualification_row,
)


class _Mappings:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def one_or_none(self):
        return self.row

    def all(self):
        return [] if self.row is None else [self.row]


class _Result:
    def __init__(self, row: dict[str, Any] | None = None, rowcount: int = 1) -> None:
        self._row = row
        self.rowcount = rowcount

    def mappings(self):
        return _Mappings(self._row)


class RecordingConnection:
    """No DB: record the exact SQLAlchemy command sequence."""

    def __init__(self, *, revision: int, next_event_seq: int = 1) -> None:
        self.revision = revision
        self.next_event_seq = next_event_seq
        self.statements: list[Any] = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Result(
                {"revision": self.revision, "next_event_seq": self.next_event_seq}
            )
        return _Result(rowcount=1)


@pytest.fixture
def runtime_scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="project-a",
            resolved_schema="project_a",
            project_registry_revision=3,
            incarnation="project-a-incarnation-1",
            scope_digest="a" * 64,
        ),
        actor_id="actor-a",
    )


def _event(event_type: str) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "schema_version": "mrw.runtime.event.v1",
        "event_metadata_json": {"reason_code": "TEST", "value_ref": "value:1"},
        "payload_ref": "project-value:1",
        "payload_digest": "b" * 64,
        "authority_digest": "c" * 64,
    }


def _compile_work_item(now: datetime) -> dict[str, Any]:
    binding = CompilerBinding.from_content(
        compiler_id="compiler",
        compiler_version="1",
        compiler_digest="1" * 64,
        operation_catalog_digest="2" * 64,
        domain_contract_snapshot_digest="3" * 64,
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-2",
        assignment_kind=AssignmentKind.COMPILE,
        project_key="project-a",
        run_id="run-1",
        capability_id="compile",
        handler_binding_kind=HandlerBindingKind.COMPILER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest="4" * 64,
        deployment_catalog_digest="5" * 64,
        execution_epoch=0,
        incarnation="run-incarnation-1",
        queue_eligibility_digest="6" * 64,
        resource_policy_epoch=0,
        claim_authority_epoch=1,
        claim_policy_digest="7" * 64,
        trace_id="trace-1",
    )
    return {
        "work_item_id": assignment.work_item_id,
        "assignment_kind": assignment.assignment_kind.value,
        "capability_id": assignment.capability_id,
        "assignment_digest": assignment.assignment_digest,
        "assignment_binding_json": assignment.model_dump(mode="json"),
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "input_closure_digest": assignment.input_closure_digest,
        "claim_authority_epoch": assignment.claim_authority_epoch,
        "claim_policy_digest": assignment.claim_policy_digest,
        "handler_binding_kind": assignment.handler_binding_kind.value,
        "handler_binding_ref": assignment.handler_binding_ref,
        "handler_binding_digest": assignment.handler_binding_digest,
        "deployment_catalog_digest": assignment.deployment_catalog_digest,
        "runtime_protocol_version": assignment.runtime_protocol_version,
        "required_node_profile_selector": "8" * 64,
        "program_digest": assignment.program_digest,
        "authority_digest": "9" * 64,
        "resource_policy_digest": "a" * 64,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "fairness_key": "project-a",
        "state": "READY",
        "declared_priority": 0,
        "enqueued_at": now,
        "due_at": now,
        "attempt_count": 0,
        "revision": 0,
    }


def test_event_snapshot_and_successor_work_item_are_one_command_set(runtime_scope):
    now = datetime.now(UTC)
    connection = RecordingConnection(revision=7, next_event_seq=41)
    repository = RuntimeJournalRepository(connection, runtime_scope)
    commands = repository.commands(
        run_id="run-1",
        expected_revision=7,
        snapshot_values={"state": "RUNNING"},
        events=(_event("StepClaimed"), _event("EffectStarted")),
        work_items=(_compile_work_item(now),),
    )
    receipt = commands.execute(connection)

    assert (receipt.first_event_seq, receipt.last_event_seq) == (41, 42)
    assert receipt.revision == 8
    # lock + snapshot CAS + two append-only events + successor work item
    assert len(connection.statements) == 5
    sql = "\n".join(str(statement).lower() for statement in connection.statements)
    assert "for update" in sql
    assert "max(" not in sql
    assert "runtime_runs" in sql
    assert sql.count("runtime_events") == 2
    assert "runtime_work_items" in sql
    assert not hasattr(connection, "commit")


def test_stale_run_cas_emits_no_event_or_snapshot_commands(runtime_scope):
    connection = RecordingConnection(revision=8, next_event_seq=41)
    commands = RuntimeJournalRepository(connection, runtime_scope).commands(
        run_id="run-1",
        expected_revision=7,
        snapshot_values={"state": "RUNNING"},
        events=(_event("StepClaimed"),),
    )
    with pytest.raises(StaleRevisionError, match="stale runtime run revision"):
        commands.execute(connection)
    assert len(connection.statements) == 1


@pytest.mark.parametrize(
    "bad_event",
    [
        {**_event("Bad"), "payload": {"secret": "inline"}},
        {**_event("Bad"), "event_metadata_json": {"exact_bytes": b"secret"}},
        {**_event("Bad"), "event_metadata_json": {"safe": b"secret"}},
        {**_event("Bad"), "event_metadata_json": {"body": {"secret": "x"}}},
    ],
)
def test_public_journal_rejects_payload_fields_and_bytes(runtime_scope, bad_event):
    with pytest.raises(PublicPayloadViolation):
        RuntimeJournalRepository(RecordingConnection(revision=0), runtime_scope).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "SUBMITTED"},
            events=(bad_event,),
        )


@pytest.mark.parametrize("sequence_type", [tuple, list])
@pytest.mark.parametrize("count", [0, 2, 4096])
def test_public_journal_accepts_bounded_child_settlement(runtime_scope, sequence_type, count):
    connection = RecordingConnection(revision=0)
    metadata = {
        "source_step_id": "traversal-step-a",
        "child_count": count,
        "child_run_ids": sequence_type(f"child-{index}" for index in range(count)),
        "child_result_digests": sequence_type("b" * 64 if index % 2 else None for index in range(count)),
        "result_digest": "b" * 64,
    }
    receipt = RuntimeJournalRepository(connection, runtime_scope).commands(
        run_id="run-1", expected_revision=0, snapshot_values={"state": "RUNNING"},
        events=({**_event("ActiveChildrenSettled"), "event_metadata_json": metadata},),
    ).execute(connection)
    assert receipt.revision == 1
    event_insert = connection.statements[-1].compile().params
    assert event_insert["event_metadata_json"] == metadata


@pytest.mark.parametrize("event_type,metadata", [
    ("TraversalMaterializationRequested", {
        "source_step_id": "traversal-step-a", "input_ref": "project-value:sequence",
        "traversal_policy": "MATERIALIZED_SHAPE", "input_sequence_digest": "b" * 64,
        "element_program_digest": "b" * 64, "element_count": 2,
        "element_digests": ("b" * 64, "c" * 64), "shape_digest": "b" * 64,
        "binding_digest": "b" * 64, "materialization_digest": "b" * 64,
    }),
    ("ActiveChildMaterialized", {
        "source_step_id": "traversal-step-a", "child_run_id": "child-0",
        "root_value_identity": "retrieval-budget:root", "root_value_ref": "project-value:budget",
        "result_step_id": "result", "input_ref": "project-value:invocation-0",
        "input_digest": "b" * 64, "materialization_digest": "b" * 64,
        "element_index": 0, "element_digest": "b" * 64,
        "child_program_digest": "b" * 64, "root_value_digest": "b" * 64,
    }),
])
def test_public_journal_accepts_traversal_lifecycle_metadata(runtime_scope, event_type, metadata):
    connection = RecordingConnection(revision=0)
    receipt = RuntimeJournalRepository(connection, runtime_scope).commands(
        run_id="run-1", expected_revision=0, snapshot_values={"state": "WAITING"},
        events=({**_event(event_type), "event_metadata_json": metadata},),
    ).execute(connection)
    assert receipt.revision == 1
    assert connection.statements[-1].compile().params["event_metadata_json"] == metadata


@pytest.mark.parametrize("field,value", [
    ("child_count", True), ("child_count", -1), ("child_count", 4097),
    ("child_count", 1.0), ("child_count", None),
    ("child_run_ids", "child-0"), ("child_run_ids", ["child-0"] * 4097),
    ("child_run_ids", [None]), ("child_run_ids", [""]),
    ("child_run_ids", ["x" * 257]), ("child_run_ids", ["tenant document body"]),
    ("child_run_ids", [{"body": "secret"}]), ("child_run_ids", [b"secret"]),
    ("child_result_digests", "b" * 64), ("child_result_digests", [None] * 4097),
    ("child_result_digests", ["g" * 64]), ("child_result_digests", ["b" * 63]),
    ("child_result_digests", [1]), ("child_result_digests", [["b" * 64]]),
    ("child_result_digests", [{"body": "secret"}]),
    ("arbitrary_ids", ["child-0"]), ("result_digest", ["b" * 64]),
    ("element_count", False), ("element_count", -1), ("element_count", 4097),
    ("element_index", True), ("element_index", -1), ("element_index", 4096),
    ("element_index", 1.0), ("element_digests", [None]),
    ("element_digests", ["b" * 64] * 4097), ("element_digests", ["g" * 64]),
    ("element_digests", [{"body": "secret"}]),
    ("root_value_identity", "tenant document body"), ("root_value_identity", "x" * 257),
    ("root_value_identity", {"body": "secret"}),
    ("traversal_policy", "tenant document body"), ("traversal_policy", {"body": "secret"}),
])
def test_public_journal_rejects_malformed_child_metadata(runtime_scope, field, value):
    connection = RecordingConnection(revision=0)
    with pytest.raises(PublicPayloadViolation):
        RuntimeJournalRepository(connection, runtime_scope).commands(
            run_id="run-1", expected_revision=0, snapshot_values={"state": "RUNNING"},
            events=({**_event("ActiveChildrenSettled"), "event_metadata_json": {field: value}},),
        )
    assert connection.statements == []


def test_public_program_and_plan_tables_are_opaque_refs_only():
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES

    program_columns = set(PUBLIC_TABLES["runtime_program_refs"].c.keys())
    plan_columns = set(PUBLIC_TABLES["runtime_plan_refs"].c.keys())
    assert {"spec_json", "program_json", "payload", "exact_bytes"}.isdisjoint(program_columns)
    assert {"plan_json", "payload", "exact_bytes"}.isdisjoint(plan_columns)
    assert {"program_id", "program_digest", "project_storage_ref"} <= program_columns
    assert {"plan_id", "plan_digest", "project_storage_ref"} <= plan_columns


def test_work_item_assignment_binding_is_rehashed_before_database_effect(
    runtime_scope,
):
    now = datetime.now(UTC)
    work_item = _compile_work_item(now)

    work_item["assignment_digest"] = "f" * 64
    connection = RecordingConnection(revision=0)
    with pytest.raises(ExactBindingConflict, match="digest mismatch"):
        RuntimeJournalRepository(connection, runtime_scope).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(work_item,),
        )
    assert connection.statements == []

    indexed_drift = _compile_work_item(now)
    indexed_drift["handler_binding_digest"] = "e" * 64
    with pytest.raises(ExactBindingConflict, match="duplicated-column drift"):
        RuntimeJournalRepository(RecordingConnection(revision=0), runtime_scope).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(indexed_drift,),
        )

    nullable_drift = _compile_work_item(now)
    nullable_drift["plan_digest"] = "6" * 64
    with pytest.raises(ExactBindingConflict, match="plan_digest"):
        RuntimeJournalRepository(RecordingConnection(revision=0), runtime_scope).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(nullable_drift,),
        )

    noncanonical = _compile_work_item(now)
    noncanonical["assignment_binding_json"] = {
        key: value
        for key, value in noncanonical["assignment_binding_json"].items()
        if key != "step_role"
    }
    with pytest.raises(ExactBindingConflict, match="not canonical"):
        RuntimeJournalRepository(RecordingConnection(revision=0), runtime_scope).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(noncanonical,),
        )

    opaque = _compile_work_item(now)
    opaque_assignment = RuntimeAssignment.model_validate(
        {
            **opaque["assignment_binding_json"],
            "payload_ref": "FULL TENANT DOCUMENT BYTES",
            "payload_digest": "d" * 64,
        }
    )
    opaque.update(
        assignment_digest=opaque_assignment.assignment_digest,
        assignment_binding_json=opaque_assignment.model_dump(mode="json"),
        payload_ref=opaque_assignment.payload_ref,
        payload_digest=opaque_assignment.payload_digest,
    )
    with pytest.raises(PublicPayloadViolation, match="bounded opaque locator"):
        RuntimeJournalRepository(RecordingConnection(revision=0), runtime_scope).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(opaque,),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("assignment_binding_json", {"embedded_value": "secret"}),
        ("claim_binding_json", {"embedded_value": "secret"}),
    ],
)
def test_public_control_typed_binding_json_rejects_arbitrary_embedded_values(
    runtime_scope, field, value
):
    now = datetime.now(UTC)
    work_item = _compile_work_item(now)
    work_item[field] = value
    with pytest.raises(PublicPayloadViolation, match="invalid typed control binding"):
        RuntimeJournalRepository(
            RecordingConnection(revision=0), runtime_scope
        ).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(work_item,),
        )


def test_public_control_rejects_payload_ref_that_is_not_an_opaque_locator(
    runtime_scope,
) -> None:
    now = datetime.now(UTC)
    work_item = _compile_work_item(now)
    raw_assignment = dict(work_item["assignment_binding_json"])
    raw_assignment.update(
        payload_ref="FULL TENANT DOCUMENT BYTES THAT ARE NOT AN OPAQUE LOCATOR",
        payload_digest="e" * 64,
    )
    assignment = RuntimeAssignment.model_validate(raw_assignment)
    work_item.update(
        assignment_digest=assignment.assignment_digest,
        assignment_binding_json=assignment.model_dump(mode="json"),
        payload_ref=assignment.payload_ref,
        payload_digest=assignment.payload_digest,
    )
    with pytest.raises(PublicPayloadViolation, match="bounded opaque locator"):
        RuntimeJournalRepository(
            RecordingConnection(revision=0), runtime_scope
        ).commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(work_item,),
        )


def test_qualification_and_authorization_rows_rehash_exact_typed_bindings() -> None:
    now = datetime.now(UTC)
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="project-scope:project-a:3",
        source_digest="1" * 64,
        source_epoch=3,
    )
    context = AuthorityContext.from_content(
        actor_id="actor-a",
        project_key="project-a",
        resolved_schema="project_a",
        project_registry_revision=3,
        project_scope_digest="2" * 64,
        authority_source_bindings=(source,),
        grants_digest="3" * 64,
        grant_epoch=4,
        expires_at=now.replace(year=now.year + 1),
        operation_scope_digest="4" * 64,
        resource_ceiling_digest="5" * 64,
        canonical_base_revision=7,
        canonical_incarnation="canonical-incarnation-1",
        approval_refs=("approval-1",),
    )
    authorization = StepAuthorizationBinding.from_content(
        run_id="run-1",
        step_id="step-1",
        operation_kind="test.operation.v1",
        operation_contract_digest="9" * 64,
        capability_id="cap-a",
        claim_owner="successor",
        claim_authority_epoch=2,
        claim_policy_digest="a" * 64,
        payload_digest="b" * 64,
        actor_id="actor-a",
        project_key="project-a",
        project_registry_revision=3,
        project_scope_digest="2" * 64,
        interpreter_binding_digest="c" * 64,
        deployment_catalog_digest="d" * 64,
        authority_source_bindings=(source,),
        grants_digest="3" * 64,
        approval_refs=("approval-1",),
        resource_ceiling_digest="5" * 64,
        resource_policy_epoch=8,
        queue_eligibility_digest="7" * 64,
        grant_epoch=4,
        expires_at=now.replace(year=now.year + 1),
        canonical_base_revision=7,
        canonical_incarnation="canonical-incarnation-1",
    )
    authorization_row = {
        "authorization_id": "authorization-1",
        **authorization.model_dump(mode="json"),
        "expires_at": authorization.expires_at,
        "authorization_digest": authorization.binding_digest,
        "authority_source_bindings_json": [source.model_dump(mode="json")],
        "approval_refs_json": ["approval-1"],
        "authorization_binding_json": authorization.model_dump(mode="json"),
    }
    assert validate_authorization_row(authorization_row) == authorization
    with pytest.raises(ExactBindingConflict, match="duplicated-column drift"):
        validate_authorization_row(
            {**authorization_row, "interpreter_binding_digest": "e" * 64}
        )

    qualified_plan = QualifiedPlan.from_content(
        plan_digest="6" * 64,
        authority_context_digest=context.context_digest,
        step_bindings=(authorization,),
        awaiting_approval_steps=(),
        denied_steps=(),
    )
    qualification = ExactQualificationBinding.from_content(
        qualification_id="qualification-1",
        project_key="project-a",
        run_id="run-1",
        plan_id="plan-1",
        plan_digest="6" * 64,
        authority_context=context,
        authority_context_digest=context.context_digest,
        qualified_plan=qualified_plan,
        decision="QUALIFIED",
    )
    qualification_row = {
        "qualification_id": qualification.qualification_id,
        "project_key": qualification.project_key,
        "run_id": qualification.run_id,
        "plan_id": qualification.plan_id,
        "plan_digest": qualification.plan_digest,
        "authority_context_digest": qualification.authority_context_digest,
        "decision": qualification.decision,
        "qualification_digest": qualified_plan.qualification_digest,
        "qualification_binding_digest": (
            qualification.qualification_binding_digest
        ),
        "qualified_plan_json": qualified_plan.model_dump(mode="json"),
        "qualification_binding_json": qualification.model_dump(mode="json"),
    }
    assert validate_qualification_row(qualification_row) == qualification
    with pytest.raises(ExactBindingConflict, match="duplicated-column drift"):
        validate_qualification_row(
            {**qualification_row, "qualification_digest": "8" * 64}
        )
