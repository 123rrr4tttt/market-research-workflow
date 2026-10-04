"""PostgreSQL C1 Slice A/B/C RuntimeNode/restart/replay/rollback acceptance.

Each acceptance drives the exact slice Program/Plan through the production
``RuntimeNode`` + ``PostgresRuntimeNodeAdapter`` lifecycle and then binds the
durable runtime receipts, ordered event chain, replay digest, and future-owner
rollback evidence into ``C1RuntimeEvidenceRefs`` / ``C1RollbackBeforeAfter``.
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities.c1_slice_acceptance import (
    C1NamedStepObservation,
    C1RollbackBeforeAfter,
    C1RuntimeEvidenceRefs,
    C1StepStatus,
    accept_c1_slice,
)
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.runtime.replay import (
    RuntimeReplayError,
    replay_runtime_events,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
    runtime_uow_factory,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.research_ledger import (
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RuntimeJournalRepository,
    StaleRevisionError,
    validate_runtime_assignment_row,
)
from app.successor_runtime.substrate.postgres.work_items import (
    ClaimBindingMismatch,
    WorkItemClaimRepository,
)

from .c1_slice_postgres_fixture import (
    AUTHORITY_EPOCH,
    DEPLOYMENT_CATALOG_DIGEST,
    NODE_PROFILE_DIGEST,
    NOW,
    C1Database,
    PreparedC1Slice,
    _C1TypedFailureHandler,
    derive_run_completion,
    inject_run_aba_cycle,
    load_replay_events,
    make_node,
    prepare_runtime,
    replay_digest,
    require_old_authority_fails_closed,
    rollback_future_owner,
    run_to_idle,
    snapshot_attempts,
    snapshot_journal,
    snapshot_plan,
    snapshot_program,
    snapshot_receipts,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.successor_runtime.c1_slice_postgres_fixture",)


def _tag() -> str:
    return secrets.token_hex(4)


def _observations(
    prepared: PreparedC1Slice,
) -> tuple[C1NamedStepObservation, ...]:
    outcomes = prepared.handler.outcomes
    assert len(outcomes) == len(prepared.steps)
    return tuple(
        C1NamedStepObservation(
            name=f"step-{index}:{step.step_kind.lower()}",
            step_id=step.step_id,
            status=C1StepStatus.SUCCESS,
            result_digest=outcomes[step.step_id][0],
            evidence_ref=outcomes[step.step_id][1],
        )
        for index, step in enumerate(prepared.plan.ordered_steps)
    )


def _evidence_refs(
    prepared: PreparedC1Slice,
    replay_digest_value: str,
) -> tuple[C1RuntimeEvidenceRefs, C1RollbackBeforeAfter]:
    receipts = tuple(
        prepared.handler.outcomes[step.step_id][1] for step in prepared.steps
    )
    journal_ref = f"journal:{prepared.run_id}"
    readback_ref = f"readback:{prepared.run_id}"
    runtime_evidence = C1RuntimeEvidenceRefs(
        runtime_evidence_refs=receipts,
        journal_refs=(journal_ref,),
        readback_refs=(readback_ref,),
        replay_refs=(f"replay:sha256:{replay_digest_value}",),
    )
    rollback = C1RollbackBeforeAfter(
        rollback_ref=f"rollback:{prepared.run_id}:future-owner",
        before_authority_epoch=prepared.authority_epoch,
        after_authority_epoch=prepared.authority_epoch + 1,
        before_journal_refs=(journal_ref,),
        after_journal_refs=(journal_ref,),
        before_readback_refs=(readback_ref,),
        after_readback_refs=(readback_ref,),
    )
    return runtime_evidence, rollback


def _accept(
    prepared: PreparedC1Slice,
    replay_digest_value: str,
) -> Any:
    runtime_evidence, rollback = _evidence_refs(prepared, replay_digest_value)
    observations = _observations(prepared)
    return accept_c1_slice(
        in_slice_id=prepared.slice_id,
        in_program=prepared.program,
        in_plan=prepared.plan,
        in_legacy_step_observations=observations,
        in_successor_step_observations=observations,
        in_runtime_evidence=runtime_evidence,
        in_rollback_before_after=rollback,
    )


def _claim_context(prepared: PreparedC1Slice, node_id: str) -> dict[str, Any]:
    return {
        "control_scope": ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=prepared.authority_epoch,
        ),
        "node": NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}:incarnation:1",
            started_at=NOW - timedelta(minutes=1),
        ),
        "profile": RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset(
                {
                    AssignmentKind.INTERPRET,
                    AssignmentKind.VERIFY_ADMIT,
                    AssignmentKind.RECONCILE,
                }
            ),
            interpreter_profile_digests=prepared.interpreter_profile_digests,
        ),
        "deployment": DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        "protocol": RuntimeNodeProtocol(version="1", claim_batch_size=1),
        "limit": 1,
        "observed_at": NOW,
    }


@pytest.mark.parametrize("slice_id", ["A", "B", "C"])
def test_c1_slice_runtime_node_replay_restart_and_rollback(
    c1_database: C1Database,
    slice_id: str,
) -> None:
    prepared = prepare_runtime(
        c1_database,
        slice_id=slice_id,
        project_key=f"c1-slice-{slice_id.lower()}-main",
        tag=_tag(),
        run_suffix="main",
        authority_epoch=AUTHORITY_EPOCH,
    )
    reports = run_to_idle(prepared)
    assert derive_run_completion(c1_database, prepared)
    assert reports
    assert {node_id for node_id, _step, _attempt in prepared.handler.executions} == {
        "c1-slice-node-a",
        "c1-slice-node-b",
    }
    assert len(
        {attempt for _node, _step, attempt in prepared.handler.executions}
    ) == len(prepared.assignments)
    assert all(result.committed for report in reports for result in report.results)

    events = load_replay_events(c1_database, prepared)
    assert events[0].event_type == "ProgramAccepted"
    assert events[0].seq == 1
    assert events[-1].event_type == "RunCompletionDerived"
    assert tuple(event.seq for event in events) == tuple(range(1, len(events) + 1))
    first_digest = replay_digest(c1_database, prepared)

    before_program = snapshot_program(c1_database, prepared)
    before_plan = snapshot_plan(c1_database, prepared)
    before_journal = snapshot_journal(c1_database, prepared)
    before_attempts = snapshot_attempts(c1_database, prepared)
    before_receipts = snapshot_receipts(c1_database, prepared)
    rollback_future_owner(c1_database, prepared)
    assert snapshot_program(c1_database, prepared) == before_program
    assert snapshot_plan(c1_database, prepared) == before_plan
    assert snapshot_journal(c1_database, prepared) == before_journal
    assert snapshot_attempts(c1_database, prepared) == before_attempts
    assert snapshot_receipts(c1_database, prepared) == before_receipts
    require_old_authority_fails_closed(c1_database, prepared)

    c1_database.engine.dispose()
    restarted = c1_database.fresh_engine()
    try:
        with restarted.connect() as connection:
            exact_program = ProgramRepository(
                connection,
                prepared.tables,
            ).get(
                prepared.scope,
                prepared.program.program_id,
                expected_digest=prepared.program.program_digest,
            )
            exact_plan = PlanRepository(connection, prepared.tables).get(
                prepared.scope,
                prepared.plan.plan_digest,
            )
        assert exact_program.program_digest == prepared.program.program_digest
        assert exact_plan.plan_digest == prepared.plan.plan_digest
        assert exact_program.canonical_json() == prepared.program.canonical_json()
        assert canonical_bytes(exact_plan) == canonical_bytes(prepared.plan)
    finally:
        restarted.dispose()

    second_digest = replay_digest(c1_database, prepared)
    assert second_digest == first_digest

    acceptance = _accept(prepared, second_digest)
    assert acceptance.accepted
    assert acceptance.program_digest == prepared.program.program_digest
    assert acceptance.plan_digest == prepared.plan.plan_digest
    assert acceptance.rollback_before_authority_epoch == AUTHORITY_EPOCH
    assert acceptance.rollback_after_authority_epoch == AUTHORITY_EPOCH + 1
    assert _accept(prepared, second_digest).acceptance_digest == (
        acceptance.acceptance_digest
    )

    observations = _observations(prepared)
    runtime_evidence, rollback = _evidence_refs(prepared, second_digest)
    in_slice = {
        "program": prepared.program,
        "plan": prepared.plan,
        "observations": observations,
        "authority_epoch": prepared.authority_epoch,
    }
    out_runtime = {
        "receipts": tuple(
            prepared.handler.outcomes[step.step_id][1] for step in prepared.steps
        ),
        "event_chain": tuple(
            (event.seq, event.event_type, event.event_digest) for event in events
        ),
        "replay": second_digest,
        "rollback": rollback,
    }
    acceptance_from_module_vars = accept_c1_slice(
        in_slice_id=prepared.slice_id,
        in_program=in_slice["program"],
        in_plan=in_slice["plan"],
        in_legacy_step_observations=in_slice["observations"],
        in_successor_step_observations=in_slice["observations"],
        in_runtime_evidence=runtime_evidence,
        in_rollback_before_after=out_runtime["rollback"],
    )
    assert out_runtime["replay"] == second_digest
    assert len(out_runtime["receipts"]) == len(prepared.steps)
    assert acceptance_from_module_vars == acceptance

    node_a = make_node(prepared, "c1-slice-node-a")
    node_b = make_node(prepared, "c1-slice-node-b")
    assert type(node_a) is type(node_b) is RuntimeNode
    assert node_a.profile == node_b.profile
    assert node_a.deployment == node_b.deployment

    attempts = snapshot_attempts(c1_database, prepared)
    assert len(attempts) == len(prepared.assignments)
    assert all(item["disposition"] == "SUCCEEDED" for item in attempts)
    assert all(
        item["receipt_ref"] is not None
        and item["receipt_ref"].startswith("receipt:sha256:")
        for item in attempts
    )


def test_c1_cross_slice_no_duplicate_effects_and_project_isolation(
    c1_database: C1Database,
) -> None:
    slice_a = prepare_runtime(
        c1_database,
        slice_id="A",
        project_key="c1-slice-a-iso",
        tag=_tag(),
        run_suffix="iso",
    )
    slice_b = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key="c1-slice-b-iso",
        tag=_tag(),
        run_suffix="iso",
    )

    node_a = make_node(slice_a, "c1-slice-node-a")
    first = node_a.run_once()
    assert first.claimed == 1
    assert first.results[0].committed
    assert first.results[0].work_item_id.startswith(
        f"work:run:{slice_a.project_key}:iso:"
    )

    with c1_database.engine.connect() as connection:
        remaining_b = connection.scalar(
            sa.text(
                "SELECT count(*) FROM public.runtime_work_items "
                "WHERE project_key=:project_key AND state='READY'"
            ),
            {"project_key": slice_b.project_key},
        )
    assert remaining_b == len(slice_b.assignments)
    executions_before = len(slice_a.handler.executions)

    run_to_idle(slice_b)
    assert len(slice_a.handler.executions) == executions_before

    with c1_database.engine.connect() as connection:
        with pytest.raises(ProjectRecordNotFound):
            ProgramRepository(connection, slice_a.tables).get(
                slice_a.scope,
                slice_b.program.program_id,
                expected_digest=slice_b.program.program_digest,
            )
        with pytest.raises(ProjectRecordNotFound):
            PlanRepository(connection, slice_a.tables).get(
                slice_a.scope,
                slice_b.plan.plan_digest,
            )

    with c1_database.engine.begin() as connection:
        plan_compiled = (
            connection.execute(
                sa.text(
                    "SELECT * FROM public.runtime_events "
                    "WHERE project_key=:project_key AND run_id=:run_id "
                    "AND event_type='PlanCompiled'"
                ),
                {
                    "project_key": slice_a.project_key,
                    "run_id": slice_a.run_id,
                },
            )
            .mappings()
            .one()
        )
        forged_metadata = dict(plan_compiled["event_metadata_json"])
        forged_metadata["plan_digest"] = "0" * 64
        connection.execute(
            sa.text(
                "UPDATE public.runtime_events SET "
                "event_metadata_json=CAST(:metadata AS jsonb) "
                "WHERE project_key=:project_key AND run_id=:run_id AND seq=:seq"
            ),
            {
                "metadata": json.dumps(forged_metadata),
                "project_key": slice_a.project_key,
                "run_id": slice_a.run_id,
                "seq": int(plan_compiled["seq"]),
            },
        )
        connection.execute(
            sa.text(
                "UPDATE "
                f'"{slice_a.resolved_schema}".research_execution_plans '
                "SET plan_digest=:tampered "
                "WHERE project_key=:project_key AND plan_digest=:original"
            ),
            {
                "tampered": "0" * 64,
                "project_key": slice_a.project_key,
                "original": slice_a.plan.plan_digest,
            },
        )
        tampered_work = (
            connection.execute(
                sa.text(
                    "SELECT * FROM public.runtime_work_items "
                    "WHERE project_key=:project_key AND run_id=:run_id "
                    "ORDER BY work_item_id LIMIT 1"
                ),
                {
                    "project_key": slice_a.project_key,
                    "run_id": slice_a.run_id,
                },
            )
            .mappings()
            .one()
        )
        forged_assignment = dict(tampered_work["assignment_binding_json"])
        forged_assignment["plan_digest"] = "0" * 64
        connection.execute(
            sa.text(
                "UPDATE public.runtime_work_items SET "
                "assignment_binding_json=CAST(:binding AS jsonb) "
                "WHERE project_key=:project_key AND work_item_id=:work_item_id"
            ),
            {
                "binding": json.dumps(forged_assignment),
                "project_key": slice_a.project_key,
                "work_item_id": tampered_work["work_item_id"],
            },
        )
        tampered_work = (
            connection.execute(
                sa.text(
                    "SELECT * FROM public.runtime_work_items "
                    "WHERE project_key=:project_key AND work_item_id=:work_item_id"
                ),
                {
                    "project_key": slice_a.project_key,
                    "work_item_id": tampered_work["work_item_id"],
                },
            )
            .mappings()
            .one()
        )

    with pytest.raises(RuntimeReplayError):
        replay_digest(c1_database, slice_a)
    with c1_database.engine.connect() as connection:
        with pytest.raises(ProjectRecordNotFound):
            PlanRepository(connection, slice_a.tables).get(
                slice_a.scope,
                slice_a.plan.plan_digest,
            )
        with pytest.raises(ExactBindingConflict):
            validate_runtime_assignment_row(tampered_work)


def test_c1_rollback_retains_journal_and_changes_future_owner_epoch(
    c1_database: C1Database,
) -> None:
    project_key = "c1-slice-b-rollback"
    tag = _tag()
    prepared = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key=project_key,
        tag=tag,
        run_suffix="old",
        authority_epoch=AUTHORITY_EPOCH,
    )
    run_to_idle(prepared)

    before_program = snapshot_program(c1_database, prepared)
    before_plan = snapshot_plan(c1_database, prepared)
    before_journal = snapshot_journal(c1_database, prepared)
    before_attempts = snapshot_attempts(c1_database, prepared)
    before_receipts = snapshot_receipts(c1_database, prepared)
    before_epoch = prepared.authority_epoch

    _before_rows, _after_rows = rollback_future_owner(c1_database, prepared)
    assert snapshot_program(c1_database, prepared) == before_program
    assert snapshot_plan(c1_database, prepared) == before_plan
    assert snapshot_journal(c1_database, prepared) == before_journal
    assert snapshot_attempts(c1_database, prepared) == before_attempts
    assert snapshot_receipts(c1_database, prepared) == before_receipts
    require_old_authority_fails_closed(c1_database, prepared)

    future = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key=project_key,
        tag=tag,
        run_suffix="future",
        authority_epoch=before_epoch + 1,
    )
    assert future.program.program_digest == prepared.program.program_digest
    assert future.plan.plan_digest == prepared.plan.plan_digest
    assert future.program.canonical_json() == prepared.program.canonical_json()
    assert canonical_bytes(future.plan) == canonical_bytes(prepared.plan)
    run_to_idle(future, authority_epoch=before_epoch + 1)
    assert derive_run_completion(c1_database, future)
    assert replay_digest(c1_database, future)
    assert snapshot_journal(c1_database, prepared) == before_journal

    with c1_database.engine.connect() as connection:
        rows = (
            connection.execute(
                sa.text(
                    "SELECT capability_id, authority_epoch, revision "
                    "FROM public.runtime_capability_authority "
                    "WHERE project_key=:project_key ORDER BY capability_id"
                ),
                {"project_key": project_key},
            )
            .mappings()
            .all()
        )
    assert rows
    assert all(int(row["authority_epoch"]) == before_epoch + 1 for row in rows)


def test_c1_outcome_unknown_reconciles_without_duplicate_effect(
    c1_database: C1Database,
) -> None:
    prepared = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key="c1-slice-b-outcome",
        tag=_tag(),
        run_suffix="unknown",
    )
    adapter = PostgresRuntimeNodeAdapter(runtime_uow_factory(c1_database.engine))
    claimed = adapter.claim_due(**_claim_context(prepared, "c1-unknown-node"))
    assert len(claimed) == 1
    target_step_id = claimed[0].assignment.step_id
    assert target_step_id is not None
    in_flight = adapter.begin_in_flight(
        control_scope=_claim_context(prepared, "c1-unknown-node")["control_scope"],
        claim=claimed[0],
        expected_revision=claimed[0].work_item_revision,
        started_at=NOW,
    )
    assert in_flight.effect_disposition is EffectDisposition.IN_FLIGHT

    other_assignment = next(
        assignment
        for assignment in prepared.assignments
        if assignment.step_id != target_step_id
    )
    with c1_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.runtime_work_items SET state='COMPLETED' "
                "WHERE project_key=:project_key AND work_item_id=:work_item_id"
            ),
            {
                "project_key": prepared.project_key,
                "work_item_id": other_assignment.work_item_id,
            },
        )
    loser = PostgresRuntimeNodeAdapter(runtime_uow_factory(c1_database.engine))
    assert loser.claim_due(**_claim_context(prepared, "c1-slice-node-b")) == ()

    with c1_database.engine.begin() as connection:
        reaped = WorkItemClaimRepository(connection).reap_expired(
            ControlPlaneScope(
                system_actor_id="c1-reaper",
                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                authority_epoch=prepared.authority_epoch,
            ),
            now=NOW + timedelta(minutes=2),
        )
    assert reaped == (in_flight.assignment.work_item_id,)

    with c1_database.engine.connect() as connection:
        original_work = (
            connection.execute(
                sa.text(
                    "SELECT state, wait_reason FROM public.runtime_work_items "
                    "WHERE work_item_id=:work_item_id"
                ),
                {"work_item_id": in_flight.assignment.work_item_id},
            )
            .mappings()
            .one()
        )
        attempt = (
            connection.execute(
                sa.text(
                    "SELECT disposition FROM public.runtime_effect_attempts "
                    "WHERE attempt_id=:attempt_id"
                ),
                {"attempt_id": in_flight.claim_binding.attempt_id},
            )
            .mappings()
            .one()
        )
        reconcile = (
            connection.execute(
                sa.text(
                    "SELECT state, reconciliation_attempt_id "
                    "FROM public.runtime_work_items "
                    "WHERE project_key=:project_key AND run_id=:run_id "
                    "AND assignment_kind='RECONCILE' AND state='READY'"
                ),
                {
                    "project_key": prepared.project_key,
                    "run_id": prepared.run_id,
                },
            )
            .mappings()
            .one()
        )
    assert original_work == {"state": "WAITING", "wait_reason": "BACKOFF"}
    assert attempt["disposition"] == "OUTCOME_UNKNOWN"
    assert reconcile["reconciliation_attempt_id"] == in_flight.claim_binding.attempt_id

    executions_before = len(prepared.handler.executions)
    reconcile_node = make_node(
        prepared,
        "c1-reconcile-node",
        clock_start=NOW + timedelta(minutes=3),
    )
    reconcile_report = reconcile_node.run_once()
    assert reconcile_report.claimed == 1
    result = reconcile_report.results[0]
    assert result.committed
    assert result.executed is False
    assert result.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert len(prepared.handler.executions) == executions_before
    assert not any(
        step_id == target_step_id
        for _node, step_id, _attempt in prepared.handler.executions
    )

    with c1_database.engine.connect() as connection:
        target_attempts = (
            connection.execute(
                sa.text(
                    "SELECT disposition FROM public.runtime_effect_attempts "
                    "WHERE attempt_id=:attempt_id AND project_key=:project_key"
                ),
                {
                    "attempt_id": in_flight.claim_binding.attempt_id,
                    "project_key": prepared.project_key,
                },
            )
            .mappings()
            .all()
        )
        original_state = (
            connection.execute(
                sa.text(
                    "SELECT state, assignment_kind FROM public.runtime_work_items "
                    "WHERE work_item_id=:work_item_id AND project_key=:project_key"
                ),
                {
                    "work_item_id": in_flight.assignment.work_item_id,
                    "project_key": prepared.project_key,
                },
            )
            .mappings()
            .all()
        )
    assert len(target_attempts) == 1
    assert target_attempts[0]["disposition"] == "OUTCOME_UNKNOWN"
    assert original_state[0]["state"] == "WAITING"
    assert original_state[0]["assignment_kind"] == "INTERPRET"

    first_digest = replay_digest(c1_database, prepared)
    second_digest = replay_digest(c1_database, prepared)
    assert second_digest == first_digest


def test_c1_cancellation_is_observed_without_duplicate_effect(
    c1_database: C1Database,
) -> None:
    # movement binding: C1-M003
    prepared = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key="c1-slice-b-cancel",
        tag=_tag(),
        run_suffix="cancel",
    )
    baseline_journal = snapshot_journal(c1_database, prepared)
    with c1_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.runtime_runs SET cancellation_requested=true "
                "WHERE project_key=:project_key AND run_id=:run_id"
            ),
            {
                "project_key": prepared.project_key,
                "run_id": prepared.run_id,
            },
        )
        observed = connection.scalar(
            sa.text(
                "SELECT cancellation_requested FROM public.runtime_runs "
                "WHERE project_key=:project_key AND run_id=:run_id"
            ),
            {
                "project_key": prepared.project_key,
                "run_id": prepared.run_id,
            },
        )
    assert observed is True

    node_a = make_node(prepared, "c1-slice-node-a")
    with pytest.raises(ClaimBindingMismatch) as exc_info:
        node_a.run_once()
    assert "cancellation" in str(exc_info.value)

    assert prepared.handler.executions == []
    assert snapshot_attempts(c1_database, prepared) == ()
    assert snapshot_journal(c1_database, prepared) == baseline_journal
    baseline_types = {row["event_type"] for row in baseline_journal}
    assert "RunCompletionDerived" not in baseline_types
    assert "EffectFailed" not in baseline_types
    assert "CancellationRequested" not in baseline_types

    with c1_database.engine.connect() as connection:
        run_state = connection.scalar(
            sa.text(
                "SELECT state FROM public.runtime_runs "
                "WHERE project_key=:project_key AND run_id=:run_id"
            ),
            {
                "project_key": prepared.project_key,
                "run_id": prepared.run_id,
            },
        )
        step_states = tuple(
            connection.scalars(
                sa.text(
                    "SELECT state FROM public.runtime_steps "
                    "WHERE project_key=:project_key AND run_id=:run_id "
                    "ORDER BY step_id"
                ),
                {
                    "project_key": prepared.project_key,
                    "run_id": prepared.run_id,
                },
            )
        )
    assert run_state == "READY"
    assert step_states == ("READY",) * len(prepared.steps)

    with c1_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.runtime_runs SET cancellation_requested=false "
                "WHERE project_key=:project_key AND run_id=:run_id"
            ),
            {
                "project_key": prepared.project_key,
                "run_id": prepared.run_id,
            },
        )
    run_to_idle(prepared)
    assert derive_run_completion(c1_database, prepared)
    assert len(prepared.handler.executions) == len(prepared.assignments)
    assert len(
        {attempt for _node, _step, attempt in prepared.handler.executions}
    ) == len(prepared.assignments)
    attempts = snapshot_attempts(c1_database, prepared)
    assert len(attempts) == len(prepared.assignments)
    assert all(item["disposition"] == "SUCCEEDED" for item in attempts)
    assert all(
        item["receipt_ref"] is not None
        and item["receipt_ref"].startswith("receipt:sha256:")
        for item in attempts
    )
    first_digest = replay_digest(c1_database, prepared)
    second_digest = replay_digest(c1_database, prepared)
    assert second_digest == first_digest


def test_c1_store_aba_and_stale_revision_fail_closed(
    c1_database: C1Database,
) -> None:
    # movement binding: C1-M004
    project_key = "c1-slice-b-aba"
    tag = _tag()
    prepared = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key=project_key,
        tag=tag,
        run_suffix="main",
        authority_epoch=AUTHORITY_EPOCH,
    )
    run_to_idle(prepared)
    assert derive_run_completion(c1_database, prepared)

    baseline_events = load_replay_events(c1_database, prepared)
    baseline_projection = replay_runtime_events(baseline_events)
    baseline_journal = snapshot_journal(c1_database, prepared)
    baseline_attempts = snapshot_attempts(c1_database, prepared)
    baseline_receipts = snapshot_receipts(c1_database, prepared)
    baseline_digest = replay_digest(c1_database, prepared)
    assert baseline_attempts

    bindings = inject_run_aba_cycle(c1_database, prepared, suffix="main")
    with c1_database.engine.connect() as connection:
        rewritten = RuntimeJournalRepository(
            connection,
            prepared.scope,
        ).load_run(prepared.run_id)
    assert str(rewritten["program_digest"]) == bindings["original_program_digest"]
    assert str(rewritten["plan_digest"]) == bindings["original_plan_digest"]
    assert str(rewritten["incarnation"]) == bindings["aba_incarnation"]
    assert int(rewritten["revision"]) == bindings["aba_revision"]
    assert bindings["aba_incarnation"] != bindings["original_incarnation"]

    events_after = load_replay_events(c1_database, prepared)
    assert tuple(event.run_incarnation for event in events_after) == (
        bindings["aba_incarnation"],
    ) * len(events_after)
    assert snapshot_journal(c1_database, prepared) == baseline_journal
    first_aba_digest = replay_digest(c1_database, prepared)
    second_aba_digest = replay_digest(c1_database, prepared)
    assert second_aba_digest == first_aba_digest
    assert first_aba_digest != baseline_digest
    projection_after = replay_runtime_events(events_after)
    assert projection_after.run_incarnation == bindings["aba_incarnation"]
    assert projection_after.run_incarnation != baseline_projection.run_incarnation
    assert projection_after.event_chain_digest != baseline_projection.event_chain_digest

    executions_before_cas = len(prepared.handler.executions)
    with (
        c1_database.engine.begin() as connection,
        pytest.raises(StaleRevisionError),
    ):
        RuntimeJournalRepository(
            connection,
            prepared.scope,
        ).append_transition(
            run_id=prepared.run_id,
            expected_revision=bindings["original_revision"],
            snapshot_values={"state": "READY"},
            events=(),
        )
    assert len(prepared.handler.executions) == executions_before_cas
    assert snapshot_journal(c1_database, prepared) == baseline_journal
    assert snapshot_attempts(c1_database, prepared) == baseline_attempts
    assert snapshot_receipts(c1_database, prepared) == baseline_receipts

    successor = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key=project_key,
        tag=tag,
        run_suffix="aba-claim",
        authority_epoch=AUTHORITY_EPOCH,
    )
    successor_journal = snapshot_journal(c1_database, successor)
    try:
        stale_epoch_node = make_node(
            successor,
            "c1-slice-node-b",
            authority_epoch=AUTHORITY_EPOCH - 1,
        )
        with pytest.raises(ClaimBindingMismatch) as stale_exc_info:
            stale_epoch_node.run_once()
        assert "authority" in str(stale_exc_info.value)
        assert successor.handler.executions == []
        assert snapshot_attempts(c1_database, successor) == ()
        assert snapshot_journal(c1_database, successor) == successor_journal

        successor_bindings = inject_run_aba_cycle(
            c1_database,
            successor,
            suffix="claim",
        )
        with c1_database.engine.connect() as connection:
            successor_run = RuntimeJournalRepository(
                connection,
                successor.scope,
            ).load_run(successor.run_id)
        assert (
            str(successor_run["program_digest"])
            == successor_bindings["original_program_digest"]
        )
        assert (
            str(successor_run["incarnation"]) == successor_bindings["aba_incarnation"]
        )

        claim_node = make_node(successor, "c1-slice-node-a")
        with pytest.raises(ClaimBindingMismatch) as exc_info:
            claim_node.run_once()
        assert "incarnation" in str(exc_info.value)
        assert successor.handler.executions == []
        assert snapshot_attempts(c1_database, successor) == ()
        assert snapshot_journal(c1_database, successor) == successor_journal

        with c1_database.engine.connect() as connection:
            ready_after_claims = connection.scalar(
                sa.text(
                    "SELECT count(*) FROM public.runtime_work_items "
                    "WHERE project_key=:project_key AND run_id=:run_id "
                    "AND state='READY'"
                ),
                {
                    "project_key": successor.project_key,
                    "run_id": successor.run_id,
                },
            )
        assert ready_after_claims == len(successor.assignments)
    finally:
        with c1_database.engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE public.runtime_work_items SET state='COMPLETED', "
                    "updated_at=:now WHERE project_key=:project_key "
                    "AND run_id=:run_id AND state='READY'"
                ),
                {
                    "now": NOW,
                    "project_key": successor.project_key,
                    "run_id": successor.run_id,
                },
            )
    with c1_database.engine.connect() as connection:
        ready_residue = connection.scalar(
            sa.text(
                "SELECT count(*) FROM public.runtime_work_items "
                "WHERE project_key=:project_key AND run_id=:run_id AND state='READY'"
            ),
            {
                "project_key": successor.project_key,
                "run_id": successor.run_id,
            },
        )
    assert ready_residue == 0


def test_c1_typed_effect_failure_is_recorded_and_blocks_duplicate(
    c1_database: C1Database,
) -> None:
    # movement binding: C1-M003
    failure_code = "C1_TYPED_EFFECT_FAILURE"

    def failing_handler(
        binding_digest: str,
        interpreter_profile_digest: str,
        ledger: Any,
    ) -> Any:
        return _C1TypedFailureHandler(
            handler_binding_digest=binding_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            ledger=ledger,
            failure_code=failure_code,
        )

    prepared = prepare_runtime(
        c1_database,
        slice_id="B",
        project_key="c1-slice-b-failure",
        tag=_tag(),
        run_suffix="failure",
        handler_builder=failing_handler,
    )
    node_a = make_node(prepared, "c1-slice-node-a")
    report = node_a.run_once()
    assert report.claimed == 1
    assert len(report.results) == 1
    result = report.results[0]
    assert result.committed
    assert result.executed
    assert result.disposition is EffectDisposition.FAILED
    assert result.failure_code == failure_code
    failed_assignment = next(
        assignment
        for assignment in prepared.assignments
        if assignment.work_item_id == result.work_item_id
    )
    assert failed_assignment.step_id is not None
    assert prepared.handler.executions == [
        (node_a.identity.node_id, failed_assignment.step_id, result.attempt_id)
    ]

    events = load_replay_events(c1_database, prepared)
    failed_events = [
        event
        for event in events
        if event.event_type == "EffectFailed"
        and event.step_id == failed_assignment.step_id
        and event.attempt_id == result.attempt_id
    ]
    assert len(failed_events) == 1
    assert failed_events[0].schema_version == "mrw.runtime.event.effect_failed.v1"
    assert events[failed_events[0].seq].event_type == "RequiredStepFailed"
    assert not any(event.event_type == "RunCompletionDerived" for event in events)
    assert not any(
        event.event_type in {"RuntimeValueProduced", "OutcomeStaged"}
        and event.step_id == failed_assignment.step_id
        for event in events
    )

    attempts = snapshot_attempts(c1_database, prepared)
    assert len(attempts) == 1
    assert attempts[0]["step_id"] == failed_assignment.step_id
    assert attempts[0]["attempt_id"] == result.attempt_id
    assert attempts[0]["disposition"] == "FAILED"
    assert attempts[0]["receipt_ref"] is None
    assert attempts[0]["receipt_digest"] is None
    with c1_database.engine.connect() as connection:
        failure_binding = (
            connection.execute(
                sa.text(
                    "SELECT failure_ref, failure_digest "
                    "FROM public.runtime_effect_attempts "
                    "WHERE project_key=:project_key AND attempt_id=:attempt_id"
                ),
                {
                    "project_key": prepared.project_key,
                    "attempt_id": result.attempt_id,
                },
            )
            .mappings()
            .one()
        )
    assert failure_binding["failure_ref"].startswith("project-value:runtime-failure:")
    assert len(failure_binding["failure_digest"]) == 64

    with c1_database.engine.connect() as connection:
        work_state = connection.scalar(
            sa.text(
                "SELECT state FROM public.runtime_work_items "
                "WHERE work_item_id=:work_item_id"
            ),
            {"work_item_id": result.work_item_id},
        )
        step_state = connection.scalar(
            sa.text(
                "SELECT state FROM public.runtime_steps "
                "WHERE project_key=:project_key AND run_id=:run_id "
                "AND step_id=:step_id"
            ),
            {
                "project_key": prepared.project_key,
                "run_id": prepared.run_id,
                "step_id": failed_assignment.step_id,
            },
        )
        run_state = connection.scalar(
            sa.text(
                "SELECT state FROM public.runtime_runs "
                "WHERE project_key=:project_key AND run_id=:run_id"
            ),
            {
                "project_key": prepared.project_key,
                "run_id": prepared.run_id,
            },
        )
    assert work_state == "FAILED"
    assert step_state == "FAILED"
    assert run_state == "FAILED"

    executions_before = len(prepared.handler.executions)
    with pytest.raises(ClaimBindingMismatch) as exc_info:
        node_a.run_once()
    assert "cannot claim run state FAILED" in str(exc_info.value)
    assert len(prepared.handler.executions) == executions_before
    assert len(snapshot_attempts(c1_database, prepared)) == 1
    first_digest = replay_digest(c1_database, prepared)
    second_digest = replay_digest(c1_database, prepared)
    assert second_digest == first_digest
