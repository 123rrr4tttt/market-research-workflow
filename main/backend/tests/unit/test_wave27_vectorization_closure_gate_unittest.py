from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave27_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave27_vectorization_closure_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave27_vectorization_closure_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave27 closure module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave27VectorizationClosureGateTest(unittest.TestCase):
    def test_gate_retains_all_three_topics_and_preserves_provider_external_boundary(self) -> None:
        module = _load_wave27_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave27-vectorization-closure-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["summary"]["topic_count"], 3)
        self.assertEqual(contract["summary"]["retained_current_dev_count"], 3)
        self.assertEqual(contract["summary"]["archive_external_blocked_candidate_count"], 0)
        self.assertFalse(contract["summary"]["archive_external_blocked_patch_prepared"])
        self.assertEqual(contract["summary"]["provider_slice_repo_local_closed_count"], 3)

        decisions = {row["slug"]: row for row in contract["topic_decisions"]}
        self.assertEqual(
            sorted(decisions),
            [
                "2026-03-01-open-source-platform-integration",
                "2026-03-05-oss-node-platform-io-plan",
                "2026-05-14-global-vectorization-general-foundation",
            ],
        )
        for row in decisions.values():
            self.assertEqual(row["decision"], "retain_current_dev")
            self.assertFalse(row["archive_external_blocked_eligible"])
            self.assertEqual(row["provider_manifest_quality_readback_gate"], "passed")
            self.assertTrue(row["provider_slice_repo_local_closed"])
            self.assertGreater(len(row["repo_local_blockers"]), 0)

        global_topic = decisions["2026-05-14-global-vectorization-general-foundation"]
        self.assertIn("unified_vector_object_contract_not_frozen", global_topic["repo_local_blockers"])
        self.assertIn(
            "retrieval_runs_branches_hits_persistence_not_implemented",
            global_topic["repo_local_blockers"],
        )

        provider_check = contract["provider_manifest_check"]
        self.assertEqual(provider_check["status"], "passed")
        self.assertEqual(provider_check["provider_modes"], ["hybrid", "keyword", "vector"])
        self.assertFalse(provider_check["closure_claim_allowed"])
        self.assertFalse(provider_check["provider_live_closure_claim_allowed"])
        self.assertFalse(provider_check["semantic_quality_claim_allowed"])
        self.assertIn(
            "semantic_embedding_quality_not_proven",
            provider_check["observed_external_gap_codes"],
        )

        quality_check = contract["quality_readback_check"]
        self.assertEqual(quality_check["status"], "passed")
        self.assertFalse(quality_check["wave14_closure_claim_allowed"])
        self.assertFalse(quality_check["wave18_closure_claim_allowed"])
        self.assertFalse(quality_check["wave18_semantic_quality_claim_allowed"])
        self.assertIn("global_vector_contract_not_closed", quality_check["benchmark_remaining_blocker_codes"])

    def test_gate_fails_if_provider_manifest_claims_closure(self) -> None:
        module = _load_wave27_module()
        wave19_path = module.REPO_ROOT / module.ARTIFACTS["wave19_provider_manifest"]["path"]
        wave19 = json.loads(wave19_path.read_text(encoding="utf-8"))
        wave19["closure_claim_allowed"] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            mutated_path = Path(tmpdir) / "provider_manifest_readback.json"
            mutated_path.write_text(json.dumps(wave19), encoding="utf-8")
            contract = module.build_contract(artifact_overrides={"wave19_provider_manifest": mutated_path})

        self.assertEqual(contract["status"], "failed")
        self.assertTrue(
            any("closure_claim_allowed must remain false" in failure for failure in contract["failures"])
        )


if __name__ == "__main__":
    unittest.main()
