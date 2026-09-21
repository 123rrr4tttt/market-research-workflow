from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


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
        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(contract["summary"]["topic_count"], 3)
        self.assertEqual(contract["summary"]["retained_current_dev_count"], 3)
        self.assertEqual(contract["summary"]["archive_external_blocked_candidate_count"], 0)
        self.assertFalse(contract["summary"]["archive_external_blocked_patch_prepared"])
        self.assertEqual(contract["summary"]["provider_slice_repo_local_closed_count"], 0)

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
            self.assertEqual(row["provider_manifest_quality_readback_gate"], "failed")
            self.assertFalse(row["provider_slice_repo_local_closed"])
            self.assertGreater(len(row["repo_local_blockers"]), 0)

        global_topic = decisions["2026-05-14-global-vectorization-general-foundation"]
        self.assertIn("unified_vector_object_contract_not_frozen", global_topic["repo_local_blockers"])
        self.assertIn(
            "retrieval_runs_branches_hits_persistence_not_implemented",
            global_topic["repo_local_blockers"],
        )
        self.assertNotIn(
            "embedding_qdrant_pgvector_payload_provenance_not_unified",
            global_topic["repo_local_blockers"],
        )

    def test_gate_missing_manifest_fails_typed_without_reading_deleted_artifact(self) -> None:
        module = _load_wave27_module()
        contract = module.build_contract()

        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["summary"]["archive_external_blocked_patch_prepared"])


if __name__ == "__main__":
    unittest.main()
