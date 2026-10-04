from __future__ import annotations

from typing import Any

from app.services.source_library.provider_ports import (
    CrawlerProvider,
    CrawlerProviderResolver,
    CrawlerProviderResolutionError,
    normalize_crawler_provider_type,
    set_crawler_provider_resolver,
)


class DefaultCrawlerProviderResolver:
    def resolve(
        self,
        provider_type: str,
        *,
        channel: dict[str, Any],
        params: dict[str, Any],
    ) -> CrawlerProvider:
        from ..services import crawlers as _crawlers  # noqa: F401 - preserve builtin provider registration
        from ..services.crawlers.registry import get_provider, register_provider

        normalized = normalize_crawler_provider_type(provider_type)
        provider = get_provider(normalized)
        if provider is not None:
            return provider

        if normalized == "scrapy":
            try:
                from ..services.crawlers.providers.scrapy import ScrapyCrawlerProvider

                provider_config = channel.get("provider_config")
                if not isinstance(provider_config, dict):
                    provider_config = {}
                base_url = (
                    str(params.get("scrapyd_base_url") or "").strip()
                    or str(provider_config.get("scrapyd_base_url") or "").strip()
                    or str(provider_config.get("base_url") or "").strip()
                    or None
                )
                timeout_raw = params.get("scrapyd_timeout") or provider_config.get("timeout")
                timeout = float(timeout_raw) if timeout_raw is not None else None
                provider = ScrapyCrawlerProvider(base_url=base_url, timeout=timeout)
                register_provider(normalized, provider)
                return provider  # noqa: TRY300
            except Exception as exc:  # noqa: BLE001
                raise CrawlerProviderResolutionError(
                    "provider_unavailable",
                    normalized,
                    f"crawler provider '{normalized}' is unavailable: {exc}",
                ) from exc

        raise CrawlerProviderResolutionError(
            "provider_unsupported",
            normalized,
            f"unsupported crawler provider_type: {normalized}",
        )


def configure_source_library_adapters() -> None:
    set_crawler_provider_resolver(DefaultCrawlerProviderResolver())


__all__ = [
    "CrawlerProviderResolver",
    "DefaultCrawlerProviderResolver",
    "configure_source_library_adapters",
]
