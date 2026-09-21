#!/usr/bin/env python3
"""Focused tests for business-line trace baseline artifact checks."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_trace_baseline_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_business_line_trace_baseline_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessLineTraceBaselineArtifactTestCase(unittest.TestCase):
    def make_artifact_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "trace-baseline.json"

    def write_artifact(self, payload: object) -> Path:
        path = self.make_artifact_path()
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def line(
        self,
        line_key: str,
        *,
        probe_path: str | None = None,
        body_meta_trace_status: str = checker.STATUS_PASSED,
    ) -> dict[str, object]:
        trace_id = f"trace-{line_key}"
        return {
            "line_key": line_key,
            "status": checker.STATUS_PASSED,
            "probe_path": probe_path or f"/api/v1/probe/{line_key}",
            "trace_id": trace_id,
            "header_trace_id": trace_id,
            "header_request_id": trace_id,
            "body_meta_trace_status": body_meta_trace_status,
            "required_data_paths": ["status", "data", "error", "meta"],
            "missing_data_paths": [],
            "duration_ms": 12.5,
            "failures": [],
        }

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": checker.STATUS_PASSED,
            "matrix": {
                "status": checker.STATUS_PASSED,
                "trace_id": "trace-matrix",
                "header_trace_id": "trace-matrix",
                "body_meta_trace_status": checker.STATUS_PASSED,
                "failures": [],
            },
            "lines": [self.line(line_key) for line_key in checker.REQUIRED_LINE_KEYS],
        }

    def test_passed_artifact_with_all_seven_lines_passes(self) -> None:
        artifact = self.write_artifact(self.payload())

        report = checker.build_report(artifact)

        self.assertEqual(checker.CHECK_SCHEMA_VERSION, report["schema_version"])
        self.assertEqual(checker.STATUS_PASSED, report["status"])
        self.assertEqual(sorted(checker.REQUIRED_LINE_KEYS), report["checked_line_keys"])
        self.assertEqual([], report["failures"])
        self.assertEqual(7, report["summary"]["checked_line_count"])

    def test_main_supports_input_and_json_output(self) -> None:
        artifact = self.write_artifact(self.payload())
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = checker.main(["--input", str(artifact)])

        self.assertEqual(0, exit_code)
        output = json.loads(stdout.getvalue())
        self.assertEqual(checker.STATUS_PASSED, output["status"])
        self.assertEqual(sorted(checker.REQUIRED_LINE_KEYS), output["checked_line_keys"])

    def test_missing_line_fails(self) -> None:
        payload = self.payload()
        payload["lines"] = [
            line for line in payload["lines"] if line["line_key"] != "runtime_ops"  # type: ignore[index]
        ]
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertIn({"reason": "missing_line_keys", "detail": ["runtime_ops"]}, report["failures"])

    def test_probe_header_trace_mismatch_fails(self) -> None:
        payload = self.payload()
        payload["lines"][0]["header_trace_id"] = "wrong-trace"  # type: ignore[index]
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertTrue(
            any(
                item["reason"] == "header_trace_id" and item.get("line_key") == "ingest"
                for item in report["failures"]
            )
        )

    def test_body_meta_not_applicable_requires_exempt_probe_path(self) -> None:
        payload = self.payload()
        payload["lines"][0]["body_meta_trace_status"] = checker.TRACE_NOT_APPLICABLE  # type: ignore[index]
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertTrue(
            any(
                item["reason"] == "body_meta_trace_not_applicable_for_non_exempt_path"
                and item.get("line_key") == "ingest"
                for item in report["failures"]
            )
        )

    def test_body_meta_not_applicable_allowed_for_health_probe(self) -> None:
        payload = self.payload()
        payload["lines"][-1] = self.line(
            "runtime_ops",
            probe_path="/api/v1/health/deep",
            body_meta_trace_status=checker.TRACE_NOT_APPLICABLE,
        )
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_PASSED, report["status"])

    def test_missing_required_data_path_fails(self) -> None:
        payload = self.payload()
        payload["lines"][0]["missing_data_paths"] = ["data.items"]  # type: ignore[index]
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertTrue(
            any(
                item["reason"] == "required_data_paths" and item.get("line_key") == "ingest"
                for item in report["failures"]
            )
        )

    def test_missing_duration_fails(self) -> None:
        payload = self.payload()
        del payload["lines"][0]["duration_ms"]  # type: ignore[index]
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertTrue(
            any(item["reason"] == "duration_ms" and item.get("line_key") == "ingest" for item in report["failures"])
        )

    def test_matrix_trace_mismatch_fails(self) -> None:
        payload = self.payload()
        payload["matrix"]["header_trace_id"] = "wrong-trace"  # type: ignore[index]
        artifact = self.write_artifact(payload)

        report = checker.build_report(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertTrue(any(item["reason"] == "matrix_header_trace_id" for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
