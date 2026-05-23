from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_source_library_public_replay_a5_gate import CONTRACT_VERSION
from scripts.check_source_library_public_replay_a5_gate import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibraryPublicReplayA5GateUnitTestCase(unittest.TestCase):
    def test_a5_gate_freezes_manifest_fixture_and_reviewed_public_replay(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertEqual(
            result["a5_status"],
            "full_public_replay_reviewed_closed",
        )
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])

        manifest = result["a5_gate"]["embedded_manifest"]
        self.assertEqual(manifest["target_count"], 45)
        self.assertEqual(manifest["enabled_target_count"], 40)
        self.assertEqual(manifest["policy_skipped_target_count"], 5)

        artifact_input = result["a5_gate"]["artifact_input"]
        self.assertTrue(artifact_input["target_ids_match_embedded_manifest"])
        self.assertEqual(artifact_input["target_count"], 45)

        dry_run = result["a5_gate"]["fresh_no_network_dry_run"]
        self.assertEqual(dry_run["status_counts"], {"skipped_public_network_disabled": 45})
        self.assertEqual(dry_run["public_targets_attempted"], 0)

        full_public = result["full_public_replay"]
        self.assertEqual(full_public["status"], "real_evidence_present_review_required")
        self.assertEqual(full_public["target_count"], 45)
        self.assertEqual(full_public["public_targets_attempted"], 40)
        self.assertEqual(full_public["status_counts"]["skipped_policy_disabled_platform_entry"], 5)

        self.assertEqual(result["closure_review"]["status"], "reviewed_for_topic_closure")
        self.assertEqual(result["external_blocker"]["status"], "resolved")
        self.assertIsNone(result["external_blocker"]["blocker_type"])

    def test_term_fallback_public_fixture_remains_relevance_review(self) -> None:
        result = build_check(REPO_ROOT)

        live_fixture = result["public_live_fixture"]
        self.assertTrue(live_fixture["validation_passed"])
        self.assertTrue(live_fixture["live_evidence_sufficient"])
        self.assertEqual(live_fixture["target_count"], 4)
        self.assertEqual(live_fixture["status_counts"]["candidate_ready"], 2)
        self.assertEqual(live_fixture["status_counts"]["candidate_ready_with_term_fallback"], 2)

        review = result["term_fallback_relevance_review"]
        self.assertEqual(review["status"], "review_required_not_full_closure")
        self.assertEqual(review["review_target_count"], 2)
        self.assertEqual(
            {target["target_id"] for target in review["targets"]},
            {"commercialobserver_parser_weak", "hai_stanford_mixed_shell"},
        )


if __name__ == "__main__":
    unittest.main()
