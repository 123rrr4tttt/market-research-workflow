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
        seen = {"max_workers": None, "mapped_terms": []}

        class _FakeExecutor:
            def __init__(self, *, max_workers, thread_name_prefix):  # noqa: ANN001
                seen["max_workers"] = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
                return False

            def map(self, fn, iterable):
                rows = list(iterable)
                seen["mapped_terms"] = [list(x) for x in rows]
                return [fn(row) for row in rows]

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
                },
            )

        self.assertEqual(seen["max_workers"], 2)
        self.assertEqual(seen["mapped_terms"], [["alpha"], ["beta"], ["gamma"]])
        self.assertEqual(
            raw["result"]["candidates"],
            ["https://example.com/posts/alpha", "https://example.com/posts/beta", "https://example.com/posts/gamma"],
        )
        self.assertEqual(raw["result"]["search_parallelism"], 2)

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
                override_params={"query_terms": ["alpha", "beta"], "keyword_batch_size": 1},
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(raw["channel_key"], "handler.cluster")
        self.assertEqual(raw["result"]["inserted"], 4)
        self.assertEqual(raw["result"]["batches_total"], 2)
        self.assertEqual(raw["result"]["candidates"], ["https://example.com/posts/alpha", "https://example.com/posts/beta"])
        self.assertEqual(raw["result"]["middle_layer_protocol"]["front_door_owner"], "run_item_payload")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["execution_mode"], "url_routing")
        self.assertEqual(
            raw["result"]["middle_layer_protocol"]["candidate_urls"],
            ["https://example.com/posts/alpha", "https://example.com/posts/beta"],
        )

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
                override_params={"query_terms": ["gamma"]},
            )

        self.assertEqual(raw["channel_key"], "generic_web.rss")
        self.assertEqual(raw["result"]["single_write_workflow"], "front_door_url_routing")
        self.assertEqual(raw["result"]["inserted"], 1)
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
                override_params={"query_terms": ["alpha", "beta", "gamma"], "keyword_batch_size": 1},
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

    def test_source_library_adapter_always_delegates_to_run_item_by_key(self) -> None:
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
            "app.services.source_library.resolver.run_item_by_key",
            return_value=raw,
        ) as mocked:
            result = adapter.run(request)

        mocked.assert_called_once_with(
            item_key="handler.cluster.search_template",
            project_key=None,
            override_params={"query_terms": ["alpha"]},
        )
        self.assertEqual(result.inserted, 3)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.skipped, 0)


if __name__ == "__main__":
    unittest.main()
