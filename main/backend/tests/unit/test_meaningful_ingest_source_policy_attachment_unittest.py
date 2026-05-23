from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

pytestmark = pytest.mark.unit

from scripts.check_meaningful_ingest_source_policy_attachment import (  # noqa: E402
    CONTRACT_VERSION,
    DECISION_MARKER,
    PROTECTED_SHARED_INDEXES,
    TOPIC_ID,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class MeaningfulIngestSourcePolicyAttachmentTest(unittest.TestCase):
    def test_source_policy_attachment_is_resolved_by_existing_owner(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], TOPIC_ID)
        self.assertEqual(result["status"], "passed", result["validation"]["errors"])
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["decision_marker"], DECISION_MARKER)

        resolution = result["source_policy_resolution"]
        self.assertEqual(resolution["status"], "resolved_repo_local_attachment")
        self.assertTrue(resolution["owned_elsewhere"])
        self.assertFalse(resolution["successor_topic_created"])
        self.assertEqual(resolution["decision_values"], ["allow", "downgrade", "block"])
        self.assertTrue(resolution["live_tuning_requires_canary_feedback"])

        self.assertTrue(result["crawler_policy_matrix_check"]["passed"])
        self.assertEqual(result["canary_metrics_readback_check"]["status"], "passed")
        self.assertEqual(result["canary_24h_metrics_artifact_check"]["status"], "passed")
        self.assertEqual(result["repo_local_blockers"], [])

    def test_archive_recommendation_does_not_modify_shared_indexes(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["decision"]["status"], "external_blocked_candidate")
        self.assertTrue(result["decision"]["archive_eligible"])
        self.assertEqual(result["decision"]["recommended_location"], "ARCHIVE_EXTERNAL_BLOCKED")
        self.assertFalse(result["decision"]["move_performed"])
        self.assertFalse(result["decision"]["shared_index_updates_performed"])
        self.assertTrue(result["decision"]["shared_index_updates_required_by_supervisor"])
        self.assertEqual(result["protected_shared_indexes"], list(PROTECTED_SHARED_INDEXES))

        touched_paths = [result["decision_doc"]]
        touched_paths.extend(anchor["path"] for anchor in result["anchors"].values())
        for protected_path in PROTECTED_SHARED_INDEXES:
            self.assertNotIn(protected_path, touched_paths)


if __name__ == "__main__":
    unittest.main()
