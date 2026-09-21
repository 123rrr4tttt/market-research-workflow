#!/usr/bin/env python3
"""Focused tests for project config workflow dry-run smoke artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_project_config_workflow_dry_run_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_project_config_workflow_dry_run_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class ProjectConfigWorkflowDryRunArtifactTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        steps = [
            {
                "name": "config_readback",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {"project_key": "demo_proj", "workflow": "demo", "workflow_present": True},
            },
            {
                "name": "template_diff_preview",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "governance_requires_publish": True,
                    "version_summary_requires_publish": True,
                    "current_version": 4,
                    "next_version": 5,
                },
            },
            {
                "name": "stage_draft",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "stage": "draft",
                    "governance_will_mutate": True,
                    "governance_requires_publish": True,
                    "version_summary_requires_publish": True,
                    "current_version": 4,
                    "next_version": 5,
                },
            },
            {
                "name": "versions_after_draft",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "has_draft": True,
                    "draft_version": 5,
                },
            },
            {
                "name": "promote_to_staging",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "from_stage": "draft",
                    "to_stage": "staging",
                    "governance_will_mutate": True,
                    "governance_requires_publish": True,
                    "version_summary_requires_publish": True,
                    "current_version": 5,
                    "next_version": 6,
                },
            },
            {
                "name": "promote_to_active",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "from_stage": "staging",
                    "to_stage": "active",
                    "governance_will_mutate": True,
                    "governance_requires_publish": False,
                    "version_summary_requires_publish": False,
                    "current_version": 6,
                    "next_version": 7,
                },
            },
            {
                "name": "workflow_dry_run",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "dry_run": True,
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "governance_requires_publish": False,
                    "writes_blocked": True,
                    "runtime_tasks_blocked": True,
                    "policy_requires_publish": False,
                },
            },
            {
                "name": "rollback_preview",
                "status": checker.STATUS_PASSED,
                "http_status": 200,
                "evidence": {
                    "rollback_preview": True,
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "rollback_plan_will_mutate": False,
                    "version_summary_will_mutate": False,
                },
            },
        ]
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "generated_at": "2026-05-25T00:00:00Z",
            "api_base": "http://127.0.0.1:8000",
            "project_key": "demo_proj",
            "workflow": "demo",
            "smoke_id": "project-config-workflow-dry-run-test",
            "steps": steps,
            "failures": [],
            "summary": {
                "draft_version": 5,
                "staging_version": 6,
                "active_version": 7,
                "workflow_dry_run_writes_blocked": True,
                "workflow_dry_run_runtime_tasks_blocked": True,
                "rollback_preview_will_mutate": False,
            },
        }

    def test_passed_artifact_with_required_workflow_evidence_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/project-config-workflow-dry-run.json", self.payload())

        report = checker.build_report(artifact, root=root)

        self.assertEqual(checker.CHECK_SCHEMA_VERSION, report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual(5, report["evidence"]["draft_version"])
        self.assertEqual(6, report["evidence"]["staging_version"])
        self.assertEqual(7, report["evidence"]["active_version"])
        self.assertTrue(report["evidence"]["workflow_dry_run_writes_blocked"])
        self.assertTrue(report["evidence"]["workflow_dry_run_runtime_tasks_blocked"])
        self.assertFalse(report["evidence"]["rollback_preview_will_mutate"])
        self.assertEqual([], report["artifact"]["summary"]["missing_steps"])
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["steps"] = [
            {
                "name": "config_readback",
                "status": checker.STATUS_BLOCKED,
                "http_status": None,
                "reason": "backend_unreachable",
                "evidence": {"backend_unreachable": True, "error": "connection refused"},
            }
        ]
        payload["failures"] = ["config_readback:backend_unreachable"]
        artifact = self.write_json(root, "artifacts/project-config-workflow-dry-run.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(["config_readback"], report["artifact"]["summary"]["blocked_steps"])
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))

    def test_workflow_dry_run_without_runtime_blocking_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][6]["evidence"]["runtime_tasks_blocked"] = False  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/project-config-workflow-dry-run.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("workflow_dry_run.runtime_tasks_blocked", report["failures"])

    def test_rollback_preview_mutation_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][7]["evidence"]["rollback_plan_will_mutate"] = True  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/project-config-workflow-dry-run.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("rollback_preview.rollback_plan_will_mutate", report["failures"])

    def test_non_increasing_stage_versions_fail(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][5]["evidence"]["next_version"] = 6  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/project-config-workflow-dry-run.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("version_progression.staging_to_active", report["failures"])

    def test_missing_http_status_or_evidence_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["steps"][1]["http_status"]  # type: ignore[index]
        del payload["steps"][2]["evidence"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/project-config-workflow-dry-run.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("template_diff_preview.http_status", report["failures"])
        self.assertIn("stage_draft.evidence", report["failures"])


if __name__ == "__main__":
    unittest.main()
