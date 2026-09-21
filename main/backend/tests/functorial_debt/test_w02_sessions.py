"""Packet-focused failure witnesses for the agent-session service/store."""

from __future__ import annotations

from pathlib import Path

from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.services.agent_sessions.service import (
    SESSION_STATUSES,
    _normalize_execution_mode,
    _normalize_phase,
    _normalize_status,
    AgentSessionService,
)
from app.services.agent_sessions import store as store_module
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from mrw_functorial_kit.core.agent_service_semantics import agent_session_failures


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED_FILES = {
    "main/backend/app/services/agent_sessions/service.py",
    "main/backend/app/services/agent_sessions/store.py",
}


def test_w02_sessions_no_throw_scan_is_empty() -> None:
    violations = scan_project(REPO_ROOT).violations
    assert [
        violation
        for violation in violations
        if violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
        and violation.file in OWNED_FILES
    ] == []


def test_w02_sessions_domain_failures_use_closed_kit_family() -> None:
    store = InMemoryAgentSessionStore()
    cases = [
        (store.create_session({}), "session_id_required"),
        (store.create_task({"session_id": "missing"}), "task_identity_required"),
        (store.create_message({}), "session_id_required"),
        (store.upsert_artifact({"session_id": "s"}), "artifact_identity_required"),
        (store.create_or_update_approval({}), "approval_id_required"),
        (store.get_approval("missing"), "approval_not_found"),
        (store.get_session("missing"), "session_not_found"),
        (store.get_task("missing", "missing"), "session_not_found"),
    ]
    for result, code in cases:
        assert isinstance(result, Failure)
        assert result.family == agent_session_failures.name
        assert result.code == code
        assert agent_session_failures.matches(result)


def test_w02_sessions_service_claim_failures_are_typed() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(source="user", entrypoint_type="chat", goal="typed failure")
    session_id = bundle["session"]["session_id"]
    task_id = bundle["tasks"][0]["task_id"]

    service.release_task(session_id, task_id, status="completed")
    not_claimable = service.claim_task(session_id, task_id, owner="worker")
    assert isinstance(not_claimable, Failure)
    assert not_claimable.code == "task_not_claimable"

    invalid = AgentSessionService(store=InMemoryAgentSessionStore()).create_session(
        source="user",
        entrypoint_type="chat",
        goal="invalid phase",
        task_blueprints=[{"task_id": "bad", "phase": "not-a-phase"}],
    )
    assert isinstance(invalid, Failure)
    assert invalid.code == "phase_invalid"


def test_w02_sessions_normalizers_cover_exact_failure_codes() -> None:
    checks = [
        (_normalize_status("bad", allowed=SESSION_STATUSES, default="pending"), "status_invalid"),
        (_normalize_phase("bad"), "phase_invalid"),
        (_normalize_execution_mode("bad"), "execution_mode_invalid"),
    ]
    for result, code in checks:
        assert isinstance(result, Failure)
        assert result.family == agent_session_failures.name
        assert result.code == code


def test_w02_sessions_backend_failure_is_visible(monkeypatch) -> None:
    monkeypatch.setattr(store_module, "_STORE", None)
    monkeypatch.setattr(store_module.settings, "agent_session_db_store_enabled", True)

    class BrokenStore:
        def __init__(self):
            raise RuntimeError("database offline")

    monkeypatch.setattr(store_module, "SqlAgentSessionStore", BrokenStore)
    result = store_module.build_agent_session_store()
    assert isinstance(result, Failure)
    assert result.family == agent_session_failures.name
    assert result.code == "backend_unavailable"
