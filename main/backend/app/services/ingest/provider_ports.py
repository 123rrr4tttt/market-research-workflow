"""Ports and record types for legacy ingest provider adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class PolicyDocument:
    state: str
    title: str
    status: str | None
    publish_date: date | None
    summary: str | None
    content: str
    uri: str | None = None
    source_name: str | None = None


class PolicyAdapterPort(Protocol):
    def fetch_documents(self) -> Iterable[PolicyDocument]: ...


class RedditPort(Protocol):
    def fetch_posts(
        self, subreddit: str, keywords: list[str] | None, limit: int
    ) -> Iterable[Any]: ...

    def search_multiple_subreddits(
        self, subreddits: list[str], keywords: list[str] | None, limit: int
    ) -> Iterable[Any]: ...

    def discover_subreddits(
        self, *, keywords: list[str], max_results: int, min_subscribers: int
    ) -> list[str]: ...


class GoogleNewsPort(Protocol):
    def search_multiple_keywords(
        self, keywords: list[str], limit: int
    ) -> Iterable[Any]: ...


PolicyAdapterResolver = Callable[[str, str | None], PolicyAdapterPort]
RedditAdapterFactory = Callable[[], RedditPort]
GoogleNewsAdapterFactory = Callable[[], GoogleNewsPort]

_POLICY_ADAPTER_RESOLVER: PolicyAdapterResolver | None = None
_REDDIT_ADAPTER_FACTORY: RedditAdapterFactory | None = None
_GOOGLE_NEWS_ADAPTER_FACTORY: GoogleNewsAdapterFactory | None = None


def set_ingest_adapter_providers(
    *,
    policy_resolver: PolicyAdapterResolver,
    reddit_factory: RedditAdapterFactory,
    google_news_factory: GoogleNewsAdapterFactory,
) -> None:
    global _POLICY_ADAPTER_RESOLVER
    global _REDDIT_ADAPTER_FACTORY, _GOOGLE_NEWS_ADAPTER_FACTORY
    _POLICY_ADAPTER_RESOLVER = policy_resolver
    _REDDIT_ADAPTER_FACTORY = reddit_factory
    _GOOGLE_NEWS_ADAPTER_FACTORY = google_news_factory


def get_policy_adapter(state: str, source_hint: str | None = None) -> PolicyAdapterPort:
    if _POLICY_ADAPTER_RESOLVER is None:
        # kit:boundary — app composition has not registered concrete providers.
        raise RuntimeError("policy adapter provider is not configured")
    return _POLICY_ADAPTER_RESOLVER(state, source_hint)


def get_reddit_adapter() -> RedditPort:
    if _REDDIT_ADAPTER_FACTORY is None:
        # kit:boundary — app composition has not registered concrete providers.
        raise RuntimeError("Reddit adapter provider is not configured")
    return _REDDIT_ADAPTER_FACTORY()


def get_google_news_adapter() -> GoogleNewsPort:
    if _GOOGLE_NEWS_ADAPTER_FACTORY is None:
        # kit:boundary — app composition has not registered concrete providers.
        raise RuntimeError("Google News adapter provider is not configured")
    return _GOOGLE_NEWS_ADAPTER_FACTORY()
