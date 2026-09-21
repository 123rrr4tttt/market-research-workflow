from __future__ import annotations

from typing import Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import (
    crawler_registry_contract_failures,
    crawler_runtime_failures,
)

from .base import CrawlerProvider


_PROVIDERS: dict[str, CrawlerProvider] = {}
_CRAWLER_FAILURE_WITNESS = "test:test_w03_crawler_failure_lifts"
_CRAWLER_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _failure(
    code: str,
    message: str,
    *,
    operation: str = "crawler.runtime",
    site: str = "app.services.crawlers",
    public_exception: str = "ValueError",
    **details: Any,
) -> Failure:
    """Create a closed crawler failure before the compatibility lift."""
    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": crawler_runtime_failures.name,
        "operation": operation,
        "owner": site,
        "public_exception": public_exception,
        "public_message": message,
        "site": site,
        "witness": _CRAWLER_FAILURE_WITNESS,
    }
    context.update(details)
    return crawler_runtime_failures.fail(code, message, context)


def _registry_precondition_failure(
    message: str,
    *,
    operation: str,
    site: str,
) -> Failure:
    """Return the registry's closed precondition outcome before ABI lifting."""
    return crawler_registry_contract_failures.fail(
        "provider_key_required",
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": crawler_registry_contract_failures.name,
            "operation": operation,
            "owner": site,
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _CRAWLER_FAILURE_WITNESS,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Retain the existing public exception ABI at one explicit boundary."""
    context = failure.context or {}
    known_family = (
        crawler_runtime_failures.matches(failure)
        or crawler_registry_contract_failures.matches(failure)
    )
    if (
        not known_family
        or _CRAWLER_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("failure_family") != failure.family
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != exception_type.__name__
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=crawlers.registry.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w03_crawler_failure_lifts
        raise TypeError("crawler failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if cause is None:
        # kit:boundary owner=crawlers.registry.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=crawler.registry.contract_failure witness=test:test_w03_crawler_failure_lifts
        raise exception_type(message)
    # kit:boundary owner=crawlers.registry.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=crawler.registry.contract_failure witness=test:test_w03_crawler_failure_lifts
    raise exception_type(message) from cause


def _normalize(provider: str) -> str:
    return str(provider or "").strip().lower()


def register_provider(provider: str, instance: CrawlerProvider) -> None:
    key = _normalize(provider)
    if not key:
        failure = _registry_precondition_failure(
            "crawler provider key is required",
            operation="register_provider",
            site="app.services.crawlers.registry.register_provider",
        )
        _raise_contract_failure(failure)
    _PROVIDERS[key] = instance


def get_provider(provider: str) -> CrawlerProvider | None:
    return _PROVIDERS.get(_normalize(provider))


def list_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())


__all__ = ["register_provider", "get_provider", "list_providers"]
