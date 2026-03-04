from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.contract, pytest.mark.mocked]

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _TrackedTasks:
    def __init__(self) -> None:
        self.task_run_source_library_item = SimpleNamespace(
            delay=Mock(return_value=SimpleNamespace(id="crawler-deploy-task-1"))
        )


class CrawlerManagementApiContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"crawler management contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {
            "X-Project-Key": "demo_proj",
            "X-Request-Id": "crawler-management-contract",
        }

    def _assert_envelope(self, body: dict) -> None:
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))

    def test_import_endpoint_sync_returns_enveloped_result_with_mocked_service(self):
        with patch("app.services.source_library.sync_shared_library_from_files", return_value={"synced": 2, "updated": 1}) as sync:
            resp = self.client.post("/api/v1/ingest/source-library/sync", json={}, headers=self.headers)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"], {"ok": True, "synced": 2, "updated": 1})
        sync.assert_called_once_with()

    def test_deploy_endpoint_run_async_returns_task_contract_with_mocked_tasks(self):
        tasks = _TrackedTasks()
        payload = {
            "item_key": "crawler.demo.item",
            "project_key": "demo_proj",
            "async_mode": True,
            "override_params": {"provider": "scrapy", "spider": "market_spider"},
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["task_id"], "crawler-deploy-task-1")
        self.assertEqual(body["data"]["status"], "queued")
        self.assertTrue(body["data"]["async"])
        self.assertEqual(body["data"]["params"], {"item_key": "crawler.demo.item", "execution_mode": "apply"})

        tasks.task_run_source_library_item.delay.assert_called_once_with(
            "crawler.demo.item",
            "demo_proj",
            {
                "provider": "scrapy",
                "spider": "market_spider",
                "execution_mode": "apply",
                "_trace_id": "crawler-management-contract",
            },
        )


if __name__ == "__main__":
    unittest.main()
