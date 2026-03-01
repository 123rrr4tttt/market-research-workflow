from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api import discovery as discovery_api
from app.contracts.errors import ErrorCode

pytestmark = pytest.mark.contract


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Keep tests deterministic and isolated from DB job logger side effects.
    monkeypatch.setattr(discovery_api, "start_job", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(discovery_api, "complete_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(discovery_api, "fail_job", lambda *_args, **_kwargs: None)

    app = FastAPI()
    app.include_router(discovery_api.router, prefix="/api/v1")
    return TestClient(app)


def test_discovery_search_route_is_reachable(client: TestClient) -> None:
    resp = client.post("/api/v1/discovery/search", json={})
    assert resp.status_code == 422


def test_discovery_search_success_envelope_shape(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        discovery_api.discovery_app,
        "run_search",
        lambda **_kwargs: {
            "results": [{"title": "sample"}],
            "stored": {"inserted": 1},
        },
    )

    resp = client.post(
        "/api/v1/discovery/search",
        json={
            "topic": "ai chips",
            "language": "en",
            "max_results": 5,
            "provider": "auto",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"status", "data", "error", "meta"}
    assert body["status"] == "ok"
    assert body["error"] is None
    assert body["data"]["results"] == [{"title": "sample"}]
    assert body["data"]["stored"] == {"inserted": 1}
    assert isinstance(body["meta"], dict)


@pytest.mark.parametrize(
    ("exc_message", "expected_status", "expected_code"),
    [
        ("resource not found", 404, ErrorCode.NOT_FOUND.value),
        ("rate limit exceeded", 429, ErrorCode.RATE_LIMITED.value),
        ("upstream timeout", 502, ErrorCode.UPSTREAM_ERROR.value),
        ("api key missing", 500, ErrorCode.CONFIG_ERROR.value),
    ],
)
def test_discovery_search_exception_mapping(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    exc_message: str,
    expected_status: int,
    expected_code: str,
) -> None:
    def _raise(**_kwargs):
        raise RuntimeError(exc_message)

    monkeypatch.setattr(discovery_api.discovery_app, "run_search", _raise)

    resp = client.post(
        "/api/v1/discovery/search",
        json={
            "topic": "ai chips",
            "language": "en",
            "max_results": 5,
            "provider": "auto",
        },
    )

    assert resp.status_code == expected_status
    body = resp.json()
    assert body["status"] == "error"
    assert body["data"] is None
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"] == exc_message
    assert set(body["meta"].keys()) == {"trace_id", "pagination", "project_key", "deprecated"}
