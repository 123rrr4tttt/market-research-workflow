"""Opt-in PostgreSQL witness for durable ingest idempotency reservation.

The test only runs against an explicitly supplied local disposable database.
It creates and drops one unique schema and never uses the configured
application database.
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier, Lock
from types import SimpleNamespace
from typing import TypeGuard
from uuid import uuid4

import pytest
from app.api import ingest as ingest_api
from app.models.ingest_registry import IngestSubmissionRegistry
from app.services.ingest.adapters import submission_registry
from app.services.ingest.adapters.submission_registry import (
    MaterialIngestRegistryConflictError,
)
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Connection, Engine, ExecutionContext, make_url
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration


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


def _schema_engine(database_url: str, schema_name: str) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        execution_options={"schema_translate_map": {None: schema_name}},
    )


def _object_dict(value: object) -> dict[str, object]:
    if not _is_object_dict(value) or not all(isinstance(key, str) for key in value):
        raise TypeError("expected a string-keyed object")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def test_postgres_concurrent_reserve_is_single_row_and_hash_drift_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _safe_test_url()
    schema_name = f"mrw_ingest_registry_{uuid4().hex}"
    admin_engine = create_engine(database_url, pool_pre_ping=True)
    database_engine = _schema_engine(database_url, schema_name)
    first_select_barrier = Barrier(2, timeout=10)
    select_lock = Lock()
    initial_selects = 0
    session_factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    registry_key = "ingest.url.single:project_a:postgres-race"
    url = "https://example.com/race"
    canonical_request_payload: dict[str, object] = {
        "project_key": "project_a",
        "url": url,
        "query_terms": ["market"],
        "strict_mode": False,
        "search_options": {},
        "async_mode": True,
    }
    request_hash = hashlib.sha256(
        json.dumps(
            canonical_request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    def synchronize_initial_selects(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        nonlocal initial_selects
        if "ingest_submission_registry" not in statement or not statement.lstrip().upper().startswith("SELECT"):
            return
        with select_lock:
            should_wait = initial_selects < 2
            initial_selects += 1
        if should_wait:
            first_select_barrier.wait()

    def bind_test_project(_project_key: str):
        return nullcontext()

    def reserve_same_payload() -> tuple[dict[str, object], bool]:
        return submission_registry.reserve_submission_db(
            registry_key=registry_key,
            project_key="project_a",
            idempotency_key="postgres-race",
            trigger_type="ingest.url.single",
            subject={"url": url, "project_key": "project_a"},
            request_payload=canonical_request_payload,
            request_hash=request_hash,
        )

    def reserve_drift_payload(
        *, url_suffix: str, request_hash_value: str
    ) -> tuple[dict[str, object], bool]:
        return submission_registry.reserve_submission_db(
            registry_key="ingest.url.single:project_a:postgres-drift-race",
            project_key="project_a",
            idempotency_key="postgres-drift-race",
            trigger_type="ingest.url.single",
            subject={"url": f"https://example.com/{url_suffix}"},
            request_payload={"url": f"https://example.com/{url_suffix}"},
            request_hash=request_hash_value,
        )

    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        IngestSubmissionRegistry.__table__.create(database_engine)
        event.listen(database_engine, "before_cursor_execute", synchronize_initial_selects)
        monkeypatch.setattr(submission_registry, "SessionLocal", session_factory)
        monkeypatch.setattr(submission_registry, "bind_project", bind_test_project)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(reserve_same_payload)
                for _index in range(2)
            ]
            observations = [future.result(timeout=15) for future in futures]

        assert sorted(duplicate for _submission, duplicate in observations) == [False, True]
        assert len({submission["submission_id"] for submission, _duplicate in observations}) == 1
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(IngestSubmissionRegistry)) == 1

        initial_selects = 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            drift_futures = [
                executor.submit(
                    reserve_drift_payload,
                    url_suffix="first",
                    request_hash_value="c" * 64,
                ),
                executor.submit(
                    reserve_drift_payload,
                    url_suffix="second",
                    request_hash_value="d" * 64,
                ),
            ]
            drift_outcomes: list[object] = []
            for future in drift_futures:
                try:
                    drift_outcomes.append(future.result(timeout=15))
                except MaterialIngestRegistryConflictError as exc:
                    drift_outcomes.append(exc)

        assert sum(isinstance(outcome, tuple) for outcome in drift_outcomes) == 1
        assert sum(isinstance(outcome, MaterialIngestRegistryConflictError) for outcome in drift_outcomes) == 1
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(IngestSubmissionRegistry)) == 2

        trusted_request = SimpleNamespace(
            state=SimpleNamespace(authenticated_actor_id="postgres-url-actor"),
            headers={},
        )
        exact_response = ingest_api.ingest_url_single(
            ingest_api.SingleUrlIngestRequest(
                project_key="project_a",
                url=url,
                query_terms=["market"],
                strict_mode=False,
                async_mode=True,
                idempotency_key="postgres-race",
            ),
            trusted_request,
        )
        exact_envelope = _object_dict(exact_response)
        exact_data = _object_dict(exact_envelope.get("data"))
        assert exact_data["duplicate"] is True
        assert exact_data["submission_id"] == observations[0][0]["submission_id"]
        with pytest.raises(HTTPException) as conflict:
            ingest_api.ingest_url_single(
                ingest_api.SingleUrlIngestRequest(
                    project_key="project_a",
                    url="https://example.com/changed",
                    query_terms=["market"],
                    strict_mode=False,
                    async_mode=True,
                idempotency_key="postgres-race",
            ),
            trusted_request,
        )
        assert conflict.value.status_code == 409
        conflict_detail = _object_dict(conflict.value.detail)
        conflict_error_envelope = _object_dict(conflict_detail.get("error"))
        conflict_error = _object_dict(conflict_error_envelope.get("details"))
        assert conflict_error["reason"] == "idempotency_key_payload_conflict"

        with pytest.raises(MaterialIngestRegistryConflictError) as raised:
            submission_registry.reserve_submission_db(
                registry_key=registry_key,
                project_key="project_a",
                idempotency_key="postgres-race",
                trigger_type="ingest.url.single",
                subject={"url": "https://example.com/changed"},
                request_payload={"url": "https://example.com/changed"},
                request_hash="b" * 64,
            )
        assert raised.value.registry_key == registry_key
        assert raised.value.request_hash == "b" * 64
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(IngestSubmissionRegistry)) == 2
    finally:
        database_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        admin_engine.dispose()
