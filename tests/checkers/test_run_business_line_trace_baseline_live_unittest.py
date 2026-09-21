#!/usr/bin/env python3
"""Focused tests for live business-line trace baseline artifacts."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_business_line_trace_baseline_live.py"
SPEC = importlib.util.spec_from_file_location("run_business_line_trace_baseline_live", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
trace_live = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = trace_live
SPEC.loader.exec_module(trace_live)


class BusinessLineTraceBaselineLiveTestCase(unittest.TestCase):
    def make_output_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "trace-baseline.json"

    def matrix_payload(self) -> dict[str, object]:
        return {
            "status": "ok",
            "data": {
                "lines": [
                    {
                        "line_key": line_key,
                        "live_smoke": {
                            "probe_path": f"/api/v1/probe/{line_key}",
                            "expected_statuses": [200],
                            "response_assertions": {
                                "required_data_paths": ["status", "data.items", "error", "meta"],
                            },
                        },
                    }
                    for line_key in trace_live.EXPECTED_LINE_KEYS
                ],
            },
            "error": None,
            "meta": {"trace_id": "trace-test-matrix"},
        }

    def http_result(self, trace_id: str, payload: object, *, duration_ms: float = 10.0) -> object:
        return trace_live.HttpResult(
            status_code=200,
            body=json.dumps(payload),
            headers={"x-trace-id": trace_id, "x-request-id": trace_id},
            duration_ms=duration_ms,
        )

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = trace_live.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def test_passed_when_every_line_preserves_trace_and_required_paths(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float, trace_id: str) -> object:
            if url.endswith(trace_live.MATRIX_PATH):
                return self.http_result(trace_id, self.matrix_payload())
            return self.http_result(
                trace_id,
                {"status": "ok", "data": {"items": []}, "error": None, "meta": {"trace_id": trace_id}},
            )

        with patch.object(trace_live, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--base-url",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--trace-prefix",
                    "trace-test",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(7, payload["summary"]["passed_count"])
        self.assertEqual(0, payload["summary"]["failed_count"])
        self.assertTrue(all(line["body_meta_trace_status"] == "passed" for line in payload["lines"]))

    def test_missing_body_meta_trace_fails_contract_endpoint(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float, trace_id: str) -> object:
            if url.endswith(trace_live.MATRIX_PATH):
                return self.http_result(trace_id, self.matrix_payload())
            return self.http_result(
                trace_id,
                {"status": "ok", "data": {"items": []}, "error": None, "meta": {"trace_id": None}},
            )

        with patch.object(trace_live, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--base-url",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--trace-prefix",
                    "trace-test",
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertIn("body_meta_trace_id", payload["summary"]["first_failure"])

    def test_non_envelope_health_style_payload_uses_header_trace_only(self) -> None:
        status, trace_id = trace_live.body_meta_trace_status({"status": "ok"}, "trace-1")

        self.assertEqual("not_applicable", status)
        self.assertIsNone(trace_id)


if __name__ == "__main__":
    unittest.main()
