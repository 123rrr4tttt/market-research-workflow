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
        mocked_results = [
            {
                "id": "doc-1",
                "score": 0.91,
                "backend": "opensearch",
                "source_type": "document",
                "provenance": {"source_id": "source-a"},
            },
            {
                "id": "doc-2",
                "score": 0.73,
                "backend": "qdrant",
                "source_type": "resource",
                "provenance": {"source_id": "source-b"},
            },
        ]

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
                response_body = response.json()
                readback_response = self.client.get(
                    f"/api/v1/search/runs/{response_body['data']['retrieval_run_id']}",
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
        self.assertEqual(body["data"]["index_backend"], "opensearch_lexical")
        self.assertTrue(body["data"]["fallback_used"])
        self.assertEqual(body["data"]["provider_trace"]["contract_version"], "search.provider_trace.compat.v1")
        self.assertEqual(body["data"]["provider_trace"]["retrieval_run_id"], body["data"]["retrieval_run_id"])
        self.assertEqual(body["data"]["provider_trace"]["query_group_id"], body["data"]["query_group_id"])
        self.assertEqual(body["data"]["provider_trace"]["providers_used"], body["data"]["search_backends_used"])
        self.assertEqual(body["data"]["provider_trace"]["fallback_order"], body["data"]["search_fallback_order"])
        self.assertEqual(body["data"]["provider_trace"]["index_backend"], body["data"]["index_backend"])
        self.assertEqual(body["data"]["provider_trace"]["fallback_used"], body["data"]["fallback_used"])
        self.assertEqual(body["data"]["index_freshness"]["contract_version"], "search.index_freshness.v1")
        self.assertEqual(body["data"]["index_freshness"]["index_backend"], body["data"]["index_backend"])
        self.assertTrue(body["data"]["index_freshness"]["readback_available"])
        self.assertEqual(body["data"]["index_freshness"]["freshness_state"], "fallback_available")
        self.assertTrue(body["data"]["index_freshness"]["fallback_used"])
        self.assertEqual(body["data"]["index_freshness"]["freshness_basis"], "retrieval_run_readback")
        self.assertEqual(
            body["data"]["provider_trace"]["index_freshness"]["freshness_state"],
            body["data"]["index_freshness"]["freshness_state"],
        )
        self.assertEqual(len(body["data"]["result_groups"]), 2)
        self.assertEqual(body["data"]["result_groups"][0]["backend"], "opensearch_lexical")
        self.assertEqual(body["data"]["result_groups"][0]["source_type"], "document")
        self.assertEqual(body["data"]["result_groups"][0]["count"], 1)
        self.assertTrue(body["data"]["result_groups"][0]["result_ids"][0].startswith("eh_"))
        self.assertEqual(body["data"]["result_groups"][1]["backend"], "qdrant_vector")
        self.assertEqual(body["data"]["result_groups"][1]["source_type"], "resource")
        self.assertEqual(
            body["data"]["provider_trace"]["branches"][0]["matrix_branch_id"],
            body["data"]["search_branches"][0]["matrix_branch_id"],
        )
        self.assertEqual(body["data"]["trace_chain"]["contract_version"], "ingest_search.trace_chain.v1")
        self.assertEqual(body["data"]["trace_chain"]["trace_id"], "search-core-contract")
        self.assertEqual(body["data"]["trace_chain"]["entrypoint"], "search.query")
        self.assertEqual(
            body["data"]["trace_chain"]["ids"]["retrieval_run_id"],
            body["data"]["retrieval_run_id"],
        )
        self.assertEqual(body["data"]["trace_chain"]["provider"], "opensearch_lexical")
        self.assertTrue(body["data"]["trace_chain"]["fallback"]["used"])
        self.assertEqual(
            body["data"]["trace_chain"]["fallback"]["fallback_order"],
            body["data"]["search_fallback_order"],
        )
        self.assertEqual(body["data"]["trace_chain"]["index"]["index_backend"], body["data"]["index_backend"])
        self.assertEqual(
            body["data"]["trace_chain"]["index"]["freshness_state"],
            body["data"]["index_freshness"]["freshness_state"],
        )
        self.assertFalse(body["data"]["trace_chain"]["index"]["real_timestamp_available"])
        self.assertEqual(body["data"]["trace_chain"]["run_order"][0]["stage"], "search_request")
        self.assertEqual(body["data"]["trace_chain"]["run_order"][1]["stage"], "provider_trace")
        self.assertEqual(body["data"]["trace_chain"]["run_order"][2]["stage"], "retrieval_run")
        self.assertEqual(body["data"]["trace_chain"]["run_order"][3]["stage"], "index_freshness")
        self.assertIn("no_real_index_timestamp", body["data"]["trace_chain"]["known_limitations"])

        self.assertIsInstance(body["meta"], dict)
        self.assertTrue({"trace_id", "pagination", "project_key", "deprecated"}.issubset(body["meta"].keys()))

        self.assertEqual(readback_response.status_code, 200)
        readback_body = readback_response.json()
        self._assert_envelope_fields(readback_body)
        self.assertEqual(readback_body["status"], "ok")
        self.assertIsNone(readback_body["error"])
        readback_data = readback_body["data"]
        self.assertEqual(readback_data["retrieval_run_id"], body["data"]["retrieval_run_id"])
        self.assertEqual(readback_data["retrieval_run"], body["data"]["retrieval_run"])
        self.assertEqual(readback_data["source_query"]["scope"], "search.retrieval_run")
        self.assertEqual(readback_data["source_query"]["query"], "market")
        self.assertEqual(readback_data["source_query"]["filters"]["state"], "CA")
        self.assertEqual(readback_data["source_query"]["top_k"], 2)
        self.assertEqual(readback_data["source_refs"][0]["type"], "search_retrieval_run")
        self.assertEqual(readback_data["source_refs"][0]["retrieval_run_id"], body["data"]["retrieval_run_id"])
        self.assertEqual(len(readback_data["source_refs"]), 3)
        self.assertEqual(readback_data["source_refs"][1]["source_id"], "source-a")
        self.assertEqual(readback_data["source_refs"][2]["source_id"], "source-b")
        self.assertEqual(
            readback_data["provider_trace"]["retrieval_run_id"],
            body["data"]["provider_trace"]["retrieval_run_id"],
        )
        self.assertEqual(readback_data["provider_trace"]["providers_used"], ["opensearch_lexical", "qdrant_vector"])
        self.assertEqual(readback_data["index_freshness"]["retrieval_run_id"], body["data"]["retrieval_run_id"])
        self.assertTrue(readback_data["index_freshness"]["readback_available"])
        self.assertEqual(readback_data["index_freshness"]["freshness_basis"], "retrieval_run_readback")
        self.assertEqual(readback_data["retrieval_run_readback"]["status"], "passed")
        self.assertEqual(readback_data["readback"], readback_data["retrieval_run_readback"])

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

    def test_search_retrieval_run_rejects_whitespace_id_with_exact_error_contract(self):
        response = self.client.get(
            "/api/v1/search/runs/bad%20run",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        body = response.json()
        self._assert_envelope_fields(body)
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["error"]["message"], "retrieval_run_id must not contain whitespace")
        self.assertEqual(body["error"]["details"]["field"], "retrieval_run_id")
        self.assertEqual(
            body["error"]["details"]["category"],
            "search_retrieval_run_readback",
        )
        self.assertEqual(body["detail"]["error"], body["error"])

    def test_search_retrieval_run_missing_store_keeps_not_found_contract(self):
        with patch(
            "app.api.search.read_search_retrieval_run_record",
            side_effect=FileNotFoundError("missing test store"),
        ):
            response = self.client.get(
                "/api/v1/search/runs/retrieval_run_missing",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)
        body = response.json()
        self._assert_envelope_fields(body)
        self.assertEqual(body["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["error"]["message"], "search retrieval run store is missing")
        self.assertEqual(body["error"]["details"]["retrieval_run_id"], "retrieval_run_missing")
        self.assertEqual(body["error"]["details"]["store_kind"], "local_jsonl")
        self.assertEqual(body["detail"]["error"], body["error"])

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
