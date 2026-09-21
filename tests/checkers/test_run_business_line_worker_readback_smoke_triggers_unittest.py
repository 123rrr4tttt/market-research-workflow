#!/usr/bin/env python3
"""Focused tests for worker-required smoke trigger helper."""

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


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_business_line_worker_readback_smoke_triggers.py"
SPEC = importlib.util.spec_from_file_location("run_business_line_worker_readback_smoke_triggers", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class BusinessLineWorkerReadbackSmokeTriggersTestCase(unittest.TestCase):
    def make_output_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "worker-readback-smoke-triggers.json"

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = runner.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def http_result(self, payload: object, status_code: int = 200) -> object:
        return runner.HttpResult(status_code=status_code, body=json.dumps(payload))

    def agent_batch_payload(self, *, job_id: str, task_id: str, run_id: str, channel: str) -> dict[str, object]:
        return {
            "status": "success",
            "data": {
                "job_id": job_id,
                "status": "accepted",
                "accepted_count": 1,
                "rejected_count": 0,
                "accepted_job_items": [
                    {
                        "item_id": f"item-{channel}",
                        "task_id": task_id,
                        "run_id": run_id,
                        "workflow_run_id": run_id,
                        "channel": channel,
                    }
                ],
                "run_ids": [run_id],
            },
            "error": None,
        }

    def test_backend_unreachable_writes_blocked_by_environment_artifact(self) -> None:
        output = self.make_output_path()
        with patch.object(runner, "_http_post_json", return_value=runner.HttpResult(None, "", "connection refused")):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                    "--timeout",
                    "1",
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual(runner.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual(4, payload["summary"]["blocked"])
        self.assertEqual(list(runner.WORKER_REQUIRED_LINE_KEYS), payload["scope"]["worker_required_line_keys"])
        self.assertEqual(list(runner.WORKER_REQUIRED_LINE_KEYS), payload["summary"]["blocked_line_keys"])
        self.assertEqual([], payload["summary"]["accepted_line_keys"])
        for line in payload["lines"]:
            self.assertFalse(line["accepted"])
            self.assertTrue(line["blocked"])
            self.assertEqual("blocked_by_environment", line["status"])
            self.assertIn("recommended_next_commands", line)

    def test_fake_http_responses_generate_passed_artifact_without_real_network(self) -> None:
        output = self.make_output_path()
        requested_urls: list[str] = []
        requested_payloads: list[dict[str, object]] = []

        def fake_post(url: str, payload: dict[str, object], *, timeout: float) -> object:
            requested_urls.append(url)
            requested_payloads.append(payload)
            if url.endswith("/api/v1/agent-batch/jobs"):
                jobs = dict(dict(payload["batch"])["jobs"][0])  # type: ignore[index]
                channel = str(jobs["channel"])
                self.assertEqual("search.market", channel)
                return self.http_result(
                    self.agent_batch_payload(
                        job_id="abj-search",
                        task_id="task-search",
                        run_id="run-search",
                        channel=channel,
                    )
                )
            if url.endswith("/api/v1/ingest/source-library/run"):
                self.assertEqual("url_pool.default", payload["item_key"])
                override_params = dict(payload["override_params"])  # type: ignore[arg-type]
                self.assertTrue(override_params["_source_library_smoke_only"])
                return self.http_result(
                    {
                        "status": "success",
                        "data": {
                            "task_id": "task-source",
                            "status": "queued",
                            "async_mode": True,
                            "trace_chain": {"task_id": "task-source"},
                        },
                    }
                )
            if url.endswith("/api/v1/writing/llm-actions"):
                return self.http_result(
                    {
                        "status": "success",
                        "data": {
                            "job_id": 704,
                            "trace_id": "trace-writing",
                            "status": "queued",
                            "observability": {"job_id": 704},
                        },
                    }
                )
            if url.endswith("/api/v1/ingest/url/single"):
                return self.http_result(
                    {
                        "status": "success",
                        "data": {
                            "task_id": "task-ingest",
                            "status": "queued",
                            "async_mode": True,
                            "trace_chain": {"task_id": "task-ingest"},
                        },
                    }
                )
            self.fail(f"unexpected URL: {url}")

        with patch.object(runner, "_http_post_json", side_effect=fake_post):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(4, len(requested_urls))
        self.assertEqual(4, payload["summary"]["accepted"])
        self.assertEqual([], payload["summary"]["blocked_line_keys"])
        self.assertEqual([], payload["summary"]["failed_line_keys"])
        self.assertCountEqual(runner.WORKER_REQUIRED_LINE_KEYS, payload["summary"]["accepted_line_keys"])

        by_line = {line["line_key"]: line for line in payload["lines"]}
        self.assertEqual("task-search", by_line["search_discovery_index"]["task_id"])
        self.assertEqual("run-search", by_line["search_discovery_index"]["run_id"])
        self.assertEqual("abj-search", by_line["search_discovery_index"]["job_id"])
        self.assertEqual("task-source", by_line["resource_source_library"]["task_id"])
        self.assertEqual("704", by_line["writing_knowledge_graph_agent"]["job_id"])
        self.assertEqual("task-ingest", by_line["ingest"]["task_id"])
        for line in payload["lines"]:
            self.assertTrue(line["accepted"])
            self.assertFalse(line["blocked"])
            self.assertIn("trigger_kind", line)
            self.assertIn("recommended_next_commands", line)

        self.assertTrue(all(item["project_key"] == "demo_proj" for item in requested_payloads))
        self.assertIn("run_business_line_worker_readback_evidence_chain.py", payload["recommended_next_commands"][0])

    def test_http_error_marks_line_failed_not_blocked(self) -> None:
        output = self.make_output_path()

        def fake_post(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith("/api/v1/agent-batch/jobs"):
                return runner.HttpResult(
                    status_code=500,
                    body=json.dumps({"status": "error", "error": {"message": "boom"}}),
                    error="HTTP Error 500",
                )
            return self.http_result({"status": "success", "data": {"task_id": "unused"}})

        with patch.object(runner, "_http_post_json", side_effect=fake_post):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        first = payload["lines"][0]
        self.assertEqual("failed", first["status"])
        self.assertFalse(first["blocked"])
        self.assertEqual("http_error", first["reason"])


if __name__ == "__main__":
    unittest.main()
