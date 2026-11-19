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
    from app.services.ingest import market_web as market_web_module
    from app.services.ingest import news as news_module
    from app.services.ingest import social as social_module
    from app.services.ingest import url_pool as url_pool_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, *_args, **_kwargs):
        return _FakeQuery()

    def add(self, *_args, **_kwargs):
        return None

    def flush(self):
        return None

    def commit(self):
        return None

    def expunge_all(self):
        return None


class IngestFrontdoorContextUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest frontdoor context tests require backend dependencies: {_IMPORT_ERROR}")

    def test_news_dispatch_links_via_source_library_frontdoor_enables_frontdoor_by_default(self):
        captured: dict = {}

        def _fake_collect(request):
            from app.services.collect_runtime.contracts import CollectResult

            captured["request"] = request
            return CollectResult(
                channel="url_pool",
                status="partial",
                inserted=1,
                meta={
                    "raw": {
                        "inserted": 1,
                        "inserted_valid": 1,
                        "skipped": 0,
                        "queued": 0,
                    }
                },
            )

        with patch("app.services.collect_runtime.runtime.run_collect", side_effect=_fake_collect), patch.object(
            news_module, "current_project_key", return_value="demo_proj"
        ):
            result = news_module._dispatch_links_via_source_library_frontdoor(
                links=["https://example.com/news/1"],
                query_terms=["market"],
            )

        self.assertEqual(result.get("inserted"), 1)
        request = captured["request"]
        self.assertEqual(request.channel, "url_pool")
        self.assertEqual(request.urls, ["https://example.com/news/1"])
        self.assertEqual(request.project_key, "demo_proj")
        self.assertEqual(request.query_terms, ["market"])
        self.assertTrue(request.options["enable_extraction"])
        self.assertEqual(request.options.get("front_door_owner"), "ingest.news")
        self.assertEqual(request.options.get("frontdoor_route_decision"), "front_door_url_routing")
        self.assertEqual(request.options.get("frontdoor_write_mode"), "front_door_url_routing")
        self.assertEqual(request.options.get("frontdoor_execution_mode"), "url_routing")

    def test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer(self):
        captured: dict = {}

        def _fake_route(**kwargs):
            captured["protocol"] = kwargs["protocol"]
            captured["params"] = dict(kwargs["params"])
            captured["execution_layer"] = kwargs["execution_layer"]
            return {
                "records": [
                    {
                        "url": "https://example.com/article",
                        "title": "Example article",
                        "content_text": "Meaningful market article body with enough detail for the frontdoor writer.",
                        "summary": "Meaningful market article body",
                        "source_label": "url_pool",
                        "record_meta": {"http_status": 200},
                    }
                ],
                "errors": [],
                "by_url": [{"url": "https://example.com/article", "status": "ok"}],
            }

        def _fake_postprocess(*, ingress_envelope, run_writer):
            captured["ingress"] = dict(ingress_envelope)
            captured["run_writer"] = run_writer
            return {
                "status": "ok",
                "data": {
                    "admission": "accept",
                    "writer_result": {"material_id": 42, "inserted": 1, "skipped": 0},
                },
                "meta": {"reason_code": "ok"},
            }

        with patch("app.services.source_library.resolver.list_effective_channels", return_value=[{"channel_key": "url_pool"}]), patch(
            "app.services.source_library.orchestrators.url_execution.fetch_routed_targets",
            side_effect=_fake_route,
        ), patch(
            "app.services.ingest.postprocess_frontdoor.run_postprocess_frontdoor",
            side_effect=_fake_postprocess,
        ):
            result = url_pool_module.ingest_url_via_source_library_frontdoor(
                url="https://example.com/article",
                project_key=None,
                query_terms=["market"],
                strict_mode=True,
                frontdoor_options={"route_hint": "static_detail", "prefer_crawler": True},
                enable_extraction=False,
            )

        protocol = captured["protocol"]
        self.assertEqual(protocol.item_key, "url_pool")
        self.assertEqual(protocol.item_channel_key, "url_pool")
        self.assertEqual(protocol.candidate_urls, ["https://example.com/article"])
        self.assertNotIn("single_url_compat", protocol.to_dict())
        self.assertEqual(captured["execution_layer"], "terminal_output_only")
        self.assertEqual(captured["params"]["urls"], ["https://example.com/article"])
        self.assertEqual(captured["params"]["query_terms"], ["market"])
        self.assertEqual(captured["params"]["strict_mode"], True)
        self.assertEqual(captured["params"]["prefer_crawler_first"], True)
        self.assertEqual(captured["params"]["force_url_routing_flow"], False)
        self.assertEqual(captured["params"]["frontdoor_route_hint"], "static_detail")

        ingress = captured["ingress"]
        self.assertEqual(ingress["ingress_type"], "source_library")
        self.assertEqual(ingress["entrypoint"], "ingest.url_pool")
        self.assertEqual(ingress["source_mode"], "url_execution")
        self.assertEqual(ingress["source_ref"]["url"], "https://example.com/article")
        self.assertEqual(ingress["source_ref"]["locator"], "https://example.com/article")
        self.assertEqual(ingress["source_ref"]["domain"], "example.com")
        self.assertEqual(ingress["source_ref"]["ingress_type"], "source_library")
        self.assertEqual(ingress["source_ref"]["source_mode"], "url_execution")
        self.assertEqual(ingress["collection_payload"]["material_candidate"]["uri"], "https://example.com/article")
        self.assertEqual(ingress["collection_payload"]["terminal_context"]["strict_mode"], True)
        self.assertEqual(ingress["collection_payload"]["extraction_plan"]["enabled"], False)
        self.assertEqual(captured["run_writer"], True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["inserted_valid"], 1)
        self.assertEqual(result["material_id"], 42)
        self.assertEqual(result["single_write_workflow"], "source_library_frontdoor")
        self.assertEqual(result["source_library_collect_only"], True)

    def test_market_web_routed_fetch_enables_frontdoor_and_passes_route_context(self):
        captured: dict = {}

        def _fake_collect(request):
            from app.services.collect_runtime.contracts import CollectResult

            captured["request"] = request
            return CollectResult(
                channel="url_pool",
                status="partial",
                skipped=1,
                meta={
                    "raw": {
                        "inserted": 0,
                        "inserted_valid": 0,
                        "skipped": 1,
                        "queued": 0,
                    }
                },
            )

        def _fake_search_and_ingest(spec, ports):
            missing_url = "https://example.com/post/1"
            routed = ports.route_missing([missing_url])
            return SimpleNamespace(
                routed=routed,
                inserted=0,
                skipped=0,
                links=(missing_url,),
                missing_urls=(missing_url,),
            )

        with patch.object(market_web_module, "start_job", return_value=1), patch.object(
            market_web_module, "complete_job"
        ), patch.object(
            market_web_module, "run_search_and_ingest", side_effect=_fake_search_and_ingest
        ), patch.object(
            market_web_module, "SessionLocal", return_value=_FakeSession()
        ), patch.object(
            market_web_module, "_get_or_create_source", return_value=SimpleNamespace(id=123)
        ), patch(
            "app.services.collect_runtime.runtime.run_collect", side_effect=_fake_collect
        ), patch.object(
            market_web_module, "current_project_key", return_value="demo_proj"
        ), patch.object(
            market_web_module, "build_display_meta", return_value={}
        ):
            result = market_web_module.collect_market_info(
                keywords=["ev"],
                limit=1,
                enable_extraction=False,
            )

        self.assertEqual(result.get("body_fetch_routed_urls"), 1)
        request = captured["request"]
        self.assertEqual(request.channel, "url_pool")
        self.assertEqual(request.urls, ["https://example.com/post/1"])
        self.assertEqual(request.project_key, "demo_proj")
        self.assertEqual(request.query_terms, ["ev"])
        self.assertEqual(request.options["enable_extraction"], False)
        self.assertEqual(request.options.get("front_door_owner"), "ingest.market_web")
        self.assertEqual(request.options.get("frontdoor_route_decision"), "front_door_url_routing")
        self.assertEqual(request.options.get("frontdoor_write_mode"), "front_door_url_routing")
        self.assertEqual(request.options.get("frontdoor_execution_mode"), "url_routing")

    def test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures(self):
        with self.assertRaisesRegex(TypeError, "requires mapping"):
            social_module._as_str_object_dict([])
        with self.assertRaisesRegex(TypeError, "requires string keys"):
            social_module._as_str_object_dict({1: "value"})
        with self.assertRaisesRegex(TypeError, "requires string name"):
            social_module._required_str({"name": None}, "name")
        with self.assertRaisesRegex(TypeError, "requires optional string label"):
            social_module._optional_str({"label": 1}, "label")
        with self.assertRaisesRegex(TypeError, "requires mapping details"):
            social_module._required_str_object_dict({"details": None}, "details")
        with self.assertRaisesRegex(TypeError, "not convertible to integer"):
            social_module._as_count(object())

    def test_url_pool_dynamic_database_ports_reject_incompatible_bindings(self):
        with patch.object(
            url_pool_module,
            "import_module",
            return_value=SimpleNamespace(SessionLocal=object()),
        ):
            with self.assertRaisesRegex(TypeError, "SessionLocal has an incompatible"):
                url_pool_module._open_session()
        with patch.object(
            url_pool_module,
            "import_module",
            return_value=SimpleNamespace(list_urls=object()),
        ):
            with self.assertRaisesRegex(TypeError, "list_urls has an incompatible"):
                url_pool_module.list_urls()

if __name__ == "__main__":
    unittest.main()
