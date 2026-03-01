from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.api import source_library as source_library_api
    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


HEADERS = {"X-Project-Key": "demo_proj", "X-Request-Id": "core-source-library-contract"}


@pytest.fixture(scope="module")
def client():
    if _IMPORT_ERROR is not None:
        pytest.skip(f"source_library core contract tests require backend dependencies: {_IMPORT_ERROR}")
    return TestClient(backend_app)


@pytest.mark.parametrize(
    ("path", "service_attr", "result", "data_field"),
    [
        (
            "/api/v1/source_library/channels",
            "list_effective_channels",
            [{"channel_key": "news", "name": "News"}],
            "items",
        ),
        (
            "/api/v1/source_library/items",
            "list_effective_items",
            [{"item_key": "macro", "name": "Macro Feed"}],
            "items",
        ),
        (
            "/api/v1/source_library/items/by_symbol",
            "list_items_by_symbol",
            {"AAPL": [{"item_key": "apple_feed"}]},
            "by_symbol",
        ),
    ],
)
def test_source_library_query_endpoints_success_envelope(
    client,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    service_attr: str,
    result,
    data_field: str,
):
    called = {}

    def _fake_service(scope: str, project_key: str | None):
        called["scope"] = scope
        called["project_key"] = project_key
        return result

    monkeypatch.setattr(source_library_api, service_attr, _fake_service)

    resp = client.get(path, params={"scope": "effective", "project_key": "demo_proj"}, headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["error"] is None
    assert body["data"][data_field] == result
    assert body["data"]["scope"] == "effective"
    assert body["data"]["project_key"] == "demo_proj"
    assert called == {"scope": "effective", "project_key": "demo_proj"}


@pytest.mark.parametrize(
    ("path", "service_attr"),
    [
        ("/api/v1/source_library/channels", "list_effective_channels"),
        ("/api/v1/source_library/items", "list_effective_items"),
        ("/api/v1/source_library/items/by_symbol", "list_items_by_symbol"),
    ],
)
def test_source_library_query_endpoints_error_envelope(
    client,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    service_attr: str,
):
    def _fake_service(*_args, **_kwargs):
        raise RuntimeError("simulated service failure")

    monkeypatch.setattr(source_library_api, service_attr, _fake_service)

    resp = client.get(path, params={"scope": "effective", "project_key": "demo_proj"}, headers=HEADERS)

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value

    body = resp.json()
    assert body["status"] == "error"
    assert body["data"] is None
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "simulated service failure" in body["error"]["message"]
    assert body["detail"]["error"]["code"] == ErrorCode.INVALID_INPUT.value
