from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.celery_app import celery_app
from app.services.collect_runtime.adapters.search_market import SearchMarketAdapter
from app.services.collect_runtime.adapters.source_library import SourceLibraryAdapter
from app.services.collect_runtime.contracts import CollectRequest
from app.services.tasks import (
    task_raw_import_materials,
)


class _EmptyRawImportSession:
    def __init__(self, enabled=True) -> None:
        self.committed = False
        self.enabled = enabled

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _statement, _parameters):
        return SimpleNamespace(scalar_one_or_none=lambda: self.enabled)

    def commit(self) -> None:
        self.committed = True


class TaskRuntimeReadbackIngestBoundaryUnitTestCase(unittest.TestCase):
    def test_raw_import_task_is_registered_and_forwards_project_scope(self) -> None:
        from app.services.ingest import raw_import

        task_name = "app.services.tasks.task_raw_import_materials"
        retired_task_name = "app.services.tasks.task_raw_import_documents"
        payload = {"source_name": "async-material-import", "items": []}
        session = _EmptyRawImportSession()
        completed: list[tuple[int, str, object]] = []

        self.assertEqual(task_raw_import_materials.name, task_name)
        self.assertEqual(celery_app.tasks[task_name].name, task_name)
        self.assertNotIn(retired_task_name, celery_app.tasks)

        with (
            patch(
                "app.composition.raw_material_import_task.bind_project",
                return_value=nullcontext(),
            ) as mocked_bind,
            patch.object(raw_import, "SessionLocal", return_value=session),
            patch.object(raw_import, "start_job", return_value=91),
            patch.object(
                raw_import,
                "complete_job",
                side_effect=lambda job_id, status="completed", result=None: completed.append(
                    (job_id, status, result)
                ),
            ),
            patch.object(raw_import, "fail_job") as mocked_fail,
        ):
            result = task_raw_import_materials.run(payload, "local_demo_20260921")

        self.assertEqual(
            result,
            {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "error_count": 0,
                "errors": [],
                "items": [],
                "source_name": "async-material-import",
                "project_key": "local_demo_20260921",
            },
        )
        mocked_bind.assert_called_once_with("local_demo_20260921")
        self.assertTrue(session.committed)
        self.assertEqual(completed, [(91, "completed", result)])
        mocked_fail.assert_not_called()

    def test_queued_raw_import_rejects_project_archived_before_worker_starts(self) -> None:
        from app.services.ingest import raw_import
        from app.services.projects.context import ProjectNotWritableError

        session = _EmptyRawImportSession(enabled=False)
        with (
            patch.object(raw_import, "SessionLocal", return_value=session),
            patch.object(raw_import, "start_job") as start_job,
            patch.object(raw_import, "fetch_html") as fetch_html,
        ):
            with pytest.raises(ProjectNotWritableError, match="archived/disabled"):
                task_raw_import_materials.run(
                    {"items": [{"uri": "https://example.test/archived"}]},
                    "archived_project",
                )
        start_job.assert_not_called()
        fetch_html.assert_not_called()
        self.assertFalse(session.committed)

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

    def test_source_library_adapter_preserves_runtime_readback_in_resolver_override(self) -> None:
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
            patch(
                "app.services.source_library.resolver.list_effective_channels",
                return_value=[{"channel_key": "handler.cluster", "enabled": True}],
            ),
            patch(
                "app.services.source_library.resolver.list_effective_items",
                return_value=[{"item_key": "handler.cluster.search_template", "channel_key": "handler.cluster"}],
            ),
            patch("app.services.source_library.resolver.run_item_payload", return_value=raw) as mocked_run,
        ):
            result = adapter.run(request)

        self.assertEqual(result.inserted, 2)
        override = mocked_run.call_args.kwargs["override_params"]
        self.assertEqual(override["runtime_readback"]["line_key"], "resource_source_library")
        self.assertEqual(override["runtime_readback"]["task_id"], "celery-source-1")
        self.assertEqual(result.meta["raw"], raw)
        self.assertEqual(
            result.meta["terminal_output"]["contract_version"],
            "source_library.terminal_output.v1",
        )

if __name__ == "__main__":
    unittest.main()
