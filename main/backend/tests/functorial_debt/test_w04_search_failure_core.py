"""Focused W04 witness for the Qdrant provider outcome and compatibility lift."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure

from app.services.search import hybrid


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_w04_search_qdrant_failure_core() -> None:
    failure = hybrid._qdrant_failure(
        "vector_search_failed",
        "qdrant_search_failed: transport closed",
        RuntimeError("transport closed"),
    )

    assert isinstance(failure, Failure)
    assert failure.family == "search.failure"
    assert failure.code == "vector_search_failed"
    assert failure.message == "qdrant_search_failed: transport closed"
    assert failure.context == {
        "owner": "search.hybrid.qdrant_port",
        "provider": "qdrant",
        "exception_type": "RuntimeError",
    }


def test_w04_search_qdrant_public_compatibility_lift(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = hybrid._qdrant_failure(
        "embedding_failed",
        "embed_failed: provider unavailable",
        RuntimeError("provider unavailable"),
    )
    monkeypatch.setattr(hybrid, "try_qdrant_vector_search", lambda *_args, **_kwargs: failure)

    with pytest.raises(RuntimeError, match=r"^embed_failed: provider unavailable$"):
        hybrid.qdrant_vector_search("market", None, 3)


def test_w04_search_vector_fallback_consumes_typed_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = hybrid._qdrant_failure(
        "backend_unavailable",
        "qdrant_unavailable: missing client",
        ImportError("missing client"),
    )

    class UnavailableEmbeddings:
        def embed_query(self, _query: str) -> list[float]:
            raise RuntimeError("fallback embeddings unavailable")

    monkeypatch.setattr(hybrid, "try_qdrant_vector_search", lambda *_args, **_kwargs: failure)
    monkeypatch.setattr(hybrid, "get_embeddings", lambda: UnavailableEmbeddings())

    assert hybrid.vector_search("market", None, 3) == []


def test_w04_search_qdrant_core_has_one_explicit_compatibility_lift() -> None:
    path = REPO_ROOT / "main/backend/app/services/search/hybrid.py"
    source = path.read_text(encoding="utf-8")
    raises = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Raise)]

    assert len(raises) == 1
    assert ast.get_source_segment(source, raises[0]) == "raise RuntimeError(result.message)"
    line = source.splitlines()[raises[0].lineno - 2]
    assert (
        "kit:boundary owner=search.hybrid.qdrant_compatibility_lift "
        "class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure "
        "witness=test:test_w04_search_qdrant_failure_core"
    ) in line
