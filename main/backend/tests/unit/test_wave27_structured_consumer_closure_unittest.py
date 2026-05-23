from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

pytestmark = pytest.mark.unit

from scripts.check_wave27_structured_consumer_closure import (  # noqa: E402
    CONSUMER_TOPIC_ID,
    CONTRACT_VERSION,
    STRUCTURED_TOPIC_ID,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class Wave27StructuredConsumerClosureDecisionUnitTest(unittest.TestCase):
    def test_combined_endpoint_and_consumer_gates_pass(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_ids"], [STRUCTURED_TOPIC_ID, CONSUMER_TOPIC_ID])
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"], result)
        self.assertEqual(result["validation"]["gate_count"], result["validation"]["passed_gate_count"])

        gates = {gate["name"]: gate for gate in result["gates"]}
        for gate_name in (
            "structured_sql_helper_migration",
            "structured_endpoint_projection",
            "consumer_side_facade_contract",
            "consumer_sql_predicate_facade",
            "admin_dashboard_consumer_boundary",
            "policy_state_document_query_boundary",
            "prompt_time_density_consumer_boundary",
        ):
            self.assertIn(gate_name, gates)
            self.assertTrue(gates[gate_name]["passed"], gates[gate_name])

    def test_decision_marks_structured_and_consumer_as_external_blocked_candidates(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["decision"]["status"], "external_blocked_candidate")
        self.assertTrue(result["decision"]["archive_eligible"])
        self.assertTrue(result["decision"]["topics"][STRUCTURED_TOPIC_ID]["archive_eligible"])
        self.assertEqual(result["decision"]["topics"][STRUCTURED_TOPIC_ID]["status"], "external_blocked_candidate")
        self.assertTrue(result["decision"]["topics"][CONSUMER_TOPIC_ID]["archive_eligible"])
        self.assertEqual(result["decision"]["topics"][CONSUMER_TOPIC_ID]["status"], "external_blocked_candidate")
        self.assertEqual(result["repo_local_blockers"], [])
        self.assertEqual(result["external_blockers"][0]["id"], "live_db_api_smoke_not_run")

        builder = result["validation"]["document_query_statement_builder"]
        self.assertEqual(builder["status"], "covered")
        self.assertEqual(
            set(builder["exported_tokens"]),
            {
                "build_document_query_statement",
                "compile_document_query_statement",
                "apply_document_query_to_statement",
                "document_query_to_statement",
            },
        )
        self.assertEqual(builder["compile_gaps"], [])


if __name__ == "__main__":
    unittest.main()
