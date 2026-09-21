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
    def store(
        self,
        results: list[dict[str, Any]],
        *,
        project_key: str | None = None,
        job_type: str | None = None,
    ) -> dict[str, Any]:
        ...


class DiscoveryAdapterPort(DiscoverySearchPort, DiscoveryStorePort, Protocol):
    """Complete discovery capability required by the application service."""
