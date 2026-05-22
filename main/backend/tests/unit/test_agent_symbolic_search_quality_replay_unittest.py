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
        / "check_agent_symbolic_search_quality_replay.py"
    )
    spec = importlib.util.spec_from_file_location("check_agent_symbolic_search_quality_replay", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentSymbolicSearchQualityReplayContractTest(unittest.TestCase):
    def test_checker_proves_quality_replay_boundary_and_uplift(self) -> None:
        checker = _load_checker_module()
        contract = checker.build_contract()

        self.assertEqual(contract["contract_version"], "agent-symbolic-batch-search.wave11.quality_replay.v1")
        self.assertEqual(contract["scope"], "provider_quality_replay_boundary_and_benchmark_uplift_no_network")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["closure_claim"], "deterministic_quality_replay_closed_not_live_provider_quality")

        replay = contract["evidence"]["source_quality_signals"]
        self.assertEqual(replay["contract_version"], "agent_batch.search_quality_replay.v1")
        self.assertFalse(replay["live_provider_gap_state"]["quality_claim_allowed"])
        self.assertEqual(replay["live_provider_gap_state"]["providers_not_started"], ["searxng", "yacy", "web"])
        self.assertTrue(
            all(signal["provider_live_verified"] is False for signal in replay["source_quality_signals"])
        )

        boundary = contract["evidence"]["critic_retry_boundary"]
        self.assertEqual(boundary["critic_stop_boundary"]["decision"], "retry_blocked")
        self.assertEqual(boundary["source_gap_boundary"]["decision"], "retry_allowed")
        self.assertTrue(boundary["source_gap_boundary"]["threshold_bypassed"])

        benchmark = contract["evidence"]["deterministic_benchmark_uplift"]
        self.assertEqual(benchmark["status"], "passed")
        self.assertGreater(benchmark["average_uplift"], 0.0)
        self.assertEqual(benchmark["quality_claim"], "deterministic_replay_only_not_live_provider_quality")

        self.assertEqual(
            sorted(item["code"] for item in contract["remaining_gaps"]),
            [
                "global_topic_closure_requires_index_audit",
                "live_provider_quality_not_verified",
                "production_benchmark_requires_live_provider_replay",
            ],
        )


if __name__ == "__main__":
    unittest.main()
