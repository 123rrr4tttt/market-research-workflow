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
    from app.services.crawlers.base import CrawlerDispatchResult
    from app.services.source_library import provider_ports

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SourceLibraryRunnerGrayRolloutUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"source_library runner unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_crawler_provider_statuses_map_collection_boundary_status(self):
        from app.composition.source_library import configure_source_library_adapters

        channel = {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "provider": "crawler",
            "kind": "collect",
            "execution_policy": {},
            "param_schema": {},
            "credential_refs": [],
        }
        params = {"spider": "news_spider"}
        customization = SimpleNamespace(get_channel_handlers=lambda: {})
        original_resolver = provider_ports._CRAWLER_PROVIDER_RESOLVER
        configure_source_library_adapters()

        class _FakeProvider:
            provider_type = "scrapy"

            def dispatch(self, request):  # noqa: ANN001
                self.request = request
                return CrawlerDispatchResult(
                    provider_type="scrapy",
                    provider_status=self.status,
                    provider_job_id=f"job-{self.status or 'unknown'}",
                    attempt_count=1,
                )

        provider = _FakeProvider()

        class _FakeResolver:
            def resolve(self, provider_type, *, channel, params):  # noqa: ANN001
                self.calls = [(provider_type, channel, params)]
                return provider

        fake_resolver = _FakeResolver()
        provider_ports.set_crawler_provider_resolver(fake_resolver)
        try:
            for status, expected in (
                ("queued", "accepted"),
                ("scheduled", "accepted"),
                ("running", "accepted"),
                ("accepted", "accepted"),
                ("failed", "failed"),
                ("unknown", "failed"),
            ):
                with (
                    self.subTest(status=status),
                    patch("app.services.source_library.runner._ensure_handlers_registered"),
                    patch(
                        "app.services.source_library.runner.get_project_customization",
                        return_value=customization,
                    ),
                ):
                    provider.status = status
                    result = run_channel(
                        channel=channel,
                        params=params,
                        project_key="demo_proj",
                        item_key="handler.cluster.news",
                    )

                self.assertEqual(result["status"], expected)
                self.assertEqual(result["inserted"], 0)
                self.assertEqual(result["updated"], 0)
                self.assertEqual(result["skipped"], 0)
                self.assertEqual(result["provider_job_id"], f"job-{status}")

            self.assertEqual(fake_resolver.calls, [("scrapy", channel, params)])
            self.assertEqual(provider.request.provider, "scrapy")
            self.assertEqual(provider.request.project, "demo_proj")
            self.assertEqual(provider.request.spider, "news_spider")
        finally:
            provider_ports.set_crawler_provider_resolver(original_resolver)

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

    def test_run_channel_blocks_single_source_guard_before_crawler_dispatch(self):
        channel = {
            "channel_key": "crawler.market",
            "provider_type": "scrapy",
            "provider": "market",
            "kind": "search",
            "execution_policy": {},
            "param_schema": {},
            "credential_refs": [],
        }
        params = {
            "site_entries": ["https://example.com/a"],
            "single_source_guard": {
                "strict_source": True,
                "guarantee": True,
                "allowed_count": 1,
                "allowed_urls": ["https://example.com/b"],
            },
        }

        with (
            patch("app.services.source_library.runner._ensure_handlers_registered"),
            patch("app.services.source_library.runner._run_via_crawler_provider_registry") as run_crawler,
        ):
            with self.assertRaisesRegex(ValueError, "site_entries must exactly match"):
                run_channel(
                    channel=channel,
                    params=params,
                    project_key="demo_proj",
                    item_key="item.guard",
                )

        run_crawler.assert_not_called()

    def test_run_channel_blocks_single_source_guard_before_native_handler(self):
        channel = {
            "channel_key": "native.market",
            "provider_type": "native",
            "provider": "market",
            "kind": "search",
            "param_schema": {},
            "credential_refs": [],
        }
        params = {
            "site_entries": ["https://example.com/a"],
            "single_source_guard": {
                "strict_source": True,
                "guarantee": False,
                "blocked_reason": "not_accepted",
                "allowed_count": 1,
                "allowed_urls": ["https://example.com/a"],
            },
        }
        native_handler = lambda _params, _project_key: {"provider_type": "native"}  # noqa: E731
        customization = SimpleNamespace(get_channel_handlers=lambda: {})

        with (
            patch("app.services.source_library.runner._ensure_handlers_registered"),
            patch("app.services.source_library.runner.get_project_customization", return_value=customization),
            patch("app.services.source_library.runner.get", return_value=native_handler) as get_handler,
        ):
            with self.assertRaisesRegex(ValueError, "single_source_guard is blocked"):
                run_channel(
                    channel=channel,
                    params=params,
                    project_key="demo_proj",
                    item_key="item.guard",
                )

        get_handler.assert_not_called()

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

    def test_scrapy_provider_is_lazily_constructed_when_registry_is_empty(self):
        from app.composition.source_library import configure_source_library_adapters

        channel = {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "provider": "crawler",
            "kind": "collect",
            "execution_policy": {},
            "param_schema": {},
            "credential_refs": [],
            "provider_config": {"project": "demo_proj", "scrapyd_base_url": "http://channel.scrapyd"},
        }
        params = {
            "spider": "news_spider",
            "arguments": {"keyword": "ai"},
            "scrapyd_base_url": "http://params.scrapyd",
            "scrapyd_timeout": 12,
        }
        customization = SimpleNamespace(get_channel_handlers=lambda: {})
        original_resolver = provider_ports._CRAWLER_PROVIDER_RESOLVER
        configure_source_library_adapters()

        class _FakeProvider:
            provider_type = "scrapy"

            def dispatch(self, request):  # noqa: ANN001
                return CrawlerDispatchResult(
                    provider_type="scrapy",
                    provider_status="queued",
                    provider_job_id="job-123",
                    attempt_count=1,
                    raw={"provider": request.provider, "project": request.project, "spider": request.spider},
                )

        try:
            with (
                patch("app.services.source_library.runner._ensure_handlers_registered"),
                patch("app.services.source_library.runner.get_project_customization", return_value=customization),
                patch("app.services.source_library.runner.get"),
                patch("app.services.crawlers.registry.get_provider", return_value=None),
                patch("app.services.crawlers.registry.register_provider") as register_provider,
                patch(
                    "app.services.crawlers.providers.scrapy.ScrapyCrawlerProvider",
                    return_value=_FakeProvider(),
                ) as scrapy_provider,
            ):
                result = run_channel(
                    channel=channel,
                    params=params,
                    project_key="demo_proj",
                    item_key="handler.cluster.news",
                )
        finally:
            provider_ports.set_crawler_provider_resolver(original_resolver)

        self.assertEqual(result["provider_type"], "scrapy")
        self.assertEqual(result["provider_status"], "queued")
        self.assertEqual(result["runtime_channel"]["runtime_scope"], "project_config")
        self.assertEqual(result["runtime_channel"]["architecture_layer"], "runtime_only")
        self.assertEqual(
            result["runtime_channel"]["source_tiering"]["tier"],
            "tier_2_directed_high_value",
        )
        self.assertEqual(
            result["runtime_channel"]["layer_boundary"]["provider_dispatch"],
            "crawlers/providers",
        )
        register_provider.assert_called_once()
        scrapy_provider.assert_called_once_with(base_url="http://params.scrapyd", timeout=12.0)

    def test_scrapy_provider_reports_unavailable_instead_of_unsupported_when_init_fails(self):
        from app.composition.source_library import configure_source_library_adapters
        from app.services.source_library.provider_ports import (
            CrawlerProviderResolutionError,
        )

        channel = {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "provider": "crawler",
            "kind": "collect",
            "execution_policy": {},
            "param_schema": {},
            "credential_refs": [],
            "provider_config": {"project": "demo_proj"},
        }
        params = {"spider": "news_spider"}
        customization = SimpleNamespace(get_channel_handlers=lambda: {})
        original_resolver = provider_ports._CRAWLER_PROVIDER_RESOLVER
        configure_source_library_adapters()

        try:
            with (
                patch("app.services.source_library.runner._ensure_handlers_registered"),
                patch("app.services.source_library.runner.get_project_customization", return_value=customization),
                patch("app.services.source_library.runner.get"),
                patch("app.services.crawlers.registry.get_provider", return_value=None),
                patch(
                    "app.services.crawlers.providers.scrapy.ScrapyCrawlerProvider",
                    side_effect=RuntimeError("missing scrapyd"),
                ),
            ):
                with self.assertRaisesRegex(
                    CrawlerProviderResolutionError,
                    "crawler provider 'scrapy' is unavailable",
                ) as error:
                    run_channel(
                        channel=channel,
                        params=params,
                        project_key="demo_proj",
                        item_key="handler.cluster.news",
                    )
                self.assertEqual(error.exception.code, "provider_unavailable")
                self.assertEqual(error.exception.provider_type, "scrapy")
        finally:
            provider_ports.set_crawler_provider_resolver(original_resolver)


if __name__ == "__main__":
    unittest.main()
