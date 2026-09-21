from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


pytestmark = pytest.mark.unit


def _load_wave18_readback_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave18_vectorization_hybrid_readback.py"
    )
    spec = importlib.util.spec_from_file_location("wave18_vectorization_hybrid_readback", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave18 readback module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave18VectorizationHybridReadbackTest(unittest.TestCase):
    def test_explicit_prerequisite_paths_are_available_to_build_and_cli(self) -> None:
        module = _load_wave18_readback_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paths = {name: tmp / f"{name}.json" for name in ("wave8", "wave10", "wave12", "wave14")}
            contract = module.build_contract(
                wave8_path=paths["wave8"],
                wave10_path=paths["wave10"],
                wave12_path=paths["wave12"],
                wave14_path=paths["wave14"],
            )
            args = module._parse_args(
                [
                    "--wave8-contract",
                    str(paths["wave8"]),
                    "--wave10-contract",
                    str(paths["wave10"]),
                    "--wave12-provider-readiness",
                    str(paths["wave12"]),
                    "--wave14-provider-capability",
                    str(paths["wave14"]),
                ]
            )

        for name, path in paths.items():
            self.assertEqual(contract["inputs"][name]["path"], str(path))
        self.assertEqual(args.wave8_contract, str(paths["wave8"]))
        self.assertEqual(args.wave10_contract, str(paths["wave10"]))
        self.assertEqual(args.wave12_provider_readiness, str(paths["wave12"]))
        self.assertEqual(args.wave14_provider_capability, str(paths["wave14"]))

    def test_checker_proves_mode_identity_quality_trace_and_readback_without_live_closure(self) -> None:
        module = _load_wave18_readback_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave18-vectorization-hybrid-readback.v1")
        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertFalse(contract["provider_live_closure_claim_allowed"])
        self.assertFalse(contract["semantic_quality_claim_allowed"])
        self.assertEqual(
            contract["scope"],
            "deterministic_repo_local_fixture_no_network_no_container_no_live_provider_closure",
        )

        self.assertEqual(
            sorted(contract["mode_identity_readback"]["exported_modes"]),
            ["hybrid", "keyword", "vector"],
        )
        self.assertEqual(contract["mode_identity_readback"]["status"], "passed")
        cases = {case["mode"]: case for case in contract["mode_identity_readback"]["cases"]}
        self.assertEqual(sorted(cases), ["hybrid", "keyword", "vector"])
        self.assertEqual(cases["keyword"]["chunk_order"], ["kw-primary", "kw-secondary"])
        self.assertEqual(cases["vector"]["chunk_order"], ["vec-primary", "vec-secondary"])
        self.assertEqual(cases["hybrid"]["chunk_order"], ["hybrid-primary", "hybrid-secondary"])

        for mode, case in cases.items():
            self.assertEqual(case["failures"], [])
            for row in case["trace_readback"]:
                trace = row["trace"]
                self.assertEqual(row["retrieval_mode"], mode)
                self.assertEqual(trace["requested_mode"], mode)
                self.assertEqual(trace["executed_mode"], mode)
                self.assertNotIn("fallback_from", trace)
                self.assertNotIn("fallback_reason", trace)
                self.assertEqual(trace["quality_trace"]["mode_identity"], mode)
                self.assertFalse(trace["quality_trace"]["provider_live_verified"])
                self.assertFalse(trace["quality_trace"]["semantic_quality_claim_allowed"])
                self.assertEqual(trace["readback"]["chunk_id"], row["chunk_id"])
                self.assertEqual(trace["readback"]["retrieval_mode"], mode)
                components = trace["quality_trace"]["score_components"]
                if mode == "keyword":
                    self.assertIsNotNone(components["keyword_score"])
                if mode == "vector":
                    self.assertIsNotNone(components["vector_score"])
                if mode == "hybrid":
                    self.assertIsNotNone(components["keyword_score"])
                    self.assertIsNotNone(components["vector_score"])
                    self.assertIsNotNone(components["hybrid_score"])

        self.assertEqual(
            sorted(item["code"] for item in contract["remaining_gaps"]),
            [
                "live_provider_quality_not_closed",
                "oss_node_platform_io_sla_not_closed",
                "semantic_embedding_quality_not_proven",
            ],
        )
        self.assertEqual(
            contract["gate_semantics"]["status_passed_does_not_mean"],
            (
                "live embedding providers, SearXNG/YaCy live quality, provider=auto promotion, "
                "semantic relevance quality, or OSS node SLA are sealed"
            ),
        )


if __name__ == "__main__":
    unittest.main()
