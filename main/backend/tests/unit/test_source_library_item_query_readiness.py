from __future__ import annotations

from contextlib import nullcontext

import pytest

from app.services.source_library import item_writer
from app.services.source_library.item_plan import (
    ITEM_QUERY_READINESS_CONTRACT_VERSION,
    build_item_definition_view,
    build_item_query_readiness,
)


def _base_item(params: dict[str, object], extra: dict[str, object] | None = None):
    return {
        "item_key": "demo.item",
        "name": "Demo Item",
        "channel_key": "news",
        "params": params,
        "extra": extra or {},
    }


def test_query_readiness_uses_declared_static_routes_without_network() -> None:
    item = _base_item(
        {
            "site_entries": [
                "https://example.com/search?q={{q}}",
                "https://example.com/feed.xml",
                "https://example.com/sitemap.xml",
            ],
            "expected_entry_type": "search_template",
        }
    )
    readiness = build_item_query_readiness(
        item,
        site_entries=[
            {"site_url": "https://example.com/search?q={{q}}", "entry_type": "search_template"},
            {"site_url": "https://example.com/feed.xml", "entry_type": "rss"},
            {"site_url": "https://example.com/sitemap.xml", "entry_type": "sitemap"},
            {"site_url": "https://api.example.com/v1/search", "entry_type": "official_api", "capabilities": {"supports_query_terms": True}},
        ],
    )

    assert readiness["contract_version"] == ITEM_QUERY_READINESS_CONTRACT_VERSION
    assert readiness["automatic_assembly"] is True
    assert readiness["network_verified"] is False
    assert readiness["status"] == "ready"
    assert readiness["counts"] == {
        "ready": 4,
        "discovery_required": 0,
        "not_applicable": 0,
        "blocked": 0,
        "total": 4,
    }
    assert [row["status"] for row in readiness["entry_rows"]] == ["ready"] * 4
    assert readiness["entry_rows"][0]["route_kind"] == "search_template"


def test_domain_root_is_discovery_required_and_not_ready() -> None:
    readiness = build_item_query_readiness(
        _base_item({"site_entries": ["https://example.com/"], "expected_entry_type": "domain_root"}),
        site_entries=[{"site_url": "https://example.com/", "entry_type": "domain_root"}],
    )

    assert readiness["status"] == "discovery_required"
    assert readiness["entry_rows"] == [
        {
            "source_url": "https://example.com/",
            "status": "discovery_required",
            "route_kind": "domain_root",
            "reasons": ["domain_root_query_contract_not_declared"],
        }
    ]
    assert readiness["counts"]["ready"] == 0


def test_entry_template_takes_priority_over_source_root_url() -> None:
    readiness = build_item_query_readiness(
        _base_item({"expected_entry_type": "search_template"}),
        site_entries=[
            {
                "site_url": "https://example.com/",
                "template": "https://example.com/search?q={{q}}",
                "entry_type": "search_template",
            }
        ],
    )

    assert readiness["status"] == "ready"
    assert readiness["entry_rows"][0]["reasons"] == [
        "declared_query_template:entry_template"
    ]


def test_disabled_item_and_entry_are_explicitly_blocked_but_not_writer_rejections() -> None:
    disabled_item = _base_item(
        {
            "site_entries": ["https://example.com/search?q={{q}}"],
            "expected_entry_type": "search_template",
        }
    )
    disabled_item["enabled"] = False
    disabled_item_readiness = build_item_query_readiness(disabled_item)
    mixed_readiness = build_item_query_readiness(
        _base_item({"expected_entry_type": "search_template"}),
        site_entries=[
            {
                "site_url": "https://enabled.example.com/search?q={{q}}",
                "entry_type": "search_template",
            },
            {
                "site_url": "https://disabled.example.com/search?q={{q}}",
                "entry_type": "search_template",
                "enabled": False,
            },
        ],
    )

    assert disabled_item_readiness["status"] == "blocked"
    assert disabled_item_readiness["entry_rows"][0]["reasons"] == ["item_disabled"]
    assert mixed_readiness["status"] == "blocked"
    assert [row["status"] for row in mixed_readiness["entry_rows"]] == ["ready", "blocked"]
    assert mixed_readiness["entry_rows"][1]["reasons"] == ["entry_disabled"]
    assert mixed_readiness["counts"] == {
        "ready": 1,
        "discovery_required": 0,
        "not_applicable": 0,
        "blocked": 1,
        "total": 2,
    }


def test_disabled_external_project_is_blocked_before_route_readiness() -> None:
    item = _base_item(
        {},
        {
            "external_project_manifest": {
                "execution_mode": "rss_feed",
                "runner_ref": "https://example.com/feed.xml",
            },
        },
    )
    item["channel_key"] = "external_project"
    item["enabled"] = False
    readiness = build_item_query_readiness(item)

    assert readiness["status"] == "blocked"
    assert readiness["reasons"] == ["item_disabled"]
    assert readiness["entry_rows"][0]["status"] == "blocked"
    assert readiness["entry_rows"][0]["reasons"] == ["item_disabled"]
    assert readiness["counts"] == {
        "ready": 0,
        "discovery_required": 0,
        "not_applicable": 0,
        "blocked": 1,
        "total": 1,
    }


def test_disabled_empty_catalog_has_item_level_blocked_reason_without_fake_entry() -> None:
    item = _base_item({})
    item["enabled"] = False
    readiness = build_item_query_readiness(item)

    assert readiness["status"] == "blocked"
    assert readiness["reasons"] == ["item_disabled", "no_declared_site_entries"]
    assert readiness["entry_rows"] == []
    assert readiness["counts"]["total"] == 0


def test_site_entries_none_derives_conservatively_from_declared_members() -> None:
    item = _base_item(
        {},
        {
            "members": [
                {"site_url": "https://example.com/review", "role": "review_only"},
            ],
        },
    )
    readiness = build_item_query_readiness(item)

    assert readiness["status"] == "discovery_required"
    assert readiness["entry_rows"][0]["reasons"] == ["role=review_only", "entry_type_not_declared"]
    assert readiness["network_verified"] is False


def test_no_query_capability_catalog_is_not_applicable_and_inputs_unchanged() -> None:
    original = _base_item({"urls": ["https://example.com/article"]})
    item = {
        **original,
        "params": dict(original["params"]),
        "extra": dict(original["extra"]),
    }
    readiness = build_item_query_readiness(item)

    assert readiness["status"] == "not_applicable"
    assert readiness["entry_rows"] == []
    assert readiness["counts"]["not_applicable"] == 0
    assert item["params"] == {"urls": ["https://example.com/article"]}
    assert item["extra"] == {}


def test_definition_view_projects_readiness_in_plan_meta_without_mutating_input() -> None:
    item = _base_item(
        {"site_entries": ["https://example.com/"], "expected_entry_type": "domain_root"},
    )
    view = build_item_definition_view(item, include_execution_plan=True)
    plan = view["execution_plan"]
    assert isinstance(plan, dict)
    readiness = plan["plan_meta"]["query_readiness"]
    assert isinstance(readiness, dict)

    assert view["params"] == item["params"]
    assert set(item["extra"].items()).issubset(view["extra"].items())
    assert readiness["status"] == "discovery_required"
    assert readiness == build_item_query_readiness(item)


def test_writer_success_response_contains_same_derived_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExecuteResult:
        @staticmethod
        def scalar_one_or_none():
            return None

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def execute(_query):
            return _ExecuteResult()

        @staticmethod
        def add(_row):
            return None

        @staticmethod
        def commit():
            return None

    monkeypatch.setattr(item_writer, "require_project_key", lambda _value: "demo_proj")
    monkeypatch.setattr(item_writer, "bind_project", lambda _key: nullcontext())
    monkeypatch.setattr(item_writer, "SessionLocal", lambda: _Session())

    response = item_writer.upsert_project_item(
        payload=item_writer.SourceLibraryItemUpsertPayload(
            item_key="demo.item",
            name="Demo Item",
            channel_key="news",
            params={"site_entries": ["https://example.com/"], "expected_entry_type": "domain_root"},
            enabled=False,
        ),
        project_key="demo_proj",
    )

    item = {
        "item_key": "demo.item",
        "name": "Demo Item",
        "channel_key": "news",
        "enabled": False,
        "params": {
            "site_entries": ["https://example.com/"],
            "expected_entry_type": "domain_root",
        },
        "extra": {"capability": item_writer.SOURCE_ITEM_CAPABILITY_DEFAULT},
    }
    assert response["status"] == "ok"
    assert response["data"]["ok"] is True
    assert response["data"]["query_readiness"] == build_item_query_readiness(item)
    assert response["data"]["query_readiness"]["status"] == "blocked"
    assert response["data"]["query_readiness"]["network_verified"] is False


@pytest.mark.parametrize(
    ("source_url", "entry_type", "expected_status"),
    [
        ("https://example.com/search?q={{q}}", "search_template", "ready"),
        ("https://example.com/feed.xml", "rss", "ready"),
        ("https://example.com/sitemap.xml", "sitemap", "ready"),
    ],
)
def test_declared_route_kinds_are_static_only(
    source_url: str,
    entry_type: str,
    expected_status: str,
) -> None:
    readiness = build_item_query_readiness(
        _base_item({"expected_entry_type": entry_type}),
        site_entries=[{"site_url": source_url, "entry_type": entry_type}],
    )
    assert readiness["status"] == expected_status
    assert readiness["network_verified"] is False
