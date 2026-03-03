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
    from app.services.search.hybrid import vector_search

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
            title="vector title",
            summary="vector summary",
            content="vector content",
            state="CA",
            publish_date=None,
        )
        emb = SimpleNamespace(vector=[0.1, 0.2, 0.3])
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
            "mode",
        }
        self.assertTrue(expected_keys.issubset(set(row.keys())))
        self.assertEqual(row["mode"], "vector")
        self.assertIsInstance(row["highlight"], list)

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
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertTrue({"trace_id", "pagination", "project_key", "deprecated"}.issubset(body["meta"].keys()))
        self.assertTrue(set(vector_like_results[0].keys()).issubset(set(body["data"]["results"][0].keys())))


if __name__ == "__main__":
    unittest.main()
