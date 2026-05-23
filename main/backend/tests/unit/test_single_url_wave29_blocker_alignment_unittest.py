from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_single_url_wave29_blocker_alignment import (  # noqa: E402
    ARCHIVE_RECOMMENDATION,
    CONTRACT_VERSION,
    build_report,
    validate_report,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class SingleUrlWave29BlockerAlignmentTestCase(unittest.TestCase):
    def test_repo_local_blockers_close_and_archive_recommendation_is_external_blocked(self) -> None:
        report = build_report(REPO_ROOT)

        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["repo_local_blockers_open"])
        self.assertEqual(report["archive_recommendation"], ARCHIVE_RECOMMENDATION)
        self.assertTrue(report["shared_index_updates_required"])
        self.assertFalse(report["shared_indexes_edited_by_this_gate"])
        self.assertTrue(report["wave29_doc"]["passed"], report["wave29_doc"])

        blockers = {item["code"]: item for item in report["blockers"]}
        self.assertEqual(
            set(blockers),
            {"broader_fetch_router", "official_api_adapter", "dashboard_tri_state"},
        )
        for blocker in blockers.values():
            self.assertEqual(blocker["repo_local_status"], "closed_repo_local")
            self.assertFalse(blocker["repo_local_blocker_open"])
            self.assertTrue(blocker["anchors"])
            self.assertTrue(all(anchor["passed"] for anchor in blocker["anchors"]))

    def test_validator_rejects_reopened_repo_local_blocker(self) -> None:
        report = build_report(REPO_ROOT)
        report["repo_local_blockers_open"] = True
        report["blockers"][0]["repo_local_status"] = "retained_repo_local_missing_evidence"

        errors = validate_report(report)

        self.assertTrue(any("repo-local status" in error for error in errors))
        self.assertTrue(any("repo_local_blockers_open" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
