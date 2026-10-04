"""Focused W03 witnesses for Service-A shell and compatibility boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import ProgrammingError

from app.services.collect_runtime import runtime as collect_runtime
from app.services.collect_runtime.contracts import CollectRequest, CollectResult
from app.services.crawlers import registry
from app.services.http.client import HttpClient
from app.services.indexer import policy as indexer_policy
from app.services import job_logger


# Keep the exact witness strings discoverable by the boundary metadata scanner.
WITNESSES = {
    "test:test_w03_collect_contract_failures",
    "test:test_w03_collect_programmer_defect_boundary",
    "test:test_w03_crawler_failure_lifts",
    "test:test_w03_indexer_contract_failures",
    "test:test_w03_effect_boundaries",
}


def test_w03_collect_contract_failures() -> None:
    assert "test:" + test_w03_collect_contract_failures.__name__ in WITNESSES
    failure = collect_runtime._collect_contract_failure(
        "skill_id_required",
        "skill_id is required",
        site="test.collect",
    )
    assert failure.family == "collect.runtime.failure"
    assert failure.code == "skill_id_required"
    with pytest.raises(ValueError, match="^skill_id is required$"):
        collect_runtime.register_collect_skill("", object())


def test_w03_collect_programmer_defect_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "test:" + test_w03_collect_programmer_defect_boundary.__name__ in WITNESSES
    monkeypatch.setattr(
        collect_runtime,
        "run_collect",
        lambda request: CollectResult(channel=request.channel),
    )
    monkeypatch.setattr(collect_runtime, "_SOURCE_LIBRARY_COMPAT_PROJECTOR", None)

    with pytest.raises(RuntimeError, match="^source-library compatibility projector is not configured$"):
        collect_runtime.run_source_library_item_compat(item_key="item-1")


def test_w03_crawler_failure_lifts() -> None:
    assert "test:" + test_w03_crawler_failure_lifts.__name__ in WITNESSES
    failure = registry._registry_precondition_failure(
        "crawler provider key is required",
        operation="test.registry",
        site="tests.functorial_debt",
    )
    with pytest.raises(ValueError, match="^crawler provider key is required$"):
        registry._raise_contract_failure(failure)

    with pytest.raises(TypeError, match="^crawler failure lift context is incomplete or inconsistent$"):
        registry._raise_contract_failure(failure, TypeError)


def test_w03_indexer_contract_failures() -> None:
    assert "test:" + test_w03_indexer_contract_failures.__name__ in WITNESSES
    failure = indexer_policy._validate_vector_contract_payload({})
    assert failure is not None
    assert failure.family == "indexer.policy.failure"
    assert failure.code == "vector_contract_missing_fields"
    with pytest.raises(ValueError, match="^vector_contract_missing_fields:"):
        indexer_policy._raise_indexer_failure(failure)


class _FailingHttpTransport:
    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("network failure")

    def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("network failure")


class _Query:
    def filter(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    def order_by(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    def all(self):
        return [
            SimpleNamespace(
                id=1,
                doc_type="policy",
                content="policy content",
                summary="",
                state="published",
                uri="https://example.test/policy/1",
                publish_date=None,
                created_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
                extracted_data={},
            )
        ]

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return 0


class _IndexerSession:
    def query(self, model):  # type: ignore[no-untyped-def]
        return _Query()

    def rollback(self) -> None:
        self.rolled_back = True


class _SessionContext:
    def __init__(self, session) -> None:  # type: ignore[no-untyped-def]
        self.session = session

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self.session

    def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
        return False


class _HistorySession:
    def execute(self, statement):  # type: ignore[no-untyped-def]
        raise ProgrammingError("history backend failure", None, RuntimeError("db"))


def test_w03_effect_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "test:" + test_w03_effect_boundaries.__name__ in WITNESSES
    request = CollectRequest(channel="search.market")
    with pytest.raises(RuntimeError, match="^batch failure$"):
        collect_runtime._run_single_auto_batch(
            request,
            ["term"],
            1,
            lambda _request: (_ for _ in ()).throw(RuntimeError("batch failure")),
            fail_fast=True,
        )

    http_client = object.__new__(HttpClient)
    http_client.max_retries = 0
    http_client._client = _FailingHttpTransport()
    monkeypatch.setattr("app.services.http.client.time.sleep", lambda _seconds: None)
    for method in (http_client.get_json, http_client.post_json, http_client.get_text):
        with pytest.raises(RuntimeError, match="^network failure$"):
            method("https://example.test")

    indexer_session = _IndexerSession()
    monkeypatch.setattr(indexer_policy, "SessionLocal", lambda: _SessionContext(indexer_session))
    monkeypatch.setattr(indexer_policy.settings, "openai_api_key", "configured")
    monkeypatch.setattr(indexer_policy, "start_job", lambda *_args, **_kwargs: 1)
    failed_jobs: list[tuple[int, str]] = []
    monkeypatch.setattr(indexer_policy, "fail_job", lambda job_id, error: failed_jobs.append((job_id, error)))
    monkeypatch.setattr(
        indexer_policy,
        "get_embeddings",
        lambda: (_ for _ in ()).throw(RuntimeError("embedding failure")),
    )
    with pytest.raises(RuntimeError, match="^embedding failure$"):
        indexer_policy.index_policy_documents()
    assert failed_jobs == [(1, "embedding failure")]

    monkeypatch.setattr(job_logger, "SessionLocal", lambda: _SessionContext(_HistorySession()))
    with pytest.raises(ProgrammingError, match="history backend failure"):
        job_logger.list_jobs()
