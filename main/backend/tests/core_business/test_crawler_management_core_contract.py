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

    from app.contracts.errors import ErrorCode
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
        self.assertEqual(body["data"]["params"], {"item_key": "crawler.demo.item"})

        tasks.task_run_source_library_item.delay.assert_called_once_with(
            "crawler.demo.item",
            "demo_proj",
            {"provider": "scrapy", "spider": "market_spider"},
            workflow_run_id=None,
            trace_id=None,
        )

    def test_crawler_import_invalid_input_returns_standard_error_envelope(self):
        with patch("app.api.crawler.import_project", side_effect=ValueError("invalid crawler manifest")):
            resp = self.client.post(
                "/api/v1/crawler/projects/import",
                json={"project_key": "demo", "source_type": "git", "provider": "scrapyd"},
                headers=self.headers,
            )

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_crawler_project_missing_returns_standard_not_found_envelope(self):
        with patch("app.api.crawler.get_project", return_value=None):
            resp = self.client.get("/api/v1/crawler/projects/demo-missing", headers=self.headers)

        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_crawler_list_runtime_failure_returns_internal_error(self):
        with patch("app.api.crawler.list_projects", side_effect=RuntimeError("crawler storage down")):
            resp = self.client.get("/api/v1/crawler/projects", headers=self.headers)

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
