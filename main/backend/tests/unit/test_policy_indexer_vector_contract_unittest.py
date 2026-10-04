from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.indexer import policy as policy_module
    from app.services.indexer.policy import (
        _build_vector_contract_payload,
        _raise_indexer_failure,
        _validate_vector_contract_payload,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class PolicyIndexerVectorContractUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"policy indexer vector contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_build_vector_contract_payload_derives_required_fields(self):
        doc = SimpleNamespace(
            id=42,
            uri="https://example.org/policy/42",
            publish_date=None,
            created_at=datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc),
            extracted_data={"project_key": "demo_proj", "language": "en"},
        )
        with patch.object(policy_module, "current_project_key", return_value="demo_proj"):
            payload = _build_vector_contract_payload(doc, "  clean text body  ")

        self.assertEqual(payload["project_key"], "demo_proj")
        self.assertEqual(payload["object_id"], 42)
        self.assertEqual(payload["object_type"], "policy_chunk")
        self.assertEqual(payload["language"], "en")
        self.assertEqual(payload["source_domain"], "example.org")
        self.assertEqual(payload["clean_text"], "clean text body")
        self.assertTrue(payload["keep_for_vectorization"])
        self.assertIsNone(_validate_vector_contract_payload(payload))

    def test_build_vector_contract_payload_rejects_foreign_extracted_project(self):
        doc = SimpleNamespace(
            id=42,
            uri=None,
            publish_date=None,
            created_at=None,
            extracted_data={"project_key": "other_project"},
        )

        with (
            patch.object(policy_module, "current_project_key", return_value="demo_proj"),
            self.assertRaisesRegex(ValueError, "^project_scope_conflict$"),
        ):
            _build_vector_contract_payload(doc, "clean text")

    def test_validate_vector_contract_payload_rejects_missing_fields(self):
        payload = {
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 1,
            "vector_version": "v1",
            "clean_text": "abc",
            "language": "en",
            "source_domain": None,
            "effective_time": None,
            "keep_for_vectorization": True,
        }

        failure = _validate_vector_contract_payload(payload)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure.family, "indexer.policy.failure")
        self.assertEqual(failure.code, "vector_contract_missing_fields")
        self.assertEqual(
            failure.message,
            "vector_contract_missing_fields: effective_time,source_domain",
        )
        with self.assertRaisesRegex(ValueError, "^vector_contract_missing_fields:"):
            _raise_indexer_failure(failure)

    def test_validate_vector_contract_payload_rejects_non_vectorizable_flag(self):
        payload = {
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 1,
            "vector_version": "v1",
            "clean_text": "abc",
            "language": "en",
            "source_domain": "example.org",
            "effective_time": "2026-03-03T10:00:00+00:00",
            "keep_for_vectorization": False,
        }

        failure = _validate_vector_contract_payload(payload)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure.family, "indexer.policy.failure")
        self.assertEqual(failure.code, "vector_contract_not_vectorizable")
        self.assertEqual(failure.message, "vector_contract_keep_for_vectorization_false")
        with self.assertRaisesRegex(ValueError, "^vector_contract_keep_for_vectorization_false$"):
            _raise_indexer_failure(failure)


class _IndexerQuery:
    def __init__(self, rows: list[object], on_delete=None) -> None:
        self.rows = rows
        self.on_delete = on_delete

    def filter(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    def order_by(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    def all(self) -> list[object]:
        return list(self.rows)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.on_delete is not None:
            self.on_delete()
        return 0


class _IndexerSession:
    def __init__(self, document: object) -> None:
        self.document = document
        self.added_embeddings: list[object] = []
        self.embedding_deletes = 0
        self.commits = 0
        self.rollbacks = 0

    def query(self, model: type):  # type: ignore[no-untyped-def]
        if model is policy_module.Document:
            return _IndexerQuery([self.document])
        return _IndexerQuery(
            [],
            on_delete=lambda: setattr(self, "embedding_deletes", self.embedding_deletes + 1),
        )

    def add(self, row: object) -> None:
        self.added_embeddings.append(row)

    def flush(self) -> None:
        for index, row in enumerate(self.added_embeddings, start=1):
            setattr(row, "id", index)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _SessionContext:
    def __init__(self, session: _IndexerSession) -> None:
        self.session = session

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


class _FakeEmbeddingRow:
    object_type = None
    object_id = None

    def __init__(self, **kwargs: object) -> None:
        self.id = 0
        self.__dict__.update(kwargs)


class _RecordingElasticsearch:
    def __init__(self) -> None:
        self.delete_queries: list[dict] = []

    def delete_by_query(self, **kwargs: object) -> None:
        self.delete_queries.append(dict(kwargs))


class _OneChunkSplitter:
    def __init__(self, **_kwargs: object) -> None:
        return None

    def split_text(self, text: str) -> list[str]:
        return [text]


class _IndexEffectObservations:
    def __init__(self) -> None:
        self.provider_initializations = 0
        self.embedding_texts: list[list[str]] = []
        self.es_client_calls = 0
        self.completed_jobs: list[object] = []
        self.failed_jobs: list[str] = []


def _document(project_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=17,
        doc_type="policy",
        content="shared policy body",
        summary=None,
        state="published",
        status="active",
        publish_date=None,
        title="Shared policy",
        uri="https://example.org/policy/17",
        created_at=datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc),
        extracted_data={"project_key": project_key},
    )


def _run_index(
    monkeypatch: pytest.MonkeyPatch,
    project_key: str,
    es: _RecordingElasticsearch,
    actions: list[dict],
) -> tuple[_IndexerSession, _IndexEffectObservations]:
    return _run_index_with_document(
        monkeypatch, project_key, es, actions, _document(project_key)
    )


def _configure_index(
    monkeypatch: pytest.MonkeyPatch,
    project_key: str,
    es: _RecordingElasticsearch,
    actions: list[dict],
    document: object,
) -> tuple[_IndexerSession, _IndexEffectObservations]:
    session = _IndexerSession(document)
    effects = _IndexEffectObservations()

    def embed_documents(texts: list[str]) -> list[list[float]]:
        effects.embedding_texts.append(list(texts))
        return [[0.0] for _ in texts]

    def complete_job(*args: object, **kwargs: object) -> None:
        effects.completed_jobs.append(kwargs.get("result"))

    def fail_job(*args: object, **kwargs: object) -> None:
        error = args[1] if len(args) > 1 else kwargs.get("error")
        effects.failed_jobs.append(str(error))

    def get_embeddings() -> object:
        effects.provider_initializations += 1
        return SimpleNamespace(embed_documents=embed_documents)

    def get_es_client() -> _RecordingElasticsearch:
        effects.es_client_calls += 1
        return es

    monkeypatch.setattr(policy_module, "SessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(policy_module.settings, "openai_api_key", "configured")
    monkeypatch.setattr(policy_module, "current_project_key", lambda: project_key)
    monkeypatch.setattr(policy_module, "start_job", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(policy_module, "complete_job", complete_job)
    monkeypatch.setattr(policy_module, "fail_job", fail_job)
    monkeypatch.setattr(policy_module, "Embedding", _FakeEmbeddingRow)
    monkeypatch.setattr(policy_module, "get_embeddings", get_embeddings)
    monkeypatch.setattr(policy_module, "get_es_client", get_es_client)
    monkeypatch.setattr(policy_module, "bulk", lambda _client, new_actions: actions.extend(new_actions))
    monkeypatch.setattr(policy_module, "RecursiveCharacterTextSplitter", _OneChunkSplitter)
    monkeypatch.setattr(policy_module, "_get_qdrant_client", lambda: None)
    return session, effects


def _run_index_with_document(
    monkeypatch: pytest.MonkeyPatch,
    project_key: str,
    es: _RecordingElasticsearch,
    actions: list[dict],
    document: object,
) -> tuple[_IndexerSession, _IndexEffectObservations]:
    session, effects = _configure_index(monkeypatch, project_key, es, actions, document)
    policy_module.index_policy_documents()
    return session, effects


def test_policy_es_identity_and_delete_are_project_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    es = _RecordingElasticsearch()
    actions: list[dict] = []

    _run_index(monkeypatch, "project-a", es, actions)
    _run_index(monkeypatch, "project-b", es, actions)

    assert [action["_id"] for action in actions] == [
        "policy-project-a-17-0",
        "policy-project-b-17-0",
    ]
    assert {action["project_key"] for action in actions} == {
        "project-a",
        "project-b",
    }
    assert len(es.delete_queries) == 2
    assert [
        query["body"]["query"]["bool"]["filter"] for query in es.delete_queries
    ] == [
        [{"term": {"project_key": "project-a"}}, {"terms": {"document_id": [17]}}],
        [{"term": {"project_key": "project-b"}}, {"terms": {"document_id": [17]}}],
    ]


def test_policy_rejects_missing_contract_field_before_index_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = _RecordingElasticsearch()
    actions: list[dict] = []
    invalid_document = _document("project-a")
    invalid_document.uri = None

    session, effects = _configure_index(
        monkeypatch, "project-a", es, actions, invalid_document
    )

    with pytest.raises(
        ValueError,
        match="^vector_contract_missing_fields: source_domain$",
    ):
        policy_module.index_policy_documents()

    assert effects.provider_initializations == 0
    assert effects.embedding_texts == []
    assert effects.es_client_calls == 0
    assert es.delete_queries == []
    assert actions == []
    assert session.embedding_deletes == 0
    assert session.commits == 0
    assert session.rollbacks == 1
    assert effects.completed_jobs == []
    assert effects.failed_jobs == ["vector_contract_missing_fields: source_domain"]


def test_policy_rejects_foreign_project_before_es_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    es = _RecordingElasticsearch()
    actions: list[dict] = []

    def current_project_key() -> str:
        return "project-a"

    monkeypatch.setattr(policy_module, "current_project_key", current_project_key)
    monkeypatch.setattr(
        policy_module,
        "SessionLocal",
        lambda: _SessionContext(_IndexerSession(_document("project-b"))),
    )
    monkeypatch.setattr(policy_module.settings, "openai_api_key", "configured")
    monkeypatch.setattr(policy_module, "start_job", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(policy_module, "fail_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(policy_module, "get_embeddings", lambda: object())
    monkeypatch.setattr(policy_module, "get_es_client", lambda: es)
    monkeypatch.setattr(policy_module, "bulk", lambda _client, new_actions: actions.extend(new_actions))

    with pytest.raises(ValueError, match="^project_scope_conflict$"):
        policy_module.index_policy_documents()

    assert es.delete_queries == []
    assert actions == []


def test_policy_bulk_failure_marks_job_failed_after_db_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = _RecordingElasticsearch()
    actions: list[dict] = []
    bulk_calls = 0

    def failing_bulk(_client: object, new_actions: list[dict]) -> None:
        nonlocal bulk_calls
        bulk_calls += 1
        actions.extend(new_actions)
        raise RuntimeError("es bulk unavailable")

    session, effects = _configure_index(monkeypatch, "project-a", es, actions, _document("project-a"))
    monkeypatch.setattr(policy_module, "bulk", failing_bulk)

    with pytest.raises(RuntimeError, match="^es bulk unavailable$"):
        policy_module.index_policy_documents()

    assert bulk_calls == 1
    assert actions != []
    assert effects.provider_initializations == 1
    assert len(effects.embedding_texts) == 1
    assert session.commits == 1
    assert session.rollbacks == 1
    assert effects.failed_jobs == ["es bulk unavailable"]
    assert effects.completed_jobs == []


if __name__ == "__main__":
    unittest.main()
