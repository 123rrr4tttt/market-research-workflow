from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

pytestmark = pytest.mark.unit


def _load_checker_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_agent_symbolic_provider_quality_readiness.py"
    )
    spec = importlib.util.spec_from_file_location("check_agent_symbolic_provider_quality_readiness", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentSymbolicProviderQualityReadinessContractTest(unittest.TestCase):
    def test_checker_records_fixture_quality_unsupported_claims_and_live_gaps(self) -> None:
        checker = _load_checker_module()
        contract = checker.build_contract()

        self.assertEqual(
            contract["contract_version"],
            "agent-symbolic-batch-search.wave13.provider_quality_readiness.v1",
        )
        self.assertEqual(contract["scope"], "symbolic_search_provider_quality_readiness_no_network")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(
            contract["closure_claim"],
            "fixture_quality_recorded_live_provider_quality_not_closed",
        )

        fixture = contract["fixture_quality"]
        self.assertEqual(fixture["status"], "passed")
        self.assertEqual(fixture["case_count"], 1)
        self.assertGreater(fixture["average_uplift"], 0.0)
        self.assertEqual(fixture["false_positive_retry_rate"], 0.0)
        self.assertFalse(fixture["quality_claim_allowed"])

        readiness = contract["evidence"]["readiness_boundary"]
        self.assertEqual(readiness["status"], "passed")
        self.assertEqual(
            readiness["readiness_state"],
            "fixture_quality_ready_live_provider_gap_open",
        )
        self.assertFalse(readiness["provider_readiness"]["quality_claim_allowed"])
        self.assertFalse(readiness["provider_readiness"]["auto_promotion_allowed"])

        claim_codes = {item["code"] for item in contract["unsupported_live_provider_claims"]}
        self.assertIn("fixture_replay_proves_live_provider_quality", claim_codes)
        self.assertIn("provider_auto_promotion_supported", claim_codes)
        self.assertIn("live_retry_uplift_closed", claim_codes)

        gap_codes = {item["code"] for item in contract["remaining_live_gaps"]}
        self.assertIn("searxng_live_provider_not_ready", gap_codes)
        self.assertIn("yacy_live_provider_not_ready", gap_codes)
        self.assertIn("web_live_provider_not_ready", gap_codes)
        self.assertIn("live_retry_uplift_replay_not_run", gap_codes)

        rejected = contract["evidence"]["input_quality_claim_rejected"]
        provider = rejected["provider_readiness"]["providers"]["searxng"]
        self.assertTrue(provider["input_quality_claim_allowed"])
        self.assertFalse(provider["quality_claim_allowed"])
        self.assertIn(
            "input_provider_quality_claim_rejected",
            {item["code"] for item in rejected["unsupported_live_provider_claims"]},
        )


if __name__ == "__main__":
    unittest.main()
