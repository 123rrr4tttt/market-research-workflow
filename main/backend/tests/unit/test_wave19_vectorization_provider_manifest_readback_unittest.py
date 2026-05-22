from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave19_manifest_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave19_vectorization_provider_manifest_readback.py"
    )
    spec = importlib.util.spec_from_file_location("wave19_vectorization_provider_manifest_readback", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave19 manifest module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave19VectorizationProviderManifestReadbackTest(unittest.TestCase):
    def test_manifest_records_modes_fallback_trace_quality_and_no_live_closure(self) -> None:
        module = _load_wave19_manifest_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave19-vectorization-provider-manifest.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["manifest_state"], "partial")
        self.assertEqual(contract["failures"], [])
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertFalse(contract["provider_live_closure_claim_allowed"])
        self.assertFalse(contract["semantic_quality_claim_allowed"])

        rows = {row["mode"]: row for row in contract["provider_manifest"]["modes"]}
        self.assertEqual(sorted(rows), ["hybrid", "keyword", "vector"])

        self.assertTrue(rows["keyword"]["capabilities"]["keyword"])
        self.assertFalse(rows["keyword"]["capabilities"]["vector"])
        self.assertFalse(rows["keyword"]["capabilities"]["hybrid"])
        self.assertEqual(rows["keyword"]["fallback"]["fallback_mode"], "none")
        self.assertIsNone(rows["keyword"]["fallback"]["fallback_reason"])

        self.assertFalse(rows["vector"]["capabilities"]["keyword"])
        self.assertTrue(rows["vector"]["capabilities"]["vector"])
        self.assertFalse(rows["vector"]["capabilities"]["hybrid"])
        self.assertEqual(rows["vector"]["fallback"]["fallback_mode"], "keyword")
        self.assertEqual(rows["vector"]["fallback"]["fallback_reason"], "RuntimeError")

        self.assertTrue(rows["hybrid"]["capabilities"]["keyword"])
        self.assertTrue(rows["hybrid"]["capabilities"]["vector"])
        self.assertTrue(rows["hybrid"]["capabilities"]["hybrid"])
        self.assertEqual(rows["hybrid"]["fallback"]["fallback_mode"], "keyword")
        self.assertEqual(rows["hybrid"]["fallback"]["fallback_reason"], "RuntimeError")

        for mode, row in rows.items():
            self.assertTrue(row["capabilities"]["recorded_runtime_available"])
            self.assertTrue(row["capabilities"]["recorded_benchmark_available"])
            self.assertTrue(row["capabilities"]["deterministic_repo_manifest_only"])
            self.assertFalse(row["capabilities"]["live_provider_verified"])
            self.assertFalse(row["capabilities"]["semantic_quality_claim_allowed"])
            self.assertFalse(row["closure_claim_allowed"])
            self.assertEqual(row["trace_quality"]["status"], "passed")
            self.assertGreater(row["trace_quality"]["trace_row_count"], 0)
            self.assertFalse(row["trace_quality"]["provider_live_verified"])
            self.assertTrue(row["trace_quality"]["provider_live_verified_all_false"])
            self.assertFalse(row["trace_quality"]["semantic_quality_claim_allowed"])
            self.assertTrue(row["trace_quality"]["semantic_quality_claims_all_false"])
            for component in module.REQUIRED_TRACE_COMPONENTS[mode]:
                self.assertTrue(row["trace_quality"]["component_coverage"][component])

        boundary = contract["external_provider_boundary"]
        self.assertEqual(boundary["status"], "passed")
        self.assertFalse(boundary["external_provider_sealed"])
        self.assertFalse(boundary["provider_auto_promotion_allowed"])
        self.assertIn("external_embedding_provider_live_not_verified", boundary["gap_codes"])
        self.assertIn("semantic_embedding_quality_not_proven", boundary["gap_codes"])
        self.assertIn("oss_node_platform_io_sla_not_closed", boundary["gap_codes"])
        self.assertFalse(contract["oss_node_platform_io"]["closure_claim_allowed"])

    def test_manifest_fails_if_source_trace_claims_live_provider_verification(self) -> None:
        module = _load_wave19_manifest_module()
        wave18 = json.loads(module.WAVE18_HYBRID_READBACK.read_text(encoding="utf-8"))
        wave18["mode_identity_readback"]["cases"][0]["trace_readback"][0]["trace"]["quality_trace"][
            "provider_live_verified"
        ] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            wave18_path = Path(tmpdir) / "wave18.json"
            wave18_path.write_text(json.dumps(wave18), encoding="utf-8")
            contract = module.build_contract(wave18_path=wave18_path)

        self.assertEqual(contract["status"], "failed")
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertTrue(
            any("provider_live_verified must be false" in failure for failure in contract["failures"])
        )


if __name__ == "__main__":
    unittest.main()
