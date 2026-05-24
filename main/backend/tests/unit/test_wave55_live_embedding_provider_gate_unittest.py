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
        / "wave55_live_embedding_provider_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave55_live_embedding_provider_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave55 live embedding provider module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave55LiveEmbeddingProviderGateTest(unittest.TestCase):
    def test_gate_closes_repo_local_live_provider_scope_and_keeps_production_quality_open(self) -> None:
        module = _load_wave55_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave55-live-embedding-provider-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["scope"], "repo_local_live_embedding_provider_no_network_no_external_api")
        self.assertTrue(contract["local_provider_closure_claim_allowed"])
        self.assertFalse(contract["production_quality_claim_allowed"])
        self.assertIn("external_embedding_provider_live_not_verified", contract["closed_conditions"])
        self.assertIn("semantic_embedding_quality_not_proven", contract["remaining_conditions"])
        self.assertIn("production_vector_quality_not_proven", contract["remaining_conditions"])

        provider = contract["provider_readback"]
        self.assertEqual(provider["status"], "passed")
        self.assertEqual(provider["provider_id"], "repo_local_token_hashing")
        self.assertFalse(provider["network_required"])
        self.assertTrue(provider["live_provider_verified"])
        self.assertEqual(provider["embedding_dim"], 512)

        quality = contract["quality_readback"]
        self.assertEqual(quality["status"], "passed")
        self.assertEqual(quality["top1_accuracy"], 1.0)
        self.assertGreater(quality["min_top_margin"], 0.02)

        retrieval = contract["retrieval_contracts"]
        self.assertEqual(retrieval["readback_status"], "passed")
        self.assertEqual(retrieval["evidence_hit_count"], 3)
        self.assertEqual(contract["sample_retrieval_run"]["retrieval_family"], "main_search")


if __name__ == "__main__":
    unittest.main()
