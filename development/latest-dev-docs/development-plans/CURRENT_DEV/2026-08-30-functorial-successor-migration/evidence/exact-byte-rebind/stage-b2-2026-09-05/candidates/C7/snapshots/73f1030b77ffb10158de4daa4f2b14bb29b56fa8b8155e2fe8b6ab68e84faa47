from __future__ import annotations

import pytest
from unittest.mock import patch

from app.composition.resource_pool import (
    RequestsHttpFetchPort,
    SourceLibraryOfficialAccessPort,
    configure_resource_pool_ports,
)
from app.services.ingest.adapters import http_utils
from app.services.resource_pool import http_port


def test_FAILURE_PRESERVED__unconfigured_http_port_fails_closed() -> None:
    original = http_port._HTTP_FETCH_PORT
    http_port._HTTP_FETCH_PORT = None
    try:
        with pytest.raises(RuntimeError, match="HTTP fetch port is not configured"):
            http_port.fetch_html("https://example.com")
    finally:
        http_port._HTTP_FETCH_PORT = original


def test_FAILURE_PRESERVED__official_access_port_not_configured_fails_closed() -> None:
    original = http_port._OFFICIAL_ACCESS_PORT
    http_port._OFFICIAL_ACCESS_PORT = None
    try:
        with pytest.raises(RuntimeError, match="official-access port is not configured"):
            http_port.handle_official_access_api(
                {"provider_key": "arxiv"}, project_key=None
            )
    finally:
        http_port._OFFICIAL_ACCESS_PORT = original


def test_INVARIANT__composition_registers_resource_pool_ports() -> None:
    configure_resource_pool_ports()
    assert isinstance(http_port._HTTP_FETCH_PORT, RequestsHttpFetchPort)
    assert isinstance(http_port._OFFICIAL_ACCESS_PORT, SourceLibraryOfficialAccessPort)


def test_INVARIANT__requests_port_projects_provider_response() -> None:
    class _Response:
        text = "<html>ok</html>"
        content = b"<html>ok</html>"
        headers = {"Content-Type": "text/html"}
        status_code = 200
        url = "https://final.example"

    port = RequestsHttpFetchPort()
    with patch.object(
        http_utils,
        "fetch_html",
        return_value=("<html>ok</html>", _Response()),
    ) as mocked:
        text, response = port.fetch_html(
            "https://example.com",
            headers={"X-Test": "1"},
            timeout=3.0,
            retries=2,
            backoff=1.0,
        )

    mocked.assert_called_once_with(
        "https://example.com",
        headers={"X-Test": "1"},
        params=None,
        cookies=None,
        timeout=3.0,
        retries=2,
        backoff=1.0,
    )
    assert text == "<html>ok</html>"
    assert response.status_code == 200
    assert response.headers == {"content-type": "text/html"}
    assert response.content == b"<html>ok</html>"
    assert response.final_url == "https://final.example"


def test_FAILURE_PRESERVED__http_status_maps_to_closed_error_fields() -> None:
    class _Response:
        status_code = 404

        def raise_for_status(self) -> None:
            raise http_utils.requests.HTTPError("404 Not Found")

    class _Session:
        headers: dict[str, str] = {}
        cookies: object = None

        def get(self, *_args: object, **_kwargs: object) -> _Response:
            return _Response()

    with (
        patch.object(http_utils.requests, "Session", return_value=_Session()),
    ):
        with pytest.raises(http_utils.HttpFetchError) as ctx:
            http_utils.fetch_html("https://example.com/missing", retries=1)

    assert ctx.value.reason.value == "http_status"
    assert ctx.value.url == "https://example.com/missing"
    assert ctx.value.status_code == 404
    assert ctx.value.retryable is False


def test_FAILURE_PRESERVED__http_retry_exhaustion_preserves_status_failure() -> None:
    class _Response:
        status_code = 503

    class _Session:
        headers: dict[str, str] = {}
        cookies: object = None

        def get(self, *_args: object, **_kwargs: object) -> _Response:
            return _Response()

    with (
        patch.object(http_utils.requests, "Session", return_value=_Session()),
        patch.object(http_utils.time, "sleep"),
    ):
        with pytest.raises(http_utils.HttpFetchError) as ctx:
            http_utils.fetch_html("https://example.com/unavailable", retries=2)

    assert ctx.value.reason.value == "http_status"
    assert ctx.value.url == "https://example.com/unavailable"
    assert ctx.value.status_code == 503
    assert ctx.value.retryable is True
