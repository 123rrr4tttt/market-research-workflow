from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi import HTTPException
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode, map_exception_to_error, map_status_to_error_code
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ContractsErrorsCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"contracts error core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "contracts-errors-core"}

        cls.known_code_path = "/api/v1/test/contracts-errors/http-known-code"
        cls.unknown_code_path = "/api/v1/test/contracts-errors/http-unknown-code"
        cls.dict_detail_path = "/api/v1/test/contracts-errors/http-dict-detail"
        cls.none_detail_path = "/api/v1/test/contracts-errors/http-none-detail"

        if not cls._has_route(cls.known_code_path):
            def _raise_known_code() -> None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "error",
                        "data": None,
                        "error": {
                            "code": ErrorCode.RATE_LIMITED.value,
                            "message": "quota reached",
                            "details": {},
                        },
                        "meta": {},
                    },
                )

            backend_app.add_api_route(cls.known_code_path, _raise_known_code, methods=["GET"])

        if not cls._has_route(cls.unknown_code_path):
            def _raise_unknown_code() -> None:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "status": "error",
                        "data": None,
                        "error": {
                            "code": "NOT_A_REAL_ERROR_CODE",
                            "message": "upstream says throttled",
                            "details": {},
                        },
                        "meta": {},
                    },
                )

            backend_app.add_api_route(cls.unknown_code_path, _raise_unknown_code, methods=["GET"])

        if not cls._has_route(cls.dict_detail_path):
            def _raise_dict_detail() -> None:
                raise HTTPException(status_code=409, detail={"message": "conflict happened", "field": "topic"})

            backend_app.add_api_route(cls.dict_detail_path, _raise_dict_detail, methods=["GET"])

        if not cls._has_route(cls.none_detail_path):
            def _raise_none_detail() -> None:
                raise HTTPException(status_code=503, detail="")

            backend_app.add_api_route(cls.none_detail_path, _raise_none_detail, methods=["GET"])

    @staticmethod
    def _has_route(path: str) -> bool:
        return any(isinstance(route, APIRoute) and route.path == path for route in backend_app.routes)

    def test_map_status_to_error_code_core_matrix(self):
        cases = [
            (400, ErrorCode.INVALID_INPUT),
            (422, ErrorCode.INVALID_INPUT),
            (404, ErrorCode.NOT_FOUND),
            (429, ErrorCode.RATE_LIMITED),
            (502, ErrorCode.UPSTREAM_ERROR),
            (503, ErrorCode.UPSTREAM_ERROR),
            (504, ErrorCode.UPSTREAM_ERROR),
            (500, ErrorCode.INTERNAL_ERROR),
            (409, ErrorCode.INVALID_INPUT),
            (401, ErrorCode.INTERNAL_ERROR),
        ]
        for status_code, expected in cases:
            with self.subTest(status_code=status_code):
                self.assertEqual(map_status_to_error_code(status_code), expected)

    def test_map_exception_to_error_keyword_branches(self):
        cases = [
            (RuntimeError("resource not found"), ErrorCode.NOT_FOUND),
            (RuntimeError("429 rate limit exceeded"), ErrorCode.RATE_LIMITED),
            (RuntimeError("json parse failed"), ErrorCode.PARSE_ERROR),
            (RuntimeError("api key missing"), ErrorCode.CONFIG_ERROR),
            (RuntimeError("upstream timeout"), ErrorCode.UPSTREAM_ERROR),
        ]
        for exc, expected_code in cases:
            with self.subTest(message=str(exc)):
                code, message, details = map_exception_to_error(exc)
                self.assertEqual(code, expected_code)
                self.assertEqual(message, str(exc))
                self.assertIsNone(details)

    def test_map_exception_to_error_default_sets_exception_type(self):
        code, message, details = map_exception_to_error(ValueError("boom"))

        self.assertEqual(code, ErrorCode.INTERNAL_ERROR)
        self.assertEqual(message, "boom")
        self.assertEqual(details, {"exception_type": "ValueError"})

    def test_http_exception_envelope_prefers_known_error_code_from_detail(self):
        resp = self.client.get(self.known_code_path, headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.RATE_LIMITED.value)

        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.RATE_LIMITED.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.RATE_LIMITED.value)

    def test_http_exception_envelope_unknown_detail_code_falls_back_to_status_mapping(self):
        resp = self.client.get(self.unknown_code_path, headers=self.headers)

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.RATE_LIMITED.value)

        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "NOT_A_REAL_ERROR_CODE")
        self.assertEqual(body["detail"]["error"]["code"], "NOT_A_REAL_ERROR_CODE")

    def test_http_exception_dict_detail_is_wrapped_with_meta_and_details(self):
        resp = self.client.get(self.dict_detail_path, headers=self.headers)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["data"])
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["error"]["message"], "conflict happened")
        self.assertEqual(body["error"]["details"]["field"], "topic")
        self.assertEqual(body["meta"]["trace_id"], "contracts-errors-core")
        self.assertEqual(body["meta"]["project_key"], "demo_proj")
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)

    def test_http_exception_empty_detail_uses_default_message(self):
        resp = self.client.get(self.none_detail_path, headers=self.headers)

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(body["error"]["message"], "Request failed")


if __name__ == "__main__":
    unittest.main()
