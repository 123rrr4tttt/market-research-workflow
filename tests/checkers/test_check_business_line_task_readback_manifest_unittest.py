#!/usr/bin/env python3
"""Focused tests for standalone business-line task readback manifests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_task_readback_manifest.py"

WORKER_REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
)
SYNTHETIC_MARKERS = ("synthetic", "fixture", "fake", "mock", "generated", "dummy")


class BusinessLineTaskReadbackManifestCheckerTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, name: str, payload: object) -> Path:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def line(self, line_key: str, **overrides: object) -> dict[str, object]:
        terminal = "succeeded" if line_key == "search_discovery_index" else "completed"
        row: dict[str, object] = {
            "line_key": line_key,
            "task_id": f"task-{line_key}-20260525",
            "run_id": f"run-{line_key}-20260525",
            "worker_name": f"celery@{line_key}",
            "queue": f"{line_key}.queue",
            "trace_id": f"trace-{line_key}-20260525",
            "readback_endpoint": f"/api/v1/task-readback/{line_key}/task-{line_key}-20260525",
            "status": terminal,
            "events": ["queued", "started", terminal],
        }
        row.update(overrides)
        return row

    def manifest(self, *, lines: list[dict[str, object]] | None = None, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "business_line_task_readback_manifest.v1",
            "manifest_kind": "business_line_task_readback",
            "lines": lines if lines is not None else [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS],
        }
        payload.update(overrides)
        return payload

    def run_checker(self, manifest_path: Path, *extra_args: str) -> tuple[int, dict[str, object], str]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(manifest_path), *extra_args, "--json"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                "checker must exist and print JSON with --json; "
                f"exit={completed.returncode}, stdout={completed.stdout!r}, stderr={completed.stderr!r}, error={exc}"
            )
        return completed.returncode, report, completed.stderr

    def summary(self, report: dict[str, object]) -> dict[str, object]:
        summary = report.get("summary")
        if isinstance(summary, dict):
            return summary
        artifact = report.get("artifact")
        if isinstance(artifact, dict) and isinstance(artifact.get("summary"), dict):
            return artifact["summary"]
        self.fail(f"checker JSON report must expose a summary object: {report}")

    def line_failures(self, report: dict[str, object]) -> dict[str, list[str]]:
        summary = self.summary(report)
        failures = summary.get("line_failures")
        if isinstance(failures, dict):
            return {
                str(line_key): [str(item) for item in values]
                for line_key, values in failures.items()
                if isinstance(values, list)
            }
        return {}

    def assert_line_failure(self, report: dict[str, object], line_key: str, field: str) -> None:
        summary = self.summary(report)
        invalid_line_keys = summary.get("invalid_line_keys")
        if isinstance(invalid_line_keys, list):
            self.assertIn(line_key, invalid_line_keys)
        line_failures = self.line_failures(report)
        if line_failures:
            self.assertIn(field, line_failures.get(line_key, []))

    def assert_status(self, report: dict[str, object], expected: str) -> None:
        self.assertEqual(expected, report.get("status"))

    def assert_blocked_status(self, report: dict[str, object]) -> None:
        self.assertIn(report.get("status"), {"blocked", "blocked_by_environment"})

    def test_qualified_manifest_with_all_worker_required_lines_passes(self) -> None:
        root = self.make_repo()
        manifest = self.write_json(root, "qualified-manifest.json", self.manifest())

        exit_code, report, _ = self.run_checker(manifest)

        self.assertEqual(0, exit_code)
        self.assert_status(report, "passed")
        summary = self.summary(report)
        passed_line_keys = summary.get("qualified_line_keys", summary.get("passed_line_keys"))
        if isinstance(passed_line_keys, list):
            self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, passed_line_keys)
        self.assertEqual([], summary.get("missing_line_keys"))
        self.assertEqual([], summary.get("duplicate_line_keys"))
        self.assertEqual([], summary.get("synthetic_line_keys"))

    def test_synthetic_manifest_fails_and_reports_all_synthetic_lines(self) -> None:
        root = self.make_repo()
        lines = [
            self.line(
                "ingest",
                task_id="synthetic-task-ingest",
                run_id="fixture-run-ingest",
            ),
            self.line(
                "search_discovery_index",
                worker_name="celery@fake-search-discovery-index",
                trace_id="mock-trace-search-discovery-index",
            ),
            self.line(
                "resource_source_library",
                task_id="generated-task-resource-source-library",
            ),
            self.line(
                "writing_knowledge_graph_agent",
                trace_id="dummy-trace-writing-knowledge-graph-agent",
            ),
        ]
        marker_blob = json.dumps(
            {"manifest_kind": "synthetic_fixture_manifest", "lines": lines},
            sort_keys=True,
        )
        for marker in SYNTHETIC_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, marker_blob)
        manifest = self.write_json(
            root,
            "synthetic-manifest.json",
            self.manifest(lines=lines, manifest_kind="synthetic_fixture_manifest"),
        )

        exit_code, report, _ = self.run_checker(manifest)

        self.assertEqual(1, exit_code)
        self.assert_status(report, "failed")
        self.assertCountEqual(WORKER_REQUIRED_LINE_KEYS, self.summary(report).get("synthetic_line_keys"))

    def test_missing_worker_required_line_fails(self) -> None:
        root = self.make_repo()
        lines = [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS if key != "resource_source_library"]
        manifest = self.write_json(root, "missing-line.json", self.manifest(lines=lines))

        exit_code, report, _ = self.run_checker(manifest)

        self.assertEqual(1, exit_code)
        self.assert_status(report, "failed")
        self.assertIn("resource_source_library", self.summary(report).get("missing_line_keys"))

    def test_duplicate_worker_required_line_fails(self) -> None:
        root = self.make_repo()
        lines = [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS]
        lines.append(self.line("ingest", task_id="task-ingest-duplicate"))
        manifest = self.write_json(root, "duplicate-line.json", self.manifest(lines=lines))

        exit_code, report, _ = self.run_checker(manifest)

        self.assertEqual(1, exit_code)
        self.assert_status(report, "failed")
        self.assertIn("ingest", self.summary(report).get("duplicate_line_keys"))

    def test_missing_worker_name_or_queue_fails(self) -> None:
        cases = (
            ("missing-worker-name.json", "ingest", "worker_name"),
            ("missing-queue.json", "search_discovery_index", "queue"),
        )
        for filename, line_key, field in cases:
            with self.subTest(field=field):
                root = self.make_repo()
                lines = [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS]
                for row in lines:
                    if row["line_key"] == line_key:
                        row.pop(field)
                manifest = self.write_json(root, filename, self.manifest(lines=lines))

                exit_code, report, _ = self.run_checker(manifest)

                self.assertEqual(1, exit_code)
                self.assert_status(report, "failed")
                self.assert_line_failure(report, line_key, field)

    def test_task_id_or_run_id_allows_either_identifier_but_not_neither(self) -> None:
        allowed_cases = (
            ("missing-task-id.json", "resource_source_library", "task_id"),
            ("missing-run-id.json", "writing_knowledge_graph_agent", "run_id"),
        )
        for filename, line_key, field in allowed_cases:
            with self.subTest(field=field):
                root = self.make_repo()
                lines = [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS]
                for row in lines:
                    if row["line_key"] == line_key:
                        row.pop(field)
                manifest = self.write_json(root, filename, self.manifest(lines=lines))

                exit_code, report, _ = self.run_checker(manifest)

                self.assertEqual(0, exit_code)
                self.assert_status(report, "passed")

        root = self.make_repo()
        lines = [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS]
        for row in lines:
            if row["line_key"] == "resource_source_library":
                row.pop("task_id")
                row.pop("run_id")
        manifest = self.write_json(root, "missing-task-and-run-id.json", self.manifest(lines=lines))

        exit_code, report, _ = self.run_checker(manifest)

        self.assertEqual(1, exit_code)
        self.assert_status(report, "failed")
        self.assert_line_failure(report, "resource_source_library", "task_id_or_run_id")

    def test_missing_terminal_event_fails(self) -> None:
        root = self.make_repo()
        lines = [self.line(key) for key in WORKER_REQUIRED_LINE_KEYS]
        for row in lines:
            if row["line_key"] == "writing_knowledge_graph_agent":
                row["events"] = ["queued", "started"]
        manifest = self.write_json(root, "missing-terminal-event.json", self.manifest(lines=lines))

        exit_code, report, _ = self.run_checker(manifest)

        self.assertEqual(1, exit_code)
        self.assert_status(report, "failed")

    def test_missing_or_unreadable_manifest_is_blocked_and_allow_blocked_exits_zero(self) -> None:
        root = self.make_repo()
        missing_path = root / "missing-manifest.json"
        unreadable_path = root / "unreadable-manifest.json"
        unreadable_path.mkdir()

        for manifest_path in (missing_path, unreadable_path):
            with self.subTest(path=manifest_path.name):
                exit_code, report, _ = self.run_checker(manifest_path)

                self.assertEqual(1, exit_code)
                self.assert_blocked_status(report)

                allowed_exit_code, allowed_report, _ = self.run_checker(manifest_path, "--allow-blocked")

                self.assertEqual(0, allowed_exit_code)
                self.assert_blocked_status(allowed_report)


if __name__ == "__main__":
    unittest.main()
