#!/usr/bin/env python3
"""Focused tests for runtime worker task readback manifest candidate building."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_business_line_task_readback_manifest_from_runtime.py"
)
SPEC = importlib.util.spec_from_file_location("build_business_line_task_readback_manifest_from_runtime", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)

CHECKER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_task_readback_manifest.py"
CHECKER_SPEC = importlib.util.spec_from_file_location("check_business_line_task_readback_manifest", CHECKER_PATH)
assert CHECKER_SPEC is not None and CHECKER_SPEC.loader is not None
checker = importlib.util.module_from_spec(CHECKER_SPEC)
sys.modules[CHECKER_SPEC.name] = checker
CHECKER_SPEC.loader.exec_module(checker)


WORKER_REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
)

NON_WORKER_CANONICAL_LINE_KEYS = (
    "projects_config_workflow",
    "dashboard_admin_governance",
    "runtime_ops",
)

REQUIRED_EVENTS_BY_LINE = {
    "ingest": [
        "submission_accepted",
        "task_queued",
        "worker_started",
        "source_fetch_completed",
        "index_handoff_recorded",
        "readback_persisted",
    ],
    "search_discovery_index": [
        "search_or_discovery_run_accepted",
        "task_queued",
        "worker_started",
        "index_refresh_started",
        "index_refresh_completed",
        "results_readback_persisted",
    ],
    "resource_source_library": [
        "resource_action_accepted",
        "task_queued",
        "worker_started",
        "adapter_capture_completed",
        "source_lifecycle_updated",
        "readback_persisted",
    ],
    "writing_knowledge_graph_agent": [
        "agent_batch_submitted",
        "task_queued",
        "worker_started",
        "agent_event_persisted",
        "approval_state_recorded",
        "artifact_readback_persisted",
    ],
}


class BusinessLineTaskReadbackManifestRuntimeBuilderTestCase(unittest.TestCase):
    def make_output_path(self, name: str = "manifest.json") -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / name

    def http_result(self, status_code: int | None, payload: object | None = None, error: str | None = None) -> object:
        return builder.HttpResult(
            status_code=status_code,
            body=json.dumps(payload if payload is not None else {}),
            error=error,
        )

    def evidence_line(self, line_key: str) -> dict[str, object]:
        return {
            "line_key": line_key,
            "live_smoke": {"probe_path": f"/api/v1/runtime/{line_key}/latest"},
            "async_task_readback": {
                "proof_level": "async_task_readback_contract",
                "requires_worker_readback": True,
                "readback_artifact": f"business_line_async_task_readback.{line_key}.v1",
                "readback_paths": [f"/api/v1/readback/{line_key}/{{task_id}}"],
                "required_events": REQUIRED_EVENTS_BY_LINE[line_key],
                "terminal_states": ["completed", "succeeded", "blocked_by_environment"],
                "blocked_semantics": "missing real task readback is blocked_by_environment, not passed",
            },
        }

    def non_worker_evidence_line(self, line_key: str) -> dict[str, object]:
        return {
            "line_key": line_key,
            "live_smoke": {"probe_path": f"/api/v1/runtime/{line_key}/latest"},
            "async_task_readback": {
                "proof_level": "async_task_readback_contract",
                "requires_worker_readback": False,
                "readback_artifact": f"business_line_async_task_readback.{line_key}.v1",
                "readback_paths": [f"/api/v1/readback/{line_key}"],
                "required_events": ["completed"],
                "terminal_states": ["completed", "blocked_by_environment"],
                "blocked_semantics": "non-worker line is outside worker manifest candidate scope",
            },
        }

    def matrix_payload(self, *, lines: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "status": "ok",
            "data": {
                "contract_version": "business_line.evidence_matrix.v1",
                "lines": lines if lines is not None else [self.evidence_line(key) for key in WORKER_REQUIRED_LINE_KEYS],
            },
            "error": None,
            "meta": {},
        }

    def runtime_payload(self, line_key: str, *, include_identity: bool = True) -> dict[str, object]:
        terminal = "succeeded" if line_key == "search_discovery_index" else "completed"
        task: dict[str, object] = {
            "line_key": line_key,
            "worker_name": f"celery@{line_key}",
            "queue": f"{line_key}.queue",
            "trace_id": f"trace-{line_key}-20260525",
            "readback_endpoint": f"/api/v1/readback/{line_key}/task-{line_key}-20260525",
            "status": terminal,
            "events": [*REQUIRED_EVENTS_BY_LINE[line_key], terminal],
        }
        if include_identity:
            task["task_id"] = f"task-{line_key}-20260525"
            task["run_id"] = f"run-{line_key}-20260525"
        return {"status": "ok", "data": {"task": task}, "meta": {"trace_id": task["trace_id"]}}

    def process_runtime_item(self, line_key: str, *, include_identity: bool = True) -> dict[str, object]:
        terminal = "succeeded" if line_key == "search_discovery_index" else "completed"
        run_ids = {
            "ingest": "701",
            "search_discovery_index": "702",
            "resource_source_library": "703",
            "writing_knowledge_graph_agent": "704",
        }
        run_id = run_ids.get(line_key, "799")
        item: dict[str, object] = {
            "line_key": line_key,
            "worker_name": f"process-worker@{line_key}",
            "queue": f"process.{line_key}",
            "trace_id": f"process-trace-{line_key}-20260525",
            "readback_source": "etl_job_runs",
            "readback_path": f"/api/v1/process/db-job-{run_id}",
            "status": terminal,
            "events": [{"event": event} for event in [*REQUIRED_EVENTS_BY_LINE[line_key], terminal]],
        }
        if include_identity:
            item["task_id"] = f"process-task-{line_key}-20260525"
            item["run_id"] = run_id
        return item

    def process_items_envelope(self, line_key: str) -> dict[str, object]:
        return {
            "status": "success",
            "data": {"items": [self.process_runtime_item(line_key)]},
            "meta": {"trace_id": f"envelope-trace-{line_key}-20260525"},
        }

    def process_items_envelope_without_line_key(self, line_key: str) -> dict[str, object]:
        item = self.process_runtime_item(line_key)
        item.pop("line_key", None)
        return {
            "status": "success",
            "data": {"items": [item]},
            "meta": {"trace_id": f"envelope-trace-{line_key}-20260525"},
        }

    def process_items_envelope_with_wrong_line_key(self, line_key: str) -> dict[str, object]:
        item = self.process_runtime_item(line_key)
        item["line_key"] = "resource_source_library" if line_key != "resource_source_library" else "ingest"
        return {
            "status": "success",
            "data": {"items": [item]},
            "meta": {"trace_id": f"envelope-trace-{line_key}-20260525"},
        }

    def process_logs_envelope(self, line_key: str) -> dict[str, object]:
        return {
            "status": "success",
            "data": {"logs": [self.process_runtime_item(line_key)]},
            "meta": {"trace_id": f"envelope-trace-{line_key}-20260525"},
        }

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = builder.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def line_key_from_url(self, url: str) -> str:
        for line_key in WORKER_REQUIRED_LINE_KEYS:
            if f"/{line_key}/" in url or f"line_key={line_key}" in url:
                return line_key
        self.fail(f"test URL does not include a worker-required line key: {url}")

    def test_backend_unreachable_writes_blocked_and_allow_blocked_exits_zero(self) -> None:
        output = self.make_output_path()
        with patch.object(builder, "_http_get", return_value=builder.HttpResult(None, "", "connection refused")):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--timeout",
                    "2",
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(builder.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("evidence_matrix_unreachable", payload["matrix"]["reason"])
        self.assertEqual([], payload["samples"])
        self.assertEqual(list(WORKER_REQUIRED_LINE_KEYS), payload["summary"]["blocked_line_keys"])

    def test_matrix_malformed_fails(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return builder.HttpResult(200, "{not-json")
            return self.http_result(200, {})

        with patch.object(builder, "_http_get", side_effect=fake_get):
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

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual("evidence_matrix_invalid_json", payload["matrix"]["reason"])

    def test_four_real_runtime_candidates_pass(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            return self.http_result(200, self.runtime_payload(line_key))

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, payload["summary"]["passed_line_keys"])
        self.assertEqual([], payload["summary"]["blocked_line_keys"])
        self.assertEqual([], payload["summary"]["failed_line_keys"])
        self.assertEqual(payload["samples"], payload["task_readback_manifest"])
        self.assertTrue(payload["recommended_next_commands"][0].startswith("python3 scripts/check_business_line_task_readback_manifest.py"))
        self.assertIn("--task-readback-manifest", payload["recommended_next_commands"][1])

    def test_process_tasks_envelope_items_pass_without_legacy_task_readback_path(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            if "/api/v1/process/tasks" in url:
                return self.http_result(200, self.process_items_envelope(line_key))
            self.assertIn("/api/v1/runtime/", url)
            return self.http_result(404, {"status": "error", "error": "legacy readback route disabled"})

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, payload["summary"]["passed_line_keys"])
        self.assertEqual(payload["samples"], payload["task_readback_manifest"])
        for sample in payload["samples"]:
            line_key = sample["line_key"]
            self.assertEqual(f"process-task-{line_key}-20260525", sample["task_id"])
            self.assertTrue(str(sample["run_id"]).isdigit())
            self.assertEqual(f"process-worker@{line_key}", sample["worker_name"])
            self.assertEqual(f"process.{line_key}", sample["queue"])
            self.assertEqual(f"process-trace-{line_key}-20260525", sample["trace_id"])
            self.assertEqual(sample["readback_path"], sample["readback_endpoint"])
            self.assertTrue(sample["readback_endpoint"].startswith("/api/v1/process/db-job-"))

    def test_project_key_is_added_to_matrix_and_process_runtime_discovery_urls(self) -> None:
        output = self.make_output_path()
        requested_urls: list[str] = []

        def fake_get(url: str, *, timeout: float) -> object:
            requested_urls.append(url)
            if "/api/v1/business-lines/evidence-matrix" in url:
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            if "/api/v1/process/tasks" in url:
                return self.http_result(200, self.process_items_envelope(line_key))
            self.assertIn("/api/v1/runtime/", url)
            return self.http_result(404, {"status": "error", "error": "legacy readback route disabled"})

        with patch.object(builder, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--project-key",
                    "demo_proj",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual("demo_proj", payload["project_key"])
        self.assertIn("--project-key demo_proj", " ".join(payload["recommended_next_commands"]))

        matrix_urls = [url for url in requested_urls if "/api/v1/business-lines/evidence-matrix" in url]
        self.assertEqual(1, len(matrix_urls))
        self.assertEqual(["demo_proj"], parse_qs(urlparse(matrix_urls[0]).query)["project_key"])

        process_task_urls = [url for url in requested_urls if "/api/v1/process/tasks" in url]
        self.assertEqual(len(WORKER_REQUIRED_LINE_KEYS), len(process_task_urls))
        for url in process_task_urls:
            query = parse_qs(urlparse(url).query)
            self.assertIn(query["line_key"][0], WORKER_REQUIRED_LINE_KEYS)
            self.assertEqual(["5"], query["limit"])
            self.assertEqual(["demo_proj"], query["project_key"])
            self.assertIn("&project_key=demo_proj", url)
        for sample in payload["samples"]:
            self.assertIn("project_key=demo_proj", sample["readback_endpoint"])
            self.assertIn("project_key=demo_proj", sample["readback_path"])

    def test_process_logs_envelope_passes_when_tasks_are_empty(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            if "/api/v1/process/tasks" in url:
                return self.http_result(200, {"status": "success", "data": {"items": []}})
            if "/api/v1/process/logs" in url:
                return self.http_result(200, self.process_logs_envelope(line_key))
            self.assertIn("/api/v1/runtime/", url)
            return self.http_result(404, {"status": "error", "error": "legacy readback route disabled"})

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        for sample in payload["samples"]:
            line_key = sample["line_key"]
            self.assertEqual(f"process-task-{line_key}-20260525", sample["task_id"])
            self.assertEqual(sample["readback_path"], sample["readback_endpoint"])
            self.assertTrue(sample["readback_endpoint"].startswith("/api/v1/process/db-job-"))

    def test_process_tasks_empty_items_do_not_pass_or_generate_fake_samples(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            if "/api/v1/process/tasks" in url:
                return self.http_result(200, {"status": "success", "data": {"items": []}})
            if "/api/v1/process/logs" in url:
                return self.http_result(200, {"status": "success", "data": {"logs": []}})
            self.assertIn("/api/v1/runtime/", url)
            return self.http_result(404, {"status": "error", "error": "legacy readback route disabled"})

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        self.assertEqual([], payload["samples"])
        self.assertEqual([], payload["task_readback_manifest"])
        self.assertEqual([], payload["summary"]["passed_line_keys"])
        self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, payload["summary"]["blocked_line_keys"])
        for line in payload["lines"]:
            self.assertEqual("blocked_by_environment", line["status"])
            self.assertIn(
                line["reason"],
                {"runtime_candidate_missing_required_fields", "runtime_payload_has_no_candidate_objects"},
            )
            self.assertEqual(0, line["sample_count"])
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("process-task-", serialized)
        self.assertNotIn("process-worker@", serialized)

    def test_process_tasks_require_explicit_matching_line_key(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            if "/api/v1/process/tasks" in url:
                return self.http_result(200, self.process_items_envelope_without_line_key(line_key))
            if "/api/v1/process/logs" in url:
                return self.http_result(200, self.process_items_envelope_with_wrong_line_key(line_key))
            self.assertIn("/api/v1/runtime/", url)
            return self.http_result(404, {"status": "error", "error": "legacy readback route disabled"})

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        self.assertEqual([], payload["samples"])
        self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, payload["summary"]["blocked_line_keys"])
        for line in payload["lines"]:
            self.assertEqual("runtime_payload_has_no_candidate_objects", line["reason"])

    def test_missing_id_blocks_line(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            return self.http_result(200, self.runtime_payload(line_key, include_identity=line_key != "ingest"))

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        ingest = next(line for line in payload["lines"] if line["line_key"] == "ingest")
        self.assertEqual("blocked_by_environment", ingest["status"])
        self.assertEqual("runtime_candidate_missing_required_fields", ingest["reason"])
        self.assertIn("task_id_or_run_id", ingest["missing_fields"])

    def test_builder_does_not_auto_generate_identifier(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            return self.http_result(200, self.runtime_payload(line_key, include_identity=False))

        with patch.object(builder, "_http_get", side_effect=fake_get):
            _exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                ]
            )

        self.assertEqual([], payload["samples"])
        for line in payload["lines"]:
            self.assertIn("task_id_or_run_id", line["missing_fields"])
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("task-ingest", serialized)
        self.assertNotIn("run-ingest", serialized)

    def test_output_can_be_read_by_batch_74_checker_extract_structure(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = self.line_key_from_url(url)
            return self.http_result(200, self.runtime_payload(line_key))

        with patch.object(builder, "_http_get", side_effect=fake_get):
            _exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        extracted = checker.extract_manifest_items(payload)
        self.assertEqual(4, len(extracted))
        self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, [item["line_key"] for item in extracted])
        report = checker.build_report(output, root=output.parent, observed_at="2026-05-25T00:00:00Z")
        self.assertEqual("passed", report["status"])

    def test_canonical_non_worker_lines_are_not_matrix_anomalies(self) -> None:
        output = self.make_output_path()
        lines = [
            self.evidence_line(line_key) for line_key in WORKER_REQUIRED_LINE_KEYS
        ] + [
            self.non_worker_evidence_line(line_key)
            for line_key in NON_WORKER_CANONICAL_LINE_KEYS
        ]

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(builder.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload(lines=lines))
            line_key = self.line_key_from_url(url)
            return self.http_result(200, self.runtime_payload(line_key))

        with patch.object(builder, "_http_get", side_effect=fake_get):
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
        self.assertEqual([], payload["matrix_anomalies"]["unexpected_line_keys"])


if __name__ == "__main__":
    unittest.main()
