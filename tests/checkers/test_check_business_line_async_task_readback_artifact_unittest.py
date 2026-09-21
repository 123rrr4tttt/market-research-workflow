#!/usr/bin/env python3
"""Focused tests for business-line async task readback artifact checks."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_async_task_readback_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_business_line_async_task_readback_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessLineAsyncTaskReadbackCheckerTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def sample(self, line_key: str, *, mocked: bool = False, skipped: bool = False) -> dict[str, object]:
        return {
            "line_key": line_key,
            "task_id": f"task-{line_key}",
            "run_id": f"run-{line_key}",
            "status": "completed",
            "events": ["queued", "started", "completed"],
            "worker_name": "celery@local",
            "queue": "default",
            "trace_id": f"trace-{line_key}",
            "readback_path": f"artifacts/{line_key}/task-readback.json",
            "readback_endpoint": f"/api/v1/{line_key}/tasks/task-{line_key}",
            "mocked": mocked,
            "skipped": skipped,
        }

    def manifest_sample(self, line_key: str, **overrides: object) -> dict[str, object]:
        sample = self.sample(line_key)
        sample.pop("mocked")
        sample.pop("skipped")
        sample.update(overrides)
        return sample

    def manifest_payload(self, *, lines: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "schema_version": "business_line_task_readback_manifest.v1",
            "manifest_kind": "business_line_task_readback",
            "status": checker.STATUS_PASSED,
            "lines": lines
            if lines is not None
            else [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS],
        }

    def write_manifest(
        self,
        root: Path,
        rel_path: str = "artifacts/task-readback-manifest.json",
        *,
        lines: list[dict[str, object]] | None = None,
    ) -> Path:
        return self.write_json(root, rel_path, self.manifest_payload(lines=lines))

    def line(
        self,
        line_key: str,
        *,
        status: str = checker.STATUS_PASSED,
        requires_worker_readback: bool = True,
        mocked: bool = False,
        skipped: bool = False,
    ) -> dict[str, object]:
        return {
            "line_key": line_key,
            "status": status,
            "requires_worker_readback": requires_worker_readback,
            "mocked": mocked,
            "skipped": skipped,
            "reason": "async_task_readback_completed"
            if requires_worker_readback
            else "process_config_audit_readback_completed",
            "required_events": ["queued", "started", "completed"] if requires_worker_readback else [],
            "samples": [self.sample(line_key)],
        }

    def run_checker_json(self, artifact: Path, *extra_args: str) -> dict[str, object]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = checker.main([str(artifact), *extra_args, "--json"])
        try:
            report = json.loads(stdout.getvalue())
        except json.JSONDecodeError as exc:
            self.fail(f"checker --json output must be valid JSON: {stdout.getvalue()!r}; error={exc}")
        report["_exit_code"] = exit_code
        return report

    def assert_worker_contract_failure(
        self,
        report: dict[str, object],
        line_key: str,
        structural_failure: str,
        summary_key: str,
    ) -> None:
        artifact = report["artifact"]  # type: ignore[index]
        summary = artifact["summary"]  # type: ignore[index]
        self.assertEqual("failed", report["status"])
        self.assertIn(line_key, summary["incomplete_line_keys"])  # type: ignore[index]
        self.assertIn(line_key, summary[summary_key])  # type: ignore[index]
        self.assertIn(structural_failure, artifact["structural_failures"])  # type: ignore[index]

    def assert_manifest_contract_failure(
        self,
        report: dict[str, object],
        line_key: str,
        structural_failure: str,
        summary_key: str,
    ) -> None:
        artifact = report["artifact"]  # type: ignore[index]
        summary = artifact["summary"]  # type: ignore[index]
        self.assertEqual(1, report["_exit_code"])
        self.assertEqual("failed", report["status"])
        self.assertIn(line_key, summary[summary_key])  # type: ignore[index]
        self.assertIn(line_key, summary["incomplete_line_keys"])  # type: ignore[index]
        self.assertIn(structural_failure, artifact["structural_failures"])  # type: ignore[index]

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        non_worker = {"projects_config_workflow", "dashboard_admin_governance", "runtime_ops"}
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "lines": [
                self.line(line_key, requires_worker_readback=line_key not in non_worker)
                for line_key in checker.REQUIRED_LINE_KEYS
            ],
        }

    def test_task_readback_manifest_matching_worker_required_samples_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        manifest = self.write_manifest(root)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assertEqual(0, report["_exit_code"])
        self.assertEqual("passed", report["status"])
        summary = report["artifact"]["summary"]  # type: ignore[index]
        self.assertEqual([], summary["manifest_missing_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_identity_mismatch_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_worker_name_mismatch_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_queue_mismatch_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_trace_mismatch_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_readback_location_mismatch_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_status_mismatch_line_keys"])  # type: ignore[index]
        self.assertEqual([], summary["manifest_events_mismatch_line_keys"])  # type: ignore[index]

    def test_task_readback_manifest_identity_mismatch_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
        lines[0]["task_id"] = "wrong-task-ingest"
        lines[0]["run_id"] = "wrong-run-ingest"
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "ingest",
            "task_readback_manifest_identity_mismatch",
            "manifest_identity_mismatch_line_keys",
        )

    def test_task_readback_manifest_worker_name_mismatch_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
        lines[0]["worker_name"] = "celery@wrong-worker"
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "ingest",
            "task_readback_manifest_worker_name_mismatch",
            "manifest_worker_name_mismatch_line_keys",
        )

    def test_task_readback_manifest_queue_mismatch_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
        lines[0]["queue"] = "wrong.queue"
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "ingest",
            "task_readback_manifest_queue_mismatch",
            "manifest_queue_mismatch_line_keys",
        )

    def test_task_readback_manifest_trace_mismatch_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
        lines[0]["trace_id"] = "wrong-trace-ingest"
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "ingest",
            "task_readback_manifest_trace_mismatch",
            "manifest_trace_mismatch_line_keys",
        )

    def test_task_readback_manifest_readback_location_mismatch_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
        lines[0]["readback_path"] = "artifacts/wrong/task-readback.json"
        lines[0]["readback_endpoint"] = "/api/v1/wrong/tasks/wrong-task"
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "ingest",
            "task_readback_manifest_readback_location_mismatch",
            "manifest_readback_location_mismatch_line_keys",
        )

    def test_task_readback_manifest_status_mismatch_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
        lines[0]["status"] = "succeeded"
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "ingest",
            "task_readback_manifest_status_mismatch",
            "manifest_status_mismatch_line_keys",
        )

    def test_task_readback_manifest_events_missing_or_mismatch_fails(self) -> None:
        cases = (
            ("missing-started", ["queued", "completed"]),
            ("wrong-terminal", ["queued", "started", "succeeded"]),
        )
        for name, events in cases:
            with self.subTest(name=name):
                root = self.make_repo()
                artifact = self.write_json(root, f"artifacts/{name}/async-task-readback.json", self.payload())
                lines = [self.manifest_sample(line_key) for line_key in checker.WORKER_REQUIRED_LINE_KEYS]
                lines[0]["events"] = events
                manifest = self.write_manifest(root, f"artifacts/{name}/task-readback-manifest.json", lines=lines)

                report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

                self.assert_manifest_contract_failure(
                    report,
                    "ingest",
                    "task_readback_manifest_events_mismatch",
                    "manifest_events_mismatch_line_keys",
                )

    def test_task_readback_manifest_missing_worker_required_line_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())
        lines = [
            self.manifest_sample(line_key)
            for line_key in checker.WORKER_REQUIRED_LINE_KEYS
            if line_key != "resource_source_library"
        ]
        manifest = self.write_manifest(root, lines=lines)

        report = self.run_checker_json(artifact, "--task-readback-manifest", str(manifest))

        self.assert_manifest_contract_failure(
            report,
            "resource_source_library",
            "task_readback_manifest_missing_line",
            "manifest_missing_line_keys",
        )

    def test_passed_artifact_with_all_seven_lines_and_terminal_samples_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback.json", self.payload())

        report = checker.build_report(artifact, root=root)

        self.assertEqual("business_line_async_task_readback_check.v1", report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["artifact"]["summary"]["missing_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["blocked_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["failed_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["terminal_evidence_missing_line_keys"])
        self.assertEqual(
            [
                "ingest",
                "resource_source_library",
                "search_discovery_index",
                "writing_knowledge_graph_agent",
            ],
            report["artifact"]["summary"]["requires_worker_readback_line_keys"],
        )
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        for line in payload["lines"]:  # type: ignore[index]
            if line["requires_worker_readback"]:  # type: ignore[index]
                line["status"] = checker.STATUS_BLOCKED  # type: ignore[index]
                line["samples"] = []  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback-blocked.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(
            [
                "ingest",
                "resource_source_library",
                "search_discovery_index",
                "writing_knowledge_graph_agent",
            ],
            report["artifact"]["summary"]["blocked_line_keys"],
        )
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))

    def test_missing_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"] = [
            line for line in payload["lines"] if line["line_key"] != "runtime_ops"  # type: ignore[index]
        ]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("runtime_ops", report["artifact"]["summary"]["missing_line_keys"])
        self.assertIn("missing_line_keys", report["artifact"]["structural_failures"])

    def test_duplicate_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("ingest"))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertIn("duplicate_line_keys", report["artifact"]["structural_failures"])

    def test_unexpected_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("unexpected_line", requires_worker_readback=False))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("unexpected_line", report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertIn("unexpected_line_keys", report["artifact"]["structural_failures"])

    def test_mocked_or_skipped_lines_fail(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["mocked"] = True  # type: ignore[index]
        payload["lines"][1]["skipped"] = True  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["mocked_or_skipped_line_keys"])
        self.assertIn("search_discovery_index", report["artifact"]["summary"]["mocked_or_skipped_line_keys"])
        self.assertIn("line_mocked_or_skipped_fields", report["artifact"]["structural_failures"])

    def test_mocked_or_skipped_samples_fail(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["samples"][0]["mocked"] = True  # type: ignore[index]
        payload["lines"][1]["samples"][0]["skipped"] = True  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertIn("search_discovery_index", report["artifact"]["summary"]["incomplete_line_keys"])

    def test_passed_worker_required_line_without_terminal_sample_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["samples"][0]["status"] = "started"  # type: ignore[index]
        payload["lines"][0]["samples"][0]["events"] = ["queued", "started"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["terminal_evidence_missing_line_keys"])
        self.assertIn("terminal_task_readback_evidence", report["artifact"]["structural_failures"])

    def test_passed_worker_required_line_without_worker_name_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["lines"][0]["samples"][0]["worker_name"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(
            report,
            "ingest",
            "worker_readback_worker_name",
            "worker_name_missing_line_keys",
        )

    def test_passed_worker_required_line_without_queue_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["lines"][0]["samples"][0]["queue"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(report, "ingest", "worker_readback_queue", "worker_queue_missing_line_keys")

    def test_passed_worker_required_line_without_trace_id_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["lines"][0]["samples"][0]["trace_id"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(report, "ingest", "worker_readback_trace_id", "worker_trace_missing_line_keys")

    def test_passed_worker_required_line_without_task_or_run_id_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["lines"][0]["samples"][0]["task_id"]  # type: ignore[index]
        del payload["lines"][0]["samples"][0]["run_id"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(
            report,
            "ingest",
            "worker_readback_identity",
            "worker_identity_missing_line_keys",
        )

    def test_passed_worker_required_line_without_readback_location_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["lines"][0]["samples"][0]["readback_path"]  # type: ignore[index]
        del payload["lines"][0]["samples"][0]["readback_endpoint"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(
            report,
            "ingest",
            "worker_readback_location",
            "worker_readback_location_missing_line_keys",
        )

    def test_passed_worker_required_line_without_required_event_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["samples"][0]["events"] = ["queued", "completed"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(
            report,
            "ingest",
            "worker_readback_required_events",
            "required_events_missing_line_keys",
        )

    def test_canonical_worker_required_line_cannot_disable_worker_readback(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["requires_worker_readback"] = False  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["worker_required_flag_mismatch_line_keys"])
        self.assertIn("worker_required_flag_mismatch", report["artifact"]["structural_failures"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])

    def test_passed_worker_required_line_without_declared_required_events_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["required_events"] = []  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assert_worker_contract_failure(
            report,
            "ingest",
            "worker_readback_required_events",
            "required_events_missing_line_keys",
        )

    def test_worker_required_line_cannot_weaken_success_terminal_states(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["success_terminal_states"] = ["started"]  # type: ignore[index]
        payload["lines"][0]["samples"][0]["status"] = "started"  # type: ignore[index]
        payload["lines"][0]["samples"][0]["events"] = ["queued", "started"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["terminal_evidence_missing_line_keys"])
        self.assertIn("terminal_task_readback_evidence", report["artifact"]["structural_failures"])

    def test_passed_non_worker_line_does_not_require_worker_readback_fields(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        for line in payload["lines"]:  # type: ignore[index]
            if line["line_key"] == "runtime_ops":  # type: ignore[index]
                del line["samples"][0]["worker_name"]  # type: ignore[index]
                del line["samples"][0]["queue"]  # type: ignore[index]
                del line["samples"][0]["trace_id"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertNotIn("worker_readback_worker_name", report["artifact"]["structural_failures"])
        self.assertNotIn("worker_readback_queue", report["artifact"]["structural_failures"])
        self.assertNotIn("worker_readback_trace_id", report["artifact"]["structural_failures"])

    def test_blocked_worker_required_line_without_samples_keeps_blocked_semantics(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        for line in payload["lines"]:  # type: ignore[index]
            if line["line_key"] == "ingest":  # type: ignore[index]
                line["status"] = checker.STATUS_BLOCKED  # type: ignore[index]
                line["samples"] = []  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback-blocked.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("blocked_by_environment", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["blocked_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertNotIn("worker_readback_identity", report["artifact"]["structural_failures"])
        self.assertNotIn("worker_readback_worker_name", report["artifact"]["structural_failures"])
        self.assertNotIn("worker_readback_queue", report["artifact"]["structural_failures"])
        self.assertNotIn("worker_readback_trace_id", report["artifact"]["structural_failures"])

    def test_passed_non_worker_line_without_terminal_sample_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        for line in payload["lines"]:  # type: ignore[index]
            if line["line_key"] == "runtime_ops":  # type: ignore[index]
                line["samples"] = []  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-task-readback.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("runtime_ops", report["artifact"]["summary"]["terminal_evidence_missing_line_keys"])
        self.assertIn("runtime_ops", report["artifact"]["summary"]["sample_missing_line_keys"])
        self.assertIn("readback_sample_required", report["artifact"]["structural_failures"])

    def test_failed_artifact_fails_even_when_blocked_is_allowed(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-task-readback-failed.json", self.payload(status=checker.STATUS_FAILED))

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("failed_artifact_status", report["artifact"]["structural_failures"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))


if __name__ == "__main__":
    unittest.main()
