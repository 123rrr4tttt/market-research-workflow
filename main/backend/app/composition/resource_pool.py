"""Composition root for resource-pool network ports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.ingest.adapters import http_utils
from app.services.resource_pool.http_port import (
    HttpFetchPort,
    HttpFetchResponse,
    OfficialAccessPort,
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
        params: Mapping[str, Any] | None = None,
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
        params: dict[str, Any],
        project_key: str | None,
    ) -> dict[str, Any]:
        return official_access.handle_official_access_api(params, project_key)


def configure_resource_pool_ports() -> None:
    set_http_fetch_port(RequestsHttpFetchPort())
    set_official_access_port(SourceLibraryOfficialAccessPort())
