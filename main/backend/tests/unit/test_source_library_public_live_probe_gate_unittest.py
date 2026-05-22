from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.source_library_public_live_probes import DEFAULT_TARGETS
from scripts.source_library_public_live_probes import classify_public_probe_result
from scripts.source_library_public_live_probes import run_probe


class SourceLibraryPublicLiveProbeGateUnitTestCase(unittest.TestCase):
    def test_public_probe_is_skip_safe_by_default(self) -> None:
        result = run_probe(
            targets=DEFAULT_TARGETS[:1],
            allow_public_network=False,
            probe_timeout=0.01,
        )

        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertTrue(result["validation"]["skipped"])
        self.assertFalse(result["validation"]["live_evidence_sufficient"])
        self.assertEqual(result["outputs"]["status_counts"], {"skipped_public_network_disabled": 1})
        self.assertEqual(
            result["outputs"]["target_results"][0]["classification"]["blocker_type"],
            "operator_gate",
        )

    def test_transport_blocker_classification_keeps_anti_bot_separate(self) -> None:
        classification = classify_public_probe_result(
            {
                "candidates": [],
                "diagnostics": {"transport_errors": 1, "raw_candidates": 0, "selected_candidates": 0},
                "errors": [{"error": "429 received from https://example.com/search"}],
            }
        )

        self.assertEqual(classification["status"], "anti_bot_or_transport_blocked")
        self.assertEqual(classification["blocker_type"], "public_network_or_anti_bot")

    def test_raw_candidate_without_selection_is_dirty_source_or_parser_blocker(self) -> None:
        classification = classify_public_probe_result(
            {
                "candidates": [],
                "diagnostics": {
                    "transport_errors": 0,
                    "raw_candidates": 4,
                    "selected_candidates": 0,
                    "candidate_filter_state": "term_filter_empty_no_fallback",
                },
                "errors": [],
            }
        )

        self.assertEqual(classification["status"], "parser_or_source_semantics_blocked")
        self.assertEqual(classification["blocker_type"], "parser_or_dirty_source")

    def test_candidate_with_term_fallback_is_review_evidence_not_full_closure(self) -> None:
        classification = classify_public_probe_result(
            {
                "candidates": ["https://example.com/article"],
                "used_term_fallback": True,
                "diagnostics": {
                    "transport_errors": 0,
                    "raw_candidates": 5,
                    "selected_candidates": 1,
                    "candidate_filter_state": "term_filter_empty_fallback_used",
                },
                "errors": [],
            }
        )

        self.assertEqual(classification["status"], "candidate_ready_with_term_fallback")
        self.assertEqual(classification["blocker_type"], "relevance_review")


if __name__ == "__main__":
    unittest.main()
