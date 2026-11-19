from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.services.document_queries import writing_documents
from app.services.writing import document_service, keyword_card_service
from functorial_kit import Failure
from sqlalchemy.orm import Session

from mrw_functorial_kit.core.service_failure_semantics import writing_failures

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_writing_failure_family_and_document_abi() -> None:
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


def test_writing_conflict_lift_preserves_fields_and_snapshot() -> None:
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


def test_writing_cache_and_action_not_found_keep_public_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    card = keyword_card_service.try_get_card_preview(
        type("Payload", (), {"card_id": "missing-card"})()
    )
    assert isinstance(card, Failure)
    assert card.code == "card_not_found"
    with pytest.raises(KeyError, match=r"^'card not found: missing-card'$" ):
        keyword_card_service.get_card_preview(type("Payload", (), {"card_id": "missing-card"})())


def test_writing_document_query_failure_lift(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)

    def missing_document(
        _session: Session,
        *,
        doc_id: int,
        project_key: str,
    ) -> None:
        del doc_id, project_key
        return None

    monkeypatch.setattr(writing_documents, "fetch_active_document", missing_document)
    with pytest.raises(KeyError, match=r"^'writing document not found: 404'$"):
        writing_documents.require_active_document(
            session,
            doc_id=404,
            project_key="demo",
        )

    invalid = Failure(family="other.failure", code="bad", message="bad", context={})

    def invalid_failure(
        _session: Session,
        *,
        doc_id: int,
        project_key: str,
    ) -> Failure:
        del doc_id, project_key
        return invalid

    monkeypatch.setattr(
        writing_documents,
        "try_require_active_document",
        invalid_failure,
    )
    with pytest.raises(TypeError, match="failure lift context"):
        writing_documents.require_active_document(
            session,
            doc_id=404,
            project_key="demo",
        )

def test_writing_owned_services_have_only_centralized_raise_boundary() -> None:
    paths = (
        REPO_ROOT / "main/backend/app/services/writing/document_service.py",
        REPO_ROOT / "main/backend/app/services/writing/keyword_card_service.py",
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
                    "witness=test:test_writing_failure_family_and_document_abi"
                )
        assert raise_functions <= {"_raise_writing_legacy"}
