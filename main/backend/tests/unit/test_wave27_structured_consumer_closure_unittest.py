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

    def test_decision_splits_consumer_archive_candidate_from_structured_blocker(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["decision"]["status"], "split_retained_and_external_blocked_candidate")
        self.assertFalse(result["decision"]["archive_eligible"])
        self.assertFalse(result["decision"]["topics"][STRUCTURED_TOPIC_ID]["archive_eligible"])
        self.assertEqual(result["decision"]["topics"][STRUCTURED_TOPIC_ID]["status"], "retained_partial")
        self.assertTrue(result["decision"]["topics"][CONSUMER_TOPIC_ID]["archive_eligible"])
        self.assertEqual(result["decision"]["topics"][CONSUMER_TOPIC_ID]["status"], "external_blocked_candidate")
        blocker_ids = {item["id"] for item in result["repo_local_blockers"]}
        self.assertEqual(blocker_ids, {"generic_document_query_db_statement_builder_missing"})
        self.assertEqual(result["external_blockers"][0]["id"], "live_db_api_smoke_not_run")

        builder = result["validation"]["document_query_statement_builder"]
        self.assertEqual(builder["status"], "missing_repo_local_builder")
        self.assertFalse(builder["exported_tokens"])


if __name__ == "__main__":
    unittest.main()
