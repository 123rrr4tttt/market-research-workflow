from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.collect_runtime.adapters.source_library import to_source_library_response
from app.services.collect_runtime.adapters import source_library as source_library_adapter_module
from app.services.collect_runtime.contracts import CollectResult
from app.services.collect_runtime.runtime import collect_request_from_source_library_api


class CollectRuntimeSourceLibraryAdapterUnitTestCase(unittest.TestCase):
    def test_collect_request_from_source_library_api_uses_shared_runtime_param_parser(self) -> None:
        request = collect_request_from_source_library_api(
            item_key="ai_terminal.weekly",
            project_key="demo_proj",
            override_params={
                "query_terms": ["ai terminal"],
                "urls": ["https://example.com/a", "invalid"],
                "max_items": 3,
                "provider": "Google",
                "language": "ZH",
                "scope": "project",
                "platforms": ["web", "rss"],
                "source_mode": "site_search",
            },
        )

        self.assertEqual(request.item_key, "ai_terminal.weekly")
        self.assertEqual(request.project_key, "demo_proj")
        self.assertEqual(request.query_terms, ["ai terminal"])
        self.assertEqual(request.urls, ["https://example.com/a"])
        self.assertEqual(request.limit, 3)
        self.assertEqual(request.provider, "google")
        self.assertEqual(request.language, "zh")
        self.assertEqual(request.scope, "project")
        self.assertEqual(request.platforms, ["web", "rss"])
        self.assertEqual(request.options["override_params"]["source_mode"], "site_search")

    def test_to_source_library_response_keeps_legacy_fields_and_adds_dual_track_when_raw_is_dict(self) -> None:
        raw = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "params": {"query_terms": ["alpha"]},
            "result": {
                "records": [
                    {
                        "record_id": "r1",
                        "url": "https://example.com/a",
                        "title": "Alpha",
                        "content_text": "alpha text",
                    }
                ],
                "errors": [],
            },
            "display_meta": {"summary": "raw-display"},
        }
        collect_result = CollectResult(
            channel="source_library",
            inserted=99,
            updated=99,
            skipped=99,
            errors=[{"message": "ignored"}],
            meta={"raw": raw},
            display_meta={"summary": "collect-display"},
        )

        response = to_source_library_response(collect_result)

        self.assertEqual(response["item_key"], raw["item_key"])
        self.assertEqual(response["channel_key"], raw["channel_key"])
        self.assertEqual(response["params"], raw["params"])
        self.assertEqual(response["result"], raw["result"])
        self.assertEqual(response["display_meta"], raw["display_meta"])

        self.assertIn("terminal_output", response)
        terminal_output = response["terminal_output"]
        self.assertEqual(terminal_output["contract_version"], "source_library.terminal_output.v1")
        self.assertEqual(terminal_output["status"], "ok")
        self.assertEqual(terminal_output["source_mode"], "site_search")
        self.assertEqual(len(terminal_output["results"]["records"]), 1)
        self.assertEqual(terminal_output["results"]["records"][0]["url"], "https://example.com/a")
        self.assertEqual(terminal_output["errors"], [])
        self.assertEqual(terminal_output["results"]["stats"]["normalized"], 1)
        self.assertEqual(terminal_output["item"]["item_key"], raw["item_key"])
        self.assertNotIn("channel_key", terminal_output["item"])
        self.assertNotIn("source_params", terminal_output["request"])
        self.assertEqual(terminal_output["raw_snapshot"]["result"]["records"][0]["record_id"], "r1")
        self.assertEqual(response["frontdoor_ingress"]["contract_version"], "frontdoor.ingress.v1")
        self.assertEqual(response["frontdoor_ingress"]["ingress_type"], "source_library")
        self.assertEqual(response["postprocess_frontdoor"]["data"]["admission"], "defer")
        self.assertEqual(response["postprocess_frontdoor"]["data"]["dispatch_plan"]["run_writer"], False)
        self.assertEqual(response["authority_output"]["contract_version"], "source_library.authority_output.v1")
        self.assertEqual(response["authority_output"]["summary"]["record_stats"]["normalized"], 1)
        self.assertEqual(response["authority_output"]["summary"]["handoff"]["admission"], "defer")
        self.assertEqual(response["compat_projection"]["contract_version"], "source_library.compat_projection.v1")
        self.assertTrue(response["compat_projection"]["deprecated"])
        self.assertEqual(response["compat_projection"]["legacy_result"]["item_key"], raw["item_key"])

        self.assertIn("legacy_result", response)
        self.assertEqual(response["legacy_result"], raw)

    def test_to_source_library_response_builds_complete_terminal_output_on_fallback_path(self) -> None:
        collect_result = CollectResult(
            channel="source_library",
            inserted=3,
            updated=4,
            skipped=5,
            errors=[{"message": "e1"}, {"message": "e2"}],
            meta={"raw": "non-dict-raw"},
            display_meta={"summary": "collect-display"},
        )

        response = to_source_library_response(collect_result)

        self.assertEqual(response["item_key"], None)
        self.assertEqual(response["channel_key"], None)
        self.assertEqual(response["params"], {})
        self.assertEqual(response["result"], {"inserted": 3, "updated": 4, "skipped": 5, "errors": ["e1", "e2"]})
        self.assertEqual(response["display_meta"], {"summary": "collect-display"})

        terminal_output = response.get("terminal_output") or {}
        self.assertEqual(terminal_output["contract_version"], "source_library.terminal_output.v1")
        self.assertEqual(terminal_output["status"], "error")
        self.assertEqual(terminal_output["source_mode"], "protocol_search")
        self.assertEqual(terminal_output["results"]["records"], [])
        self.assertEqual(len(terminal_output["errors"]), 2)
        self.assertEqual(terminal_output["results"]["stats"]["normalized"], 0)
        self.assertEqual(terminal_output["results"]["stats"]["dropped"], 0)
        self.assertEqual(terminal_output["meta"]["reason_code"], "fetch_errors")
        self.assertNotIn("channel_key", terminal_output["item"])
        self.assertNotIn("source_params", terminal_output["request"])
        self.assertEqual(terminal_output["raw_snapshot"]["result"]["inserted"], 3)
        self.assertEqual(response["frontdoor_ingress"]["contract_version"], "frontdoor.ingress.v1")
        self.assertEqual(response["postprocess_frontdoor"]["data"]["admission"], "reject")
        self.assertEqual(response["authority_output"]["summary"]["write_effects"]["inserted"], 3)
        self.assertEqual(response["authority_output"]["summary"]["write_effects"]["updated"], 4)
        self.assertEqual(response["authority_output"]["summary"]["write_effects"]["skipped"], 5)
        self.assertFalse(response["authority_output"]["summary"]["bootstrap_required"])
        self.assertEqual(response["compat_projection"]["status"], "retained_compat")

        self.assertIn("legacy_result", response)
        self.assertEqual(response["legacy_result"]["display_meta"], {"summary": "collect-display"})

    def test_to_source_library_response_uses_shared_ingress_builders(self) -> None:
        collect_result = CollectResult(
            channel="source_library",
            inserted=1,
            updated=0,
            skipped=0,
            meta={
                "raw": {
                    "item_key": "handler.cluster.search_template",
                    "channel_key": "handler.cluster",
                    "params": {"query_terms": ["alpha"]},
                    "result": {
                        "records": [
                            {
                                "record_id": "r1",
                                "url": "https://example.com/a",
                                "title": "Alpha",
                                "content_text": "alpha text",
                            }
                        ],
                        "errors": [],
                    },
                }
            },
        )

        with patch.object(
            source_library_adapter_module,
            "build_source_library_ingress_envelope",
            return_value={"contract_version": "frontdoor.ingress.v1", "meta": {"reason_code": "ok"}},
        ) as ingress_mock, patch.object(
            source_library_adapter_module,
            "run_postprocess_frontdoor",
            return_value={"status": "ok", "data": {"admission": "defer"}, "meta": {"reason_code": "deferred"}},
        ) as postprocess_mock:
            response = to_source_library_response(collect_result)

        ingress_mock.assert_called_once()
        postprocess_mock.assert_called_once()
        self.assertEqual(response["frontdoor_ingress"]["contract_version"], "frontdoor.ingress.v1")
        self.assertEqual(response["postprocess_frontdoor"]["data"]["admission"], "defer")
        self.assertEqual(response["legacy_result"]["item_key"], "handler.cluster.search_template")
        self.assertEqual(response["authority_output"]["frontdoor_ingress"]["contract_version"], "frontdoor.ingress.v1")

    def test_to_source_library_response_propagates_external_manifest_summary(self) -> None:
        raw = {
            "item_key": "external.demo.item",
            "channel_key": "external_project.manifest",
            "name": "External Demo Item",
            "item_type": "user_defined",
            "managed_by": "user",
            "extra": {
                "external_project_manifest": {
                    "contract_version": "external_item.manifest.v1",
                    "item_key": "external.demo.item",
                    "display_name": "External Demo Item",
                    "project_link": "https://github.com/example/external-demo",
                    "source_kind": "feed_aggregator",
                    "source_scope": "finance_news",
                    "capabilities": {
                        "candidate_urls": True,
                        "article_metadata": True,
                        "article_body": False,
                        "pdf_artifact": False,
                    },
                    "accepted_inputs": {
                        "query_terms": True,
                        "urls": False,
                        "domains": False,
                        "date_range": False,
                        "max_items": True,
                    },
                    "execution_mode": "rss_feed",
                    "runner_ref": "https://example.com/feed.xml",
                    "normalization": {
                        "record_kind": "article_metadata",
                        "frontdoor_strategy": "records_only_defer",
                    },
                    "limits": {
                        "default_max_items": 20,
                        "max_items_cap": 100,
                        "request_timeout_ms": 30000,
                    },
                    "refresh_policy": {
                        "manifest_ttl_minutes": 60,
                        "probe_ttl_minutes": 1440,
                    },
                    "provenance": {
                        "discovered_by": "manual_registration",
                        "source_refs": ["https://github.com/example/external-demo"],
                    },
                }
            },
            "params": {"query_terms": ["alpha"]},
            "result": {
                "records": [
                    {
                        "record_id": "r1",
                        "url": "https://example.com/a",
                        "title": "Alpha",
                        "summary": "alpha summary",
                    }
                ],
                "errors": [],
            },
        }
        collect_result = CollectResult(channel="source_library", meta={"raw": raw})

        response = to_source_library_response(collect_result)

        self.assertEqual(
            response["terminal_output"]["item"]["external_manifest"]["project_link"],
            "https://github.com/example/external-demo",
        )
        self.assertEqual(response["frontdoor_ingress"]["source_ref"]["source_kind"], "feed_aggregator")
        self.assertEqual(response["frontdoor_ingress"]["source_ref"]["execution_mode"], "rss_feed")
        self.assertEqual(response["authority_output"]["summary"]["record_stats"]["normalized"], 1)

    def test_to_source_library_response_promotes_external_article_body_record_to_document_candidate(self) -> None:
        body = " ".join(["Materialized article body paragraph"] * 40)
        raw = {
            "item_key": "external.demo.article",
            "channel_key": "external_project.manifest",
            "name": "External Demo Article",
            "item_type": "user_defined",
            "managed_by": "user",
            "extra": {
                "external_project_manifest": {
                    "contract_version": "external_item.manifest.v1",
                    "item_key": "external.demo.article",
                    "display_name": "External Demo Article",
                    "project_link": "https://github.com/example/external-demo",
                    "source_kind": "article_extraction_stack",
                    "source_scope": "finance_news",
                    "capabilities": {
                        "candidate_urls": True,
                        "article_metadata": True,
                        "article_body": True,
                        "pdf_artifact": False,
                    },
                    "accepted_inputs": {
                        "query_terms": True,
                        "urls": True,
                        "domains": False,
                        "date_range": False,
                        "max_items": True,
                    },
                    "execution_mode": "article_extractor",
                    "runner_ref": "article-extractor://trafilatura-or-heuristic",
                    "normalization": {
                        "record_kind": "document_candidate",
                        "frontdoor_strategy": "records_allow_extract",
                    },
                    "limits": {
                        "default_max_items": 2,
                        "max_items_cap": 10,
                        "request_timeout_ms": 5000,
                    },
                    "refresh_policy": {
                        "manifest_ttl_minutes": 60,
                        "probe_ttl_minutes": 1440,
                    },
                    "provenance": {
                        "discovered_by": "manual_registration",
                        "source_refs": ["https://github.com/example/external-demo"],
                    },
                    "runtime_config": {"parser": "heuristic.main_content.v1"},
                }
            },
            "params": {"urls": ["https://example.com/article"]},
            "result": {
                "records": [
                    {
                        "record_id": "r1",
                        "url": "https://example.com/article",
                        "title": "Article",
                        "content_text": body,
                        "record_meta": {
                            "article_extraction": {
                                "contract_version": "external_project.article_body_extraction.v1",
                                "state": "article_body_extracted",
                                "content_chars": len(body),
                            }
                        },
                    }
                ],
                "errors": [],
            },
        }
        collect_result = CollectResult(channel="source_library", meta={"raw": raw})

        response = to_source_library_response(collect_result)

        payload = response["frontdoor_ingress"]["collection_payload"]
        self.assertEqual(payload["document_candidate"]["uri"], "https://example.com/article")
        self.assertEqual(payload["document_candidate"]["content"], body)
        self.assertEqual(payload["dispatch_plan"]["reason"], "external_project_article_body_materialized")
        self.assertFalse(payload["dispatch_plan"]["run_extraction"])
        self.assertFalse(payload["dispatch_plan"]["run_writer"])
        self.assertEqual(payload["terminal_context"]["article_extraction"]["state"], "article_body_extracted")
        self.assertEqual(response["frontdoor_ingress"]["source_ref"]["execution_mode"], "article_extractor")

    def test_to_source_library_response_preserves_provider_handoff_contract(self) -> None:
        provider_handoff = {
            "contract_version": "source_library.provider_handoff.v1",
            "handoff_kind": "crawler_provider",
            "channel_key": "crawler.demo_proj",
            "provider": "crawler",
            "provider_type": "scrapy",
            "provider_dispatch": "crawlers/providers",
            "downstream_handoff": "ingest",
            "execution_layer": "terminal_output_only",
            "route_hint": "crawler_browse",
            "fetch_strategy": "browser_render",
            "render_required": True,
            "prefer_crawler_first": True,
            "force_url_routing_flow": False,
            "provider_job_id": "job-high-js-1",
            "provider_status": "queued",
            "attempt_count": 1,
            "frontdoor_route_profile": {
                "contract_version": "ingest.frontdoor_route_profile.v1",
                "route_hint": "crawler_browse",
                "fetch_strategy": "browser_render",
                "domain": "x.com",
                "high_js": True,
                "render_required": True,
                "router_contract": {
                    "contract_version": "ingest.frontdoor_fetch_router.v1",
                    "tri_state_statuses": ["success", "degraded_success", "failed"],
                    "dashboard_status": "degraded_success",
                    "router_state": "needs_browser",
                    "route_hint": "crawler_browse",
                    "fetch_strategy": "browser_render",
                    "reason_code": "needs_browser_runtime",
                    "reason_category": "technical",
                    "retryable": False,
                    "render_required": True,
                    "high_js": True,
                    "search_like": True,
                    "fallback_boundary": {
                        "http_fetch_allowed": False,
                        "browser_fetch_required": True,
                        "crawler_provider_allowed": True,
                        "http_fetch_fallback_allowed": False,
                        "legacy_url_only_write_allowed": False,
                        "public_browser_replay_performed": False,
                        "boundary_reason": "body_only_after_fetch",
                    },
                    "diagnostics": {"source": "test"},
                },
            },
        }
        provider_handoff["router_contract"] = provider_handoff["frontdoor_route_profile"]["router_contract"]
        raw = {
            "item_key": "handler.cluster.high_js",
            "channel_key": "handler.cluster",
            "params": {
                "urls": ["https://x.com/search?q=robotics"],
                "query_terms": ["robotics"],
                "frontdoor_route_profile": provider_handoff["frontdoor_route_profile"],
            },
            "result": {
                "by_url": [
                    {
                        "url": "https://x.com/search?q=robotics",
                        "channel_key": "crawler.demo_proj",
                        "error": None,
                        "result": {
                            "status": "accepted",
                            "provider_type": "scrapy",
                            "provider_status": "queued",
                            "provider_job_id": "job-high-js-1",
                            "attempt_count": 1,
                        },
                        "provider_handoff": provider_handoff,
                        "frontdoor_route_profile": provider_handoff["frontdoor_route_profile"],
                    }
                ],
                "execution_request": {
                    "source_mode": "url_execution",
                    "project_key": "demo_proj",
                    "params": {
                        "urls": ["https://x.com/search?q=robotics"],
                        "query_terms": ["robotics"],
                        "frontdoor_route_profile": provider_handoff["frontdoor_route_profile"],
                        "frontdoor_router_contract": provider_handoff["router_contract"],
                    },
                },
            },
        }
        collect_result = CollectResult(channel="source_library", meta={"raw": raw})

        response = to_source_library_response(collect_result)

        terminal_meta = response["terminal_output"]["meta"]
        self.assertEqual(terminal_meta["provider_handoff"]["provider_type"], "scrapy")
        self.assertEqual(terminal_meta["provider_handoff"]["provider_job_id"], "job-high-js-1")
        self.assertEqual(terminal_meta["frontdoor_route_profile"]["fetch_strategy"], "browser_render")
        self.assertEqual(terminal_meta["frontdoor_router_contract"]["router_state"], "needs_browser")
        self.assertEqual(terminal_meta["frontdoor_router_contract"]["reason_code"], "needs_browser_runtime")

        frontdoor = response["frontdoor_ingress"]
        self.assertEqual(frontdoor["source_ref"]["provider_type"], "scrapy")
        self.assertEqual(frontdoor["source_ref"]["provider_dispatch"], "crawlers/providers")
        self.assertEqual(frontdoor["source_ref"]["frontdoor_route_hint"], "crawler_browse")
        self.assertEqual(frontdoor["source_ref"]["fetch_strategy"], "browser_render")
        self.assertEqual(frontdoor["source_ref"]["render_required"], "True")
        self.assertEqual(frontdoor["source_ref"]["router_state"], "needs_browser")
        self.assertEqual(frontdoor["source_ref"]["router_reason_code"], "needs_browser_runtime")
        self.assertEqual(frontdoor["collection_payload"]["provider_handoff"]["provider_job_id"], "job-high-js-1")
        self.assertEqual(frontdoor["collection_payload"]["frontdoor_route_profile"]["domain"], "x.com")
        self.assertEqual(frontdoor["collection_payload"]["frontdoor_router_contract"]["router_state"], "needs_browser")

        provider_summary = response["authority_output"]["summary"]["provider_handoff"]
        self.assertTrue(provider_summary["present"])
        self.assertEqual(provider_summary["provider_type"], "scrapy")
        self.assertEqual(provider_summary["provider_dispatch"], "crawlers/providers")
        self.assertEqual(provider_summary["provider_job_id"], "job-high-js-1")
        self.assertEqual(provider_summary["fetch_strategy"], "browser_render")
        self.assertTrue(provider_summary["render_required"])
        self.assertEqual(provider_summary["router_state"], "needs_browser")
        self.assertEqual(provider_summary["router_reason_code"], "needs_browser_runtime")
        self.assertFalse(provider_summary["fallback_boundary"]["http_fetch_fallback_allowed"])


if __name__ == "__main__":
    unittest.main()
