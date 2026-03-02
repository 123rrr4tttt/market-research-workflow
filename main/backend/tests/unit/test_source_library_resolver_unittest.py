from __future__ import annotations

import sys
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

    def test_url_pool_legacy_url_list_is_frozen_by_default(self):
        item = {
            "item_key": "url_pool.default",
            "channel_key": "url_pool",
            "enabled": True,
            "params": {"urls": ["https://example.com/a"], "scope": "effective", "limit": 10},
        }
        channels = [{"channel_key": "url_pool", "enabled": True, "default_params": {"scope": "effective", "limit": 50}}]
        captured_params = {}

        def _fake_run_channel(*, channel, params, project_key, item_key):  # noqa: ANN001
            captured_params.update(dict(params))
            return {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}

        with (
            patch("app.services.source_library.resolver.run_item_with_url_routing") as run_routed,
            patch("app.services.source_library.resolver.run_channel", side_effect=_fake_run_channel),
        ):
            result = resolver.run_item_payload(item=item, channels=channels, project_key=None, override_params=None)

        run_routed.assert_not_called()
        self.assertNotIn("urls", captured_params)
        self.assertTrue(captured_params.get("legacy_url_list_frozen"))
        self.assertEqual(result.get("channel_key"), "url_pool")

    def test_url_pool_legacy_url_list_can_be_enabled_explicitly(self):
        item = {
            "item_key": "url_pool.default",
            "channel_key": "url_pool",
            "enabled": True,
            "params": {"urls": ["https://example.com/a"]},
        }
        channels = [{"channel_key": "url_pool", "enabled": True, "default_params": {}}]
        fake_result = {"inserted": 1, "skipped": 0, "by_url": [], "errors": []}

        with (
            patch("app.services.source_library.resolver.run_item_with_url_routing", return_value=fake_result) as run_routed,
            patch("app.services.source_library.resolver.run_channel") as run_single,
        ):
            result = resolver.run_item_payload(
                item=item,
                channels=channels,
                project_key=None,
                override_params={"enable_legacy_url_list": True},
            )

        run_routed.assert_called_once()
        run_single.assert_not_called()
        self.assertEqual(result.get("result"), fake_result)


if __name__ == "__main__":
    unittest.main()
