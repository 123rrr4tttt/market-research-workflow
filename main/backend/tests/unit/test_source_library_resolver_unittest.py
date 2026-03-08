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
        self.assertTrue(result["middle_layer_protocol"]["force_single_url_flow"])
        resolve_channel.assert_not_called()

    def test_force_single_url_flow_can_be_disabled_explicitly(self):
        item = {"item_key": "url_pool.default", "channel_key": "url_pool"}
        params = {
            "urls": ["https://example.com/a"],
            "force_single_url_flow": False,
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
            "force_single_url_flow": False,
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


if __name__ == "__main__":
    unittest.main()
