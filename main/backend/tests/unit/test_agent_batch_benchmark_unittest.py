from __future__ import annotations

import unittest

import pytest

pytestmark = pytest.mark.unit

try:
    from app.services.agent_batch.benchmark import (
        SEARCH_POLICY_BENCHMARK_CONTRACT_VERSION,
        build_search_policy_benchmark_pack,
        evaluate_search_policy_gate,
    )
except Exception as exc:  # pragma: no cover - dependency/import guard
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class AgentBatchBenchmarkUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent batch benchmark unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_benchmark_pack_contains_fixed_categories(self):
        pack = build_search_policy_benchmark_pack()

        self.assertEqual(pack["contract_version"], SEARCH_POLICY_BENCHMARK_CONTRACT_VERSION)
        self.assertEqual(len(pack["cases"]), 5)
        categories = [case["category"] for case in pack["cases"]]
        self.assertEqual(
            categories,
            [
                "market_landscape",
                "company_watchlist",
                "product_scan",
                "financing_scan",
                "policy_tracking",
            ],
        )

    def test_gate_holds_without_enough_benchmark_evidence(self):
        gate = evaluate_search_policy_gate(
            {
                "critic_job_count": 2,
                "retry_outcome_counts": {"scheduled": 1, "skipped": 1},
                "average_submit_rounds": 1.5,
            }
        )

        self.assertEqual(gate["contract_version"], SEARCH_POLICY_BENCHMARK_CONTRACT_VERSION)
        self.assertEqual(gate["decision"], "hold")
        criteria = {item["name"]: item for item in gate["criteria"]}
        self.assertEqual(criteria["benchmark_evidence"]["status"], "hold")
        self.assertEqual(criteria["round_budget"]["status"], "pass")
