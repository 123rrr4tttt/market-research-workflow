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
        / "check_time_semantics_release_gate.py"
    )
    spec = importlib.util.spec_from_file_location("check_time_semantics_release_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load time-semantics release gate checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TimeSemanticsReleaseGateTest(unittest.TestCase):
    def test_checker_reduces_repo_local_blockers_and_keeps_live_boundary(self) -> None:
        module = _load_checker_module()
        result = module.build_check(include_doc_checks=False)

        self.assertEqual(result["contract_version"], "time-semantics.release-gate-readback.v1")
        self.assertEqual(result["status"], "passed_with_known_gaps")
        self.assertEqual(result["failures"], [])
        self.assertFalse(result["closure_claim"])
        self.assertFalse(result["full_closure_allowed"])
        self.assertTrue(result["checks"]["deterministic_source_time_contract_verified"])
        self.assertTrue(result["checks"]["decision_log_provenance_verified"])
        self.assertTrue(result["checks"]["sample_provenance_readback_verified"])
        self.assertTrue(result["checks"]["source_time_distribution_repo_local_verified"])
        self.assertTrue(result["checks"]["decision_log_features_readback_repo_local_verified"])
        self.assertTrue(result["checks"]["release_gate_integration_verified"])
        self.assertFalse(result["checks"]["configured_semantic_chain_evidence_verified"])
        self.assertFalse(result["checks"]["production_data_semantic_chain_live_verified"])
        self.assertEqual(
            result["external_blockers_reduced"],
            [
                "release_gate_integration",
                "source_time_distribution_repo_local_readback",
                "decision_log_features_repo_local_readback",
            ],
        )
        self.assertEqual(
            result["remaining_external_blockers"],
            [
                "production_data_semantic_chain_live_validation_not_run",
                "live_source_time_coverage_distribution_not_measured",
                "live_decision_log_features_readback_not_verified",
            ],
        )
        distribution_stage = {
            stage["name"]: stage for stage in result["stages"]
        }["source_time_distribution_decision_log_readback"]
        evidence = distribution_stage["evidence"]
        self.assertEqual(evidence["source_distribution_90d"]["source_time_count"], 4)
        self.assertAlmostEqual(evidence["source_time_coverage_90d"], 4.0 / 6.0)
        self.assertAlmostEqual(evidence["explicit_semantic_time_coverage_90d"], 5.0 / 6.0)

    def test_live_evidence_can_close_production_boundary_without_changing_closure_claim(self) -> None:
        module = _load_checker_module()
        result = module.build_check(
            include_doc_checks=False,
            live_evidence={
                "evidence_tier": "configured_live",
                "data_source": "configured_db_existing_decision_logs",
                "production_data_semantic_chain_verified": True,
                "live_query_used": True,
                "configured_services_used": True,
                "effective_time_source_distribution_readback": True,
                "source_time_coverage_measured": True,
                "decision_log_rows_readback": True,
                "decision_log_features_readback": True,
                "feedback_reward_alignment_readback": True,
                "semantic_chain_sample_count": 6,
                "source_time_coverage": 0.67,
                "source_time_count": 67,
                "source_time_total_docs": 100,
                "decision_log_row_count": 6,
                "feedback_row_count": 6,
            },
        )

        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["closure_claim"])
        self.assertTrue(result["full_closure_allowed"])
        self.assertTrue(result["checks"]["configured_semantic_chain_evidence_verified"])
        self.assertTrue(result["checks"]["production_data_semantic_chain_live_verified"])
        self.assertEqual(result["remaining_external_blockers"], [])

    def test_release_gate_rejects_live_payload_without_source_count_proof(self) -> None:
        module = _load_checker_module()
        result = module.build_check(
            include_doc_checks=False,
            live_evidence={
                "evidence_tier": "configured_live",
                "data_source": "configured_db_existing_decision_logs",
                "production_data_semantic_chain_verified": True,
                "live_query_used": True,
                "configured_services_used": True,
                "effective_time_source_distribution_readback": True,
                "source_time_coverage_measured": True,
                "decision_log_rows_readback": True,
                "decision_log_features_readback": True,
                "feedback_reward_alignment_readback": True,
                "semantic_chain_sample_count": 6,
                "source_time_coverage": 0.67,
                "decision_log_row_count": 6,
                "feedback_row_count": 6,
            },
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("source_readiness.failed", result["failures"])
        self.assertFalse(result["checks"]["production_data_semantic_chain_live_verified"])

    def test_strict_closure_fails_without_true_live_evidence(self) -> None:
        module = _load_checker_module()
        result = module.build_check(include_doc_checks=False, strict_closure=True)

        self.assertEqual(result["status"], "failed")
        self.assertIn("production_data_semantic_chain_live_required", result["failures"])
        self.assertFalse(result["checks"]["production_data_semantic_chain_live_verified"])

    def test_production_like_evidence_is_not_full_live_closure(self) -> None:
        module = _load_checker_module()
        result = module.build_check(
            include_doc_checks=False,
            live_evidence={
                "evidence_tier": "production_like",
                "data_source": "configured_db_production_like_sample",
                "production_data_semantic_chain_verified": True,
                "live_query_used": True,
                "configured_services_used": True,
                "effective_time_source_distribution_readback": True,
                "source_time_coverage_measured": True,
                "decision_log_rows_readback": True,
                "decision_log_features_readback": True,
                "feedback_reward_alignment_readback": True,
                "semantic_chain_sample_count": 1,
                "source_time_coverage": 1.0,
                "source_time_count": 4,
                "source_time_total_docs": 4,
                "decision_log_row_count": 3,
                "feedback_row_count": 3,
            },
        )

        self.assertEqual(result["status"], "passed_with_configured_evidence")
        self.assertFalse(result["full_closure_allowed"])
        self.assertTrue(result["checks"]["configured_semantic_chain_evidence_verified"])
        self.assertTrue(
            result["checks"]["configured_production_like_semantic_chain_evidence_verified"]
        )
        self.assertFalse(result["checks"]["production_data_semantic_chain_live_verified"])
        self.assertEqual(
            result["remaining_external_blockers"],
            ["production_live_dataset_not_verified"],
        )

    def test_release_gate_marker_check_fails_for_unwired_gate(self) -> None:
        module = _load_checker_module()
        with tempfile.TemporaryDirectory() as tmp:
            gate = Path(tmp) / "pre_release_gate.sh"
            gate.write_text("#!/usr/bin/env bash\npytest\n", encoding="utf-8")
            result = module.build_check(
                include_doc_checks=False,
                pre_release_gate_path=gate,
            )

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["release_gate_integration_verified"])
        release_stage = {
            stage["name"]: stage for stage in result["stages"]
        }["pre_release_gate_integration"]
        self.assertIn(
            "release_gate_calls_time_semantics_checker",
            release_stage["missing_requirements"],
        )


if __name__ == "__main__":
    unittest.main()
