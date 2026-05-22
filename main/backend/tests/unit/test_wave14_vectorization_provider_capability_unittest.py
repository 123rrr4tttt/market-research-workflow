from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave14_gate_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "main"
        / "backend"
        / "scripts"
        / "check_wave14_vectorization_provider_capability.py"
    )
    spec = importlib.util.spec_from_file_location("check_wave14_vectorization_provider_capability", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave14 provider capability module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave14VectorizationProviderCapabilityTest(unittest.TestCase):
    def test_gate_reports_local_capability_external_gap_and_no_closure_claim(self) -> None:
        module = _load_wave14_gate_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave14-vectorization-provider-capability.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["capability_state"], "partial")
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertIn("closure_claim_allowed=false", contract["assertions"])

        local = contract["local_capability"]
        self.assertEqual(local["status"], "passed")
        self.assertTrue(local["mode_contract_exported"])
        self.assertEqual(local["supported_modes"], ["keyword", "vector", "hybrid"])
        self.assertTrue(local["deterministic_vector_provider"]["available"])
        self.assertFalse(local["deterministic_vector_provider"]["external_dependency"])
        self.assertFalse(local["deterministic_vector_provider"]["semantic_quality_claim_allowed"])
        for mode in ["keyword", "vector", "hybrid"]:
            self.assertTrue(local["modes"][mode]["recorded_runtime_available"])
            self.assertTrue(local["modes"][mode]["recorded_benchmark_available"])
            self.assertTrue(local["modes"][mode]["fallback_visible"])

        gap = contract["external_provider_gap"]
        self.assertFalse(gap["external_provider_sealed"])
        self.assertFalse(gap["provider_auto_promotion_allowed"])
        self.assertIn("external_embedding_provider_live_not_verified", gap["gap_codes"])
        self.assertIn("semantic_embedding_quality_not_proven", gap["gap_codes"])
        self.assertIn("oss_node_platform_io_sla_not_closed", gap["gap_codes"])
        for provider in ["searxng", "yacy"]:
            self.assertFalse(gap["local_open_search_providers"][provider]["provider_auto_included"])
            self.assertFalse(gap["local_open_search_providers"][provider]["external_provider_claim_allowed"])

        self.assertFalse(contract["oss_node_platform_io"]["closure_claim_allowed"])
        self.assertIn("unsupported_claim_codes", contract["oss_node_platform_io"]["must_propagate_gap_fields"])

    def test_malformed_provider_auto_evidence_fails_the_gate(self) -> None:
        module = _load_wave14_gate_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wave10_path = tmp / "wave10.json"
            wave12_path = tmp / "wave12.json"
            wave10_path.write_text(json.dumps(_minimal_wave10_contract(auto_called=True)), encoding="utf-8")
            wave12_path.write_text(json.dumps(_minimal_wave12_summary()), encoding="utf-8")

            contract = module.build_contract(wave10_path=wave10_path, wave12_path=wave12_path)

        self.assertEqual(contract["status"], "failed")
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertTrue(
            any("provider=auto local open-search exclusion is not recorded" in failure for failure in contract["failures"])
        )


def _minimal_wave10_contract(*, auto_called: bool) -> dict:
    modes = {
        mode: {
            "executed_mode": mode,
            "retrieval_mode": mode,
            "failures": [],
        }
        for mode in ["keyword", "vector", "hybrid"]
    }
    return {
        "status": "passed",
        "evidence": {
            "search_provider_trace": {
                "status": "passed",
                "auto_local_open_search_called": auto_called,
            },
            "local_index_runtime_smoke": {"modes": modes},
            "local_index_benchmark_quality": {
                "threshold_status": "passed",
                "ranking_modes": ["hybrid", "keyword", "vector"],
                "filter_modes": ["hybrid", "keyword", "vector"],
            },
            "local_index_fallback_contract": {
                "fallback_cases": [
                    {
                        "requested_mode": "vector",
                        "retrieval_mode": "keyword",
                        "trace": {"fallback_from": "vector", "fallback_reason": "RuntimeError"},
                    },
                    {
                        "requested_mode": "hybrid",
                        "retrieval_mode": "keyword",
                        "trace": {"fallback_from": "hybrid", "fallback_reason": "RuntimeError"},
                    },
                ]
            },
        },
    }


def _minimal_wave12_summary() -> dict:
    return {
        "status": "passed",
        "mode_availability": {
            "modes": {
                mode: {
                    "live_probe_status": "not_run",
                    "live_fallback_reason": "test",
                }
                for mode in ["keyword", "vector", "hybrid"]
            }
        },
        "provider_availability": {
            "providers": {
                provider: {
                    "live_probe_status": "not_run",
                    "live_result_count": None,
                    "live_fallback_reason": "test",
                }
                for provider in ["searxng", "yacy"]
            }
        },
        "unsupported_claims": [
            {"code": "provider_auto_quality_not_closed"},
            {"code": "current_provider_live_quality_not_closed"},
            {"code": "current_local_index_live_quality_not_closed"},
            {"code": "semantic_embedding_quality_not_closed"},
            {"code": "oss_node_platform_io_not_closed"},
        ],
    }


if __name__ == "__main__":
    unittest.main()
