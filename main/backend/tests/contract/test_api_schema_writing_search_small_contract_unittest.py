from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_TARGET_MODULE_OPERATIONS = {
    "indexer.py": frozenset((("POST", "/api/v1/indexer/policy"),)),
    "reports.py": frozenset((("POST", "/api/v1/reports"),)),
    "search.py": frozenset(
        (
            ("GET", "/api/v1/search/runs/{retrieval_run_id}"),
            ("GET", "/api/v1/search"),
            ("POST", "/api/v1/search/_init"),
        )
    ),
    "writing.py": frozenset(
        (
            ("GET", "/api/v1/writing/documents"),
            ("POST", "/api/v1/writing/documents"),
            ("DELETE", "/api/v1/writing/documents/{doc_id}"),
            ("GET", "/api/v1/writing/documents/{doc_id}"),
            ("PATCH", "/api/v1/writing/documents/{doc_id}"),
            ("POST", "/api/v1/writing/documents/{doc_id}/draft"),
            ("GET", "/api/v1/writing/documents/{doc_id}/citations"),
            ("POST", "/api/v1/writing/documents/{doc_id}/citations"),
            ("GET", "/api/v1/writing/templates"),
            ("POST", "/api/v1/writing/templates/validate"),
            ("POST", "/api/v1/writing/keyword-cards"),
            ("POST", "/api/v1/writing/keyword-cards/preview"),
            ("GET", "/api/v1/writing/cards/{card_id}"),
            ("GET", "/api/v1/writing/suggest"),
            ("POST", "/api/v1/writing/llm-actions"),
            ("GET", "/api/v1/writing/llm-actions/history"),
            ("GET", "/api/v1/writing/llm-actions/{job_id}"),
            ("POST", "/api/v1/writing/export/markdown"),
        )
    ),
}
_TARGET_MODULE_COUNTS = {
    module: len(operations) for module, operations in _TARGET_MODULE_OPERATIONS.items()
}

try:
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaWritingSearchSmallContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing/search/small schema tests require backend dependencies: {_IMPORT_ERROR}")

    def _target_operations(self) -> list[dict]:
        inventory = build_inventory(backend_app)
        return [
            operation
            for operation in inventory["operations"]
            if operation["source_module"] in _TARGET_MODULE_OPERATIONS
        ]

    def test_target_modules_have_expected_operation_coverage(self):
        counts = {module: 0 for module in _TARGET_MODULE_COUNTS}
        for operation in self._target_operations():
            counts[operation["source_module"]] += 1

        self.assertEqual(counts, _TARGET_MODULE_COUNTS)
        self.assertEqual(sum(counts.values()), 23)
        actual_operations = {
            module: {
                (operation["method"], operation["path"])
                for operation in self._target_operations()
                if operation["source_module"] == module
            }
            for module in _TARGET_MODULE_OPERATIONS
        }
        self.assertEqual(
            actual_operations,
            {module: set(operations) for module, operations in _TARGET_MODULE_OPERATIONS.items()},
        )

    def test_target_operations_have_no_untyped_200_schemas(self):
        untyped = [
            f"{operation['source_module']} {operation['method']} {operation['path']}"
            for operation in self._target_operations()
            if operation["response_200_schema"] == "untyped"
        ]
        self.assertEqual(untyped, [])

    def test_json_target_operations_have_response_models(self):
        missing_response_model = [
            f"{operation['source_module']} {operation['method']} {operation['path']}"
            for operation in self._target_operations()
            if operation["response_model"] == "none"
            and operation["path"] != "/api/v1/writing/export/markdown"
        ]
        self.assertEqual(missing_response_model, [])

    def test_markdown_export_keeps_explicit_non_json_schema(self):
        operations = {
            (operation["method"], operation["path"]): operation
            for operation in self._target_operations()
        }
        markdown_export = operations[("POST", "/api/v1/writing/export/markdown")]

        self.assertEqual(markdown_export["response_model"], "none")
        self.assertEqual(markdown_export["response_200_schema"], "non-json")


if __name__ == "__main__":
    unittest.main()
