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
        / "wave57_oss_node_public_corpus_semantic_relevance_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave57_oss_node_public_corpus_semantic_relevance_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave57 public-corpus semantic relevance module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave57OssNodePublicCorpusSemanticRelevanceGateTest(unittest.TestCase):
    def test_gate_closes_target_local_public_corpus_provider_quality_route(self) -> None:
        module = _load_wave57_module()
        contract = module.build_contract()

        self.assertEqual(
            contract["contract_version"],
            "wave57-oss-node-public-corpus-semantic-relevance-gate.v1",
        )
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(
            contract["scope"],
            "target_local_public_oss_corpus_semantic_relevance_no_network_no_live_container",
        )

        self.assertTrue(contract["public_corpus_semantic_relevance_claim_allowed"])
        self.assertFalse(contract["live_container_quality_claim_allowed"])
        self.assertFalse(contract["production_traffic_quality_claim_allowed"])
        self.assertTrue(contract["target_archive_closed_candidate"])
        self.assertFalse(contract["global_manifest_sync_performed"])
        self.assertEqual(contract["remaining_conditions"], [])
        self.assertIn("local_open_search_live_container_quality_not_replayed", contract["non_claimed_scope"])
        self.assertIn("oss_node_provider_quality", contract["closed_conditions"])
        self.assertIn("public_corpus_semantic_relevance_not_attached", contract["closed_conditions"])
        self.assertIn("production_semantic_embedding_quality_not_proven", contract["closed_conditions"])

        input_readback = contract["input_artifact_readback"]
        self.assertEqual(input_readback["status"], "passed")
        self.assertGreaterEqual(
            input_readback["public_corpus_index"]["evaluated_repo_count"],
            contract["quality_evaluation"]["thresholds"]["min_public_sources"],
        )
        self.assertEqual(input_readback["wave55_search_quality_gate"]["gate_status"], "passed")
        self.assertTrue(input_readback["wave55_search_quality_gate"]["local_open_search_quality_claim_allowed"])

        corpus = contract["public_corpus_readback"]
        self.assertEqual(corpus["status"], "passed")
        self.assertGreaterEqual(corpus["source_count"], contract["quality_evaluation"]["thresholds"]["min_public_sources"])
        self.assertEqual(corpus["failures"], [])
        self.assertTrue(all(row["path"].startswith("reference-pool/oss/") for row in corpus["sources"]))

        provider = contract["provider_readback"]
        self.assertEqual(provider["status"], "passed")
        self.assertEqual(provider["provider_id"], "repo_local_token_hashing")
        self.assertEqual(provider["model_version"], "2026-05-23.wave56")
        self.assertEqual(provider["embedding_dim"], 512)
        self.assertFalse(provider["network_required"])

        quality = contract["quality_evaluation"]
        self.assertEqual(quality["status"], "passed")
        self.assertEqual(quality["top1_accuracy"], 1.0)
        self.assertEqual(quality["recall_at_3"], 1.0)
        self.assertEqual(quality["mrr"], 1.0)
        self.assertGreaterEqual(quality["min_top2_margin"], quality["thresholds"]["min_top2_margin"])
        self.assertGreaterEqual(
            quality["min_hard_negative_margin"],
            quality["thresholds"]["min_hard_negative_margin"],
        )
        self.assertTrue(all(case["passed"] for case in quality["cases"]))
        self.assertTrue(all(case["stable_order"] for case in quality["cases"]))

        retrieval = contract["retrieval_contracts"]
        self.assertEqual(retrieval["status"], "passed")
        self.assertEqual(retrieval["evidence_hit_count"], quality["case_count"])
        self.assertEqual(contract["sample_retrieval_run"]["retrieval_family"], "main_search")


if __name__ == "__main__":
    unittest.main()
