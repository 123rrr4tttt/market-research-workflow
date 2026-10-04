"""Effect ports for resource-pool search and discovery.

Resource-pool planning/parsing code depends on these declarations. Concrete
network adapters are registered by the application composition root.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from selectolax.parser import HTMLParser


class HttpFetchFailureReason(str, Enum):
    PORT_NOT_CONFIGURED = "port_not_configured"
    TRANSPORT = "transport"
    HTTP_STATUS = "http_status"


class HttpFetchError(RuntimeError):
    """HTTP transport failed after the configured retry policy."""

    reason: HttpFetchFailureReason
    url: str
    status_code: int | None
    retryable: bool

    def __init__(
        self,
        message: str,
        *,
        reason: HttpFetchFailureReason = HttpFetchFailureReason.TRANSPORT,
        url: str = "",
        status_code: int | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.url = url
        self.status_code = status_code
        self.retryable = retryable


class PortNotConfigured(HttpFetchError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            reason=HttpFetchFailureReason.PORT_NOT_CONFIGURED,
            retryable=False,
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
    ) -> tuple[str, HttpFetchResponse]: ...


class OfficialAccessPort(Protocol):
    def handle(self, params: dict[str, Any], project_key: str | None) -> dict[str, Any]: ...


_HTTP_FETCH_PORT: HttpFetchPort | None = None
_OFFICIAL_ACCESS_PORT: OfficialAccessPort | None = None


def set_http_fetch_port(port: HttpFetchPort) -> None:
    global _HTTP_FETCH_PORT
    _HTTP_FETCH_PORT = port


def set_official_access_port(port: OfficialAccessPort) -> None:
    global _OFFICIAL_ACCESS_PORT
    _OFFICIAL_ACCESS_PORT = port


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
    if _HTTP_FETCH_PORT is None:
        # kit:boundary — composition was not initialized in this process.
        raise PortNotConfigured("resource-pool HTTP fetch port is not configured")
    return _HTTP_FETCH_PORT.fetch_html(
        url,
        headers=headers,
        params=params,
        cookies=cookies,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
    )


def handle_official_access_api(
    params: dict[str, Any],
    *,
    project_key: str | None,
) -> dict[str, Any]:
    if _OFFICIAL_ACCESS_PORT is None:
        # kit:boundary — composition was not initialized in this process.
        raise RuntimeError("resource-pool official-access port is not configured")
    return _OFFICIAL_ACCESS_PORT.handle(params, project_key)


def make_html_parser(html: str) -> HTMLParser:
    """Canonical pure HTML parser construction used by resource-pool services."""

    return HTMLParser(html)
