from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

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


if __name__ == "__main__":
    unittest.main()
