"""CW11: projection write and offset share one PostgreSQL UoW."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.projections import (
    PostgresRuntimeRunProjector,
    RuntimeJournalSource,
)

from .p0c_postgres_fixture import (
    PROJECT_KEY,
    LiveP0CDatabase,
)

pytest_plugins = ("tests.successor_runtime.p0c_postgres_fixture",)
pytestmark = pytest.mark.integration

RUN_ID = "p0d-cw11-run"
RUN_INCARNATION = "p0d-cw11-run-incarnation"
PROGRAM_DIGEST = sha256_hex("p0d-cw11-program")
AUTHORITY_DIGEST = sha256_hex("p0d-cw11-authority")


class ProjectorCrash(RuntimeError):
    pass


def _seed_run(database: LiveP0CDatabase) -> RuntimeJournalSource:
    with database.engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
                project_key=PROJECT_KEY,
                program_id="p0d-cw11-program",
                program_digest=PROGRAM_DIGEST,
                project_storage_ref="project-program:p0d-cw11",
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
                program_id="p0d-cw11-program",
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
                    "program_id": "p0d-cw11-program",
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


def test_cw11_crash_after_projection_write_before_offset_rolls_back_both(
    p0c_database: LiveP0CDatabase,
) -> None:
    source = _seed_run(p0c_database)

    def failpoint(point: str) -> None:
        if point == "after_projection_write_before_offset":
            raise ProjectorCrash(point)

    with (
        pytest.raises(ProjectorCrash),
        RuntimeUnitOfWork(engine=p0c_database.engine) as uow,
    ):
        PostgresRuntimeRunProjector(
            uow.connection,
            p0c_database.scope,
            failpoint=failpoint,
        ).apply(source)
        uow.commit()

    with p0c_database.engine.connect() as connection:
        projection_count = connection.scalar(
            sa.select(sa.func.count()).select_from(
                PUBLIC_TABLES["runtime_run_projections"]
            )
        )
        offset_count = connection.scalar(
            sa.select(sa.func.count()).select_from(
                PUBLIC_TABLES["runtime_projection_offsets"]
            )
        )
        run_state = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_runs"].c.state).where(
                PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID
            )
        )
    assert (projection_count, offset_count) == (0, 0)
    assert run_state == "SUBMITTED"

    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        PostgresRuntimeRunProjector(uow.connection, p0c_database.scope).apply(source)
        uow.commit()

    with p0c_database.engine.connect() as connection:
        projection_count = connection.scalar(
            sa.select(sa.func.count()).select_from(
                PUBLIC_TABLES["runtime_run_projections"]
            )
        )
        offset_count = connection.scalar(
            sa.select(sa.func.count()).select_from(
                PUBLIC_TABLES["runtime_projection_offsets"]
            )
        )
    assert (projection_count, offset_count) == (1, 1)
