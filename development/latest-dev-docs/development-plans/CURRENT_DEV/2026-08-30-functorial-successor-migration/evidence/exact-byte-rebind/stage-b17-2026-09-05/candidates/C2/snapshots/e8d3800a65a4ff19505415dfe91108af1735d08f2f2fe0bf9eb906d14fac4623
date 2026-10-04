from __future__ import annotations

from typing import Any, Literal, NoReturn, Protocol, get_args

from ..crawlers.base import CrawlerDispatchRequest, CrawlerDispatchResult
from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import (
    source_library_crawler_provider_resolution_failures,
)


CrawlerProviderResolutionCode = Literal[
    "resolver_not_configured",
    "provider_unavailable",
    "provider_unsupported",
]
_CRAWLER_PROVIDER_RESOLUTION_CODES = frozenset(
    get_args(CrawlerProviderResolutionCode)
)


def normalize_crawler_provider_type(provider_type: str) -> str:
    return str(provider_type or "").strip().lower()


def _raise_programmer_defect(message: str) -> NoReturn:
    # kit:boundary owner=source_library.crawler_provider_resolution class=PROGRAMMER_DEFECT failure_family=none witness=test:test_crawler_resolution_programmer_defect
    raise ValueError(message)


def _raise_invalid_resolution_failure_lift() -> NoReturn:
    # kit:boundary owner=source_library.crawler_provider_resolution class=PROGRAMMER_DEFECT failure_family=none witness=test:test_unconfigured_crawler_resolver_fails_closed
    raise TypeError(
        "crawler provider resolution failure lift context is inconsistent"
    )


def _raise_unconfigured_resolution(provider_type: str) -> NoReturn:
    failure = source_library_crawler_provider_resolution_failures.fail(
        "resolver_not_configured",
        "crawler provider resolver is not configured",
        {"provider_type": provider_type},
    )
    if not source_library_crawler_provider_resolution_failures.matches(failure):
        _raise_invalid_resolution_failure_lift()
    # kit:boundary owner=source_library.crawler_provider_resolution class=SHELL_BOUNDARY_EXCEPTION failure_family=source_library.crawler_provider_resolution.failure witness=test:test_unconfigured_crawler_resolver_fails_closed
    raise CrawlerProviderResolutionError(
        "resolver_not_configured",
        provider_type,
        "crawler provider resolver is not configured",
    )


class CrawlerProviderResolutionError(RuntimeError):
    def __init__(
        self,
        code: CrawlerProviderResolutionCode,
        provider_type: str,
        message: str,
    ) -> None:
        if code not in _CRAWLER_PROVIDER_RESOLUTION_CODES:
            _raise_programmer_defect(
                f"unknown crawler provider resolution code: {code}"
            )
        self.code = code
        self.provider_type = normalize_crawler_provider_type(provider_type)
        super().__init__(message)


class CrawlerProvider(Protocol):
    provider_type: str

    def dispatch(self, request: CrawlerDispatchRequest) -> CrawlerDispatchResult:
        ...


class CrawlerProviderResolver(Protocol):
    def resolve(
        self,
        provider_type: str,
        *,
        channel: dict[str, Any],
        params: dict[str, Any],
    ) -> CrawlerProvider:
        ...


_CRAWLER_PROVIDER_RESOLVER: CrawlerProviderResolver | None = None


def set_crawler_provider_resolver(resolver: CrawlerProviderResolver | None) -> None:
    global _CRAWLER_PROVIDER_RESOLVER
    _CRAWLER_PROVIDER_RESOLVER = resolver


def resolve_crawler_provider(
    provider_type: str,
    *,
    channel: dict[str, Any],
    params: dict[str, Any],
) -> CrawlerProvider:
    normalized_provider_type = normalize_crawler_provider_type(provider_type)
    if _CRAWLER_PROVIDER_RESOLVER is None:
        _raise_unconfigured_resolution(normalized_provider_type)
    return _CRAWLER_PROVIDER_RESOLVER.resolve(
        normalized_provider_type,
        channel=channel,
        params=params,
    )


__all__ = [
    "CrawlerProvider",
    "CrawlerProviderResolver",
    "CrawlerProviderResolutionCode",
    "CrawlerProviderResolutionError",
    "normalize_crawler_provider_type",
    "resolve_crawler_provider",
    "set_crawler_provider_resolver",
]
