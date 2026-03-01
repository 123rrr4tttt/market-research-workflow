from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.crawlers.base import CrawlerDispatchResult
    from app.services.crawlers.bridge import poll_crawler_job, submit_crawler_job

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class CrawlerManagementBridgeUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"crawler bridge unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_submit_crawler_job_dispatches_to_registered_provider(self):
        provider = Mock()
        provider.dispatch.return_value = CrawlerDispatchResult(
            provider_status="queued",
            provider_job_id="scrapyd-job-1",
            provider_type="scrapy",
            attempt_count=1,
            raw={"node": "n1"},
        )

        with patch("app.services.crawlers.bridge.get_provider", return_value=provider) as get_provider:
            result = submit_crawler_job(
                provider="scrapy",
                project="demo_scrapy",
                spider="market_spider",
                arguments={"q": "ai"},
                settings={"CONCURRENT_REQUESTS": 8},
                version="v1",
                priority=10,
            )

        get_provider.assert_called_once_with("scrapy")
        provider.dispatch.assert_called_once()
        request_obj = provider.dispatch.call_args.args[0]
        self.assertEqual(request_obj.provider, "scrapy")
        self.assertEqual(request_obj.project, "demo_scrapy")
        self.assertEqual(request_obj.spider, "market_spider")
        self.assertEqual(request_obj.arguments, {"q": "ai"})
        self.assertEqual(request_obj.settings, {"CONCURRENT_REQUESTS": 8})
        self.assertEqual(request_obj.version, "v1")
        self.assertEqual(request_obj.priority, 10)

        self.assertEqual(
            result,
            {
                "provider_status": "queued",
                "provider_job_id": "scrapyd-job-1",
                "provider_type": "scrapy",
                "attempt_count": 1,
                "raw": {"node": "n1"},
            },
        )

    def test_submit_crawler_job_raises_for_unregistered_provider(self):
        with patch("app.services.crawlers.bridge.get_provider", return_value=None):
            with self.assertRaises(ValueError) as ctx:
                submit_crawler_job(provider="unknown", project="demo", spider="spider")

        self.assertIn("crawler provider is not registered", str(ctx.exception))

    def test_poll_crawler_job_calls_provider_poll_and_sets_tracking_defaults(self):
        provider = Mock()
        provider.poll.return_value = SimpleNamespace(state="running", progress=0.5)

        with patch("app.services.crawlers.bridge.get_provider", return_value=provider) as get_provider:
            payload = poll_crawler_job(
                external_provider="scrapy",
                external_job_id="job-123",
                project="demo_scrapy",
                spider="market_spider",
                options={"verbose": True},
            )

        get_provider.assert_called_once_with("scrapy")
        provider.poll.assert_called_once_with(
            external_job_id="job-123",
            project="demo_scrapy",
            spider="market_spider",
            options={"verbose": True},
        )
        self.assertEqual(payload["state"], "running")
        self.assertEqual(payload["progress"], 0.5)
        self.assertEqual(payload["external_provider"], "scrapy")
        self.assertEqual(payload["external_job_id"], "job-123")

    def test_poll_crawler_job_raises_when_provider_has_no_poll(self):
        provider = Mock()
        provider.poll = None

        with patch("app.services.crawlers.bridge.get_provider", return_value=provider):
            with self.assertRaises(ValueError) as ctx:
                poll_crawler_job(external_provider="scrapy", external_job_id="job-1")

        self.assertIn("does not support poll()", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
