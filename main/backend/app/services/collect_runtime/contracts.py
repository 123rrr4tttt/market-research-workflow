from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CollectRequest:
    flow: str = "collect"
    channel: str = ""
    project_key: str | None = None
    query_terms: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    limit: int | None = None
    provider: str | None = None
    language: str | None = None
    scope: str | None = None
    item_key: str | None = None
    resource_id: str | None = None
    platforms: list[str] | None = None
    options: dict[str, Any] = field(default_factory=dict)
    source_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CollectResult:
    flow: str = "collect"
    channel: str = ""
    status: str = "completed"
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    display_meta: dict[str, Any] = field(default_factory=dict)


class CollectAdapter(Protocol):
    def run(self, request: CollectRequest) -> CollectResult:
        ...
