"""Event-only PostgreSQL projection/rebuild evidence for P0-D."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.projections import (
    PostgresRuntimeRunProjector,
    RuntimeJournalSource,
    RuntimeProjectionError,
)

from .p0c_postgres_fixture import (
    PROJECT_KEY,
    LiveP0CDatabase,
)
from .test_p0c_full_runtime_chain_postgres import run_full_chain_first_specimen

pytest_plugins = ("tests.successor_runtime.p0c_postgres_fixture",)
pytestmark = pytest.mark.integration

RUN_ID = "p0d-runtime-projection-run"
RUN_INCARNATION = "p0d-runtime-projection-incarnation"
PROGRAM_DIGEST = sha256_hex("p0d-runtime-projection-program")
AUTHORITY_DIGEST = sha256_hex("p0d-runtime-projection-authority")


def _runtime_control_snapshot(
    connection: sa.Connection, run_id: str
) -> tuple[tuple[tuple[str, object], ...], ...]:
    rows: list[tuple[tuple[str, object], ...]] = []
    for table_name, order_by in (
        ("runtime_runs", ("run_id",)),
        ("runtime_steps", ("step_id",)),
        ("runtime_effect_attempts", ("attempt_id",)),
        ("runtime_work_items", ("work_item_id",)),
    ):
        table = PUBLIC_TABLES[table_name]
        statement = sa.select(table).where(
            table.c.project_key == PROJECT_KEY,
            table.c.run_id == run_id,
        )
        statement = statement.order_by(*(table.c[name] for name in order_by))
        for row in connection.execute(statement).mappings():
            rows.append(
                (("table", table_name), *tuple(sorted(dict(row).items())))
            )
    return tuple(rows)


def _seed_run(database: LiveP0CDatabase) -> RuntimeJournalSource:
    with database.engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
                project_key=PROJECT_KEY,
                program_id="p0d-runtime-projection-program",
                program_digest=PROGRAM_DIGEST,
                project_storage_ref="project-program:p0d-runtime-projection",
                contract_version="1.0.0",
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                run_id=RUN_ID,
                project_key=PROJECT_KEY,
                project_registry_revision=database.scope.project_scope.project_registry_revision,
                project_scope_digest=database.scope.project_scope.scope_digest,
                resolved_schema=database.scope.project_scope.resolved_schema,
                program_id="p0d-runtime-projection-program",
                program_digest=PROGRAM_DIGEST,
                state="SUBMITTED",
                revision=0,
                next_event_seq=2,
                execution_epoch=0,
                incarnation=RUN_INCARNATION,
                submission_authority_digest=AUTHORITY_DIGEST,
                cancellation_requested=False,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_events"]).values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                seq=1,
                event_type="ProgramAccepted",
                schema_version="mrw.runtime.event.program_accepted.v1",
                event_metadata_json={
                    "program_id": "p0d-runtime-projection-program",
                    "program_digest": PROGRAM_DIGEST,
                },
                authority_digest=AUTHORITY_DIGEST,
            )
        )
    return RuntimeJournalSource(
        run_id=RUN_ID,
        run_incarnation=RUN_INCARNATION,
        source_ref=f"runtime-run:{RUN_ID}",
    )


def test_delete_rebuild_is_digest_equivalent_and_never_controls_runtime(
    p0c_database: LiveP0CDatabase,
) -> None:
    source = _seed_run(p0c_database)
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        first = PostgresRuntimeRunProjector(uow.connection, p0c_database.scope).apply(
            source
        )
        uow.commit()
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        rebuilt = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).rebuild(source)
        uow.commit()

    assert first["projection_digest"] == rebuilt["projection_digest"]
    assert first["source_digest"] == rebuilt["source_digest"]
    assert first["source_revision"] == rebuilt["source_revision"] == 1
    assert first["projection_generation"] == 0
    assert rebuilt["projection_generation"] == 1
    with p0c_database.engine.connect() as connection:
        run_state = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_runs"].c.state).where(
                PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID
            )
        )
        offset = (
            connection.execute(sa.select(PUBLIC_TABLES["runtime_projection_offsets"]))
            .mappings()
            .one()
        )
    assert run_state == "SUBMITTED"
    assert offset["projection_generation"] == 1
    assert offset["source_digest"] == rebuilt["source_digest"]


def test_incremental_projector_replays_and_rejects_changed_source_prefix(
    p0c_database: LiveP0CDatabase,
) -> None:
    source = _seed_run(p0c_database)
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        PostgresRuntimeRunProjector(uow.connection, p0c_database.scope).apply(source)
        uow.commit()
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_events"])
            .where(
                PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_events"].c.run_id == RUN_ID,
                PUBLIC_TABLES["runtime_events"].c.seq == 1,
            )
            .values(
                event_metadata_json={
                    "program_id": "p0d-runtime-projection-program",
                    "program_digest": sha256_hex("mutated-program"),
                }
            )
        )

    with (
        pytest.raises(RuntimeProjectionError, match="prefix digest/state drift"),
        RuntimeUnitOfWork(engine=p0c_database.engine) as uow,
    ):
        PostgresRuntimeRunProjector(uow.connection, p0c_database.scope).apply(source)
        uow.commit()


def test_real_first_specimen_journal_delete_rebuild_is_exact_and_non_authoritative(
    p0c_database: LiveP0CDatabase,
    tmp_path,
) -> None:
    command = run_full_chain_first_specimen(p0c_database, tmp_path, "happy")
    assert command is not None
    source = RuntimeJournalSource(
        run_id=command.run_id,
        run_incarnation=command.run_incarnation,
        source_ref=f"runtime-run:{command.run_id}",
    )
    with p0c_database.engine.connect() as connection:
        event_rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_events"].c.run_id == command.run_id,
                )
                .order_by(PUBLIC_TABLES["runtime_events"].c.seq)
            )
            .mappings()
            .all()
        )
        event_pairs = frozenset(
            connection.execute(
                sa.select(
                    PUBLIC_TABLES["runtime_events"].c.event_type,
                    PUBLIC_TABLES["runtime_events"].c.schema_version,
                ).where(
                    PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_events"].c.run_id == command.run_id,
                )
            ).all()
        )
        before = _runtime_control_snapshot(connection, command.run_id)
    assert [row["seq"] for row in event_rows] == list(
        range(1, len(event_rows) + 1)
    )
    assert [row["event_type"] for row in event_rows[:4]] == [
        "ProgramAccepted",
        "CompileSucceeded",
        "PlanCompiled",
        "QualificationActivated",
    ]
    assert event_rows[-1]["event_type"] == "RunCompletionDerived"
    assert all(
        (row["payload_ref"] is None) == (row["payload_digest"] is None)
        for row in event_rows
    )
    for row in event_rows:
        metadata = row["event_metadata_json"]
        assert isinstance(metadata, dict)
        if row["event_type"] == "StepActivated":
            assert {
                "assignment_digest",
                "activation_digest",
                "input_closure_digest",
            } <= metadata.keys()
        elif row["event_type"] == "RunCompletionDerived":
            assert metadata["required_step_ids"]
        elif row["event_type"] == "StepClaimed":
            assert metadata["assignment_kind"] != "RECONCILE"
            assert metadata["reconciliation_attempt_id"] is None
    assert event_pairs == frozenset(
        {
            ("ProgramAccepted", "mrw.runtime.event.program_accepted.v1"),
            ("CompileSucceeded", "mrw.runtime.event.compile-succeeded.v1"),
            ("PlanCompiled", "mrw.runtime.event.plan_compiled.v1"),
            (
                "QualificationActivated",
                "mrw.runtime.event.qualification_activated.v1",
            ),
            ("StepActivated", "mrw.runtime.event.step_activated.v1"),
            ("StepClaimed", "mrw.runtime.event.step_claimed.v1"),
            ("EffectStarted", "mrw.runtime.event.effect_started.v1"),
            ("RuntimeValueProduced", "mrw.runtime.event.effect_succeeded.v1"),
            ("OutcomeStaged", "mrw.runtime.event.effect_succeeded.v1"),
            ("CommitPrepared", "mrw.runtime.event.commit_prepared.v1"),
            (
                "CommitReadbackConfirmed",
                "mrw.runtime.event.commit_readback_confirmed.v1",
            ),
            ("DeliveryReady", "mrw.runtime.event.delivery_ready.v1"),
            (
                "RunCompletionDerived",
                "mrw.runtime.event.run_completion_derived.v1",
            ),
        }
    )

    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        first = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).apply(source)
        uow.commit()
    with p0c_database.engine.connect() as connection:
        assert _runtime_control_snapshot(connection, command.run_id) == before
    projection = PUBLIC_TABLES["runtime_run_projections"]
    offsets = PUBLIC_TABLES["runtime_projection_offsets"]
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.delete(projection).where(
                projection.c.project_key == PROJECT_KEY,
                projection.c.source_ref == source.source_ref,
                projection.c.source_incarnation == source.run_incarnation,
            )
        )
        connection.execute(
            sa.delete(offsets).where(
                offsets.c.project_key == PROJECT_KEY,
                offsets.c.source_ref == source.source_ref,
                offsets.c.source_incarnation == source.run_incarnation,
            )
        )
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        journal_only = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).rebuild(source)
        uow.commit()
    assert journal_only["projection_digest"] == first["projection_digest"]
    assert journal_only["source_digest"] == first["source_digest"]
    with p0c_database.engine.connect() as connection:
        assert _runtime_control_snapshot(connection, command.run_id) == before


    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        rebuilt = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).rebuild(source)
        uow.commit()
    assert rebuilt["projection_digest"] == first["projection_digest"]
    assert rebuilt["source_digest"] == first["source_digest"]
    assert rebuilt["source_revision"] == first["source_revision"]
    with p0c_database.engine.connect() as connection:
        assert _runtime_control_snapshot(connection, command.run_id) == before


def test_real_recovery_journal_rebuild_preserves_original_effect_attempt(
    p0c_database: LiveP0CDatabase,
    tmp_path,
) -> None:
    command = run_full_chain_first_specimen(
        p0c_database, tmp_path, "delivery-reconcile-lease-expiry"
    )
    assert command is not None
    source = RuntimeJournalSource(
        run_id=command.run_id,
        run_incarnation=command.run_incarnation,
        source_ref=f"runtime-run:{command.run_id}",
    )
    with p0c_database.engine.connect() as connection:
        before = _runtime_control_snapshot(connection, command.run_id)
        recovery_events = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_events"].c.run_id == command.run_id,
                    PUBLIC_TABLES["runtime_events"].c.event_type.in_(
                        ("StepClaimed", "ReconcileRequested")
                    ),
                )
                .order_by(PUBLIC_TABLES["runtime_events"].c.seq)
            )
            .mappings()
            .all()
        )
    assert recovery_events
    for row in recovery_events:
        metadata = row["event_metadata_json"]
        if metadata["assignment_kind"] == "RECONCILE":
            assert metadata["reconciliation_attempt_id"]
            assert row["attempt_id"] != metadata["reconciliation_attempt_id"]
        else:
            assert metadata["reconciliation_attempt_id"] is None
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        first = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).apply(source)
        uow.commit()
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        rebuilt = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).rebuild(source)
        uow.commit()

    assert first["projection_digest"] == rebuilt["projection_digest"]
    state = rebuilt["state_json"]
    effect_attempt_ids = {item["attempt_id"] for item in state["attempts"]}
    recovery_claim_ids = {
        item["attempt_id"] for item in state["recovery_claim_bindings"]
    }
    assert effect_attempt_ids
    assert recovery_claim_ids
    assert effect_attempt_ids.isdisjoint(recovery_claim_ids)

    projection = PUBLIC_TABLES["runtime_run_projections"]
    offsets = PUBLIC_TABLES["runtime_projection_offsets"]
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(projection)
            .where(
                projection.c.project_key == PROJECT_KEY,
                projection.c.source_ref == source.source_ref,
                projection.c.source_incarnation == source.run_incarnation,
            )
            .values(state_json={"schema": "hostile.runtime-projection.v0"})
        )
    with p0c_database.engine.connect() as connection:
        assert _runtime_control_snapshot(connection, command.run_id) == before
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.delete(projection).where(
                projection.c.project_key == PROJECT_KEY,
                projection.c.source_ref == source.source_ref,
                projection.c.source_incarnation == source.run_incarnation,
            )
        )
        connection.execute(
            sa.delete(offsets).where(
                offsets.c.project_key == PROJECT_KEY,
                offsets.c.source_ref == source.source_ref,
                offsets.c.source_incarnation == source.run_incarnation,
            )
        )
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        journal_only = PostgresRuntimeRunProjector(
            uow.connection, p0c_database.scope
        ).rebuild(source)
        uow.commit()

    assert journal_only["projection_digest"] == first["projection_digest"]
    assert journal_only["source_digest"] == first["source_digest"]
    assert journal_only["source_revision"] == first["source_revision"]
    with p0c_database.engine.connect() as connection:
        assert _runtime_control_snapshot(connection, command.run_id) == before
