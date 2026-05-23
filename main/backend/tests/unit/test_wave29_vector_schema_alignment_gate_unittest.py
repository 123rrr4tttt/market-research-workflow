from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave29_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave29_vector_schema_alignment_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave29_vector_schema_alignment_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave29 schema alignment module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave29VectorSchemaAlignmentGateTest(unittest.TestCase):
    def test_gate_closes_vector_object_and_main_search_evidence_hit_schema_blockers(self) -> None:
        module = _load_wave29_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave29-vector-schema-alignment-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["sample_hit_count"], 3)
        self.assertEqual(contract["sample_backends"], ["opensearch_lexical", "qdrant_vector", "pgvector_fallback"])
        self.assertEqual(contract["sample_retrieval_modes"], ["keyword", "vector", "vector"])
        self.assertEqual(
            contract["closed_repo_local_blockers"],
            [
                "unified_vector_object_contract_not_frozen",
                "main_search_evidence_hit_contract_not_aligned",
                "embedding_qdrant_pgvector_payload_provenance_not_unified",
            ],
        )
        self.assertNotIn(
            "unified_vector_object_contract_not_frozen",
            contract["remaining_repo_local_blockers"],
        )
        self.assertNotIn(
            "main_search_evidence_hit_contract_not_aligned",
            contract["remaining_repo_local_blockers"],
        )
        self.assertNotIn(
            "embedding_qdrant_pgvector_payload_provenance_not_unified",
            contract["remaining_repo_local_blockers"],
        )
        self.assertIn(
            "retrieval_runs_branches_hits_persistence_not_implemented",
            contract["remaining_repo_local_blockers"],
        )
        self.assertTrue(contract["payload_provenance_repo_local_closed"])
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertFalse(contract["provider_live_closure_claim_allowed"])
        self.assertFalse(contract["semantic_quality_claim_allowed"])

        for hit in contract["sample_evidence_hits"]:
            self.assertEqual(hit["retrieval_family"], "main_search")
            self.assertEqual(hit["query_group_id"], contract["query_group_id"])
            self.assertTrue(hit["matrix_branch_id"].startswith("branch_"))
            self.assertEqual(hit["global_vector_object"]["project_key"], "demo_proj")
            provenance = hit["global_vector_object"]["provenance"]
            for key in contract["required_fields"]["global_vector_object_provenance"]:
                self.assertIn(key, provenance)

        qdrant_hit = next(hit for hit in contract["sample_evidence_hits"] if hit["backend"] == "qdrant_vector")
        self.assertEqual(qdrant_hit["global_vector_object"]["provenance"]["provider"], "openai")
        self.assertEqual(
            qdrant_hit["global_vector_object"]["provenance"]["embedding_model_version"],
            "2026-05-embedding-manifest",
        )
        pgvector_hit = next(hit for hit in contract["sample_evidence_hits"] if hit["backend"] == "pgvector_fallback")
        self.assertEqual(
            pgvector_hit["global_vector_object"]["provenance"]["fallback_reason"],
            "qdrant_unavailable: deterministic gate fallback",
        )


if __name__ == "__main__":
    unittest.main()
