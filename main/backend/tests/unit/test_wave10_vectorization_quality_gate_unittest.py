from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave10_gate_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave10_vectorization_quality_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave10_vectorization_quality_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave10 quality gate module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave10VectorizationQualityGateTest(unittest.TestCase):
    def test_gate_checks_provider_trace_modes_thresholds_and_fallback_reason(self) -> None:
        module = _load_wave10_gate_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave10-vectorization-quality-gate.v1")
        self.assertEqual(contract["scope"], "deterministic_local_fixture_no_network_no_container_start")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["quality_thresholds"]["required_modes"], ["keyword", "vector", "hybrid"])

        provider_trace = contract["evidence"]["search_provider_trace"]
        self.assertEqual(provider_trace["status"], "passed")
        self.assertEqual(
            provider_trace["required_result_fields"],
            ["provider_route", "provider_family", "provider_auto_included", "backend_trace"],
        )
        self.assertFalse(provider_trace["auto_local_open_search_called"])

        benchmark = contract["evidence"]["local_index_benchmark_quality"]
        self.assertEqual(benchmark["status"], "passed")
        self.assertEqual(benchmark["threshold_status"], "passed")
        self.assertEqual(benchmark["ranking_case_count"], 3)
        self.assertEqual(benchmark["filter_case_count"], 3)
        self.assertEqual(benchmark["ranking_modes"], ["hybrid", "keyword", "vector"])
        self.assertEqual(benchmark["filter_modes"], ["hybrid", "keyword", "vector"])

        fallback = contract["evidence"]["local_index_fallback_contract"]
        self.assertEqual(fallback["status"], "passed")
        for case in fallback["fallback_cases"]:
            self.assertEqual(case["retrieval_mode"], "keyword")
            self.assertEqual(case["trace"]["executed_mode"], "keyword")
            self.assertEqual(case["trace"]["fallback_from"], case["requested_mode"])
            self.assertEqual(case["trace"]["fallback_reason"], "RuntimeError")
            self.assertEqual(case["query_types"], [case["requested_mode"], "fts"])

        self.assertEqual(
            sorted(item["code"] for item in contract["remaining_gaps"]),
            [
                "current_container_availability_not_replayed",
                "global_vector_contract_not_closed",
                "semantic_embedding_quality_not_proven",
            ],
        )


if __name__ == "__main__":
    unittest.main()
