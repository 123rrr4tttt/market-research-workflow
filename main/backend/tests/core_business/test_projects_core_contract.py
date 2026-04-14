from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ProjectsCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"projects core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "projects-core-contract"}

    @staticmethod
    def _session_local_with_result(result: Mock) -> Mock:
        session = Mock()
        session.execute.return_value = result
        session_cm = Mock()
        session_cm.__enter__ = Mock(return_value=session)
        session_cm.__exit__ = Mock(return_value=None)
        return Mock(return_value=session_cm)

    def test_list_projects_returns_enveloped_items(self):
        rows = [
            SimpleNamespace(
                id=1,
                project_key="demo_proj",
                name="Demo",
                schema_name="tenant_demo_proj",
                enabled=True,
                is_active=True,
            ),
            SimpleNamespace(
                id=2,
                project_key="alpha_proj",
                name="Alpha",
                schema_name="tenant_alpha_proj",
                enabled=True,
                is_active=False,
            ),
        ]
        result = Mock()
        result.scalars.return_value.all.return_value = rows

        with (
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", self._session_local_with_result(result)),
        ):
            response = self.client.get("/api/v1/projects", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(len(payload["data"]["items"]), 2)
        self.assertEqual(payload["data"]["items"][0]["project_key"], "demo_proj")
        self.assertEqual(payload["data"]["items"][1]["project_key"], "alpha_proj")

    def test_project_detail_path_not_found_maps_to_not_found_error_code(self):
        result = Mock()
        result.scalar_one_or_none.return_value = None

        with (
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", self._session_local_with_result(result)),
        ):
            response = self.client.post("/api/v1/projects/missing_proj/activate", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_invalid_parameter_maps_to_invalid_input_error_code(self):
        response = self.client.post(
            "/api/v1/projects/inject-initial",
            headers=self.headers,
            json={"source_project_key": "   "},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)


if __name__ == "__main__":
    unittest.main()
