from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


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
    def test_explicit_prerequisite_paths_are_available_to_build_and_cli(self) -> None:
        module = _load_wave19_manifest_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wave14_path = tmp / "wave14.json"
            wave18_path = tmp / "wave18.json"
            contract = module.build_contract(wave14_path=wave14_path, wave18_path=wave18_path)
            args = module._parse_args(
                [
                    "--wave14-provider-capability",
                    str(wave14_path),
                    "--wave18-hybrid-readback",
                    str(wave18_path),
                ]
            )

        self.assertEqual(contract["inputs"]["wave14"]["path"], str(wave14_path))
        self.assertEqual(contract["inputs"]["wave18"]["path"], str(wave18_path))
        self.assertEqual(args.wave14_provider_capability, str(wave14_path))
        self.assertEqual(args.wave18_hybrid_readback, str(wave18_path))

    def test_manifest_records_modes_fallback_trace_quality_and_no_live_closure(self) -> None:
        module = _load_wave19_manifest_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave19-vectorization-provider-manifest.v1")
        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(contract["manifest_state"], "partial")
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertFalse(contract["provider_live_closure_claim_allowed"])
        self.assertFalse(contract["semantic_quality_claim_allowed"])
        self.assertFalse(contract["oss_node_platform_io"]["closure_claim_allowed"])

    def test_manifest_missing_source_fails_typed_without_reading_deleted_artifact(self) -> None:
        module = _load_wave19_manifest_module()
        contract = module.build_contract()

        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["closure_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
