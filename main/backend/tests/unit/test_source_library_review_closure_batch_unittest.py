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

from scripts.check_source_library_review_closure_batch import CONTRACT_VERSION
from scripts.check_source_library_review_closure_batch import build_check
from scripts.check_source_library_review_closure_batch import build_expected_artifact


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibraryReviewClosureBatchUnitTestCase(unittest.TestCase):
    def test_expected_artifact_closes_only_the_deterministic_fixture_batch(self) -> None:
        artifact = build_expected_artifact(REPO_ROOT)

        self.assertEqual(artifact["contract_version"], CONTRACT_VERSION)
        self.assertTrue(artifact["scope"]["fixture_only"])
        self.assertFalse(artifact["scope"]["public_network_attempted"])
        self.assertFalse(artifact["scope"]["applies_to_full_current_dev_review"])
        self.assertTrue(artifact["review_batch"]["deterministic_batch_closed"])
        self.assertEqual(artifact["review_batch"]["decision_count"], 1)
        self.assertEqual(
            artifact["review_batch"]["decisions"][0]["decision"],
            "reject_low_confidence_fixture_candidate",
        )
        self.assertFalse(artifact["non_closure_markers"]["claims_human_relevance_review_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_live_public_replay_complete"])
        self.assertFalse(artifact["non_closure_markers"]["claims_full_45_site_public_replay"])

    def test_checker_validates_committed_artifact_topic_docs_and_non_closure_markers(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertTrue(result["governance_scope"]["deterministic_batch_closed"])
        self.assertFalse(result["governance_scope"]["claims_human_relevance_review_complete"])
        self.assertFalse(result["governance_scope"]["claims_live_public_replay_complete"])
        self.assertEqual(result["artifact_check"]["decision_count"], 1)
        self.assertEqual(len(result["topic_evidence"]["docs"]), 4)

    def test_checker_rejects_public_or_human_closure_claims_in_artifact(self) -> None:
        artifact = build_expected_artifact(REPO_ROOT)
        artifact = copy.deepcopy(artifact)
        artifact["non_closure_markers"]["claims_human_relevance_review_complete"] = True
        artifact["non_closure_markers"]["claims_live_public_replay_complete"] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review_batch.json"
            path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

            result = build_check(REPO_ROOT, artifact_path=path)

        self.assertFalse(result["validation"]["passed"])
        self.assertIn(
            "artifact non-closure marker must be false: claims_human_relevance_review_complete",
            result["validation"]["errors"],
        )
        self.assertIn(
            "artifact non-closure marker must be false: claims_live_public_replay_complete",
            result["validation"]["errors"],
        )


if __name__ == "__main__":
    unittest.main()
