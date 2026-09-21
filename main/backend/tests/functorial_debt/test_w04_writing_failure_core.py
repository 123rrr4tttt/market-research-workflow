from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import writing_failures

from app.services.writing import document_service, keyword_card_service, llm_action_service


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_w04_writing_failure_family_and_document_abi() -> None:
    failure = document_service._writing_failure(
        "document_not_found",
        "writing document not found: 404",
        owner="writing.document_service.get_document",
        public_exception=KeyError,
    )
    assert isinstance(failure, Failure)
    assert writing_failures.matches(failure)
    assert (failure.family, failure.code, failure.message) == (
        "writing.failure",
        "document_not_found",
        "writing document not found: 404",
    )
    with pytest.raises(KeyError, match=r"^'writing document not found: 404'$" ):
        document_service._raise_writing_legacy(failure)


def test_w04_writing_conflict_lift_preserves_fields_and_snapshot() -> None:
    snapshot = {"conflict_code": "VERSION_CONFLICT", "etag": "etag-2"}
    failure = document_service._writing_failure(
        "version_conflict",
        "writing document version conflict",
        owner="writing.document_service.save_document",
        public_exception="WritingVersionConflictError",
        expected_version=1,
        current_version=2,
        server_snapshot=snapshot,
    )
    with pytest.raises(document_service.WritingVersionConflictError) as raised:
        document_service._raise_writing_legacy(failure)
    assert raised.value.expected_version == 1
    assert raised.value.current_version == 2
    assert raised.value.server_snapshot == snapshot


def test_w04_writing_cache_and_action_not_found_keep_public_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    card = keyword_card_service.try_get_card_preview(
        type("Payload", (), {"card_id": "missing-card"})()
    )
    assert isinstance(card, Failure)
    assert card.code == "card_not_found"
    with pytest.raises(KeyError, match=r"^'card not found: missing-card'$" ):
        keyword_card_service.get_card_preview(type("Payload", (), {"card_id": "missing-card"})())

    monkeypatch.setattr(llm_action_service, "get_action_history", lambda **_kwargs: [])
    action = llm_action_service.try_get_action_detail(909, project_key="demo")
    assert isinstance(action, Failure)
    assert action.code == "action_not_found"
    with pytest.raises(KeyError, match=r"^'action history not found: 909'$" ):
        llm_action_service.get_action_detail(909, project_key="demo")


def test_w04_writing_llm_failure_fails_job_before_original_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    cause = RuntimeError("provider exploded")
    failure = llm_action_service._writing_failure(
        "action_execution_failed",
        str(cause),
        owner="writing.llm_action_service.dispatch_action",
        public_exception=type(cause).__name__,
        cause=cause,
        job_id=17,
    )
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(llm_action_service, "try_dispatch_action", lambda _payload: failure)
    monkeypatch.setattr(llm_action_service, "fail_job", lambda job_id, message: events.append(("fail_job", (job_id, message))))
    with pytest.raises(RuntimeError) as raised:
        llm_action_service.dispatch_action(object())
    assert raised.value is cause
    assert events == [("fail_job", (17, "provider exploded"))]


def test_w04_writing_owned_services_have_only_centralized_raise_boundary() -> None:
    paths = (
        REPO_ROOT / "main/backend/app/services/writing/document_service.py",
        REPO_ROOT / "main/backend/app/services/writing/keyword_card_service.py",
        REPO_ROOT / "main/backend/app/services/writing/llm_action_service.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        parent: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[child] = node
        raise_functions: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            current = parent.get(node)
            while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                current = parent.get(current)
            assert isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef))
            raise_functions.add(current.name)
            lines = source.splitlines()
            metadata = lines[node.lineno - 2] if node.lineno >= 2 else ""
            if current.name == "_raise_writing_legacy":
                statement = ast.get_source_segment(source, node) or ""
                expected_class = (
                    "PROGRAMMER_DEFECT"
                    if "TypeError" in statement
                    else "LEGACY_COMPATIBILITY_EXCEPTION"
                )
                assert metadata.strip() == (
                    "# kit:boundary owner=writing.document_service.failure_lift "
                    f"class={expected_class} "
                    f"failure_family={'none' if expected_class == 'PROGRAMMER_DEFECT' else 'writing.failure'} "
                    "witness=test:test_w04_writing_failure_core"
                )
        assert raise_functions <= {"_raise_writing_legacy"}
