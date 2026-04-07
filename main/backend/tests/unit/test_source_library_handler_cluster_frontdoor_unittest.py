from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.collect_runtime.adapters.source_library import SourceLibraryAdapter
from app.services.collect_runtime.contracts import CollectRequest
from app.services.source_library.resolver import run_item_payload


class SourceLibraryHandlerClusterFrontDoorUnitTestCase(unittest.TestCase):
    def test_run_item_payload_uses_controlled_parallel_search_batches(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }
        seen = {"max_workers": None, "mapped_terms": [], "submitted_terms": []}

        class _FakeExecutor:
            def __init__(self, *, max_workers, thread_name_prefix):  # noqa: ANN001
                seen["max_workers"] = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
                return False

            class _Future:
                def __init__(self, value):  # noqa: ANN001
                    self._value = value

                def result(self):
                    return self._value

            def map(self, fn, iterable):
                rows = list(iterable)
                seen["mapped_terms"] = [list(x) for x in rows]
                return [fn(row) for row in rows]

            def submit(self, fn, *args, **kwargs):  # noqa: ANN001
                if len(args) >= 2 and isinstance(args[1], list):
                    seen["submitted_terms"].append(list(args[1]))
                return self._Future(fn(*args, **kwargs))

        def _fake_run(**kwargs):
            query_terms = list(kwargs.get("query_terms") or [])
            term = query_terms[0] if query_terms else ""
            return SimpleNamespace(
                site_entries_used=[{"site_url": f"https://example.com/search?q={term}"}],
                candidates=[f"https://example.com/posts/{term}"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "inserted_valid": 0,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[],
            )

        with patch("app.services.source_library.resolver.ThreadPoolExecutor", _FakeExecutor), patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            side_effect=_fake_run,
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 0, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={
                    "query_terms": ["alpha", "beta", "gamma"],
                    "keyword_batch_size": 1,
                    "search_parallelism": 2,
                    "_allow_internal_generic_web": True,
                },
            )

        self.assertEqual(seen["max_workers"], 2)
        self.assertEqual(seen["submitted_terms"], [["alpha"], ["beta"], ["gamma"]])
        self.assertEqual(
            raw["result"]["candidates"],
            ["https://example.com/posts/alpha", "https://example.com/posts/beta", "https://example.com/posts/gamma"],
        )
        self.assertEqual(raw["result"]["search_parallelism"], 2)
        self.assertEqual(raw["result"]["concurrency_plan"]["search"]["parallelism"], 2)
        self.assertEqual(raw["result"]["fetch_diagnostics"]["concurrency"]["search"]["budget"], 3)
        self.assertEqual(raw["result"]["candidate_pipeline"]["mode"], "query_search_candidate_fetch")
        self.assertFalse(raw["result"]["candidate_pipeline"]["candidate_generation"]["candidate_sources_are_fetch_targets"])
        self.assertEqual(raw["result"]["candidate_pipeline"]["candidate_generation"]["search_service_breakdown"], {})
        self.assertEqual(raw["result"]["candidate_pipeline"]["candidate_generation"]["site_policy_breakdown"], {})

    def test_run_item_payload_handles_handler_cluster_inside_resolver(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }

        def _fake_run(**kwargs):
            query_terms = list(kwargs.get("query_terms") or [])
            term = query_terms[0] if query_terms else ""
            return SimpleNamespace(
                site_entries_used=[{"site_url": f"https://example.com/search?q={term}"}],
                candidates=[f"https://example.com/posts/{term}"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={
                    "inserted": 2,
                    "updated": 0,
                    "skipped": 0,
                    "inserted_valid": 2,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[],
            )

        with patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_run) as mocked, patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 4, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["alpha", "beta"], "keyword_batch_size": 1, "_allow_internal_generic_web": True},
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(raw["channel_key"], "handler.cluster")
        self.assertEqual(raw["result"]["stats"]["fetched"], 2)
        self.assertEqual(raw["result"]["stats"]["normalized"], 2)
        self.assertEqual(raw["result"]["batches_total"], 2)
        self.assertEqual(raw["result"]["candidates"], ["https://example.com/posts/alpha", "https://example.com/posts/beta"])
        self.assertEqual(raw["result"]["middle_layer_protocol"]["front_door_owner"], "run_item_payload")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["execution_mode"], "url_routing")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["pipeline"]["mode"], "candidate_fetch")
        self.assertEqual(
            raw["result"]["middle_layer_protocol"]["candidate_urls"],
            ["https://example.com/posts/alpha", "https://example.com/posts/beta"],
        )

    def test_run_item_payload_refetches_candidate_only_results_via_url_pool(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }

        initial_routed = {
            "errors": [],
            "by_url": [
                {
                    "url": "https://example.com/posts/alpha",
                    "channel_key": "crawler.demo_proj",
                    "error": None,
                    "result": {"status": "accepted"},
                }
            ],
            "stats": {"fetched": 1, "normalized": 0, "dropped": 1, "errors": 0},
            "legacy_counts": {"inserted": 0, "updated": 0, "skipped": 0},
            "execution_layer": "terminal_output_only",
        }
        refetched_routed = {
            "errors": [],
            "by_url": [
                {
                    "url": "https://example.com/posts/alpha",
                    "channel_key": "url_pool",
                    "error": None,
                    "result": {
                        "status": "accepted",
                        "errors": [],
                        "by_url": [
                            {
                                "url": "https://example.com/posts/alpha",
                                "error": None,
                                "result": {
                                    "status": "fetched",
                                    "record_id": "https://example.com/posts/alpha",
                                    "title": "Alpha",
                                    "content_text": "Alpha body",
                                    "content_preview": "Alpha body",
                                    "source_label": "url_pool",
                                    "execution_layer": "terminal_output_only",
                                    "record_meta": {
                                        "artifact_ref": {
                                            "artifact_source": "pdf",
                                            "source_locator": "https://example.com/posts/alpha.pdf",
                                            "mime_type": "application/pdf",
                                            "download_status": "downloaded",
                                            "storage_kind": "local_file",
                                            "local_path": "/tmp/source-library-artifacts/alpha.pdf",
                                        }
                                    },
                                },
                            }
                        ],
                        "records": [
                            {
                                "record_id": "https://example.com/posts/alpha",
                                "url": "https://example.com/posts/alpha",
                                "title": "Alpha",
                                "content_text": "Alpha body",
                                "summary": None,
                                "published_at": None,
                                "author": None,
                                "language": None,
                                "source_label": "url_pool",
                                "record_meta": {
                                    "artifact_ref": {
                                        "artifact_source": "pdf",
                                        "source_locator": "https://example.com/posts/alpha.pdf",
                                        "mime_type": "application/pdf",
                                        "download_status": "downloaded",
                                        "storage_kind": "local_file",
                                        "local_path": "/tmp/source-library-artifacts/alpha.pdf",
                                    }
                                },
                                "raw_ref": {"source": "url_pool", "url": "https://example.com/posts/alpha"},
                            }
                        ],
                    },
                }
            ],
            "records": [],
            "stats": {"fetched": 1, "normalized": 1, "dropped": 0, "errors": 0},
            "legacy_counts": {"inserted": 0, "updated": 0, "skipped": 0},
            "execution_layer": "terminal_output_only",
        }

        with patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            return_value=SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search?q=alpha"}],
                candidates=["https://example.com/posts/alpha"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
            ),
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            side_effect=[initial_routed, refetched_routed],
        ) as routed_run:
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["alpha"], "_allow_internal_generic_web": True},
            )

        self.assertEqual(routed_run.call_count, 2)
        first_call = routed_run.call_args_list[0].kwargs
        second_call = routed_run.call_args_list[1].kwargs
        self.assertNotIn("force_url_routing_flow", first_call["params"])
        self.assertTrue(second_call["params"]["force_url_routing_flow"])
        self.assertFalse(second_call["params"]["force_crawler_fallback_on_empty"])
        self.assertEqual(raw["result"]["records"][0]["title"], "Alpha")
        self.assertEqual(raw["result"]["records"][0]["content_text"], "Alpha body")
        self.assertEqual(
            raw["result"]["records"][0]["record_meta"]["artifact_ref"]["local_path"],
            "/tmp/source-library-artifacts/alpha.pdf",
        )
        self.assertEqual(raw["result"]["stats"]["normalized"], 1)

    def test_run_item_payload_exposes_candidate_generation_policy_and_service_breakdown(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }

        with patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            return_value=SimpleNamespace(
                site_entries_used=[
                    {
                        "site_url": "https://example.com/search?q=alpha",
                        "entry_type": "search_template",
                        "site_policy": "keep",
                        "search_service": "resilient",
                    }
                ],
                candidates=["https://example.com/posts/alpha"],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[
                    {
                        "site_url": "https://example.com/search?q=alpha",
                        "error": "429 Client Error",
                        "error_class": "transport_failure",
                    }
                ],
            ),
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 1, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["alpha"], "_allow_internal_generic_web": True},
            )

        generation = raw["result"]["candidate_pipeline"]["candidate_generation"]
        self.assertEqual(generation["site_policy_breakdown"], {"keep": 1})
        self.assertEqual(generation["search_service_breakdown"], {"resilient": 1})
        self.assertEqual(generation["error_class_breakdown"], {"transport_failure": 1})

    def test_run_item_payload_exposes_browser_candidate_deferred_search_route(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }

        with patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            return_value=SimpleNamespace(
                site_entries_used=[
                    {
                        "site_url": "https://example.com/search?q=alpha",
                        "entry_type": "search_template",
                        "site_policy": "keep",
                        "search_service": "external_search_slowlane",
                        "browser_candidate_deferred": True,
                        "browser_candidate_reason": "throttle_or_blocking_signals",
                    }
                ],
                candidates=[],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[
                    {
                        "site_url": "https://example.com/search?q=alpha",
                        "error": "browser_candidate_required",
                        "error_class": "deferred_browser_required",
                        "browser_candidate_enqueued": True,
                        "browser_candidate_reason": "throttle_or_blocking_signals",
                    }
                ],
            ),
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 0, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["alpha"], "_allow_internal_generic_web": True},
            )

        route = raw["result"]["candidate_pipeline"]["search_route"]
        generation = raw["result"]["candidate_pipeline"]["candidate_generation"]
        self.assertTrue(route["slow_lane_enabled"])
        self.assertEqual(route["slow_lane"]["deferred_count"], 1)
        self.assertEqual(route["slow_lane"]["reasons"], {"throttle_or_blocking_signals": 2})
        self.assertTrue(route["degraded_to_static"])
        self.assertEqual(generation["slow_lane_deferred_count"], 1)

    def test_run_item_payload_merges_override_params_into_unified_search_item(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }
        seen = {}

        def _fake_run(**kwargs):
            seen["item"] = kwargs.get("item")
            return SimpleNamespace(
                site_entries_used=[],
                candidates=[],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
            )

        with patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            side_effect=_fake_run,
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 0, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={
                    "query_terms": ["alpha"],
                    "allow_deprioritized_site_entries": True,
                    "_allow_internal_generic_web": True,
                },
            )

        self.assertTrue(seen["item"]["params"]["allow_deprioritized_site_entries"])
        self.assertTrue(seen["item"]["extra"]["allow_deprioritized_site_entries"])

    def test_run_item_payload_treats_site_entries_item_as_front_door_search(self) -> None:
        item = {
            "item_key": "report1.root_site_search",
            "channel_key": "generic_web.rss",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
            },
            "extra": {},
        }

        with patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            return_value=SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search?q=gamma"}],
                candidates=["https://example.com/posts/gamma"],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
            ),
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 1, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["gamma"], "_allow_internal_generic_web": True},
            )

        self.assertEqual(raw["channel_key"], "handler.cluster")
        self.assertEqual(raw["result"]["single_write_workflow"], "front_door_url_routing")
        self.assertEqual(raw["result"]["stats"]["fetched"], 1)
        self.assertEqual(raw["result"]["stats"]["normalized"], 1)
        self.assertEqual(raw["result"]["middle_layer_protocol"]["route_decision"], "front_door_url_routing")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["front_door_owner"], "run_item_payload")

    def test_run_item_payload_preserves_first_seen_candidate_order_across_batches(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }

        batch_payloads = {
            "alpha": ["https://example.com/posts/alpha", "https://example.com/posts/shared"],
            "beta": ["https://example.com/posts/beta", "https://example.com/posts/shared"],
            "gamma": ["https://example.com/posts/gamma"],
        }

        def _fake_run(**kwargs):
            query_terms = list(kwargs.get("query_terms") or [])
            term = query_terms[0] if query_terms else ""
            return SimpleNamespace(
                site_entries_used=[{"site_url": f"https://example.com/search?q={term}"}],
                candidates=batch_payloads.get(term, []),
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "inserted_valid": 0,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[],
            )

        with patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_run), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 0, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["alpha", "beta", "gamma"], "keyword_batch_size": 1, "_allow_internal_generic_web": True},
            )

        self.assertEqual(
            raw["result"]["candidates"],
            [
                "https://example.com/posts/alpha",
                "https://example.com/posts/shared",
                "https://example.com/posts/beta",
                "https://example.com/posts/gamma",
            ],
        )
        self.assertEqual(
            raw["result"]["middle_layer_protocol"]["candidate_urls"],
            [
                "https://example.com/posts/alpha",
                "https://example.com/posts/shared",
                "https://example.com/posts/beta",
                "https://example.com/posts/gamma",
            ],
        )

    def test_source_library_adapter_always_delegates_to_run_item_payload(self) -> None:
        adapter = SourceLibraryAdapter()
        request = CollectRequest(
            channel="source_library",
            project_key=None,
            item_key="handler.cluster.search_template",
            options={"override_params": {"query_terms": ["alpha"]}},
        )
        raw = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "params": {},
            "result": {"inserted": 3, "updated": 1, "skipped": 0, "errors": []},
        }

        with patch("app.services.collect_runtime.adapters.source_library.start_job", return_value=7), patch(
            "app.services.collect_runtime.adapters.source_library.complete_job"
        ), patch(
            "app.services.source_library.resolver.list_effective_channels",
            return_value=[{"channel_key": "handler.cluster", "enabled": True}],
        ), patch(
            "app.services.source_library.resolver.list_effective_items",
            return_value=[
                {
                    "item_key": "handler.cluster.search_template",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "params": {},
                }
            ],
        ), patch(
            "app.services.source_library.resolver.run_item_payload",
            return_value=raw,
        ) as mocked:
            result = adapter.run(request)

        mocked.assert_called_once_with(
            item={
                "item_key": "handler.cluster.search_template",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {},
            },
            channels=[{"channel_key": "handler.cluster", "enabled": True}],
            project_key=None,
            override_params={"query_terms": ["alpha"]},
        )
        self.assertEqual(result.inserted, 3)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.skipped, 0)


if __name__ == "__main__":
    unittest.main()
