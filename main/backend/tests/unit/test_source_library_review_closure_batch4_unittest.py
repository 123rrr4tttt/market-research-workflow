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

from scripts.check_source_library_review_closure_batch4 import CONTRACT_VERSION
from scripts.check_source_library_review_closure_batch4 import build_check
from scripts.check_source_library_review_closure_batch4 import build_expected_artifact


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibraryReviewClosureBatch4UnitTestCase(unittest.TestCase):
    def test_expected_artifact_closes_fourth_fixture_batch_and_keeps_live_gaps_open(self) -> None:
        artifact = build_expected_artifact(REPO_ROOT)

        self.assertEqual(artifact["contract_version"], CONTRACT_VERSION)
        self.assertTrue(artifact["scope"]["fixture_only"])
        self.assertFalse(artifact["scope"]["public_network_attempted"])
        self.assertFalse(artifact["scope"]["applies_to_full_current_dev_review"])
        self.assertFalse(artifact["scope"]["applies_to_live_source_collection"])
        self.assertFalse(artifact["scope"]["applies_to_live_ingest_migration"])
        self.assertTrue(artifact["review_batch"]["deterministic_batch4_closed"])
        self.assertEqual(artifact["review_batch"]["decision_count"], 4)
        self.assertEqual(artifact["input_contracts"]["batch4_fixture_queue"]["queued_count"], 4)
        self.assertTrue(artifact["input_contracts"]["wave16_review_batch"]["validation_passed"])
        self.assertTrue(artifact["input_contracts"]["wave18_review_batch"]["validation_passed"])
        self.assertTrue(artifact["input_contracts"]["wave19_review_batch"]["validation_passed"])
        self.assertEqual(
            [row["decision"] for row in artifact["review_batch"]["decisions"]],
            [
                "reject_low_confidence_fixture_candidate",
                "defer_source_marked_candidate_pending_human_review",
                "reject_low_confidence_fixture_candidate",
                "reject_low_confidence_fixture_candidate",
            ],
        )
        self.assertEqual(
            set(artifact["review_batch"]["decisions"][0]["decision_basis"]),
            {
                "fallback_anchor_only_profile",
                "term_fallback_candidates",
                "low_confidence_candidate",
                "adapter_capability_review",
            },
        )
        self.assertEqual(
            artifact["review_batch"]["decisions"][1]["decision_basis"],
            ["source_marked_review_required"],
        )
        self.assertIn("adapter_capability_review", artifact["review_batch"]["decisions"][2]["decision_basis"])
        self.assertIn("term_fallback_candidates", artifact["review_batch"]["decisions"][3]["decision_basis"])
        self.assertEqual(artifact["remaining_gaps"]["human_review"]["status"], "open")
        self.assertEqual(artifact["remaining_gaps"]["public_replay"]["status"], "open")
        self.assertEqual(artifact["remaining_gaps"]["live_source_collection"]["status"], "open")
        self.assertEqual(artifact["remaining_gaps"]["live_ingest_migration"]["status"], "open")
        self.assertFalse(artifact["non_closure_markers"]["claims_human_review_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_public_replay_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_live_source_collection_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_live_ingest_migration_complete"])
        self.assertEqual(
            sorted(artifact["topic_coverage"]),
            ["adapter_capability", "minimal_migration", "search_chain", "three_lane"],
        )
        self.assertTrue(
            artifact["topic_coverage"]["three_lane"]["wave20_evidence_doc"].startswith(
                "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            )
        )
        self.assertTrue(
            artifact["topic_coverage"]["minimal_migration"]["wave20_evidence_doc"].startswith(
                "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            )
        )

    def test_checker_validates_committed_artifact_topic_docs_and_gap_register(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertTrue(result["governance_scope"]["deterministic_batch4_closed"])
        self.assertFalse(result["governance_scope"]["claims_human_review_complete"])
        self.assertFalse(result["governance_scope"]["claims_public_replay_complete"])
        self.assertFalse(result["governance_scope"]["claims_live_source_collection_complete"])
        self.assertFalse(result["governance_scope"]["claims_live_ingest_migration_complete"])
        self.assertEqual(result["artifact_check"]["decision_count"], 4)
        self.assertEqual(
            result["artifact_check"]["remaining_gap_keys"],
            ["human_review", "live_ingest_migration", "live_source_collection", "public_replay"],
        )
        self.assertEqual(len(result["topic_evidence"]["docs"]), 4)
        doc_paths = {row["topic"]: row["path"] for row in result["topic_evidence"]["docs"]}
        self.assertTrue(
            doc_paths["three_lane"].startswith(
                "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            )
        )
        self.assertTrue(
            doc_paths["minimal_migration"].startswith(
                "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            )
        )

    def test_checker_rejects_human_public_source_or_ingest_closure_claims(self) -> None:
        artifact = build_expected_artifact(REPO_ROOT)
        artifact = copy.deepcopy(artifact)
        artifact["non_closure_markers"]["claims_human_review_complete"] = True
        artifact["non_closure_markers"]["claims_public_replay_complete"] = True
        artifact["non_closure_markers"]["claims_live_source_collection_complete"] = True
        artifact["non_closure_markers"]["claims_live_ingest_migration_complete"] = True
        artifact["remaining_gaps"]["live_ingest_migration"]["status"] = "closed"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review_batch4.json"
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
            "artifact non-closure marker must be false: claims_live_ingest_migration_complete",
            result["validation"]["errors"],
        )
        self.assertIn(
            "remaining gap must stay open: live_ingest_migration",
            result["validation"]["errors"],
        )


if __name__ == "__main__":
    unittest.main()
