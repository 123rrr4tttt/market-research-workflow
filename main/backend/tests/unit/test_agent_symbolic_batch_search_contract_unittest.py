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
        / "check_agent_symbolic_batch_search_contract.py"
    )
    spec = importlib.util.spec_from_file_location("check_agent_symbolic_batch_search_contract", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentSymbolicBatchSearchContractTest(unittest.TestCase):
    def test_checker_proves_minimal_brief_critic_retry_loop(self) -> None:
        checker = _load_checker_module()
        contract = checker.build_contract()

        self.assertEqual(contract["contract_version"], "agent-symbolic-batch-search.wave9.v1")
        self.assertEqual(contract["scope"], "deterministic_no_network_agent_batch_search_brief_critic_retry")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["closure_claim"], "minimal_runtime_loop_closed_not_global_topic")

        task_contract = contract["evidence"]["agent_exposed_task_contract"]
        self.assertIn("search.market", task_contract["callable_channels"])
        self.assertIn("source_library", task_contract["callable_channels"])
        self.assertEqual(task_contract["retry_fail_closed_reason"], "retry_action_rewrite_fields_unsupported")

        precision = contract["evidence"]["precision_retry_loop"]
        self.assertEqual(precision["status"], "passed")
        self.assertEqual(precision["retry_action"]["action"], "narrow_query_terms")
        self.assertEqual(len(precision["submit_rounds"]), 2)
        self.assertNotEqual(precision["first_query"], precision["retry_query"])

        source_retry = contract["evidence"]["source_library_retry_loop"]
        self.assertEqual(source_retry["status"], "passed")
        self.assertEqual(source_retry["retry_action"]["action"], "attach_source_library")
        self.assertTrue(source_retry["threshold_bypassed"])
        self.assertEqual(source_retry["retried_source_task"]["item_key"], "robotics.market_watch")

        self.assertEqual(
            sorted(item["code"] for item in contract["remaining_blockers"]),
            [
                "benchmark_uplift_not_proven",
                "global_topic_closure_requires_index_audit",
                "live_provider_and_source_quality_not_replayed",
            ],
        )


if __name__ == "__main__":
    unittest.main()
