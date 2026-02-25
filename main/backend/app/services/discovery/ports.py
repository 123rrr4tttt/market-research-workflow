from __future__ import annotations

from typing import Any, Protocol


class DiscoverySearchPort(Protocol):
    def search(self, **kwargs) -> list[dict[str, Any]]:
        ...

    def smart_search(self, **kwargs) -> list[dict[str, Any]]:
        ...

    def deep_search(self, **kwargs) -> dict[str, Any]:
        ...


class DiscoveryStorePort(Protocol):
    def store(self, results: list[dict[str, Any]]) -> dict[str, int]:
        ...
