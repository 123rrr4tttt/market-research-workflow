from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_source_library_review_closure_batch2 import CONTRACT_VERSION
from scripts.check_source_library_review_closure_batch2 import build_check
from scripts.check_source_library_review_closure_batch2 import build_expected_artifact


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibraryReviewClosureBatch2UnitTestCase(unittest.TestCase):
    def test_expected_artifact_closes_second_fixture_batch_and_keeps_live_gaps_open(self) -> None:
        artifact = build_expected_artifact(REPO_ROOT)

        self.assertEqual(artifact["contract_version"], CONTRACT_VERSION)
        self.assertTrue(artifact["scope"]["fixture_only"])
        self.assertFalse(artifact["scope"]["public_network_attempted"])
        self.assertFalse(artifact["scope"]["applies_to_full_current_dev_review"])
        self.assertFalse(artifact["scope"]["applies_to_live_source_collection"])
        self.assertTrue(artifact["review_batch"]["deterministic_batch2_closed"])
        self.assertEqual(artifact["review_batch"]["decision_count"], 2)
        self.assertEqual(artifact["input_contracts"]["batch2_fixture_queue"]["queued_count"], 2)
        self.assertTrue(artifact["input_contracts"]["wave16_review_batch"]["validation_passed"])
        self.assertEqual(
            {row["decision"] for row in artifact["review_batch"]["decisions"]},
            {
                "defer_source_marked_candidate_pending_human_review",
                "reject_low_confidence_fixture_candidate",
            },
        )
        self.assertEqual(artifact["remaining_gaps"]["human_review"]["status"], "open")
        self.assertEqual(artifact["remaining_gaps"]["public_replay"]["status"], "open")
        self.assertEqual(artifact["remaining_gaps"]["live_source_collection"]["status"], "open")
        self.assertFalse(artifact["non_closure_markers"]["claims_human_review_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_public_replay_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_live_source_collection_complete"])

    def test_checker_validates_committed_artifact_topic_docs_and_gap_register(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertTrue(result["governance_scope"]["deterministic_batch2_closed"])
        self.assertFalse(result["governance_scope"]["claims_human_review_complete"])
        self.assertFalse(result["governance_scope"]["claims_public_replay_complete"])
        self.assertFalse(result["governance_scope"]["claims_live_source_collection_complete"])
        self.assertEqual(result["artifact_check"]["decision_count"], 2)
        self.assertEqual(
            result["artifact_check"]["remaining_gap_keys"],
            ["human_review", "live_source_collection", "public_replay"],
        )
        self.assertEqual(len(result["topic_evidence"]["docs"]), 4)

    def test_checker_rejects_human_public_or_live_source_closure_claims(self) -> None:
        artifact = build_expected_artifact(REPO_ROOT)
        artifact = copy.deepcopy(artifact)
        artifact["non_closure_markers"]["claims_human_review_complete"] = True
        artifact["non_closure_markers"]["claims_public_replay_complete"] = True
        artifact["non_closure_markers"]["claims_live_source_collection_complete"] = True
        artifact["remaining_gaps"]["live_source_collection"]["status"] = "closed"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review_batch2.json"
            path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

            result = build_check(REPO_ROOT, artifact_path=path)

        self.assertFalse(result["validation"]["passed"])
        self.assertIn(
            "artifact non-closure marker must be false: claims_human_review_complete",
            result["validation"]["errors"],
        )
        self.assertIn(
            "artifact non-closure marker must be false: claims_public_replay_complete",
            result["validation"]["errors"],
        )
        self.assertIn(
            "artifact non-closure marker must be false: claims_live_source_collection_complete",
            result["validation"]["errors"],
        )
        self.assertIn(
            "remaining gap must stay open: live_source_collection",
            result["validation"]["errors"],
        )


if __name__ == "__main__":
    unittest.main()
