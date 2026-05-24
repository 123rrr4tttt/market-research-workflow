from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave55_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave55_oss_node_search_quality_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave55_oss_node_search_quality_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave55 OSS node search quality module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave55OssNodeSearchQualityGateTest(unittest.TestCase):
    def test_gate_closes_repo_local_open_search_quality_and_reduces_semantic_scope(self) -> None:
        module = _load_wave55_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave55-oss-node-search-quality-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(
            contract["scope"],
            "repo_local_controlled_open_search_and_semantic_quality_no_network",
        )
        self.assertTrue(contract["local_open_search_quality_claim_allowed"])
        self.assertTrue(contract["repo_local_semantic_quality_claim_allowed"])
        self.assertFalse(contract["production_quality_claim_allowed"])
        self.assertIn("local_open_search_live_quality_not_sealed", contract["closed_conditions"])
        self.assertIn("semantic_embedding_quality_not_proven", contract["reduced_conditions"])
        self.assertIn("production_semantic_embedding_quality_not_proven", contract["remaining_conditions"])
        self.assertIn("local_open_search_live_container_quality_not_replayed", contract["remaining_conditions"])

        input_readback = contract["input_artifact_readback"]
        self.assertEqual(input_readback["status"], "passed")
        self.assertFalse(input_readback["open_search_trace"]["auto_local_open_search_called"])
        self.assertEqual(input_readback["live_embedding_provider_gate"]["gate_status"], "passed")
        self.assertFalse(input_readback["live_embedding_provider_gate"]["production_quality_claim_allowed"])

        open_search = contract["open_search_quality_readback"]
        self.assertEqual(open_search["status"], "passed")
        self.assertEqual(open_search["providers"], ["searxng", "yacy"])
        self.assertEqual(open_search["query_count"], 4)
        self.assertEqual(open_search["top1_accuracy"], 1.0)
        self.assertGreaterEqual(open_search["min_top_margin"], 0.05)
        for case in open_search["cases"]:
            self.assertTrue(case["passed"])
            self.assertEqual(case["provider_family"], "local_open_search")
            self.assertFalse(case["provider_auto_included"])
            self.assertEqual(case["provider_route"], f"explicit:{case['provider']}")

        semantic = contract["semantic_quality_readback"]
        self.assertEqual(semantic["status"], "passed")
        self.assertEqual(semantic["provider_id"], "repo_local_token_hashing")
        self.assertGreaterEqual(semantic["embedding_dim"], 64)
        self.assertEqual(semantic["query_count"], 3)
        self.assertEqual(semantic["top1_accuracy"], 1.0)
        self.assertGreaterEqual(semantic["min_top_margin"], 0.05)

        retrieval = contract["retrieval_contracts"]
        self.assertEqual(retrieval["status"], "passed")
        self.assertEqual(retrieval["evidence_hit_count"], 3)
        self.assertEqual(retrieval["sample_retrieval_run"]["retrieval_family"], "main_search")


if __name__ == "__main__":
    unittest.main()
