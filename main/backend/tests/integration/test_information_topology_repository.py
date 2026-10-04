"""PostgreSQL-only integration coverage; target schema is provisioned by P00."""
from __future__ import annotations

import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, delete, inspect, text
from sqlalchemy.orm import sessionmaker

from app.models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from app.services.information_topology.contracts import BoundRef, Element, ElementRef, TopologyState
from app.services.information_topology.profiles import ProfileSpec, TypeRule
from app.services.information_topology.repository import InformationTopologyRepository, StateWrite


URL = os.environ.get("INFORMATION_TOPOLOGY_TEST_DATABASE_URL")
SCHEMA = os.environ.get("INFORMATION_TOPOLOGY_TEST_SCHEMA")
pytestmark = pytest.mark.skipif(
    not URL or not SCHEMA,
    reason="P00 must provide a dedicated PostgreSQL schema; shared/default DBs are not accepted",
)


def _state(project_key: str, local_id: str, revision: str) -> TopologyState:
    return TopologyState("test.profile", "1", (
        Element(BoundRef(ElementRef(project_key, "test-module", "test", "node", local_id), revision)),
    ))


def _repo() -> InformationTopologyRepository:
    profile = ProfileSpec("test.profile", "1", {"node": TypeRule()}, frozenset())
    return InformationTopologyRepository({("test.profile", "1"): profile})


def _session_factory():
    assert URL and SCHEMA
    assert re.fullmatch(r"[a-z_][a-z0-9_]*", SCHEMA), "dedicated schema must be a simple PostgreSQL identifier"
    engine = create_engine(URL, future=True, pool_size=4, max_overflow=0)

    @__import__("sqlalchemy").event.listens_for(engine, "connect")
    def _set_schema(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{SCHEMA}"')
        dbapi_connection.commit()
        cursor.close()

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_schema()")) == SCHEMA
        inspector = inspect(connection)
        assert inspector.has_table("information_topology_states", schema=SCHEMA)
        assert inspector.has_table("information_topology_links", schema=SCHEMA)
    return engine, sessionmaker(bind=engine, autoflush=False, future=True)


def _delete_test_project(engine, project_key: str) -> None:
    with engine.begin() as connection:
        connection.execute(delete(InformationTopologyLink).where(
            InformationTopologyLink.project_key == project_key,
        ))
        connection.execute(delete(InformationTopologyState).where(
            InformationTopologyState.project_key == project_key,
        ))


def test_postgres_batch_conflict_and_rollback():
    engine, sessions = _session_factory()
    repo = _repo()
    project_key = f"topology-test-{uuid.uuid4().hex}"
    key_a = (project_key, "test-module", "test", "a")
    key_b = (project_key, "test-module", "test", "b")
    try:
        with sessions.begin() as session:
            result = repo.apply_batch(session, states=(
                StateWrite(key_a, _state(project_key, "a", "source-1"), None),
                StateWrite(key_b, _state(project_key, "b", "source-1"), None),
            ))
            assert len(result) == 2
        with sessions.begin() as session:
            result = repo.apply_batch(session, states=(
                StateWrite(key_a, _state(project_key, "a", "source-2"), 1),
                StateWrite(key_b, _state(project_key, "b", "source-2"), 99),
            ))
            assert getattr(result, "code", None) == "VERSION_CONFLICT"
        with sessions() as session:
            assert repo.read_state(session, key_a)["revision"] == 1
    finally:
        _delete_test_project(engine, project_key)
        engine.dispose()


def test_postgres_two_clients_same_base_only_one_wins():
    engine, sessions = _session_factory()
    repo = _repo()
    project_key = f"topology-test-{uuid.uuid4().hex}"
    key = (project_key, "test-module", "test", "concurrent")
    with sessions.begin() as session:
        repo.apply_batch(session, states=(StateWrite(
            key, _state(project_key, "concurrent", "source-1"), None,
        ),))
    barrier = threading.Barrier(2)

    def writer(revision: str):
        with sessions.begin() as session:
            barrier.wait(timeout=10)
            return repo.apply_batch(
                session,
                states=(StateWrite(key, _state(project_key, "concurrent", revision), 1),),
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(writer, ("source-2a", "source-2b")))
        successes = [value for value in outcomes if isinstance(value, tuple)]
        conflicts = [value for value in outcomes if getattr(value, "code", None) == "VERSION_CONFLICT"]
        assert len(successes) == len(conflicts) == 1
        with sessions() as session:
            assert repo.read_state(session, key)["revision"] == 2
    finally:
        _delete_test_project(engine, project_key)
        engine.dispose()
