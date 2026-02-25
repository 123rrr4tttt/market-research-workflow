from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from app.contracts.api import error_response, success_response
    from app.contracts.errors import ErrorCode
    from app.contracts.responses import fail, ok, ok_page
    from app.contracts.tasks import task_result_response
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_success_response_shape(self):
        payload = success_response({"hello": "world"}, meta={"trace_id": "t-1"})
        self.assertEqual(payload["status"], "ok")
        self.assertIn("data", payload)
        self.assertIn("error", payload)
        self.assertIn("meta", payload)
        self.assertEqual(payload["meta"]["trace_id"], "t-1")

    def test_error_response_shape(self):
        payload = error_response(ErrorCode.CONFIG_ERROR, "missing key")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.CONFIG_ERROR.value)

    def test_task_response_shape(self):
        payload = task_result_response(task_id="job-1", async_mode=True, params={"state": "CA"})
        self.assertTrue(payload["async"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["params"]["state"], "CA")

    def test_ok_envelope_helper_shape(self):
        payload = ok({"hello": "world"})
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["hello"], "world")
        self.assertIsNone(payload["error"])
        self.assertIn("meta", payload)

    def test_fail_envelope_helper_shape(self):
        payload = fail(ErrorCode.INVALID_INPUT, "bad request", details={"field": "topic"})
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(payload["error"]["details"]["field"], "topic")

    def test_ok_page_helper_shape(self):
        payload = ok_page({"items": [1, 2]}, page=2, page_size=10, total=25, total_pages=3)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["items"], [1, 2])
        self.assertEqual(payload["meta"]["pagination"]["page"], 2)
        self.assertEqual(payload["meta"]["pagination"]["total_pages"], 3)


if __name__ == "__main__":
    unittest.main()
