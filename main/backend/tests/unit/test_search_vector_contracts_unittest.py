from __future__ import annotations

import unittest

import pytest

from app.services.search.vector_contracts import (
    AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION,
    GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
    SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    build_agent_matrix_evidence_hits,
    build_retrieval_run_record,
    build_search_evidence_hits,
    load_retrieval_run_record,
    serialize_retrieval_run_record,
    validate_retrieval_run_record,
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
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-large",
                    "embedding_model_version": "2026-05-embedding-manifest",
                    "embedding_dim": 3072,
                    "score": 0.91,
                    "backend": "qdrant",
                    "mode": "vector",
                    "source_reference": "qdrant://policy_chunks/policy-8-chunk-0",
                },
                {
                    "document_id": 9,
                    "object_type": "policy_chunk",
                    "object_id": 9,
                    "source_id": "source-policy",
                    "vector_version": "v1",
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_model_version": "2026-05-embedding-manifest",
                    "embedding_dim": 1536,
                    "score": 0.77,
                    "backend": "pgvector",
                    "mode": "vector",
                    "source_reference": "postgres://embeddings/9",
                    "fallback_reason": "qdrant_unavailable: deterministic test fallback",
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
            provenance = hit["global_vector_object"]["provenance"]
            self.assertIn("provider", provenance)
            self.assertIn("embedding_model_version", provenance)
            self.assertIn("source", provenance)
            self.assertIn("source_id", provenance)
            self.assertIn("reference", provenance)
            self.assertIn("provider_payload_kind", provenance)
            self.assertIn("retrieval_mode", provenance)
            self.assertIn("source_reference", provenance)
            self.assertIn("score", provenance)
            self.assertIn("rank", hit["rank_features"])

        self.assertEqual(hits[0]["retrieval_mode"], "keyword")
        self.assertEqual(hits[0]["global_vector_object"]["chunk_id"], "7:chunk:0")
        self.assertEqual(hits[1]["global_vector_object"]["chunk_id"], "policy-8-chunk-0")
        qdrant_provenance = hits[1]["global_vector_object"]["provenance"]
        self.assertEqual(qdrant_provenance["provider"], "openai")
        self.assertEqual(qdrant_provenance["backend"], "qdrant_vector")
        self.assertEqual(qdrant_provenance["embedding_model"], "text-embedding-3-large")
        self.assertEqual(qdrant_provenance["embedding_model_version"], "2026-05-embedding-manifest")
        self.assertEqual(qdrant_provenance["source_reference"], "qdrant://policy_chunks/policy-8-chunk-0")
        self.assertEqual(hits[2]["verification_state"], "fallback")
        self.assertEqual(hits[2]["global_vector_object"]["vector_version"], "v1")
        pgvector_provenance = hits[2]["global_vector_object"]["provenance"]
        self.assertEqual(pgvector_provenance["provider"], "openai")
        self.assertEqual(pgvector_provenance["backend"], "pgvector_fallback")
        self.assertEqual(pgvector_provenance["embedding_model"], "text-embedding-3-small")
        self.assertEqual(
            pgvector_provenance["fallback_reason"],
            "qdrant_unavailable: deterministic test fallback",
        )

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

    def test_retrieval_run_record_persists_branch_hit_readback_contract(self) -> None:
        query_group_id, hits = build_search_evidence_hits(
            [
                {"document_id": "doc-a", "score": 0.8, "mode": "bm25", "backend": "opensearch"},
                {"document_id": "doc-b", "score": 0.7, "mode": "vector", "backend": "qdrant"},
            ],
            query="market",
            project_key="demo_proj",
            rank_mode="hybrid",
            top_k=2,
        )

        record = build_retrieval_run_record(
            query="market",
            query_group_id=query_group_id,
            evidence_hits=hits,
            project_key="demo_proj",
            rank_mode="hybrid",
            top_k=2,
        )

        self.assertEqual(record["contract_version"], SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION)
        self.assertEqual(record["query_group_id"], query_group_id)
        self.assertEqual(len(record["branch_records"]), 2)
        self.assertEqual(len(record["retrieval_branches"]), 2)
        self.assertEqual(len(record["retrieval_hits"]), 2)
        self.assertEqual(len(record["evidence_hits"]), 2)
        validate_retrieval_run_record(record)
        loaded = load_retrieval_run_record(serialize_retrieval_run_record(record))
        self.assertEqual(loaded["run_id"], record["run_id"])
        self.assertEqual(loaded["retrieval_hits"][0]["run_id"], record["run_id"])
        self.assertEqual(
            sorted(branch["hit_count"] for branch in loaded["branch_records"]),
            [1, 1],
        )

    def test_agent_matrix_candidates_use_main_search_evidence_schema(self) -> None:
        query_group_id, hits = build_agent_matrix_evidence_hits(
            [
                {
                    "title": "Official report",
                    "url": "https://example.gov/report",
                    "snippet": "Robotics report",
                    "source_provider": "fallback-provider",
                    "trust": {"status": "accepted", "trust_score": 88, "url_checksum": "urlsha-report"},
                    "matrix_branches": [
                        {
                            "branch_id": "b1",
                            "query": "robotics commercialization official report",
                            "provider": "serper",
                        }
                    ],
                }
            ],
            query="robotics commercialization",
            project_key="demo_proj",
            top_k=1,
        )

        self.assertEqual(AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION, "agent_matrix_search_evidence.v1")
        self.assertTrue(query_group_id.startswith("qg_"))
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        validate_search_evidence_hit(hit)
        self.assertEqual(hit["retrieval_family"], "agent_matrix")
        self.assertEqual(hit["matrix_branch_id"], "b1")
        self.assertEqual(hit["backend"], "serper")
        self.assertEqual(hit["global_vector_object"]["object_type"], "source_candidate")
        self.assertEqual(hit["global_vector_object"]["document_id"], "urlsha-report")
        self.assertEqual(hit["global_vector_object"]["provenance"]["provider_payload_kind"], "agent_matrix_candidate")


if __name__ == "__main__":
    unittest.main()
