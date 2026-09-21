#!/usr/bin/env python3
"""Focused tests for live async task readback sample generation."""

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


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_business_line_async_task_readback_live_samples.py"
SPEC = importlib.util.spec_from_file_location("run_business_line_async_task_readback_live_samples", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)

BUILDER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_business_line_async_task_readback_artifact.py"
BUILDER_SPEC = importlib.util.spec_from_file_location("build_business_line_async_task_readback_artifact", BUILDER_PATH)
assert BUILDER_SPEC is not None and BUILDER_SPEC.loader is not None
builder = importlib.util.module_from_spec(BUILDER_SPEC)
sys.modules[BUILDER_SPEC.name] = builder
BUILDER_SPEC.loader.exec_module(builder)

WORKER_REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
)
NON_WORKER_LINE_KEYS = (
    "projects_config_workflow",
    "dashboard_admin_governance",
    "runtime_ops",
)


class BusinessLineAsyncTaskReadbackLiveSamplesTestCase(unittest.TestCase):
    def make_output_path(self, name: str = "live-samples.json") -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / name

    def write_json(self, name: str, payload: object) -> Path:
        path = self.make_output_path(name)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def evidence_line(self, line_key: str, *, requires_worker_readback: bool) -> dict[str, object]:
        terminal = {
            "projects_config_workflow": "applied",
            "dashboard_admin_governance": "available",
            "runtime_ops": "healthy",
        }.get(line_key, "completed")
        required_events = (
            ["queued", "started", terminal]
            if requires_worker_readback
            else ["readback_probe_started", "readback_probe_completed", terminal]
        )
        return {
            "line_key": line_key,
            "live_smoke": {"probe_path": f"/api/v1/live-smoke/{line_key}"},
            "async_task_readback": {
                "proof_level": "async_task_readback_contract",
                "requires_worker_readback": requires_worker_readback,
                "readback_artifact": f"business_line_async_task_readback.{line_key}.v1",
                "readback_paths": [f"/api/v1/readback/{line_key}/{{id}}"],
                "required_events": required_events,
                "terminal_states": [terminal, "blocked_by_environment"],
                "blocked_semantics": "missing readback is blocked_by_environment, not passed",
            },
        }

    def matrix_payload(
        self,
        *,
        line_keys: list[str] | None = None,
        duplicate: str | None = None,
        unexpected: str | None = None,
    ) -> dict[str, object]:
        keys = line_keys if line_keys is not None else list(runner.EXPECTED_LINE_KEYS)
        lines = [
            self.evidence_line(line_key, requires_worker_readback=line_key in WORKER_REQUIRED_LINE_KEYS)
            for line_key in keys
        ]
        if duplicate is not None:
            lines.append(self.evidence_line(duplicate, requires_worker_readback=duplicate in WORKER_REQUIRED_LINE_KEYS))
        if unexpected is not None:
            lines.append(self.evidence_line(unexpected, requires_worker_readback=False))
        return {
            "status": "ok",
            "data": {
                "contract_version": "business_line.evidence_matrix.v1",
                "lines": lines,
            },
            "error": None,
            "meta": {},
        }

    def worker_manifest_sample(self, line_key: str) -> dict[str, object]:
        terminal = "succeeded" if line_key == "search_discovery_index" else "completed"
        return {
            "line_key": line_key,
            "task_id": f"task-{line_key}",
            "run_id": f"run-{line_key}",
            "status": terminal,
            "events": ["queued", "started", terminal],
            "worker_name": f"celery@{line_key}",
            "queue": f"{line_key}.queue",
            "trace_id": f"trace-{line_key}",
            "readback_endpoint": f"/api/v1/task-readback/{line_key}/task-{line_key}",
            "mocked": False,
            "skipped": False,
        }

    def worker_manifest_payload(self) -> dict[str, object]:
        return {
            "schema_version": "business_line_async_task_readback_manifest.v1",
            "samples": [self.worker_manifest_sample(line_key) for line_key in WORKER_REQUIRED_LINE_KEYS],
        }

    def worker_readback_payload(self, line_key: str, **overrides: object) -> dict[str, object]:
        sample = self.worker_manifest_sample(line_key)
        terminal = "completed"
        payload = {
            "task_id": sample["task_id"],
            "run_id": sample["run_id"],
            "worker_name": sample["worker_name"],
            "queue": sample["queue"],
            "trace_id": sample["trace_id"],
            "status": terminal,
            "events": ["queued", "started", terminal],
            "meta": {"request_id": f"req-{line_key}"},
        }
        payload.update(overrides)
        return payload

    def run_with_manifest(self, manifest_payload: dict[str, object], *, output_name: str) -> tuple[int, dict[str, object]]:
        output = self.make_output_path(output_name)
        manifest = self.write_json(f"{output_name}-manifest.json", manifest_payload)

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            line_key = next((key for key in runner.EXPECTED_LINE_KEYS if key in url), "unknown")
            if line_key in WORKER_REQUIRED_LINE_KEYS:
                return self.http_result(200, self.worker_readback_payload(line_key))
            return self.http_result(200, {"status": "ok", "meta": {"trace_id": f"trace-{line_key}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            return self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                    "--allow-blocked",
                    "--json",
                ]
            )

    def run_with_worker_readback_payload(
        self,
        line_key: str,
        readback_payload: dict[str, object],
        *,
        output_name: str,
    ) -> tuple[int, dict[str, object]]:
        output = self.make_output_path(output_name)
        manifest = self.write_json(f"{output_name}-manifest.json", self.worker_manifest_payload())
        matrix = self.matrix_payload()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, matrix)
            current_line_key = next((key for key in runner.EXPECTED_LINE_KEYS if key in url), "unknown")
            if current_line_key == line_key:
                return self.http_result(200, readback_payload)
            if current_line_key in WORKER_REQUIRED_LINE_KEYS:
                return self.http_result(200, self.worker_readback_payload(current_line_key))
            return self.http_result(200, {"status": "ok", "meta": {"request_id": f"req-{current_line_key}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            return self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                    "--json",
                ]
            )

    def http_result(self, status_code: int, payload: object | None = None) -> object:
        return runner.HttpResult(status_code=status_code, body=json.dumps(payload if payload is not None else {}))

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = runner.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def test_matrix_unreachable_blocks_and_allow_blocked_exits_zero(self) -> None:
        output = self.make_output_path()
        with patch.object(runner, "_http_get", return_value=runner.HttpResult(None, "", "connection refused")):
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
        self.assertEqual("evidence_matrix_unreachable", payload["matrix"]["reason"])
        self.assertEqual([], payload["samples"])
        self.assertEqual(list(runner.EXPECTED_LINE_KEYS), payload["summary"]["blocked_line_keys"])

    def test_matrix_unreachable_does_not_mask_manifest_anomaly_failure(self) -> None:
        output = self.make_output_path()
        manifest_payload = self.worker_manifest_payload()
        manifest_payload["samples"].append(self.worker_manifest_sample("shadow_line"))  # type: ignore[union-attr]
        manifest = self.write_json("unreachable-unexpected-manifest.json", manifest_payload)

        with patch.object(runner, "_http_get", return_value=runner.HttpResult(None, "", "connection refused")):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual(["shadow_line"], payload["task_readback_manifest"]["unexpected_line_keys"])
        self.assertEqual(list(WORKER_REQUIRED_LINE_KEYS), payload["summary"]["failed_line_keys"])

    def test_live_non_worker_samples_pass_and_worker_required_lines_block(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            return self.http_result(200, {"status": "ok", "meta": {"request_id": f"req-{url.rsplit('/', 1)[-1]}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
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
        self.assertEqual(runner.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual(
            list(NON_WORKER_LINE_KEYS),
            payload["summary"]["sample_line_keys"],
        )
        self.assertEqual(3, len(payload["samples"]))
        self.assertEqual(
            {
                "projects_config_workflow": "applied",
                "dashboard_admin_governance": "available",
                "runtime_ops": "healthy",
            },
            {sample["line_key"]: sample["status"] for sample in payload["samples"]},
        )
        self.assertEqual(
            list(WORKER_REQUIRED_LINE_KEYS),
            payload["summary"]["blocked_line_keys"],
        )
        lines_by_key = {line["line_key"]: line for line in payload["lines"]}
        self.assertTrue(
            all(lines_by_key[line_key]["status"] == "blocked_by_environment" for line_key in WORKER_REQUIRED_LINE_KEYS)
        )
        self.assertTrue(
            all(
                lines_by_key[line_key]["reason"] == "task_readback_manifest_missing"
                for line_key in WORKER_REQUIRED_LINE_KEYS
            )
        )
        self.assertTrue(all(lines_by_key[line_key]["status"] == "passed" for line_key in NON_WORKER_LINE_KEYS))
        self.assertTrue(all(sample["mocked"] is False for sample in payload["samples"]))
        self.assertTrue(all(sample["skipped"] is False for sample in payload["samples"]))

    def test_worker_required_manifest_generates_live_worker_samples(self) -> None:
        output = self.make_output_path()
        manifest = self.write_json("task-readback-manifest.json", self.worker_manifest_payload())
        matrix = self.matrix_payload()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, matrix)
            line_key = next((key for key in runner.EXPECTED_LINE_KEYS if key in url), "unknown")
            if line_key in WORKER_REQUIRED_LINE_KEYS:
                return self.http_result(200, self.worker_readback_payload(line_key))
            return self.http_result(200, {"status": "ok", "meta": {"request_id": f"req-{line_key}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(list(runner.EXPECTED_LINE_KEYS), payload["summary"]["sample_line_keys"])
        samples_by_line = {sample["line_key"]: sample for sample in payload["samples"]}
        for line_key in WORKER_REQUIRED_LINE_KEYS:
            with self.subTest(line_key=line_key):
                sample = samples_by_line[line_key]
                self.assertEqual(f"task-{line_key}", sample["task_id"])
                self.assertEqual(f"run-{line_key}", sample["run_id"])
                self.assertEqual(f"celery@{line_key}", sample["worker_name"])
                self.assertEqual(f"{line_key}.queue", sample["queue"])
                self.assertEqual(f"trace-{line_key}", sample["trace_id"])
                self.assertEqual(self.worker_readback_payload(line_key)["status"], sample["status"])
                self.assertEqual(self.worker_readback_payload(line_key)["events"], sample["events"])
                self.assertEqual(f"/api/v1/task-readback/{line_key}/task-{line_key}", sample["readback_endpoint"])
                self.assertIs(sample["mocked"], False)
                self.assertIs(sample["skipped"], False)
        self.assertEqual([], payload["summary"]["blocked_line_keys"])
        self.assertEqual([], payload["summary"]["failed_line_keys"])
        self.assertEqual([], payload["task_readback_manifest"]["unexpected_line_keys"])
        self.assertEqual([], payload["task_readback_manifest"]["duplicate_line_keys"])

    def test_worker_required_process_db_job_exact_endpoint_generates_live_sample(self) -> None:
        output = self.make_output_path("process-db-job-exact.json")
        manifest_payload = self.worker_manifest_payload()
        run_ids = {
            "ingest": "701",
            "search_discovery_index": "702",
            "resource_source_library": "703",
            "writing_knowledge_graph_agent": "704",
        }
        for item in manifest_payload["samples"]:  # type: ignore[index]
            line_key = item["line_key"]
            run_id = run_ids[line_key]
            item["task_id"] = f"process-task-{line_key}"
            item["run_id"] = run_id
            item["worker_name"] = f"process-worker@{line_key}"
            item["queue"] = f"process.{line_key}"
            item["trace_id"] = f"process-trace-{line_key}"
            item["readback_endpoint"] = f"/api/v1/process/db-job-{run_id}"
            item["readback_path"] = f"/api/v1/process/db-job-{run_id}"
        manifest = self.write_json("process-db-job-manifest.json", manifest_payload)
        matrix = self.matrix_payload()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, matrix)
            line_key = next((key for key in runner.EXPECTED_LINE_KEYS if key in url), "ingest")
            if "/api/v1/process/db-job-" in url:
                run_id = url.rsplit("db-job-", 1)[1].split("?", 1)[0]
                line_key = next((key for key, value in run_ids.items() if value == run_id), "ingest")
                return self.http_result(
                    200,
                    {
                        "status": "ok",
                        "data": {
                            "line_key": line_key,
                            "task_id": f"process-task-{line_key}",
                            "run_id": run_id,
                            "worker_name": f"process-worker@{line_key}",
                            "queue": f"process.{line_key}",
                            "trace_id": f"process-trace-{line_key}",
                            "status": "completed",
                            "events": ["queued", "started", "completed"],
                        },
                    },
                )
            return self.http_result(200, {"status": "ok", "meta": {"request_id": f"req-{line_key}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        ingest = next(sample for sample in payload["samples"] if sample["line_key"] == "ingest")
        self.assertEqual("/api/v1/process/db-job-701", ingest["readback_endpoint"])
        self.assertEqual("process-task-ingest", ingest["task_id"])
        self.assertEqual("701", ingest["run_id"])

    def test_project_key_is_applied_to_matrix_and_process_db_job_exact_endpoint(self) -> None:
        output = self.make_output_path("process-db-job-project-key.json")
        manifest_payload = self.worker_manifest_payload()
        ingest = manifest_payload["samples"][0]  # type: ignore[index]
        ingest["task_id"] = "process-task-ingest"
        ingest["run_id"] = "701"
        ingest["worker_name"] = "process-worker@ingest"
        ingest["queue"] = "process.ingest"
        ingest["trace_id"] = "process-trace-ingest"
        ingest["readback_endpoint"] = "/api/v1/process/db-job-701"
        ingest["readback_path"] = "/api/v1/process/db-job-701"
        manifest = self.write_json("process-db-job-project-key-manifest.json", manifest_payload)
        requested_urls: list[str] = []

        def fake_get(url: str, *, timeout: float) -> object:
            requested_urls.append(url)
            if url.endswith(f"{runner.MATRIX_PATH}?project_key=demo_proj"):
                return self.http_result(200, self.matrix_payload())
            if "/api/v1/process/db-job-701?project_key=demo_proj" in url:
                return self.http_result(
                    200,
                    {
                        "status": "ok",
                        "data": {
                            "line_key": "ingest",
                            "task_id": "process-task-ingest",
                            "run_id": "701",
                            "worker_name": "process-worker@ingest",
                            "queue": "process.ingest",
                            "trace_id": "process-trace-ingest",
                            "status": "completed",
                            "events": ["queued", "started", "completed"],
                        },
                    },
                )
            line_key = next((key for key in runner.EXPECTED_LINE_KEYS if key in url), "unknown")
            if line_key in WORKER_REQUIRED_LINE_KEYS:
                return self.http_result(200, self.worker_readback_payload(line_key))
            return self.http_result(200, {"status": "ok", "meta": {"request_id": f"req-{line_key}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                    "--project-key",
                    "demo_proj",
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("demo_proj", payload["project_key"])
        self.assertEqual("/api/v1/business-lines/evidence-matrix?project_key=demo_proj", payload["matrix_path"])
        self.assertIn("--project-key demo_proj", payload["recommended_command"])
        self.assertTrue(any(url.endswith("/api/v1/process/db-job-701?project_key=demo_proj") for url in requested_urls))
        ingest_sample = next(sample for sample in payload["samples"] if sample["line_key"] == "ingest")
        self.assertEqual("/api/v1/process/db-job-701?project_key=demo_proj", ingest_sample["readback_endpoint"])

    def test_worker_required_process_collection_manifest_endpoint_is_rejected(self) -> None:
        manifest_payload = self.worker_manifest_payload()
        ingest = manifest_payload["samples"][0]  # type: ignore[index]
        ingest["readback_endpoint"] = "/api/v1/process/tasks?line_key=ingest&limit=5"
        ingest["readback_path"] = "/api/v1/process/tasks?line_key=ingest&limit=5"

        exit_code, payload = self.run_with_manifest(
            manifest_payload,
            output_name="process-collection-endpoint.json",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", payload["status"])
        ingest_line = next(line for line in payload["lines"] if line["line_key"] == "ingest")
        self.assertEqual("blocked_by_environment", ingest_line["status"])
        self.assertEqual("readback_location_not_precise", ingest_line["reason"])

    def test_worker_required_2xx_without_status_events_does_not_pass(self) -> None:
        line_key = "ingest"
        readback_payload = self.worker_readback_payload(line_key)
        readback_payload.pop("status")
        readback_payload.pop("events")

        exit_code, payload = self.run_with_worker_readback_payload(
            line_key,
            readback_payload,
            output_name="missing-terminal-evidence.json",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("live_readback_terminal_evidence_missing", ingest["reason"])
        self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_worker_required_trace_mismatch_does_not_pass(self) -> None:
        line_key = "ingest"
        readback_payload = self.worker_readback_payload(line_key, trace_id="trace-other")

        exit_code, payload = self.run_with_worker_readback_payload(
            line_key,
            readback_payload,
            output_name="trace-mismatch.json",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("live_readback_trace_mismatch", ingest["reason"])
        self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_worker_required_request_id_does_not_replace_trace_id(self) -> None:
        line_key = "ingest"
        readback_payload = self.worker_readback_payload(line_key)
        readback_payload.pop("trace_id")
        readback_payload["request_id"] = f"trace-{line_key}"
        readback_payload["correlation_id"] = f"trace-{line_key}"

        exit_code, payload = self.run_with_worker_readback_payload(
            line_key,
            readback_payload,
            output_name="trace-fallback-rejected.json",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("live_readback_trace_missing", ingest["reason"])
        self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_worker_required_identity_mismatch_does_not_pass(self) -> None:
        line_key = "ingest"
        readback_payload = self.worker_readback_payload(line_key, task_id="task-other", run_id="run-other")

        exit_code, payload = self.run_with_worker_readback_payload(
            line_key,
            readback_payload,
            output_name="identity-mismatch.json",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("live_readback_identity_mismatch", ingest["reason"])
        self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_worker_required_partial_identity_mismatch_does_not_pass(self) -> None:
        line_key = "ingest"
        readback_payload = self.worker_readback_payload(line_key, run_id="run-other")

        exit_code, payload = self.run_with_worker_readback_payload(
            line_key,
            readback_payload,
            output_name="partial-identity-mismatch.json",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("live_readback_identity_mismatch", ingest["reason"])
        self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_worker_required_missing_required_event_does_not_pass(self) -> None:
        line_key = "ingest"
        readback_payload = self.worker_readback_payload(line_key)
        readback_payload["events"] = ["queued", "completed"]

        exit_code, payload = self.run_with_worker_readback_payload(
            line_key,
            readback_payload,
            output_name="missing-required-event.json",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("live_readback_required_events_missing", ingest["reason"])
        self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_worker_required_worker_queue_mismatch_does_not_pass(self) -> None:
        cases = [
            ("worker", {"worker_name": "celery@other"}, "live_readback_worker_mismatch"),
            ("queue", {"queue": "other.queue"}, "live_readback_queue_mismatch"),
        ]
        for name, overrides, reason in cases:
            with self.subTest(name=name):
                line_key = "ingest"
                readback_payload = self.worker_readback_payload(line_key, **overrides)

                exit_code, payload = self.run_with_worker_readback_payload(
                    line_key,
                    readback_payload,
                    output_name=f"{name}-mismatch.json",
                )

                self.assertEqual(1, exit_code)
                self.assertEqual("failed", payload["status"])
                ingest = next(line for line in payload["lines"] if line["line_key"] == line_key)
                self.assertEqual("failed", ingest["status"])
                self.assertEqual(reason, ingest["reason"])
                self.assertNotIn(line_key, payload["summary"]["sample_line_keys"])

    def test_duplicate_manifest_line_fails_worker_required_line(self) -> None:
        manifest_payload = self.worker_manifest_payload()
        manifest_payload["samples"].append(self.worker_manifest_sample("ingest"))  # type: ignore[union-attr]

        exit_code, payload = self.run_with_manifest(manifest_payload, output_name="duplicate-manifest.json")

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual(["ingest"], payload["task_readback_manifest"]["duplicate_line_keys"])
        ingest = next(line for line in payload["lines"] if line["line_key"] == "ingest")
        self.assertEqual("failed", ingest["status"])
        self.assertEqual("task_readback_manifest_duplicate_line_keys", ingest["reason"])
        self.assertIn("ingest", payload["summary"]["failed_line_keys"])

    def test_unexpected_manifest_line_fails_worker_required_lines(self) -> None:
        manifest_payload = self.worker_manifest_payload()
        manifest_payload["samples"].append(self.worker_manifest_sample("shadow_line"))  # type: ignore[union-attr]

        exit_code, payload = self.run_with_manifest(manifest_payload, output_name="unexpected-manifest.json")

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual(["shadow_line"], payload["task_readback_manifest"]["unexpected_line_keys"])
        worker_lines = [line for line in payload["lines"] if line["line_key"] in WORKER_REQUIRED_LINE_KEYS]
        self.assertTrue(worker_lines)
        self.assertTrue(all(line["status"] == "failed" for line in worker_lines))
        self.assertTrue(
            all(line["reason"] == "task_readback_manifest_unexpected_line_keys" for line in worker_lines)
        )

    def test_worker_required_manifest_missing_worker_context_does_not_pass(self) -> None:
        cases = [
            ("missing_worker_name", "worker_name"),
            ("missing_queue", "queue"),
        ]
        for name, missing_field in cases:
            with self.subTest(name=name):
                output = self.make_output_path(f"{name}-samples.json")
                manifest_payload = self.worker_manifest_payload()
                first_sample = manifest_payload["samples"][0]  # type: ignore[index]
                first_sample.pop(missing_field)  # type: ignore[attr-defined]
                manifest = self.write_json(f"{name}-manifest.json", manifest_payload)

                def fake_get(url: str, *, timeout: float) -> object:
                    if url.endswith(runner.MATRIX_PATH):
                        return self.http_result(200, self.matrix_payload())
                    return self.http_result(200, {"status": "ok", "meta": {"trace_id": "trace-live"}})

                with patch.object(runner, "_http_get", side_effect=fake_get):
                    exit_code, payload = self.run_main(
                        [
                            "--api-base",
                            "http://127.0.0.1:8000",
                            "--output",
                            str(output),
                            "--task-readback-manifest",
                            str(manifest),
                            "--allow-blocked",
                            "--json",
                        ]
                    )

                self.assertIn(payload["status"], {"failed", "blocked_by_environment"})
                self.assertEqual(1 if payload["status"] == "failed" else 0, exit_code)
                ingest = next(line for line in payload["lines"] if line["line_key"] == "ingest")
                self.assertNotEqual("passed", ingest["status"])
                sample = next((sample for sample in payload["samples"] if sample.get("line_key") == "ingest"), None)
                if sample is not None:
                    built_line = builder.build_line(
                        "ingest",
                        evidence_line=self.evidence_line("ingest", requires_worker_readback=True),
                        samples=[sample],
                    )
                    self.assertNotEqual("passed", built_line["status"])

    def test_builder_keeps_worker_required_blocked_and_non_worker_passed(self) -> None:
        output = self.make_output_path()
        matrix = self.matrix_payload()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, matrix)
            return self.http_result(200, {"status": "ok", "meta": {"request_id": "req-live"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                ]
            )

        self.assertEqual(0, exit_code)
        artifact = builder.build_artifact(
            matrix,
            payload,
            evidence_matrix_path=Path("matrix.json"),
            task_readback_samples_path=output,
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("blocked_by_environment", artifact["status"])
        line_statuses = {line["line_key"]: line["status"] for line in artifact["lines"]}
        self.assertEqual("blocked_by_environment", line_statuses["ingest"])
        self.assertEqual("blocked_by_environment", line_statuses["search_discovery_index"])
        self.assertEqual("blocked_by_environment", line_statuses["resource_source_library"])
        self.assertEqual("blocked_by_environment", line_statuses["writing_knowledge_graph_agent"])
        self.assertEqual("passed", line_statuses["projects_config_workflow"])
        self.assertEqual("passed", line_statuses["dashboard_admin_governance"])
        self.assertEqual("passed", line_statuses["runtime_ops"])

    def test_builder_consumes_runner_manifest_samples_and_passes_all_lines(self) -> None:
        output = self.make_output_path()
        manifest = self.write_json("task-readback-manifest.json", self.worker_manifest_payload())
        matrix = self.matrix_payload()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, matrix)
            line_key = next((key for key in runner.EXPECTED_LINE_KEYS if key in url), "unknown")
            if line_key in WORKER_REQUIRED_LINE_KEYS:
                return self.http_result(200, self.worker_readback_payload(line_key))
            return self.http_result(200, {"status": "ok", "meta": {"trace_id": f"trace-{line_key}"}})

        with patch.object(runner, "_http_get", side_effect=fake_get):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--task-readback-manifest",
                    str(manifest),
                ]
            )

        self.assertEqual(0, exit_code)
        artifact = builder.build_artifact(
            matrix,
            payload,
            evidence_matrix_path=Path("matrix.json"),
            task_readback_samples_path=output,
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("passed", artifact["status"])
        self.assertEqual(list(runner.EXPECTED_LINE_KEYS), artifact["summary"]["passed_line_keys"])
        self.assertEqual([], artifact["summary"]["blocked_line_keys"])
        self.assertEqual([], artifact["summary"]["failed_line_keys"])

    def test_non_worker_probe_5xx_fails(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            if url.endswith("/projects_config_workflow"):
                return self.http_result(503)
            return self.http_result(200)

        with patch.object(runner, "_http_get", side_effect=fake_get):
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
        self.assertIn("projects_config_workflow", payload["summary"]["failed_line_keys"])
        self.assertNotIn("projects_config_workflow", payload["summary"]["sample_line_keys"])

    def test_missing_duplicate_and_unexpected_matrix_lines_fail(self) -> None:
        cases = [
            (
                "missing",
                self.matrix_payload(line_keys=list(runner.EXPECTED_LINE_KEYS[:-1])),
                "missing_line_keys",
                "runtime_ops",
            ),
            ("duplicate", self.matrix_payload(duplicate="ingest"), "duplicate_line_keys", "ingest"),
            ("unexpected", self.matrix_payload(unexpected="other_line"), "unexpected_line_keys", "other_line"),
        ]
        for name, matrix, anomaly_key, expected_value in cases:
            with self.subTest(name=name):
                output = self.make_output_path(f"{name}.json")

                def fake_get(url: str, *, timeout: float) -> object:
                    if url.endswith(runner.MATRIX_PATH):
                        return self.http_result(200, matrix)
                    return self.http_result(200)

                with patch.object(runner, "_http_get", side_effect=fake_get):
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
                self.assertIn(expected_value, payload["matrix_anomalies"][anomaly_key])

    def test_no_mocked_or_skipped_samples_are_generated(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith(runner.MATRIX_PATH):
                return self.http_result(200, self.matrix_payload())
            return self.http_result(200)

        with patch.object(runner, "_http_get", side_effect=fake_get):
            _exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                ]
            )

        self.assertTrue(payload["samples"])
        self.assertTrue(all(sample.get("mocked") is False for sample in payload["samples"]))
        self.assertTrue(all(sample.get("skipped") is False for sample in payload["samples"]))


if __name__ == "__main__":
    unittest.main()
