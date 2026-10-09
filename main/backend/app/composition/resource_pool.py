"""Composition root for resource-pool network ports."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
import requests

from app.services.ingest.adapters import http_utils
from app.services.ingest.retry_policy import RateGate
from app.services.ingest.retry_policy import RequestScope
from app.services.search import web
from app.services.resource_pool.http_port import (
    HttpFetchResponse,
    set_http_fetch_port,
    set_official_access_port,
)
from app.services.source_library.adapters import official_access


class RequestsHttpFetchPort:
    def fetch_html(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.5,
    ) -> tuple[str, HttpFetchResponse]:
        text, response = http_utils.fetch_html(
            url,
            headers=headers,
            params=params,
            cookies=cookies,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
        )
        return text, HttpFetchResponse(
            text=response.text,
            content=response.content,
            headers={str(key).lower(): str(value) for key, value in response.headers.items()},
            status_code=int(response.status_code),
            final_url=str(response.url),
        )


class SourceLibraryOfficialAccessPort:
    def handle(
        self,
        params: dict[str, object],
        project_key: str | None,
    ) -> dict[str, object]:
        open_params: dict[object, object] = {key: value for key, value in params.items()}
        return official_access.handle_official_access_api(open_params, project_key)


class RequestHtmlSearchRequestPort:
    def __init__(
        self,
        *,
        rate_gate: RateGate,
        client_factory: Callable[[], requests.Session] | None = None,
    ) -> None:
        self._rate_gate = rate_gate
        self._client_factory = client_factory

    def request_json(
        self,
        url: str,
        *,
        scope: RequestScope,
        headers: dict[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        outcome = http_utils.request_html(
            url,
            scope=scope,
            headers=headers,
            params=params,
            timeout=20.0,
            retries=3,
            retry_gate=self._rate_gate,
            client_factory=self._client_factory,
        )
        if outcome.ok and outcome.response is not None:
            response_json: object = outcome.response.json()
            return response_json
        if outcome.response is not None:
            outcome.response.raise_for_status()
        if outcome.last_exception is not None:
            raise outcome.last_exception
        raise RuntimeError(outcome.failures[-1].message)


def configure_resource_pool_ports() -> None:
    set_http_fetch_port(RequestsHttpFetchPort())
    set_official_access_port(SourceLibraryOfficialAccessPort())
    web.set_search_request_port(
        RequestHtmlSearchRequestPort(rate_gate=web.SEARCH_RATE_GATE)
    )
