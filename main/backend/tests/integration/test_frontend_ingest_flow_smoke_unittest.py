from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


def _response_payload(body: dict) -> dict:
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


class _TasksStub:
    def __init__(self):
        self.task_run_source_library_item = SimpleNamespace(
            delay=Mock(return_value=SimpleNamespace(id="source-library-task-1"))
        )
        self.task_ingest_url_via_source_library = SimpleNamespace(
            delay=Mock(return_value=SimpleNamespace(id="single-url-task-1"))
        )

    def task_collect_market_data(self, *_args, **_kwargs):  # pragma: no cover - compatibility only
        return SimpleNamespace(id="market-task")

    def task_collect_news_resource(self, *_args, **_kwargs):  # pragma: no cover - compatibility only
        return SimpleNamespace(id="news-task")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as tclient:
        yield tclient


def test_frontend_ingest_flow_contract_smoke(client: TestClient):
    headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "ingest-flow-smoke"}
    tasks_stub = _TasksStub()

    with patch("app.api.ingest._tasks_module", return_value=tasks_stub):
        source_library_async_resp = client.post(
            "/api/v1/ingest/source-library/run",
            json={
                "project_key": "demo_proj",
                "item_key": "reddit.general",
                "async_mode": True,
                "override_params": {"limit": 2},
            },
            headers=headers,
        )

        url_single_async_resp = client.post(
            "/api/v1/ingest/url/single",
            json={
                "project_key": "demo_proj",
                "url": "https://example.com",
                "query_terms": ["market"],
                "async_mode": True,
            },
            headers=headers,
        )

    assert source_library_async_resp.status_code == 200, source_library_async_resp.text
    assert url_single_async_resp.status_code == 200, url_single_async_resp.text

    source_payload = _response_payload(source_library_async_resp.json())
    single_payload = _response_payload(url_single_async_resp.json())

    assert source_payload["status"] == "queued"
    assert source_payload["task_id"] == "source-library-task-1"
    assert source_payload["async"] is True
    assert source_payload["params"]["item_key"] == "reddit.general"

    assert single_payload["status"] == "queued"
    assert single_payload["task_id"] == "single-url-task-1"
    assert single_payload["async"] is True
    assert single_payload["params"]["url"] == "https://example.com"

    tasks_stub.task_run_source_library_item.delay.assert_called_once_with(
        "reddit.general",
        "demo_proj",
        {"limit": 2},
        workflow_run_id=None,
        trace_id=None,
    )
    tasks_stub.task_ingest_url_via_source_library.delay.assert_called_once_with(
        "https://example.com",
        ["market"],
        False,
        "demo_proj",
    )

    with patch(
        "app.services.collect_runtime.run_source_library_item_compat",
        return_value={
            "terminal_output": {
                "contract_version": "source_library.terminal_output.v1",
                "status": "ok",
                "source_mode": "protocol_search",
                "item": {"item_key": "url_pool.default", "item_type": "user_defined", "managed_by": "user"},
                "request": {"project_key": "demo_proj"},
                "results": {"records": [], "stats": {"fetched": 0, "normalized": 0, "dropped": 0, "errors": 0}},
                "errors": [],
                "meta": {"reason_code": "empty"},
            },
            "frontdoor_ingress": {
                "contract_version": "frontdoor.ingress.v1",
                "ingress_type": "source_library",
            },
            "postprocess_frontdoor": {
                "status": "ok",
                "data": {"admission": "reject"},
            },
            "legacy_result": {"item_key": "url_pool.default", "channel_key": "url_pool"},
        },
    ):
        source_library_sync_resp = client.post(
            "/api/v1/ingest/source-library/run",
            json={
                "project_key": "demo_proj",
                "item_key": "url_pool.default",
                "async_mode": False,
                "override_params": {"limit": 1, "max_items": 1},
            },
            headers=headers,
        )

    assert source_library_sync_resp.status_code == 200, source_library_sync_resp.text
    sync_payload = _response_payload(source_library_sync_resp.json())
    assert sync_payload["contract_version"] == "source_library.terminal_output.v1"
    assert sync_payload["source_mode"] == "protocol_search"
    assert sync_payload["results"]["records"] == []
    assert sync_payload["results"]["stats"]["normalized"] == 0
    assert sync_payload["terminal_output"]["contract_version"] == "source_library.terminal_output.v1"
    assert sync_payload["authority_output"]["contract_version"] == "source_library.authority_output.v1"
    assert sync_payload["compat_projection"]["contract_version"] == "source_library.compat_projection.v1"
    assert sync_payload["frontdoor_ingress"]["contract_version"] == "frontdoor.ingress.v1"
    assert sync_payload["postprocess_frontdoor"]["data"]["admission"] == "reject"
    assert sync_payload["legacy_result"]["item_key"] == "url_pool.default"
    assert "inserted" not in sync_payload
    assert "updated" not in sync_payload
    assert "skipped" not in sync_payload
    assert "legacy_ingest_result" not in sync_payload
    assert "channel_key" not in sync_payload["item"]


def test_frontend_ingest_flow_headers_derive_project():
    with TestClient(app) as client_obj:
        resp = client_obj.get("/api/v1/health", headers={"X-Project-Key": "demo_proj"})

    assert resp.status_code == 200
    assert resp.headers.get("X-Project-Key-Source") == "header"
    assert resp.headers.get("X-Project-Key-Resolved") == "demo_proj"
