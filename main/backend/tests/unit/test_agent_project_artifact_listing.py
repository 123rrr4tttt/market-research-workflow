from unittest.mock import MagicMock

import pytest
from functorial_kit import Failure
from sqlalchemy.dialects import postgresql

from app.services.agent_sessions import store as store_module
from app.services.agent_sessions.store import InMemoryAgentSessionStore, SqlAgentSessionStore


pytestmark = pytest.mark.unit


def test_exact_project_artifact_missing_is_optional_and_invalid_write_is_failure(monkeypatch):
    memory = InMemoryAgentSessionStore()
    assert memory.get_project_artifact(project_key="a", name="missing") is None
    assert isinstance(memory.upsert_project_artifact({}), Failure)
    session = MagicMock()
    session.__enter__.return_value = session
    session.query.return_value.filter.return_value.all.return_value = []
    monkeypatch.setattr(store_module, "SessionLocal", lambda: session)
    sql = SqlAgentSessionStore.__new__(SqlAgentSessionStore)
    assert sql.get_project_artifact(project_key="a", name="missing") is None
    assert isinstance(sql.upsert_project_artifact({}), Failure)


def test_memory_project_artifacts_are_scoped_sorted_and_copied():
    store = InMemoryAgentSessionStore()
    for project, name in (("a", "z"), ("b", "other"), ("a", "a")):
        store.upsert_project_artifact({
            "project_key": project, "name": name, "content_json": {"value": name},
        })
    rows = store.list_project_artifacts(project_key="a")
    assert [row["name"] for row in rows] == ["a", "z"]
    rows[0]["content_json"]["value"] = "mutated"
    assert store.list_project_artifacts(project_key="a")[0]["content_json"]["value"] == "a"
    assert store.list_project_artifacts(project_key="missing") == []
    assert isinstance(store.list_project_artifacts(project_key=""), Failure)


def test_sql_project_listing_uses_canonical_project_scope(monkeypatch):
    session = MagicMock()
    query = session.query.return_value
    query.filter.return_value.order_by.return_value.all.return_value = []
    session.__enter__.return_value = session
    monkeypatch.setattr(store_module, "SessionLocal", lambda: session)
    store = SqlAgentSessionStore.__new__(SqlAgentSessionStore)
    assert store.list_project_artifacts(project_key="project-a") == []
    clauses = query.filter.call_args.args
    compiled = [clause.compile(dialect=postgresql.dialect()) for clause in clauses]
    assert any("agent_macro.registration_package" in clause.params.values() for clause in compiled)
    assert any("project-a" in clause.params.values() for clause in compiled)
    assert any("project_scope" in clause.params.values() and "IS true" in str(clause) for clause in compiled)
    assert isinstance(store.list_project_artifacts(project_key=""), Failure)


def test_native_thread_lookup_is_exact_scoped_and_rejects_ambiguity():
    store = InMemoryAgentSessionStore()
    payload = {
        "session_id": "host-session", "source": "codex_webui_host",
        "entrypoint_type": "codex_native_thread", "metadata": {"native_thread_id": "native-1"},
    }
    store.create_session(payload)
    store.create_session({**payload, "session_id": "untrusted", "source": "user"})
    store.create_session({**payload, "session_id": "different", "metadata": {"native_thread_id": "native-2"}})
    assert store.find_session_by_native_thread_id("native-1")["session_id"] == "host-session"
    assert store.find_session_by_native_thread_id("missing") is None
    store.create_session({**payload, "session_id": "duplicate"})
    assert isinstance(store.find_session_by_native_thread_id("native-1"), Failure)


def test_sql_native_thread_lookup_uses_exact_owner_and_bounded_query(monkeypatch):
    session = MagicMock()
    query = session.query.return_value
    query.filter.return_value.limit.return_value.all.return_value = []
    session.__enter__.return_value = session
    monkeypatch.setattr(store_module, "SessionLocal", lambda: session)
    store = SqlAgentSessionStore.__new__(SqlAgentSessionStore)
    assert store.find_session_by_native_thread_id("native-1") is None
    compiled = [clause.compile(dialect=postgresql.dialect()) for clause in query.filter.call_args.args]
    parameters = [value for clause in compiled for value in clause.params.values()]
    assert all(value in parameters for value in ("codex_webui_host", "codex_native_thread", "native-1"))
    query.filter.return_value.limit.assert_called_once_with(2)
