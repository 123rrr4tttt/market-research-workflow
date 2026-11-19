from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaInventoryContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api schema inventory contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_all_v1_openapi_operations_are_covered_with_typed_success_schemas(self):
        expected = {
            (method.upper(), path)
            for path, methods in backend_app.openapi()["paths"].items()
            if path.startswith("/api/v1/")
            for method in methods
            if method in {"delete", "get", "patch", "post", "put", "head", "options", "trace"}
        }
        inventory = build_inventory(backend_app)
        actual = [(op["method"], op["path"]) for op in inventory["operations"]]
        self.assertTrue(expected)
        self.assertCountEqual(actual, expected)
        self.assertEqual(inventory["summary"]["untyped_openapi_200_operations"], 0)

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
