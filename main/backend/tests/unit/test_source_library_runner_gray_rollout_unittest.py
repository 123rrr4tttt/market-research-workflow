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
    from app.services.crawlers.base import CrawlerDispatchResult
    from app.services.source_library import provider_ports
    from app.services.source_library.runner import run_channel

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

    def test_json_boundaries_share_recursive_legacy_semantics(self):
        from app.services.source_library.runner import _json_object, _mapping

        source = {
            1: "integer-key",
            "set": {"b", "a"},
            "frozenset": frozenset({"y", "x"}),
            "tuple": (1, 2),
            "error": ValueError("invalid option"),
            "nested": {"ok": True, 2: "nested-integer-key"},
        }

        crawler = _json_object(source)

        self.assertEqual(crawler["1"], "integer-key")
        self.assertEqual(set(crawler["set"]), {"a", "b"})
        self.assertEqual(set(crawler["frozenset"]), {"x", "y"})
        self.assertEqual(crawler["tuple"], [1, 2])
        self.assertEqual(crawler["error"], "invalid option")
        self.assertEqual(crawler["nested"], {"ok": True, "2": "nested-integer-key"})
        self.assertEqual(_mapping({"keyword": "ai", "nested": {7: "invalid-runner-key"}}), {})
        self.assertEqual(_mapping({"download_delay": 1, 8: "invalid-setting-key"}), {})

    def test_registered_scrapy_output_ingest_is_the_terminal_material_writer(self):
        from app.services.source_library.provider_ports import CrawlerOutputIngestResult
        from app.services.source_library.runner import _run_via_crawler_provider_registry

        channel = {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "provider_config": {},
            "execution_policy": {},
        }
        params = {
            "scrapy_project": "crawler_runtime",
            "spider": "news_spider",
            "output_ingest": {"enabled": True, "enable_extraction": False},
        }

        class _Provider:
            client = SimpleNamespace(base_url="http://scrapyd.test")

            def dispatch(self, request):  # noqa: ANN001
                return CrawlerDispatchResult(
                    provider_type="scrapy",
                    provider_status="queued",
                    provider_job_id="job-output-1",
                    attempt_count=1,
                )

            def poll(self, **_kwargs):  # noqa: ANN003
                return {
                    "external_provider": "scrapy",
                    "external_job_id": "job-output-1",
                    "provider_status": "completed",
                }

        with (
            patch("app.services.source_library.runner.resolve_crawler_provider", return_value=_Provider()),
            patch(
                "app.services.source_library.runner.ingest_crawler_output",
                return_value=CrawlerOutputIngestResult(
                    status="ingested",
                    payload={"import_result": {"inserted": 1, "updated": 2, "skipped": 3}},
                ),
            ) as ingest,
        ):
            result = _run_via_crawler_provider_registry(
                channel=channel,
                params=params,
                project_key="demo_proj",
                provider_type="scrapy",
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual((result["inserted"], result["updated"], result["skipped"]), (1, 2, 3))
        self.assertEqual(result["output_ingest"]["status"], "ingested")
        self.assertEqual(result["terminal_readback"]["kind"], "terminal")
        ingest.assert_called_once()
        request = ingest.call_args.args[0]
        self.assertEqual(request.provider_type, "scrapy")
        self.assertEqual(request.project_key, "demo_proj")
        self.assertEqual(request.provider_project, "crawler_runtime")
        self.assertEqual(request.provider_job_id, "job-output-1")
        self.assertEqual(request.base_url, "http://scrapyd.test")
        self.assertEqual(request.wait_timeout_seconds, 120.0)
        self.assertEqual(request.poll_interval_seconds, 0.5)
        self.assertEqual(request.source_name, "crawler.demo_proj")
        self.assertEqual(request.material_type, "news")
        self.assertFalse(request.enable_extraction)
        self.assertEqual(request.max_items, 100)

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


def _run_crawler_provider(provider: object, *, params: dict[str, object] | None = None):
    from app.services.source_library.runner import _run_via_crawler_provider_registry

    with patch("app.services.source_library.runner.resolve_crawler_provider", return_value=provider):
        return _run_via_crawler_provider_registry(
            channel={"channel_key": "crawler.demo_proj", "provider_type": "scrapy", "execution_policy": {"timeout": 7}},
            params={
                "spider": "news_spider",
                "attempt_id": "attempt-explicit",
                "idempotency_key": "key-explicit",
                **(params or {}),
            },
            project_key="demo_proj",
            provider_type="scrapy",
        )


def test_canonical_readback_and_ingest_project_once_after_effects() -> None:
    from app.services.source_library.provider_ports import CrawlerOutputIngestResult
    from app.successor_runtime.capabilities.source_contracts import (
        ReadbackTerminal,
        ReadbackWaiting,
    )

    initial = ReadbackWaiting(attempt_ref="provider-attempt:attempt-explicit", observed_at="2026-10-08T00:00:00Z")
    events: list[str] = []

    class Provider:
        def dispatch(self, request):
            events.append("dispatch")
            return CrawlerDispatchResult("scrapy", "queued", "job-1", terminal_readback=initial)

        def poll(self, **options):
            events.append("poll")
            assert options == {
                "external_job_id": "job-1",
                "project": "demo_proj",
                "spider": "news_spider",
                "options": {"attempt_id": "attempt-explicit", "idempotency_key": "key-explicit"},
            }
            return {"provider_status": "completed", "observed_at": "2026-10-08T00:01:00Z"}

    ingest = CrawlerOutputIngestResult("ingested", {"import_result": {"inserted": "1", "updated": 2, "skipped": 3}})
    terminal_to_plain = ReadbackTerminal.to_plain
    ingest_to_plain = CrawlerOutputIngestResult.to_plain
    with (
        patch.object(
            ReadbackWaiting, "to_plain", autospec=True, side_effect=ReadbackWaiting.to_plain
        ) as waiting_projection,
        patch.object(ReadbackTerminal, "to_plain", autospec=True, side_effect=terminal_to_plain) as terminal_projection,
        patch.object(
            CrawlerOutputIngestResult, "to_plain", autospec=True, side_effect=ingest_to_plain
        ) as ingest_projection,
    ):

        def ingest_effect(request):
            events.append("ingest")
            assert waiting_projection.call_count == terminal_projection.call_count == ingest_projection.call_count == 0
            assert (request.wait_timeout_seconds, request.poll_interval_seconds, request.max_items) == (1.0, 5.0, 1000)
            return ingest

        with patch("app.services.source_library.runner.ingest_crawler_output", side_effect=ingest_effect):
            result = _run_crawler_provider(
                Provider(),
                params={
                    "output_ingest": {
                        "enabled": True,
                        "wait_timeout_seconds": -5,
                        "poll_interval_seconds": 20,
                        "max_items": 5000,
                    }
                },
            )
        assert waiting_projection.call_count == 0
        assert terminal_projection.call_count == ingest_projection.call_count == 1
    assert events == ["dispatch", "ingest", "poll"]
    assert result["status"] == "completed"
    assert (result["inserted"], result["updated"], result["skipped"]) == (1, 2, 3)
    assert result["readback"] is result["terminal_readback"]
    assert result["terminal_readback"]["readback"]["terminal_status"] == "COMPLETED"
    assert result["reconciliation"] == {
        "required": False,
        "state": "terminal_readback",
        "derived_as": "none",
        "durability": "not_configured",
    }


@pytest.mark.parametrize("provider_status, expected", [("completed", "accepted"), ("unknown", "failed")])
def test_dispatch_ack_and_unknown_survive_unavailable_poll(provider_status: str, expected: str) -> None:
    class Provider:
        def dispatch(self, request):
            return CrawlerDispatchResult("scrapy", provider_status, "job-1")

        def poll(self, **options):
            raise RuntimeError("poll unavailable")

    result = _run_crawler_provider(Provider())
    assert result["status"] == expected
    assert result["dispatch_acknowledged"] is (provider_status == "completed")
    assert result["terminal_readback"] is None
    assert result["reconciliation"]["state"] == ("not_attempted" if provider_status == "completed" else "unknown")


@pytest.mark.parametrize("legacy_method", [False, True])
@pytest.mark.parametrize("terminal_status, expected", [("COMPLETED", "completed"), ("CANCELLED", "failed")])
def test_legacy_terminal_observation_controls_poll_and_status(
    legacy_method: bool,
    terminal_status: str,
    expected: str,
) -> None:
    payload = {"kind": "terminal", "readback": {"terminal_status": terminal_status}}
    projections: list[str] = []

    class LegacyReadback:
        def to_plain(self):
            projections.append("legacy")
            return payload

    class Provider:
        def dispatch(self, request):
            return CrawlerDispatchResult(
                "scrapy",
                "unknown",
                "job-1",
                terminal_readback=LegacyReadback() if legacy_method else payload,
            )

        def poll(self, **options):
            pytest.fail("a present legacy observation must suppress the initial poll")

    result = _run_crawler_provider(Provider())
    assert result["status"] == expected
    assert result["readback"] == payload
    assert result["readback"] is result["terminal_readback"]
    assert projections == (["legacy"] if legacy_method else [])
    assert result["reconciliation"]["state"] == "terminal_readback"
    assert result["errors"] == ([] if expected == "completed" else ["crawler provider terminal status: cancelled"])


def test_legacy_readback_exception_keeps_initial_and_poll_boundaries() -> None:
    class LegacyReadback:
        def to_plain(self):
            raise ValueError("legacy conversion failed")

    class Provider:
        def dispatch(self, request):
            return CrawlerDispatchResult("scrapy", "queued", "job-1", terminal_readback=LegacyReadback())

        def poll(self, **options):
            return {"provider_status": "queued"}

    with pytest.raises(ValueError, match="legacy conversion failed"):
        _run_crawler_provider(Provider())

    class PollProvider(Provider):
        def dispatch(self, request):
            return CrawlerDispatchResult("scrapy", "queued", "job-1")

    with patch("app.services.source_library.runner.typed_crawler_readback", return_value=LegacyReadback()):
        result = _run_crawler_provider(PollProvider())
    assert result["status"] == "accepted"
    assert result["terminal_readback"] is None


@pytest.mark.parametrize("kind", ["exception", "failure", "foreign_failure", "noncanonical"])
def test_dispatch_failure_fields_and_identity_remain_exact(kind: str) -> None:
    from mrw_functorial_kit.core.application_failure_semantics import source_library_contract_failures
    from mrw_functorial_kit.core.provider_port_failures import crawler_runtime_failures

    class Provider:
        def dispatch(self, request):
            if kind == "exception":
                raise RuntimeError("transport unavailable")
            if kind == "failure":
                return crawler_runtime_failures.fail("scrapyd_transport", "transport failed", {})
            if kind == "foreign_failure":
                return source_library_contract_failures.fail("required_params_missing", "foreign failure", {})
            return {"provider_status": "completed"}

    result = _run_crawler_provider(Provider())
    assert result["status"] == "failed"
    assert result["errors"][0]["family"] == crawler_runtime_failures.name
    assert result["errors"][0]["code"] == (
        "scrapyd_response_invalid" if kind == "noncanonical" else "scrapyd_transport"
    )
    assert result["execution_policy"] == {"timeout": 7}
    assert result["runtime_channel"]["runtime_scope"] == "project_config"
    if kind == "noncanonical":
        assert not {"attempt_id", "idempotency_key", "reconciliation"} & result.keys()
    else:
        assert result["attempt_id"] == "attempt-explicit"
        assert result["idempotency_key"] == "key-explicit"
        assert result["reconciliation"]["state"] == "unknown"
        assert result["reconciliation"]["required"] is False


def test_invalid_explicit_attempt_store_fails_before_dispatch() -> None:
    provider = SimpleNamespace(dispatch=lambda _request: pytest.fail("invalid store must block dispatch"))
    result = _run_crawler_provider(provider, params={"durable_store": object()})
    assert result["errors"][0]["context"]["reason_code"] == "attempt_store_unavailable"
    assert result["reconciliation"] == {
        "required": True,
        "state": "unknown",
        "derived_as": "durable_attempt_store",
        "durability": "injected_repository",
    }


@pytest.mark.parametrize("invalid_option", [False, True])
def test_ingest_failure_precedes_terminal_completion_and_keeps_effect_boundary(invalid_option: bool) -> None:
    from app.successor_runtime.capabilities.source_contracts import AuthoritativeProviderReadback, ReadbackTerminal

    class Provider:
        def dispatch(self, request):
            return CrawlerDispatchResult(
                "scrapy",
                "queued",
                "job-1",
                terminal_readback=ReadbackTerminal(
                    AuthoritativeProviderReadback(
                        "provider-attempt:attempt-explicit", "job-1", "COMPLETED", "receipt-1", "now"
                    )
                ),
            )

    with patch(
        "app.services.source_library.runner.ingest_crawler_output", side_effect=RuntimeError("ingest unavailable")
    ) as ingest:
        result = _run_crawler_provider(
            Provider(),
            params={
                "output_ingest": {
                    "enabled": True,
                    "wait_timeout_seconds": [1] if invalid_option else 0,
                }
            },
        )
    assert result["status"] == "failed"
    assert result["terminal_readback"]["kind"] == "terminal"
    assert len(result["errors"]) == 1
    if invalid_option:
        ingest.assert_not_called()
        assert "crawler option 'output_ingest.wait_timeout_seconds' must be numeric" in result["errors"][0]
    else:
        ingest.assert_called_once()
        assert ingest.call_args.args[0].wait_timeout_seconds == 120.0
        assert result["errors"] == ["crawler output ingest failed: ingest unavailable"]


def test_malformed_terminal_observation_fails_before_output_ingest() -> None:
    from app.successor_runtime.capabilities.source_contracts import ReadbackTerminal

    class Provider:
        def dispatch(self, request):
            return CrawlerDispatchResult("scrapy", "queued", "job-1", terminal_readback=ReadbackTerminal(None))

    with patch("app.services.source_library.runner.ingest_crawler_output") as ingest:
        with pytest.raises(AttributeError, match="to_plain"):
            _run_crawler_provider(Provider(), params={"output_ingest": {"enabled": True}})
    ingest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
