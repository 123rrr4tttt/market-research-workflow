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


class AdminDashboardSchemaContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"admin/dashboard schema contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_admin_and_dashboard_legacy_dict_endpoints_have_openapi_200_schema(self):
        inventory = build_inventory(backend_app)
        by_source = {row["source_module"]: row for row in inventory["source_summary"]}

        for source_module in ("admin.py", "dashboard.py"):
            row = by_source[source_module]
            self.assertEqual(row["untyped_200"], 0, msg=row)
            self.assertEqual(row["response_models"], row["operations"], msg=row)

    def test_admin_and_dashboard_success_responses_keep_envelope_schema(self):
        operations = {
            (operation["method"], operation["path"]): operation
            for operation in build_inventory(backend_app)["operations"]
        }

        for key in (
            ("GET", "/api/v1/admin/stats"),
            ("GET", "/api/v1/admin/content-graph"),
            ("GET", "/api/v1/dashboard/stats"),
            ("GET", "/api/v1/dashboard/ecom-price-trends"),
        ):
            operation = operations[key]
            self.assertIn("ApiEnvelope", operation["response_model"], msg=operation)
            self.assertNotEqual(operation["response_200_schema"], "untyped", msg=operation)


if __name__ == "__main__":
    unittest.main()
