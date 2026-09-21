from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


pytestmark = pytest.mark.unit


def _load_wave12_gate_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave12_provider_readiness_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave12_provider_readiness_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave12 provider readiness gate module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimal_wave10_contract(*, status: str = "passed") -> dict:
    modes = {
        mode: {
            "executed_mode": mode,
            "retrieval_mode": mode,
            "failures": [],
        }
        for mode in ("keyword", "vector", "hybrid")
    }
    return {
        "contract_version": "wave10-vectorization-quality-gate.v1",
        "status": status,
        "failures": [],
        "evidence_sources": [],
        "evidence": {
            "search_provider_trace": {
                "status": "passed",
                "auto_local_open_search_called": False,
            },
            "local_index_runtime_smoke": {"modes": modes},
            "local_index_benchmark_quality": {
                "threshold_status": "passed",
                "ranking_modes": ["keyword", "vector", "hybrid"],
                "filter_modes": ["keyword", "vector", "hybrid"],
            },
            "local_index_fallback_contract": {
                "fallback_cases": [
                    {
                        "requested_mode": mode,
                        "retrieval_mode": "keyword",
                        "trace": {
                            "fallback_from": mode,
                            "fallback_reason": "RuntimeError",
                        },
                    }
                    for mode in ("vector", "hybrid")
                ]
            },
        },
        "remaining_gaps": [],
    }


class Wave12ProviderReadinessGateTest(unittest.TestCase):
    def test_fresh_wave10_receipt_is_validated_and_forwarded_without_live_probes(self) -> None:
        module = _load_wave12_gate_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            wave10_path = Path(tmpdir) / "wave10.json"
            wave10_path.write_text(json.dumps(_minimal_wave10_contract()), encoding="utf-8")
            contract = module.build_contract(
                enable_live_probes=False,
                wave10_contract_path=wave10_path,
            )
            args = module._parse_args(
                ["--skip-live-probes", "--wave10-contract", str(wave10_path)]
            )

        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["baseline"]["wave10_contract_path"], str(wave10_path))
        self.assertTrue(args.skip_live_probes)
        self.assertEqual(args.wave10_contract, str(wave10_path))
        self.assertEqual(
            {row["live_probe_status"] for row in contract["mode_availability"]["modes"].values()},
            {"not_run"},
        )
        self.assertEqual(
            {row["live_probe_status"] for row in contract["provider_availability"]["providers"].values()},
            {"not_run"},
        )

    def test_fresh_wave10_receipt_fails_closed_on_status_root_and_key_fields(self) -> None:
        module = _load_wave12_gate_module()
        cases = {
            "failed_status_without_upstream_failures": (
                _minimal_wave10_contract(status="failed"),
                "wave10 baseline status expected 'passed'",
            ),
            "non_object_root": ([], "wave10 contract root must be a JSON object"),
            "missing_evidence": (
                {
                    "contract_version": "wave10-vectorization-quality-gate.v1",
                    "status": "passed",
                },
                "wave10 baseline evidence must be a JSON object",
            ),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for name, (payload, expected_failure) in cases.items():
                with self.subTest(name=name):
                    wave10_path = tmp / f"{name}.json"
                    wave10_path.write_text(json.dumps(payload), encoding="utf-8")
                    contract = module.build_contract(
                        enable_live_probes=False,
                        wave10_contract_path=wave10_path,
                    )
                    self.assertEqual(contract["status"], "failed")
                    self.assertTrue(
                        any(expected_failure in failure for failure in contract["failures"]),
                        contract["failures"],
                    )

    def test_gate_reports_live_probe_status_fallbacks_and_unsupported_claims(self) -> None:
        module = _load_wave12_gate_module()
        mode_probe = {
            "status": "partial",
            "probe_type": "test",
            "packages": {"lancedb": "test", "pyarrow": "test"},
            "modes": {
                "keyword": {
                    "live_probe_status": "ready",
                    "executed_mode": "keyword",
                    "fallback_from": None,
                    "fallback_reason": None,
                },
                "vector": {
                    "live_probe_status": "fallback",
                    "executed_mode": "keyword",
                    "fallback_from": "vector",
                    "fallback_reason": "RuntimeError",
                },
                "hybrid": {
                    "live_probe_status": "blocked",
                    "executed_mode": None,
                    "fallback_from": None,
                    "fallback_reason": "missing_optional_dependency",
                },
            },
            "failures": [],
        }

        def provider_probe(provider: str, *, timeout: float, keyword: str = module.DEFAULT_PROBE_KEYWORD) -> dict:
            if provider == "searxng":
                return {
                    "provider": provider,
                    "base_url": "http://127.0.0.1:8088",
                    "live_probe_status": "ready",
                    "result_count": 1,
                    "fallback_reason": None,
                    "trace_failures": [],
                }
            return {
                "provider": provider,
                "base_url": "http://127.0.0.1:8090",
                "live_probe_status": "unavailable",
                "result_count": 0,
                "fallback_reason": "ConnectError",
                "error": "connection refused",
            }

        with patch.object(module, "probe_local_index_modes", return_value=mode_probe):
            with patch.object(module, "probe_provider", side_effect=provider_probe):
                contract = module.build_contract(enable_live_probes=True, probe_timeout=0.01)

        self.assertEqual(contract["contract_version"], "wave12-provider-readiness-gate.v1")
        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(contract["readiness_state"], "partial")
        self.assertTrue(all(row["exists"] for row in contract["target_topics"]))
        self.assertEqual(contract["baseline"]["wave10_status"], "failed")

        modes = contract["mode_availability"]["modes"]
        self.assertEqual(sorted(modes), ["hybrid", "keyword", "vector"])
        self.assertEqual(modes["keyword"]["availability_state"], "ready")
        self.assertEqual(modes["vector"]["live_probe_status"], "fallback")
        self.assertEqual(modes["vector"]["live_fallback_from"], "vector")
        self.assertEqual(modes["vector"]["live_fallback_reason"], "RuntimeError")
        self.assertEqual(modes["vector"]["fallback_contract_reason"], "RuntimeError")
        self.assertEqual(modes["hybrid"]["live_probe_status"], "blocked")
        self.assertEqual(modes["hybrid"]["live_fallback_reason"], "missing_optional_dependency")

        providers = contract["provider_availability"]["providers"]
        self.assertEqual(providers["searxng"]["availability_state"], "ready")
        self.assertFalse(providers["searxng"]["provider_auto_included"])
        self.assertEqual(providers["yacy"]["availability_state"], "explicit_recorded_only")
        self.assertEqual(providers["yacy"]["live_fallback_reason"], "ConnectError")
        self.assertFalse(providers["yacy"]["auto_route_excluded"])

        claim_codes = {item["code"] for item in contract["unsupported_claims"]}
        self.assertIn("provider_auto_quality_not_closed", claim_codes)
        self.assertIn("current_provider_live_quality_not_closed", claim_codes)
        self.assertIn("oss_node_platform_io_not_closed", claim_codes)
        self.assertEqual(
            contract["gate_semantics"]["status_passed_means"],
            "required recorded contracts and report shape are valid",
        )

    def test_skip_live_probes_keeps_gate_passed_with_not_run_visibility(self) -> None:
        module = _load_wave12_gate_module()
        contract = module.build_contract(enable_live_probes=False)

        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(contract["readiness_state"], "partial")
        self.assertEqual(
            {row["live_probe_status"] for row in contract["mode_availability"]["modes"].values()},
            {"not_run"},
        )
        self.assertEqual(
            {row["live_probe_status"] for row in contract["provider_availability"]["providers"].values()},
            {"not_run"},
        )
        self.assertEqual(
            {row["live_fallback_reason"] for row in contract["provider_availability"]["providers"].values()},
            {"live_probe_disabled"},
        )


if __name__ == "__main__":
    unittest.main()
