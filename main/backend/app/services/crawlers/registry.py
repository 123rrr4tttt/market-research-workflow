from __future__ import annotations

from .base import CrawlerProvider


_PROVIDERS: dict[str, CrawlerProvider] = {}


def _normalize(provider: str) -> str:
    return str(provider or "").strip().lower()


def register_provider(provider: str, instance: CrawlerProvider) -> None:
    key = _normalize(provider)
    if not key:
        raise ValueError("crawler provider key is required")
    _PROVIDERS[key] = instance


def get_provider(provider: str) -> CrawlerProvider | None:
    return _PROVIDERS.get(_normalize(provider))


def list_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())


__all__ = ["register_provider", "get_provider", "list_providers"]
