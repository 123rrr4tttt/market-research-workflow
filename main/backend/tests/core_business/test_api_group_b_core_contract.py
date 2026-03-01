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
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeResult:
    def __init__(self, scalar_value=None, all_value=None):
        self._scalar_value = scalar_value
        self._all_value = all_value

    def scalar(self):
        return self._scalar_value

    def all(self):
        return self._all_value


class _FakeDashboardSession:
    def __init__(self):
        self._execute_count = 0

    def execute(self, _query):
        self._execute_count += 1
        if self._execute_count == 1:
            return _FakeResult(scalar_value=12)  # doc_total
        if self._execute_count == 2:
            return _FakeResult(scalar_value=3)  # doc_recent_today
        if self._execute_count == 3:
            return _FakeResult(scalar_value=5)  # doc_recent_7d
        if self._execute_count == 4:
            return _FakeResult(scalar_value=4)  # source_total
        if self._execute_count == 5:
            return _FakeResult(scalar_value=3)  # source_enabled
        if self._execute_count == 6:
            return _FakeResult(scalar_value=9)  # market_total
        if self._execute_count == 7:
            return _FakeResult(scalar_value=6)  # states_count
        if self._execute_count == 8:
            return _FakeResult(scalar_value=7)  # history_total
        if self._execute_count == 9:
            return _FakeResult(scalar_value=10)  # task_total
        if self._execute_count == 10:
            return _FakeResult(scalar_value=2)  # task_running
        if self._execute_count == 11:
            return _FakeResult(scalar_value=6)  # task_completed
        if self._execute_count == 12:
            return _FakeResult(scalar_value=2)  # task_failed
        if self._execute_count == 13:
            rows = [SimpleNamespace(doc_type="policy", count=7), SimpleNamespace(doc_type="news", count=5)]
            return _FakeResult(all_value=rows)
        if self._execute_count == 14:
            return _FakeResult(scalar_value=6)  # doc_with_extracted
        return _FakeResult(scalar_value=0)


class _FakeSessionLocalOk:
    def __enter__(self):
        return _FakeDashboardSession()

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSessionLocalOperationalError:
    def __enter__(self):
        raise Exception("database timeout")

    def __exit__(self, exc_type, exc, tb):
        return False


class _TrackedIngestTasks:
    def __init__(self):
        self.task_ingest_policy = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="policy-task-2")))
        self.task_ingest_market = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="market-task-2")))
        self.task_run_source_library_item = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="source-library-task-2")))


class ApiGroupBCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"group-b core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {
            "X-Project-Key": "demo_proj",
            "X-Request-Id": "api-group-b-core-contract",
        }

    def _assert_envelope(self, body: dict):
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))

    def test_admin_raw_import_async_success_contract(self):
        mock_delay = Mock(return_value=SimpleNamespace(id="admin-raw-import-task-1"))
        fake_tasks_module = SimpleNamespace(task_raw_import_documents=SimpleNamespace(delay=mock_delay))

        with patch("app.api.admin._tasks_module", return_value=fake_tasks_module):
            resp = self.client.post(
                "/api/v1/admin/documents/raw-import",
                headers=self.headers,
                json={
                    "items": [{"text": "hello group b"}],
                    "source_name": "manual",
                    "async_mode": True,
                },
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertTrue(body["data"]["async"])
        self.assertEqual(body["data"]["task_id"], "admin-raw-import-task-1")

    def test_admin_raw_import_rate_limited_error_contract(self):
        mock_delay = Mock(side_effect=HTTPException(status_code=429, detail="too many requests"))
        fake_tasks_module = SimpleNamespace(task_raw_import_documents=SimpleNamespace(delay=mock_delay))

        with patch("app.api.admin._tasks_module", return_value=fake_tasks_module):
            resp = self.client.post(
                "/api/v1/admin/documents/raw-import",
                headers=self.headers,
                json={
                    "items": [{"text": "hello group b"}],
                    "source_name": "manual",
                    "async_mode": True,
                },
            )

        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.RATE_LIMITED.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.RATE_LIMITED.value)

    def test_dashboard_stats_success_contract(self):
        with patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalOk()):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["documents"]["total"], 12)
        self.assertEqual(body["data"]["documents"]["extraction_rate"], 50.0)

    def test_dashboard_stats_db_failure_maps_to_upstream_error(self):
        with patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalOperationalError()):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_process_stats_success_contract(self):
        inspect = SimpleNamespace(
            active=lambda: {"w1": [{"id": "a1"}]},
            registered=lambda: {"w1": ["task.alpha", "task.beta"]},
            scheduled=lambda: {"w1": [{"request": {"id": "s1"}}]},
            reserved=lambda: {"w1": [{"id": "r1"}]},
        )

        with patch("app.api.process.celery_app.control.inspect", return_value=inspect):
            resp = self.client.get("/api/v1/process/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["active_tasks"], 1)
        self.assertEqual(body["data"]["total_running"], 3)

    def test_process_stats_failure_maps_to_internal_error(self):
        inspect = SimpleNamespace(
            active=Mock(side_effect=RuntimeError("inspect failed")),
            registered=lambda: {},
            scheduled=lambda: {},
            reserved=lambda: {},
        )

        with patch("app.api.process.celery_app.control.inspect", return_value=inspect):
            resp = self.client.get("/api/v1/process/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_ingest_policy_async_success_contract(self):
        tasks = _TrackedIngestTasks()
        payload = {
            "state": "CA",
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/policy", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["task_id"], "policy-task-2")
        self.assertEqual(body["data"]["status"], "queued")
        self.assertTrue(body["data"]["async"])
        self.assertEqual(body["data"]["params"], {"state": "CA"})
        tasks.task_ingest_policy.delay.assert_called_once_with("CA", "demo_proj")

    def test_ingest_market_rejects_empty_query_terms(self):
        tasks = _TrackedIngestTasks()
        payload = {
            "query_terms": [],
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/market", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        tasks.task_ingest_market.delay.assert_not_called()

    def test_ingest_source_library_conflict_identifiers_invalid_input(self):
        tasks = _TrackedIngestTasks()
        payload = {
            "project_key": "demo_proj",
            "item_key": "demo-item",
            "handler_key": "news",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self._assert_envelope(body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        tasks.task_run_source_library_item.delay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
