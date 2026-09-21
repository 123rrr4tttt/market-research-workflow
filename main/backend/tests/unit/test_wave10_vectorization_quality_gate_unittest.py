from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


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
    def test_explicit_input_paths_are_available_to_build_and_cli(self) -> None:
        module = _load_wave10_gate_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            trace_path = tmp / "trace.json"
            runtime_path = tmp / "runtime.json"
            benchmark_path = tmp / "benchmark.json"
            contract = module.build_contract(
                search_provider_trace_path=trace_path,
                local_index_runtime_path=runtime_path,
                local_index_benchmark_path=benchmark_path,
            )
            args = module._parse_args(
                [
                    "--search-provider-trace",
                    str(trace_path),
                    "--local-index-runtime",
                    str(runtime_path),
                    "--local-index-benchmark",
                    str(benchmark_path),
                ]
            )

        self.assertEqual(contract["evidence"]["search_provider_trace"]["path"], str(trace_path))
        self.assertEqual(contract["evidence"]["local_index_runtime_smoke"]["path"], str(runtime_path))
        self.assertEqual(contract["evidence"]["local_index_benchmark_quality"]["path"], str(benchmark_path))
        self.assertEqual(args.search_provider_trace, str(trace_path))
        self.assertEqual(args.local_index_runtime, str(runtime_path))
        self.assertEqual(args.local_index_benchmark, str(benchmark_path))

    def test_gate_checks_provider_trace_modes_thresholds_and_fallback_reason(self) -> None:
        module = _load_wave10_gate_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave10-vectorization-quality-gate.v1")
        self.assertEqual(contract["scope"], "deterministic_local_fixture_no_network_no_container_start")
        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(contract["quality_thresholds"]["required_modes"], ["keyword", "vector", "hybrid"])

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
