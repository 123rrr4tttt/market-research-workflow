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


class ApiSchemaIngestResourceContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api schema ingest/resource tests require backend dependencies: {_IMPORT_ERROR}")

    def test_ingest_and_resource_pool_200_schemas_are_enveloped(self):
        operations = build_inventory(backend_app)["operations"]
        by_module = {
            module: [operation for operation in operations if operation["source_module"] == module]
            for module in ("ingest.py", "resource_pool.py")
        }

        self.assertEqual(len(by_module["ingest.py"]), 19)
        self.assertEqual(len(by_module["resource_pool.py"]), 19)
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
