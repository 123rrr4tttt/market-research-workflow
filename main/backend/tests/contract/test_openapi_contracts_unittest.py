from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract


class OpenApiContractsTestCase(unittest.TestCase):
    def _build_app(self):
        try:
            from fastapi import FastAPI
            from app.api.policies import router as policies_router
            from app.api.discovery import router as discovery_router
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import routers for OpenAPI contract test: {exc}")
        app = FastAPI()
        app.include_router(policies_router, prefix="/api/v1")
        app.include_router(discovery_router, prefix="/api/v1")
        return app

    def test_openapi_contains_policy_contracts(self):
        schema = self._build_app().openapi()
        self.assertIn("/api/v1/policies", schema["paths"])
        self.assertIn("/api/v1/policies/stats", schema["paths"])
        self.assertIn("/api/v1/policies/state/{state}", schema["paths"])
        self.assertIn("/api/v1/policies/{policy_id}", schema["paths"])

        resp_schema = (
            schema["paths"]["/api/v1/policies"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        )
        self.assertIn("$ref", resp_schema)
        self.assertIn("ApiEnvelope", resp_schema["$ref"])

        components = schema.get("components", {}).get("schemas", {})
        self.assertIn("ApiErrorModel", components)
        self.assertIn("PaginationMetaModel", components)
        self.assertIn("PolicySummary", components)

    def test_openapi_discovery_error_statuses_present(self):
        schema = self._build_app().openapi()
        search_post = schema["paths"]["/api/v1/discovery/search"]["post"]["responses"]
        # Snapshot-like assertions on critical status codes for route C first phase.
        self.assertIn("200", search_post)
        self.assertIn("400", search_post)
        self.assertIn("404", search_post)
        self.assertIn("429", search_post)
        self.assertIn("500", search_post)
        self.assertIn("502", search_post)
        self.assertIn("422", search_post)  # FastAPI validation


if __name__ == "__main__":
    unittest.main()
