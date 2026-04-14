from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import pytest

    pytestmark = pytest.mark.integration
except Exception:  # noqa: BLE001
    pytestmark = []

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class DeepHealthDbDegradedIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"deep health integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_deep_health_returns_degraded_when_database_check_fails(self):
        headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "deep-health-db-fail-it"}
        with patch("app.main.engine.connect", side_effect=RuntimeError("db unavailable")):
            response = self.client.get("/api/v1/health/deep", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database"], "error: RuntimeError")
        self.assertIn("elasticsearch", payload)

    def test_deep_health_returns_degraded_when_pool_is_exhausted(self):
        headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "deep-health-pool-exhausted-it"}
        fake_conn = MagicMock()
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_conn
        fake_ctx.__exit__.return_value = None

        fake_es = MagicMock()
        fake_es.ping.return_value = True

        with (
            patch("app.main.engine.connect", return_value=fake_ctx),
            patch("app.main.get_es_client", return_value=fake_es),
            patch("app.main.get_db_pool_status", return_value={"size": 2, "checkedout": 2}),
            patch("app.main.settings.db_pool_max_overflow", 0),
            patch("app.main.settings.deep_health_pool_gate_enabled", True),
            patch("app.main.settings.deep_health_pool_exhaustion_ratio", 1.0),
        ):
            response = self.client.get("/api/v1/health/deep", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database"], "ok")
        self.assertEqual(payload["database_pool"], "error: pool_exhausted")
        self.assertEqual(payload["elasticsearch"], "ok")
        self.assertIn("database_pool_gate", payload["details"])
        self.assertEqual(payload["details"]["database_pool_gate"]["exhaustion_ratio"], 1.0)

    def test_deep_health_pool_gate_can_be_tuned_by_ratio(self):
        headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "deep-health-pool-ratio-it"}
        fake_conn = MagicMock()
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_conn
        fake_ctx.__exit__.return_value = None

        fake_es = MagicMock()
        fake_es.ping.return_value = True

        with (
            patch("app.main.engine.connect", return_value=fake_ctx),
            patch("app.main.get_es_client", return_value=fake_es),
            patch("app.main.get_db_pool_status", return_value={"size": 10, "checkedout": 8}),
            patch("app.main.settings.db_pool_max_overflow", 0),
            patch("app.main.settings.deep_health_pool_gate_enabled", True),
            patch("app.main.settings.deep_health_pool_exhaustion_ratio", 0.8),
        ):
            response = self.client.get("/api/v1/health/deep", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database_pool"], "error: pool_exhausted")
        self.assertEqual(payload["details"]["database_pool_gate"]["exhaustion_threshold"], 8)


if __name__ == "__main__":
    unittest.main()
