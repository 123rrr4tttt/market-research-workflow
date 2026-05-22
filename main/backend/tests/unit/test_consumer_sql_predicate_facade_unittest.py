from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services import document_queries  # noqa: E402
from scripts.check_consumer_sql_predicate_facade import (  # noqa: E402
    CONTRACT_VERSION,
    REQUIRED_FACADE_FUNCTIONS,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class ConsumerSqlPredicateFacadeUnitTestCase(unittest.TestCase):
    def test_checker_passes_for_admin_dashboard_sql_predicate_facade(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], "2026-03-14-consumer-side-modularization")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["validation"]["direct_admin_dashboard_document_extracted_data_read_count"], 0)
        self.assertGreater(result["facade"]["owned_document_extracted_data_expression_count"], 0)
        self.assertFalse(result["facade"]["missing_functions"])
        self.assertFalse(result["exports"]["missing_exports"])

        surfaces = {item["path"]: item for item in result["checked_surfaces"]}
        self.assertEqual(
            set(surfaces),
            {
                "main/backend/app/api/admin.py",
                "main/backend/app/api/dashboard.py",
            },
        )
        for surface in surfaces.values():
            self.assertTrue(surface["passed"], surface)
            self.assertFalse(surface["direct_document_extracted_data_reads"], surface)
            for function in surface["functions"]:
                self.assertTrue(function["passed"], function)
                self.assertFalse(function["missing_facade_calls"], function)
                self.assertFalse(function["direct_document_extracted_data_reads"], function)

    def test_consumer_predicate_helpers_compile_to_expected_json_paths(self) -> None:
        compiled = {
            "social_platform": str(
                document_queries.social_platform_condition("reddit").compile(compile_kwargs={"literal_binds": True})
            ),
            "social_sentiment": str(
                document_queries.social_sentiment_orientation_condition("positive").compile(
                    compile_kwargs={"literal_binds": True}
                )
            ),
            "content_graph": str(
                document_queries.content_graph_structured_condition().compile(compile_kwargs={"literal_binds": True})
            ),
            "market_graph": str(
                document_queries.market_graph_structured_condition(deep_view=True, topic_scope="company").compile(
                    compile_kwargs={"literal_binds": True}
                )
            ),
            "market_report_date": str(
                document_queries.market_report_date_expr().compile(compile_kwargs={"literal_binds": True})
            ),
            "policy_type": str(
                document_queries.policy_graph_type_ilike_condition("regulation").compile(
                    compile_kwargs={"literal_binds": True}
                )
            ),
        }

        self.assertEqual(set(REQUIRED_FACADE_FUNCTIONS) - set(document_queries.__all__), set())
        self.assertIn("platform", compiled["social_platform"])
        self.assertIn("sentiment_orientation", compiled["social_sentiment"])
        self.assertIn("entities_relations", compiled["content_graph"])
        self.assertIn("company_structured", compiled["market_graph"])
        self.assertIn("report_date", compiled["market_report_date"])
        self.assertIn("DATE", compiled["market_report_date"])
        self.assertIn("policy_type", compiled["policy_type"])


if __name__ == "__main__":
    unittest.main()
