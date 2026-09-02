from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import RuntimeClaim
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres import (
    reconciliation as postgres_reconciliation,
)
from app.successor_runtime.substrate.postgres.reconciliation import (
    PostgresReconciliationOwner,
    ReconciliationAdoptionError,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class _AllowCurrentTerminalAuthority:
    def require_current(self, **_kwargs: object) -> None:
        return None


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
                "required-readback" if self.required else "optional-readback"
            ),
        )


def _digest(label: str) -> str:
    return canonical_digest((label,))


def _tables() -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    runs = sa.Table(
        "runtime_runs",
        metadata,
        sa.Column("project_key", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("incarnation", sa.String),
        sa.Column("program_digest", sa.String),
        sa.Column("execution_epoch", sa.Integer),
        sa.Column("state", sa.String),
        sa.Column("revision", sa.Integer),
        sa.Column("next_event_seq", sa.Integer),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    steps = sa.Table(
        "runtime_steps",
        metadata,
        sa.Column("project_key", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("step_id", sa.String, primary_key=True),
        sa.Column("state", sa.String),
        sa.Column("revision", sa.Integer),
        sa.Column("execution_epoch", sa.Integer),
        sa.Column("input_digest", sa.String),
        sa.Column("output_digest", sa.String),
        sa.Column("failure_digest", sa.String),
        sa.Column("lease_token", sa.String),
        sa.Column("lease_owner", sa.String),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    attempts = sa.Table(
        "runtime_effect_attempts",
        metadata,
        sa.Column("project_key", sa.String, primary_key=True),
        sa.Column("attempt_id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String),
        sa.Column("step_id", sa.String),
        sa.Column("assignment_digest", sa.String),
        sa.Column("handler_binding_digest", sa.String),
        sa.Column("claim_binding_json", sa.JSON),
        sa.Column("claim_binding_digest", sa.String),
        sa.Column("disposition", sa.String),
        sa.Column("external_ref", sa.String),
        sa.Column("receipt_ref", sa.String),
        sa.Column("receipt_digest", sa.String),
        sa.Column("failure_ref", sa.String),
        sa.Column("failure_digest", sa.String),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    works = sa.Table(
        "runtime_work_items",
        metadata,
        sa.Column("project_key", sa.String, primary_key=True),
        sa.Column("work_item_id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String),
        sa.Column("step_id", sa.String),
        sa.Column("assignment_kind", sa.String),
        sa.Column("capability_id", sa.String),
        sa.Column("operation_contract_digest", sa.String),
        sa.Column("assignment_digest", sa.String),
        sa.Column("assignment_binding_json", sa.JSON),
        sa.Column("execution_epoch", sa.Integer),
        sa.Column("assignment_incarnation", sa.String),
        sa.Column("input_closure_digest", sa.String),
        sa.Column("claim_authority_epoch", sa.Integer),
        sa.Column("claim_policy_digest", sa.String),
        sa.Column("handler_binding_kind", sa.String),
        sa.Column("handler_binding_ref", sa.String),
        sa.Column("handler_binding_digest", sa.String),
        sa.Column("deployment_catalog_digest", sa.String),
        sa.Column("runtime_protocol_version", sa.String),
        sa.Column("interpreter_profile_digest", sa.String),
        sa.Column("required_node_profile_selector", sa.String),
        sa.Column("program_digest", sa.String),
        sa.Column("plan_digest", sa.String),
        sa.Column("qualification_digest", sa.String),
        sa.Column("expected_step_revision", sa.Integer),
        sa.Column("reconciliation_attempt_id", sa.String),
        sa.Column("payload_ref", sa.String),
        sa.Column("payload_digest", sa.String),
        sa.Column("resource_policy_epoch", sa.Integer),
        sa.Column("queue_eligibility_digest", sa.String),
        sa.Column("resource_policy_digest", sa.String),
        sa.Column("resource_class", sa.String),
        sa.Column("resource_units", sa.Integer),
        sa.Column("concurrency_key", sa.String),
        sa.Column("provider_key", sa.String),
        sa.Column("delivery_intent_ref", sa.String),
        sa.Column("fairness_key", sa.String),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("recovery_binding_json", sa.JSON),
        sa.Column("recovery_handler_binding_ref", sa.String),
        sa.Column("recovery_handler_binding_digest", sa.String),
        sa.Column("authoritative_readback_profile_ref", sa.String),
        sa.Column("authority_digest", sa.String),
        sa.Column("state", sa.String),
        sa.Column("wait_reason", sa.String),
        sa.Column("declared_priority", sa.Integer),
        sa.Column("enqueued_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer),
        sa.Column("revision", sa.Integer),
        sa.Column("lease_token", sa.String),
        sa.Column("lease_owner", sa.String),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("claim_binding_json", sa.JSON),
        sa.Column("claim_binding_digest", sa.String),
        sa.Column("last_failure_ref", sa.String),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    events = sa.Table(
        "runtime_events",
        metadata,
        sa.Column("project_key", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("seq", sa.Integer, primary_key=True),
        sa.Column("event_type", sa.String),
        sa.Column("schema_version", sa.String),
        sa.Column("step_id", sa.String),
        sa.Column("attempt_id", sa.String),
        sa.Column("event_metadata_json", sa.JSON),
        sa.Column("authority_digest", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    return {table.name: table for table in (runs, steps, attempts, works, events)}


def _effect_assignment(recovery: RecoveryBinding) -> RuntimeAssignment:
    operation_digest = _digest("operation")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        deployment_catalog_digest=_digest("catalog"),
        runtime_protocol_version="1",
        project_scope_digest=_digest("scope"),
        resource_policy_epoch=1,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-original",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="project-1",
        run_id="run-1",
        step_id="step-1",
        step_role=CompiledStepRole.EFFECT,
        capability_id="capability-1",
        operation_contract_ref=OperationContractRef(
            kind="fixture.operation.v1",
            contract_version="1",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "fixture.return.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
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
        execution_epoch=1,
        incarnation="run-incarnation-1",
        input_refs=("value:1",),
        input_closure_digest=_digest("input"),
        queue_eligibility_digest=_digest("eligibility"),
        resource_policy_epoch=1,
        claim_authority_epoch=2,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace-1",
    )


def _recovery_assignment(
    original: RuntimeAssignment,
    recovery: RecoveryBinding,
    target_attempt_id: str,
) -> RuntimeAssignment:
    values = original.model_dump(mode="python")
    values.update(
        work_item_id="work-reconcile",
        assignment_kind=AssignmentKind.RECONCILE,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        expected_step_revision=4,
        reconciliation_attempt_id=target_attempt_id,
    )
    return RuntimeAssignment(**values)


def _work_values(
    assignment: RuntimeAssignment,
    *,
    state: str,
    revision: int,
    claim: ClaimBinding | None,
    recovery: RecoveryBinding,
) -> dict[str, object]:
    handler = assignment.handler_binding
    values: dict[str, object] = {
        "project_key": assignment.project_key,
        "work_item_id": assignment.work_item_id,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "assignment_kind": assignment.assignment_kind.value,
        "capability_id": assignment.capability_id,
        "operation_contract_digest": assignment.operation_contract_digest,
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
        "interpreter_profile_digest": handler.interpreter_profile_digest,
        "required_node_profile_selector": "node-profile:reconcile",
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "qualification_digest": _digest("qualification"),
        "expected_step_revision": assignment.expected_step_revision,
        "reconciliation_attempt_id": assignment.reconciliation_attempt_id,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "resource_policy_digest": _digest("resource-policy"),
        "resource_class": None,
        "resource_units": None,
        "concurrency_key": None,
        "provider_key": None,
        "delivery_intent_ref": None,
        "fairness_key": "project-1:reconcile",
        "deadline_at": assignment.deadline_at,
        "recovery_binding_json": None,
        "recovery_handler_binding_ref": None,
        "recovery_handler_binding_digest": None,
        "authoritative_readback_profile_ref": (
            recovery.authoritative_readback_profile_ref
        ),
        "authority_digest": _digest("authorization"),
        "state": state,
        "wait_reason": "BACKOFF" if state == "WAITING" else None,
        "declared_priority": 0,
        "enqueued_at": NOW,
        "due_at": NOW,
        "attempt_count": 0,
        "revision": revision,
        "lease_token": None if claim is None else claim.lease_token,
        "lease_owner": None if claim is None else claim.node_id,
        "lease_expires_at": None if claim is None else claim.lease_expires_at,
        "claim_binding_json": (
            None if claim is None else claim.model_dump(mode="json")
        ),
        "claim_binding_digest": None if claim is None else claim.binding_digest,
        "last_failure_ref": None,
        "updated_at": NOW,
    }
    if assignment.assignment_kind is AssignmentKind.INTERPRET:
        values.update(
            recovery_binding_json=recovery.model_dump(mode="json"),
            recovery_handler_binding_ref=(
                f"handler-binding:sha256:{recovery.binding_digest}"
            ),
            recovery_handler_binding_digest=recovery.binding_digest,
        )
    return values


@pytest.fixture
def adoption_store(monkeypatch: pytest.MonkeyPatch):
    tables = _tables()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    next(iter(tables.values())).metadata.create_all(engine)
    monkeypatch.setattr(postgres_reconciliation, "_table", tables.__getitem__)
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="authoritative-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=_digest("interpreter-profile"),
        authoritative_readback_profile_ref="readback-profile:1",
    )
    original = _effect_assignment(recovery)
    original_claim = ClaimBinding.bind(
        original,
        authorization_digest=_digest("authorization"),
        lease_token="lease-original",
        lease_expires_at=NOW + timedelta(minutes=1),
        node_id="node-previous",
        node_profile_digest=_digest("old-node-profile"),
        authority_digest=_digest("authorization"),
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        execution_reservation_ref="reservation:original",
        execution_reservation_digest=_digest("reservation"),
    )
    target_attempt_id = original_claim.attempt_id
    assignment = _recovery_assignment(original, recovery, target_attempt_id)
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease-reconcile",
        lease_expires_at=NOW + timedelta(minutes=2),
        node_id="runtime-node",
        node_profile_digest=_digest("node-profile"),
        authority_digest=_digest("authorization"),
        interpreter_profile_digest=recovery.interpreter_profile_digest,
    )
    runtime_claim = RuntimeClaim(
        assignment=assignment,
        claim_binding=claim,
        work_item_revision=2,
    )
    with engine.begin() as connection:
        connection.execute(
            tables["runtime_runs"]
            .insert()
            .values(
                project_key="project-1",
                run_id="run-1",
                incarnation="run-incarnation-1",
                program_digest=_digest("program"),
                execution_epoch=1,
                state="RECONCILING",
                revision=7,
                next_event_seq=10,
                updated_at=NOW,
            )
        )
        connection.execute(
            tables["runtime_steps"]
            .insert()
            .values(
                project_key="project-1",
                run_id="run-1",
                step_id="step-1",
                state="RECONCILING",
                revision=5,
                execution_epoch=1,
                input_digest=_digest("input"),
                lease_token=claim.lease_token,
                lease_owner=claim.node_id,
                lease_expires_at=claim.lease_expires_at,
                updated_at=NOW,
            )
        )
        connection.execute(
            tables["runtime_work_items"].insert(),
            [
                _work_values(
                    original,
                    state="COMPLETED",
                    revision=4,
                    claim=original_claim,
                    recovery=recovery,
                ),
                _work_values(
                    assignment,
                    state="CLAIMED",
                    revision=2,
                    claim=claim,
                    recovery=recovery,
                ),
            ],
        )
        connection.execute(
            tables["runtime_effect_attempts"]
            .insert()
            .values(
                project_key="project-1",
                attempt_id=target_attempt_id,
                run_id="run-1",
                step_id="step-1",
                assignment_digest=original.assignment_digest,
                handler_binding_digest=original.handler_binding_digest,
                claim_binding_json=original_claim.model_dump(mode="json"),
                claim_binding_digest=original_claim.binding_digest,
                disposition="OUTCOME_UNKNOWN",
                revision=3,
                updated_at=NOW,
            )
        )
    return engine, tables, runtime_claim


@pytest.mark.parametrize(
    ("disposition", "required"),
    [
        (EffectDisposition.SUCCEEDED, True),
        (EffectDisposition.FAILED, True),
        (EffectDisposition.FAILED, False),
    ],
)
def test_resolved_readback_is_adopted_once_without_new_attempt(
    adoption_store, disposition: EffectDisposition, required: bool
) -> None:
    engine, tables, claim = adoption_store
    success = disposition is EffectDisposition.SUCCEEDED
    readback = AuthoritativeEffectReadback(
        attempt_id=claim.assignment.reconciliation_attempt_id,
        disposition=disposition,
        provider_locator="provider:receipt" if success else None,
        receipt_digest=_digest("receipt") if success else None,
        failure_digest=_digest("failure") if not success else None,
        observation_digest=_digest("observation"),
    )
    outcome = ReconciliationHandlerOutcome(
        result=ReconciliationResult(
            state=ReconciliationState.RESOLVED,
            attempt_id=claim.assignment.reconciliation_attempt_id,
            disposition=disposition,
            readback=readback,
        ),
        output_digest=_digest("output") if success else None,
        receipt_ref="receipt:authoritative" if success else None,
    )
    with engine.begin() as connection:
        owner = PostgresReconciliationOwner(
            connection,
            terminal_authority=_AllowCurrentTerminalAuthority(),
            failure_policy=_StaticFailurePolicy(required=required),
        )
        owner.adopt(
            claim=claim,
            outcome=outcome,
            actor_id="runtime-node",
            observed_at=NOW + timedelta(seconds=1),
        )
        with pytest.raises(ReconciliationAdoptionError):
            owner.adopt(
                claim=claim,
                outcome=outcome,
                actor_id="runtime-node",
                observed_at=NOW + timedelta(seconds=2),
            )

    with engine.connect() as connection:
        attempts = (
            connection.execute(sa.select(tables["runtime_effect_attempts"]))
            .mappings()
            .all()
        )
        assert len(attempts) == 1
        assert attempts[0]["disposition"] == disposition.value
        original = (
            connection.execute(
                sa.select(tables["runtime_work_items"]).where(
                    tables["runtime_work_items"].c.work_item_id == "work-original"
                )
            )
            .mappings()
            .one()
        )
        recovery = (
            connection.execute(
                sa.select(tables["runtime_work_items"]).where(
                    tables["runtime_work_items"].c.work_item_id == "work-reconcile"
                )
            )
            .mappings()
            .one()
        )
        step = connection.execute(sa.select(tables["runtime_steps"])).mappings().one()
        run = connection.execute(sa.select(tables["runtime_runs"])).mappings().one()
        events = (
            connection.execute(
                sa.select(tables["runtime_events"]).order_by(
                    tables["runtime_events"].c.seq
                )
            )
            .mappings()
            .all()
        )
        event = events[0]
        assert original["state"] == ("COMPLETED" if success else "FAILED")
        assert recovery["state"] == "COMPLETED"
        assert step["state"] == ("SUCCEEDED" if success else "FAILED")
        assert run["state"] == (
            "RUNNING" if success else ("FAILED" if required else "RECONCILING")
        )
        assert event["event_type"] == (
            "AuthoritativeReadbackSucceeded"
            if success
            else "AuthoritativeReadbackFailed"
        )
        assert event["event_metadata_json"]["observation_digest"] == _digest(
            "observation"
        )
        assert event["event_metadata_json"]["required_step_failed"] is (
            not success and required
        )
        if not success and required:
            assert [item["event_type"] for item in events] == [
                "AuthoritativeReadbackFailed",
                "RequiredStepFailed",
            ]
            assert events[1]["event_metadata_json"]["source_event_digest"]
        else:
            assert len(events) == 1


def test_waiting_preserves_target_and_creates_revision_exact_successor(
    adoption_store,
) -> None:
    engine, tables, claim = adoption_store
    outcome = ReconciliationHandlerOutcome(
        result=ReconciliationResult(
            state=ReconciliationState.WAITING,
            attempt_id=claim.assignment.reconciliation_attempt_id,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            readback=AuthoritativeEffectReadback(
                attempt_id=claim.assignment.reconciliation_attempt_id,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                observation_digest=_digest("waiting-observation"),
                reason="PROVIDER_PENDING",
            ),
            wait_reason="PROVIDER_PENDING",
        )
    )
    with engine.begin() as connection:
        PostgresReconciliationOwner(
            connection,
            terminal_authority=_AllowCurrentTerminalAuthority(),
            failure_policy=_StaticFailurePolicy(required=True),
        ).adopt(
            claim=claim,
            outcome=outcome,
            actor_id="runtime-node",
            observed_at=NOW + timedelta(seconds=1),
        )

    with engine.connect() as connection:
        attempt = (
            connection.execute(sa.select(tables["runtime_effect_attempts"]))
            .mappings()
            .one()
        )
        step = connection.execute(sa.select(tables["runtime_steps"])).mappings().one()
        work = (
            connection.execute(
                sa.select(tables["runtime_work_items"]).where(
                    tables["runtime_work_items"].c.work_item_id == "work-reconcile"
                )
            )
            .mappings()
            .one()
        )
        run = connection.execute(sa.select(tables["runtime_runs"])).mappings().one()
        successor = (
            connection.execute(
                sa.select(tables["runtime_work_items"]).where(
                    tables["runtime_work_items"].c.work_item_id != "work-original",
                    tables["runtime_work_items"].c.work_item_id != "work-reconcile",
                )
            )
            .mappings()
            .one()
        )
        successor_assignment = RuntimeAssignment.model_validate(
            successor["assignment_binding_json"]
        )
        assert attempt["disposition"] == "OUTCOME_UNKNOWN"
        assert attempt["revision"] == 3
        assert step["state"] == "WAITING_EXTERNAL"
        assert work["state"] == "SUPERSEDED"
        assert work["wait_reason"] is None
        assert successor["state"] == "READY"
        assert successor["expected_step_revision"] == step["revision"]
        assert successor_assignment.expected_step_revision == step["revision"]
        assert successor_assignment.reconciliation_attempt_id == attempt["attempt_id"]
        assert successor["assignment_digest"] == successor_assignment.assignment_digest
        assert run["state"] == "RECONCILING"
