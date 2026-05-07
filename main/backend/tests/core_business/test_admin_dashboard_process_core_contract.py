from __future__ import annotations

import json
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
        match self._execute_count:
            case 1:
                return _FakeResult(scalar_value=10)  # doc_total
            case 2:
                return _FakeResult(scalar_value=2)  # doc_recent_today
            case 3:
                return _FakeResult(scalar_value=4)  # doc_recent_7d
            case 4:
                return _FakeResult(scalar_value=3)  # source_total
            case 5:
                return _FakeResult(scalar_value=2)  # source_enabled
            case 6:
                return _FakeResult(scalar_value=8)  # market_total
            case 7:
                return _FakeResult(scalar_value=5)  # states_count
            case 8:
                return _FakeResult(scalar_value=7)  # history_total
            case 9:
                return _FakeResult(scalar_value=9)  # task_total
            case 10:
                return _FakeResult(scalar_value=1)  # task_running
            case 11:
                return _FakeResult(scalar_value=6)  # task_completed
            case 12:
                return _FakeResult(scalar_value=2)  # task_failed
            case 13:
                rows = [SimpleNamespace(doc_type="policy", count=6), SimpleNamespace(doc_type="news", count=4)]
                return _FakeResult(all_value=rows)  # doc_type_dist
            case 14:
                return _FakeResult(scalar_value=5)  # doc_with_extracted
            case _:
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


class _FakeResultNone:
    def scalar_one_or_none(self):
        return None


class _FakeResultDoc:
    def __init__(self, doc):
        self._doc = doc

    def scalar_one_or_none(self):
        return self._doc


class _FakeAdminSession:
    def __init__(self, doc=None):
        self._doc = doc

    def execute(self, _query):
        return _FakeResultDoc(self._doc) if self._doc is not None else _FakeResultNone()

    def commit(self):
        return None


class _FakeAdminSessionLocal:
    def __init__(self, doc=None):
        self._doc = doc

    def __enter__(self):
        return _FakeAdminSession(self._doc)

    def __exit__(self, exc_type, exc, tb):
        return False


class AdminDashboardProcessCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "core-contract-h"}

    def test_admin_raw_import_success_returns_envelope(self):
        mock_delay = Mock(return_value=SimpleNamespace(id="task-123"))
        fake_tasks_module = SimpleNamespace(task_raw_import_documents=SimpleNamespace(delay=mock_delay))

        with patch("app.api.admin._tasks_module", return_value=fake_tasks_module):
            resp = self.client.post(
                "/api/v1/admin/documents/raw-import",
                headers=self.headers,
                json={
                    "items": [{"text": "hello"}],
                    "source_name": "manual",
                    "async_mode": True,
                },
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["async"], True)
        self.assertEqual(body["data"]["task_id"], "task-123")

    def test_admin_raw_import_http_exception_maps_to_rate_limited(self):
        mock_delay = Mock(side_effect=HTTPException(status_code=429, detail="too many requests"))
        fake_tasks_module = SimpleNamespace(task_raw_import_documents=SimpleNamespace(delay=mock_delay))

        with patch("app.api.admin._tasks_module", return_value=fake_tasks_module):
            resp = self.client.post(
                "/api/v1/admin/documents/raw-import",
                headers=self.headers,
                json={
                    "items": [{"text": "hello"}],
                    "source_name": "manual",
                    "async_mode": True,
                },
            )

        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.RATE_LIMITED.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.RATE_LIMITED.value)

    def test_dashboard_stats_success_returns_envelope(self):
        with patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalOk()):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["documents"]["total"], 10)
        self.assertEqual(body["data"]["documents"]["extraction_rate"], 50.0)

    def test_dashboard_stats_db_failure_maps_to_upstream_error(self):
        with patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalOperationalError()):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_admin_get_document_not_found_returns_error_envelope(self):
        with patch("app.api.admin.SessionLocal", return_value=_FakeAdminSessionLocal()):
            resp = self.client.get("/api/v1/admin/documents/999", headers=self.headers)

        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_admin_update_document_invalid_merge_returns_error_envelope(self):
        doc = SimpleNamespace(id=1, extracted_data="raw")
        with patch("app.api.admin.SessionLocal", return_value=_FakeAdminSessionLocal(doc)):
            resp = self.client.post(
                "/api/v1/admin/documents/1/extracted-data",
                headers=self.headers,
                json={"mode": "merge", "extracted_data": {"a": 1}},
            )

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_bulk_update_requires_doc_ids_returns_error_envelope(self):
        from app.api.admin import BulkUpdateExtractedDataRequest, bulk_update_document_extracted_data

        resp = bulk_update_document_extracted_data(
            BulkUpdateExtractedDataRequest(doc_ids=[], mode="replace", extracted_data={})
        )

        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_export_graph_empty_doc_ids_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/export-graph?doc_ids=", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_export_graph_invalid_doc_ids_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/export-graph?doc_ids=1,abc", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_content_graph_invalid_start_date_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/content-graph?start_date=not-a-date&limit=10", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["details"]["field"], "start_date")
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_market_graph_invalid_start_date_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/market-graph?start_date=2026-13-99&limit=10", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["details"]["field"], "start_date")
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_policy_graph_invalid_end_date_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/policy-graph?end_date=bad-date&limit=10", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["details"]["field"], "end_date")
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_dashboard_ecom_price_trends_invalid_start_date_returns_422_invalid_input(self):
        resp = self.client.get(
            "/api/v1/dashboard/ecom-price-trends",
            headers=self.headers,
            params={"start_date": "2026-01-01"},
        )

        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("start_date", body["error"]["message"])
        self.assertIn("ISO8601 datetime", body["error"]["message"])
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_process_stats_success_returns_envelope(self):
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
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
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
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
