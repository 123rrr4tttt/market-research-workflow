from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


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
        assert_typed_evidence_unavailable(
            self,
            contract,
            expected_missing_paths=(
                "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/"
                "2026-05-22/search_provider_trace_contract.json",
                "development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/"
                "2026-05-22/runtime_smoke_results.json",
            ),
        )


if __name__ == "__main__":
    unittest.main()
