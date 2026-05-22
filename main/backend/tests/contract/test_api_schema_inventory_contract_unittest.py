from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC_PATH = (
    _REPO_ROOT
    / "development"
    / "latest-dev-docs"
    / "backend-docs"
    / "B_API"
    / "API_SCHEMA_INVENTORY_2026-05-22.md"
)

try:
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory, render_markdown

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaInventoryContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api schema inventory contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_schema_inventory_doc_matches_current_openapi_surface(self):
        self.assertTrue(_DOC_PATH.exists(), msg=f"missing schema inventory: {_DOC_PATH}")
        documented = _DOC_PATH.read_text(encoding="utf-8")
        current = render_markdown(build_inventory(backend_app))

        if documented != current:
            self.fail(
                "API_SCHEMA_INVENTORY_2026-05-22.md is out of sync with app.openapi(); "
                "regenerate it with `cd main/backend && ./.venv311/bin/python scripts/generate_api_schema_inventory.py`."
            )

    def test_schema_inventory_summary_keeps_route_map_scope_explicit(self):
        current = build_inventory(backend_app)
        summary = current["summary"]

        self.assertEqual(summary["api_v1_operations"], 253)
        self.assertEqual(summary["api_router_operations"], 250)
        self.assertEqual(summary["app_level_operations"], 3)
        self.assertEqual(summary["request_body_operations"], 114)
        self.assertGreaterEqual(summary["component_schemas"], 100)
        self.assertEqual(summary["untyped_openapi_200_operations"], 0)

    def test_major_request_and_response_schema_surfaces_are_visible(self):
        operations = {
            (operation["method"], operation["path"]): operation
            for operation in build_inventory(backend_app)["operations"]
        }

        self.assertEqual(
            operations[("POST", "/api/v1/projects/auto-create")]["request_body"],
            "AutoCreateProjectPayload",
        )
        self.assertEqual(
            operations[("POST", "/api/v1/ingest/graph/structured-search")]["request_body"],
            "GraphStructuredSearchRequest",
        )
        self.assertEqual(
            operations[("POST", "/api/v1/resource_pool/discover/search-contract")]["request_body"],
            "DiscoverSearchContractPayload",
        )
        self.assertEqual(
            operations[("GET", "/api/v1/policies")]["response_model"],
            "ApiEnvelope[PoliciesListData]",
        )
        self.assertEqual(
            operations[("GET", "/api/v1/policies")]["response_200_schema"],
            "ApiEnvelope_PoliciesListData_",
        )
        self.assertEqual(
            operations[("POST", "/api/v1/workflow-graph/compile")]["response_200_schema"],
            "ApiEnvelope_dict_str__Any__",
        )


if __name__ == "__main__":
    unittest.main()
