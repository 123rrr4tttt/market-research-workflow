"""Packet-focused failure witnesses for the agent-session service/store."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project
from pytest import MonkeyPatch, skip
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.agent_sessions.service import (
    TASK_STATUSES,
    _normalize_execution_mode,
    _normalize_phase,
    _normalize_status,
    AgentSessionService,
)
from app.services.agent_sessions import store as store_module
from app.services.agent_sessions import service as service_module
from app.services.agent_sessions.store import InMemoryAgentSessionStore, SqlAgentSessionStore
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


def test_w02_sessions_service_input_failures_are_typed() -> None:
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
        (_normalize_status("bad", allowed=TASK_STATUSES, default="pending"), "status_invalid"),
        (_normalize_phase("bad"), "phase_invalid"),
        (_normalize_execution_mode("bad"), "execution_mode_invalid"),
    ]
    for result, code in checks:
        assert isinstance(result, Failure)
        assert result.family == agent_session_failures.name
        assert result.code == code


def test_w02_sessions_backend_failure_is_visible(monkeypatch: MonkeyPatch) -> None:
    store_module.reset_agent_session_store_for_tests()
    monkeypatch.setattr(store_module.settings, "agent_session_db_store_enabled", True)

    class BrokenStore:
        def __init__(self):
            raise RuntimeError("database offline")

    monkeypatch.setattr(store_module, "SqlAgentSessionStore", BrokenStore)
    result = store_module.build_agent_session_store()
    assert isinstance(result, Failure)
    assert result.family == agent_session_failures.name
    assert result.code == "backend_unavailable"


def test_w02_sessions_service_propagates_store_initialization_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    backend_failure = agent_session_failures.fail(
        "backend_unavailable",
        "agent session database backend unavailable",
        {"error": "database offline"},
    )
    monkeypatch.setattr(service_module, "build_agent_session_store", lambda: backend_failure)

    service = AgentSessionService()

    assert service.list_sessions() is backend_failure
    assert service.get_session("missing") is backend_failure
    assert service.list_events("missing") is backend_failure


def test_w02_sessions_postgres_commands_events_and_approvals_are_atomic(
    monkeypatch: MonkeyPatch,
) -> None:
    database_url = os.getenv("MRW_AGENT_SESSION_TEST_DATABASE_URL", "").strip()
    if not database_url:
        skip("set MRW_AGENT_SESSION_TEST_DATABASE_URL to an exclusive PostgreSQL test database")

    dedicated_engine = create_engine(database_url, pool_pre_ping=True)
    dedicated_session_local = sessionmaker(
        bind=dedicated_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(store_module, "engine", dedicated_engine)
    monkeypatch.setattr(store_module, "SessionLocal", dedicated_session_local)
    store = SqlAgentSessionStore()
    service = AgentSessionService(store=store)
    prefix = f"w02-{uuid4().hex[:12]}"

    try:
        sequence_session_id = f"{prefix}-events"
        created_session = store.create_session({"session_id": sequence_session_id})
        assert not isinstance(created_session, Failure)
        with ThreadPoolExecutor(max_workers=12) as executor:
            appended = list(
                executor.map(
                    lambda index: store.append_event(
                        sequence_session_id,
                        event_type="test.concurrent",
                        payload={"index": index},
                    ),
                    range(40),
                )
            )
        assert not any(isinstance(item, Failure) for item in appended)
        sequence_events = store.list_events(sequence_session_id)
        assert not isinstance(sequence_events, Failure)
        assert [event["seq"] for event in sequence_events] == list(range(1, 41))

        command_session_id = f"{prefix}-command-rollback"
        command_task_id = f"{prefix}-command-task"
        command_approval_id = f"{prefix}-command-approval"
        invalid_command_session_id = f"{prefix}-command-invalid-json"
        invalid_command = store.commit_session_command(
            invalid_command_session_id,
            session_create={
                "session_id": invalid_command_session_id,
                "metadata": {"invalid": ("tuple",)},
            },
            expected_session_statuses=None,
            session_changes={},
            task_creates=[],
            task_mutations=[],
            message_creates=[],
            artifact_upserts=[],
            approval_mutation=None,
            events=[],
        )
        assert isinstance(invalid_command, Failure)
        assert invalid_command.code == "json_value_invalid"
        assert isinstance(store.get_session(invalid_command_session_id), Failure)

        command_failure = store.commit_session_command(
            command_session_id,
            session_create={
                "session_id": command_session_id,
                "source": "test",
                "entrypoint_type": "test",
                "goal": "rollback every command fact",
                "status": "pending",
            },
            expected_session_statuses=None,
            session_changes={},
            task_creates=[
                {
                    "session_id": command_session_id,
                    "task_id": command_task_id,
                    "subject": "command task",
                    "task_type": "implementation",
                    "phase": "implementation",
                }
            ],
            task_mutations=[],
            message_creates=[
                {
                    "session_id": command_session_id,
                    "role": "user",
                    "content": "must rollback",
                }
            ],
            artifact_upserts=[
                {
                    "session_id": command_session_id,
                    "artifact_type": "test.snapshot",
                    "name": "must-rollback.json",
                    "content_json": {"value": "rollback"},
                }
            ],
            approval_mutation={
                "expected_statuses": [],
                "payload": {
                    "approval_id": command_approval_id,
                    "binding_hash": "binding",
                    "binding_payload": {"action": "rollback"},
                    "requester_session_id": command_session_id,
                    "requester_task_id": command_task_id,
                    "requester_actor": "test",
                    "status": "pending",
                },
            },
            events=[
                {
                    "event_type": "x" * 200,
                    "task_id": command_task_id,
                    "payload": {"result": "must rollback"},
                }
            ],
        )
        assert isinstance(command_failure, Failure)
        assert command_failure.code == "backend_unavailable"
        assert command_failure.context["operation"] == "commit_session_command"
        assert isinstance(store.get_session(command_session_id), Failure)
        assert isinstance(store.get_approval(command_approval_id), Failure)

        approval_bundle = service.create_session(
            source="test",
            entrypoint_type="test",
            goal="PostgreSQL approval CAS",
            logical_task_list_key=f"{prefix}-approval",
            task_blueprints=[
                {
                    "task_id": f"{prefix}-approval-task",
                    "subject": "approval task",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["external:approval"],
                }
            ],
        )
        assert not isinstance(approval_bundle, Failure)
        approval_session_id = approval_bundle["session"]["session_id"]
        approval = service.request_approval(
            session_id=approval_session_id,
            task_id=f"{prefix}-approval-task",
            requester_actor="test",
            binding_payload={"action": "write"},
            metadata={"force_approval": True},
        )
        assert not isinstance(approval, Failure)
        original_get_approval = store.get_approval
        approval_readers_ready = Barrier(2)

        def synchronized_get_approval(approval_id: str):
            value = original_get_approval(approval_id)
            approval_readers_ready.wait(timeout=5)
            return value

        with patch.object(store, "get_approval", side_effect=synchronized_get_approval):
            with ThreadPoolExecutor(max_workers=2) as executor:
                resolutions = list(
                    executor.map(
                        lambda actor: service.resolve_approval(
                            approval["approval_id"],
                            approved_by=actor,
                        ),
                        ("approver-a", "approver-b"),
                    )
                )
        approval_winners = [
            item for item in resolutions if not isinstance(item, Failure)
        ]
        approval_losers = [
            item for item in resolutions if isinstance(item, Failure)
        ]
        assert len(approval_winners) == 1
        assert len(approval_losers) == 1
        approval_events = store.list_events(approval_session_id)
        assert not isinstance(approval_events, Failure)
        assert [event["event_type"] for event in approval_events].count(
            "approval.approved"
        ) == 1

    finally:
        dedicated_engine.dispose()
