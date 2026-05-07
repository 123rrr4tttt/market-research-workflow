from __future__ import annotations

import sys
from pathlib import Path
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
    assert body["error"]["code"] == "PROJECT_KEY_REQUIRED"
    assert body["detail"]["error"]["code"] == "PROJECT_KEY_REQUIRED"
    assert "project_key is required" in body["error"]["message"]
    assert resp.headers.get("x-error-code") == "PROJECT_KEY_REQUIRED"


def test_list_urls_shared_scope_allows_missing_project_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_list_urls(**kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(resource_pool_api, "list_urls", _fake_list_urls)

    resp = client.get("/api/v1/resource_pool/urls", params={"scope": "shared"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert captured["scope"] == "shared"
    assert captured["project_key"] is None


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
    assert body["detail"]["error"]["code"] == "INVALID_INPUT"
    assert "invalid site url" in body["error"]["message"]
    assert resp.headers.get("x-error-code") == "INVALID_INPUT"


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
    assert body["detail"]["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" in body["error"]["message"]
    assert resp.headers.get("x-error-code") == "INTERNAL_ERROR"


def test_list_site_entries_shared_scope_allows_missing_project_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_list_site_entries(**kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(resource_pool_api, "list_site_entries", _fake_list_site_entries)

    resp = client.get("/api/v1/resource_pool/site_entries", params={"scope": "shared"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert captured["scope"] == "shared"
    assert captured["project_key"] is None


def test_recommend_site_entry_does_not_require_project_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource_pool_api,
        "classify_site_entry",
        lambda **_: type(
            "Rec",
            (),
            {
                "channel_key": "news",
                "entry_type": "domain_root",
                "template": None,
                "validated": True,
                "source": "rule",
                "capabilities": {},
            },
        )(),
    )

    resp = client.post(
        "/api/v1/resource_pool/site_entries/recommend",
        json={"site_url": "https://example.com"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["channel_key"] == "news"


def test_import_open_source_presets_shared_scope_allows_missing_project_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Result:
        pack_key = "demo-pack"
        title = "Demo Pack"
        scope = "shared"
        project_key = None
        inserted_or_updated = ["https://example.com/feed.xml"]

    def _fake_import(**kwargs: Any):
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr(resource_pool_api, "import_open_source_preset_pack", _fake_import)

    resp = client.post(
        "/api/v1/resource_pool/import/open-source-presets",
        json={"scope": "shared", "pack_key": "demo-pack", "enabled": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["scope"] == "shared"
    assert captured["project_key"] is None


def test_discover_search_contract_shared_scope_allows_missing_project_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _ProbeRow:
        template = "https://example.com/search?q={{q}}"
        query_text = "acme"
        candidate_count = 3
        selected_count = 2
        search_service = "basic"
        score = 0.8

    class _Result:
        site_url = "https://example.com"
        domain = "example.com"
        entry_type = "search_template"
        templates_tried = ["https://example.com/search?q={{q}}"]
        suffixes_tried = []
        best_template = "https://example.com/search?q={{q}}"
        best_suffix = None
        best_score = 0.8
        probe_rows = [_ProbeRow()]
        persisted_entry = None

    def _fake_discover(**kwargs: Any):
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr(resource_pool_api, "discover_search_contract", _fake_discover)

    resp = client.post(
        "/api/v1/resource_pool/discover/search-contract",
        json={
            "scope": "shared",
            "site_url": "https://example.com",
            "query_terms": ["acme"],
            "persist": False,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["entry_type"] == "search_template"
    assert captured["scope"] == "shared"
    assert captured["project_key"] is None


def test_discover_search_contract_error_paths_return_standard_error_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "discover_search_contract", lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad search contract")))
    invalid_resp = client.post(
        "/api/v1/resource_pool/discover/search-contract",
        json={"project_key": "demo_proj", "scope": "project", "site_url": "https://example.com", "query_terms": ["acme"]},
    )

    assert invalid_resp.status_code == 400
    assert invalid_resp.headers.get("x-error-code") == "INVALID_INPUT"
    assert invalid_resp.json()["error"]["code"] == "INVALID_INPUT"
    assert invalid_resp.json()["detail"]["error"]["code"] == "INVALID_INPUT"

    monkeypatch.setattr(resource_pool_api, "discover_search_contract", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("search contract exploded")))
    runtime_resp = client.post(
        "/api/v1/resource_pool/discover/search-contract",
        json={"project_key": "demo_proj", "scope": "project", "site_url": "https://example.com", "query_terms": ["acme"]},
    )

    assert runtime_resp.status_code == 500
    assert runtime_resp.headers.get("x-error-code") == "INTERNAL_ERROR"
    assert runtime_resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert runtime_resp.json()["detail"]["error"]["code"] == "INTERNAL_ERROR"


def test_simplify_site_entries_shared_scope_allows_missing_project_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_simplify(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"deleted": 0, "kept": 5, "dry_run": True}

    monkeypatch.setattr(resource_pool_api, "simplify_site_entries", _fake_simplify)

    resp = client.post(
        "/api/v1/resource_pool/site_entries/simplify",
        json={"scope": "shared", "dry_run": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["dry_run"] is True
    assert captured["scope"] == "shared"
    assert captured["project_key"] is None


def test_extract_from_documents_sync_returns_task_result_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_extract(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"documents_scanned": 2, "urls_extracted": 4, "scope": kwargs["scope"]}

    monkeypatch.setattr(resource_pool_api, "extract_from_documents", _fake_extract)

    resp = client.post(
        "/api/v1/resource_pool/extract/from-documents",
        json={"project_key": "demo_proj", "scope": "project", "filters": {"limit": 2}, "async_mode": False},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["error"] is None
    assert body["data"]["status"] == "finished"
    assert body["data"]["result"]["documents_scanned"] == 2
    assert body["data"]["params"]["project_key"] == "demo_proj"
    assert captured["project_key"] == "demo_proj"


def test_extract_from_documents_async_returns_queued_task_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Task:
        id = "task-docs-1"

    class _TasksModule:
        class task_extract_resource_pool_from_documents:
            @staticmethod
            def delay(**_kwargs: Any):
                return _Task()

    monkeypatch.setattr(resource_pool_api, "_get_tasks_module", lambda: _TasksModule)

    resp = client.post(
        "/api/v1/resource_pool/extract/from-documents",
        json={"project_key": "demo_proj", "scope": "project", "filters": {}, "async_mode": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["async"] is True
    assert body["data"]["status"] == "queued"
    assert body["data"]["task_id"] == "task-docs-1"


def test_capture_enable_returns_standard_ok_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource_pool_api,
        "upsert_capture_config",
        lambda **kwargs: {
            "project_key": kwargs["project_key"],
            "job_types": kwargs["job_types"],
            "scope": kwargs["scope"],
            "enabled": kwargs["enabled"],
        },
    )

    resp = client.post(
        "/api/v1/resource_pool/capture/enable",
        json={"project_key": "demo_proj", "scope": "project", "job_types": ["ingest"], "enabled": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["project_key"] == "demo_proj"
    assert body["data"]["job_types"] == ["ingest"]


def test_capture_from_tasks_async_returns_queued_task_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Task:
        id = "task-capture-1"

    class _TasksModule:
        class task_extract_resource_pool_from_tasks:
            @staticmethod
            def delay(**_kwargs: Any):
                return _Task()

    monkeypatch.setattr(resource_pool_api, "_get_tasks_module", lambda: _TasksModule)

    resp = client.post(
        "/api/v1/resource_pool/capture/from-tasks",
        json={"project_key": "demo_proj", "scope": "project", "limit": 20, "async_mode": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["async"] is True
    assert body["data"]["status"] == "queued"
    assert body["data"]["task_id"] == "task-capture-1"


def test_capture_from_tasks_internal_error_maps_to_standard_error_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "extract_from_tasks", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    resp = client.post(
        "/api/v1/resource_pool/capture/from-tasks",
        json={"project_key": "demo_proj", "scope": "project", "limit": 20, "async_mode": False},
    )

    assert resp.status_code == 500
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["detail"]["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" in body["error"]["message"]
    assert resp.headers.get("x-error-code") == "INTERNAL_ERROR"


def test_discover_site_entries_sync_write_returns_write_result_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "get_ingest_config", lambda *_args, **_kwargs: {"payload": {}})

    class _DiscoveryResult:
        domains_scanned = 2
        candidates = [{"site_url": "https://example.com/rss.xml", "entry_type": "rss"}]
        probe_stats = {"rss": 1}
        errors: list[dict[str, Any]] = []

    class _WriteResult:
        upserted = 1
        skipped = 0
        errors: list[dict[str, Any]] = []

    monkeypatch.setattr(resource_pool_api, "discover_site_entries_from_urls", lambda **_kwargs: _DiscoveryResult())
    monkeypatch.setattr(resource_pool_api, "write_discovered_site_entries", lambda **_kwargs: _WriteResult())

    resp = client.post(
        "/api/v1/resource_pool/discover/site-entries",
        json={
            "project_key": "demo_proj",
            "url_scope": "effective",
            "target_scope": "project",
            "dry_run": False,
            "write": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["candidates_count"] == 1
    assert body["data"]["write_result"]["upserted"] == 1


def test_discover_site_entries_async_returns_queued_task_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "get_ingest_config", lambda *_args, **_kwargs: {"payload": {}})

    class _Task:
        id = "task-discovery-1"

    class _TasksModule:
        class task_discover_site_entries_batched:
            @staticmethod
            def delay(**_kwargs: Any):
                return _Task()

    monkeypatch.setattr(resource_pool_api, "_get_tasks_module", lambda: _TasksModule)

    resp = client.post(
        "/api/v1/resource_pool/discover/site-entries",
        json={
            "project_key": "demo_proj",
            "url_scope": "effective",
            "target_scope": "project",
            "dry_run": True,
            "write": False,
            "async_mode": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["async"] is True
    assert body["data"]["status"] == "queued"
    assert body["data"]["task_id"] == "task-discovery-1"


def test_discover_site_entries_error_paths_return_standard_error_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "get_ingest_config", lambda *_args, **_kwargs: {"payload": {}})
    monkeypatch.setattr(resource_pool_api, "discover_site_entries_from_urls", lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid discovery request")))

    invalid_resp = client.post(
        "/api/v1/resource_pool/discover/site-entries",
        json={"project_key": "demo_proj", "url_scope": "effective", "target_scope": "project"},
    )
    assert invalid_resp.status_code == 400
    assert invalid_resp.headers.get("x-error-code") == "INVALID_INPUT"
    assert invalid_resp.json()["error"]["code"] == "INVALID_INPUT"
    assert invalid_resp.json()["detail"]["error"]["code"] == "INVALID_INPUT"

    monkeypatch.setattr(resource_pool_api, "discover_site_entries_from_urls", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("discovery crashed")))
    runtime_resp = client.post(
        "/api/v1/resource_pool/discover/site-entries",
        json={"project_key": "demo_proj", "url_scope": "effective", "target_scope": "project"},
    )
    assert runtime_resp.status_code == 500
    assert runtime_resp.headers.get("x-error-code") == "INTERNAL_ERROR"
    assert runtime_resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert runtime_resp.json()["detail"]["error"]["code"] == "INTERNAL_ERROR"


def test_unified_search_success_returns_standard_ok_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Result:
        item_key = "demo-item"
        query_terms = ["acme"]
        site_entries_used = [{"site_url": "https://example.com/search?q={{q}}"}]
        candidates = ["https://example.com/article-1"]
        written = {"new": 1, "duplicate": 0}
        ingest_result = None
        errors: list[dict[str, Any]] = []

    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", lambda **_kwargs: _Result())

    resp = client.post(
        "/api/v1/resource_pool/unified-search",
        json={"project_key": "demo_proj", "item_key": "demo-item", "query_terms": ["acme"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["item_key"] == "demo-item"
    assert body["data"]["candidates"] == ["https://example.com/article-1"]


def test_source_library_collect_runs_keyword_to_structured_project_flow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Result:
        item_key = "demo-item"
        query_terms = ["acme", "market"]
        site_entries_used = [{"site_url": "https://example.com/search?q={{q}}"}]
        candidates = ["https://example.com/article-1", "https://example.com/article-2"]
        written = {"urls_new": 2, "urls_skipped": 0}
        ingest_result = {
            "inserted": 2,
            "inserted_valid": 2,
            "skipped": 0,
            "queued": 0,
            "rejected_count": 0,
            "single_write_workflow": "front_door_url_routing",
        }
        errors: list[dict[str, Any]] = []

    def _fake_unified_search_by_item(**kwargs: Any) -> _Result:
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", _fake_unified_search_by_item)

    resp = client.post(
        "/api/v1/resource_pool/source-library/collect",
        json={
            "project_key": "demo_proj",
            "item_key": "demo-item",
            "query_terms": ["acme", "market"],
            "max_candidates": 500,
            "ingest_limit": 100,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["contract_version"] == "source_library.keyword_collect.v1"
    assert data["summary"]["candidates_found"] == 2
    assert data["summary"]["documents_inserted_valid"] == 2
    assert data["summary"]["ready_for_project_flows"] is True
    assert data["pipeline"]["structured_extraction"] == "frontdoor.unified.structured.v1"
    assert "writing_materials" in data["pipeline"]["project_downstream"]

    assert captured["project_key"] == "demo_proj"
    assert captured["item_key"] == "demo-item"
    assert captured["query_terms"] == ["acme", "market"]
    assert captured["max_candidates"] == 500
    assert captured["write_to_pool"] is True
    assert captured["auto_ingest"] is True
    assert captured["enable_extraction"] is True
    assert captured["ingest_limit"] == 100


def test_source_library_collect_reports_not_ready_when_no_material_is_ingested(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Result:
        item_key = "demo-item"
        query_terms = ["unknown"]
        site_entries_used: list[dict[str, Any]] = []
        candidates: list[str] = []
        written = {"urls_new": 0, "urls_skipped": 0}
        ingest_result = {"inserted": 0, "inserted_valid": 0, "skipped": 0, "queued": 0, "rejected_count": 0}
        errors = [{"phase": "search", "error": "no candidates"}]

    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", lambda **_kwargs: _Result())

    resp = client.post(
        "/api/v1/resource_pool/source-library/collect",
        json={"project_key": "demo_proj", "item_key": "demo-item", "query_terms": ["unknown"]},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["summary"]["candidates_found"] == 0
    assert data["summary"]["documents_inserted_valid"] == 0
    assert data["summary"]["ready_for_project_flows"] is False
    assert data["errors"] == [{"phase": "search", "error": "no candidates"}]


def test_unified_search_value_error_maps_to_invalid_input(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad item")))

    resp = client.post(
        "/api/v1/resource_pool/unified-search",
        json={"project_key": "demo_proj", "item_key": "demo-item", "query_terms": ["acme"]},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "bad item" in body["error"]["message"]
    assert body["detail"]["error"]["code"] == "INVALID_INPUT"
    assert resp.headers.get("x-error-code") == "INVALID_INPUT"


def test_unified_search_runtime_error_maps_to_internal_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("search backend crashed")))

    resp = client.post(
        "/api/v1/resource_pool/unified-search",
        json={"project_key": "demo_proj", "item_key": "demo-item", "query_terms": ["acme"]},
    )

    assert resp.status_code == 500
    assert resp.headers.get("x-error-code") == "INTERNAL_ERROR"
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["detail"]["error"]["code"] == "INTERNAL_ERROR"


def test_unified_search_config_error_maps_to_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "unified_search_by_item", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("missing API key")))

    resp = client.post(
        "/api/v1/resource_pool/unified-search",
        json={"project_key": "demo_proj", "item_key": "demo-item", "query_terms": ["acme"]},
    )

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == "CONFIG_ERROR"
    body = resp.json()
    assert body["error"]["code"] == "CONFIG_ERROR"
    assert body["detail"]["error"]["code"] == "CONFIG_ERROR"


def test_recommend_site_entries_batch_returns_standard_ok_envelope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource_pool_api,
        "classify_site_entries_batch",
        lambda rows, **_kwargs: [
            {
                "index": rows[0]["index"],
                "site_url": rows[0]["site_url"],
                "entry_type": "rss",
                "channel_key": "news",
                "template": None,
                "validated": True,
                "source": "rule",
                "capabilities": {},
                "symbol_suggestion": None,
            }
        ],
    )

    resp = client.post(
        "/api/v1/resource_pool/site_entries/recommend-batch",
        json={"entries": [{"site_url": "https://example.com/feed.xml"}], "use_llm": False},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["count"] == 1
    assert body["data"]["items"][0]["channel_key"] == "news"


def test_recommend_site_entries_batch_error_paths_return_standard_error_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_pool_api, "classify_site_entries_batch", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid recommendation batch")))
    invalid_resp = client.post(
        "/api/v1/resource_pool/site_entries/recommend-batch",
        json={"entries": [{"site_url": "https://example.com/feed.xml"}], "use_llm": False},
    )

    assert invalid_resp.status_code == 400
    assert invalid_resp.headers.get("x-error-code") == "INVALID_INPUT"
    assert invalid_resp.json()["error"]["code"] == "INVALID_INPUT"

    monkeypatch.setattr(resource_pool_api, "classify_site_entries_batch", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("batch classifier crashed")))
    runtime_resp = client.post(
        "/api/v1/resource_pool/site_entries/recommend-batch",
        json={"entries": [{"site_url": "https://example.com/feed.xml"}], "use_llm": False},
    )

    assert runtime_resp.status_code == 500
    assert runtime_resp.headers.get("x-error-code") == "INTERNAL_ERROR"
    assert runtime_resp.json()["error"]["code"] == "INTERNAL_ERROR"
