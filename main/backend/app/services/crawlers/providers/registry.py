from __future__ import annotations

from ..base import CrawlerProvider
from ..registry import get_provider, list_providers, register_provider


def get(provider: str) -> CrawlerProvider | None:
    return get_provider(provider)


__all__ = ["register_provider", "get_provider", "list_providers", "get"]
