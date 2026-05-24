from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave56_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave56_semantic_vector_quality_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave56_semantic_vector_quality_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave56 semantic vector quality module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave56SemanticVectorQualityGateTest(unittest.TestCase):
    def test_gate_closes_repo_local_semantic_quality_and_reduces_production_quality_blocker(self) -> None:
        module = _load_wave56_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave56-semantic-vector-quality-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(
            contract["scope"],
            "repo_local_production_like_semantic_vector_quality_no_network_no_live_traffic",
        )
        self.assertIn("semantic_embedding_quality_not_proven", contract["closed_conditions"])
        self.assertIn("production_vector_quality_not_proven", contract["reduced_conditions"])
        self.assertFalse(contract["production_quality_claim_allowed"])
        self.assertTrue(contract["semantic_quality_claim_allowed"])

        provider = contract["provider_readback"]
        self.assertEqual(provider["status"], "passed")
        self.assertEqual(provider["provider_id"], "repo_local_token_hashing")
        self.assertEqual(provider["model_version"], "2026-05-23.wave56")
        self.assertEqual(provider["embedding_dim"], 512)
        self.assertEqual(provider["vector_version"], "repo-local-live-v2")
        self.assertFalse(provider["network_required"])

        quality = contract["quality_evaluation"]
        self.assertEqual(quality["status"], "passed")
        self.assertGreaterEqual(quality["domain_count"], quality["thresholds"]["min_domains"])
        self.assertGreaterEqual(quality["case_count"], quality["thresholds"]["min_cases"])
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
        self.assertEqual(retrieval["readback_status"], "passed")
        self.assertEqual(retrieval["evidence_hit_count"], quality["case_count"])
        self.assertEqual(contract["sample_retrieval_run"]["retrieval_family"], "main_search")


if __name__ == "__main__":
    unittest.main()
