from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class RuntimeOpsErrorContractIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"runtime ops integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "runtime-ops-contract"}

    def test_process_list_failure_returns_structured_internal_error(self):
        inspect = SimpleNamespace(active=Mock(side_effect=RuntimeError("inspect failed")))
        with patch("app.api.process.celery_app.control.inspect", return_value=inspect):
            response = self.client.get("/api/v1/process/list", headers=self.headers)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_process_retry_non_db_job_returns_structured_invalid_input(self):
        response = self.client.post("/api/v1/process/celery-task-1/retry", headers=self.headers)

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_process_retry_missing_db_job_returns_structured_not_found(self):
        with patch("app.api.process._resolve_db_job", return_value=None):
            response = self.client.post("/api/v1/process/db-job-7/retry", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_market_stats_db_failure_returns_structured_upstream_error(self):
        class _BoomSessionLocal:
            def __enter__(self):
                raise RuntimeError("database timeout")

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("app.api.market.SessionLocal", return_value=_BoomSessionLocal()):
            response = self.client.get("/api/v1/market", params={"state": "CA"}, headers=self.headers)

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_market_stats_success_returns_standard_ok_envelope(self):
        row = SimpleNamespace(
            date=SimpleNamespace(isoformat=lambda: "2026-01-01"),
            revenue=10,
            sales_volume=20,
            jackpot=30,
            ticket_price=2,
            game="Powerball",
            source_name="src",
            source_uri="https://example.com",
        )
        query = Mock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [row]
        session = Mock()
        session.query.return_value = query

        class _SessionLocal:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("app.api.market.SessionLocal", return_value=_SessionLocal()):
            response = self.client.get("/api/v1/market", params={"state": "CA"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["state"], "CA")
        self.assertEqual(payload["data"]["series"][0]["game"], "Powerball")

    def test_market_validation_error_returns_invalid_input_envelope(self):
        response = self.client.get("/api/v1/market", params={"state": "CA", "period": "yearly"}, headers=self.headers)

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_market_games_internal_error_returns_structured_internal_error(self):
        class _BoomSessionLocal:
            def __enter__(self):
                raise RuntimeError("boom")

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("app.api.market.SessionLocal", return_value=_BoomSessionLocal()):
            response = self.client.get("/api/v1/market/games", params={"state": "CA"}, headers=self.headers)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_market_games_success_returns_standard_ok_envelope(self):
        session = Mock()
        session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [("Powerball",), ("Mega",)]

        class _SessionLocal:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("app.api.market.SessionLocal", return_value=_SessionLocal()):
            response = self.client.get("/api/v1/market/games", params={"state": "CA"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["games"], ["Powerball", "Mega"])

    def test_governance_cleanup_runtime_error_returns_structured_internal_error(self):
        with patch("app.api.governance.cleanup_old_data", side_effect=RuntimeError("cleanup failed")):
            response = self.client.post("/api/v1/governance/cleanup", json={"retention_days": 90}, headers=self.headers)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_governance_sync_aggregator_async_success_returns_ok_envelope(self):
        class _Task:
            id = "task-sync-1"

        with patch("app.api.governance.task_sync_aggregator.delay", return_value=_Task()):
            response = self.client.post("/api/v1/governance/aggregator/sync", json={"async_mode": True}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["task_id"], "task-sync-1")

    def test_governance_cleanup_validation_error_returns_invalid_input_envelope(self):
        response = self.client.post("/api/v1/governance/cleanup", json={"retention_days": 0}, headers=self.headers)

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_indexer_policy_missing_api_key_returns_structured_config_error(self):
        with patch("app.api.indexer.settings.openai_api_key", ""):
            response = self.client.post("/api/v1/indexer/policy", json={}, headers=self.headers)

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.CONFIG_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.CONFIG_ERROR.value)

    def test_indexer_policy_value_error_returns_structured_invalid_input(self):
        with (
            patch("app.api.indexer.settings.openai_api_key", "sk-test"),
            patch("app.api.indexer.index_policy_documents", side_effect=ValueError("vector_contract_missing_fields:source_domain")),
        ):
            response = self.client.post("/api/v1/indexer/policy", json={}, headers=self.headers)

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_indexer_policy_upstream_error_returns_structured_upstream_error(self):
        with (
            patch("app.api.indexer.settings.openai_api_key", "sk-test"),
            patch("app.api.indexer.index_policy_documents", side_effect=RuntimeError("database timeout")),
        ):
            response = self.client.post("/api/v1/indexer/policy", json={}, headers=self.headers)

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_indexer_policy_internal_error_returns_structured_internal_error(self):
        with (
            patch("app.api.indexer.settings.openai_api_key", "sk-test"),
            patch("app.api.indexer.index_policy_documents", side_effect=RuntimeError("boom")),
        ):
            response = self.client.post("/api/v1/indexer/policy", json={}, headers=self.headers)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
