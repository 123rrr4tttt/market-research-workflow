"""Composition root for legacy ingest provider adapters."""

from __future__ import annotations

from collections.abc import Iterable

from app.services.ingest.adapters.base import PolicyAdapter
from app.services.ingest.adapters.ca_legislature import CaliforniaLegislatureAdapter
from app.services.ingest.adapters.legiscan_api import LegiScanApiAdapter
from app.services.ingest.adapters.news_google import GoogleNewsAdapter, GoogleNewsItem
from app.services.ingest.adapters.social_reddit import RedditAdapter, RedditPost
from app.services.ingest.provider_ports import set_ingest_adapter_providers


def _resolve_policy_adapter(state: str, source_hint: str | None) -> PolicyAdapter:
    state_key = state.upper()
    if source_hint and source_hint.lower() == "legiscan":
        return LegiScanApiAdapter(state_key)
    if state_key != "CA":
        raise ValueError(f"暂无州 {state_key} 的政策适配器；可尝试设置 source_hint=legiscan")
    return CaliforniaLegislatureAdapter(state_key)


class _RedditPortAdapter:
    def __init__(self) -> None:
        self._adapter = RedditAdapter()

    def fetch_posts(
        self,
        subreddit: str,
        keywords: list[str] | None,
        limit: int,
    ) -> Iterable[RedditPost]:
        return self._adapter.fetch_posts(subreddit, keywords, limit)

    def search_multiple_subreddits(
        self,
        subreddits: list[str],
        keywords: list[str] | None,
        limit: int,
    ) -> Iterable[RedditPost]:
        return self._adapter.search_multiple_subreddits(
            subreddits,
            keywords,
            limit_per_subreddit=limit,
        )

    def discover_subreddits(
        self,
        *,
        keywords: list[str],
        max_results: int,
        min_subscribers: int,
    ) -> list[str]:
        return self._adapter.discover_subreddits(
            keywords=keywords,
            max_results=max_results,
            min_subscribers=min_subscribers,
        )


class _GoogleNewsPortAdapter:
    def __init__(self) -> None:
        self._adapter = GoogleNewsAdapter()

    def search_multiple_keywords(
        self,
        keywords: list[str],
        limit: int,
    ) -> Iterable[GoogleNewsItem]:
        return self._adapter.search_multiple_keywords(
            keywords,
            limit_per_keyword=limit,
        )


def configure_ingest_adapters() -> None:
    set_ingest_adapter_providers(
        policy_resolver=_resolve_policy_adapter,
        reddit_factory=_RedditPortAdapter,
        google_news_factory=_GoogleNewsPortAdapter,
    )
