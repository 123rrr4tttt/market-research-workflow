from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave8_contract_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave8_search_vectorization_contract.py"
    )
    spec = importlib.util.spec_from_file_location("wave8_search_vectorization_contract", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave8 contract module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave8SearchVectorizationContractTest(unittest.TestCase):
    def test_wave8_contract_reuses_recorded_evidence_without_claiming_live_services(self) -> None:
        module = _load_wave8_contract_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave8-search-vectorization-runtime-contract.v1")
        self.assertEqual(contract["scope"], "deterministic_reuse_no_network_no_container_start")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])

        provider_trace = contract["evidence"]["search_provider_trace"]
        self.assertEqual(provider_trace["status"], "passed")
        self.assertEqual(provider_trace["explicit_providers"], ["searxng", "yacy"])
        self.assertFalse(provider_trace["auto_local_open_search_called"])

        container_replay = contract["evidence"]["search_provider_container_replay"]
        self.assertEqual(container_replay["status"], "passed")
        self.assertEqual(container_replay["source"], "preexisting_artifact_only")
        self.assertFalse(container_replay["current_container_availability_asserted"])

        runtime = contract["evidence"]["local_index_runtime_smoke"]
        self.assertEqual(runtime["status"], "passed")
        for mode in ("keyword", "vector", "hybrid"):
            self.assertEqual(runtime["modes"][mode]["executed_mode"], mode)
            self.assertEqual(runtime["modes"][mode]["retrieval_mode"], mode)
            self.assertEqual(runtime["modes"][mode]["top_chunk_id"], runtime["modes"][mode]["expected_chunk_id"])
            self.assertEqual(runtime["modes"][mode]["failures"], [])

        benchmark = contract["evidence"]["local_index_benchmark"]
        self.assertEqual(benchmark["status"], "passed")
        self.assertEqual(benchmark["ranking_modes"], ["hybrid", "keyword", "vector"])
        self.assertEqual(benchmark["filter_modes"], ["hybrid", "keyword", "vector"])
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
