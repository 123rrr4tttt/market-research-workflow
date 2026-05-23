from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app
    from app.models.entities import Embedding
    from app.services.search.hybrid import qdrant_vector_search, vector_search
    from app.services.search.vector_contracts import SEARCH_EVIDENCE_HIT_CONTRACT_VERSION

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeEmbeddingsClient:
    def embed_query(self, _query: str):
        return [0.1, 0.2, 0.3]


class _FakeSession:
    def execute(self, _stmt):
        doc = SimpleNamespace(
            id=101,
            source_id=202,
            title="vector title",
            summary="vector summary",
            content="vector content",
            state="CA",
            publish_date=None,
            uri="https://example.org/vector/101",
        )
        emb = SimpleNamespace(
            object_id=101,
            object_type="policy_chunk",
            vector=[0.1, 0.2, 0.3],
            dim=3,
            provider="openai",
            model="test-embedding-model",
        )
        return SimpleNamespace(all=lambda: [(emb, doc)])


class _FakeSessionLocal:
    def __enter__(self):
        return _FakeSession()

    def __exit__(self, exc_type, exc, tb):
        return False


class VectorizationContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"vectorization contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "vector-contract"}

    def test_embedding_model_contract_keeps_compatibility_fields(self):
        columns = Embedding.__table__.columns

        expected = {
            "object_id",
            "object_type",
            "modality",
            "vector",
            "dim",
            "provider",
            "model",
            "created_at",
        }
        self.assertTrue(expected.issubset(set(columns.keys())))

        self.assertEqual(str(columns["dim"].server_default.arg), "3072")
        self.assertEqual(str(columns["provider"].server_default.arg), "openai")
        self.assertEqual(str(columns["model"].server_default.arg), "text-embedding-3-large")
        self.assertIn("vector", str(columns["vector"].type).lower())
        self.assertIn("3072", str(columns["vector"].type))

    def test_vector_search_output_shape_contract(self):
        with (
            patch(
                "app.services.search.hybrid.qdrant_vector_search",
                side_effect=RuntimeError("qdrant_unavailable: deterministic test fallback"),
            ),
            patch("app.services.search.hybrid.get_embeddings", return_value=_FakeEmbeddingsClient()),
            patch("app.services.search.hybrid.SessionLocal", return_value=_FakeSessionLocal()),
        ):
            results = vector_search("market trend", "CA", 3)

        self.assertEqual(len(results), 1)
        row = results[0]
        expected_keys = {
            "document_id",
            "score",
            "chunk_index",
            "title",
            "summary",
            "text",
            "highlight",
            "state",
            "publish_date",
            "object_type",
            "object_id",
            "vector_version",
            "embedding_model",
            "embedding_dim",
            "mode",
        }
        self.assertTrue(expected_keys.issubset(set(row.keys())))
        self.assertEqual(row["mode"], "vector")
        self.assertEqual(row["backend"], "pgvector")
        self.assertEqual(row["embedding_provider"], "openai")
        provenance = row["provenance"]
        self.assertEqual(provenance["provider"], "openai")
        self.assertEqual(provenance["backend"], "pgvector_fallback")
        self.assertEqual(provenance["embedding_model"], "test-embedding-model")
        self.assertEqual(provenance["source_reference"], "https://example.org/vector/101")
        self.assertEqual(provenance["fallback_reason"], "qdrant_unavailable: deterministic test fallback")
        self.assertIsInstance(row["highlight"], list)

    def test_qdrant_vector_search_maps_payload_provenance(self):
        class _FakeFilter:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class _FakeFieldCondition:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class _FakeMatchValue:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class _FakeQdrantClient:
            def __init__(self, **_kwargs):
                pass

            def search(self, **_kwargs):
                payload = {
                    "document_id": 303,
                    "project_key": "demo_proj",
                    "object_type": "policy_chunk",
                    "object_id": 303,
                    "chunk_id": "policy-303-chunk-0",
                    "source_id": "source-policy",
                    "vector_version": "v2",
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-large",
                    "embedding_model_version": "2026-05-embedding-manifest",
                    "embedding_dim": 3072,
                    "source_reference": "qdrant://policy_chunks/policy-303-chunk-0",
                    "source_uri": "https://example.org/vector/303",
                    "title": "qdrant title",
                    "summary": "qdrant summary",
                    "text": "qdrant body",
                }
                return [SimpleNamespace(payload=payload, score=0.91)]

        fake_qdrant_module = SimpleNamespace(QdrantClient=_FakeQdrantClient)
        fake_models_module = SimpleNamespace(
            Filter=_FakeFilter,
            FieldCondition=_FakeFieldCondition,
            MatchValue=_FakeMatchValue,
        )

        with (
            patch.dict(
                sys.modules,
                {
                    "qdrant_client": fake_qdrant_module,
                    "qdrant_client.models": fake_models_module,
                },
            ),
            patch("app.services.search.hybrid.get_embeddings", return_value=_FakeEmbeddingsClient()),
        ):
            results = qdrant_vector_search("market trend", None, 3)

        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["backend"], "qdrant")
        self.assertEqual(row["embedding_provider"], "openai")
        provenance = row["provenance"]
        self.assertEqual(provenance["provider"], "openai")
        self.assertEqual(provenance["backend"], "qdrant_vector")
        self.assertEqual(provenance["embedding_model"], "text-embedding-3-large")
        self.assertEqual(provenance["embedding_model_version"], "2026-05-embedding-manifest")
        self.assertEqual(provenance["source_reference"], "qdrant://policy_chunks/policy-303-chunk-0")
        self.assertEqual(provenance["score"], 0.91)

    def test_search_api_vector_rank_response_shape_contract(self):
        vector_like_results = [
            {
                "document_id": 101,
                "score": 0.98,
                "chunk_index": 0,
                "title": "vector title",
                "summary": "vector summary",
                "text": "vector body",
                "highlight": [],
                "state": "CA",
                "publish_date": None,
                "mode": "vector",
            }
        ]

        with patch("app.api.search.hybrid_search", return_value=vector_like_results):
            resp = self.client.get(
                "/api/v1/search",
                params={"q": "market", "rank": "vector", "modality": "text", "top_k": 5},
                headers=self.headers,
            )

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["rank"], "vector")
        self.assertEqual(body["data"]["top_k"], 5)
        self.assertIsInstance(body["data"]["results"], list)
        self.assertEqual(body["data"]["evidence_hit_contract_version"], SEARCH_EVIDENCE_HIT_CONTRACT_VERSION)
        self.assertEqual(len(body["data"]["evidence_hits"]), 1)
        evidence_hit = body["data"]["evidence_hits"][0]
        self.assertEqual(evidence_hit["retrieval_mode"], "vector")
        self.assertEqual(evidence_hit["retrieval_family"], "main_search")
        self.assertEqual(evidence_hit["global_vector_object"]["document_id"], "101")
        self.assertEqual(evidence_hit["global_vector_object"]["vector_version"], "v1")
        self.assertTrue(evidence_hit["matrix_branch_id"].startswith("branch_"))
        self.assertEqual(body["data"]["retrieval_run"]["contract_version"], "search_retrieval_run.v1")
        self.assertEqual(body["data"]["retrieval_run"]["query_group_id"], body["data"]["query_group_id"])
        self.assertEqual(body["data"]["retrieval_run"]["evidence_hits"][0]["hit_id"], evidence_hit["hit_id"])
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertTrue({"trace_id", "pagination", "project_key", "deprecated"}.issubset(body["meta"].keys()))
        self.assertTrue(set(vector_like_results[0].keys()).issubset(set(body["data"]["results"][0].keys())))


if __name__ == "__main__":
    unittest.main()
