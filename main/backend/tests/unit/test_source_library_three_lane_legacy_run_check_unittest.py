from __future__ import annotations

import unittest

try:
    from scripts.check_source_library_three_lane_legacy_run_contract import check_contract

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SourceLibraryThreeLaneLegacyRunCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"source-library three-lane checker imports failed: {_IMPORT_ERROR}")

    def test_legacy_run_endpoint_returns_explicit_410_contract(self) -> None:
        report = check_contract()

        self.assertEqual(report["status"], "pass", report["failures"])
        response = report["legacy_response"]
        self.assertEqual(response["status_code"], 410)
        self.assertEqual(response["x_error_code"], "INVALID_INPUT")
        self.assertEqual(response["error_code"], "INVALID_INPUT")
        self.assertEqual(response["deprecated"], "source_library.legacy_item_run.v1")
        self.assertEqual(response["details"]["replacement_endpoint"], "/api/v1/ingest/source-library/run")
        self.assertEqual(response["details"]["legacy_status"], "410_gone")
        self.assertFalse(response["details"]["runs_source_library_item"])


if __name__ == "__main__":
    unittest.main()
