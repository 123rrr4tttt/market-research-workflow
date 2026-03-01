from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.api import process as process_api
    from app.services.collect_runtime.contracts import CollectRequest, CollectResult
    from app.services.collect_runtime.display_meta import build_display_meta

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class CollectRuntimeProcessFallbackUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"collect_runtime/process unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_collect_runtime_build_display_meta_maps_new_provider_fields(self):
        request = CollectRequest(
            channel="search.market",
            project_key="demo_proj",
            query_terms=["embodied ai", "policy"],
            limit=20,
            provider="auto",
            language="en",
        )
        result = CollectResult(
            channel="search.market",
            status="running",
            inserted=3,
            updated=1,
            skipped=2,
            provider_job_id="ext-job-123",
            provider_type="scrapyd",
            provider_status="queued",
            attempt_count=2,
        )

        meta = build_display_meta(request, result, summary="市场信息采集")

        self.assertEqual(meta["channel"], "search.market")
        self.assertEqual(meta["provider"], "auto")
        self.assertEqual(meta["provider_job_id"], "ext-job-123")
        self.assertEqual(meta["provider_type"], "scrapyd")
        self.assertEqual(meta["provider_status"], "queued")
        self.assertEqual(meta["attempt_count"], 2)

    def test_process_db_job_provider_fallback_consistent_for_info_and_logs(self):
        fake_job = SimpleNamespace(
            id=7,
            status="running",
            job_type="source_library_run",
            params={"item_key": "handler.cluster.rss", "project_key": "demo_proj"},
            started_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
            error=None,
            external_provider="scrapyd",
            external_job_id="spider-job-77",
            retry_count=1,
        )

        with patch("app.api.process._resolve_db_job", return_value=fake_job):
            info_resp = process_api.get_task_info("db-job-7")
            logs_resp = process_api.get_task_logs("db-job-7", tail=50)

        self.assertEqual(info_resp["status"], "ok")
        info = info_resp["data"]
        self.assertEqual(info["task_id"], "db-job-7")
        self.assertEqual(info["worker"], "external-provider")
        self.assertFalse(info["ready"])
        self.assertEqual(info["external_provider"], "scrapyd")
        self.assertEqual(info["external_job_id"], "spider-job-77")
        self.assertEqual(info["progress"]["external_provider"], "scrapyd")
        self.assertEqual(info["progress"]["external_job_id"], "spider-job-77")

        self.assertEqual(logs_resp["status"], "ok")
        logs = logs_resp["data"]
        self.assertEqual(logs["source"], "db")
        self.assertEqual(logs["log_file"], "db://etl_job_runs")
        self.assertIn("external_provider=scrapyd", logs["text"])
        self.assertIn("External provider task is DB-tracked", logs["text"])


if __name__ == "__main__":
    unittest.main()
