"""Effect ports for resource-pool search and discovery.

Resource-pool planning/parsing code depends on these declarations. Concrete
network adapters are registered by the application composition root.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
import inspect
from typing import Any, NoReturn, Protocol
from urllib.parse import urlsplit

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import resource_pool_http_fetch_failures
from selectolax.parser import HTMLParser


class HttpFetchFailureReason(str, Enum):
    PORT_NOT_CONFIGURED = "port_not_configured"
    TRANSPORT = "transport"
    HTTP_STATUS = "http_status"
    TARGET_POLICY_UNAVAILABLE = "target_policy_unavailable"
    UNSAFE_TARGET = "unsafe_target"
    REQUEST_BUDGET_EXHAUSTED = "request_budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    DISCOVERY_DISABLED = "discovery_disabled"


class HttpFetchError(RuntimeError):
    """HTTP transport failed after the configured retry policy."""

    reason: HttpFetchFailureReason
    url: str
    status_code: int | None
    retryable: bool
    reason_code: str
    failure: Failure | None

    def __init__(
        self,
        message: str,
        *,
        reason: HttpFetchFailureReason = HttpFetchFailureReason.TRANSPORT,
        url: str = "",
        status_code: int | None = None,
        retryable: bool = True,
        reason_code: str = "",
        failure: Failure | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.url = url
        self.status_code = status_code
        self.retryable = retryable
        self.reason_code = reason_code
        self.failure = failure


class PortNotConfigured(HttpFetchError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            reason=HttpFetchFailureReason.PORT_NOT_CONFIGURED,
            retryable=False,
        )


class HttpTargetRequestBudget(Protocol):
    @property
    def remaining_seconds(self) -> float: ...

    def try_acquire_request(self, url: str) -> tuple[bool, str | None]: ...

    def record_denial(self, reason: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SameOriginHttpTargetPolicy:
    """Pure target-policy declaration interpreted by the native HTTP adapter."""

    allowed_origin: str
    max_redirects: int = 3
    budget: HttpTargetRequestBudget | None = None

    @staticmethod
    def canonical_origin(url: str) -> str | Failure:
        raw = str(url or "").strip()
        try:
            parts = urlsplit(raw)
            port = parts.port
        except ValueError:
            return _unsafe_origin_failure("target URL port is invalid", raw)
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"}:
            return _unsafe_origin_failure("target URL must use http or https", raw)
        if parts.username or parts.password:
            return _unsafe_origin_failure("target URL cannot contain userinfo", raw)
        host = str(parts.hostname or "").strip().lower()
        if not host or host == "localhost" or host.endswith((".localhost", ".local")):
            return _unsafe_origin_failure("target URL host is not public", raw)
        effective_port = port or (443 if scheme == "https" else 80)
        default_port = 443 if scheme == "https" else 80
        bracketed_host = f"[{host}]" if ":" in host else host
        netloc = (
            bracketed_host
            if effective_port == default_port
            else f"{bracketed_host}:{effective_port}"
        )
        return f"{scheme}://{netloc}"


def _unsafe_origin_failure(message: str, url: str) -> Failure:
    return resource_pool_http_fetch_failures.fail(
        "unsafe_target",
        message,
        {
            "boundary_class": "PROVIDER_PORT_FAILURE",
            "failure_family": resource_pool_http_fetch_failures.name,
            "operation": "resource_pool.http_port.SameOriginHttpTargetPolicy.canonical_origin",
            "owner": "resource_pool.http_fetch",
            "url": url,
        },
    )


def _target_policy_unavailable_failure(url: str) -> Failure:
    return resource_pool_http_fetch_failures.fail(
        "target_policy_unavailable",
        "configured resource-pool HTTP fetch port cannot carry a target policy",
        {
            "boundary_class": "PROVIDER_PORT_FAILURE",
            "failure_family": resource_pool_http_fetch_failures.name,
            "operation": "resource_pool.http_port.fetch_html",
            "owner": "resource_pool.http_fetch",
            "public_exception": "HttpFetchError",
            "public_message": "configured resource-pool HTTP fetch port cannot carry a target policy",
            "url": url,
            "witness": "test:test_http_port_reports_target_policy_unavailable_without_calling_legacy_port",
        },
    )


def _raise_target_policy_unavailable(url: str) -> NoReturn:
    failure = _target_policy_unavailable_failure(url)
    # kit:boundary owner=resource_pool.http_fetch.target_policy_unavailable_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=resource_pool.http_fetch.failure witness=test:test_http_port_reports_target_policy_unavailable_without_calling_legacy_port
    raise HttpFetchError(
        str(failure.message),
        reason=HttpFetchFailureReason.TARGET_POLICY_UNAVAILABLE,
        url=url,
        retryable=False,
        reason_code=str(failure.code),
        failure=failure,
    )


@dataclass(frozen=True, slots=True)
class HttpFetchResponse:
    """Provider-independent projection of an HTTP response."""

    text: str
    content: bytes
    headers: Mapping[str, str]
    status_code: int
    final_url: str


class HttpFetchPort(Protocol):
    def fetch_html(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.5,
        target_policy: SameOriginHttpTargetPolicy | None = None,
    ) -> tuple[str, HttpFetchResponse]: ...


class OfficialAccessPort(Protocol):
    def handle(self, params: dict[str, Any], project_key: str | None) -> dict[str, Any]: ...


_http_fetch_port: HttpFetchPort | None = None
_official_access_port: OfficialAccessPort | None = None
_http_target_policy: ContextVar[SameOriginHttpTargetPolicy | None] = ContextVar(
    "mrw_http_target_policy",
    default=None,
)


def set_http_fetch_port(port: HttpFetchPort) -> None:
    global _http_fetch_port
    _http_fetch_port = port


def set_official_access_port(port: OfficialAccessPort) -> None:
    global _official_access_port
    _official_access_port = port


def http_fetch_target_policy_supported() -> bool:
    """Whether the configured native port explicitly carries target policies."""

    if _http_fetch_port is None:
        return False
    try:
        parameters = inspect.signature(_http_fetch_port.fetch_html).parameters
    except (TypeError, ValueError):
        return False
    return "target_policy" in parameters


@contextmanager
def scoped_http_target_policy(policy: SameOriginHttpTargetPolicy | None):
    token: Token[SameOriginHttpTargetPolicy | None] = _http_target_policy.set(policy)
    try:
        yield
    finally:
        _http_target_policy.reset(token)


def fetch_html(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    cookies: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    retries: int = 3,
    backoff: float = 1.5,
) -> tuple[str, HttpFetchResponse]:
    if _http_fetch_port is None:
        # kit:boundary — composition was not initialized in this process.
        raise PortNotConfigured("resource-pool HTTP fetch port is not configured")
    target_policy = _http_target_policy.get()
    if target_policy is not None and not http_fetch_target_policy_supported():
        _raise_target_policy_unavailable(url)
    if target_policy is None:
        return _http_fetch_port.fetch_html(
            url,
            headers=headers,
            params=params,
            cookies=cookies,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
        )
    return _http_fetch_port.fetch_html(
        url,
        headers=headers,
        params=params,
        cookies=cookies,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        target_policy=target_policy,
    )


def handle_official_access_api(
    params: dict[str, Any],
    *,
    project_key: str | None,
) -> dict[str, Any]:
    if _official_access_port is None:
        # kit:boundary — composition was not initialized in this process.
        raise RuntimeError("resource-pool official-access port is not configured")
    return _official_access_port.handle(params, project_key)


def make_html_parser(html: str) -> HTMLParser:
    """Canonical pure HTML parser construction used by resource-pool services."""

    return HTMLParser(html)
