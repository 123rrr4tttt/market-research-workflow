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
    assert body["meta"]["deprecated"] == "resource_pool.site_entries_dash_alias.v1"
    assert resp.headers.get("deprecation") == "true"
    assert resp.headers.get("x-deprecated-endpoint") == "/api/v1/resource_pool/site-entries"
    assert resp.headers.get("x-replacement-endpoint") == "/api/v1/resource_pool/site_entries"
    assert body["meta"]["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }


def test_list_site_entries_main_route_adds_lifecycle_fields_without_deprecation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource_pool_api,
        "list_site_entries",
        lambda **_: (
            [
                {
                    "id": 1,
                    "site_url": "https://example.com/feed.xml",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "source": "manual",
                    "scope": "project",
                    "enabled": False,
                    "extra": {},
                },
                {
                    "id": 2,
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "source": "manual",
                    "scope": "shared",
                    "enabled": True,
                    "extra": {"lifecycle_state": "candidate"},
                },
                {
                    "id": 3,
                    "site_url": "",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "source": "manual",
                    "scope": "project",
                    "enabled": True,
                    "extra": {"lifecycle_state": "accepted"},
                },
            ],
            3,
        ),
    )

    resp = client.get("/api/v1/resource_pool/site_entries", params={"project_key": "demo_proj"})

    assert resp.status_code == 200
    body = resp.json()
    items = body["data"]["items"]
    assert [item["lifecycle_state"] for item in items] == ["disabled", "candidate", "accepted"]
    assert items[0]["lifecycle_summary"]["state_source"] == "enabled"
    assert items[1]["lifecycle_summary"]["state_source"] == "extra.lifecycle_state"
    assert items[0]["execution_fact"]["contract_version"] == "resource.execution_fact.v1"
    assert items[0]["execution_fact"]["reason_code"] == "review_disabled"
    assert items[1]["execution_fact"]["reason_code"] == "review_candidate"
    assert items[2]["execution_fact"]["reason_code"] == "missing_site_entry_url"
    assert items[2]["execution_fact"]["guard_status"] == "blocked"
    assert items[2]["execution_fact"]["single_source_guard"]["reason_code"] == "missing_site_entry_url"
    assert items[2]["next_actions"][0]["enabled"] is False
    assert items[2]["next_actions"][0]["blocked"] is True
    assert items[2]["next_actions"][0]["block_reason"] == "missing_site_entry_url"
    assert body["meta"]["deprecated"] is None
    assert resp.headers.get("deprecation") is None


def test_list_site_entries_readbacks_lifecycle_transition_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transition = {
        "contract_version": "resource_pool.site_entry.lifecycle_transition.v1",
        "from_state": "needs_review",
        "to_state": "accepted",
        "reviewer": "qa",
        "reason": "source verified",
        "updated_at": "2026-05-25T12:00:00+00:00",
        "event_ref": "resource_pool.site_entry.lifecycle_transition:project:10:accepted:2026-05-25T12:00:00+00:00",
        "source_ref": {"site_entry_url": "https://example.com/feed.xml"},
        "report_source_ref": "resource_pool.site_entry:project:10",
        "executable_before": False,
        "executable_after": True,
        "to_state_executable": True,
        "executable": True,
    }
    monkeypatch.setattr(
        resource_pool_api,
        "list_site_entries",
        lambda **_: (
            [
                {
                    "id": 10,
                    "site_url": "https://example.com/feed.xml",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "source": "manual",
                    "source_ref": {},
                    "scope": "project",
                    "enabled": True,
                    "extra": {
                        "lifecycle_state": "accepted",
                        "review_state": "accepted",
                        "lifecycle_transition": transition,
                    },
                }
            ],
            1,
        ),
    )

    resp = client.get("/api/v1/resource_pool/site_entries", params={"project_key": "demo_proj"})

    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["lifecycle_transition"] == transition
    assert item["extra"]["lifecycle_transition"] == transition
    assert item["review_closure"]["lifecycle_transition"] == transition
    assert item["execution_fact"]["lifecycle_transition"] == transition
    assert item["lifecycle_summary"]["lifecycle_transition_ref"] == transition["event_ref"]
    assert item["lifecycle_summary"]["lifecycle_transition_contract_version"] == transition["contract_version"]


def test_list_site_entries_adds_execution_plan_preview_from_item_plan(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource_pool_api,
        "list_site_entries",
        lambda **_: (
            [
                {
                    "id": 7,
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "source": "manual",
                    "scope": "project",
                    "enabled": True,
                    "extra": {},
                }
            ],
            1,
        ),
    )

    resp = client.get("/api/v1/resource_pool/site_entries", params={"project_key": "demo_proj"})

    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    preview = item["execution_plan_preview"]
    assert preview["contract_version"] == "source_library.item_execution_plan.v1"
    assert preview["site_entry_urls"] == ["https://example.com/search?q={{q}}"]
    assert preview["expected_entry_type"] == "search_template"
    assert preview["route_bucket_counts"]["total"] == 1
    assert preview["plan_meta"]["preview_source"] == "resource_pool.site_entry"


def test_upsert_site_entry_with_lifecycle_extra_persists_transition_evidence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_upsert_site_entry(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": 12,
            "site_url": kwargs["site_url"],
            "domain": kwargs["domain"],
            "entry_type": kwargs["entry_type"],
            "template": kwargs["template"],
            "name": kwargs["name"],
            "capabilities": kwargs["capabilities"],
            "source": kwargs["source"],
            "source_ref": kwargs["source_ref"],
            "tags": kwargs["tags"],
            "enabled": kwargs["enabled"],
            "scope": kwargs["scope"],
            "extra": kwargs["extra"],
        }

    monkeypatch.setattr(resource_pool_api, "upsert_site_entry", _fake_upsert_site_entry)

    resp = client.post(
        "/api/v1/resource_pool/site_entries",
        json={
            "project_key": "demo_proj",
            "scope": "project",
            "site_url": "https://example.com/feed.xml",
            "entry_type": "rss",
            "source_ref": {},
            "extra": {"lifecycle_state": "accepted", "review_state": "accepted"},
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    transition = captured["extra"]["lifecycle_transition"]
    assert transition["contract_version"] == "resource_pool.site_entry.lifecycle_transition.v1"
    assert transition["from_state"] is None
    assert transition["to_state"] == "accepted"
    assert transition["report_source_ref"] == "resource_pool.site_entry:project:https://example.com/feed.xml"
    assert transition["executable_before"] is False
    assert transition["executable_after"] is True
    assert transition["to_state_executable"] is True
    assert captured["extra"]["review_closure"]["status"] == "ready_to_collect"
    assert captured["extra"]["evidence_binding"]["report_source_ref"] == transition["report_source_ref"]
    assert captured["extra"]["execution_fact"]["lifecycle_transition"] == transition
    assert data["lifecycle_transition"]["event_ref"] == transition["event_ref"]
    assert data["extra"]["lifecycle_transition"]["event_ref"] == transition["event_ref"]


def test_patch_site_entry_lifecycle_writes_review_state_and_returns_lifecycle_summary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_get_site_entry_by_url(**kwargs: Any) -> dict[str, Any]:
        captured["lookup"] = kwargs
        return {
            "id": 10,
            "site_url": "https://example.com/feed.xml",
            "domain": "example.com",
            "entry_type": "rss",
            "template": None,
            "name": "Example Feed",
            "capabilities": {"rss": True},
            "source": "manual",
            "source_ref": {},
            "tags": ["news"],
            "enabled": True,
            "scope": "project",
            "extra": {"legacy_key": "kept"},
        }

    def _fake_upsert_site_entry(**kwargs: Any) -> dict[str, Any]:
        captured["upsert"] = kwargs
        return {
            "id": 10,
            "site_url": kwargs["site_url"],
            "domain": kwargs["domain"],
            "entry_type": kwargs["entry_type"],
            "template": kwargs["template"],
            "name": kwargs["name"],
            "capabilities": kwargs["capabilities"],
            "source": kwargs["source"],
            "source_ref": kwargs["source_ref"],
            "tags": kwargs["tags"],
            "enabled": kwargs["enabled"],
            "scope": kwargs["scope"],
            "extra": kwargs["extra"],
        }

    monkeypatch.setattr(resource_pool_api, "get_site_entry_by_url", _fake_get_site_entry_by_url)
    monkeypatch.setattr(resource_pool_api, "upsert_site_entry", _fake_upsert_site_entry)

    resp = client.patch(
        "/api/v1/resource_pool/site_entries/lifecycle",
        json={
            "project_key": "demo_proj",
            "scope": "project",
            "site_url": "https://example.com/feed.xml",
            "lifecycle_state": "accepted",
            "reviewer": "qa",
            "review_note": "approved for ingestion",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["lifecycle_state"] == "accepted"
    assert body["data"]["lifecycle_summary"]["state"] == "accepted"
    assert body["data"]["lifecycle_summary"]["state_source"] == "extra.lifecycle_state"
    lifecycle_transition = body["data"]["lifecycle_transition"]
    assert lifecycle_transition["contract_version"] == "resource_pool.site_entry.lifecycle_transition.v1"
    assert lifecycle_transition["from_state"] == "active"
    assert lifecycle_transition["to_state"] == "accepted"
    assert lifecycle_transition["reviewer"] == "qa"
    assert lifecycle_transition["reason"] == "approved for ingestion"
    assert lifecycle_transition["event_ref"]
    assert lifecycle_transition["report_source_ref"] == "resource_pool.site_entry:project:10"
    assert lifecycle_transition["source_ref"]["site_entry_url"] == "https://example.com/feed.xml"
    assert lifecycle_transition["executable_before"] is False
    assert lifecycle_transition["executable_after"] is True
    assert lifecycle_transition["to_state_executable"] is True
    assert body["data"]["lifecycle_summary"]["lifecycle_transition_ref"] == lifecycle_transition["event_ref"]
    assert body["data"]["review_closure"]["status"] == "ready_to_collect"
    assert body["data"]["review_closure"]["reason_code"] == "ready_to_collect"
    assert body["data"]["review_closure"]["executable"] is True
    assert body["data"]["review_closure"]["lifecycle_transition"] == lifecycle_transition
    assert body["data"]["review_closure"]["site_entry_url"] == "https://example.com/feed.xml"
    assert body["data"]["review_closure"]["report_source_ref"] == "resource_pool.site_entry:project:10"
    collect_action = body["data"]["next_actions"][0]
    assert collect_action["action"] == "collect_source_library_run"
    assert collect_action["enabled"] is True
    assert collect_action["payload"]["handler_key"] == "rss"
    assert collect_action["payload"]["override_params"]["site_entries"] == ["https://example.com/feed.xml"]
    assert "urls" not in collect_action["payload"]
    single_source_guard = collect_action["single_source_guard"]
    assert single_source_guard == body["data"]["review_closure"]["single_source_guard"]
    assert single_source_guard == collect_action["payload"]["override_params"]["single_source_guard"]
    assert single_source_guard["contract_version"] == "resource_pool.site_entry.single_source_guard.v1"
    assert single_source_guard["strict_source"] is True
    assert single_source_guard["guarantee"] is True
    assert single_source_guard["status"] == "passed"
    assert single_source_guard["reason_code"] is None
    assert single_source_guard["allowed_urls"] == ["https://example.com/feed.xml"]
    assert single_source_guard["allowed_count"] == 1
    assert single_source_guard["blocked_reason"] is None
    assert single_source_guard["source_ref"]["site_entry_url"] == "https://example.com/feed.xml"
    assert single_source_guard["report_source_ref"] == "resource_pool.site_entry:project:10"
    assert single_source_guard["runner_contract"]["guard_field"] == "override_params.site_entries"
    assert body["data"]["evidence_binding"]["source_ref"]["site_entry_url"] == "https://example.com/feed.xml"
    assert body["data"]["evidence_binding"]["report_source_ref"] == "resource_pool.site_entry:project:10"
    execution_fact = body["data"]["execution_fact"]
    assert execution_fact["contract_version"] == "resource.execution_fact.v1"
    assert execution_fact["reason_code"] == "ready_to_collect"
    assert execution_fact["review_state"] == "accepted"
    assert execution_fact["guard_status"] == "passed"
    assert execution_fact["lifecycle_transition"] == lifecycle_transition
    assert execution_fact["source_refs"][0]["report_source_ref"] == "resource_pool.site_entry:project:10"
    assert execution_fact["execution_plan_ref"]["site_entry_urls"] == ["https://example.com/feed.xml"]
    assert execution_fact["next_actions"][0]["action"] == "collect_source_library_run"
    assert captured["lookup"] == {
        "scope": "project",
        "project_key": "demo_proj",
        "site_url": "https://example.com/feed.xml",
    }
    assert captured["upsert"]["extra"]["legacy_key"] == "kept"
    assert captured["upsert"]["extra"]["lifecycle_state"] == "accepted"
    assert captured["upsert"]["extra"]["review_state"] == "accepted"
    assert captured["upsert"]["extra"]["lifecycle_review"]["reviewer"] == "qa"
    assert captured["upsert"]["extra"]["lifecycle_transition"] == lifecycle_transition
    assert captured["upsert"]["extra"]["review_closure"]["status"] == "ready_to_collect"
    assert captured["upsert"]["extra"]["review_closure"]["lifecycle_transition"] == lifecycle_transition
    assert captured["upsert"]["extra"]["evidence_binding"]["report_source_ref"] == "resource_pool.site_entry:project:10"
    assert captured["upsert"]["extra"]["execution_fact"]["reason_code"] == "ready_to_collect"
    assert captured["upsert"]["extra"]["execution_fact"]["lifecycle_transition"] == lifecycle_transition
    assert captured["upsert"]["enabled"] is True


def test_patch_site_entry_lifecycle_blocks_accepted_when_persisted_site_url_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        resource_pool_api,
        "get_site_entry_by_url",
        lambda **_: {
            "id": 13,
            "site_url": "",
            "domain": "example.com",
            "entry_type": "rss",
            "template": None,
            "name": "Broken Feed",
            "capabilities": {},
            "source": "manual",
            "source_ref": {},
            "tags": [],
            "enabled": True,
            "scope": "project",
            "extra": {},
        },
    )

    def _fake_upsert_site_entry(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": 13,
            "site_url": kwargs["site_url"],
            "domain": kwargs["domain"],
            "entry_type": kwargs["entry_type"],
            "template": kwargs["template"],
            "name": kwargs["name"],
            "capabilities": kwargs["capabilities"],
            "source": kwargs["source"],
            "source_ref": kwargs["source_ref"],
            "tags": kwargs["tags"],
            "enabled": kwargs["enabled"],
            "scope": kwargs["scope"],
            "extra": kwargs["extra"],
        }

    monkeypatch.setattr(resource_pool_api, "upsert_site_entry", _fake_upsert_site_entry)

    resp = client.patch(
        "/api/v1/resource_pool/site_entries/lifecycle",
        json={
            "project_key": "demo_proj",
            "scope": "project",
            "site_url": "https://example.com/feed.xml",
            "lifecycle_state": "accepted",
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    collect_action = data["next_actions"][0]
    assert data["lifecycle_state"] == "accepted"
    assert data["review_closure"]["status"] == "blocked"
    assert data["review_closure"]["reason_code"] == "missing_site_entry_url"
    assert data["review_closure"]["executable"] is False
    assert collect_action["enabled"] is False
    assert collect_action["blocked"] is True
    assert collect_action["block_reason"] == "missing_site_entry_url"
    assert collect_action["payload"]["override_params"]["site_entries"] == []
    assert data["execution_fact"]["guard_status"] == "blocked"
    assert data["lifecycle_transition"]["to_state"] == "accepted"
    assert data["lifecycle_transition"]["executable_after"] is False
    assert data["lifecycle_transition"]["to_state_executable"] is False
    assert captured["extra"]["site_entry_url_missing"] is True
    assert captured["extra"]["lifecycle_transition"]["executable_after"] is False


@pytest.mark.parametrize(
    ("lifecycle_state", "expected_enabled"),
    [
        ("accepted", True),
        ("rejected", True),
        ("needs_review", True),
        ("disabled", False),
    ],
)
def test_patch_site_entry_lifecycle_supports_review_states(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_state: str,
    expected_enabled: bool,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        resource_pool_api,
        "get_site_entry_by_url",
        lambda **_: {
            "id": 11,
            "site_url": "https://example.com/feed.xml",
            "domain": "example.com",
            "entry_type": "rss",
            "template": None,
            "name": "Example Feed",
            "capabilities": {},
            "source": "manual",
            "source_ref": {},
            "tags": [],
            "enabled": True,
            "scope": "project",
            "extra": {},
        },
    )

    def _fake_upsert_site_entry(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": 11,
            "site_url": kwargs["site_url"],
            "domain": kwargs["domain"],
            "entry_type": kwargs["entry_type"],
            "template": kwargs["template"],
            "name": kwargs["name"],
            "capabilities": kwargs["capabilities"],
            "source": kwargs["source"],
            "source_ref": kwargs["source_ref"],
            "tags": kwargs["tags"],
            "enabled": kwargs["enabled"],
            "scope": kwargs["scope"],
            "extra": kwargs["extra"],
        }

    monkeypatch.setattr(resource_pool_api, "upsert_site_entry", _fake_upsert_site_entry)

    resp = client.patch(
        "/api/v1/resource_pool/site_entries/lifecycle",
        json={
            "project_key": "demo_proj",
            "scope": "project",
            "site_url": "https://example.com/feed.xml",
            "lifecycle_state": lifecycle_state,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["lifecycle_state"] == lifecycle_state
    assert captured["extra"]["lifecycle_state"] == lifecycle_state
    assert captured["extra"]["review_state"] == lifecycle_state
    assert captured["enabled"] is expected_enabled
    collect_action = data["next_actions"][0]
    execution_fact = data["execution_fact"]
    single_source_guard = collect_action["single_source_guard"]
    assert single_source_guard == data["review_closure"]["single_source_guard"]
    assert single_source_guard == collect_action["payload"]["override_params"]["single_source_guard"]
    assert single_source_guard["strict_source"] is True
    assert single_source_guard["allowed_urls"] == ["https://example.com/feed.xml"]
    assert single_source_guard["allowed_count"] == 1
    assert collect_action["payload"]["override_params"]["site_entries"] == ["https://example.com/feed.xml"]
    assert "urls" not in collect_action["payload"]
    if lifecycle_state == "accepted":
        assert data["review_closure"]["status"] == "ready_to_collect"
        assert data["review_closure"]["reason_code"] == "ready_to_collect"
        assert collect_action["enabled"] is True
        assert collect_action["blocked"] is False
        assert collect_action["payload"]["handler_key"] == "rss"
        assert single_source_guard["guarantee"] is True
        assert single_source_guard["status"] == "passed"
        assert single_source_guard["blocked_reason"] is None
        assert execution_fact["reason_code"] == "ready_to_collect"
        assert execution_fact["review_state"] == "accepted"
        assert execution_fact["guard_status"] == "passed"
    else:
        assert data["review_closure"]["status"] == "blocked"
        assert collect_action["enabled"] is False
        assert collect_action["blocked"] is True
        assert collect_action["block_reason"] in {"review_rejected", "review_disabled", "review_needs_review"}
        assert single_source_guard["guarantee"] is False
        assert single_source_guard["status"] == "blocked"
        assert single_source_guard["blocked_reason"] == collect_action["block_reason"]
        assert execution_fact["reason_code"] == collect_action["block_reason"]
        assert execution_fact["review_state"] == lifecycle_state
        assert execution_fact["guard_status"] == "blocked"


def test_patch_site_entry_lifecycle_rejects_invalid_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_upsert(**_: Any) -> dict[str, Any]:
        raise AssertionError("upsert_site_entry should not be called for invalid lifecycle_state")

    monkeypatch.setattr(resource_pool_api, "upsert_site_entry", _unexpected_upsert)

    resp = client.patch(
        "/api/v1/resource_pool/site_entries/lifecycle",
        json={
            "project_key": "demo_proj",
            "scope": "project",
            "site_url": "https://example.com/feed.xml",
            "lifecycle_state": "archived",
        },
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "lifecycle_state must be one of" in body["error"]["message"]
    assert resp.headers.get("x-error-code") == "INVALID_INPUT"


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
    assert data["lifecycle_summary"]["state"] == "ready"
    assert data["lifecycle_summary"]["documents_inserted_valid"] == 2
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
    assert data["lifecycle_summary"]["state"] == "not_ready"
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
