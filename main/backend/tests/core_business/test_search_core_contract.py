from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.contract, pytest.mark.unit]

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.services.search.vector_contracts import (
        GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
        SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SearchCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"search core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {
            "X-Project-Key": "demo_proj",
            "X-Request-Id": "search-core-contract",
        }

    def _assert_envelope_fields(self, payload: dict):
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))

    def test_search_success_envelope_complete(self):
        mocked_results = [{"id": "doc-1", "score": 0.91}, {"id": "doc-2", "score": 0.73}]

        with tempfile.TemporaryDirectory(prefix="search-core-retrieval-runs-") as tmp_dir:
            retrieval_runs_path = Path(tmp_dir) / "retrieval_runs.jsonl"
            with (
                patch("app.api.search.hybrid_search", return_value=mocked_results),
                patch(
                    "app.api.search.get_last_used_backends",
                    return_value=["opensearch", "qdrant", "pgvector", "custom"],
                ),
                patch.dict("os.environ", {"SEARCH_RETRIEVAL_RUNS_PATH": str(retrieval_runs_path)}),
            ):
                response = self.client.get(
                    "/api/v1/search",
                    params={"q": "market", "state": "CA", "modality": "text", "rank": "hybrid", "top_k": 2},
                    headers=self.headers,
                )
            self.assertTrue(retrieval_runs_path.is_file())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self._assert_envelope_fields(body)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])

        self.assertEqual(body["data"]["query"], "market")
        self.assertEqual(body["data"]["state"], "CA")
        self.assertEqual(body["data"]["modality"], "text")
        self.assertEqual(body["data"]["rank"], "hybrid")
        self.assertEqual(body["data"]["top_k"], 2)
        self.assertEqual(body["data"]["results"], mocked_results)
        self.assertEqual(body["data"]["document_query_contract_version"], "document_queries.v1")
        self.assertEqual(body["data"]["document_query"]["consumer"], "api.search")
        self.assertEqual(body["data"]["document_query"]["project_key"], "demo_proj")
        self.assertEqual(body["data"]["document_query"]["filters"], [{"field": "state", "op": "eq", "value": "CA"}])
        self.assertEqual(body["data"]["document_query"]["limit"], 2)
        self.assertEqual(body["data"]["document_query_results"][0]["source_type"], "document")
        self.assertEqual(body["data"]["document_query_results"][0]["rank"], 1)
        self.assertEqual(body["data"]["document_query_pagination"]["result_count"], 2)
        self.assertEqual(body["data"]["document_query_meta"]["source"], "api.search.hybrid")
        self.assertEqual(
            body["data"]["global_vector_object_contract_version"],
            GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
        )
        self.assertEqual(body["data"]["evidence_hit_contract_version"], SEARCH_EVIDENCE_HIT_CONTRACT_VERSION)
        self.assertTrue(body["data"]["query_group_id"].startswith("qg_"))
        self.assertEqual(len(body["data"]["evidence_hits"]), 2)
        self.assertEqual(body["data"]["evidence_hits"][0]["rank"], 1)
        self.assertEqual(body["data"]["evidence_hits"][0]["retrieval_family"], "main_search")
        self.assertEqual(body["data"]["retrieval_run"]["query_group_id"], body["data"]["query_group_id"])
        self.assertEqual(body["data"]["retrieval_run"]["retrieval_family"], "main_search")
        self.assertEqual(len(body["data"]["retrieval_run"]["evidence_hits"]), 2)
        self.assertGreaterEqual(len(body["data"]["retrieval_run"]["branch_records"]), 1)
        self.assertTrue(body["data"]["retrieval_run_id"].startswith("retrieval_run_"))
        self.assertEqual(body["data"]["search_branches"], body["data"]["retrieval_run"]["retrieval_branches"])
        self.assertEqual(body["data"]["branch_hit_details"], body["data"]["retrieval_run"]["retrieval_hits"])
        self.assertEqual(body["data"]["retrieval_run_readback"]["status"], "passed")
        self.assertTrue(body["data"]["retrieval_run_readback"]["readback_available"])
        self.assertEqual(
            body["data"]["search_backends_used"],
            ["opensearch_lexical", "qdrant_vector", "pgvector_fallback", "custom"],
        )

        self.assertIsInstance(body["meta"], dict)
        self.assertTrue({"trace_id", "pagination", "project_key", "deprecated"}.issubset(body["meta"].keys()))

    def test_search_upstream_error_envelope_complete(self):
        with patch("app.api.search.hybrid_search", side_effect=RuntimeError("Elasticsearch Connection refused")):
            response = self.client.get(
                "/api/v1/search",
                params={"q": "market", "top_k": 1},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

        body = response.json()
        self._assert_envelope_fields(body)
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["data"])
        self.assertEqual(body["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertIn("Elasticsearch服务不可用", body["error"]["message"])
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)

    def test_search_internal_error_envelope_complete(self):
        with patch("app.api.search.hybrid_search", side_effect=RuntimeError("boom")):
            response = self.client.get(
                "/api/v1/search",
                params={"q": "market", "top_k": 1},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)

        body = response.json()
        self._assert_envelope_fields(body)
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["data"])
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertIn("搜索失败: boom", body["error"]["message"])
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)

    def test_search_init_indices_success_envelope_complete(self):
        with (
            patch("app.api.search.get_es_client", return_value=object()),
            patch("app.api.search.ensure_indices", return_value={"created": ["documents"], "exists": ["reports"]}),
        ):
            response = self.client.post("/api/v1/search/_init", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self._assert_envelope_fields(body)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["created"], ["documents"])
        self.assertEqual(body["data"]["exists"], ["reports"])


if __name__ == "__main__":
    unittest.main()
