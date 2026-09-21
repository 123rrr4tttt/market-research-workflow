#!/usr/bin/env python3
"""Focused tests for resource source lifecycle smoke artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_resource_source_lifecycle_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_resource_source_lifecycle_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class ResourceSourceLifecycleArtifactTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def guard(self, *, status: str = "passed") -> dict[str, object]:
        blocked = status == "blocked"
        return {
            "contract_version": "resource_pool.site_entry.single_source_guard.v1",
            "strict_source": True,
            "guarantee": not blocked,
            "status": status,
            "reason_code": None if not blocked else "review_rejected",
            "allowed_urls": ["https://example.com/source.xml"],
            "allowed_count": 1,
            "blocked_reason": None if not blocked else "review_rejected",
            "source_ref": {"site_entry_url": "https://example.com/source.xml"},
            "report_source_ref": "resource_pool.site_entry:project:10",
        }

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        accepted_guard = self.guard(status="passed")
        blocked_guard = self.guard(status="blocked")
        steps = [
            {"name": "create_site_entry", "status": checker.STATUS_PASSED, "http_status": 200},
            {"name": "readback_site_entry", "status": checker.STATUS_PASSED, "http_status": 200, "matched": True},
            {
                "name": "accept_lifecycle",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "lifecycle_state": "accepted",
                    "review_closure_status": "ready_to_collect",
                    "next_action": "collect_source_library_run",
                    "next_action_enabled": True,
                    "report_source_ref": "resource_pool.site_entry:project:10",
                    "single_source_guard": accepted_guard,
                },
            },
            {
                "name": "source_library_run",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "task_id": "source-library-task-1",
                    "terminal_status": None,
                    "trace_id": "trace-1",
                    "submission_id": "submission-1",
                },
            },
            {
                "name": "reject_lifecycle",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "lifecycle_state": "rejected",
                    "review_closure_status": "blocked",
                    "next_action": "collect_source_library_run",
                    "next_action_enabled": False,
                    "next_action_blocked": True,
                    "block_reason": "review_rejected",
                    "single_source_guard": blocked_guard,
                },
            },
        ]
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "generated_at": "2026-05-25T00:00:00Z",
            "api_base": "http://127.0.0.1:8000",
            "project_key": "demo_proj",
            "site_entry_url": "https://example.com/source.xml",
            "steps": steps,
            "failures": [],
            "summary": {
                "accepted_guard_status": "passed",
                "blocked_review_status": "blocked",
                "run_task_id": "source-library-task-1",
            },
        }

    def test_passed_artifact_with_guard_blocked_review_and_task_evidence_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/resource-source-lifecycle.json", self.payload())

        report = checker.build_report(artifact, root=root)

        self.assertEqual(checker.CHECK_SCHEMA_VERSION, report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual("passed", report["evidence"]["accepted_guard_status"])
        self.assertEqual("blocked", report["evidence"]["blocked_review_status"])
        self.assertEqual("source-library-task-1", report["evidence"]["task_id"])
        self.assertEqual([], report["artifact"]["summary"]["missing_steps"])
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["steps"] = [
            {
                "name": "create_site_entry",
                "status": checker.STATUS_BLOCKED,
                "http_status": None,
                "reason": "backend_unreachable",
            }
        ]
        payload["failures"] = ["create_site_entry:backend_unreachable"]
        artifact = self.write_json(root, "artifacts/resource-source-lifecycle.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(["create_site_entry"], report["artifact"]["summary"]["blocked_steps"])
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))

    def test_missing_accepted_guard_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][2]["evidence"]["single_source_guard"] = {}  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/resource-source-lifecycle.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("accept_lifecycle.single_source_guard.status", report["failures"])
        self.assertIn("accept_lifecycle.single_source_guard.strict_source", report["failures"])

    def test_blocked_without_environment_evidence_fails_even_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["steps"] = [
            {
                "name": "create_site_entry",
                "status": checker.STATUS_BLOCKED,
                "http_status": 409,
                "reason": "http_error",
            }
        ]
        payload["failures"] = ["create_site_entry:http_409"]
        artifact = self.write_json(root, "artifacts/resource-source-lifecycle.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("blocked_without_environment_evidence", report["failures"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))

    def test_missing_blocked_review_fields_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][4]["evidence"]["review_closure_status"] = "ready_to_collect"  # type: ignore[index]
        payload["steps"][4]["evidence"]["next_action_enabled"] = True  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/resource-source-lifecycle.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("reject_lifecycle.review_closure_status", report["failures"])
        self.assertIn("reject_lifecycle.next_action_blocked", report["failures"])

    def test_missing_run_task_terminal_or_trace_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][3]["evidence"] = {"task_id": None, "terminal_status": None, "trace_id": None}  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/resource-source-lifecycle.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("source_library_run.task_or_terminal_or_trace", report["failures"])


if __name__ == "__main__":
    unittest.main()
