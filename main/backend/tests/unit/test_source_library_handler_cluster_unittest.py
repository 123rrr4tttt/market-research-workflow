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
from app.services.source_library.adapters.handler_cluster import handle_handler_cluster
from app.services.source_library.resolver import list_effective_channels
from app.services.source_library.orchestrators.site_search import fold_search_observations


class SourceLibraryHandlerClusterUnitTestCase(unittest.TestCase):
    def test_list_effective_channels_includes_builtin_handler_cluster_channel(self) -> None:
        channels = list_effective_channels(scope="effective", project_key=None)
        channel_map = {str(ch.get("channel_key") or ""): ch for ch in channels}

        self.assertIn("handler.cluster", channel_map)
        channel = channel_map["handler.cluster"]
        self.assertEqual(channel.get("provider"), "handler")
        self.assertEqual(channel.get("kind"), "cluster")
        self.assertTrue(channel.get("enabled"))

    def test_source_library_adapter_uses_run_item_payload_for_handler_cluster_items(self) -> None:
        adapter = SourceLibraryAdapter()
        request = CollectRequest(
            flow="source_collect",
            channel="source_library",
            project_key="demo_proj",
            item_key="handler.cluster.search_template",
            options={"override_params": {"query_terms": ["Humane AI Pin"]}},
            source_context={"summary": "执行来源项 handler.cluster.search_template"},
        )
        raw = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "params": {},
            "result": {"inserted": 1, "updated": 0, "skipped": 0, "errors": []},
        }

        with (
            patch(
                "app.services.source_library.resolver.list_effective_channels",
                return_value=[{"channel_key": "handler.cluster", "enabled": True}],
            ),
            patch(
                "app.services.source_library.resolver.list_effective_items",
                return_value=[
                    {
                        "item_key": "handler.cluster.search_template",
                        "channel_key": "handler.cluster",
                        "enabled": True,
                        "params": {},
                    }
                ],
            ),
            patch("app.services.source_library.resolver.run_item_payload", return_value=raw) as mocked_run_item_payload,
        ):
            result = adapter.run(request)

        mocked_run_item_payload.assert_called_once_with(
            item={
                "item_key": "handler.cluster.search_template",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {},
            },
            channels=[{"channel_key": "handler.cluster", "enabled": True}],
            project_key="demo_proj",
            override_params={"query_terms": ["Humane AI Pin"]},
        )
        self.assertEqual(result.inserted, 1)
        self.assertEqual(result.status, "completed")
        self.assertEqual(((result.meta or {}).get("raw") or {}).get("channel_key"), "handler.cluster")
        self.assertEqual(
            ((result.meta or {}).get("terminal_output") or {}).get("contract_version"),
            "source_library.terminal_output.v1",
        )

    def test_handler_cluster_adapter_reports_site_search_taxonomy(self) -> None:
        with patch("app.services.resource_pool.unified_search.unified_search_by_item_payload") as unified_search:
            unified_search.return_value = type(
                "UnifiedSearchResult",
                (),
                {
                    "site_entries_used": [{"site_url": "https://example.com/search?q=robotics", "entry_type": "search_template"}],
                    "candidates": ["https://example.com/posts/robotics-1"],
                    "written": {"urls_new": 1, "urls_skipped": 0},
                    "ingest_result": {
                        "inserted": 0,
                        "updated": 0,
                        "skipped": 0,
                        "inserted_valid": 0,
                        "rejected_count": 0,
                        "rejection_breakdown": {},
                    },
                    "errors": [],
                },
            )()
            result = handle_handler_cluster(
                {
                    "_item_key": "handler.cluster.search_template",
                    "query_terms": ["robotics"],
                    "expected_entry_type": "search_template",
                    "_source_library_item": {
                        "item_key": "handler.cluster.search_template",
                        "item_type": "service_aggregated",
                        "managed_by": "system",
                        "extra": {"expected_entry_type": "search_template"},
                    },
                },
                project_key="demo_proj",
            )

        self.assertEqual(result["source_mode"], "site_search")
        self.assertEqual(result["capability_profile"]["entry_type"], "search_template")
        self.assertEqual(result["execution_taxonomy"]["lane"], "site_search")
        self.assertEqual(result["execution_taxonomy"]["item_type"], "service_aggregated")
        self.assertEqual(result["execution_taxonomy"]["managed_by"], "system")

    def test_handler_cluster_adapter_preserves_duplicate_non_benign_errors(self) -> None:
        def search_result(query_term: str) -> SimpleNamespace:
            return SimpleNamespace(
                site_entries_used=[{"site_url": f"https://example.com/search?q={query_term}"}],
                runtime_diagnostics=[],
                candidates=[f"https://example.com/posts/{query_term}"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={
                    "inserted": 1,
                    "updated": 0,
                    "skipped": 0,
                    "inserted_valid": 1,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[
                    {"error": "search unavailable", "query_terms": [query_term]},
                    {"error": "url_term_filter_empty_fallback_used"},
                ],
                relevance_review_queue={"rows": [{"query_term": query_term}]},
            )

        with patch(
            "app.services.resource_pool.unified_search.unified_search_by_item_payload",
            side_effect=lambda **kwargs: search_result(kwargs["query_terms"][0]),
        ) as unified_search:
            result = handle_handler_cluster(
                {"query_terms": ["alpha", "beta"], "keyword_batch_size": 1, "auto_ingest": False},
                project_key="demo_proj",
            )

        self.assertEqual(unified_search.call_count, 2)
        self.assertEqual(result["errors"], ["search unavailable", "search unavailable"])
        self.assertEqual(
            [error["query_terms"] for error in result["error_details"] if error.get("error") == "search unavailable"],
            [["alpha"], ["beta"]],
        )
        self.assertNotIn("url_term_filter_empty_fallback_used", result["errors"])
        self.assertIn({"error": "url_term_filter_empty_fallback_used"}, result["error_details"])
        self.assertEqual(result["candidates"], ["https://example.com/posts/alpha", "https://example.com/posts/beta"])
        self.assertEqual(result["legacy_ingest_result"]["inserted"], 2)

    def test_handler_cluster_adapter_keeps_candidates_after_auto_ingest_failure(self) -> None:
        with patch("app.services.resource_pool.unified_search.unified_search_by_item_payload") as unified_search:
            unified_search.return_value = SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search?q=alpha"}],
                runtime_diagnostics=[],
                candidates=["https://example.com/posts/alpha"],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "inserted_valid": 0,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[{"error": "auto_ingest_failed", "phase": "auto_ingest"}],
                relevance_review_queue={},
            )
            result = handle_handler_cluster(
                {"query_terms": ["alpha"], "auto_ingest": True},
                project_key="demo_proj",
            )

        self.assertEqual(result["errors"], ["auto_ingest_failed"])
        self.assertEqual(result["candidates"], ["https://example.com/posts/alpha"])
        self.assertEqual(result["legacy_ingest_result"]["inserted"], 0)

    def test_fold_search_observations_can_deduplicate_error_messages_without_details(self) -> None:
        results = [
            SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/one"}],
                candidates=["https://example.com/posts/one"],
                written={"urls_new": 1, "urls_skipped": 0},
                errors=[{"error": "same"}],
            ),
            SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/two"}],
                candidates=["https://example.com/posts/two"],
                runtime_diagnostics=None,
                written={"urls_new": 0, "urls_skipped": 1},
                errors=None,
                relevance_review_queue=None,
            ),
        ]

        observations = fold_search_observations(results, deduplicate_error_messages=True)

        self.assertEqual(observations.errors, ["same"])
        self.assertEqual([error["error"] for error in observations.error_details], ["same"])
        self.assertEqual(observations.candidates, ["https://example.com/posts/one", "https://example.com/posts/two"])
        self.assertEqual((observations.written_urls_new, observations.written_urls_skipped), (1, 1))
        self.assertEqual(
            observations.runtime_diagnostics,
            [{"site_url": "https://example.com/one"}, {"site_url": "https://example.com/two"}],
        )
        self.assertEqual(observations.relevance_review_queues, [])


if __name__ == "__main__":
    unittest.main()
