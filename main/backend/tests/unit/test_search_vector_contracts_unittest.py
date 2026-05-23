from __future__ import annotations

import unittest

import pytest

from app.services.search.vector_contracts import (
    GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
    SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    build_search_evidence_hits,
    validate_search_evidence_hit,
)


pytestmark = pytest.mark.unit


class SearchVectorContractsUnitTestCase(unittest.TestCase):
    def test_builder_aligns_bm25_qdrant_and_pgvector_rows_to_evidence_hit_schema(self) -> None:
        query_group_id, hits = build_search_evidence_hits(
            [
                {
                    "document_id": 7,
                    "project_key": "demo_proj",
                    "object_type": "policy_chunk",
                    "object_id": 7,
                    "chunk_index": 0,
                    "source_id": "source-policy",
                    "vector_version": "v2",
                    "embedding_model": "text-embedding-3-large",
                    "embedding_dim": 3072,
                    "score": 4.2,
                    "backend": "opensearch",
                    "mode": "bm25",
                    "source_uri": "https://example.org/policy/7",
                    "source_domain": "example.org",
                    "effective_time": "2026-03-03",
                    "language": "en",
                },
                {
                    "document_id": 8,
                    "project_key": "demo_proj",
                    "object_type": "policy_chunk",
                    "object_id": 8,
                    "chunk_id": "policy-8-chunk-0",
                    "source_id": "source-policy",
                    "vector_version": "v2",
                    "score": 0.91,
                    "backend": "qdrant",
                    "mode": "vector",
                },
                {
                    "document_id": 9,
                    "object_type": "policy_chunk",
                    "object_id": 9,
                    "score": 0.77,
                    "backend": "pgvector",
                    "mode": "vector",
                    "tags": ["vector", "pgvector", "fallback"],
                },
            ],
            query="market trend",
            project_key="demo_proj",
            rank_mode="hybrid",
            state="CA",
            modality="text",
            top_k=3,
        )

        self.assertTrue(query_group_id.startswith("qg_"))
        self.assertEqual(len(hits), 3)
        backends = [hit["backend"] for hit in hits]
        self.assertEqual(backends, ["opensearch_lexical", "qdrant_vector", "pgvector_fallback"])

        for index, hit in enumerate(hits, start=1):
            validate_search_evidence_hit(hit)
            self.assertEqual(hit["contract_version"], SEARCH_EVIDENCE_HIT_CONTRACT_VERSION)
            self.assertEqual(hit["rank"], index)
            self.assertEqual(hit["query_group_id"], query_group_id)
            self.assertEqual(hit["retrieval_family"], "main_search")
            self.assertTrue(hit["matrix_branch_id"].startswith("branch_"))
            self.assertEqual(hit["global_vector_object"]["contract_version"], GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION)
            self.assertEqual(hit["global_vector_object"]["project_key"], "demo_proj")
            self.assertEqual(hit["provenance"]["project_key"], "demo_proj")
            self.assertIn("rank", hit["rank_features"])

        self.assertEqual(hits[0]["retrieval_mode"], "keyword")
        self.assertEqual(hits[0]["global_vector_object"]["chunk_id"], "7:chunk:0")
        self.assertEqual(hits[1]["global_vector_object"]["chunk_id"], "policy-8-chunk-0")
        self.assertEqual(hits[2]["verification_state"], "fallback")
        self.assertEqual(hits[2]["global_vector_object"]["vector_version"], "v1")

    def test_validator_rejects_missing_global_vector_object_field(self) -> None:
        _, hits = build_search_evidence_hits(
            [{"document_id": "doc-1", "score": 0.5, "mode": "vector", "backend": "qdrant"}],
            query="market",
            project_key="demo_proj",
        )
        broken = dict(hits[0])
        broken["global_vector_object"] = dict(broken["global_vector_object"])
        del broken["global_vector_object"]["chunk_id"]

        with self.assertRaisesRegex(ValueError, "global_vector_object_missing_fields:chunk_id"):
            validate_search_evidence_hit(broken)


if __name__ == "__main__":
    unittest.main()
