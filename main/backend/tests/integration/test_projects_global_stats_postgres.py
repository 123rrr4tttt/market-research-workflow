"""Opt-in PostgreSQL witness for canonical dashboard global counts.

Runs only when ``MRW_TEST_POSTGRES_URL`` names a local disposable database
whose name starts with ``mrw_test_``.  Each test creates and drops a unique
``mrw_test_gstats_*`` database and one random project schema.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine, ExecutionContext, make_url

from app.services.projects import global_stats
from app.settings.config import settings


pytestmark = pytest.mark.integration

DATABASE_ENV = "MRW_TEST_POSTGRES_URL"
SCHEMA_PREFIX = "project_gstats_"


def _safe_test_url() -> str:
    raw_url = str(os.environ.get(DATABASE_ENV) or "").strip()
    if not raw_url:
        pytest.skip(f"{DATABASE_ENV} is not configured")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() not in {"postgresql", "postgres"}:
        pytest.fail(f"{DATABASE_ENV} must use PostgreSQL")
    if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail(f"{DATABASE_ENV} must target local isolated PostgreSQL")
    if not str(parsed.database or "").startswith("mrw_test_"):
        pytest.fail(f"{DATABASE_ENV} database must start with mrw_test_")
    return raw_url


def _create_witness_database(admin_url: str) -> tuple[str, str, Engine]:
    database_name = f"mrw_test_gstats_{uuid4().hex}"
    admin_engine = create_engine(admin_url, pool_pre_ping=True)
    try:
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except Exception:
        admin_engine.dispose()
        raise
    witness_url = make_url(admin_url).set(database=database_name)
    return witness_url.render_as_string(hide_password=False), database_name, admin_engine


def _create_public_projects_if_needed(engine: Engine) -> bool:
    if inspect(engine).has_table("projects", schema="public"):
        return False
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE public.projects (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    schema_name VARCHAR(128) NOT NULL UNIQUE,
                    enabled BOOLEAN NOT NULL DEFAULT true,
                    is_active BOOLEAN NOT NULL DEFAULT false
                )
                """
            )
        )
    return True


def _drop_witness_database(admin_engine: Engine, database_name: str) -> None:
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :database_name AND pid <> pg_backend_pid()
                """
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))


@pytest.fixture
def witness(monkeypatch: pytest.MonkeyPatch):
    admin_url = _safe_test_url()
    database_url, database_name, admin_engine = _create_witness_database(admin_url)
    engine: Engine | None = None
    schema = f"{SCHEMA_PREFIX}{uuid4().hex}"
    project_key = f"gstats_{uuid4().hex}"
    public_projects_created = False
    schema_created = False
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        public_projects_created = _create_public_projects_if_needed(engine)
        monkeypatch.setattr(settings, "project_schema_prefix", "project_")
        monkeypatch.setattr(global_stats, "engine", engine)

        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            for table in ("documents", "market_metric_points", "price_observations"):
                connection.execute(text(f'CREATE TABLE "{schema}".{table} (id BIGSERIAL PRIMARY KEY)'))

        yield SimpleNamespace(engine=engine, schema=schema, project_key=project_key)
    finally:
        try:
            if engine is not None:
                try:
                    if public_projects_created and inspect(engine).has_table("projects", schema="public"):
                        with engine.begin() as connection:
                            connection.execute(
                                text("DELETE FROM public.projects WHERE project_key = :project_key"),
                                {"project_key": project_key},
                            )
                    if schema_created:
                        with engine.begin() as connection:
                            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                finally:
                    engine.dispose()
        finally:
            try:
                _drop_witness_database(admin_engine, database_name)
            finally:
                admin_engine.dispose()


def _insert_project(
    engine: Engine,
    *,
    project_key: str,
    schema: str,
    enabled: bool = True,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.projects(project_key, name, schema_name, enabled)
                VALUES (:project_key, :name, :schema, :enabled)
                """
            ),
            {"project_key": project_key, "name": project_key, "schema": schema, "enabled": enabled},
        )


def _insert_count(
    engine: Engine,
    *,
    schema: str,
    table: str,
    count: int,
) -> None:
    with engine.begin() as connection:
        for _ in range(count):
            connection.execute(text(f'INSERT INTO "{schema}".{table} DEFAULT VALUES'))


def test_enabled_project_counts_follow_current_canonical_rows(witness) -> None:
    _insert_project(witness.engine, project_key=witness.project_key, schema=witness.schema)
    _insert_count(witness.engine, schema=witness.schema, table="documents", count=3)
    _insert_count(witness.engine, schema=witness.schema, table="market_metric_points", count=5)
    _insert_count(witness.engine, schema=witness.schema, table="price_observations", count=2)

    disabled_schema = f"{witness.schema}_disabled"
    disabled_key = f"{witness.project_key}_disabled"
    with witness.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{disabled_schema}"'))
        connection.execute(text(f'CREATE TABLE "{disabled_schema}".documents (id BIGSERIAL PRIMARY KEY)'))
    _insert_project(witness.engine, project_key=disabled_key, schema=disabled_schema, enabled=False)
    _insert_count(witness.engine, schema=disabled_schema, table="documents", count=9)

    assert global_stats.query_global_canonical_stats() == {
        "documents_total": 3,
        "metrics_total": 5,
        "prices_total": 2,
    }

    with witness.engine.begin() as connection:
        connection.execute(text(f'DELETE FROM "{witness.schema}".documents WHERE id = 1'))
        connection.execute(text(f'DELETE FROM "{witness.schema}".price_observations WHERE id = 2'))

    assert global_stats.query_global_canonical_stats() == {
        "documents_total": 2,
        "metrics_total": 5,
        "prices_total": 1,
    }

    with witness.engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{disabled_schema}" CASCADE'))


def test_one_repeatable_read_snapshot_excludes_concurrent_committed_change(witness) -> None:
    _insert_project(witness.engine, project_key=witness.project_key, schema=witness.schema)
    _insert_count(witness.engine, schema=witness.schema, table="documents", count=1)
    _insert_count(witness.engine, schema=witness.schema, table="market_metric_points", count=1)
    _insert_count(witness.engine, schema=witness.schema, table="price_observations", count=1)

    project_query_seen = Event()
    project_query_may_finish = Event()

    def pause_after_project_snapshot(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        if "FROM public.projects" not in statement:
            return
        project_query_seen.set()
        assert project_query_may_finish.wait(timeout=10)

    event.listen(witness.engine, "after_cursor_execute", pause_after_project_snapshot)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(global_stats.query_global_canonical_stats)
            assert project_query_seen.wait(timeout=10)

            with witness.engine.begin() as connection:
                connection.execute(text(f'INSERT INTO "{witness.schema}".documents DEFAULT VALUES'))

            project_query_may_finish.set()
            result = future.result(timeout=10)
    finally:
        project_query_may_finish.set()
        event.remove(witness.engine, "after_cursor_execute", pause_after_project_snapshot)

    assert result == {"documents_total": 1, "metrics_total": 1, "prices_total": 1}

    assert global_stats.query_global_canonical_stats() == {
        "documents_total": 2,
        "metrics_total": 1,
        "prices_total": 1,
    }

    with witness.engine.begin() as connection:
        connection.execute(
            text("UPDATE public.projects SET enabled = false WHERE project_key = :project_key"),
            {"project_key": witness.project_key},
        )

    assert global_stats.query_global_canonical_stats() == {
        "documents_total": 0,
        "metrics_total": 0,
        "prices_total": 0,
    }


def test_invalid_stored_schema_fails_closed(witness) -> None:
    with witness.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.projects(project_key, name, schema_name, enabled)
                VALUES (:project_key, :name, 'aggregator', true)
                """
            ),
            {"project_key": witness.project_key, "name": witness.project_key},
        )

    with pytest.raises(ValueError, match="invalid stored schema"):
        global_stats.query_global_canonical_stats()


def test_missing_tenant_schema_fails_closed(witness) -> None:
    missing_schema = f"{witness.schema}_missing"
    _insert_project(witness.engine, project_key=witness.project_key, schema=missing_schema)

    with pytest.raises(Exception, match=f'"{missing_schema}"'):
        global_stats.query_global_canonical_stats()
