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
        / "check_source_time_production_readiness.py"
    )
    spec = importlib.util.spec_from_file_location("check_source_time_production_readiness", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load source-time production readiness checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SourceTimeProductionReadinessTest(unittest.TestCase):
    def test_checker_distinguishes_deterministic_decision_log_and_live_gap(self) -> None:
        module = _load_checker_module()
        result = module.build_check()

        self.assertEqual(result["contract_version"], "source-time.production-readiness.v1")
        self.assertEqual(result["status"], "passed_with_known_gaps")
        self.assertFalse(result["closure_claim"])
        self.assertFalse(result["full_closure_allowed"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(
            result["readiness_boundaries"],
            {
                "deterministic_source_time_contract": "passed",
                "decision_log_provenance": "passed",
                "deterministic_sample_readback_chain": "passed",
                "production_data_semantic_chain": "ready_not_run",
            },
        )
        self.assertTrue(result["checks"]["deterministic_source_time_contract_verified"])
        self.assertTrue(result["checks"]["decision_log_provenance_verified"])
        self.assertTrue(result["checks"]["deterministic_sample_readback_chain_verified"])
        self.assertFalse(result["checks"]["production_data_semantic_chain_live_verified"])
        self.assertTrue(result["checks"]["production_data_semantic_chain_live_gap_retained"])
        self.assertIn(
            "production_data_semantic_chain_live_validation_not_run",
            result["remaining_live_gaps"],
        )
        sample_stage = {
            stage["name"]: stage for stage in result["stages"]
        }["deterministic_sample_readback_chain"]
        self.assertEqual(sample_stage["status"], "passed")
        self.assertFalse(sample_stage["production_live_verified"])
        self.assertEqual(sample_stage["evidence"]["source_time"], "2026-03-02T12:00:00Z")
        self.assertEqual(sample_stage["evidence"]["processed_time"], "2026-03-10T12:00:00Z")
        self.assertGreater(float(sample_stage["evidence"]["target_overlap_gap_90d"]), 0.0)
        self.assertEqual(
            sample_stage["evidence"]["target_overlap_gap_90d"],
            sample_stage["evidence"]["features_json_target_overlap_gap_90d"],
        )
        self.assertEqual(sample_stage["evidence"]["source_time_coverage_90d"], 1.0)
        self.assertEqual(
            sample_stage["evidence"]["effective_time_source_distribution_90d"]["source_time_count"],
            2,
        )
        self.assertIn(
            "production_freshness_probe_not_run",
            sample_stage["evidence"]["live_gap_markers_90d"],
        )
        doc_paths = {Path(result["doc_results"][0]["path"]).parts[-2]}
        self.assertIn("ARCHIVE_EXTERNAL_BLOCKED", result["doc_results"][0]["path"])
        self.assertEqual(doc_paths, {"2026-03-02-source-time-window-smart-timestamp-plan"})

    def test_doc_checks_fall_back_to_current_dev_when_archive_is_absent(self) -> None:
        module = _load_checker_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current_topic = (
                root
                / "development/latest-dev-docs/development-plans/CURRENT_DEV"
                / module.TOPIC_NAME
            )
            current_topic.mkdir(parents=True)
            source_topic = module.REPO_ROOT / module.TOPIC_DIR_CANDIDATES[0]
            for filename in (
                module.WAVE10_EVIDENCE,
                module.WAVE12_EVIDENCE,
                module.WAVE15_EVIDENCE,
                module.WAVE17_EVIDENCE,
            ):
                (current_topic / filename).write_text(
                    (source_topic / filename).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )

            doc_results = module._doc_token_results(root)

        self.assertTrue(all(result["passed"] for result in doc_results), doc_results)
        self.assertTrue(all("CURRENT_DEV" in result["path"] for result in doc_results), doc_results)

    def test_incomplete_live_evidence_fails_without_conflating_prior_contracts(self) -> None:
        module = _load_checker_module()
        result = module.build_check(
            live_evidence={
                "production_data_semantic_chain_verified": True,
                "live_query_used": True,
                "semantic_chain_sample_count": 3,
            }
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["readiness_boundaries"]["deterministic_source_time_contract"], "passed")
        self.assertEqual(result["readiness_boundaries"]["decision_log_provenance"], "passed")
        self.assertEqual(result["readiness_boundaries"]["deterministic_sample_readback_chain"], "passed")
        self.assertEqual(result["readiness_boundaries"]["production_data_semantic_chain"], "failed_evidence")
        production_stage = {
            stage["name"]: stage for stage in result["stages"]
        }["production_data_semantic_chain"]
        self.assertIn("configured_services_used", production_stage["missing_requirements"])
        self.assertIn("decision_log_features_readback", production_stage["missing_requirements"])

    def test_complete_live_evidence_marks_production_chain_verified(self) -> None:
        module = _load_checker_module()
        result = module.build_check(
            live_evidence={
                "production_data_semantic_chain_verified": True,
                "live_query_used": True,
                "configured_services_used": True,
                "effective_time_source_distribution_readback": True,
                "source_time_coverage_measured": True,
                "decision_log_rows_readback": True,
                "decision_log_features_readback": True,
                "semantic_chain_sample_count": 12,
                "source_time_coverage": 0.84,
                "decision_log_row_count": 12,
            }
        )

        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["closure_claim"])
        self.assertTrue(result["full_closure_allowed"])
        self.assertEqual(result["readiness_boundaries"]["production_data_semantic_chain"], "live_verified")
        self.assertTrue(result["checks"]["production_data_semantic_chain_live_verified"])
        self.assertFalse(result["checks"]["production_data_semantic_chain_live_gap_retained"])
        self.assertEqual(result["remaining_live_gaps"], [])


if __name__ == "__main__":
    unittest.main()
