from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiGroupACoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api group a contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {
            "X-Project-Key": "demo_proj",
            "X-Request-Id": "api-group-a-core-contract",
        }

    def test_source_library_channels_success_envelope(self):
        mocked_items = [{"channel_key": "news", "name": "News"}]

        with patch("app.api.source_library.list_effective_channels", return_value=mocked_items):
            response = self.client.get(
                "/api/v1/source_library/channels",
                params={"scope": "effective", "project_key": "demo_proj"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["items"], mocked_items)
        self.assertEqual(body["data"]["scope"], "effective")

    def test_resource_pool_urls_success_envelope_with_pagination(self):
        list_urls_mock = Mock(
            return_value=(
                [
                    {
                        "id": 1,
                        "url": "https://example.com/news/1",
                        "domain": "example.com",
                    }
                ],
                21,
            )
        )

        with patch("app.api.resource_pool.list_urls", list_urls_mock):
            response = self.client.get(
                "/api/v1/resource_pool/urls",
                params={
                    "project_key": "demo_proj",
                    "scope": "effective",
                    "page": 2,
                    "page_size": 10,
                    "domain": "example.com",
                },
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["items"][0]["url"], "https://example.com/news/1")
        self.assertEqual(body["meta"]["pagination"], {"page": 2, "page_size": 10, "total": 21, "total_pages": 3})
        list_urls_mock.assert_called_once_with(
            scope="effective",
            project_key="demo_proj",
            source=None,
            domain="example.com",
            page=2,
            page_size=10,
        )

    def test_search_success_envelope(self):
        mocked_results = [{"id": "doc-1", "score": 0.91}]

        with patch("app.api.search.hybrid_search", return_value=mocked_results):
            response = self.client.get(
                "/api/v1/search",
                params={"q": "market", "state": "CA", "rank": "hybrid", "top_k": 1},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["query"], "market")
        self.assertEqual(body["data"]["results"], mocked_results)

    def test_search_upstream_error_maps_to_standard_error_envelope(self):
        with patch("app.api.search.hybrid_search", side_effect=RuntimeError("Elasticsearch Connection refused")):
            response = self.client.get(
                "/api/v1/search",
                params={"q": "market", "top_k": 1},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["data"])
        self.assertEqual(body["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)


if __name__ == "__main__":
    unittest.main()
