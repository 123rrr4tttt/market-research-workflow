from __future__ import annotations

import sys
import tempfile
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
        with (
            patch("app.api.search.hybrid_search", return_value=[{"id": "doc-1"}]),
            patch("app.api.search.get_last_used_backends", return_value=["opensearch"]),
        ):
            response = self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["query"], "market")
        self.assertEqual(body["data"]["results"], [{"id": "doc-1"}])
        self.assertEqual(body["data"]["search_backends_used"], ["opensearch_lexical"])
        self.assertEqual(body["data"]["index_backend"], "opensearch_lexical")
        self.assertFalse(body["data"]["fallback_used"])
        self.assertEqual(body["data"]["provider_trace"]["providers_used"], ["opensearch_lexical"])
        self.assertEqual(body["data"]["provider_trace"]["index_backend"], "opensearch_lexical")
        self.assertFalse(body["data"]["provider_trace"]["fallback_used"])
        self.assertEqual(body["data"]["result_groups"][0]["backend"], "opensearch_lexical")
        self.assertEqual(body["data"]["result_groups"][0]["count"], 1)
        self.assertEqual(body["data"]["index_freshness"]["contract_version"], "search.index_freshness.v1")
        self.assertEqual(body["data"]["index_freshness"]["index_backend"], "opensearch_lexical")
        self.assertTrue(body["data"]["index_freshness"]["readback_available"])
        self.assertEqual(body["data"]["index_freshness"]["freshness_state"], "available")
        self.assertEqual(
            body["data"]["provider_trace"]["index_freshness"]["freshness_state"],
            body["data"]["index_freshness"]["freshness_state"],
        )

    def test_search_passes_explicit_request_scope_to_hybrid_search(self):
        mocked_search = patch("app.api.search.hybrid_search", return_value=[{"id": "doc-1"}])
        mocked_backends = patch("app.api.search.get_last_used_backends", return_value=["opensearch"])
        with mocked_search as hybrid_mock, mocked_backends:
            response = self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        hybrid_mock.assert_called_once_with(
            "market",
            None,
            10,
            "hybrid",
            project_key="demo_proj",
        )

    def test_search_retrieval_run_readback_reads_success_response_run_id(self):
        mocked_results = [
            {
                "id": "doc-1",
                "score": 0.91,
                "backend": "opensearch",
                "source_type": "document",
                "provenance": {"source_id": "source-a", "source_reference": "documents:doc-1"},
            }
        ]

        with tempfile.TemporaryDirectory(prefix="search-api-retrieval-runs-") as tmp_dir:
            retrieval_runs_path = Path(tmp_dir) / "retrieval_runs.jsonl"
            with (
                patch("app.api.search.hybrid_search", return_value=mocked_results),
                patch("app.api.search.get_last_used_backends", return_value=["opensearch"]),
                patch.dict("os.environ", {"SEARCH_RETRIEVAL_RUNS_PATH": str(retrieval_runs_path)}),
            ):
                search_response = self.client.get(
                    "/api/v1/search",
                    params={"q": "market", "top_k": 1},
                    headers=self.headers,
                )
                run_id = search_response.json()["data"]["retrieval_run_id"]
                readback_response = self.client.get(f"/api/v1/search/runs/{run_id}", headers=self.headers)

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(readback_response.status_code, 200)
        data = readback_response.json()["data"]
        self.assertEqual(data["retrieval_run_id"], run_id)
        self.assertEqual(data["retrieval_run"]["run_id"], run_id)
        self.assertEqual(data["source_query"]["query"], "market")
        self.assertEqual(data["source_refs"][0]["type"], "search_retrieval_run")
        self.assertEqual(data["source_refs"][1]["type"], "search_evidence_hit")
        self.assertEqual(data["source_refs"][1]["source_id"], "source-a")
        self.assertEqual(data["provider_trace"]["retrieval_run_id"], run_id)
        self.assertEqual(data["index_freshness"]["retrieval_run_id"], run_id)
        self.assertTrue(data["retrieval_run_readback"]["readback_available"])

    def test_search_retrieval_run_readback_errors_are_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="search-api-retrieval-runs-") as tmp_dir:
            missing_store_path = Path(tmp_dir) / "missing.jsonl"
            with patch.dict("os.environ", {"SEARCH_RETRIEVAL_RUNS_PATH": str(missing_store_path)}):
                invalid = self.client.get("/api/v1/search/runs/%20", headers=self.headers)
                missing_store = self.client.get("/api/v1/search/runs/retrieval_run_missing", headers=self.headers)

            retrieval_runs_path = Path(tmp_dir) / "retrieval_runs.jsonl"
            with (
                patch("app.api.search.hybrid_search", return_value=[{"id": "doc-1"}]),
                patch("app.api.search.get_last_used_backends", return_value=["opensearch"]),
                patch.dict("os.environ", {"SEARCH_RETRIEVAL_RUNS_PATH": str(retrieval_runs_path)}),
            ):
                self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)
                not_found = self.client.get("/api/v1/search/runs/retrieval_run_not_found", headers=self.headers)

            corrupt_path = Path(tmp_dir) / "corrupt.jsonl"
            corrupt_path.write_text("{not-json}\n", encoding="utf-8")
            with patch.dict("os.environ", {"SEARCH_RETRIEVAL_RUNS_PATH": str(corrupt_path)}):
                corrupt = self.client.get("/api/v1/search/runs/retrieval_run_corrupt", headers=self.headers)

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        self.assertEqual(missing_store.status_code, 404)
        self.assertEqual(missing_store.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)
        self.assertEqual(corrupt.status_code, 500)
        self.assertEqual(corrupt.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

    def test_search_fallback_index_freshness_handles_unavailable_readback(self):
        with (
            patch(
                "app.api.search.hybrid_search",
                return_value=[
                    {
                        "id": "doc-fallback",
                        "backend": "pgvector",
                        "source_type": "document",
                        "provenance": {"source_id": "fallback-source"},
                    }
                ],
            ),
            patch("app.api.search.get_last_used_backends", return_value=["pgvector"]),
            patch(
                "app.api.search.persist_search_retrieval_run_record",
                return_value={
                    "contract_version": "search_retrieval_run_readback.v1",
                    "status": "failed",
                    "readback_available": False,
                    "branch_count": 0,
                    "hit_count": 0,
                },
            ),
        ):
            response = self.client.get("/api/v1/search", params={"q": "market"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["index_backend"], "pgvector_fallback")
        self.assertTrue(body["data"]["fallback_used"])
        self.assertFalse(body["data"]["index_freshness"]["readback_available"])
        self.assertEqual(body["data"]["index_freshness"]["freshness_state"], "fallback_unknown")
        self.assertTrue(body["data"]["index_freshness"]["fallback_used"])
        self.assertEqual(body["data"]["result_groups"][0]["backend"], "pgvector_fallback")
        self.assertEqual(body["data"]["result_groups"][0]["source_type"], "document")
        self.assertEqual(
            body["data"]["provider_trace"]["index_freshness"]["readback_available"],
            body["data"]["index_freshness"]["readback_available"],
        )

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
