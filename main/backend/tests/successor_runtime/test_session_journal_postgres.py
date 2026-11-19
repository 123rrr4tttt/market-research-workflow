"""Read the session and recovery state from a real PostgreSQL runtime journal."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.runtime.replay import replay_runtime_events
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
    runtime_uow_factory,
)
from app.successor_runtime.substrate.postgres.runtime_journal import RecordNotFound, RuntimeJournalRepository
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    RequestCancel,
    RuntimeLifecycleRepository,
)
from app.successor_runtime.substrate.postgres.work_items import WorkItemClaimRepository
from app.successor_runtime.substrate.projections.agent_session import (
    AgentSessionProjectionError,
    PostgresAgentSessionReadAdapter,
    RuntimeJournalSource,
    SessionStatus,
    TaskStatus,
)

from .slice_runtime_postgres_fixture import (
    NOW,
    PreparedRuntimeSlice,
    SliceRuntimeDatabase,
    derive_run_completion,
    load_replay_events,
    make_node,
    prepare_runtime,
    run_to_idle,
)

pytest_plugins = ("tests.successor_runtime.slice_runtime_postgres_fixture",)
pytestmark = pytest.mark.integration


def _prepare(database: SliceRuntimeDatabase, *, slice_id: str, name: str) -> PreparedRuntimeSlice:
    # Workers may claim across projects; give each case an exact deployment/profile binding.
    return prepare_runtime(
        database,
        slice_id=slice_id,
        project_key=f"journal-{name}",
        tag=f"journal_{name}",
        run_suffix=name,
        node_profile_digest=sha256_hex(f"journal-node-profile:{name}"),
        deployment_catalog_digest=sha256_hex(f"journal-deployment:{name}"),
    )


def _source(prepared: PreparedRuntimeSlice) -> RuntimeJournalSource:
    return RuntimeJournalSource(
        run_id=prepared.run_id,
        run_incarnation=prepared.run_incarnation,
        source_ref=f"runtime-run:{prepared.run_id}",
    )


def test_session_reads_ordered_journal_without_writes(
    slice_runtime_database: SliceRuntimeDatabase,
) -> None:
    prepared = _prepare(slice_runtime_database, slice_id="C", name="completion")
    run_to_idle(prepared, node_ids=(f"{prepared.project_key}-a", f"{prepared.project_key}-b"))
    assert derive_run_completion(slice_runtime_database, prepared)
    events = load_replay_events(slice_runtime_database, prepared)
    assert events[-1].event_type == "RunCompletionDerived"
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    expected_digest = replay_runtime_events(events).event_chain_digest
    engine = slice_runtime_database.engine
    statements: list[str] = []

    def record_sql(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record_sql)
    try:
        with engine.connect() as connection:
            direct = PostgresAgentSessionReadAdapter(connection, prepared.scope).load(_source(prepared))
    finally:
        sa.event.remove(engine, "before_cursor_execute", record_sql)

    assert statements and all(statement.lstrip().startswith("SELECT") for statement in statements)
    assert all("runtime_run_projections" not in sql and "runtime_projection_offsets" not in sql for sql in statements)
    assert direct.status is SessionStatus.COMPLETED
    assert direct.source_revision == len(events)
    assert direct.source_digest == expected_digest
    assert direct.tasks and all(task.status is TaskStatus.COMPLETED for task in direct.tasks)


def test_session_rejects_wrong_scope_incarnation_and_sequence_gap(
    slice_runtime_database: SliceRuntimeDatabase,
) -> None:
    prepared = _prepare(slice_runtime_database, slice_id="B", name="identity")
    other = _prepare(slice_runtime_database, slice_id="B", name="other")
    engine = slice_runtime_database.engine
    with engine.connect() as connection:
        with pytest.raises(RecordNotFound):
            PostgresAgentSessionReadAdapter(connection, other.scope).load(_source(prepared))
        with pytest.raises(AgentSessionProjectionError, match="incarnation is stale"):
            PostgresAgentSessionReadAdapter(connection, prepared.scope).load(
                replace(_source(prepared), run_incarnation="wrong-incarnation")
            )
    runtime_events = PUBLIC_TABLES["runtime_events"]
    with engine.begin() as connection:
        # Model a missing persisted journal event without modifying shared databases.
        connection.execute(
            runtime_events.delete().where(
                runtime_events.c.project_key == prepared.project_key,
                runtime_events.c.run_id == prepared.run_id,
                runtime_events.c.seq == 2,
            )
        )
        with pytest.raises(AgentSessionProjectionError, match="journal replay failed closed"):
            PostgresAgentSessionReadAdapter(connection, prepared.scope).load(_source(prepared))


def test_session_uses_terminal_journal_not_control_snapshot(
    slice_runtime_database: SliceRuntimeDatabase,
) -> None:
    prepared = _prepare(slice_runtime_database, slice_id="C", name="terminal")
    run_to_idle(prepared, node_ids=(f"{prepared.project_key}-a", f"{prepared.project_key}-b"))
    runs = PUBLIC_TABLES["runtime_runs"]
    with slice_runtime_database.engine.begin() as connection:
        connection.execute(runs.update().where(runs.c.run_id == prepared.run_id).values(state="COMPLETED"))
        snapshot = PostgresAgentSessionReadAdapter(connection, prepared.scope).load(_source(prepared))
    assert snapshot.status is SessionStatus.ACTIVE
    assert snapshot.terminal_events == ()
    assert snapshot.tasks and all(task.status is TaskStatus.COMPLETED for task in snapshot.tasks)


def test_cancellation_service_reads_the_run_and_journal(
    slice_runtime_database: SliceRuntimeDatabase,
) -> None:
    prepared = _prepare(slice_runtime_database, slice_id="B", name="cancellation")
    engine = slice_runtime_database.engine
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    kwargs = dict(project_key=prepared.project_key, actor_id=prepared.scope.actor_id, engine=engine)
    assert sessions.read_run_cancellation(prepared.run_id, **kwargs) is False
    with engine.begin() as connection:
        run = RuntimeJournalRepository(connection, prepared.scope).load_run(prepared.run_id)
        RuntimeLifecycleRepository(connection, prepared.scope).request_cancel(
            RequestCancel(
                run_id=prepared.run_id,
                expected_run_revision=int(run["revision"]),
                reason="cancel journal test",
            ),
            observed_at=NOW,
        )
        # The journal still reports the cancellation if the mutable flag/state drift.
        runs = PUBLIC_TABLES["runtime_runs"]
        connection.execute(
            runs.update()
            .where(runs.c.run_id == prepared.run_id)
            .values(
                cancellation_requested=False,
                state="RUNNING",
            )
        )
    assert sessions.read_run_cancellation(prepared.run_id, **kwargs) is True


def _slice_claim_context(prepared: PreparedRuntimeSlice, node_id: str) -> dict[str, Any]:
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
            profile_digest=prepared.profile_digest,
            supported_assignment_kinds=frozenset(assignment.assignment_kind for assignment in prepared.assignments),
            interpreter_profile_digests=prepared.interpreter_profile_digests,
        ),
        "deployment": DeploymentBinding(
            catalog_digest=prepared.deployment_catalog_digest,
            node_profile_digest=prepared.profile_digest,
            runtime_protocol_version="1",
        ),
        "protocol": RuntimeNodeProtocol(version="1", claim_batch_size=1),
        "limit": 1,
        "observed_at": NOW,
    }


def test_recovery_session_retains_original_effect_attempt(
    slice_runtime_database: SliceRuntimeDatabase,
) -> None:
    prepared = _prepare(slice_runtime_database, slice_id="B", name="recovery")
    adapter = PostgresRuntimeNodeAdapter(runtime_uow_factory(slice_runtime_database.engine))
    make_node(prepared, "unknown-node")  # register its exact deployment before claiming
    context = _slice_claim_context(prepared, "unknown-node")
    claimed = adapter.claim_due(**context)
    assert len(claimed) == 1
    target_step_id = claimed[0].assignment.step_id
    assert target_step_id is not None
    in_flight = adapter.begin_in_flight(
        control_scope=context["control_scope"],
        claim=claimed[0],
        expected_revision=claimed[0].work_item_revision,
        started_at=NOW,
    )
    assert in_flight.effect_disposition is EffectDisposition.IN_FLIGHT

    other_work_ids = tuple(
        assignment.work_item_id for assignment in prepared.assignments if assignment.step_id != target_step_id
    )
    assert other_work_ids
    with slice_runtime_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.project_key == prepared.project_key,
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id.in_(other_work_ids),
            )
            .values(state="COMPLETED")
        )
        reaped = WorkItemClaimRepository(connection).reap_expired(
            ControlPlaneScope(
                system_actor_id="journal-reaper",
                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                authority_epoch=prepared.authority_epoch,
            ),
            now=NOW + timedelta(minutes=2),
        )
    assert reaped == (in_flight.assignment.work_item_id,)

    reconcile_node = make_node(
        prepared,
        "reconcile-node",
        clock_start=NOW + timedelta(minutes=3),
    )
    reconcile_report = reconcile_node.run_once()
    assert reconcile_report.claimed == 1
    assert reconcile_report.results[0].committed
    assert reconcile_report.results[0].executed is False
    assert reconcile_report.results[0].disposition is EffectDisposition.OUTCOME_UNKNOWN

    events = load_replay_events(slice_runtime_database, prepared)
    replay = replay_runtime_events(events)
    original_attempt = claimed[0].claim_binding.attempt_id
    assert dict(replay.attempts)[original_attempt] is EffectDisposition.OUTCOME_UNKNOWN
    assert any(
        claimed_step == target_step_id and target_attempt == original_attempt
        for _, claimed_step, target_attempt in replay.recovery_claim_bindings
    )
    with slice_runtime_database.engine.connect() as connection:
        snapshot = PostgresAgentSessionReadAdapter(connection, prepared.scope).load(_source(prepared))
    task = next(task for task in snapshot.tasks if task.step_id == target_step_id)
    assert task.attempt_id == original_attempt
    assert task.disposition is EffectDisposition.OUTCOME_UNKNOWN
