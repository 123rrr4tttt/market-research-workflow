from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

pytestmark = pytest.mark.unit

from scripts.check_graph_typed_writing_consumer_status_boundary import (  # noqa: E402
    CONTRACT_VERSION,
    TARGET_STATUS,
    build_check,
    validate_report,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class GraphTypedWritingConsumerStatusBoundaryUnitTest(unittest.TestCase):
    def test_current_status_is_external_blocked_without_active_partial(self) -> None:
        report = build_check(REPO_ROOT)

        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["status"], "passed", report["validation"])
        self.assertTrue(report["validation"]["passed"], report["validation"])
        self.assertEqual(report["current_dev_status_counts"]["partial"], 0)

        topic_statuses = {topic["topic_id"]: topic for topic in report["topics"]}
        self.assertEqual(len(topic_statuses), 4)
        for topic in topic_statuses.values():
            self.assertEqual(topic["canonical_status"], TARGET_STATUS)
            self.assertTrue(topic["external_blocked_index_row"]["has_external_blocked"])
            self.assertEqual(topic["current_status_problem_count"], 0)

        gates = report["repo_local_gates"]
        self.assertTrue(gates["graph"]["passed"], gates["graph"])
        self.assertFalse(gates["graph"]["closure_claim"])
        self.assertTrue(gates["graph"]["live_tenant_db_audit_open"])
        self.assertTrue(gates["typed_writing"]["passed"], gates["typed_writing"])
        self.assertFalse(gates["typed_writing"]["closure_claim_allowed"])
        self.assertTrue(gates["typed_writing"]["remaining_live_gaps"])
        self.assertTrue(gates["consumer"]["passed"], gates["consumer"])
        self.assertEqual(gates["consumer"]["repo_local_blockers"], [])

    def test_legacy_status_terms_are_reported_as_legacy_only(self) -> None:
        report = build_check(REPO_ROOT)
        semantics = report["legacy_status_semantics"]

        self.assertGreater(semantics["legacy_status_mention_count"], 0)
        self.assertEqual(semantics["current_status_problem_count"], 0)
        self.assertTrue(semantics["legacy_status_mentions_by_file"])

        broken = dict(report)
        broken["topics"] = [dict(topic) for topic in report["topics"]]
        broken["topics"][0]["current_status_problem_count"] = 1
        failures = validate_report(broken)
        self.assertIn(
            f"decision_file_contains_legacy_status_terms:{broken['topics'][0]['topic_id']}",
            failures,
        )


if __name__ == "__main__":
    unittest.main()
