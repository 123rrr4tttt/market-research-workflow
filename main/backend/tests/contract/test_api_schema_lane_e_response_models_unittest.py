from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_TARGET_MODULE_COUNTS = {
    "config.py": 4,
    "crawler.py": 8,
    "keywords.py": 5,
    "llm_config.py": 14,
    "stats.py": 4,
}

try:
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaLaneEResponseModelsContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"lane E schema response model tests require backend dependencies: {_IMPORT_ERROR}")

    def _target_operations(self) -> list[dict]:
        inventory = build_inventory(backend_app)
        return [
            operation
            for operation in inventory["operations"]
            if operation["source_module"] in _TARGET_MODULE_COUNTS
        ]

    def test_lane_e_target_modules_have_expected_operation_coverage(self):
        operations = self._target_operations()
        counts = {module: 0 for module in _TARGET_MODULE_COUNTS}
        for operation in operations:
            counts[operation["source_module"]] += 1

        self.assertEqual(counts, _TARGET_MODULE_COUNTS)
        self.assertEqual(sum(counts.values()), 35)

    def test_lane_e_target_operations_have_typed_200_response_schemas(self):
        untyped = [
            f"{operation['method']} {operation['path']}"
            for operation in self._target_operations()
            if operation["response_200_schema"] == "untyped"
        ]
        missing_response_model = [
            f"{operation['method']} {operation['path']}"
            for operation in self._target_operations()
            if operation["response_model"] == "none"
        ]

        self.assertEqual(untyped, [])
        self.assertEqual(missing_response_model, [])


if __name__ == "__main__":
    unittest.main()
