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

        def _fake_collect(urls, *, project_key=None, query_terms=None, extra_params=None, enable_extraction=True):
            captured["urls"] = list(urls)
            captured["project_key"] = project_key
            captured["query_terms"] = list(query_terms or [])
            captured["extra_params"] = dict(extra_params or {})
            captured["enable_extraction"] = bool(enable_extraction)
            return {"inserted": 1, "inserted_valid": 1, "skipped": 0, "queued": 0}

        with patch("app.services.ingest.url_pool.collect_urls_from_list", side_effect=_fake_collect), patch.object(
            news_module, "current_project_key", return_value="demo_proj"
        ):
            result = news_module._dispatch_links_via_source_library_frontdoor(
                links=["https://example.com/news/1"],
                query_terms=["market"],
            )

        self.assertEqual(result.get("inserted"), 1)
        self.assertEqual(captured["project_key"], "demo_proj")
        self.assertEqual(captured["query_terms"], ["market"])
        self.assertTrue(captured["enable_extraction"])
        self.assertEqual(captured["extra_params"].get("url_routing_frontdoor_enabled"), True)
        self.assertEqual(captured["extra_params"].get("front_door_owner"), "ingest.news")
        self.assertEqual(captured["extra_params"].get("frontdoor_route_decision"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_write_mode"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_execution_mode"), "url_routing")

    def test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer(self):
        captured: dict = {}

        def _fake_route(**kwargs):
            captured["item"] = dict(kwargs["item"])
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
                    "writer_result": {"doc_id": 42, "inserted": 1, "skipped": 0},
                },
                "meta": {"reason_code": "ok"},
            }

        with patch("app.services.source_library.resolver.list_effective_channels", return_value=[{"channel_key": "url_pool"}]), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            side_effect=_fake_route,
        ), patch(
            "app.services.ingest.postprocess_frontdoor.run_postprocess_frontdoor",
            side_effect=_fake_postprocess,
        ):
            result = url_pool_module.ingest_url_via_source_library_frontdoor(
                url="https://example.com/article",
                project_key=None,
                query_terms=["market"],
                frontdoor_options={"route_hint": "static_detail", "prefer_crawler": True},
                enable_extraction=False,
            )

        self.assertEqual(captured["item"]["item_key"], "url_pool.single_url_compat")
        self.assertEqual(captured["item"]["channel_key"], "url_pool")
        self.assertEqual(captured["item"]["extra"]["managed_by"], "single_url_compat")
        self.assertEqual(captured["execution_layer"], "terminal_output_only")
        self.assertEqual(captured["params"]["urls"], ["https://example.com/article"])
        self.assertEqual(captured["params"]["query_terms"], ["market"])
        self.assertEqual(captured["params"]["prefer_crawler_first"], True)
        self.assertEqual(captured["params"]["force_url_routing_flow"], False)
        self.assertEqual(captured["params"]["frontdoor_route_hint"], "static_detail")

        ingress = captured["ingress"]
        self.assertEqual(ingress["ingress_type"], "source_library")
        self.assertEqual(ingress["entrypoint"], "ingest.url_pool")
        self.assertEqual(ingress["source_mode"], "url_execution")
        self.assertEqual(ingress["collection_payload"]["document_candidate"]["uri"], "https://example.com/article")
        self.assertEqual(ingress["collection_payload"]["extraction_plan"]["enabled"], False)
        self.assertEqual(captured["run_writer"], True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["inserted_valid"], 1)
        self.assertEqual(result["document_id"], 42)
        self.assertEqual(result["single_write_workflow"], "source_library_frontdoor")
        self.assertEqual(result["source_library_collect_only"], True)

    def test_market_web_routed_fetch_enables_frontdoor_and_passes_route_context(self):
        captured: dict = {}

        def _fake_collect(urls, *, project_key=None, query_terms=None, extra_params=None, enable_extraction=True):
            captured["urls"] = list(urls)
            captured["project_key"] = project_key
            captured["query_terms"] = list(query_terms or [])
            captured["extra_params"] = dict(extra_params or {})
            captured["enable_extraction"] = bool(enable_extraction)
            return {"inserted": 0, "inserted_valid": 0, "skipped": 1, "queued": 0}

        with patch.object(market_web_module, "start_job", return_value=1), patch.object(
            market_web_module, "complete_job"
        ), patch.object(
            market_web_module, "search_sources", return_value=[{"link": "https://example.com/post/1", "title": "t", "snippet": "s"}]
        ), patch.object(
            market_web_module, "fetch_html", return_value=("<html><body></body></html>", None)
        ), patch.object(
            market_web_module, "_extract_text_from_html", return_value=""
        ), patch.object(
            market_web_module, "SessionLocal", return_value=_FakeSession()
        ), patch.object(
            market_web_module, "_get_or_create_source", return_value=SimpleNamespace(id=123)
        ), patch.object(
            market_web_module, "collect_urls_from_list", side_effect=_fake_collect
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
        self.assertEqual(captured["project_key"], "demo_proj")
        self.assertEqual(captured["query_terms"], ["ev"])
        self.assertEqual(captured["enable_extraction"], False)
        self.assertEqual(captured["extra_params"].get("url_routing_frontdoor_enabled"), True)
        self.assertEqual(captured["extra_params"].get("front_door_owner"), "ingest.market_web")
        self.assertEqual(captured["extra_params"].get("frontdoor_route_decision"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_write_mode"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_execution_mode"), "url_routing")

    def test_collect_urls_from_pool_preserves_target_specific_search_contracts(self):
        captured: list[dict] = []
        targets = [
            {
                "url": "https://alpha.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "alpha.example",
                "from_url": "https://alpha.example/search?q={{q}}",
                "is_site_seed": True,
                "source_search_contract": {
                    "param_key": "term",
                    "max_candidates": 2,
                    "min_results_required": 2,
                },
            },
            {
                "url": "https://beta.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "beta.example",
                "from_url": "https://beta.example/search?q={{q}}",
                "is_site_seed": True,
                "source_search_contract": {
                    "param_key": "query",
                    "max_candidates": 5,
                    "min_results_required": 5,
                },
            },
        ]
        pool_items = [
            {"url": "https://alpha.example/search?q={{q}}", "scope": "effective", "source": "alpha"},
            {"url": "https://beta.example/search?q={{q}}", "scope": "effective", "source": "beta"},
        ]

        def _fake_frontdoor_ingress(**kwargs):
            captured.append(
                {
                    "url": kwargs["url"],
                    "search_options": dict(kwargs.get("search_options") or {}),
                    "frontdoor_options": dict(kwargs.get("frontdoor_options") or {}),
                }
            )
            return {
                "status": "degraded_success",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "rejected_count": 0,
                "rejection_breakdown": {},
                "degradation_flags": ["empty_records"],
                "document_id": None,
                "quality_score": 0.0,
            }

        def _fake_unwrap(url, *, enable_network_redirect=True):
            return SimpleNamespace(url=url, redirected=False, network_attempted=enable_network_redirect)

        with patch.object(url_pool_module, "list_urls", return_value=(pool_items, len(pool_items))), patch.object(
            url_pool_module, "_resolve_runtime_targets", return_value=(targets, "site_only")
        ), patch.object(url_pool_module, "unwrap_url", side_effect=_fake_unwrap), patch.object(
            url_pool_module, "is_ingest_frontdoor_enabled", return_value=True
        ), patch.object(
            url_pool_module, "start_job", return_value=101
        ), patch.object(
            url_pool_module, "complete_job"
        ), patch.object(
            url_pool_module, "_run_source_library_frontdoor_ingress", side_effect=_fake_frontdoor_ingress
        ):
            result = url_pool_module.collect_urls_from_pool(
                project_key="demo_proj",
                query_terms=["robotics"],
                extra_params={
                    "url_routing_frontdoor_enabled": True,
                    "url_parallel_workers": 1,
                    "url_parallel_batch_size": 1,
                },
            )

        self.assertEqual(result["debug"]["target_mode"], "site_only")
        self.assertEqual(result["debug"]["frontdoor_enabled"], True)
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]["search_options"]["source_search_contract"]["param_key"], "term")
        self.assertEqual(captured[0]["search_options"]["target_candidates"], 2)
        self.assertEqual(captured[0]["frontdoor_options"]["route_hint"], "search_shell")
        self.assertEqual(captured[1]["search_options"]["source_search_contract"]["param_key"], "query")
        self.assertEqual(captured[1]["search_options"]["target_candidates"], 5)
        self.assertEqual(captured[1]["frontdoor_options"]["route_hint"], "search_shell")

    def test_high_js_frontdoor_route_prefers_browser_render_and_projects_dashboard_status(self):
        captured: dict = {}

        def _fake_frontdoor_ingress(**kwargs):
            captured["url"] = kwargs["url"]
            captured["search_options"] = dict(kwargs.get("search_options") or {})
            captured["frontdoor_options"] = dict(kwargs.get("frontdoor_options") or {})
            return {
                "status": "degraded_success",
                "reason_code": "source_library_fetch_empty",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "rejected_count": 0,
                "rejection_breakdown": {},
                "degradation_flags": ["empty_records"],
                "document_id": None,
                "quality_score": 0.0,
                "frontdoor_route": {
                    "contract_version": "ingest.frontdoor_route_profile.v1",
                    "route_hint": "crawler_browse",
                    "fetch_strategy": "browser_render",
                    "render_required": True,
                    "prefer_crawler_first": True,
                    "force_url_routing_flow": False,
                },
                "postprocess_frontdoor": {
                    "data": {"admission": "defer"},
                    "meta": {"reason_code": "deferred", "retryable": False},
                },
            }

        with patch.object(url_pool_module, "is_ingest_frontdoor_enabled", return_value=True), patch.object(
            url_pool_module, "start_job", return_value=202
        ), patch.object(url_pool_module, "complete_job"), patch.object(
            url_pool_module, "_run_source_library_frontdoor_ingress", side_effect=_fake_frontdoor_ingress
        ):
            result = url_pool_module.collect_urls_from_list(
                ["https://x.com/search?q=robotics"],
                project_key="demo_proj",
                query_terms=["robotics"],
                extra_params={
                    "url_routing_frontdoor_enabled": True,
                    "disable_site_seed_expansion": True,
                    "url_parallel_workers": 1,
                    "url_parallel_batch_size": 1,
                },
            )

        self.assertEqual(captured["url"], "https://x.com/search?q=robotics")
        self.assertEqual(captured["search_options"]["frontdoor_route_hint"], "crawler_browse")
        self.assertEqual(captured["search_options"]["frontdoor_fetch_strategy"], "browser_render")
        self.assertTrue(captured["search_options"]["frontdoor_render_required"])
        self.assertTrue(captured["search_options"]["frontdoor_prefers_crawler"])
        self.assertTrue(captured["search_options"]["frontdoor_prefers_search_shell"])
        self.assertEqual(captured["frontdoor_options"]["route_hint"], "crawler_browse")
        self.assertEqual(captured["frontdoor_options"]["fetch_strategy"], "browser_render")
        self.assertTrue(captured["frontdoor_options"]["prefer_crawler"])
        self.assertTrue(captured["frontdoor_options"]["render_required"])

        status_summary = result["meta"]["frontdoor_status_summary"]
        self.assertEqual(status_summary["sample_size"], 1)
        self.assertEqual(status_summary["dashboard_status_counts"], {"degraded_success": 1})
        self.assertEqual(status_summary["admission_counts"], {"defer": 1})
        detail_status = result["debug"]["url_details"][0]["frontdoor_status"]
        self.assertEqual(detail_status["dashboard_status"], "degraded_success")
        self.assertEqual(detail_status["frontdoor_admission"], "defer")


if __name__ == "__main__":
    unittest.main()
