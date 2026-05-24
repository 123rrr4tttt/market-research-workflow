from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave57_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave57_production_vector_quality_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave57_production_vector_quality_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave57 production vector quality module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave57ProductionVectorQualityGateTest(unittest.TestCase):
    def test_gate_replays_production_like_corpus_and_closes_when_vector_store_is_available(self) -> None:
        module = _load_wave57_module()
        contract = module.build_contract(require_vector_store=False)

        self.assertEqual(contract["contract_version"], "wave57-production-vector-quality-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertFalse(contract["global_manifest_update_performed"])
        self.assertFalse(contract["production_traffic_claim_allowed"])

        corpus = contract["corpus_readback"]
        self.assertEqual(corpus["status"], "passed")
        self.assertGreaterEqual(corpus["row_count"], corpus["thresholds"]["min_corpus_rows"])
        self.assertGreaterEqual(corpus["distinct_document_count"], corpus["thresholds"]["min_distinct_documents"])
        self.assertGreaterEqual(corpus["source_group_count"], corpus["thresholds"]["min_source_groups"])
        self.assertIn("target_blocker_docs", corpus["source_groups"])
        self.assertIn("existing_lancedb_jsonl_artifact", corpus["source_groups"])
        self.assertIn("automation_run_artifact", corpus["source_groups"])

        provider = contract["provider_readback"]
        self.assertEqual(provider["status"], "passed")
        self.assertEqual(provider["provider_id"], "repo_local_token_hashing")
        self.assertEqual(provider["embedding_dim"], 512)
        self.assertFalse(provider["network_required"])

        quality = contract["quality_evaluation"]
        self.assertEqual(quality["status"], "passed")
        self.assertEqual(quality["case_count"], quality["thresholds"]["min_cases"])
        self.assertEqual(quality["top1_accuracy"], 1.0)
        self.assertEqual(quality["recall_at_3"], 1.0)
        self.assertEqual(quality["mrr"], 1.0)
        self.assertTrue(all(case["passed"] for case in quality["cases"]))
        self.assertTrue(all(case["stable_order"] for case in quality["cases"]))
        self.assertTrue(all(case["retrieval_mode"] == "vector" for case in quality["cases"]))

        retrieval = contract["retrieval_contracts"]
        self.assertEqual(retrieval["status"], "passed")
        self.assertEqual(retrieval["evidence_hit_count"], quality["case_count"])
        self.assertEqual(retrieval["sample_retrieval_run"]["retrieval_family"], "main_search")

        vector_store = contract["vector_store_readback"]
        if vector_store["backend"] == "lancedb":
            self.assertTrue(contract["production_like_vector_quality_claim_allowed"])
            self.assertTrue(contract["target_topic_migration_ready"])
            self.assertIn("production_vector_quality_not_proven", contract["closed_conditions"])
            self.assertEqual(contract["remaining_conditions"], [])
        else:
            self.assertEqual(vector_store["backend"], "repo_local_direct_vector")
            self.assertFalse(contract["production_like_vector_quality_claim_allowed"])
            self.assertFalse(contract["target_topic_migration_ready"])
            self.assertEqual(contract["closed_conditions"], [])

    def test_require_vector_store_passes_in_optional_lancedb_environment(self) -> None:
        module = _load_wave57_module()
        from app.services.local_index.adapters import is_lancedb_available

        if not is_lancedb_available():
            self.skipTest("optional LanceDB runtime is not installed")

        contract = module.build_contract(require_vector_store=True)

        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["vector_store_readback"]["backend"], "lancedb")
        self.assertTrue(contract["production_like_vector_quality_claim_allowed"])
        self.assertTrue(contract["target_topic_migration_ready"])
        self.assertIn("production_vector_quality_not_proven", contract["closed_conditions"])


if __name__ == "__main__":
    unittest.main()
