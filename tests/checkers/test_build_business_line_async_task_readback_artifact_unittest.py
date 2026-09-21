#!/usr/bin/env python3
"""Focused tests for building business-line async task readback artifacts."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_business_line_async_task_readback_artifact.py"
SPEC = importlib.util.spec_from_file_location("build_business_line_async_task_readback_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class BusinessLineAsyncTaskReadbackBuilderTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def evidence_line(self, line_key: str, *, requires_worker_readback: bool) -> dict[str, object]:
        terminal = "succeeded" if line_key == "search_discovery_index" else "completed"
        return {
            "line_key": line_key,
            "async_task_readback": {
                "proof_level": "async_task_readback_contract",
                "requires_worker_readback": requires_worker_readback,
                "readback_artifact": f"business_line_async_task_readback.{line_key}.v1",
                "readback_paths": [f"artifacts/{line_key}/task-readback.json"],
                "required_events": ["queued", "started", terminal],
                "terminal_states": ["completed", "succeeded"],
                "blocked_semantics": "missing task readback is blocked_by_environment, not passed",
            },
        }

    def evidence_matrix(self, *, include_readback: bool = True) -> dict[str, object]:
        worker_lines = {
            "ingest",
            "search_discovery_index",
            "resource_source_library",
            "writing_knowledge_graph_agent",
        }
        lines = []
        for line_key in builder.REQUIRED_LINE_KEYS:
            if include_readback:
                lines.append(self.evidence_line(line_key, requires_worker_readback=line_key in worker_lines))
            else:
                lines.append({"line_key": line_key})
        return {
            "contract_version": "business_line.evidence_matrix.v1",
            "lines": lines,
        }

    def sample(self, line_key: str, *, status: str = "completed", mocked: bool = False, skipped: bool = False) -> dict[str, object]:
        return {
            "line_key": line_key,
            "task_id": f"task-{line_key}",
            "run_id": f"run-{line_key}",
            "status": status,
            "events": ["queued", "started", status],
            "worker_name": "celery@local",
            "queue": "default",
            "trace_id": f"trace-{line_key}",
            "readback_path": f"artifacts/{line_key}/task-readback.json",
            "readback_endpoint": f"/api/v1/{line_key}/tasks/task-{line_key}",
            "mocked": mocked,
            "skipped": skipped,
        }

    def samples(self) -> dict[str, object]:
        return {
            "samples": [
                self.sample(line_key, status="succeeded" if line_key == "search_discovery_index" else "completed")
                for line_key in builder.REQUIRED_LINE_KEYS
            ]
        }

    def test_builds_passed_artifact_when_all_lines_have_terminal_samples(self) -> None:
        artifact = builder.build_artifact(
            self.evidence_matrix(),
            self.samples(),
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual(builder.ARTIFACT_SCHEMA_VERSION, artifact["schema_version"])
        self.assertEqual("passed", artifact["status"])
        self.assertEqual([], artifact["summary"]["blocked_line_keys"])
        self.assertEqual([], artifact["summary"]["failed_line_keys"])
        self.assertEqual(
            [
                "ingest",
                "search_discovery_index",
                "resource_source_library",
                "writing_knowledge_graph_agent",
            ],
            artifact["summary"]["requires_worker_readback_line_keys"],
        )
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("async_task_readback_completed", ingest["reason"])
        self.assertEqual(1, ingest["terminal_sample_count"])
        runtime_ops = [line for line in artifact["lines"] if line["line_key"] == "runtime_ops"][0]
        self.assertEqual("process_config_audit_readback_completed", runtime_ops["reason"])
        self.assertEqual(1, runtime_ops["terminal_sample_count"])

    def test_missing_samples_blocks_all_lines_without_passing(self) -> None:
        artifact = builder.build_artifact(
            self.evidence_matrix(),
            None,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=None,
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("blocked_by_environment", artifact["status"])
        self.assertEqual(list(builder.REQUIRED_LINE_KEYS), artifact["summary"]["blocked_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("async_task_readback_missing", ingest["reason"])
        self.assertNotEqual("passed", ingest["status"])
        runtime_ops = [line for line in artifact["lines"] if line["line_key"] == "runtime_ops"][0]
        self.assertEqual("async_task_readback_missing", runtime_ops["reason"])
        self.assertNotEqual("passed", runtime_ops["status"])

    def test_worker_required_sample_without_worker_context_fails(self) -> None:
        samples = self.samples()
        samples["samples"][0].pop("worker_name")  # type: ignore[index]

        artifact = builder.build_artifact(
            self.evidence_matrix(),
            samples,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("missing_worker_queue_context", ingest["reason"])

    def test_worker_required_sample_without_trace_fails(self) -> None:
        samples = self.samples()
        samples["samples"][0].pop("trace_id")  # type: ignore[index]

        artifact = builder.build_artifact(
            self.evidence_matrix(),
            samples,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("missing_trace_id", ingest["reason"])

    def test_worker_required_sample_without_required_event_fails(self) -> None:
        samples = self.samples()
        samples["samples"][0]["events"] = ["queued", "completed"]  # type: ignore[index]

        artifact = builder.build_artifact(
            self.evidence_matrix(),
            samples,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("missing_required_events", ingest["reason"])

    def test_worker_required_line_cannot_disable_worker_readback_in_evidence_contract(self) -> None:
        matrix = self.evidence_matrix()
        matrix["lines"][0]["async_task_readback"]["requires_worker_readback"] = False  # type: ignore[index]

        artifact = builder.build_artifact(
            matrix,
            self.samples(),
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("worker_required_flag_mismatch", ingest["reason"])

    def test_worker_required_line_cannot_weaken_success_terminal_states(self) -> None:
        samples = self.samples()
        samples["samples"][0]["status"] = "started"  # type: ignore[index]
        samples["samples"][0]["events"] = ["queued", "started", "completed"]  # type: ignore[index]
        matrix = self.evidence_matrix()
        matrix["lines"][0]["async_task_readback"]["terminal_states"] = ["started"]  # type: ignore[index]

        artifact = builder.build_artifact(
            matrix,
            samples,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertNotEqual("passed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["blocked_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("terminal_task_readback_missing", ingest["reason"])

    def test_sample_without_identity_or_readback_location_fails(self) -> None:
        samples = self.samples()
        samples["samples"][0].pop("task_id")  # type: ignore[index]
        samples["samples"][0].pop("run_id")  # type: ignore[index]
        samples["samples"][1].pop("readback_path")  # type: ignore[index]
        samples["samples"][1].pop("readback_endpoint")  # type: ignore[index]

        artifact = builder.build_artifact(
            self.evidence_matrix(),
            samples,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        self.assertIn("search_discovery_index", artifact["summary"]["failed_line_keys"])

    def test_missing_async_task_readback_contract_fails_lines(self) -> None:
        artifact = builder.build_artifact(
            self.evidence_matrix(include_readback=False),
            self.samples(),
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertEqual(sorted(builder.REQUIRED_LINE_KEYS), sorted(artifact["summary"]["failed_line_keys"]))
        self.assertEqual("missing_async_task_readback_contract", artifact["lines"][0]["reason"])

    def test_mocked_or_skipped_samples_fail(self) -> None:
        samples = self.samples()
        samples["samples"][0]["mocked"] = True  # type: ignore[index]
        samples["samples"][1]["skipped"] = True  # type: ignore[index]

        artifact = builder.build_artifact(
            self.evidence_matrix(),
            samples,
            evidence_matrix_path=Path("evidence.json"),
            task_readback_samples_path=Path("samples.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        self.assertIn("search_discovery_index", artifact["summary"]["failed_line_keys"])

    def test_main_writes_output_file(self) -> None:
        root = self.make_repo()
        evidence_path = self.write_json(root, "evidence.json", self.evidence_matrix())
        samples_path = self.write_json(root, "samples.json", self.samples())
        output_path = root / "artifact.json"

        exit_code = builder.main(
            [
                "--evidence-matrix",
                str(evidence_path),
                "--task-readback-samples",
                str(samples_path),
                "--output",
                str(output_path),
            ]
        )

        self.assertEqual(0, exit_code)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(builder.ARTIFACT_SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("passed", payload["status"])


if __name__ == "__main__":
    unittest.main()
