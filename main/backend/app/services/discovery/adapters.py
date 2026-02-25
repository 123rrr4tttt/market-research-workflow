from __future__ import annotations

from typing import Any

from .deep_search import deep_search
from .store import store_results
from ..search.smart import smart_search
from ..search.web import search_sources


class DefaultDiscoveryAdapter:
    def search(self, **kwargs) -> list[dict[str, Any]]:
        return search_sources(**kwargs)

    def smart_search(self, **kwargs) -> list[dict[str, Any]]:
        return smart_search(**kwargs)

    def deep_search(self, **kwargs) -> dict[str, Any]:
        return deep_search(
            kwargs["topic"],
            kwargs.get("language", "en"),
            kwargs.get("iterations", 2),
            kwargs.get("breadth", 2),
            kwargs.get("max_results", 20),
        )

    def store(self, results: list[dict[str, Any]]) -> dict[str, int]:
        return store_results(results)
