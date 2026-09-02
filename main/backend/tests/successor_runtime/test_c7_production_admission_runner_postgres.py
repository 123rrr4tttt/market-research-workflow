"""Disposable PostgreSQL evidence for the production C7 admission runner.

The runner is the successor composition root that later drives the real
``postgres`` canonical acceptance row.  This test proves fresh commit,
idempotent replay and zero legacy writes against a disposable database using
the exact public/project schema shape of the movement-admission evidence.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.successor_runtime.substrate.postgres.c7_production_admission import (
    C7ProductionAdmissionInput,
    run_c7_production_cutover_admission,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES, project_tables
from app.successor_runtime.substrate.postgres.session import compute_scope_digest

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_c7_production_admission_runner_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "c7-production-runner-demo"
RESOLVED_SCHEMA = "c7_production_runner_demo"
REGISTRY_REVISION = 1
INCARNATION = "inc:c7-production-runner-demo"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, INCARNATION
)
ACTOR_ID = "actor:c7-production-runner"
APPROVAL_REF = "approval:c7-production-runner-test"
TRACE_ID = "runner-acceptance-2026-09-03-001"
RAW_BYTES = (
    b'{"title": "C7 production cutover acceptance 2026-09-03", '
    b'"text": "Bounded successor canonical write acceptance on a disposable database."}'
)


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
    except OperationalError as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{RESOLVED_SCHEMA}"'))
        for table in PUBLIC_TABLES.values():
            table.create(connection)
        C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection)
        project_tables(sa.MetaData(), RESOLVED_SCHEMA).successor_values.create(
            connection
        )
        connection.execute(
            text(
                "CREATE TABLE public.legacy_canary (id integer primary key, "
                "project_key varchar(128) not null)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO public.legacy_canary (id, project_key) "
                "VALUES (1, :project_key)"
            ),
            {"project_key": PROJECT_KEY},
        )
        connection.execute(
            PUBLIC_TABLES["project_scope_registry"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                registry_revision=REGISTRY_REVISION,
                resolved_schema=RESOLVED_SCHEMA,
                scope_digest=SCOPE_DIGEST,
                incarnation=INCARNATION,
                state="ACTIVE",
                updated_by=ACTOR_ID,
                approval_ref=APPROVAL_REF,
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


def _legacy_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text("SELECT count(*) FROM public.legacy_canary")).scalar_one()
        )


def _input() -> C7ProductionAdmissionInput:
    return C7ProductionAdmissionInput(
        project_key=PROJECT_KEY,
        trace_id=TRACE_ID,
        actor_id=ACTOR_ID,
        approval_ref=APPROVAL_REF,
        canonical_object_id=f"ingest-doc:c7-production:{TRACE_ID}",
        source_locator="file://disposable/c7-production-acceptance.json",
        raw_bytes=RAW_BYTES,
        raw_incarnation=f"raw-inc:c7-production:{TRACE_ID}",
        authority_epoch=1,
    )


def test_fresh_commit_then_idempotent_replay(disposable_database: Engine) -> None:
    admission_input = _input()

    first = run_c7_production_cutover_admission(
        disposable_database,
        admission_input=admission_input,
    )
    assert first.status == "COMMITTED"
    assert first.canonical_rows_before == 0
    assert first.canonical_rows_after == 1
    assert first.result.readback.idempotency_key == (
        f"idem:c7-production:{admission_input.trace_id}"
    )
    assert first.result.readback.project_key == PROJECT_KEY
    assert first.result.receipt.committed_revision == 1

    second = run_c7_production_cutover_admission(
        disposable_database,
        admission_input=admission_input,
    )
    assert second.status == "REPLAYED_COMMITTED"
    assert second.canonical_rows_before == 1
    assert second.canonical_rows_after == 1
    assert second.result.readback == first.result.readback
    assert second.result.receipt == first.result.receipt
    assert _legacy_count(disposable_database) == 1


def test_runner_seeds_exact_runtime_authority(disposable_database: Engine) -> None:
    run_c7_production_cutover_admission(
        disposable_database,
        admission_input=_input(),
    )
    with disposable_database.connect() as connection:
        authority = connection.execute(
            sa.select(PUBLIC_TABLES["runtime_capability_authority"]).where(
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == PROJECT_KEY
            )
        ).mappings().one()
        assert authority["successor_claim_enabled"] is True
        assert authority["legacy_claim_enabled"] is False
        canonical = connection.execute(
            sa.select(sa.func.count()).select_from(C7_MOVEMENT_CANONICAL_DOCUMENTS)
        ).scalar_one()
        assert int(canonical) == 1
