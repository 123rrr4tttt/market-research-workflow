from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_crawler_source_expansion_closure import CONTRACT_VERSION
from scripts.check_crawler_source_expansion_closure import PROTECTED_SHARED_INDEXES
from scripts.check_crawler_source_expansion_closure import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


class CrawlerSourceExpansionClosureCheckUnitTest(unittest.TestCase):
    def test_closure_check_maps_plan_tasks_to_current_code_and_evidence(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["overall_status"], "not_closed")
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertEqual(result["doc_drift"]["status"], "outdated_snapshot")

        statuses = {task["task_id"]: task["status"] for task in result["tasks"]}
        self.assertEqual(statuses["A1"], "closed")
        self.assertEqual(statuses["A2"], "closed")
        self.assertEqual(statuses["A3"], "closed")
        self.assertEqual(statuses["A4"], "needs_update")
        self.assertEqual(statuses["A5"], "not_closed")
        self.assertEqual(statuses["A6"], "closed")
        self.assertEqual(statuses["A7"], "not_closed")

    def test_closure_check_keeps_shared_navigation_out_of_this_lane(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["protected_shared_indexes"], PROTECTED_SHARED_INDEXES)
        self.assertIn(
            "Update shared navigation only in a later integration lane.",
            result["minimum_development_plan"],
        )
        for protected_path in PROTECTED_SHARED_INDEXES:
            self.assertNotIn("2026-03-07-crawler-source-expansion/", protected_path)


if __name__ == "__main__":
    unittest.main()
