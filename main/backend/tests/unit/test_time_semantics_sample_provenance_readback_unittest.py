from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_checker_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_time_semantics_sample_provenance_readback.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_time_semantics_sample_provenance_readback",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave20 time-semantics checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TimeSemanticsSampleProvenanceReadbackTest(unittest.TestCase):
    def test_checker_reports_readback_gate_and_retains_production_gap(self) -> None:
        module = _load_checker_module()
        result = module.build_check()

        self.assertEqual(result["contract_version"], "time-semantics.sample-provenance-readback.v1")
        self.assertEqual(result["scope"], "repo_local_deterministic_sample_provenance_readback_no_live_production_probe")
        self.assertEqual(result["status"], "passed_with_known_gaps")
        self.assertFalse(result["closure_claim"])
        self.assertFalse(result["full_closure_allowed"])
        self.assertFalse(result["production_data_semantic_chain_live_verified"])
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["checks"]["deterministic_sample_readback_gate"])
        self.assertTrue(result["checks"]["provenance_readback_gate"])
        self.assertTrue(result["checks"]["production_boundary_gate"])
        self.assertTrue(result["checks"]["wave20_topic_evidence_gate"])
        self.assertEqual(
            result["readiness_boundaries"]["production_data_semantic_chain"],
            "ready_not_run",
        )
        self.assertIn(
            "production_data_semantic_chain_live_validation_not_run",
            result["remaining_live_gaps"],
        )
        self.assertEqual(result["sample_evidence"]["source_time"], "2026-03-02T12:00:00Z")
        self.assertEqual(result["sample_evidence"]["time_provenance"], "source_time")
        self.assertEqual(result["sample_evidence"]["source_time_coverage_90d"], 1.0)
        self.assertEqual(
            result["sample_evidence"]["effective_time_source_distribution_90d"]["source_time_count"],
            2,
        )
        self.assertTrue(
            all(
                row["path"].startswith(
                    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
                )
                for row in result["topic_evidence"].values()
            )
        )

    def test_checker_fails_when_wave20_topic_evidence_is_missing(self) -> None:
        module = _load_checker_module()

        with tempfile.TemporaryDirectory() as tmp:
            result = module.build_check(repo_root=Path(tmp))

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["wave20_topic_evidence_gate"])
        self.assertIn("doc.source_time_window.missing_wave20_evidence", result["failures"])
        self.assertIn("doc.time_statistics.missing_wave20_evidence", result["failures"])
        self.assertIn("doc.time_semantics_density.missing_wave20_evidence", result["failures"])
        self.assertTrue(result["checks"]["deterministic_sample_readback_gate"])
        self.assertTrue(result["checks"]["provenance_readback_gate"])


if __name__ == "__main__":
    unittest.main()
