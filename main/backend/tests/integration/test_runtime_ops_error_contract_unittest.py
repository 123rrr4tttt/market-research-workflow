from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

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

    def test_legacy_market_statistics_routes_are_retired(self):
        routes = (
            ("get", "/api/v1/market"),
            ("get", "/api/v1/market/games"),
            ("get", "/api/v1/dashboard/market-trends"),
            ("post", "/api/v1/admin/market-stats/list"),
        )
        for method, path in routes:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, headers=self.headers)
                self.assertEqual(response.status_code, 404)

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

    def test_health_reports_provider_and_environment_without_dependency_probes(self):
        with (
            patch("app.main.settings.llm_provider", "local"),
            patch("app.main.settings.env", "test"),
            patch("app.main.engine.connect") as connect,
            patch("app.main.get_db_pool_status") as pool,
            patch("app.main.get_es_client") as es,
        ):
            response = self.client.get("/api/v1/health", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "provider": "local", "env": "test"})
        connect.assert_not_called()
        pool.assert_not_called()
        es.assert_not_called()

    def test_deep_health_reports_actual_database_pool_and_es_probes(self):
        connect_context = MagicMock()
        es_client = Mock()
        es_client.ping.return_value = True
        pool_status = {"size": 5, "checkedout": 0}
        with (
            patch("app.main.engine.connect", return_value=connect_context) as connect,
            patch("app.main.get_db_pool_status", return_value=pool_status) as pool,
            patch("app.main.get_es_client", return_value=es_client) as es,
        ):
            response = self.client.get("/api/v1/health/deep", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["database"], "ok")
        self.assertEqual(payload["database_pool"], "ok")
        self.assertEqual(payload["elasticsearch"], "ok")
        self.assertEqual(payload["details"]["database_pool"], pool_status)
        for key in ("database_latency_ms", "elasticsearch_latency_ms"):
            self.assertIsInstance(payload["details"][key], (int, float))
            self.assertGreaterEqual(payload["details"][key], 0)
        connect.assert_called_once_with()
        conn = connect_context.__enter__.return_value
        conn.execute.assert_called_once()
        self.assertEqual(str(conn.execute.call_args.args[0]), "SELECT 1")
        pool.assert_called_once_with()
        es.assert_called_once_with()
        es_client.ping.assert_called_once_with()

    def test_deep_health_reports_es_ping_failure_and_exception_independently(self):
        for side_effect, ping_result, expected in (
            (None, False, "error: ping failed"),
            (RuntimeError("es unavailable"), True, "error: RuntimeError"),
        ):
            with self.subTest(expected=expected):
                connect_context = MagicMock()
                es_client = Mock()
                es_client.ping.side_effect = side_effect
                es_client.ping.return_value = ping_result
                with (
                    patch("app.main.engine.connect", return_value=connect_context),
                    patch("app.main.get_db_pool_status", return_value={"size": 5, "checkedout": 0}),
                    patch("app.main.get_es_client", return_value=es_client),
                ):
                    response = self.client.get("/api/v1/health/deep", headers=self.headers)

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["status"], "degraded")
                self.assertEqual(payload["database"], "ok")
                self.assertEqual(payload["database_pool"], "ok")
                self.assertEqual(payload["elasticsearch"], expected)
                es_client.ping.assert_called_once_with()

    def test_deep_health_reports_pool_probe_failure_independently(self):
        es_client = Mock()
        es_client.ping.return_value = True
        with (
            patch("app.main.engine.connect", return_value=MagicMock()),
            patch("app.main.get_db_pool_status", side_effect=RuntimeError("pool unavailable")),
            patch("app.main.get_es_client", return_value=es_client),
        ):
            response = self.client.get("/api/v1/health/deep", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database"], "ok")
        self.assertEqual(payload["database_pool"], "error: RuntimeError")
        self.assertEqual(payload["elasticsearch"], "ok")
        es_client.ping.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
