#!/usr/bin/env python3
"""Focused tests for business-line worker project schema preflight."""

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


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_worker_project_schema_preflight.py"
SPEC = importlib.util.spec_from_file_location("check_business_line_worker_project_schema_preflight", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)


class BusinessLineWorkerProjectSchemaPreflightTestCase(unittest.TestCase):
    def make_output_path(self) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        return Path(tmp_dir.name) / "preflight.json"

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = preflight.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def result(self, status_code: int | None, payload: object, error: str = "") -> object:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return preflight.HttpResult(status_code, text, error)

    def base_argv(self, output: Path, *extra: str) -> list[str]:
        return [
            "--api-base",
            "http://127.0.0.1:8000",
            "--project-key",
            "demo_proj",
            "--output",
            str(output),
            *extra,
        ]

    def test_backend_unreachable_writes_blocked_and_allow_blocked_exits_zero(self) -> None:
        output = self.make_output_path()
        with patch.object(
            preflight,
            "_http_get",
            return_value=preflight.HttpResult(None, "", "connection refused"),
        ):
            exit_code, payload = self.run_main(self.base_argv(output, "--timeout", "1", "--allow-blocked", "--json"))

        self.assertEqual(0, exit_code)
        self.assertEqual(preflight.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("demo_proj", payload["project_key"])
        self.assertEqual(["backend_health"], [item["name"] for item in payload["checked_endpoints"]])
        self.assertEqual("backend_unreachable", payload["checked_endpoints"][0]["reason"])
        self.assertIn("--project-key demo_proj", payload["recommended_next_commands"][1])

    def test_process_tasks_and_logs_200_pass(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float, project_key: str) -> object:
            self.assertEqual("demo_proj", project_key)
            if url.endswith("/api/v1/health"):
                return self.result(200, {"status": "ok"})
            self.assertIn("project_key=demo_proj", url)
            return self.result(200, {"status": "ok", "data": {"items": []}})

        with patch.object(preflight, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(self.base_argv(output, "--json"))

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(["backend_health", "process_tasks", "process_logs"], [item["name"] for item in payload["checked_endpoints"]])
        self.assertTrue(all(item["status"] == "passed" for item in payload["checked_endpoints"]))
        self.assertEqual(3, payload["summary"]["passed_count"])

    def test_process_5xx_or_schema_missing_marker_fails_not_passed(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float, project_key: str) -> object:
            if url.endswith("/api/v1/health"):
                return self.result(200, {"status": "ok"})
            if "/api/v1/process/tasks" in url:
                return self.result(
                    500,
                    {
                        "status": "error",
                        "error": 'sqlalchemy.exc.ProgrammingError: relation "sources" does not exist',
                    },
                )
            return self.result(200, {"status": "ok", "data": {"items": []}})

        with patch.object(preflight, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(self.base_argv(output, "--allow-blocked", "--json"))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual(["process_tasks"], payload["summary"]["failed_endpoints"])
        tasks_endpoint = next(item for item in payload["checked_endpoints"] if item["name"] == "process_tasks")
        self.assertEqual("failed", tasks_endpoint["status"])
        self.assertEqual("schema_missing_marker", tasks_endpoint["reason"])
        self.assertTrue(tasks_endpoint["schema_missing_marker"])


if __name__ == "__main__":
    unittest.main()
