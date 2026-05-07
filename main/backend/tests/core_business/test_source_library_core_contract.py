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
    if path == "/api/v1/source_library/items":
        # item list now enriches taxonomy fields (item_type/managed_by/extra) at API boundary.
        actual_items = body["data"][data_field]
        assert len(actual_items) == len(result)
        for expected, actual in zip(result, actual_items):
            for key, value in expected.items():
                assert actual.get(key) == value
            assert actual.get("item_type") in {"user_defined", "service_aggregated"}
            assert actual.get("managed_by") in {"user", "system"}
    else:
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

    assert resp.status_code == 500
    assert resp.headers.get("x-error-code") == ErrorCode.INTERNAL_ERROR.value

    body = resp.json()
    assert body["status"] == "error"
    assert body["data"] is None
    assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
    assert "simulated service failure" in body["error"]["message"]
    assert body["detail"]["error"]["code"] == ErrorCode.INTERNAL_ERROR.value


def test_source_library_shared_scope_allows_missing_project_key(client, monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def _fake_service(scope: str, project_key: str | None):
        captured["scope"] = scope
        captured["project_key"] = project_key
        return [{"channel_key": "news", "name": "News"}]

    monkeypatch.setattr(source_library_api, "list_effective_channels", _fake_service)

    resp = client.get("/api/v1/source_library/channels", params={"scope": "shared"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["project_key"] is None
    assert captured == {"scope": "shared", "project_key": None}


def test_source_library_items_default_filters_user_defined_and_include_system_opt_in(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    def _fake_service(scope: str, project_key: str | None):
        assert scope == "effective"
        assert project_key == "demo_proj"
        return [
            {"item_key": "legacy.user", "name": "Legacy User", "extra": {}},
            {"item_key": "explicit.user", "name": "Explicit User", "extra": {"item_type": "user_defined"}},
            {"item_key": "db.system", "name": "DB System", "item_type": "service_aggregated", "managed_by": "system", "extra": {}},
            {"item_key": "sys.cluster", "name": "System Cluster", "extra": {"item_type": "service_aggregated"}},
            {"item_key": "legacy.cluster", "name": "Legacy Cluster", "extra": {"stable_handler_cluster": True}},
        ]

    monkeypatch.setattr(source_library_api, "list_effective_items", _fake_service)

    default_resp = client.get("/api/v1/source_library/items", params={"scope": "effective", "project_key": "demo_proj"}, headers=HEADERS)
    assert default_resp.status_code == 200
    default_items = default_resp.json()["data"]["items"]
    assert {x["item_key"] for x in default_items} == {"legacy.user", "explicit.user"}
    assert {x["item_type"] for x in default_items} == {"user_defined"}

    include_system_resp = client.get(
        "/api/v1/source_library/items",
        params={"scope": "effective", "project_key": "demo_proj", "include_system": "true"},
        headers=HEADERS,
    )
    assert include_system_resp.status_code == 200
    include_system_items = include_system_resp.json()["data"]["items"]
    assert {x["item_key"] for x in include_system_items} == {"legacy.user", "explicit.user", "db.system", "sys.cluster", "legacy.cluster"}
    assert {x["item_type"] for x in include_system_items} == {"user_defined", "service_aggregated"}


def test_source_library_items_service_aggregated_requires_include_system(client):
    resp = client.get(
        "/api/v1/source_library/items",
        params={"scope": "effective", "project_key": "demo_proj", "item_type": "service_aggregated"},
        headers=HEADERS,
    )

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    body = resp.json()
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "include_system=true" in body["error"]["message"]


@pytest.mark.parametrize("method,path", [("post", "/api/v1/source_library/items"), ("put", "/api/v1/source_library/items/system.item")])
def test_source_library_item_write_rejects_service_aggregated_from_user_api(client, method: str, path: str):
    payload = {
        "item_key": "system.item",
        "name": "System Item",
        "channel_key": "handler.cluster",
        "params": {"site_entries": ["https://example.com/feed"]},
        "extra": {"item_type": "service_aggregated"},
        "item_type": "service_aggregated",
    }
    requester = getattr(client, method)
    resp = requester(path, params={"project_key": "demo_proj"}, json=payload, headers=HEADERS)

    assert 400 <= resp.status_code < 500
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    body = resp.json()
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "system-managed" in body["error"]["message"]


def test_source_library_item_write_rejects_generic_web_user_defined(client):
    payload = {
        "item_key": "user.generic.search",
        "name": "User Generic Search",
        "channel_key": "generic_web.search_template",
        "params": {"template": "https://example.com/search?q={{q}}"},
        "extra": {},
        "item_type": "user_defined",
    }
    resp = client.post("/api/v1/source_library/items", params={"project_key": "demo_proj"}, json=payload, headers=HEADERS)

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    body = resp.json()
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "internal adapter-only" in body["error"]["message"]


def test_source_library_item_write_requires_external_manifest_for_external_channel(client):
    payload = {
        "item_key": "external.demo.item",
        "name": "External Demo Item",
        "channel_key": "external_project.manifest",
        "params": {"max_items": 20},
        "extra": {},
        "item_type": "user_defined",
    }

    resp = client.post("/api/v1/source_library/items", params={"project_key": "demo_proj"}, json=payload, headers=HEADERS)

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    body = resp.json()
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "external_project.manifest" in body["error"]["message"]


def test_source_library_item_write_rejects_external_manifest_channel_mismatch(client):
    payload = {
        "item_key": "external.demo.item",
        "name": "External Demo Item",
        "channel_key": "market.general",
        "params": {"max_items": 20},
        "extra": {
            "external_project_manifest": {
                "contract_version": "external_item.manifest.v1",
                "item_key": "external.demo.item",
                "display_name": "External Demo Item",
                "project_link": "https://github.com/example/external-demo",
                "source_kind": "feed_aggregator",
                "source_scope": "finance_news",
                "capabilities": {
                    "candidate_urls": True,
                    "article_metadata": True,
                    "article_body": False,
                    "pdf_artifact": False,
                },
                "accepted_inputs": {
                    "query_terms": True,
                    "urls": False,
                    "domains": False,
                    "date_range": False,
                    "max_items": True,
                },
                "execution_mode": "rss_feed",
                "runner_ref": "https://example.com/feed.xml",
                "normalization": {
                    "record_kind": "article_metadata",
                    "frontdoor_strategy": "records_only_defer",
                },
                "limits": {
                    "default_max_items": 20,
                    "max_items_cap": 100,
                    "request_timeout_ms": 30000,
                },
                "refresh_policy": {
                    "manifest_ttl_minutes": 60,
                    "probe_ttl_minutes": 1440,
                },
                "provenance": {
                    "discovered_by": "manual_registration",
                    "source_refs": ["https://github.com/example/external-demo"],
                },
            }
        },
        "item_type": "user_defined",
    }

    resp = client.post("/api/v1/source_library/items", params={"project_key": "demo_proj"}, json=payload, headers=HEADERS)

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    body = resp.json()
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "requires channel_key=external_project.manifest" in body["error"]["message"]


def _external_registration_item_payload() -> dict:
    return {
        "item_key": "external.demo.item",
        "name": "External Demo Item",
        "channel_key": "external_project.manifest",
        "description": "Synthesized external item",
        "params": {},
        "tags": ["ai"],
        "enabled": True,
        "item_type": "user_defined",
        "extra": {
            "external_project_manifest": {
                "contract_version": "external_item.manifest.v1",
                "item_key": "external.demo.item",
                "display_name": "External Demo Item",
                "project_link": "https://github.com/example/external-demo",
                "source_kind": "feed_aggregator",
                "source_scope": "finance_news",
                "capabilities": {
                    "candidate_urls": True,
                    "article_metadata": True,
                    "article_body": False,
                    "pdf_artifact": False,
                },
                "accepted_inputs": {
                    "query_terms": True,
                    "urls": False,
                    "domains": False,
                    "date_range": False,
                    "max_items": True,
                },
                "execution_mode": "rss_feed",
                "runner_ref": "https://example.com/feed.xml",
                "normalization": {
                    "record_kind": "article_metadata",
                    "frontdoor_strategy": "records_only_defer",
                },
                "limits": {
                    "default_max_items": 20,
                    "max_items_cap": 100,
                    "request_timeout_ms": 30000,
                },
                "refresh_policy": {
                    "manifest_ttl_minutes": 60,
                    "probe_ttl_minutes": 1440,
                },
                "provenance": {
                    "discovered_by": "llm_probe",
                    "source_refs": ["https://github.com/example/external-demo"],
                },
            }
        },
        "registration_context": {
            "source": "github",
            "project_link": "https://github.com/example/external-demo",
            "evidence": [{"kind": "readme", "content": "demo"}],
        },
    }


def test_external_project_register_preview_returns_synthesized_item_without_persist(client, monkeypatch: pytest.MonkeyPatch):
    def _fake_synthesize(**kwargs):
        assert kwargs["project_link"] == "https://github.com/example/external-demo"
        return _external_registration_item_payload()

    monkeypatch.setattr(source_library_api, "synthesize_external_project_item", _fake_synthesize)

    resp = client.post(
        "/api/v1/source_library/external-projects/register",
        params={"project_key": "demo_proj"},
        json={
            "project_link": "https://github.com/example/external-demo",
            "persist": False,
            "hints": {"query_terms": ["ai"]},
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["persisted"] is False
    assert body["data"]["item"]["item_key"] == "external.demo.item"
    assert body["data"]["item"]["channel_key"] == "external_project.manifest"
    assert body["data"]["item"]["execution_plan"]["plan_meta"]["execution_family"] == "external_project"
    assert (
        body["data"]["item"]["execution_plan"]["plan_meta"]["external_project"]["provider_binding"]["provider_key"]
        == "external_project.rss_feed"
    )
    assert body["data"]["registration_context"]["source"] == "github"
    assert body["data"]["registration_context"]["provider_binding"]["provider_key"] == "external_project.rss_feed"
    assert body["data"]["manifest_summary"]["provider_binding"]["provider_key"] == "external_project.rss_feed"


def test_external_project_register_persist_upserts_synthesized_item(client, monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def _fake_synthesize(**_kwargs):
        payload = _external_registration_item_payload()
        payload["enabled"] = False
        return payload

    def _fake_upsert(payload, project_key: str):
        captured["project_key"] = project_key
        captured["payload"] = payload.model_dump()
        return {"status": "ok"}

    monkeypatch.setattr(source_library_api, "synthesize_external_project_item", _fake_synthesize)
    monkeypatch.setattr(source_library_api, "upsert_project_item", _fake_upsert)

    resp = client.post(
        "/api/v1/source_library/external-projects/register",
        params={"project_key": "demo_proj"},
        json={
            "project_link": "https://github.com/example/external-demo",
            "persist": True,
            "enabled": False,
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["persisted"] is True
    assert captured["project_key"] == "demo_proj"
    assert captured["payload"]["item_key"] == "external.demo.item"
    assert captured["payload"]["channel_key"] == "external_project.manifest"
    assert captured["payload"]["enabled"] is False
    assert body["data"]["item"]["execution_plan"]["plan_meta"]["external_project"]["execution_mode"] == "rss_feed"
    assert (
        body["data"]["item"]["execution_plan"]["plan_meta"]["external_project"]["provider_binding"]["provider_key"]
        == "external_project.rss_feed"
    )
    assert body["data"]["manifest_summary"]["provider_binding"]["provider_key"] == "external_project.rss_feed"


def test_external_project_register_surfaces_synthesis_failure_as_invalid_input(client, monkeypatch: pytest.MonkeyPatch):
    def _fake_synthesize(**_kwargs):
        raise ValueError("project_link cannot target localhost or local hosts")

    monkeypatch.setattr(source_library_api, "synthesize_external_project_item", _fake_synthesize)

    resp = client.post(
        "/api/v1/source_library/external-projects/register",
        params={"project_key": "demo_proj"},
        json={"project_link": "http://127.0.0.1:8000/demo"},
        headers=HEADERS,
    )

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "localhost" in body["error"]["message"]


def test_external_project_register_surfaces_runtime_failure_as_internal_error(client, monkeypatch: pytest.MonkeyPatch):
    def _fake_synthesize(**_kwargs):
        raise RuntimeError("manifest loader crashed")

    monkeypatch.setattr(source_library_api, "synthesize_external_project_item", _fake_synthesize)

    resp = client.post(
        "/api/v1/source_library/external-projects/register",
        params={"project_key": "demo_proj"},
        json={"project_link": "https://github.com/example/external-demo"},
        headers=HEADERS,
    )

    assert resp.status_code == 500
    assert resp.headers.get("x-error-code") == ErrorCode.INTERNAL_ERROR.value
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
    assert "manifest loader crashed" in body["error"]["message"]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/v1/source_library/items",
            {
                "item_key": "demo.item",
                "name": "Demo Item",
                "channel_key": "market.general",
                "params": {},
                "extra": {},
            },
        ),
        (
            "put",
            "/api/v1/source_library/items/demo.item",
            {
                "item_key": "demo.item",
                "name": "Demo Item",
                "channel_key": "market.general",
                "params": {},
                "extra": {},
            },
        ),
        (
            "post",
            "/api/v1/source_library/items/demo.item/refresh",
            {
                "incremental": True,
                "max_site_entries": 10,
            },
        ),
        (
            "post",
            "/api/v1/source_library/handler_clusters/sync",
            {
                "handlers": ["rss"],
                "incremental": True,
                "max_site_entries": 10,
            },
        ),
        (
            "post",
            "/api/v1/source_library/external-projects/register",
            {
                "project_link": "https://github.com/example/demo",
                "persist": False,
            },
        ),
    ],
)
def test_source_library_write_routes_require_project_key_with_standard_error_envelope(
    client,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict,
):
    monkeypatch.setattr(source_library_api, "get_effective_project_key_enforcement_mode", lambda: "require")

    requester = getattr(client, method)
    resp = requester(path, json=payload)

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value


def test_source_library_sync_shared_from_files_requires_project_key_with_standard_error_envelope(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(source_library_api, "get_effective_project_key_enforcement_mode", lambda: "require")

    resp = client.post("/api/v1/source_library/sync_shared_from_files")

    assert resp.status_code == 400
    assert resp.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value


def test_source_library_refresh_missing_item_returns_not_found_envelope(client):
    resp = client.post(
        "/api/v1/source_library/items/demo.item/refresh",
        json={"project_key": "demo_proj", "incremental": True, "max_site_entries": 10},
        headers=HEADERS,
    )

    assert resp.status_code == 404
    assert resp.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert body["detail"]["error"]["details"]["item_key"] == "demo.item"


def test_source_library_refresh_runtime_failure_returns_internal_error_envelope(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeResult:
        @staticmethod
        def scalar_one_or_none():
            return type("Row", (), {"params": {}, "extra": {}})()

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query):
            return _FakeResult()

        def commit(self):
            return None

    def _boom(**_kwargs):
        raise RuntimeError("refresh backend exploded")

    monkeypatch.setattr(source_library_api, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(source_library_api, "_refresh_handler_item_site_entries", _boom)

    resp = client.post(
        "/api/v1/source_library/items/demo.item/refresh",
        json={"project_key": "demo_proj", "incremental": True, "max_site_entries": 10},
        headers=HEADERS,
    )

    assert resp.status_code == 500
    assert resp.headers.get("x-error-code") == ErrorCode.INTERNAL_ERROR.value
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
    assert "refresh backend exploded" in body["error"]["message"]
