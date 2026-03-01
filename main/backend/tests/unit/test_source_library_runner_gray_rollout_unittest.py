from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.source_library.runner import run_channel

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SourceLibraryRunnerGrayRolloutUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"source_library runner unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_crawler_provider_routes_via_registry_when_whitelisted(self):
        channel = {
            "channel_key": "crawler.market",
            "provider_type": "scrapy",
            "provider": "market",
            "kind": "search",
            "execution_policy": {
                "gray_release": {
                    "allowlist": {
                        "projects": ["demo_proj"],
                        "items": ["item.whitelisted"],
                    }
                }
            },
            "param_schema": {},
            "credential_refs": [],
        }
        params = {"keywords": ["ai"]}
        crawler_result = {"provider_type": "scrapy", "provider_status": "queued"}
        native_handler = lambda _params, _project_key: {"provider_type": "native"}  # noqa: E731
        customization = SimpleNamespace(get_channel_handlers=lambda: {})

        with (
            patch("app.services.source_library.runner._ensure_handlers_registered"),
            patch("app.services.source_library.runner.get_project_customization", return_value=customization),
            patch("app.services.source_library.runner.get", return_value=native_handler),
            patch(
                "app.services.source_library.runner._run_via_crawler_provider_registry",
                return_value=crawler_result,
            ) as run_crawler,
        ):
            result = run_channel(
                channel=channel,
                params=params,
                project_key="demo_proj",
                item_key="item.whitelisted",
            )

        self.assertEqual(result, crawler_result)
        run_crawler.assert_called_once()

    def test_crawler_provider_falls_back_to_native_when_not_whitelisted(self):
        channel = {
            "channel_key": "crawler.market",
            "provider_type": "scrapy",
            "provider": "market",
            "kind": "search",
            "execution_policy": {
                "gray_release": {
                    "allowlist": {
                        "projects": ["demo_proj"],
                        "items": ["item.whitelisted"],
                    }
                }
            },
            "param_schema": {},
            "credential_refs": [],
        }
        params = {"keywords": ["ai"]}
        native_result = {"provider_type": "native", "inserted": 1}
        customization = SimpleNamespace(get_channel_handlers=lambda: {})

        def native_handler(_params, _project_key):
            return native_result

        with (
            patch("app.services.source_library.runner._ensure_handlers_registered"),
            patch("app.services.source_library.runner.get_project_customization", return_value=customization),
            patch("app.services.source_library.runner.get", return_value=native_handler),
            patch("app.services.source_library.runner._run_via_crawler_provider_registry") as run_crawler,
        ):
            result = run_channel(
                channel=channel,
                params=params,
                project_key="other_proj",
                item_key="item.not_in_allowlist",
            )

        self.assertEqual(result, native_result)
        run_crawler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
