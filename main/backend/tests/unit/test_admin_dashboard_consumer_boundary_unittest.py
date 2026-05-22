from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_admin_dashboard_consumer_boundary import (  # noqa: E402
    CONTRACT_VERSION,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class AdminDashboardConsumerBoundaryUnitTestCase(unittest.TestCase):
    def test_checker_passes_for_wave13_admin_dashboard_python_read_slice(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], "2026-03-14-consumer-side-modularization")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["validation"]["direct_instance_extracted_data_read_count"], 0)
        self.assertGreater(result["validation"]["allowed_sql_json_expression_count"], 0)

        surfaces = {item["path"]: item for item in result["checked_surfaces"]}
        self.assertIn("main/backend/app/api/dashboard.py", surfaces)
        self.assertIn("main/backend/app/api/admin.py", surfaces)

        dashboard_functions = {
            item["name"]: item
            for item in surfaces["main/backend/app/api/dashboard.py"]["functions"]
        }
        self.assertEqual(
            set(dashboard_functions),
            {"get_sentiment_analysis", "get_sentiment_sources"},
        )
        for function in dashboard_functions.values():
            self.assertTrue(function["passed"], function)
            self.assertFalse(function["missing_boundary_calls"], function)

        admin_functions = {
            item["name"]: item
            for item in surfaces["main/backend/app/api/admin.py"]["functions"]
        }
        for name in (
            "_augment_market_graph_with_topic_structured",
            "list_social_data",
            "get_content_graph",
            "get_market_graph",
            "get_policy_graph",
        ):
            self.assertIn(name, admin_functions)
            self.assertTrue(admin_functions[name]["passed"], admin_functions[name])
            self.assertFalse(admin_functions[name]["missing_boundary_calls"], admin_functions[name])

    def test_checker_keeps_sql_json_predicates_as_deferred_query_scope(self) -> None:
        result = build_check(REPO_ROOT)
        admin_surface = next(
            item
            for item in result["checked_surfaces"]
            if item["path"] == "main/backend/app/api/admin.py"
        )
        by_name = {item["name"]: item for item in admin_surface["functions"]}

        self.assertGreater(by_name["get_content_graph"]["sql_json_expression_count"], 0)
        self.assertGreater(by_name["get_market_graph"]["sql_json_expression_count"], 0)
        self.assertIn("query-layer work", result["boundary_rule"])


if __name__ == "__main__":
    unittest.main()
