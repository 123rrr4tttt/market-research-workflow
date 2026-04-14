from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CrawlerDispatchRequest:
    provider: str
    project: str
    spider: str
    arguments: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    version: str | None = None
    priority: int | None = None
    job_id: str | None = None


@dataclass(slots=True)
class CrawlerDispatchResult:
    provider_type: str
    provider_status: str
    provider_job_id: str | None = None
    attempt_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class CrawlerProvider(Protocol):
    provider_type: str

    def dispatch(self, request: CrawlerDispatchRequest) -> CrawlerDispatchResult:
        ...


__all__ = [
    "CrawlerDispatchRequest",
    "CrawlerDispatchResult",
    "CrawlerProvider",
]
