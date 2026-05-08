from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


class KeywordsApiContractIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"keywords integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "keywords-contract"}

    def test_keywords_stats_success_returns_standard_ok_envelope(self):
        with patch("app.api.keywords.keyword_memory_stats", return_value={"history_total": 3, "priors_total": 2}):
            response = self.client.get("/api/v1/keywords/stats", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["history_total"], 3)
        self.assertIsNone(payload["error"])

    def test_keywords_history_validation_error_returns_invalid_input_envelope(self):
        response = self.client.get("/api/v1/keywords/history", params={"limit": 0}, headers=self.headers)

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_keywords_priors_validation_error_returns_invalid_input_envelope(self):
        response = self.client.get("/api/v1/keywords/priors", params={"limit": 1001}, headers=self.headers)

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_keywords_upsert_validation_error_returns_invalid_input_envelope(self):
        response = self.client.post(
            "/api/v1/keywords/priors/upsert",
            json={"keyword": "", "prior_score": 0.5, "confidence": 0.5},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_keywords_stats_runtime_error_returns_internal_error_envelope(self):
        with patch("app.api.keywords.keyword_memory_stats", side_effect=RuntimeError("keyword stats exploded")):
            response = self.client.get("/api/v1/keywords/stats", headers=self.headers)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_keywords_priors_runtime_error_returns_internal_error_envelope(self):
        with patch("app.api.keywords.list_keyword_priors", side_effect=RuntimeError("priors exploded")):
            response = self.client.get("/api/v1/keywords/priors", params={"limit": 10}, headers=self.headers)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
