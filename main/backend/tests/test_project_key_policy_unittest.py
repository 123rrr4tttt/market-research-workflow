from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    from app.contracts.errors import ErrorCode
    from app.api import ingest as ingest_api
    from app.api import source_library as source_library_api
    from app.main import app as backend_app
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ProjectKeyPolicyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"project key policy tests require backend dependencies: {_IMPORT_ERROR}")

    def test_error_code_contains_project_key_required(self):
        self.assertEqual(ErrorCode.PROJECT_KEY_REQUIRED.value, "PROJECT_KEY_REQUIRED")

    def test_ingest_require_project_key_uses_explicit_value(self):
        value = ingest_api._require_project_key("demo_proj")
        self.assertEqual(value, "demo_proj")

    def test_ingest_require_project_key_fallback_logs_warning(self):
        with patch("app.api.ingest.current_project_key", return_value="demo_proj"):
            with self.assertLogs("app.api.ingest", level="WARNING") as cm:
                value = ingest_api._require_project_key(None)
        self.assertEqual(value, "demo_proj")
        self.assertTrue(any("project_key_fallback_used" in msg for msg in cm.output))

    def test_ingest_require_project_key_missing_raises_structured_error(self):
        with patch("app.api.ingest.current_project_key", return_value=""):
            with self.assertRaises(HTTPException) as ctx:
                ingest_api._require_project_key(None)
        detail = ctx.exception.detail
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail["status"], "error")
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_ingest_require_project_key_in_require_mode_rejects_fallback(self):
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            with patch("app.api.ingest.current_project_key", return_value="demo_proj"):
                with self.assertRaises(HTTPException) as ctx:
                    ingest_api._require_project_key(None)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_require_project_key_fallback_logs_warning(self):
        with patch("app.api.source_library.current_project_key", return_value="demo_proj"):
            with self.assertLogs("app.api.source_library", level="WARNING") as cm:
                value = source_library_api._require_project_key(None)
        self.assertEqual(value, "demo_proj")
        self.assertTrue(any("project_key_fallback_used" in msg for msg in cm.output))

    def test_middleware_sets_project_context_headers(self):
        client = TestClient(backend_app)
        resp = client.get("/api/v1/health", headers={"X-Project-Key": "demo_proj", "X-Request-Id": "req-1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-request-id"), "req-1")
        self.assertEqual(resp.headers.get("x-project-key-source"), "header")
        self.assertEqual(resp.headers.get("x-project-key-resolved"), "demo_proj")


if __name__ == "__main__":
    unittest.main()
