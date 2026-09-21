"""Opt-in live PostgreSQL witness for cross-process schema DDL serialization.

This module never uses the configured application database. It runs only when
``MRW_TEST_POSTGRES_URL`` names a local database whose name starts with
``mrw_test_``.
"""

# ruff: noqa: E402, TRY003

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import queue
import sys
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.services.projects.schema_initialization import run_serialized_schema_ddl


def _safe_test_url() -> str:
    raw_url = str(os.environ.get("MRW_TEST_POSTGRES_URL") or "").strip()
    if not raw_url:
        pytest.skip("MRW_TEST_POSTGRES_URL is not configured")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() not in {"postgresql", "postgres"}:
        pytest.skip("MRW_TEST_POSTGRES_URL is not PostgreSQL")
    if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("MRW_TEST_POSTGRES_URL must target a local isolated PostgreSQL")
    if not str(parsed.database or "").startswith("mrw_test_"):
        pytest.fail("MRW_TEST_POSTGRES_URL database must start with mrw_test_")
    return raw_url


def _ddl_worker(
    database_url: str,
    schema_name: str,
    worker_id: int,
    fail_after_ddl: bool,
    events: multiprocessing.Queue,
) -> None:
    database_engine = create_engine(database_url, pool_pre_ping=True)

    def operation(connection: object) -> None:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        connection.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS "{schema_name}".startup_race_witness '
                "(worker_id INTEGER PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema_name}".startup_race_witness(worker_id) '
                "VALUES (:worker_id) ON CONFLICT DO NOTHING"
            ),
            {"worker_id": worker_id},
        )
        if fail_after_ddl:
            events.put(("lock_acquired", worker_id))
            time.sleep(0.2)
            raise RuntimeError("injected transaction rollback")

    try:
        run_serialized_schema_ddl(
            database_engine,
            schema_name=schema_name,
            operation=operation,
        )
    except RuntimeError as exc:
        events.put(("failed", worker_id, str(exc)))
    else:
        events.put(("succeeded", worker_id))
    finally:
        database_engine.dispose()


@pytest.mark.integration
def test_postgresql_cross_process_ddl_race_rolls_back_and_recovers() -> None:
    database_url = _safe_test_url()
    schema_name = f"mrw_startup_{uuid4().hex}"
    context = multiprocessing.get_context("spawn")
    events = context.Queue()
    failing = context.Process(
        target=_ddl_worker,
        args=(database_url, schema_name, -1, True, events),
    )
    successful = [
        context.Process(
            target=_ddl_worker,
            args=(database_url, schema_name, worker_id, False, events),
        )
        for worker_id in range(6)
    ]
    database_engine = create_engine(database_url, pool_pre_ping=True)

    try:
        failing.start()
        assert events.get(timeout=10) == ("lock_acquired", -1)
        for process in successful:
            process.start()
        failing.join(timeout=15)
        for process in successful:
            process.join(timeout=15)
        assert failing.exitcode == 0
        assert all(process.exitcode == 0 for process in successful)

        observations = []
        for _index in range(7):
            try:
                observations.append(events.get(timeout=5))
            except queue.Empty as exc:
                raise AssertionError("missing worker observation") from exc
        assert ("failed", -1, "injected transaction rollback") in observations
        assert sorted(item[1] for item in observations if item[0] == "succeeded") == list(range(6))

        with database_engine.connect() as connection:
            worker_ids = connection.execute(
                text(
                    f'SELECT worker_id FROM "{schema_name}".startup_race_witness '
                    "ORDER BY worker_id"
                )
            ).scalars().all()
        assert worker_ids == list(range(6))
    finally:
        for process in [failing, *successful]:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        with database_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        database_engine.dispose()
