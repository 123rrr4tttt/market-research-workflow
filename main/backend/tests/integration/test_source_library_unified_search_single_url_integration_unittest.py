from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from app.services.collect_runtime.runtime import run_source_library_item_compat

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SourceLibraryUnifiedSearchSingleUrlIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"integration test requires backend dependencies: {_IMPORT_ERROR}")

    def test_handler_cluster_item_bridges_unified_search_and_single_url_summary(self):
        fake_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "handler cluster item",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {"site_entries": ["https://example.com/search"], "expected_entry_type": "search_template"},
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            }
        ]

        unified_calls: list[dict] = []

        def _fake_unified_search_by_item_payload(**kwargs):
            unified_calls.append(kwargs)
            batch_terms = list(kwargs.get("query_terms") or [])
            inserted = len(batch_terms)
            return SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search", "entry_type": "search_template"}],
                candidates=[f"https://example.com/news/{i}" for i in range(1, inserted + 1)],
                written={"urls_new": inserted, "urls_skipped": 0},
                ingest_result={
                    "inserted": inserted,
                    "updated": 0,
                    "skipped": 0,
                    "inserted_valid": inserted,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[],
            )

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_unified_search_by_item_payload),
        ):
            result = run_source_library_item_compat(
                item_key="handler.cluster.search_template",
                project_key="demo_proj",
                override_params={
                    "query_terms": ["ai", "robotics", "embodied", "automation", "supply"],
                    "keyword_batch_size": 2,
                    "per_keyword_limit": 2,
                    "ingest_limit": 20,
                    "write_to_pool": True,
                    "auto_ingest": True,
                },
            )

        self.assertEqual(len(unified_calls), 3)
        self.assertTrue(all(bool(call.get("allow_term_fallback")) for call in unified_calls))
        nested = result.get("result") or {}
        self.assertEqual(nested.get("inserted_valid"), 5)
        self.assertEqual(nested.get("rejected_count"), 0)
        self.assertEqual(nested.get("rejection_breakdown"), {})
        self.assertEqual(nested.get("single_write_workflow"), "single_url")
        ingest_result = nested.get("ingest_result") or {}
        self.assertEqual(ingest_result.get("inserted"), 5)
        self.assertEqual(ingest_result.get("inserted_valid"), 5)
        self.assertEqual(ingest_result.get("rejected_count"), 0)
        self.assertEqual(nested.get("batches_total"), 3)

    def test_source_library_job_params_include_trace_id(self):
        fake_items = [
            {
                "item_key": "normal.item",
                "name": "normal item",
                "channel_key": "url_pool",
                "enabled": True,
                "params": {},
                "extra": {},
            }
        ]

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value=123) as start_job_mock,
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch(
                "app.services.source_library.resolver.run_item_by_key",
                return_value={
                    "item_key": "normal.item",
                    "channel_key": "url_pool",
                    "params": {},
                    "result": {"inserted": 0, "updated": 0, "skipped": 0, "errors": []},
                },
            ),
        ):
            run_source_library_item_compat(
                item_key="normal.item",
                project_key="demo_proj",
                override_params={"_trace_id": "trace-s1"},
            )

        start_job_mock.assert_called_once()
        called_params = start_job_mock.call_args.args[1]
        self.assertEqual(called_params.get("trace_id"), "trace-s1")

    def test_handler_cluster_missing_inserted_valid_keeps_zero_without_inserted_fallback(self):
        fake_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "handler cluster item",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {"site_entries": ["https://example.com/search"], "expected_entry_type": "search_template"},
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            }
        ]

        def _fake_unified_search_by_item_payload(**kwargs):
            _ = kwargs
            return SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search", "entry_type": "search_template"}],
                candidates=["https://example.com/news/1"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={
                    "inserted": 1,
                    "updated": 0,
                    "skipped": 0,
                    # intentionally omit inserted_valid to verify strict metric semantics
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                },
                errors=[],
            )

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_unified_search_by_item_payload),
        ):
            result = run_source_library_item_compat(
                item_key="handler.cluster.search_template",
                project_key="demo_proj",
                override_params={
                    "query_terms": ["ai"],
                    "keyword_batch_size": 1,
                    "per_keyword_limit": 1,
                    "ingest_limit": 5,
                    "write_to_pool": True,
                    "auto_ingest": True,
                },
            )

        nested = result.get("result") or {}
        ingest_result = nested.get("ingest_result") or {}
        self.assertEqual(ingest_result.get("inserted"), 1)
        self.assertEqual(ingest_result.get("inserted_valid"), 0)

    def test_handler_cluster_normalizes_rejection_breakdown_reason_codes(self):
        fake_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "handler cluster item",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {"site_entries": ["https://example.com/search"], "expected_entry_type": "search_template"},
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            }
        ]

        def _fake_unified_search_by_item_payload(**kwargs):
            _ = kwargs
            return SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search", "entry_type": "search_template"}],
                candidates=["https://example.com/news/1"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 1,
                    "inserted_valid": 0,
                    "rejected_count": 3,
                    "rejection_breakdown": {
                        "URL Policy/Low Value Endpoint": 1,
                        "content shell signature": 2,
                    },
                },
                errors=[],
            )

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_unified_search_by_item_payload),
        ):
            result = run_source_library_item_compat(
                item_key="handler.cluster.search_template",
                project_key="demo_proj",
                override_params={
                    "query_terms": ["ai"],
                    "keyword_batch_size": 1,
                    "per_keyword_limit": 1,
                    "ingest_limit": 5,
                    "write_to_pool": True,
                    "auto_ingest": True,
                },
            )

        ingest_result = (result.get("result") or {}).get("ingest_result") or {}
        self.assertEqual(
            ingest_result.get("rejection_breakdown"),
            {
                "url_policy_low_value_endpoint": 1,
                "content_shell_signature": 2,
            },
        )

    def test_non_cluster_item_forces_wf1_gate_defaults(self):
        fake_items = [
            {
                "item_key": "normal.item",
                "name": "normal item",
                "channel_key": "url_pool",
                "enabled": True,
                "params": {},
                "extra": {},
            }
        ]
        captured = {}

        def _fake_run_item_by_key(**kwargs):
            captured.update(kwargs)
            return {
                "item_key": "normal.item",
                "channel_key": "url_pool",
                "params": {},
                "result": {"inserted": 0, "updated": 0, "skipped": 0, "errors": []},
            }

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.source_library.resolver.run_item_by_key", side_effect=_fake_run_item_by_key),
        ):
            run_source_library_item_compat(
                item_key="normal.item",
                project_key="demo_proj",
                override_params={"k": "v"},
            )

        override = captured.get("override_params") or {}
        self.assertEqual(override.get("k"), "v")
        self.assertEqual(override.get("force_single_url_flow"), True)
        self.assertEqual(override.get("prefer_crawler_first"), False)
        self.assertEqual(override.get("auto_ingest_crawler_output"), False)

    def test_handler_cluster_dry_run_does_not_write_or_ingest(self):
        fake_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "handler cluster item",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {"site_entries": ["https://example.com/search"], "expected_entry_type": "search_template"},
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            }
        ]
        unified_calls: list[dict] = []

        def _fake_unified_search_by_item_payload(**kwargs):
            unified_calls.append(kwargs)
            return SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search", "entry_type": "search_template"}],
                candidates=["https://example.com/news/a", "https://example.com/news/b"],
                written={"urls_new": 999, "urls_skipped": 0},
                ingest_result={"inserted": 999, "updated": 0, "skipped": 0, "inserted_valid": 999, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
            )

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_unified_search_by_item_payload),
            patch("app.services.resource_pool.append_url") as append_url,
            patch("app.services.ingest.url_pool.collect_urls_from_pool") as collect_urls,
        ):
            result = run_source_library_item_compat(
                item_key="handler.cluster.search_template",
                project_key="demo_proj",
                override_params={
                    "query_terms": ["ai"],
                    "execution_mode": "dry_run",
                    "write_to_pool": True,
                    "auto_ingest": True,
                },
            )

        self.assertEqual(len(unified_calls), 1)
        self.assertEqual(unified_calls[0].get("write_to_pool"), False)
        self.assertEqual(unified_calls[0].get("auto_ingest"), False)
        append_url.assert_not_called()
        collect_urls.assert_not_called()
        nested = result.get("result") or {}
        self.assertEqual(nested.get("execution_mode"), "dry_run")
        self.assertEqual(nested.get("inserted"), 0)
        self.assertEqual(nested.get("written", {}).get("urls_new"), 0)

    def test_handler_cluster_apply_with_explicit_ids_writes_selected_candidates_only(self):
        fake_items = [
            {
                "item_key": "handler.cluster.search_template",
                "name": "handler cluster item",
                "channel_key": "handler.cluster",
                "enabled": True,
                "params": {"site_entries": ["https://example.com/search"], "expected_entry_type": "search_template"},
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            }
        ]
        selected_url = "https://example.com/news/b"
        selected_id = hashlib.sha1(selected_url.encode("utf-8")).hexdigest()[:12]

        def _fake_unified_search_by_item_payload(**kwargs):
            _ = kwargs
            return SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search", "entry_type": "search_template"}],
                candidates=["https://example.com/news/a", selected_url],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
            )

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-local"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=fake_items),
            patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_unified_search_by_item_payload),
            patch("app.services.resource_pool.append_url", return_value=True) as append_url,
            patch(
                "app.services.ingest.url_pool.collect_urls_from_pool",
                return_value={"inserted": 1, "updated": 0, "skipped": 0, "inserted_valid": 1, "rejected_count": 0, "rejection_breakdown": {}},
            ) as collect_urls,
        ):
            result = run_source_library_item_compat(
                item_key="handler.cluster.search_template",
                project_key="demo_proj",
                override_params={
                    "query_terms": ["ai"],
                    "execution_mode": "apply",
                    "explicit_candidate_ids": [selected_id],
                    "auto_ingest": True,
                },
            )

        append_url.assert_called_once()
        self.assertEqual(append_url.call_args.kwargs.get("url"), selected_url)
        collect_urls.assert_called_once()
        self.assertEqual(int(collect_urls.call_args.kwargs.get("limit") or 0), 1)
        nested = result.get("result") or {}
        self.assertEqual(nested.get("execution_mode"), "apply")
        self.assertEqual(nested.get("inserted"), 1)
        self.assertIn(selected_id, nested.get("selected_candidate_ids") or [])


if __name__ == "__main__":
    unittest.main()
