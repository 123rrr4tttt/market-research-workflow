#!/usr/bin/env python3
"""Focused tests for seven-line business user-flow smoke artifact behavior."""

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


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_business_line_user_flow_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_business_line_user_flow_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class BusinessLineUserFlowSmokeTestCase(unittest.TestCase):
    def make_output_path(self, name: str = "artifact.json") -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / name

    def matrix_payload(
        self,
        *,
        line_keys: list[str] | None = None,
        response_assertions_by_line: dict[str, list[str]] | None = None,
    ) -> dict[str, object]:
        keys = line_keys if line_keys is not None else list(smoke.EXPECTED_LINE_KEYS)
        response_assertions_by_line = response_assertions_by_line or {}
        lines = []
        for line_key in keys:
            live_smoke = {"probe_path": f"/api/v1/probe/{line_key}"}
            if line_key in response_assertions_by_line:
                live_smoke["response_assertions"] = {
                    "required_data_paths": response_assertions_by_line[line_key],
                }
            lines.append(
                {
                    "line_key": line_key,
                    "live_smoke": live_smoke,
                }
            )
        return {
            "status": "ok",
            "data": {
                "contract_version": "business_line.evidence_matrix.v1",
                "lines": lines,
            },
            "error": None,
            "meta": {},
        }

    def http_result(self, status_code: int, payload: object | None = None) -> object:
        body = json.dumps(payload if payload is not None else {"status": "ok"})
        return smoke.HttpResult(status_code=status_code, body=body)

    def feedback_submit_result(self) -> object:
        return self.http_result(
            200,
            {
                "status": "ok",
                "data": {
                    "submission_id": "sub-smoke",
                    "task_id": "task-smoke",
                    "status": "queued",
                    "trace_chain": {
                        "trace_id": "trace-smoke",
                        "ids": {"submission_id": "sub-smoke", "task_id": "task-smoke"},
                    },
                },
                "error": None,
                "meta": {},
            },
        )

    def feedback_history_result(self, *, include_readback: bool = True) -> object:
        items: list[dict[str, object]] = []
        if include_readback:
            items.append(
                {
                    "submission_id": "sub-smoke",
                    "task_id": "task-smoke",
                    "status": "queued",
                    "trace_chain": {
                        "trace_id": "trace-smoke",
                        "ids": {"submission_id": "sub-smoke", "task_id": "task-smoke"},
                    },
                }
            )
        return self.http_result(200, {"status": "ok", "data": items, "error": None, "meta": {}})

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with patch.object(smoke, "_http_post_json", return_value=self.feedback_submit_result()), contextlib.redirect_stdout(
            io.StringIO()
        ):
            exit_code = smoke.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def test_passed_when_matrix_and_all_line_probes_are_contract_reachable(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            if url.endswith("/ingest"):
                return self.http_result(302)
            if url.endswith("/runtime_ops"):
                return self.http_result(404)
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(smoke.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("passed", payload["status"])
        self.assertEqual(7, payload["summary"]["line_count"])
        self.assertEqual(0, payload["summary"]["blocked_count"])
        self.assertEqual(0, payload["summary"]["failed_count"])
        self.assertEqual(7, payload["summary"]["passed_contract_reachable_count"])
        self.assertEqual("passed", payload["summary"]["feedback_loop_status"])
        self.assertEqual("sub-smoke", payload["summary"]["submission_id"])
        self.assertEqual("task-smoke", payload["summary"]["task_id"])
        self.assertEqual("trace-smoke", payload["summary"]["trace_id"])
        self.assertIsNone(payload["summary"]["blocker_classification"])
        self.assertEqual("passed", payload["feedback_loop"]["status"])
        self.assertEqual(7, len(payload["lines"]))
        self.assertTrue(all(line["status"] == "passed_contract_reachable" for line in payload["lines"]))
        self.assertTrue(all(line["response_assertion_status"] == "not_declared" for line in payload["lines"]))
        self.assertTrue(all(line["missing_data_paths"] == [] for line in payload["lines"]))
        self.assertTrue(all(line["semantic_fields_checked"] == [] for line in payload["lines"]))
        self.assertEqual([], payload["matrix_anomalies"]["missing_line_keys"])

    def test_passed_when_declared_response_assertions_are_satisfied(self) -> None:
        output = self.make_output_path()
        required_paths = ["status", "data.items", "error", "meta/request_id"]
        assertions = {line_key: required_paths for line_key in smoke.EXPECTED_LINE_KEYS}

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload(response_assertions_by_line=assertions))
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            return self.http_result(
                200,
                {
                    "status": "ok",
                    "data": {"items": []},
                    "error": None,
                    "meta": {"request_id": "req-1"},
                },
            )

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertTrue(all(line["response_assertion_status"] == "passed" for line in payload["lines"]))
        self.assertTrue(all(line["missing_data_paths"] == [] for line in payload["lines"]))
        self.assertTrue(all(line["semantic_fields_checked"] == required_paths for line in payload["lines"]))

    def test_failed_when_declared_response_assertion_path_is_missing(self) -> None:
        output = self.make_output_path()
        assertions = {"ingest": ["status", "data.documents.total", "data.items"]}

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload(response_assertions_by_line=assertions))
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            if url.endswith("/ingest"):
                return self.http_result(
                    200,
                    {
                        "status": "ok",
                        "data": {"documents": {}, "items": []},
                        "error": None,
                        "meta": {},
                    },
                )
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = [line for line in payload["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("semantic_assertion_failed", ingest["reason"])
        self.assertEqual("failed", ingest["response_assertion_status"])
        self.assertEqual(["data.documents.total"], ingest["missing_data_paths"])
        self.assertEqual(["status", "data.documents.total", "data.items"], ingest["semantic_fields_checked"])

    def test_failed_when_any_line_probe_returns_5xx(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            if url.endswith("/runtime_ops"):
                return self.http_result(503)
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        runtime_ops = [line for line in payload["lines"] if line["line_key"] == "runtime_ops"][0]
        self.assertEqual("failed", runtime_ops["status"])
        self.assertEqual(503, runtime_ops["http_status"])

    def test_matrix_http_error_keeps_structured_summary(self) -> None:
        output = self.make_output_path()

        with patch.object(smoke, "_http_get", return_value=smoke.HttpResult(503, "service unavailable", "HTTP Error 503")):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual("evidence_matrix_http_error", payload["matrix"]["reason"])
        self.assertEqual("contract_or_semantic_failure", payload["summary"]["blocker_classification"])
        self.assertEqual("evidence_matrix_http_error", payload["summary"]["first_blocker_reason"])
        self.assertEqual(["http://127.0.0.1:8000/api/v1/business-lines/evidence-matrix"], payload["summary"]["checked_endpoints"])

    def test_blocked_without_allow_blocked_exits_nonzero_and_lists_recommended_command(self) -> None:
        output = self.make_output_path()

        with patch.object(smoke, "_http_get", return_value=smoke.HttpResult(None, "", "connection refused")):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("evidence_matrix_unreachable", payload["summary"]["blocker_classification"])
        self.assertEqual("ingest", payload["summary"]["first_blocked_line"])
        self.assertEqual("evidence_matrix_unreachable", payload["summary"]["first_blocker_reason"])
        self.assertEqual(["http://127.0.0.1:8000/api/v1/business-lines/evidence-matrix"], payload["summary"]["checked_endpoints"])
        self.assertEqual("evidence_matrix_unreachable", payload["matrix"]["reason"])
        self.assertEqual(7, len(payload["lines"]))
        self.assertTrue(all(line["status"] == "blocked_by_environment" for line in payload["lines"]))
        self.assertTrue(all(line["response_assertion_status"] == "not_run" for line in payload["lines"]))
        self.assertTrue(all(line["missing_data_paths"] == [] for line in payload["lines"]))
        self.assertTrue(all(line["semantic_fields_checked"] == [] for line in payload["lines"]))
        self.assertEqual([], payload["matrix_anomalies"]["missing_line_keys"])
        self.assertIn("python3 scripts/run_business_line_user_flow_smoke.py", payload["recommended_command"])
        self.assertIn("--base-url http://127.0.0.1:8000", payload["recommended_command"])

    def test_blocked_with_allow_blocked_exits_zero(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(
                    200,
                    self.matrix_payload(response_assertions_by_line={"runtime_ops": ["status", "data.items"]}),
                )
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            if url.endswith("/runtime_ops"):
                return smoke.HttpResult(None, "", "timed out")
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("line_probe_blocked", payload["summary"]["blocker_classification"])
        self.assertEqual("runtime_ops", payload["summary"]["first_blocked_line"])
        self.assertEqual(1, payload["summary"]["blocked_count"])
        runtime_ops = [line for line in payload["lines"] if line["line_key"] == "runtime_ops"][0]
        self.assertEqual("blocked_by_environment", runtime_ops["status"])
        self.assertEqual("not_run", runtime_ops["response_assertion_status"])
        self.assertEqual([], runtime_ops["missing_data_paths"])
        self.assertEqual(["status", "data.items"], runtime_ops["semantic_fields_checked"])

    def test_base_url_alias_matches_batch_gate_command(self) -> None:
        output = self.make_output_path()

        with patch.object(smoke, "_http_get", return_value=smoke.HttpResult(None, "", "connection refused")):
            exit_code, payload = self.run_main(
                [
                    "--base-url",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("http://127.0.0.1:8000", payload["api_base"])

    def test_matrix_missing_line_fails_contract(self) -> None:
        output = self.make_output_path()
        line_keys = [line_key for line_key in smoke.EXPECTED_LINE_KEYS if line_key != "runtime_ops"]

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload(line_keys=line_keys))
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertIn("runtime_ops", payload["matrix_anomalies"]["missing_line_keys"])
        runtime_ops = [line for line in payload["lines"] if line["line_key"] == "runtime_ops"][0]
        self.assertEqual("missing_line_in_evidence_matrix", runtime_ops["reason"])

    def test_matrix_unexpected_line_key_fails_contract(self) -> None:
        output = self.make_output_path()
        line_keys = list(smoke.EXPECTED_LINE_KEYS)
        line_keys[0] = "bad_line_key"

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload(line_keys=line_keys))
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result()
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertIn("bad_line_key", payload["matrix_anomalies"]["unexpected_line_keys"])
        self.assertIn("ingest", payload["matrix_anomalies"]["missing_line_keys"])

    def test_feedback_readback_missing_prevents_passed_status(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(smoke.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            if smoke.FEEDBACK_HISTORY_PATH in url:
                return self.feedback_history_result(include_readback=False)
            return self.http_result(200)

        with patch.object(smoke, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("feedback_readback_missing", payload["status"])
        self.assertEqual("feedback_readback_missing", payload["summary"]["blocker_classification"])
        self.assertEqual("feedback_readback_missing", payload["feedback_loop"]["status"])
        self.assertIn("feedback_history_missing_submission", payload["feedback_loop"]["failures"])
        self.assertEqual("sub-smoke", payload["feedback_loop"]["submission_id"])
        self.assertEqual("task-smoke", payload["feedback_loop"]["task_id"])
        self.assertEqual("trace-smoke", payload["feedback_loop"]["trace_id"])


if __name__ == "__main__":
    unittest.main()
