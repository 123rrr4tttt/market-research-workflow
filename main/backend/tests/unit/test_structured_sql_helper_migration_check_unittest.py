from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_structured_sql_helper_migration import (  # noqa: E402
    CONTRACT_VERSION,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class StructuredSqlHelperMigrationCheckUnitTestCase(unittest.TestCase):
    def test_checker_preserves_covered_query_helper_and_endpoint_inventory(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], "2026-03-12-data-structured-service-modularization")
        self.assertEqual(result["document_query_contract_version"], "document_queries.v1")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"], result["validation"])
        self.assertEqual(result["validation"]["covered_surface_gap_count"], 0)

        covered = {item["surface_id"]: item for item in result["covered_query_helpers"]}
        for surface_id in (
            "document_query_contract",
            "document_query_statement_builder",
            "policy_sql_expression_helpers",
            "writing_material_query_helpers",
            "prompt_time_density_sql_helper_consumer",
            "search_endpoint_document_query_projection",
            "api_search_endpoint_uses_projection",
        ):
            self.assertIn(surface_id, covered)
            self.assertEqual(covered[surface_id]["status"], "covered", covered[surface_id])

        self.assertEqual(covered["search_endpoint_document_query_projection"]["endpoint"], "/api/v1/search")
        self.assertEqual(covered["api_search_endpoint_uses_projection"]["endpoint"], "/api/v1/search")

    def test_checker_tracks_admin_structured_sql_predicate_boundaries(self) -> None:
        result = build_check(REPO_ROOT)
        boundaries = {item["boundary_id"]: item for item in result["remaining_migration_boundaries"]}

        for boundary_id in (
            "admin_documents_list_has_extracted_data_filter",
            "admin_social_data_structured_filters",
            "admin_content_graph_structured_filters",
            "admin_market_graph_structured_filters",
            "admin_policy_graph_structured_filters",
        ):
            self.assertIn(boundary_id, boundaries)
            self.assertIn(
                boundaries[boundary_id]["migration_status"],
                {"deferred", "covered_or_removed"},
                boundaries[boundary_id],
            )
            self.assertEqual(boundaries[boundary_id]["direct_sql_json_expression_count"], 0)

        self.assertEqual(boundaries["admin_policy_graph_structured_filters"]["endpoint"], "/api/v1/admin/policy-graph")
        self.assertEqual(result["validation"]["deferred_boundary_count"], 0)


if __name__ == "__main__":
    unittest.main()
