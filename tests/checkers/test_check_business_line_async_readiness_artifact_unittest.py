#!/usr/bin/env python3
"""Focused tests for business-line async readiness artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_async_readiness_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_business_line_async_readiness_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessLineAsyncReadinessCheckerTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def line(
        self,
        line_key: str,
        *,
        status: str = checker.STATUS_PASSED,
        requires_worker: bool = True,
        mocked: bool = False,
        skipped: bool = False,
    ) -> dict[str, object]:
        return {
            "line_key": line_key,
            "status": status,
            "requires_worker": requires_worker,
            "mocked": mocked,
            "skipped": skipped,
            "reason": "local_worker_readiness_passed"
            if requires_worker
            else "sync_or_read_only_async_not_required",
        }

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        non_worker = {"projects_config_workflow", "dashboard_admin_governance", "runtime_ops"}
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "lines": [
                self.line(line_key, requires_worker=line_key not in non_worker)
                for line_key in checker.REQUIRED_LINE_KEYS
            ],
        }

    def test_passed_artifact_with_all_seven_lines_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-readiness.json", self.payload())

        report = checker.build_report(artifact, root=root)

        self.assertEqual("business_line_async_readiness_check.v1", report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["artifact"]["summary"]["missing_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["blocked_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["failed_line_keys"])
        self.assertEqual(
            [
                "ingest",
                "resource_source_library",
                "search_discovery_index",
                "writing_knowledge_graph_agent",
            ],
            report["artifact"]["summary"]["requires_worker_line_keys"],
        )
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        for line in payload["lines"]:  # type: ignore[index]
            if line["requires_worker"]:  # type: ignore[index]
                line["status"] = checker.STATUS_BLOCKED  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-readiness-blocked.json", payload)

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
        artifact = self.write_json(root, "artifacts/async-readiness.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("runtime_ops", report["artifact"]["summary"]["missing_line_keys"])
        self.assertIn("missing_line_keys", report["artifact"]["structural_failures"])

    def test_unexpected_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("unexpected_line", requires_worker=False))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/async-readiness.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("unexpected_line", report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertIn("unexpected_line_keys", report["artifact"]["structural_failures"])

    def test_duplicate_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("ingest"))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/async-readiness.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertIn("duplicate_line_keys", report["artifact"]["structural_failures"])

    def test_requires_worker_failed_line_fails_even_when_blocked_is_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_PASSED)
        payload["lines"][0]["status"] = checker.STATUS_FAILED  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-readiness-failed-line.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["failed_line_keys"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))

    def test_non_worker_required_line_can_pass_without_worker_block(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        for line in payload["lines"]:  # type: ignore[index]
            if line["line_key"] == "runtime_ops":  # type: ignore[index]
                line["requires_worker"] = False  # type: ignore[index]
                line["status"] = checker.STATUS_PASSED  # type: ignore[index]
                line.pop("mocked", None)  # type: ignore[attr-defined]
                line.pop("skipped", None)  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/async-readiness.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("passed", report["status"])
        self.assertNotIn("runtime_ops", report["artifact"]["summary"]["incomplete_line_keys"])

    def test_requires_worker_missing_mocked_or_skipped_fields_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0].pop("mocked")  # type: ignore[index]
        payload["lines"][1].pop("skipped")  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/async-readiness.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertIn("search_discovery_index", report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertIn("line_async_readiness_fields", report["artifact"]["structural_failures"])

    def test_failed_artifact_fails_even_when_blocked_is_allowed(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/async-readiness-failed.json", self.payload(status=checker.STATUS_FAILED))

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("failed_artifact_status", report["artifact"]["structural_failures"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))


if __name__ == "__main__":
    unittest.main()
