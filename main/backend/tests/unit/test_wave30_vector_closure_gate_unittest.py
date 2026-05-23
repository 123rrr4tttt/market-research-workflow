from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_wave30_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave30_vector_closure_gate.py"
    )
    spec = importlib.util.spec_from_file_location("wave30_vector_closure_gate", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave30 closure module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave30VectorClosureGateTest(unittest.TestCase):
    def test_gate_closes_agent_matrix_and_main_search_schema_join_blocker(self) -> None:
        module = _load_wave30_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave30-vector-closure-gate.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertIn(
            "agent_matrix_and_main_search_schema_not_joined",
            contract["closed_repo_local_blockers"],
        )
        self.assertEqual(contract["remaining_repo_local_blockers"], [])
        self.assertEqual(contract["agent_matrix"]["evidence_hit_count"], 2)
        self.assertEqual(contract["sample_agent_matrix_retrieval_run"]["retrieval_family"], "agent_matrix")
        agent_hit = contract["sample_agent_matrix_retrieval_run"]["evidence_hits"][0]
        self.assertEqual(agent_hit["retrieval_family"], "agent_matrix")
        self.assertEqual(agent_hit["global_vector_object"]["object_type"], "source_candidate")


if __name__ == "__main__":
    unittest.main()
