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

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SearchApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"search integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "search-integration"}

    def test_search_success(self):
        with patch("app.api.search.hybrid_search", return_value=[{"id": "doc-1"}]):
            response = self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["query"], "market")
        self.assertEqual(body["data"]["results"], [{"id": "doc-1"}])

    def test_search_upstream_error(self):
        with patch("app.api.search.hybrid_search", side_effect=RuntimeError("Elasticsearch Connection refused")):
            response = self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_search_internal_error(self):
        with patch("app.api.search.hybrid_search", side_effect=RuntimeError("boom")):
            response = self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_search_init_indices(self):
        with (
            patch("app.api.search.get_es_client", return_value=object()),
            patch("app.api.search.ensure_indices", return_value={"created": ["documents"], "exists": []}),
        ):
            response = self.client.post("/api/v1/search/_init", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["created"], ["documents"])


if __name__ == "__main__":
    unittest.main()
