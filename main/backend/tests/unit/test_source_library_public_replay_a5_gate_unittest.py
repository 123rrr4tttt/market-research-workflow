from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_source_library_public_replay_a5_gate import CONTRACT_VERSION
from scripts.check_source_library_public_replay_a5_gate import build_check
from scripts.check_evidence_source_availability import EVIDENCE_SOURCE_UNAVAILABLE


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibraryPublicReplayA5GateUnitTestCase(unittest.TestCase):
    def test_a5_gate_fails_closed_when_tracked_evidence_is_unavailable(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["a5_status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertEqual(result["evidence_source"]["status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertFalse(result["validation"]["passed"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])
        self.assertTrue(result["evidence_source"]["missing_paths"])
        self.assertTrue(all(value is False for value in result["evidence_source"]["authority_ceiling"].values()))

    def test_term_fallback_public_fixture_remains_relevance_review(self) -> None:
        result = build_check(REPO_ROOT)

        review = result["term_fallback_relevance_review"]
        self.assertEqual(review["status"], "review_required_not_full_closure")
        self.assertEqual(review["review_target_count"], 0)
        self.assertEqual(review["targets"], [])


if __name__ == "__main__":
    unittest.main()
