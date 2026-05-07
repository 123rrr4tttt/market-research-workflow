from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.source_library import resolver

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SourceLibraryResolverUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"source_library resolver unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_url_pool_item_routes_urls_back_to_url_pool_channel_by_default(self):
        item = {"item_key": "url_pool.default", "channel_key": "url_pool"}
        params = {"urls": ["https://example.com/a", "https://example.com/b"]}
        channel_map = {
            "url_pool": {"channel_key": "url_pool", "enabled": True, "provider_type": "native", "default_params": {}},
            "crawler.demo_proj": {
                "channel_key": "crawler.demo_proj",
                "enabled": True,
                "provider_type": "scrapy",
                "default_params": {},
            },
        }

        used_channel_keys: list[str] = []

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            used_channel_keys.append(str(channel.get("channel_key")))
            return {"inserted": 1, "skipped": 0}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url") as resolve_channel,
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(used_channel_keys, ["url_pool", "url_pool"])
        self.assertEqual(result["middle_layer_protocol"]["execution_mode"], "url_routing")
        self.assertEqual(result["middle_layer_protocol"]["pipeline"]["mode"], "candidate_fetch")
        self.assertTrue(result["middle_layer_protocol"]["force_url_routing_flow"])
        resolve_channel.assert_not_called()

    def test_run_item_with_url_routing_materializes_runtime_targets_before_helper(self):
        item = {"item_key": "url_pool.default", "channel_key": "url_pool"}
        params = {"urls": ["https://example.com/a", "https://example.com/b"]}
        channel_map = {
            "url_pool": {"channel_key": "url_pool", "enabled": True, "provider_type": "native", "default_params": {}},
        }
        expected = {
            "by_url": [],
            "records": [],
            "stats": {"fetched": 0, "normalized": 0, "dropped": 0, "errors": 0},
            "legacy_counts": {"inserted": 0, "updated": 0, "skipped": 0},
            "errors": [],
            "diagnostics": {"concurrency_plan": {}, "url_stage": {}},
            "middle_layer_protocol": {"execution_mode": "url_routing"},
            "url_routing_parallelism": 1,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
        }
        captured: dict[str, object] = {}

        def _fake_helper(**kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return expected

        with patch("app.services.source_library.resolver._run_url_routing_materialization", side_effect=_fake_helper):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertIs(result, expected)
        self.assertEqual(
            captured["runtime_targets"],
            [
                ("https://example.com/a", {"source": "params.urls", "index": 0}),
                ("https://example.com/b", {"source": "params.urls", "index": 1}),
            ],
        )
        self.assertEqual(captured["item"], item)
        self.assertEqual(captured["params"], params)
        self.assertEqual(captured["project_key"], "demo_proj")
        self.assertEqual(captured["channel_map"], channel_map)

    def test_list_effective_channels_attaches_source_tiering_contract(self):
        shared_channels = [
            {
                "channel_key": "crawler.demo_proj",
                "name": "Crawler",
                "kind": "collect",
                "provider": "crawler",
                "provider_type": "scrapy",
                "provider_config": {},
                "execution_policy": {},
                "description": None,
                "credential_refs": [],
                "default_params": {},
                "param_schema": {},
                "extends_channel_key": None,
                "enabled": True,
                "extra": {},
                "scope": "shared",
            }
        ]
        with (
            patch("app.services.source_library.resolver._load_shared_channels", return_value=shared_channels),
            patch("app.services.source_library.resolver._load_project_channels", return_value=[]),
        ):
            channels = resolver.list_effective_channels(scope="effective", project_key="demo_proj")

        channel = next(ch for ch in channels if ch["channel_key"] == "crawler.demo_proj")
        self.assertEqual(channel["source_tier"], "tier_2_directed_high_value")
        self.assertEqual(channel["onboarding_priority"], "p1_next")
        self.assertEqual(
            channel["extra"]["source_tiering"]["tier"],
            "tier_2_directed_high_value",
        )

    def test_list_effective_items_returns_definition_first_handler_cluster_item_by_default(self):
        project_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "Handler Cluster search_template",
                "channel_key": "handler.cluster",
                "description": "Stable handler-cluster item generated from resource_pool.site_entries entry_type=search_template",
                "params": {
                    "site_entries": [
                        "https://stcn.com/search",
                        "https://arxiv.org/search?q=%7B%7Bq%7D%7D",
                        "https://www.finextra.com/searcharticle.aspx?search=%7B%7Bq%7D%7D",
                        "https://venturebeat.com/?s=%7B%7Bq%7D%7D",
                        "https://docs.github.com/search?query=%7B%7Bq%7D%7D",
                        "https://news.google.com/search?q=%7B%7Bq%7D%7D",
                    ],
                    "expected_entry_type": "search_template",
                },
                "tags": ["handler_cluster", "search_template"],
                "enabled": True,
                "extra": {
                    "creation_handler": "handler.entry_type",
                    "expected_entry_type": "search_template",
                    "stable_handler_cluster": True,
                },
                "scope": "project",
            }
        ]

        with (
            patch("app.services.source_library.resolver._load_shared_items", return_value=[]),
            patch("app.services.source_library.resolver._load_project_items", return_value=project_items),
        ):
            items = resolver.list_effective_items(scope="effective", project_key="demo_proj")

        item = next(row for row in items if row["item_key"] == "handler.cluster.search_template")
        self.assertEqual(
            item["params"]["site_entries"],
            [
                "https://stcn.com/search",
                "https://arxiv.org/search?q=%7B%7Bq%7D%7D",
                "https://www.finextra.com/searcharticle.aspx?search=%7B%7Bq%7D%7D",
                "https://venturebeat.com/?s=%7B%7Bq%7D%7D",
                "https://docs.github.com/search?query=%7B%7Bq%7D%7D",
                "https://news.google.com/search?q=%7B%7Bq%7D%7D",
            ],
        )
        self.assertNotIn("official_access_site_entries", item["params"])
        self.assertNotIn("search_template_source_set", item["extra"])

    def test_list_effective_items_can_opt_in_execution_plan_for_handler_cluster_item(self):
        project_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "Handler Cluster search_template",
                "channel_key": "handler.cluster",
                "description": "Stable handler-cluster item generated from resource_pool.site_entries entry_type=search_template",
                "params": {
                    "site_entries": [
                        "https://stcn.com/search",
                        "https://arxiv.org/search?q=%7B%7Bq%7D%7D",
                        "https://www.finextra.com/searcharticle.aspx?search=%7B%7Bq%7D%7D",
                        "https://venturebeat.com/?s=%7B%7Bq%7D%7D",
                        "https://docs.github.com/search?query=%7B%7Bq%7D%7D",
                        "https://news.google.com/search?q=%7B%7Bq%7D%7D",
                    ],
                    "expected_entry_type": "search_template",
                },
                "tags": ["handler_cluster", "search_template"],
                "enabled": True,
                "extra": {
                    "creation_handler": "handler.entry_type",
                    "expected_entry_type": "search_template",
                    "stable_handler_cluster": True,
                },
                "scope": "project",
            }
        ]

        with (
            patch("app.services.source_library.resolver._load_shared_items", return_value=[]),
            patch("app.services.source_library.resolver._load_project_items", return_value=project_items),
        ):
            items = resolver.list_effective_items(
                scope="effective",
                project_key="demo_proj",
                include_execution_plan=True,
            )

        item = next(row for row in items if row["item_key"] == "handler.cluster.search_template")
        self.assertEqual(
            item["execution_plan"]["route_buckets"]["site_entries"],
            [
                "https://venturebeat.com/?s=%7B%7Bq%7D%7D",
                "https://docs.github.com/search?query=%7B%7Bq%7D%7D",
            ],
        )
        self.assertEqual(
            item["execution_plan"]["route_buckets"]["official_access_site_entries"],
            ["https://arxiv.org/search?q=%7B%7Bq%7D%7D"],
        )
        self.assertEqual(item["execution_plan"]["plan_meta"]["search_template_source_set"], "validated_query_capable")
        self.assertEqual(item["execution_plan"]["plan_meta"]["search_template_source_set_counts"]["input"], 6)
        self.assertEqual(item["execution_plan"]["plan_meta"]["search_template_source_set_counts"]["official_access"], 1)
        self.assertEqual(item["execution_plan"]["plan_meta"]["search_template_source_set_counts"]["retained"], 2)
        self.assertEqual(
            item["execution_plan"]["plan_meta"]["search_template_source_set_drop_reasons"]["missing_query_placeholder"],
            1,
        )
        self.assertEqual(
            item["execution_plan"]["plan_meta"]["search_template_source_set_drop_reasons"]["policy_deprioritized"],
            2,
        )
        self.assertEqual(
            item["execution_plan"]["plan_meta"]["search_template_source_set_drop_reasons"]["api_preferred_rerouted"],
            1,
        )

    def test_force_url_routing_flow_can_be_disabled_explicitly(self):
        item = {"item_key": "url_pool.default", "channel_key": "url_pool"}
        params = {
            "urls": ["https://example.com/a"],
            "force_url_routing_flow": False,
            "prefer_crawler_first": False,
        }
        channel_map = {
            "url_pool": {"channel_key": "url_pool", "enabled": True, "provider_type": "native", "default_params": {}},
            "generic_web.rss": {"channel_key": "generic_web.rss", "enabled": True, "provider_type": "native", "default_params": {}},
        }

        used_channel_keys: list[str] = []

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            used_channel_keys.append(str(channel.get("channel_key")))
            return {"inserted": 0, "skipped": 1}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss") as resolve_channel,
        ):
            resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(used_channel_keys, ["generic_web.rss"])
        resolve_channel.assert_called_once()

    def test_default_url_routing_prefers_mechanical_channel_before_crawler(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": ["https://example.com/a"],
        }
        channel_map = {
            "crawler.demo_proj": {
                "channel_key": "crawler.demo_proj",
                "enabled": True,
                "provider_type": "scrapy",
                "default_params": {},
            },
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        used_channel_keys: list[str] = []

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            used_channel_keys.append(str(channel.get("channel_key")))
            return {"inserted": 1, "updated": 0, "skipped": 0}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss") as resolve_channel,
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(used_channel_keys, ["generic_web.rss"])
        self.assertFalse(result["middle_layer_protocol"]["prefer_crawler_first"])
        resolve_channel.assert_called_once()

    def test_default_url_routing_falls_back_to_crawler_when_mechanical_has_no_results(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": ["https://example.com/a"],
            "prefer_crawler_first": False,
        }
        channel_map = {
            "crawler.demo_proj": {
                "channel_key": "crawler.demo_proj",
                "enabled": True,
                "provider_type": "scrapy",
                "default_params": {},
            },
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        used_channel_keys: list[str] = []

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            channel_key = str(channel.get("channel_key"))
            used_channel_keys.append(channel_key)
            if channel_key == "generic_web.rss":
                return {"inserted": 0, "updated": 0, "skipped": 1}
            return {"inserted": 1, "updated": 0, "skipped": 0}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss") as resolve_channel,
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["errors"], [])
        self.assertEqual(used_channel_keys, ["generic_web.rss", "crawler.demo_proj"])
        self.assertEqual(result["by_url"][0]["channel_key"], "crawler.demo_proj")
        self.assertEqual(result["by_url"][0]["fallback_from_channel_key"], "generic_web.rss")
        self.assertEqual(result["by_url"][0]["fallback_reason"], "mechanical_no_results")
        resolve_channel.assert_called_once()

    def test_default_url_routing_can_disable_crawler_fallback_on_empty(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": ["https://example.com/a"],
            "prefer_crawler_first": False,
            "force_crawler_fallback_on_empty": False,
        }
        channel_map = {
            "crawler.demo_proj": {
                "channel_key": "crawler.demo_proj",
                "enabled": True,
                "provider_type": "scrapy",
                "default_params": {},
            },
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        used_channel_keys: list[str] = []

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            channel_key = str(channel.get("channel_key"))
            used_channel_keys.append(channel_key)
            return {"inserted": 0, "updated": 0, "skipped": 1}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss") as resolve_channel,
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(used_channel_keys, ["generic_web.rss"])
        self.assertEqual(result["by_url"][0]["channel_key"], "generic_web.rss")
        self.assertNotIn("fallback_from_channel_key", result["by_url"][0])
        resolve_channel.assert_called_once()

    def test_prefer_crawler_first_falls_back_to_resolved_channel_when_crawler_runtime_unavailable(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": ["https://example.com/a"],
            "prefer_crawler_first": True,
        }
        channel_map = {
            "crawler.demo_proj": {
                "channel_key": "crawler.demo_proj",
                "enabled": True,
                "provider_type": "scrapy",
                "default_params": {},
            },
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        used_channel_keys: list[str] = []

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            channel_key = str(channel.get("channel_key"))
            used_channel_keys.append(channel_key)
            if channel_key == "crawler.demo_proj":
                raise ValueError("crawler provider 'scrapy' is unavailable: missing scrapyd")
            return {"inserted": 1, "updated": 0, "skipped": 0}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss") as resolve_channel,
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["errors"], [])
        self.assertEqual(used_channel_keys, ["crawler.demo_proj", "generic_web.rss"])
        self.assertEqual(result["by_url"][0]["channel_key"], "generic_web.rss")
        self.assertEqual(result["by_url"][0]["fallback_from_channel_key"], "crawler.demo_proj")
        resolve_channel.assert_called_once()

    def test_url_routing_parallelism_keeps_result_order_stable(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": ["https://example.com/a", "https://example.com/b"],
            "prefer_crawler_first": False,
            "url_routing_parallelism": 2,
        }
        channel_map = {
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        lock = threading.Lock()
        release = threading.Event()
        active = 0
        peak_active = 0

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
                if peak_active >= 2:
                    release.set()
            release.wait(timeout=1.0)
            with lock:
                active -= 1
            return {"inserted": 1, "updated": 0, "skipped": 0}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss"),
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual([row["url"] for row in result["by_url"]], params["urls"])
        self.assertGreaterEqual(peak_active, 2)
        self.assertEqual(result["diagnostics"]["url_stage"]["budget"], 2)
        self.assertEqual(result["middle_layer_protocol"]["concurrency_plan"]["url"]["parallelism"], 2)

    def test_url_routing_isolates_single_url_timeout(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": ["https://example.com/a", "https://example.com/b"],
            "url_routing_parallelism": 2,
            "url_timeout_seconds": 0.01,
        }
        channel_map = {
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            url = str((params.get("urls") or [""])[0])
            if url.endswith("/a"):
                import time as _time

                _time.sleep(0.05)
            return {"inserted": 1, "updated": 0, "skipped": 0}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss"),
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["stats"]["errors"], 1)
        self.assertTrue(result["by_url"][0]["timeout"])
        self.assertIn("timeout", result["by_url"][0]["error"])
        self.assertEqual(result["by_url"][1]["channel_key"], "generic_web.rss")
        self.assertEqual(result["diagnostics"]["url_stage"]["timed_out"], 1)

    def test_url_pool_static_url_list_routes_through_front_door_by_default(self):
        item = {
            "item_key": "url_pool.default",
            "channel_key": "url_pool",
            "enabled": True,
            "params": {"urls": ["https://example.com/a"], "scope": "effective", "limit": 10},
        }
        channels = [{"channel_key": "url_pool", "enabled": True, "default_params": {"scope": "effective", "limit": 50}}]
        fake_result = {"inserted": 1, "updated": 0, "skipped": 0, "by_url": [], "errors": []}

        with (
            patch("app.services.source_library.resolver.run_item_with_url_routing", return_value=fake_result) as run_routed,
            patch("app.services.source_library.resolver.run_channel") as run_single,
        ):
            result = resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

        run_routed.assert_called_once()
        run_single.assert_not_called()
        self.assertEqual(result.get("result"), fake_result)
        self.assertEqual(result.get("params", {}).get("urls"), ["https://example.com/a"])

    def test_run_item_payload_injects_channel_source_tiering_into_protocol(self):
        item = {
            "item_key": "handler.cluster.news",
            "channel_key": "handler.cluster",
            "enabled": True,
            "params": {"urls": ["https://example.com/a"]},
            "extra": {},
        }
        channels = [
            {
                "channel_key": "handler.cluster",
                "enabled": True,
                "default_params": {},
                "source_tier": "tier_2_directed_high_value",
                "onboarding_priority": "p1_next",
                "extra": {
                    "source_tiering": {
                        "tier": "tier_2_directed_high_value",
                        "onboarding_priority": "p1_next",
                        "reason": "directed high-value provider path",
                    }
                },
            }
        ]
        fake_result = {"inserted": 1, "updated": 0, "skipped": 0, "by_url": [], "errors": []}

        with patch("app.services.source_library.resolver.run_item_with_url_routing", return_value=fake_result):
            result = resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

        protocol = result["result"]["middle_layer_protocol"]
        self.assertEqual(protocol["source_tier"], "tier_2_directed_high_value")
        self.assertEqual(protocol["onboarding_priority"], "p1_next")

    def test_url_pool_static_url_list_can_be_frozen_explicitly(self):
        item = {
            "item_key": "url_pool.default",
            "channel_key": "url_pool",
            "enabled": True,
            "params": {"urls": ["https://example.com/a"]},
        }
        channels = [{"channel_key": "url_pool", "enabled": True, "default_params": {}}]
        captured_params = {}

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            captured_params.update(dict(params))
            return {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}

        with (
            patch("app.services.source_library.resolver.run_item_with_url_routing") as run_routed,
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
        ):
            result = resolver.run_item_payload(
                item=item,
                channels=channels,
                project_key=None,
                override_params={"enable_legacy_url_list": False},
            )

        run_routed.assert_not_called()
        self.assertNotIn("urls", captured_params)
        self.assertTrue(captured_params.get("legacy_url_list_frozen"))
        self.assertEqual(result.get("channel_key"), "url_pool")

    def test_url_routing_preserves_input_order_in_aggregated_by_url_rows(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {
            "urls": [
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
            ],
            "force_url_routing_flow": False,
            "prefer_crawler_first": False,
            "url_routing_parallelism": 2,
        }
        channel_map = {
            "generic_web.rss": {"channel_key": "generic_web.rss", "enabled": True, "provider_type": "native", "default_params": {}},
        }

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            url = str((params.get("urls") or [""])[0])
            return {"inserted": 1, "updated": 0, "skipped": 0, "echo_url": url}

        with (
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss"),
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
            )

        self.assertEqual(
            [row["url"] for row in result["by_url"]],
            ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        )
        self.assertEqual(
            result["middle_layer_protocol"]["candidate_urls"],
            ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        )
        self.assertEqual(result["url_routing_parallelism"], 2)

    def test_run_item_payload_resolves_urls_to_url_execution(self):
        item = {
            "item_key": "handler.cluster.news",
            "channel_key": "handler.cluster",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com"],
                "urls": ["https://example.com/a"],
            },
        }
        channels = [{"channel_key": "handler.cluster", "enabled": True, "default_params": {}}]
        fake_result = {"inserted": 1, "updated": 0, "skipped": 0, "by_url": [], "errors": []}

        with (
            patch("app.services.source_library.resolver.run_item_with_url_routing", return_value=fake_result) as routed_run,
            patch("app.services.source_library.resolver._run_handler_cluster_item") as site_search_run,
        ):
            result = resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

        routed_run.assert_called_once()
        site_search_run.assert_not_called()
        self.assertEqual(result["result"]["execution_request"]["source_mode"], "url_execution")
        self.assertEqual(
            routed_run.call_args.kwargs.get("execution_layer"),
            "terminal_output_only",
        )

    def test_run_item_with_url_routing_terminal_layer_executes_without_write_semantics(self):
        item = {"item_key": "report1.root_site_search", "channel_key": "handler.cluster"}
        params = {"urls": ["https://example.com/a"], "prefer_crawler_first": False}
        channel_map = {
            "generic_web.rss": {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "provider_type": "native",
                "default_params": {},
            },
        }

        with (
            patch(
                "app.services.source_library.resolver.run_channel",
                return_value={"status": "fetched", "execution_layer": "terminal_output_only"},
            ) as run_channel,
            patch("app.services.source_library.resolver.resolve_channel_for_url", return_value="generic_web.rss"),
        ):
            result = resolver.run_item_with_url_routing(
                item=item,
                params=params,
                project_key="demo_proj",
                channel_map=channel_map,
                execution_layer="terminal_output_only",
            )

        run_channel.assert_called_once()
        self.assertEqual(result["execution_layer"], "terminal_output_only")
        self.assertNotIn("inserted", result)
        self.assertNotIn("updated", result)
        self.assertNotIn("skipped", result)
        self.assertEqual(result["legacy_counts"]["inserted"], 0)
        self.assertEqual(result["legacy_counts"]["updated"], 0)
        self.assertEqual(result["legacy_counts"]["skipped"], 0)
        self.assertEqual(result["by_url"][0]["channel_key"], "generic_web.rss")
        self.assertEqual(result["by_url"][0]["result"]["execution_layer"], "terminal_output_only")

    def test_site_search_mode_forces_handler_cluster_front_door(self):
        item = {
            "item_key": "custom.site.seed",
            "channel_key": "market.default",
            "enabled": True,
            "params": {"site_entries": ["https://example.com"]},
        }
        channels = [
            {"channel_key": "market.default", "enabled": True, "default_params": {}, "provider_type": "native"},
            {"channel_key": "handler.cluster", "enabled": True, "default_params": {}, "provider_type": "native"},
        ]
        captured = {}

        def _fake_run_handler_cluster_item(*, item, params, project_key, channel_map):  # noqa: ANN001
            captured["channel_key"] = item.get("channel_key")
            return {"item_key": item.get("item_key"), "channel_key": item.get("channel_key"), "params": params, "result": {}}

        with patch("app.services.source_library.resolver._run_handler_cluster_item", side_effect=_fake_run_handler_cluster_item):
            result = resolver.run_item_payload(item=item, channels=channels, project_key="demo_proj", override_params=None)

        self.assertEqual(captured["channel_key"], "handler.cluster")
        self.assertEqual(result["result"]["execution_request"]["source_mode"], "site_search")

    def test_generic_web_item_direct_execution_is_rejected(self):
        item = {
            "item_key": "generic_web.demo",
            "channel_key": "generic_web.rss",
            "enabled": True,
            "params": {"urls": ["https://example.com/feed.xml"]},
        }
        channels = [
            {
                "channel_key": "generic_web.rss",
                "enabled": True,
                "default_params": {},
                "provider": "generic_web",
                "provider_type": "native",
            }
        ]
        with self.assertRaisesRegex(ValueError, "generic_web\\.\\* direct item execution is disabled"):
            resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

    def test_normalize_search_params_unifies_aliases_and_time_fields(self):
        normalized = resolver._normalize_search_params(  # noqa: SLF001
            {
                "keywords": ["alpha", "beta"],
                "limit": 30,
                "paged": 2,
                "per_page": 25,
                "pages": 4,
                "days_back": 14,
                "date_from": "2026-03-01",
                "date_to": "2026-03-12",
            }
        )
        self.assertEqual(normalized["query_terms"], ["alpha", "beta"])
        self.assertEqual(normalized["max_items"], 30)
        self.assertEqual(normalized["ingest_limit"], 30)
        self.assertEqual(normalized["page"], 2)
        self.assertEqual(normalized["page_size"], 25)
        self.assertEqual(normalized["max_pages"], 4)
        self.assertEqual(normalized["start_time"], "2026-03-01")
        self.assertEqual(normalized["end_time"], "2026-03-12")

    def test_execution_request_contains_normalized_params_snapshot(self):
        item = {
            "item_key": "handler.cluster.news",
            "channel_key": "handler.cluster",
            "enabled": True,
            "params": {"site_entries": ["https://example.com"], "keywords": ["x"], "limit": 9},
        }
        channels = [{"channel_key": "handler.cluster", "enabled": True, "default_params": {}}]
        fake_result = {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}

        with patch("app.services.source_library.resolver._run_handler_cluster_item", return_value={"result": fake_result}):
            result = resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

        snapshot = result["result"]["execution_request"]["params"]
        self.assertEqual(snapshot.get("query_terms"), ["x"])
        self.assertEqual(snapshot.get("max_items"), 9)

    def test_execution_request_contains_taxonomy_for_site_search_item(self):
        item = {
            "item_key": "handler.cluster.news",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {"site_entries": ["https://example.com/search?q={{q}}"], "keywords": ["x"], "limit": 9},
            "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
        }
        channels = [{"channel_key": "handler.cluster", "enabled": True, "default_params": {}}]
        fake_result = {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}

        with patch("app.services.source_library.resolver._run_handler_cluster_item", return_value={"result": fake_result}):
            result = resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

        taxonomy = result["result"]["execution_request"]["taxonomy"]
        self.assertEqual(taxonomy["channel_family"], "generic_web")
        self.assertEqual(taxonomy["item_type"], "service_aggregated")
        self.assertEqual(taxonomy["managed_by"], "system")
        self.assertTrue(taxonomy["site_search_authoritative"])


if __name__ == "__main__":
    unittest.main()
