from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_TARGET_MODULE_COUNTS = {
    "indexer.py": 1,
    "market.py": 2,
    "reports.py": 1,
    "search.py": 2,
    "writing.py": 18,
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
            if operation["source_module"] in _TARGET_MODULE_COUNTS
        ]

    def test_target_modules_have_expected_operation_coverage(self):
        counts = {module: 0 for module in _TARGET_MODULE_COUNTS}
        for operation in self._target_operations():
            counts[operation["source_module"]] += 1

        self.assertEqual(counts, _TARGET_MODULE_COUNTS)
        self.assertEqual(sum(counts.values()), 24)

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
