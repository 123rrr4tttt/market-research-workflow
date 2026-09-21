from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.ingest.adapters import submission_registry
from app.services.typed_knowledge.adapters import live_service


pytestmark = pytest.mark.unit


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def scalar_one(self) -> Any:
        return self.value

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list[Any]:
        return list(self.value or [])


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.executed: list[Any] = []
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return False

    def execute(self, _statement: Any) -> _ScalarResult:
        self.executed.append(_statement)
        return _ScalarResult(None)

    def add(self, row: Any) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def refresh(self, _row: Any) -> None:
        return None


def test_ingest_submission_db_adapter_owns_project_session_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    bound_projects: list[str] = []

    @contextmanager
    def bind(project_key: str):
        bound_projects.append(project_key)
        yield

    monkeypatch.setattr(submission_registry, "SessionLocal", lambda: session)
    monkeypatch.setattr(submission_registry, "bind_project", bind)

    submission, duplicate = submission_registry.reserve_submission_db(
        registry_key="ingest.url.single:project_a:idem-1",
        project_key="project_a",
        idempotency_key="idem-1",
        trigger_type="ingest.url.single",
        subject={"url": "https://example.com"},
        request_payload={"url": "https://example.com"},
        request_hash="a" * 64,
    )

    assert bound_projects == ["project_a"]
    assert session.commit_count == 1
    assert len(session.added) == 1
    assert duplicate is False
    assert submission["project_key"] == "project_a"
    assert submission["idempotency_key"] == "idem-1"
    assert submission["registry_backend"] == "db"
    assert submission["registry_degraded"] is False


def test_typed_knowledge_live_adapter_owns_project_session_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    bound_projects: list[str] = []
    calls: list[dict[str, Any]] = []

    @contextmanager
    def bind(project_key: str):
        bound_projects.append(project_key)
        yield

    def build_envelope(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"data": {"project_key": kwargs["project_key"]}, "meta": {}}

    monkeypatch.setattr(live_service, "SessionLocal", lambda: session)
    monkeypatch.setattr(live_service, "bind_project", bind)
    monkeypatch.setattr(
        live_service.persistence_boundary,
        "build_live_db_boundary_envelope",
        build_envelope,
    )

    envelope = live_service.seed_live_sample(project_key="project_b")

    assert bound_projects == ["project_b"]
    assert session.commit_count == 1
    assert calls == [
        {"session": session, "project_key": "project_b", "seed_sample": True}
    ]
    assert envelope["data"]["project_key"] == "project_b"


def _submission_row(**overrides: Any) -> SimpleNamespace:
    values = {
        "submission_id": "sub-existing",
        "idempotency_key": "idem-existing",
        "trigger_type": "ingest.url.single",
        "project_key": "project_a",
        "registry_key": "ingest.url.single:project_a:idem-existing",
        "request_hash": "b" * 64,
        "subject_payload": {"url": "https://example.com"},
        "status": "submitted",
        "task_id": None,
        "created_at": None,
        "updated_at": None,
        "response_payload": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_ingest_submission_db_adapter_duplicate_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _submission_row()
    session = _Session()
    session.execute = lambda _statement: _ScalarResult(existing)  # type: ignore[method-assign]

    monkeypatch.setattr(submission_registry, "SessionLocal", lambda: session)

    submission, duplicate = submission_registry.reserve_submission_db(
        registry_key=existing.registry_key,
        project_key="project_a",
        idempotency_key=existing.idempotency_key,
        trigger_type=existing.trigger_type,
        subject={"url": "https://ignored.example"},
        request_payload={"url": "https://ignored.example"},
        request_hash="c" * 64,
    )

    assert duplicate is True
    assert submission["submission_id"] == "sub-existing"
    assert session.added == []
    assert session.commit_count == 0
    assert session.rollback_count == 0


def test_ingest_submission_db_adapter_integrity_conflict_rolls_back_and_rereads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _submission_row()

    class ConflictSession(_Session):
        def __init__(self) -> None:
            super().__init__()
            self.execute_count = 0

        def execute(self, _statement: Any) -> _ScalarResult:
            self.execute_count += 1
            return _ScalarResult(None if self.execute_count == 1 else existing)

        def commit(self) -> None:
            self.commit_count += 1
            raise IntegrityError("insert", {}, Exception("duplicate idempotency key"))

    session = ConflictSession()
    monkeypatch.setattr(submission_registry, "SessionLocal", lambda: session)

    submission, duplicate = submission_registry.reserve_submission_db(
        registry_key=existing.registry_key,
        project_key="project_a",
        idempotency_key=existing.idempotency_key,
        trigger_type=existing.trigger_type,
        subject={"url": "https://example.com"},
        request_payload={"url": "https://example.com"},
        request_hash="d" * 64,
    )

    assert duplicate is True
    assert submission["submission_id"] == "sub-existing"
    assert session.execute_count == 2
    assert session.commit_count == 1
    assert session.rollback_count == 1


def test_ingest_submission_db_completion_and_forget_preserve_exact_target_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _submission_row()
    complete_session = _Session()

    def complete_execute(statement: Any) -> _ScalarResult:
        complete_session.executed.append(statement)
        return _ScalarResult(row)

    complete_session.execute = complete_execute  # type: ignore[method-assign]
    forget_session = _Session()
    sessions = iter((complete_session, forget_session))
    bound_projects: list[str] = []

    @contextmanager
    def bind(project_key: str):
        bound_projects.append(project_key)
        yield

    monkeypatch.setattr(submission_registry, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(submission_registry, "bind_project", bind)

    submission_registry.complete_submission_db(
        registry_key=row.registry_key,
        response_payload={"task_id": "task-7", "status": "queued", "nested": {"ok": True}},
    )
    submission_registry.forget_submission_db(registry_key=row.registry_key)

    assert bound_projects == ["project_a", "project_a"]
    assert row.task_id == "task-7"
    assert row.status == "queued"
    assert row.response_payload == {"task_id": "task-7", "status": "queued", "nested": {"ok": True}}
    assert complete_session.commit_count == 1
    assert forget_session.commit_count == 1
    assert row.registry_key in complete_session.executed[0].compile().params.values()
    assert row.registry_key in forget_session.executed[0].compile().params.values()


def test_typed_knowledge_live_adapter_reads_do_not_commit_and_preserve_error_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = [_Session(), _Session()]
    session_iter = iter(sessions)
    sentinel = RuntimeError("typed read sentinel")

    monkeypatch.setattr(live_service, "SessionLocal", lambda: next(session_iter))
    monkeypatch.setattr(
        live_service.persistence_boundary,
        "build_live_db_boundary_envelope",
        lambda **_kwargs: {"data": {"project_key": "project_b"}, "meta": {}},
    )
    monkeypatch.setattr(
        live_service.persistence_boundary,
        "build_public_api_route_contract_envelope",
        lambda **kwargs: kwargs["boundary_envelope"],
    )

    envelope = live_service.read_live_public_route_contract(project_key="project_b")
    assert envelope["data"]["project_key"] == "project_b"
    assert sessions[0].commit_count == 0

    monkeypatch.setattr(
        live_service.persistence_boundary,
        "build_live_writing_context_from_repository",
        lambda **_kwargs: (_ for _ in ()).throw(sentinel),
    )
    with pytest.raises(RuntimeError) as raised:
        live_service.read_live_writing_context(project_key="project_b")

    assert raised.value is sentinel
    assert sessions[1].commit_count == 0
