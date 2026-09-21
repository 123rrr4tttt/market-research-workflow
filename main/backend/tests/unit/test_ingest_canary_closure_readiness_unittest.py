from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from scripts.check_ingest_canary_closure_readiness import (
    AUTHORITY_ROOT,
    CONTRACT_VERSION,
    run_check,
    validate_report,
)


pytestmark = pytest.mark.unit


class IngestCanaryClosureReadinessTest(unittest.TestCase):
    def test_current_authority_is_wave51_56_57_after_current_dev_migration(self) -> None:
        report = run_check()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["authority"]["root"], AUTHORITY_ROOT.as_posix())
        self.assertEqual(report["authority"]["wave27_classification"], "history_only")
        self.assertFalse(report["authority"]["deleted_json_or_jsonl_used_as_evidence"])
        self.assertEqual(len(report["external_blocked_targets"]), 2)
        self.assertEqual(len(report["non_target_wrappers"]), 1)
        self.assertEqual(len(report["topics"]), 3)
        for topic in report["topics"]:
            self.assertTrue(topic["authority_directory_exists"])
            self.assertTrue(topic["current_authority_doc_exists"])
            self.assertEqual(topic["missing_authority_tokens"], [])
            self.assertTrue(topic["authority_index_points_to_current_doc"])
            self.assertFalse(topic["current_dev_directory_exists"])
            self.assertTrue(topic["current_dev_navigation_row_present"])
            self.assertFalse(topic["current_dev_is_authority"])
            self.assertFalse(topic["historical_wave27"]["is_current_authority"])

        topics = {topic["slug"]: topic for topic in report["topics"]}
        parent = topics["2026-03-02-ingest-platformization-assessment"]
        self.assertEqual(parent["current_wave"], 51)
        self.assertEqual(parent["target_kind"], "non_target_parent_wrapper")
        self.assertEqual(parent["remaining_external_conditions"], [])

        meaningful = topics["2026-03-02-meaningful-ingest-guardrails-plan"]
        single_url = topics["2026-03-02-single-url-first-ingest-allocation-plan"]
        self.assertEqual(meaningful["current_wave"], 56)
        self.assertEqual(single_url["current_wave"], 57)
        for successor in (meaningful, single_url):
            self.assertEqual(successor["current_status"], "external_blocked")
            self.assertTrue(successor["remaining_external_conditions"])

    def test_validator_rejects_promoting_wave27_history_to_authority(self) -> None:
        report = run_check()
        report["topics"][0]["historical_wave27"]["is_current_authority"] = True

        errors = validate_report(report)

        self.assertTrue(any("Wave27 history must not be current authority" in error for error in errors))

    def test_write_output_round_trips_report_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ingest-canary-closure-readiness-") as tmp_dir:
            output = Path(tmp_dir) / "closure_readiness.json"

            report = run_check(write_output=output)

            self.assertEqual(report["status"], "passed")
            self.assertTrue(output.is_file())
            self.assertIn(CONTRACT_VERSION, output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
