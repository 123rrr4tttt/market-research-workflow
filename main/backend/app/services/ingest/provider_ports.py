"""Ports and record types for legacy ingest provider adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(slots=True)
class MarketRecord:
    state: str
    date: date
    sales_volume: float | None = None
    revenue: float | None = None
    jackpot: float | None = None
    ticket_price: float | None = None
    source_name: str | None = None
    uri: str | None = None
    game: str | None = None
    draw_number: str | None = None
    extra: dict[str, Any] | None = None


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


class MarketAdapterPort(Protocol):
    def fetch_records(self) -> Iterable[MarketRecord]: ...


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


MarketAdapterResolver = Callable[[str, str | None, dict[str, Any]], list[MarketAdapterPort]]
PolicyAdapterResolver = Callable[[str, str | None], PolicyAdapterPort]
RedditAdapterFactory = Callable[[], RedditPort]
GoogleNewsAdapterFactory = Callable[[], GoogleNewsPort]

_MARKET_ADAPTER_RESOLVER: MarketAdapterResolver | None = None
_POLICY_ADAPTER_RESOLVER: PolicyAdapterResolver | None = None
_REDDIT_ADAPTER_FACTORY: RedditAdapterFactory | None = None
_GOOGLE_NEWS_ADAPTER_FACTORY: GoogleNewsAdapterFactory | None = None


def set_ingest_adapter_providers(
    *,
    market_resolver: MarketAdapterResolver,
    policy_resolver: PolicyAdapterResolver,
    reddit_factory: RedditAdapterFactory,
    google_news_factory: GoogleNewsAdapterFactory,
) -> None:
    global _MARKET_ADAPTER_RESOLVER, _POLICY_ADAPTER_RESOLVER
    global _REDDIT_ADAPTER_FACTORY, _GOOGLE_NEWS_ADAPTER_FACTORY
    _MARKET_ADAPTER_RESOLVER = market_resolver
    _POLICY_ADAPTER_RESOLVER = policy_resolver
    _REDDIT_ADAPTER_FACTORY = reddit_factory
    _GOOGLE_NEWS_ADAPTER_FACTORY = google_news_factory


def get_market_adapters(
    state: str,
    source_hint: str | None = None,
    inject_params: dict[str, Any] | None = None,
) -> list[MarketAdapterPort]:
    if _MARKET_ADAPTER_RESOLVER is None:
        # kit:boundary — app composition has not registered concrete providers.
        raise RuntimeError("market adapter provider is not configured")
    return _MARKET_ADAPTER_RESOLVER(state, source_hint, inject_params or {})


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
