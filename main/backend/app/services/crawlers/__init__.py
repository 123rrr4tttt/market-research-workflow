from __future__ import annotations

from .base import CrawlerDispatchRequest, CrawlerDispatchResult, CrawlerProvider
from .providers import ScrapyCrawlerProvider
from .registry import get_provider, list_providers, register_provider


def _register_builtin_providers() -> None:
    if get_provider("scrapy") is None:
        try:
            register_provider("scrapy", ScrapyCrawlerProvider())
        except Exception:
            # Keep import-safe when scrapyd env is not configured.
            return


_register_builtin_providers()

__all__ = [
    "CrawlerDispatchRequest",
    "CrawlerDispatchResult",
    "CrawlerProvider",
    "register_provider",
    "get_provider",
    "list_providers",
]
