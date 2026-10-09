from __future__ import annotations

from typing import NotRequired, Protocol, TypedDict

from ..search.web import SearchResult


class DiscoveryDeepResult(TypedDict):
    topic: str
    language: str
    results: list[SearchResult]
    stored: NotRequired[DiscoveryStoreResult]


class DiscoveryStoreResult(TypedDict):
    inserted: int
    inserted_valid: int
    updated: int
    skipped: int
    rejected_count: int
    rejection_breakdown: dict[str, int]
    store_available: bool


class DiscoverySearchResult(TypedDict):
    # These leaves are direct observations from the open SearchResult row.
    keywords: list[object | None]
    results: list[SearchResult]
    provider_used: object
    stored: NotRequired[DiscoveryStoreResult]
    count: NotRequired[int]


class DiscoverySmartResult(TypedDict):
    topic: str
    results: list[SearchResult]
    count: int
    # This leaf is a direct observation from the open SearchResult row.
    provider_used: object
    stored: NotRequired[DiscoveryStoreResult]


class DiscoverySearchPort(Protocol):
    def search(
        self,
        *,
        topic: str,
        language: str = "en",
        max_results: int = 10,
        provider: str = "auto",
        days_back: int | None = None,
        exclude_existing: bool = True,
        start_offset: int | None = None,
        keywords: tuple[str, ...] | None = None,
        project_ref: str | None = None,
        source_ref: str | None = None,
        facet_ref: str | None = None,
    ) -> list[SearchResult]: ...

    def smart_search(
        self,
        *,
        topic: str,
        days_back: int = 30,
        max_results: int = 10,
        language: str = "en",
        provider: str = "auto",
    ) -> list[SearchResult]: ...

    def deep_search(
        self,
        *,
        topic: str,
        language: str = "en",
        iterations: int = 2,
        breadth: int = 2,
        max_results: int = 20,
    ) -> DiscoveryDeepResult: ...


class DiscoveryStorePort(Protocol):
    def store(
        self,
        results: list[SearchResult],
        *,
        project_key: str | None = None,
        job_type: str | None = None,
    ) -> DiscoveryStoreResult: ...


class DiscoveryAdapterPort(DiscoverySearchPort, DiscoveryStorePort, Protocol):
    """Complete discovery capability required by the application service."""
