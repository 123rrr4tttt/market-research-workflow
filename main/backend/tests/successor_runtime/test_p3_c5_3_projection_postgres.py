"""Real-PostgreSQL C5.3 event fold/snapshot agreement acceptance."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    RuntimeReplayProjection,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.projections.agent_session import (
    PostgresAgentSessionReadAdapter,
    SessionStatus,
    TaskStatus,
    fold_agent_session,
)
from app.successor_runtime.substrate.projections.runtime_run import (
    PostgresRuntimeRunProjector,
    RuntimeJournalSource,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

pytest_plugins = ()
pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
WORKER_DATABASE_ENV = "SUCCESSOR_P3_C5_DATABASE_URL"
WORKER_DATABASE_MARKER = "mrw_p3_c5_worker_test"
PROJECT_KEY = "p3-c5-projection"
PROJECT_SCHEMA = "mrw_p3_c5_projection"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "p3-c5-incarnation-1"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
AUTHORITY_DIGEST = sha256_hex("p3-c5-authority")
PROGRAM_DIGEST = sha256_hex("p3-c5-program")
PROGRAM_ID = "program:p3-c5"
PLAN_ID = "plan:p3-c5"
PLAN_DIGEST = sha256_hex("p3-c5-plan")
QUALIFICATION_DIGEST = sha256_hex("p3-c5-qualification")
HAPPY_RUN_ID = "run:p3-c5-happy"
HAPPY_INCARNATION = "run-inc:p3-c5-happy"
DRIFTED_RUN_ID = "run:p3-c5-drifted"
DRIFTED_INCARNATION = "run-inc:p3-c5-drifted"


@dataclass(frozen=True, slots=True)
class LiveC5Database:
    engine: Engine
    scope: RuntimeScope


def _require_database_url() -> str:
    worker_url = os.environ.get(WORKER_DATABASE_ENV)
    value = worker_url or os.environ.get(DATABASE_ENV)
    if not value:
        pytest.skip(f"{DATABASE_ENV} or {WORKER_DATABASE_ENV} is not set")
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("P3 C5 projection requires a PostgreSQL URL")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(f"P3 C5 projection refuses non-test database {database_name!r}")
    if worker_url and WORKER_DATABASE_MARKER not in database_name:
        pytest.fail(
            f"{WORKER_DATABASE_ENV} must name the unique worker database "
            f"{WORKER_DATABASE_MARKER!r}"
        )
    return value


def _event(
    seq: int,
    event_type: str,
    schema_version: str,
    *,
    step_id: str | None = None,
    attempt_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ReplayEvent:
    return ReplayEvent.from_content(
        project_key=PROJECT_KEY,
        run_id="__run__",
        run_incarnation="__inc__",
        seq=seq,
        event_type=event_type,
        schema_version=schema_version,
        step_id=step_id,
        attempt_id=attempt_id,
        metadata=metadata or {},
        payload_ref=None,
        payload_digest=None,
        authority_digest=AUTHORITY_DIGEST,
    )


def _happy_event_rows() -> tuple[dict[str, object], ...]:
    events = (
        _event(
            1,
            "ProgramAccepted",
            "mrw.runtime.event.program_accepted.v1",
            metadata={"program_id": "program:p3-c5", "program_digest": PROGRAM_DIGEST},
        ),
        _event(
            2,
            "CompileSucceeded",
            "mrw.runtime.event.compile-succeeded.v1",
            metadata={"plan_digest": PROGRAM_DIGEST},
        ),
        _event(
            3,
            "PlanCompiled",
            "mrw.runtime.event.plan_compiled.v1",
            metadata={"plan_id": "plan:p3-c5", "plan_digest": PROGRAM_DIGEST},
        ),
        _event(
            4,
            "QualificationActivated",
            "mrw.runtime.event.qualification_activated.v1",
            metadata={
                "qualification_id": "qualification:p3-c5",
                "qualification_digest": PROGRAM_DIGEST,
                "decision": "QUALIFIED",
                "reducer_event_code": "PlanCompiled",
            },
        ),
        _event(
            5,
            "StepActivated",
            "mrw.runtime.event.step_activated.v1",
            step_id="step:p3-c5",
            metadata={
                "assignment_digest": PROGRAM_DIGEST,
                "activation_digest": PROGRAM_DIGEST,
                "input_closure_digest": PROGRAM_DIGEST,
            },
        ),
        _event(
            6,
            "StepClaimed",
            "mrw.runtime.event.step_claimed.v1",
            step_id="step:p3-c5",
            attempt_id="attempt:p3-c5",
            metadata={
                "assignment_kind": "INTERPRET",
                "reconciliation_attempt_id": None,
            },
        ),
        _event(
            7,
            "EffectStarted",
            "mrw.runtime.event.effect_started.v1",
            step_id="step:p3-c5",
            attempt_id="attempt:p3-c5",
        ),
        _event(
            8,
            "RuntimeValueProduced",
            "mrw.runtime.event.effect_succeeded.v1",
            step_id="step:p3-c5",
            attempt_id="attempt:p3-c5",
        ),
    )
    return tuple(_event_row(event, run_id=HAPPY_RUN_ID) for event in events)


def _event_row(
    event: ReplayEvent,
    *,
    run_id: str,
) -> dict[str, object]:
    return {
        "project_key": PROJECT_KEY,
        "run_id": run_id,
        "seq": event.seq,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "step_id": event.step_id,
        "attempt_id": event.attempt_id,
        "event_metadata_json": dict(event.metadata),
        "payload_ref": event.payload_ref,
        "payload_digest": event.payload_digest,
        "authority_digest": AUTHORITY_DIGEST,
    }


def _happy_events() -> tuple[dict[str, object], ...]:
    rows = _happy_event_rows()
    completion = _event(
        9,
        "RunCompletionDerived",
        "mrw.runtime.event.run_completion_derived.v1",
        metadata={"required_step_ids": ["step:p3-c5"]},
    )
    return rows + (
        _event_row(
            completion,
            run_id=HAPPY_RUN_ID,
        ),
    )


def _drifted_events() -> tuple[dict[str, object], ...]:
    rows = _happy_event_rows()
    return tuple(
        {
            **row,
            "run_id": DRIFTED_RUN_ID,
        }
        for row in rows
    )


def _seed_run(
    database: LiveC5Database,
    *,
    run_id: str,
    incarnation: str,
    events: tuple[dict[str, object], ...],
    snapshot_state: str,
) -> RuntimeJournalSource:
    with database.engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                project_key=PROJECT_KEY,
                registry_revision=REGISTRY_REVISION,
                resolved_schema=PROJECT_SCHEMA,
                scope_digest=SCOPE_DIGEST,
                incarnation=SCOPE_INCARNATION,
                state="ACTIVE",
                updated_by="p3-c5-projection-fixture",
                approval_ref="approval:p3-c5-project-scope",
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
                program_id=PROGRAM_ID,
                project_key=PROJECT_KEY,
                program_digest=PROGRAM_DIGEST,
                project_storage_ref="project-program:p3-c5",
                contract_version="1.0.0",
            )
        )
        if snapshot_state not in {"SUBMITTED", "COMPILING"}:
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(
                    plan_id=PLAN_ID,
                    project_key=PROJECT_KEY,
                    plan_digest=PLAN_DIGEST,
                    program_id=PROGRAM_ID,
                    program_digest=PROGRAM_DIGEST,
                    project_storage_ref="project-plan:p3-c5",
                    compiler_id="compiler:p3-c5",
                    compiler_version="1.0.0",
                    operation_catalog_id="catalog:p3-c5",
                    catalog_version="1.0.0",
                    catalog_digest=PROGRAM_DIGEST,
                    effect_closure_digest=PROGRAM_DIGEST,
                    authority_closure_digest=PROGRAM_DIGEST,
                    resource_closure_digest=PROGRAM_DIGEST,
                )
            )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                run_id=run_id,
                project_key=PROJECT_KEY,
                project_registry_revision=REGISTRY_REVISION,
                project_scope_digest=SCOPE_DIGEST,
                resolved_schema=PROJECT_SCHEMA,
                program_id=PROGRAM_ID,
                program_digest=PROGRAM_DIGEST,
                plan_id=PLAN_ID
                if snapshot_state not in {"SUBMITTED", "COMPILING"}
                else None,
                plan_digest=(
                    PLAN_DIGEST
                    if snapshot_state not in {"SUBMITTED", "COMPILING"}
                    else None
                ),
                qualification_digest=(
                    QUALIFICATION_DIGEST
                    if snapshot_state not in {"SUBMITTED", "COMPILING"}
                    else None
                ),
                state=snapshot_state,
                revision=0,
                next_event_seq=len(events) + 1,
                execution_epoch=0,
                incarnation=incarnation,
                submission_authority_digest=AUTHORITY_DIGEST,
                cancellation_requested=False,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_events"]),
            [
                {
                    **row,
                    "run_id": run_id,
                }
                for row in events
            ],
        )
    return RuntimeJournalSource(
        run_id=run_id,
        run_incarnation=incarnation,
        source_ref=f"runtime-run:{run_id}",
    )


@contextmanager
def _capture_statements(database: LiveC5Database) -> Iterator[list[str]]:
    statements: list[str] = []

    def before_execute(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    sa.event.listen(database.engine, "before_cursor_execute", before_execute)
    try:
        yield statements
    finally:
        sa.event.remove(database.engine, "before_cursor_execute", before_execute)


@pytest.fixture(scope="module")
def live_c5_database() -> Iterator[LiveC5Database]:
    database_url = _require_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    inspector = sa.inspect(engine)
    existing_public = set(inspector.get_table_names(schema="public")) & set(
        PUBLIC_TABLES
    )
    if existing_public:
        engine.dispose()
        pytest.fail(
            "dedicated database already contains successor public tables; "
            f"refusing overwrite: {sorted(existing_public)}"
        )
    if PROJECT_SCHEMA in set(inspector.get_schema_names()):
        engine.dispose()
        pytest.fail(
            f"dedicated database already contains {PROJECT_SCHEMA}; refusing overwrite"
        )
    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id="human:p3-c5-projection",
    )
    database = LiveC5Database(engine=engine, scope=scope)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
        yield database
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()


@pytest.fixture
def c5_database(live_c5_database: LiveC5Database) -> LiveC5Database:
    with live_c5_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE "
                + ", ".join(f'"public"."{name}"' for name in PUBLIC_TABLES)
                + " RESTART IDENTITY CASCADE"
            )
        )
    return live_c5_database


def test_session_projection_agrees_with_existing_runtime_projection(
    c5_database: LiveC5Database,
) -> None:
    source = _seed_run(
        c5_database,
        run_id=HAPPY_RUN_ID,
        incarnation=HAPPY_INCARNATION,
        events=_happy_events(),
        snapshot_state="RUNNING",
    )
    with RuntimeUnitOfWork(engine=c5_database.engine) as uow:
        materialized = PostgresRuntimeRunProjector(
            uow.connection,
            c5_database.scope,
        ).apply(source)
        uow.commit()
    with c5_database.engine.connect() as connection:
        session = PostgresAgentSessionReadAdapter(
            connection,
            c5_database.scope,
        ).load(source)
        row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_run_projections"]).where(
                    PUBLIC_TABLES["runtime_run_projections"].c.run_id == HAPPY_RUN_ID
                )
            )
            .mappings()
            .one()
        )
        decoded = RuntimeReplayProjection.from_json(row["state_json"])
        folded = fold_agent_session(decoded)

    assert session.status is SessionStatus.COMPLETED
    assert session.source_digest == materialized["source_digest"]
    assert session.source_revision == materialized["source_revision"] == 9
    assert session.tasks[0].status is TaskStatus.COMPLETED
    assert session.tasks[0].attempt_id == "attempt:p3-c5"
    assert session == folded


def test_control_terminal_snapshot_cannot_fabricate_journal_derived_completion(
    c5_database: LiveC5Database,
) -> None:
    source = _seed_run(
        c5_database,
        run_id=DRIFTED_RUN_ID,
        incarnation=DRIFTED_INCARNATION,
        events=_drifted_events(),
        snapshot_state="COMPLETED",
    )
    with (
        _capture_statements(c5_database) as statements,
        c5_database.engine.connect() as connection,
    ):
        session = PostgresAgentSessionReadAdapter(
            connection,
            c5_database.scope,
        ).load(source)

    assert session.status is SessionStatus.ACTIVE
    assert session.terminal_events == ()
    assert session.tasks[0].status is TaskStatus.COMPLETED
    assert all(
        statement.lstrip().startswith("SELECT")
        for statement in statements
        if statement.strip()
    )
    with c5_database.engine.connect() as connection:
        control_state = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_runs"].c.state).where(
                PUBLIC_TABLES["runtime_runs"].c.run_id == DRIFTED_RUN_ID
            )
        )
    assert control_state == "COMPLETED"


def test_rebuild_is_digest_equivalent_for_session_projection(
    c5_database: LiveC5Database,
) -> None:
    source = _seed_run(
        c5_database,
        run_id=HAPPY_RUN_ID,
        incarnation=HAPPY_INCARNATION,
        events=_happy_events(),
        snapshot_state="RUNNING",
    )
    with RuntimeUnitOfWork(engine=c5_database.engine) as uow:
        PostgresRuntimeRunProjector(uow.connection, c5_database.scope).apply(source)
        uow.commit()
    with c5_database.engine.connect() as connection:
        before = PostgresAgentSessionReadAdapter(
            connection,
            c5_database.scope,
        ).load(source)
    with RuntimeUnitOfWork(engine=c5_database.engine) as uow:
        rebuilt = PostgresRuntimeRunProjector(
            uow.connection,
            c5_database.scope,
        ).rebuild(source)
        uow.commit()
    with c5_database.engine.connect() as connection:
        after = PostgresAgentSessionReadAdapter(
            connection,
            c5_database.scope,
        ).load(source)

    assert before.projection_digest == after.projection_digest
    assert before.source_digest == after.source_digest
    assert rebuilt["projection_generation"] == 1


def test_read_adapter_never_writes_and_source_incarnation_is_exact(
    c5_database: LiveC5Database,
) -> None:
    source = _seed_run(
        c5_database,
        run_id=HAPPY_RUN_ID,
        incarnation=HAPPY_INCARNATION,
        events=_happy_events(),
        snapshot_state="RUNNING",
    )
    with (
        _capture_statements(c5_database) as statements,
        c5_database.engine.connect() as connection,
    ):
        PostgresAgentSessionReadAdapter(
            connection,
            c5_database.scope,
        ).load(source)
    assert statements
    assert all(
        statement.lstrip().startswith("SELECT")
        for statement in statements
        if statement.strip()
    )

    stale = RuntimeJournalSource(
        run_id=HAPPY_RUN_ID,
        run_incarnation="wrong-incarnation",
        source_ref=f"runtime-run:{HAPPY_RUN_ID}",
    )
    from app.successor_runtime.substrate.projections.agent_session import (
        AgentSessionProjectionError,
    )

    with (
        c5_database.engine.connect() as connection,
        pytest.raises(AgentSessionProjectionError),
    ):
        PostgresAgentSessionReadAdapter(
            connection,
            c5_database.scope,
        ).load(stale)
