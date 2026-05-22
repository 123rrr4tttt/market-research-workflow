from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

pytestmark = pytest.mark.unit


def _load_contract_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "check_time_semantics_ope_contract.py"
    spec = importlib.util.spec_from_file_location("check_time_semantics_ope_contract", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load time semantics OPE contract checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TimeSemanticsOpeContractCheckTest(unittest.TestCase):
    def test_contract_checker_reports_deterministic_closure_and_known_gaps(self) -> None:
        module = _load_contract_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "time-semantics-ope-deterministic-contract.v1")
        self.assertEqual(contract["scope"], "deterministic_current_state_no_live_production_probe")
        self.assertEqual(contract["status"], "passed_with_known_gaps")
        self.assertEqual(contract["failures"], [])

        self.assertTrue(contract["checks"]["source_time_window"]["effective_time_uses_source_time"])
        self.assertTrue(contract["checks"]["source_time_window"]["window_bounds_anchor_to_effective_time"])
        self.assertTrue(contract["checks"]["target_overlap_priority"]["target_overlap_gap_observed"])
        self.assertTrue(contract["checks"]["target_overlap_priority"]["target_overlap_changes_probability"])
        self.assertTrue(contract["checks"]["ope_freshness_gate"]["fresh_gate_go"])
        self.assertTrue(contract["checks"]["ope_freshness_gate"]["stale_gate_no_go"])
        self.assertEqual(
            contract["remaining_gaps"],
            [
                "live_prompt_time_policy_decision_log_volume_not_verified",
                "live_prompt_time_window_feedback_alignment_not_verified",
                "real_production_data_validation_not_run",
            ],
        )


if __name__ == "__main__":
    unittest.main()
