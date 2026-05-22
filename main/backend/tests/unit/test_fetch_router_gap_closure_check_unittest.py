from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_fetch_router_gap_closure import CONTRACT_VERSION
from scripts.check_fetch_router_gap_closure import PROTECTED_SHARED_INDEXES
from scripts.check_fetch_router_gap_closure import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


class FetchRouterGapClosureCheckUnitTestCase(unittest.TestCase):
    def test_fetch_router_gap_topics_emit_status_gap_and_evidence(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["validation"]["topic_count"], 3)

        topics = {topic["topic_id"]: topic for topic in result["topics"]}
        self.assertEqual(
            set(topics),
            {
                "2026-03-02-ingest-platformization-assessment",
                "2026-03-02-single-url-first-ingest-allocation-plan",
                "2026-03-08-llm-crawler-unified-frontdoor",
            },
        )
        for topic in topics.values():
            self.assertEqual(topic["status"], "closed_narrow_runtime_contract")
            self.assertIn("closed for the narrow contract", topic["gap"])
            self.assertTrue(topic["evidence"]["doc"]["passed"], topic["evidence"]["doc"])
            self.assertTrue(topic["evidence"]["anchors"])
            self.assertTrue(all(anchor["passed"] for anchor in topic["evidence"]["anchors"]))

    def test_fetch_router_gap_gate_records_tri_state_blocker_scope(self) -> None:
        result = build_check(REPO_ROOT)

        tri_state = result["validation"]["tri_state_blocker_wording"]
        self.assertEqual(tri_state["status"], "not_blocking_narrow_closure")
        self.assertEqual(tri_state["states"], ["success", "degraded_success", "failed"])
        self.assertEqual(tri_state["source"], "main/backend/app/services/ingest/frontdoor_router_contract.py")
        self.assertFalse(result["validation"]["shared_indexes_edited"])
        self.assertEqual(result["validation"]["protected_shared_indexes"], list(PROTECTED_SHARED_INDEXES))


if __name__ == "__main__":
    unittest.main()
