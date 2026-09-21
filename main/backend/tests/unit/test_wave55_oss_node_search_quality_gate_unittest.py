from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


pytestmark = pytest.mark.unit


def _load_wave55_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave55_oss_node_search_quality_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave55_oss_node_search_quality_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave55 OSS node search quality module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave55OssNodeSearchQualityGateTest(unittest.TestCase):
    def test_explicit_prerequisite_paths_are_available_to_readback_and_cli(self) -> None:
        module = _load_wave55_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            trace_path = tmp / "trace.json"
            provider_path = tmp / "provider.json"
            readback, failures = module._input_artifact_readback(
                open_search_trace_path=trace_path,
                live_embedding_provider_gate_path=provider_path,
            )
            args = module._parse_args(
                [
                    "--open-search-trace",
                    str(trace_path),
                    "--live-embedding-provider-gate",
                    str(provider_path),
                ]
            )

        self.assertNotEqual(failures, [])
        self.assertEqual(readback["open_search_trace"]["path"], str(trace_path))
        self.assertEqual(readback["live_embedding_provider_gate"]["path"], str(provider_path))
        self.assertEqual(args.open_search_trace, str(trace_path))
        self.assertEqual(args.live_embedding_provider_gate, str(provider_path))

    def test_gate_closes_repo_local_open_search_quality_and_reduces_semantic_scope(self) -> None:
        module = _load_wave55_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave55-oss-node-search-quality-gate.v1")
        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(
            contract["scope"],
            "repo_local_controlled_open_search_and_semantic_quality_no_network",
        )
        self.assertFalse(contract["local_open_search_quality_claim_allowed"])
        self.assertFalse(contract["repo_local_semantic_quality_claim_allowed"])
        self.assertFalse(contract["production_quality_claim_allowed"])
        self.assertEqual(contract["closed_conditions"], [])
        self.assertEqual(contract["reduced_conditions"], [])
        self.assertIn("production_semantic_embedding_quality_not_proven", contract["remaining_conditions"])
        self.assertIn("local_open_search_live_container_quality_not_replayed", contract["remaining_conditions"])

        self.assertEqual(contract["input_artifact_readback"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
