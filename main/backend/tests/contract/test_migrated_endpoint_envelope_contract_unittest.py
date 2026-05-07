from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract


class MigratedEndpointEnvelopeContractTestCase(unittest.TestCase):
    def _build_app(self):
        try:
            from fastapi import FastAPI
            from app.api.config import router as config_router
            from app.api.llm_config import router as llm_config_router
            from app.api.projects import router as projects_router
            from app.api.reports import router as reports_router
            from app.api.search import router as search_router
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import routers for contract test: {exc}")
        app = FastAPI()
        app.include_router(config_router, prefix="/api/v1")
        app.include_router(llm_config_router, prefix="/api/v1")
        app.include_router(search_router, prefix="/api/v1")
        app.include_router(projects_router, prefix="/api/v1")
        app.include_router(reports_router, prefix="/api/v1")
        return app

    def test_search_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        client = TestClient(self._build_app())
        mocked_results = [{"id": "doc-1", "score": 0.99}]
        with patch("app.api.search.hybrid_search", return_value=mocked_results):
            response = client.get(
                "/api/v1/search",
                params={"q": "market", "state": "CA", "rank": "hybrid", "top_k": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["data"]["results"], mocked_results)
        self.assertEqual(payload["data"]["query"], "market")
        self.assertEqual(payload["data"]["top_k"], 1)

    def test_projects_auto_create_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        client = TestClient(self._build_app())

        def _project_exists_side_effect(project_key: str) -> bool:
            return project_key == "demo_proj"

        created_stub = {
            "project_key": "new_proj",
            "name": "New Project",
            "schema_name": "tenant_new_proj",
            "activated": True,
            "copied_counts": {},
        }

        with (
            patch("app.api.projects._project_exists", side_effect=_project_exists_side_effect),
            patch("app.api.projects.inject_initial_project", return_value=created_stub),
            patch("app.api.projects._apply_llm_configs_to_project", return_value=0),
        ):
            response = client.post(
                "/api/v1/projects/auto-create",
                json={
                    "project_name": "New Project",
                    "project_key": "new_proj",
                    "template_project_key": "demo_proj",
                    "activate": True,
                    "copy_initial_data": True,
                    "llm_configs": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertIsInstance(payload["data"], dict)
        self.assertEqual(payload["data"]["created_mode"], "inject_initial")
        self.assertEqual(payload["data"]["template_project_key"], "demo_proj")
        self.assertEqual(payload["data"]["llm_configs_applied"], 0)

    def test_reports_html_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.reports.generate_html_report", return_value="<html>report</html>"):
            response = client.post(
                "/api/v1/reports",
                json={"states": ["CA"], "start": "2026-01-01", "end": "2026-01-31", "format": "html"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["data"]["format"], "html")
        self.assertEqual(payload["data"]["data"], "<html>report</html>")

    def test_reports_csv_success_returns_download_response(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.reports.generate_csv_report", return_value=b"col1,col2\n1,2\n"):
            response = client.post(
                "/api/v1/reports",
                json={"states": ["CA"], "start": "2026-01-01", "end": "2026-01-31", "format": "csv"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("attachment; filename=lottery_report.csv", response.headers.get("content-disposition", ""))
        self.assertEqual(response.text, "col1,col2\n1,2\n")

    def test_reports_unsupported_format_returns_structured_invalid_input_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        response = client.post(
            "/api/v1/reports",
            json={"states": ["CA"], "start": "2026-01-01", "end": "2026-01-31", "format": "pdf"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("暂不支持的格式", payload["detail"]["error"]["message"])

    def test_reports_value_error_returns_structured_invalid_input_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.reports.generate_html_report", side_effect=ValueError("invalid date range")):
            response = client.post(
                "/api/v1/reports",
                json={"states": ["CA"], "start": "2026-02-01", "end": "2026-01-01", "format": "html"},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("invalid date range", payload["detail"]["error"]["message"])

    def test_search_upstream_error_returns_structured_upstream_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.search.hybrid_search", side_effect=RuntimeError("Elasticsearch Connection refused")):
            response = client.get("/api/v1/search", params={"q": "market"})

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)

    def test_config_env_invalid_payload_returns_structured_invalid_input_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        response = client.post("/api/v1/config/env", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)


if __name__ == "__main__":
    unittest.main()
