from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_INGEST_OPERATIONS = frozenset(
    (
        ("GET", "/api/v1/ingest/config"),
        ("POST", "/api/v1/ingest/config"),
        ("POST", "/api/v1/ingest/market"),
        ("POST", "/api/v1/ingest/url/single"),
        ("GET", "/api/v1/ingest/history"),
        ("POST", "/api/v1/ingest/source-library/run"),
        ("POST", "/api/v1/ingest/source-library/sync"),
        ("GET", "/api/v1/ingest/news-resources"),
        ("POST", "/api/v1/ingest/news/resource/{resource_id}"),
        ("POST", "/api/v1/ingest/subprojects/{subproject_key}/news/{resource_id}"),
        ("POST", "/api/v1/ingest/social/reddit"),
        ("POST", "/api/v1/ingest/reports/weekly"),
        ("POST", "/api/v1/ingest/reports/monthly"),
        ("POST", "/api/v1/ingest/data-api"),
        ("POST", "/api/v1/ingest/graph/structured-search"),
        ("POST", "/api/v1/ingest/policy/regulation"),
        ("POST", "/api/v1/ingest/commodity/metrics"),
        ("POST", "/api/v1/ingest/ecom/prices"),
    )
)

_RESOURCE_POOL_OPERATIONS = frozenset(
    (
        ("POST", "/api/v1/resource_pool/extract/from-documents"),
        ("GET", "/api/v1/resource_pool/urls"),
        ("GET", "/api/v1/resource_pool/open-source-presets"),
        ("POST", "/api/v1/resource_pool/import/open-source-presets"),
        ("POST", "/api/v1/resource_pool/capture/enable"),
        ("POST", "/api/v1/resource_pool/capture/from-tasks"),
        ("GET", "/api/v1/resource_pool/site-entries"),
        ("POST", "/api/v1/resource_pool/site-entries"),
        ("GET", "/api/v1/resource_pool/site_entries"),
        ("POST", "/api/v1/resource_pool/site_entries"),
        ("GET", "/api/v1/resource_pool/site-entries/grouped"),
        ("GET", "/api/v1/resource_pool/site_entries/grouped"),
        ("PATCH", "/api/v1/resource_pool/site-entries/lifecycle"),
        ("PATCH", "/api/v1/resource_pool/site_entries/lifecycle"),
        ("POST", "/api/v1/resource_pool/discover/search-contract"),
        ("POST", "/api/v1/resource_pool/discover/site-entries"),
        ("POST", "/api/v1/resource_pool/site_entries/simplify"),
        ("POST", "/api/v1/resource_pool/site_entries/recommend"),
        ("POST", "/api/v1/resource_pool/site_entries/recommend-batch"),
        ("POST", "/api/v1/resource_pool/unified-search"),
        ("POST", "/api/v1/resource_pool/source-library/collect"),
    )
)

_EXPECTED_OPERATIONS = {
    "ingest.py": _INGEST_OPERATIONS,
    "resource_pool.py": _RESOURCE_POOL_OPERATIONS,
}

try:
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaIngestResourceContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api schema ingest/resource tests require backend dependencies: {_IMPORT_ERROR}")

    def test_ingest_and_resource_pool_200_schemas_are_enveloped(self):
        operations = build_inventory(backend_app)["operations"]
        by_module = {
            module: [operation for operation in operations if operation["source_module"] == module]
            for module in _EXPECTED_OPERATIONS
        }

        actual_operations = {
            module: {(operation["method"], operation["path"]) for operation in rows}
            for module, rows in by_module.items()
        }
        self.assertEqual(actual_operations, _EXPECTED_OPERATIONS)
        for module, rows in by_module.items():
            untyped_paths = [
                f"{operation['method']} {operation['path']}"
                for operation in rows
                if operation["response_200_schema"] == "untyped"
            ]
            self.assertEqual(untyped_paths, [], msg=f"{module} still has untyped 200 schemas")
            self.assertEqual(
                {operation["response_model"] for operation in rows},
                {"ApiEnvelope[Any]"},
                msg=f"{module} should expose conservative envelope response models",
            )
            self.assertEqual(
                {operation["response_200_schema"] for operation in rows},
                {"ApiEnvelope_Any_"},
                msg=f"{module} should expose a stable OpenAPI envelope schema",
            )


if __name__ == "__main__":
    unittest.main()
