from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from scripts.check_ingest_canary_closure_readiness import CONTRACT_VERSION, run_check, validate_report


pytestmark = pytest.mark.unit


class IngestCanaryClosureReadinessTest(unittest.TestCase):
    def test_retains_current_dev_when_repo_local_blockers_remain(self) -> None:
        report = run_check()

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertTrue(report["canary_repo_local_gate_sufficient"])
        self.assertEqual(report["external_blocked_migration_candidates"], [])
        self.assertEqual(len(report["topics"]), 3)
        for topic in report["topics"]:
            self.assertEqual(topic["recommended_location"], "CURRENT_DEV")
            self.assertEqual(topic["status"], "retained_partial_repo_local_blockers_open")
            self.assertTrue(topic["repo_local_blockers_open"])
            self.assertFalse(topic["external_blocked_migration_ready"])
            self.assertTrue(topic["canary_repo_local_gate_sufficient"])
            self.assertTrue(topic["repo_local_blockers"])

    def test_validator_rejects_overclaimed_external_blocked_candidate(self) -> None:
        report = run_check()
        report["external_blocked_migration_candidates"] = [report["topics"][0]["slug"]]
        report["topics"][0]["external_blocked_migration_ready"] = True

        errors = validate_report(report)

        self.assertTrue(any("external_blocked_migration_candidates" in error for error in errors))
        self.assertTrue(any("must not be ready" in error for error in errors))

    def test_write_output_round_trips_report_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ingest-canary-closure-readiness-") as tmp_dir:
            output = Path(tmp_dir) / "closure_readiness.json"

            report = run_check(write_output=output)

            self.assertEqual(report["status"], "passed")
            self.assertTrue(output.is_file())
            self.assertIn(CONTRACT_VERSION, output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
