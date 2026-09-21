"""Focused shell-boundary witnesses for the latest Service-A ingest slice."""

from __future__ import annotations

from typing import Any
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _EnteringFailure:
    def __enter__(self) -> Any:
        raise RuntimeError("shell boundary exploded")

    def __exit__(self, *_args: Any) -> bool:
        return False


class _CommitFailure:
    def __enter__(self) -> "_CommitFailure":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def commit(self) -> None:
        raise RuntimeError("persistence boundary exploded")

    def rollback(self) -> None:
        return None


def test_latest_service_a_ingest_shell_boundaries_reraise_original_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each retained shell boundary is exercised with its original exception ABI."""
    from app.services.ingest import news, policy, raw_import, social, url_pool
    from app.services.ingest.reports import california, general

    monkeypatch.setattr(news, "start_job", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(news, "fail_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(news, "fetch_html", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("news fetch")))
    with pytest.raises(RuntimeError, match="^news fetch$"):
        news.collect_official_news_updates(url="https://example.com", source_name="example", base_url="example.com")

    class _RedditAdapter:
        def fetch_posts(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("reddit fetch")

    monkeypatch.setattr(news, "get_reddit_adapter", lambda: _RedditAdapter())
    with pytest.raises(RuntimeError, match="^reddit fetch$"):
        news.collect_reddit_discussions(subreddit="stocks", limit=1)

    class _GoogleAdapter:
        def search_multiple_keywords(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("google news fetch")

    monkeypatch.setattr(news, "get_google_news_adapter", lambda: _GoogleAdapter())
    with pytest.raises(RuntimeError, match="^google news fetch$"):
        news.collect_google_news(["market"], limit=1)

    monkeypatch.setattr(
        policy,
        "get_policy_adapter",
        lambda *_args, **_kwargs: type("A", (), {"fetch_documents": lambda self: []})(),
    )
    monkeypatch.setattr(policy, "start_job", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(policy, "fail_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(policy, "SessionLocal", lambda: _CommitFailure())
    with pytest.raises(RuntimeError, match="^persistence boundary exploded$"):
        policy.ingest_policy_documents("CA")

    class _Query:
        def filter(self, *_args: Any, **_kwargs: Any) -> "_Query":
            return self

        def first(self) -> None:
            return None

    class _PolicySession:
        def __enter__(self) -> "_PolicySession":
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def query(self, *_args: Any, **_kwargs: Any) -> _Query:
            return _Query()

        def add(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def flush(self) -> None:
            return None

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    policy_doc = SimpleNamespace(
        content="policy body",
        summary="",
        uri="https://example.com/policy",
        state="CA",
        title="Policy",
        status="published",
        publish_date=None,
    )
    monkeypatch.setattr(
        policy,
        "get_policy_adapter",
        lambda *_args, **_kwargs: SimpleNamespace(fetch_documents=lambda: [policy_doc]),
    )
    monkeypatch.setattr(policy, "SessionLocal", lambda: _PolicySession())
    monkeypatch.setattr(policy, "_get_or_create_source", lambda *_args, **_kwargs: SimpleNamespace(name="source"))
    monkeypatch.setattr(policy, "build_frontdoor_ingress_envelope", lambda **_kwargs: {})
    monkeypatch.setattr(
        policy,
        "run_postprocess_frontdoor",
        lambda **_kwargs: {"data": {"writer_result": {"inserted": 1, "doc_id": 10}}},
    )
    with patch("app.services.indexer.index_policy_documents", side_effect=RuntimeError("indexing boundary")):
        with pytest.raises(RuntimeError, match="^indexing boundary$"):
            policy.ingest_policy_documents("CA")

    monkeypatch.setattr(raw_import, "start_job", lambda *_args, **_kwargs: 3)
    monkeypatch.setattr(raw_import, "fail_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(raw_import, "SessionLocal", lambda: _EnteringFailure())
    with pytest.raises(RuntimeError, match="^shell boundary exploded$"):
        raw_import.run_raw_import_documents({"items": []}, "demo")

    monkeypatch.setattr(social, "start_job", lambda *_args, **_kwargs: 4)
    monkeypatch.setattr(social, "fail_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(social, "SessionLocal", lambda: _EnteringFailure())
    with pytest.raises(RuntimeError, match="^shell boundary exploded$"):
        social.collect_user_social_sentiment(["market"])

    with patch("app.services.search.web.search_sources", side_effect=RuntimeError("policy search")):
        monkeypatch.setattr(social, "start_job", lambda *_args, **_kwargs: 5)
        with pytest.raises(RuntimeError, match="^policy search$"):
            social.collect_policy_and_regulation(["market"], limit=1)

    with patch.object(california, "start_job", return_value=6), patch.object(
        california, "fail_job"
    ), patch.object(california, "search_sources", side_effect=RuntimeError("california search")):
        with pytest.raises(RuntimeError, match="^california search$"):
            california.collect_california_sales_reports()

    with patch.object(general, "start_job", return_value=7), patch.object(
        general, "fail_job"
    ), patch.object(general, "search_sources", side_effect=RuntimeError("weekly search")):
        with pytest.raises(RuntimeError, match="^weekly search$"):
            general.collect_weekly_market_reports()
    with patch.object(general, "start_job", return_value=8), patch.object(
        general, "fail_job"
    ), patch.object(general, "search_sources", side_effect=RuntimeError("monthly search")):
        with pytest.raises(RuntimeError, match="^monthly search$"):
            general.collect_monthly_financial_reports()

    monkeypatch.setattr(url_pool, "start_job", lambda *_args, **_kwargs: 9)
    monkeypatch.setattr(url_pool, "fail_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(url_pool, "list_urls", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("pool lookup")))
    with pytest.raises(RuntimeError, match="^pool lookup$"):
        url_pool.collect_urls_from_pool(project_key="demo")
