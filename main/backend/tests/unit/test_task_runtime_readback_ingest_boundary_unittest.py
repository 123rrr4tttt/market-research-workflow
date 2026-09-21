from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.collect_runtime.adapters.search_market import SearchMarketAdapter
from app.services.collect_runtime.adapters.source_library import SourceLibraryAdapter
from app.services.collect_runtime.contracts import CollectRequest
from app.celery_app import celery_app
from app.services.tasks import (
    task_ingest_url_via_source_library,
    task_raw_import_documents,
)


class TaskRuntimeReadbackIngestBoundaryUnitTestCase(unittest.TestCase):
    def test_raw_import_task_is_registered_and_forwards_project_scope(self) -> None:
        task_name = "app.services.tasks.task_raw_import_documents"
        payload = {"items": [{"title": "raw-import-test", "text": "local async task"}]}
        expected = {"inserted": 1, "error_count": 0}

        self.assertEqual(task_raw_import_documents.name, task_name)
        self.assertEqual(celery_app.tasks[task_name].name, task_name)

        with (
            patch("app.services.tasks.bind_project", return_value=nullcontext()) as mocked_bind,
            patch("app.services.ingest.raw_import.run_raw_import_documents", return_value=expected) as mocked_run,
        ):
            result = task_raw_import_documents.run(payload, "local_demo_20260921")

        self.assertEqual(result, expected)
        mocked_bind.assert_called_once_with("local_demo_20260921")
        mocked_run.assert_called_once_with(payload=payload, project_key="local_demo_20260921")

    def test_search_market_adapter_passes_runtime_readback_to_market_job(self) -> None:
        adapter = SearchMarketAdapter()
        request = CollectRequest(
            channel="search.market",
            query_terms=["ai terminal"],
            limit=3,
            source_context={
                "runtime_readback": {
                    "line_key": "search_discovery_index",
                    "task_id": "celery-market-1",
                    "worker_name": "worker@market",
                    "queue": "search.q",
                    "trace_id": "trace-market",
                }
            },
        )

        with patch("app.services.ingest.market_web.collect_market_info") as mocked_collect:
            mocked_collect.return_value = {"inserted": 1, "updated": 0, "skipped": 0}
            result = adapter.run(request)

        self.assertEqual(result.inserted, 1)
        runtime_readback = mocked_collect.call_args.kwargs["runtime_readback"]
        self.assertEqual(runtime_readback["line_key"], "search_discovery_index")
        self.assertEqual(runtime_readback["task_id"], "celery-market-1")
        self.assertEqual(runtime_readback["worker_name"], "worker@market")
        self.assertEqual(runtime_readback["queue"], "search.q")
        self.assertEqual(runtime_readback["trace_id"], "trace-market")

    def test_source_library_adapter_writes_runtime_readback_to_job_params_and_result(self) -> None:
        adapter = SourceLibraryAdapter()
        runtime_readback = {
            "line_key": "resource_source_library",
            "task_id": "celery-source-1",
            "worker_name": "worker@source",
            "queue": "source.q",
            "trace_id": "trace-source",
        }
        request = CollectRequest(
            channel="source_library",
            project_key="demo_proj",
            item_key="handler.cluster.search_template",
            options={"override_params": {"runtime_readback": runtime_readback}},
        )
        raw = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "params": {},
            "result": {"inserted": 2, "updated": 0, "skipped": 0, "errors": []},
        }

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value=123) as mocked_start,
            patch("app.services.collect_runtime.adapters.source_library.complete_job") as mocked_complete,
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch(
                "app.services.source_library.resolver.list_effective_channels",
                return_value=[{"channel_key": "handler.cluster", "enabled": True}],
            ),
            patch(
                "app.services.source_library.resolver.list_effective_items",
                return_value=[{"item_key": "handler.cluster.search_template", "channel_key": "handler.cluster"}],
            ),
            patch("app.services.source_library.resolver.run_item_payload", return_value=raw),
        ):
            result = adapter.run(request)

        self.assertEqual(result.inserted, 2)
        start_params = mocked_start.call_args.args[1]
        self.assertEqual(start_params["runtime_readback"]["line_key"], "resource_source_library")
        self.assertEqual(start_params["runtime_readback"]["task_id"], "celery-source-1")
        complete_result = mocked_complete.call_args.kwargs["result"]
        self.assertEqual(complete_result["runtime_readback"]["line_key"], "resource_source_library")
        self.assertEqual(complete_result["runtime_readback"]["status"], "completed")
        self.assertTrue(
            any(
                isinstance(item, dict) and item.get("event") == "completed"
                for item in complete_result["runtime_readback"]["events"]
            )
        )

    def test_url_pool_async_task_prefers_celery_request_runtime_context(self) -> None:
        task_ingest_url_via_source_library.push_request(
            id="celery-url-1",
            hostname="worker@ingest",
            delivery_info={"routing_key": "ingest.q"},
        )
        try:
            with (
                patch("app.services.tasks.start_job", return_value=456) as mocked_start,
                patch("app.services.tasks.complete_job") as mocked_complete,
                patch("app.services.tasks.fail_job"),
                patch("app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor") as mocked_ingest,
            ):
                mocked_ingest.return_value = {"status": "success", "inserted": 1, "skipped": 0}
                result = task_ingest_url_via_source_library.run(
                    "https://example.com/a",
                    ["ai terminal"],
                    False,
                    None,
                    {"runtime_readback": {"trace_id": "trace-url"}},
                )
        finally:
            task_ingest_url_via_source_library.pop_request()

        runtime_readback = mocked_start.call_args.args[1]["runtime_readback"]
        self.assertEqual(runtime_readback["line_key"], "ingest")
        self.assertEqual(runtime_readback["task_id"], "celery-url-1")
        self.assertEqual(runtime_readback["worker_name"], "worker@ingest")
        self.assertEqual(runtime_readback["queue"], "ingest.q")
        self.assertEqual(runtime_readback["trace_id"], "trace-url")
        self.assertEqual(result["runtime_readback"]["status"], "completed")
        complete_result = mocked_complete.call_args.kwargs["result"]
        self.assertEqual(complete_result["runtime_readback"]["task_id"], "celery-url-1")


if __name__ == "__main__":
    unittest.main()
