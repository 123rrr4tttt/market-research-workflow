from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.contracts.errors import ErrorCode, map_exception_to_error, map_status_to_error_code

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ContractsErrorsUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"contracts errors unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_map_status_to_error_code_matrix(self):
        pairs = [
            (400, ErrorCode.INVALID_INPUT),
            (422, ErrorCode.INVALID_INPUT),
            (404, ErrorCode.NOT_FOUND),
            (429, ErrorCode.RATE_LIMITED),
            (502, ErrorCode.UPSTREAM_ERROR),
            (503, ErrorCode.UPSTREAM_ERROR),
            (504, ErrorCode.UPSTREAM_ERROR),
            (500, ErrorCode.INTERNAL_ERROR),
            (409, ErrorCode.INVALID_INPUT),
            (418, ErrorCode.INTERNAL_ERROR),
        ]
        for status_code, expected in pairs:
            with self.subTest(status_code=status_code):
                self.assertEqual(map_status_to_error_code(status_code), expected)

    def test_map_exception_to_error_matrix(self):
        pairs = [
            (Exception("item not found"), ErrorCode.NOT_FOUND, None),
            (Exception("请求不存在"), ErrorCode.NOT_FOUND, None),
            (Exception("rate limit reached"), ErrorCode.RATE_LIMITED, None),
            (Exception("HTTP 429"), ErrorCode.RATE_LIMITED, None),
            (Exception("触发限流"), ErrorCode.RATE_LIMITED, None),
            (Exception("json parse failed"), ErrorCode.PARSE_ERROR, None),
            (Exception("解析失败"), ErrorCode.PARSE_ERROR, None),
            (Exception("missing api key"), ErrorCode.CONFIG_ERROR, None),
            (Exception("配置缺失"), ErrorCode.CONFIG_ERROR, None),
            (Exception("upstream timeout"), ErrorCode.UPSTREAM_ERROR, None),
            (Exception("HTTP error"), ErrorCode.UPSTREAM_ERROR, None),
        ]
        for exc, expected_code, expected_details in pairs:
            with self.subTest(message=str(exc)):
                code, msg, details = map_exception_to_error(exc)
                self.assertEqual(code, expected_code)
                self.assertIn(str(exc), msg)
                self.assertEqual(details, expected_details)

    def test_map_exception_to_error_default_branch(self):
        code, msg, details = map_exception_to_error(Exception("unexpected failure"))
        self.assertEqual(code, ErrorCode.INTERNAL_ERROR)
        self.assertIn("unexpected failure", msg)
        self.assertEqual(details, {"exception_type": "Exception"})

    def test_map_exception_to_error_empty_message_uses_class_name(self):
        code, msg, details = map_exception_to_error(Exception(""))
        self.assertEqual(code, ErrorCode.INTERNAL_ERROR)
        self.assertEqual(msg, "Exception")
        self.assertEqual(details, {"exception_type": "Exception"})


if __name__ == "__main__":
    unittest.main()
