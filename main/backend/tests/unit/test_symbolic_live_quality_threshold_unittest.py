from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

pytestmark = pytest.mark.unit

try:
    from app.services.agent_batch.search_quality_replay import (
        build_symbolic_live_quality_threshold_contract,
    )
except Exception as exc:  # pragma: no cover - dependency/import guard
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _load_checker_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_symbolic_live_quality_threshold.py"
    )
    spec = importlib.util.spec_from_file_location("check_symbolic_live_quality_threshold", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SymbolicLiveQualityThresholdContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"live quality threshold tests require backend dependencies: {_IMPORT_ERROR}")

    def test_checker_defines_thresholds_without_closing_live_provider_replay(self) -> None:
        checker = _load_checker_module()
        contract = checker.build_contract()

        self.assertEqual(
            contract["contract_version"],
            "agent-symbolic-batch-search.wave15.live_quality_threshold.v1",
        )
        self.assertEqual(contract["scope"], "symbolic_search_live_quality_threshold_no_network")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["threshold_status"], "threshold_contract_ready_live_replay_gap_open")
        self.assertFalse(contract["live_provider_replay_closed"])
        self.assertFalse(contract["quality_claim_allowed"])

        fixture = contract["fixture_quality_boundary"]
        self.assertGreater(fixture["average_uplift"], 0.0)
        self.assertFalse(fixture["quality_claim_allowed"])
        self.assertFalse(fixture["live_provider_quality_equivalent"])

        thresholds = contract["quality_thresholds"]
        self.assertEqual(thresholds["required_providers"], ["searxng", "yacy", "web"])
        self.assertEqual(thresholds["min_results_per_provider"], 3)
        self.assertEqual(thresholds["min_source_domains"], 2)
        self.assertEqual(thresholds["min_review_sample_count"], 3)

        claim_codes = {item["code"] for item in contract["unsupported_live_provider_claims"]}
        self.assertIn("fixture_quality_uplift_meets_live_quality_threshold", claim_codes)
        self.assertIn("provider_availability_meets_live_quality_threshold", claim_codes)
        self.assertIn("live_quality_closed_without_threshold_replay", claim_codes)

        gap_codes = {item["code"] for item in contract["remaining_live_gaps"]}
        self.assertIn("live_provider_replay_not_run", gap_codes)
        self.assertIn("searxng_live_provider_replay_not_attached", gap_codes)
        self.assertIn("operator_review_not_approved", gap_codes)

    def test_live_replay_payload_must_meet_all_thresholds_and_review(self) -> None:
        contract = build_symbolic_live_quality_threshold_contract(
            fixture_quality={
                "source": "score_quality_benchmark_replay",
                "status": "passed",
                "case_count": 1,
                "average_uplift": 0.29,
                "false_positive_retry_rate": 0.0,
                "quality_claim_allowed": False,
            },
            required_live_providers=["searxng"],
            live_provider_replay={
                "replay_type": "live_provider_quality_replay",
                "live_replay_performed": True,
                "operator_review_status": "not_run",
                "quality_claim_allowed": True,
                "providers": {
                    "searxng": {
                        "replay_status": "passed",
                        "provider_live_verified": True,
                        "case_count": 1,
                        "result_count": 3,
                        "source_domains": ["robotics.example.com", "venture.example.com"],
                        "relevance_score": 0.82,
                        "freshness_score": 0.78,
                        "duplicate_rate": 0.0,
                        "timeout_rate": 0.0,
                        "p95_latency_ms": 900,
                        "review_sample_count": 0,
                        "trace_success": True,
                        "quality_claim_allowed": True,
                    }
                },
            },
        )

        provider = contract["replay_evaluation"]["providers"]["searxng"]
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["threshold_status"], "live_replay_present_thresholds_unmet")
        self.assertIn("review_sample_count", provider["threshold_failures"])
        self.assertFalse(provider["thresholds_met"])
        self.assertFalse(contract["live_provider_replay_closed"])
        self.assertFalse(contract["quality_claim_allowed"])
        self.assertIn(
            "input_live_provider_quality_claim_rejected",
            {item["code"] for item in contract["unsupported_live_provider_claims"]},
        )
        self.assertIn(
            "searxng_live_quality_threshold_not_met",
            {item["code"] for item in contract["remaining_live_gaps"]},
        )

    def test_live_replay_payload_closes_when_all_thresholds_and_review_pass(self) -> None:
        provider_row = {
            "replay_status": "passed",
            "provider_live_verified": True,
            "case_count": 1,
            "result_count": 3,
            "source_domains": ["interestingengineering.com", "globenewswire.com"],
            "relevance_score": 0.82,
            "freshness_score": 0.84,
            "duplicate_rate": 0.0,
            "timeout_rate": 0.0,
            "p95_latency_ms": 980,
            "review_sample_count": 3,
            "trace_success": True,
        }
        contract = build_symbolic_live_quality_threshold_contract(
            fixture_quality={
                "source": "score_quality_benchmark_replay",
                "status": "passed",
                "case_count": 1,
                "average_uplift": 0.29,
                "false_positive_retry_rate": 0.0,
                "quality_claim_allowed": False,
            },
            live_provider_replay={
                "replay_type": "live_provider_quality_replay",
                "live_replay_performed": True,
                "operator_review_status": "approved",
                "providers": {
                    "searxng": dict(provider_row),
                    "yacy": dict(provider_row),
                    "web": dict(provider_row),
                },
            },
        )

        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["threshold_status"], "live_quality_thresholds_met")
        self.assertTrue(contract["live_provider_replay_closed"])
        self.assertTrue(contract["quality_claim_allowed"])
        self.assertEqual(contract["remaining_live_gaps"], [])


if __name__ == "__main__":
    unittest.main()
