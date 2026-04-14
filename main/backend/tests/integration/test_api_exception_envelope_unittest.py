from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi import HTTPException
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiExceptionEnvelopeIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"exception envelope tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "exception-envelope-it"}
        cls.error_path = "/api/v1/test/exception-envelope"
        has_route = any(
            isinstance(route, APIRoute) and route.path == cls.error_path
            for route in backend_app.routes
        )
        if not has_route:
            def _raise_http_exception_for_test() -> None:
                raise HTTPException(status_code=400, detail="invalid input in test")

            backend_app.add_api_route(cls.error_path, _raise_http_exception_for_test, methods=["GET"])

    def test_http_exception_path_returns_envelope_with_legacy_detail_alias(self):
        resp = self.client.get(self.error_path, headers=self.headers)
        self.assertEqual(resp.status_code, 400)

        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["data"])
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)

    def test_http_exception_path_sets_x_error_code_header(self):
        resp = self.client.get(self.error_path, headers=self.headers)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_health_endpoint_remains_exempt_from_error_envelope(self):
        health_route = None
        for route in backend_app.routes:
            if isinstance(route, APIRoute) and route.path == "/api/v1/health":
                health_route = route
                break

        self.assertIsNotNone(health_route)

        def _raise_http_exception() -> None:
            raise HTTPException(status_code=503, detail="health unavailable")

        with patch.object(health_route.dependant, "call", _raise_http_exception):
            resp = self.client.get("/api/v1/health", headers=self.headers)

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {"detail": "health unavailable"})
        self.assertNotIn("error", resp.json())
        self.assertNotIn("meta", resp.json())
        self.assertIsNone(resp.headers.get("x-error-code"))


if __name__ == "__main__":
    unittest.main()
