from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import resource_pool as resource_pool_api
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

        app = FastAPI()
        app.include_router(resource_pool_api.router, prefix="/api/v1")
        client = TestClient(app)

        with patch.object(resource_pool_api, "list_urls", list_urls_mock):
            response = client.get(
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

    def test_prompt_time_density_success_envelope(self):
        mocked_items = [
            {
                "source_domain": "example.com",
                "prompt_group_id": "pg-1",
                "bucket_time": "2026-03-05",
                "effective_new_docs": 3,
                "density": 0.3,
                "baseline_density": 0.2,
                "norm_density": 1.5,
                "dup_ratio": 0.0,
            }
        ]
        with patch("app.api.stats.query_prompt_time_density", return_value=mocked_items):
            response = self.client.get(
                "/api/v1/stats/prompt-time-density",
                params={"time_window": "7d", "bucket": "day"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["items"], mocked_items)
        self.assertEqual(body["data"]["total"], 1)

    def test_prompt_time_density_invalid_bucket_returns_422(self):
        response = self.client.get(
            "/api/v1/stats/prompt-time-density",
            params={"time_window": "7d", "bucket": "hour"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("bucket", body["error"]["message"])
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_prompt_time_density_priority_success_envelope(self):
        mocked_items = [
            {
                "source_domain": "example.com",
                "prompt_group_id": "pg-1",
                "window": "7d",
                "density": 0.2,
                "norm_density": 1.0,
                "dup_ratio": 0.0,
                "collection_priority_score": 0.6,
                "rank": 1,
            }
        ]
        with patch("app.api.stats.query_prompt_time_density_priority", return_value=mocked_items):
            response = self.client.get(
                "/api/v1/stats/prompt-time-density/priority",
                params={"candidate_windows": "7d"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["items"], mocked_items)
        self.assertEqual(body["data"]["total"], 1)

    def test_prompt_time_density_priority_invalid_candidate_returns_422(self):
        response = self.client.get(
            "/api/v1/stats/prompt-time-density/priority",
            params={"candidate_windows": "bad-window"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("candidate_windows", body["error"]["message"])
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_prompt_time_density_select_windows_success(self):
        mocked_rows = [
            {
                "source_domain": "example.com",
                "prompt_group_id": "pg-1",
                "window": "7d",
                "density": 0.2,
                "norm_density": 1.1,
                "dup_ratio": 0.1,
                "collection_priority_score": 0.8,
                "rank": 1,
            }
        ]
        with patch("app.api.stats.query_prompt_time_density_priority", return_value=mocked_rows):
            response = self.client.get(
                "/api/v1/stats/prompt-time-density/select-windows",
                params={"candidate_windows": "7d", "max_windows": 1},
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["items"][0]["window"], "7d")

    def test_prompt_time_density_cloud_runtime_failure_returns_internal_error(self):
        with patch("app.api.stats.query_prompt_time_density_cloud", side_effect=RuntimeError("cloud query failed")):
            response = self.client.get(
                "/api/v1/stats/prompt-time-density/cloud",
                params={"keyword": "ai", "time_window": "7d"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_prompt_time_density_select_windows_runtime_failure_returns_internal_error(self):
        with patch("app.api.stats.query_prompt_time_density_priority", side_effect=RuntimeError("priority query failed")):
            response = self.client.get(
                "/api/v1/stats/prompt-time-density/select-windows",
                params={"candidate_windows": "7d"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
