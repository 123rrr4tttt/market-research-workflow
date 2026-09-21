from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


pytestmark = pytest.mark.unit


def _load_wave57_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave57_production_vector_quality_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave57_production_vector_quality_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave57 production vector quality module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave57ProductionVectorQualityGateTest(unittest.TestCase):
    def test_gate_replays_production_like_corpus_and_closes_when_vector_store_is_available(self) -> None:
        module = _load_wave57_module()
        contract = module.build_contract(require_vector_store=False)

        self.assertEqual(contract["contract_version"], "wave57-production-vector-quality-gate.v1")
        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["global_manifest_update_performed"])
        self.assertFalse(contract["production_traffic_claim_allowed"])
        self.assertEqual(contract["corpus_readback"]["status"], "not_run")
        self.assertEqual(contract["vector_store_readback"]["status"], "not_run")
        self.assertIsNone(contract["vector_store_readback"]["backend"])
        self.assertFalse(contract["production_like_vector_quality_claim_allowed"])
        self.assertFalse(contract["target_topic_migration_ready"])
        self.assertEqual(contract["closed_conditions"], [])

    def test_require_vector_store_passes_in_optional_lancedb_environment(self) -> None:
        module = _load_wave57_module()
        with patch.object(module, "_build_vector_backend", side_effect=AssertionError("must not construct backend")):
            contract = module.build_contract(require_vector_store=True)

        assert_typed_evidence_unavailable(self, contract)
        self.assertEqual(contract["vector_store_readback"]["status"], "not_run")
        self.assertFalse(contract["production_like_vector_quality_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
