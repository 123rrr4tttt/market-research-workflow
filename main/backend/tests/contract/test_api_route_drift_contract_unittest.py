from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _route_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for route in backend_app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method not in {"HEAD", "OPTIONS"}:
                keys.add((method, route.path))
    return keys


class ApiRouteDriftContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api route drift contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_project_customization_uses_hyphenated_public_prefix(self):
        keys = _route_keys()
        self.assertIn(("GET", "/api/v1/project-customization/menu"), keys)
        self.assertIn(("POST", "/api/v1/project-customization/workflows/{workflow_name}/run"), keys)
        self.assertFalse(
            any(path.startswith("/api/v1/project_customization") for _, path in keys),
            msg="The public project customization prefix is hyphenated.",
        )

    def test_source_library_run_uses_ingest_frontdoor_only(self):
        keys = _route_keys()
        self.assertIn(("POST", "/api/v1/ingest/source-library/run"), keys)
        self.assertNotIn(("POST", "/api/v1/source_library/items/{item_key}/run"), keys)

    def test_recent_backend_core_routes_remain_in_public_surface(self):
        keys = _route_keys()
        self.assertIn(("POST", "/api/v1/ingest/graph/structured-search"), keys)
        self.assertIn(("POST", "/api/v1/projects/auto-create"), keys)


if __name__ == "__main__":
    unittest.main()
