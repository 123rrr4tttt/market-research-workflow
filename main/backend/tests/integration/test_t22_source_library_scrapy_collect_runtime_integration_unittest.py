from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from app.services.collect_runtime.runtime import (
        collect_request_from_source_library_api,
        run_collect,
        run_source_library_item_compat,
    )
    from app.services.crawlers.base import CrawlerDispatchResult

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeScrapyProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def dispatch(self, request):  # noqa: ANN001
        self.calls.append(
            {
                "provider": request.provider,
                "project": request.project,
                "spider": request.spider,
                "arguments": dict(request.arguments or {}),
            }
        )
        return CrawlerDispatchResult(
            provider_type="scrapy",
            provider_status="queued",
            provider_job_id="job-123",
            attempt_count=1,
            raw={"scheduler": "mocked"},
        )


class T22SourceLibraryScrapyCollectRuntimeIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"T22 integration test requires backend dependencies: {_IMPORT_ERROR}")

    def test_source_library_scrapy_item_dispatch_chain_surfaces_provider_metadata(self):
        item_key = "t22-item"
        channel_key = "crawler.scrapy.t22"
        fake_items = [
            {
                "item_key": item_key,
                "name": "T22 Scrapy Item",
                "channel_key": channel_key,
                "enabled": True,
                "params": {"scrapy_project": "demo_proj", "spider": "news_spider"},
                "extra": {},
            }
        ]
        fake_channels = [
            {
                "channel_key": channel_key,
                "name": "T22 Scrapy Channel",
                "kind": "crawler",
                "provider": "crawler",
                "provider_type": "scrapy",
                "provider_config": {},
                "execution_policy": {},
                "default_params": {},
                "param_schema": {},
                "enabled": True,
            }
        ]
        fake_provider = _FakeScrapyProvider()

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local-1"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.source_library.resolver.list_effective_channels", return_value=fake_channels),
            patch("app.services.source_library.runner._ensure_handlers_registered", return_value=None),
            patch("app.services.crawlers.registry.get_provider", return_value=fake_provider),
        ):
            request = collect_request_from_source_library_api(
                item_key=item_key,
                project_key=None,
                override_params={"arguments": {"keyword": "ai"}},
            )
            collect_result = run_collect(request)
            compat_result = run_source_library_item_compat(
                item_key=item_key,
                project_key=None,
                override_params={"arguments": {"keyword": "ai"}},
            )

        self.assertEqual(len(fake_provider.calls), 2)
        self.assertEqual(fake_provider.calls[0]["provider"], "scrapy")
        self.assertEqual(fake_provider.calls[0]["project"], "demo_proj")
        self.assertEqual(fake_provider.calls[0]["spider"], "news_spider")
        self.assertEqual(fake_provider.calls[0]["arguments"], {"keyword": "ai"})

        raw = (collect_result.meta or {}).get("raw") or {}
        nested = raw.get("result") or {}
        self.assertEqual(raw.get("item_key"), item_key)
        self.assertEqual(raw.get("channel_key"), channel_key)
        self.assertEqual(nested.get("provider_type"), "scrapy")
        self.assertEqual(nested.get("provider_status"), "queued")
        self.assertEqual(nested.get("provider_job_id"), "job-123")
        self.assertEqual(nested.get("attempt_count"), 1)
        self.assertEqual((nested.get("errors") or []), [])

        compat_nested = (compat_result.get("result") or {})
        self.assertEqual(compat_nested.get("provider_type"), "scrapy")
        self.assertEqual(compat_nested.get("provider_status"), "queued")
        self.assertEqual(compat_nested.get("provider_job_id"), "job-123")
        self.assertEqual(compat_nested.get("attempt_count"), 1)


if __name__ == "__main__":
    unittest.main()
