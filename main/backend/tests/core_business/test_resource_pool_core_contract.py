from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import resource_pool as resource_pool_api

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


pytestmark = [pytest.mark.integration, pytest.mark.mocked]


@pytest.fixture
def client() -> TestClient:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"resource_pool core contract tests require backend dependencies: {_IMPORT_ERROR}")

    app = FastAPI()
    app.include_router(resource_pool_api.router, prefix="/api/v1")
    return TestClient(app)


def test_list_urls_returns_envelope_with_pagination_and_passes_filters(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_list_urls(**kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        captured.update(kwargs)
        return (
            [
                {
                    "id": 1,
                    "url": "https://example.com/news/1",
                    "domain": "example.com",
                    "source": "document",
                    "scope": "project",
                }
            ],
            21,
        )

    monkeypatch.setattr(resource_pool_api, "list_urls", _fake_list_urls)

    resp = client.get(
        "/api/v1/resource_pool/urls",
        params={
            "project_key": "demo_proj",
            "scope": "effective",
            "page": 2,
            "page_size": 10,
            "source": "document",
            "domain": "example.com",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["error"] is None
    assert body["data"]["items"][0]["url"] == "https://example.com/news/1"
    assert body["meta"]["pagination"] == {
        "page": 2,
        "page_size": 10,
        "total": 21,
        "total_pages": 3,
    }
    assert captured == {
        "scope": "effective",
        "project_key": "demo_proj",
        "source": "document",
        "domain": "example.com",
        "page": 2,
        "page_size": 10,
    }


def test_list_site_entries_dash_alias_returns_standard_list_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "list_site_entries", lambda **_: ([], 0))

    resp = client.get("/api/v1/resource_pool/site-entries", params={"project_key": "demo_proj"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"] == {"items": []}
    assert body["meta"]["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }


def test_list_urls_requires_project_key_when_no_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "current_project_key", lambda: "")

    resp = client.get("/api/v1/resource_pool/urls")

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "project_key is required" in body["error"]["message"]


def test_list_urls_rejects_page_below_minimum(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/resource_pool/urls",
        params={"project_key": "demo_proj", "page": 0},
    )

    assert resp.status_code == 422


def test_list_urls_rejects_page_size_over_maximum(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/resource_pool/urls",
        params={"project_key": "demo_proj", "page_size": 101},
    )

    assert resp.status_code == 422


def test_list_site_entries_rejects_invalid_scope(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/resource_pool/site_entries",
        params={"project_key": "demo_proj", "scope": "invalid"},
    )

    assert resp.status_code == 422


def test_upsert_site_entry_maps_value_error_to_invalid_input(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_value_error(**_: Any) -> dict[str, Any]:
        raise ValueError("invalid site url")

    monkeypatch.setattr(resource_pool_api, "upsert_site_entry", _raise_value_error)

    resp = client.post(
        "/api/v1/resource_pool/site_entries",
        json={
            "project_key": "demo_proj",
            "scope": "project",
            "site_url": "https://example.com",
            "entry_type": "domain_root",
        },
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "invalid site url" in body["error"]["message"]


def test_list_site_entries_maps_unexpected_error_to_internal_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_runtime_error(**_: Any) -> tuple[list[dict[str, Any]], int]:
        raise RuntimeError("boom")

    monkeypatch.setattr(resource_pool_api, "list_site_entries", _raise_runtime_error)

    resp = client.get("/api/v1/resource_pool/site_entries", params={"project_key": "demo_proj"})

    assert resp.status_code == 500
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" in body["error"]["message"]


def test_unified_search_returns_envelope_and_passes_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_unified_search_by_item(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            item_key="demo-item",
            query_terms=["robotics", "supply chain"],
            site_entries_used=[{"site_url": "https://example.com/search", "entry_type": "search_template"}],
            candidates=["https://example.com/news/1"],
            written={"urls_new": 1, "urls_skipped": 0},
            ingest_result={"inserted": 1, "updated": 0, "skipped": 0, "inserted_valid": 1},
            errors=[],
            stats={"low_value_drop": 0},
        )

    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", _fake_unified_search_by_item)

    resp = client.post(
        "/api/v1/resource_pool/unified-search",
        json={
            "project_key": "demo_proj",
            "item_key": "demo-item",
            "query_terms": ["robotics", "supply chain"],
            "max_candidates": 120,
            "probe_timeout": 8.5,
            "write_to_pool": True,
            "pool_scope": "project",
            "auto_ingest": True,
            "ingest_limit": 6,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["item_key"] == "demo-item"
    assert data["candidates"] == ["https://example.com/news/1"]
    assert data["written"] == {"urls_new": 1, "urls_skipped": 0}
    assert data["ingest_result"]["inserted_valid"] == 1
    assert data["stats"]["low_value_drop"] == 0
    assert captured == {
        "project_key": "demo_proj",
        "item_key": "demo-item",
        "query_terms": ["robotics", "supply chain"],
        "max_candidates": 120,
        "write_to_pool": True,
        "pool_scope": "project",
        "probe_timeout": 8.5,
        "auto_ingest": True,
        "ingest_limit": 6,
    }


def test_unified_search_maps_value_error_to_invalid_input(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_value_error(**_: Any) -> Any:
        raise ValueError("source item not found: demo-item")

    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", _raise_value_error)

    resp = client.post(
        "/api/v1/resource_pool/unified-search",
        json={"project_key": "demo_proj", "item_key": "demo-item"},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "source item not found" in body["error"]["message"]
