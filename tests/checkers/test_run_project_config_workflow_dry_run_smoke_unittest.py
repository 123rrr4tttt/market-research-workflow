#!/usr/bin/env python3
"""Focused tests for project config workflow dry-run smoke artifact behavior."""

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


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_project_config_workflow_dry_run_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_project_config_workflow_dry_run_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class ProjectConfigWorkflowDryRunSmokeTestCase(unittest.TestCase):
    def make_output_path(self, name: str = "artifact.json") -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / name

    def http_result(self, status_code: int | None, payload: object | None = None, error: str | None = None) -> object:
        body = "" if payload is None else json.dumps(payload)
        return smoke.HttpResult(status_code=status_code, body=body, error=error)

    def envelope(self, data: dict[str, object]) -> object:
        return self.http_result(200, {"status": "ok", "data": data, "error": None, "meta": {}})

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = smoke.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def test_passed_project_config_workflow_dry_run_flow_writes_evidence(self) -> None:
        output = self.make_output_path()
        state = {"version": 4}

        def governance(operation: str, stage: str, dry_run: bool, will_mutate: bool, requires_publish: bool) -> dict[str, object]:
            return {
                "operation": operation,
                "stage": stage,
                "dry_run": dry_run,
                "will_mutate": will_mutate,
                "requires_publish": requires_publish,
            }

        def version_summary(
            stage: str,
            will_mutate: bool,
            requires_publish: bool,
            *,
            draft: int | None = None,
            staging: int | None = None,
            active: int | None = None,
        ) -> dict[str, object]:
            return {
                "stage": stage,
                "will_mutate": will_mutate,
                "requires_publish": requires_publish,
                "draft_version": draft,
                "staging_version": staging,
                "active_version": active,
            }

        def fake_get(url: str, *, timeout: float) -> object:
            if url == "http://127.0.0.1:8000/api/v1/projects":
                return self.envelope(
                    {
                        "items": [
                            {
                                "project_key": "demo_proj",
                                "enabled": True,
                                "schema_ready": True,
                            }
                        ]
                    }
                )
            if url.startswith("http://127.0.0.1:8000/api/v1/project-customization/workflows/demo/template/versions?"):
                return self.envelope(
                    {
                        "project_key": "demo_proj",
                        "workflow_name": "demo",
                        "current_version": state["version"],
                        "governance": governance("history", "history", True, False, False),
                        "items": [{"stage": "draft", "version": 5}],
                        "history": [{"action": "save_stage", "trace_id": "trace-draft"}],
                        "stage_summary": {
                            "has_draft": True,
                            "has_staging": False,
                            "has_active": False,
                            "draft_version": 5,
                            "staging_version": None,
                            "active_version": None,
                            "latest_audit": {"trace_id": "trace-draft"},
                        },
                    }
                )
            raise AssertionError(f"unexpected GET {url}")

        def fake_post(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith("/template/diff"):
                return self.envelope(
                    {
                        "project_key": "demo_proj",
                        "workflow_name": "demo",
                        "changed": True,
                        "reason_code": "workflow_template_steps_changed",
                        "current_version": state["version"],
                        "next_version": state["version"] + 1,
                        "governance": governance("snapshot", "draft_preview", True, False, True),
                        "version_summary": version_summary("draft_preview", False, True, draft=5, active=4),
                    }
                )
            if url.endswith("/template/stage"):
                self.assertEqual("draft", payload["stage"])
                current = state["version"]
                state["version"] += 1
                return self.envelope(
                    {
                        "project_key": "demo_proj",
                        "workflow_name": "demo",
                        "saved": True,
                        "stage": "draft",
                        "current_version": current,
                        "next_version": state["version"],
                        "governance": governance("stage", "draft", False, True, True),
                        "version_summary": version_summary("draft", True, True, draft=state["version"], active=current),
                        "audit": {"action": "save_stage", "trace_id": payload["trace_id"]},
                        "stage_record": {"stage": "draft", "version": state["version"]},
                    }
                )
            if url.endswith("/template/promote"):
                current = state["version"]
                state["version"] += 1
                to_stage = str(payload["to_stage"])
                requires_publish = to_stage != "active"
                return self.envelope(
                    {
                        "project_key": "demo_proj",
                        "workflow_name": "demo",
                        "promoted": True,
                        "from_stage": payload["from_stage"],
                        "to_stage": payload["to_stage"],
                        "current_version": current,
                        "next_version": state["version"],
                        "governance": governance("publish" if to_stage == "active" else "stage", to_stage, False, True, requires_publish),
                        "version_summary": version_summary(
                            to_stage,
                            True,
                            requires_publish,
                            draft=5,
                            staging=state["version"] if to_stage == "staging" else 6,
                            active=state["version"] if to_stage == "active" else current,
                        ),
                        "audit": {"action": "promote_stage", "trace_id": payload["trace_id"]},
                        "stage_record": {
                            "stage": payload["to_stage"],
                            "version": state["version"],
                            "promoted_from": payload["from_stage"],
                        },
                    }
                )
            if "/run?" in url:
                return self.envelope(
                    {
                        "project_key": "demo_proj",
                        "workflow_name": "demo",
                        "dry_run": True,
                        "status": "ok",
                        "reason_code": "workflow_ready",
                        "readiness": "ready",
                        "current_version": state["version"],
                        "config_version": state["version"],
                        "governance": governance("dry_run", "dry_run", True, False, False),
                        "impact_summary": {
                            "writes_blocked": True,
                            "runtime_tasks_blocked": True,
                            "policy_change": {"requires_publish": False, "will_mutate": False},
                        },
                    }
                )
            if url.endswith("/template/rollback/preview"):
                return self.envelope(
                    {
                        "project_key": "demo_proj",
                        "workflow_name": "demo",
                        "rollback_preview": True,
                        "current_version": state["version"],
                        "next_version": state["version"] + 1,
                        "governance": governance("rollback", "rollback_preview", True, False, True),
                        "rollback_plan": {
                            "will_mutate": False,
                            "can_execute": True,
                            "to_stage": "staging",
                            "target_version": payload["target_version"],
                        },
                        "version_summary": {
                            "stage": "rollback_preview",
                            "will_mutate": False,
                            "requires_publish": True,
                            "active_version": 7,
                            "staging_version": 6,
                            "target_version": payload["target_version"],
                        },
                    }
                )
            raise AssertionError(f"unexpected POST {url}")

        with (
            patch.object(smoke, "_http_get", side_effect=fake_get),
            patch.object(smoke, "_http_post_json", side_effect=fake_post),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--workflow",
                    "demo",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(smoke.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("passed", payload["status"])
        self.assertEqual([], payload["failures"])
        self.assertEqual(8, payload["summary"]["passed_step_count"])
        self.assertEqual(5, payload["summary"]["draft_version"])
        self.assertEqual(6, payload["summary"]["staging_version"])
        self.assertEqual(7, payload["summary"]["active_version"])
        self.assertTrue(payload["summary"]["workflow_dry_run_writes_blocked"])
        self.assertTrue(payload["summary"]["workflow_dry_run_runtime_tasks_blocked"])
        self.assertFalse(payload["summary"]["rollback_preview_will_mutate"])
        self.assertTrue(all("http_status" in step and isinstance(step.get("evidence"), dict) for step in payload["steps"]))

    def test_blocked_backend_unreachable_is_not_passed_without_allow_blocked(self) -> None:
        output = self.make_output_path()
        with patch.object(
            smoke,
            "_http_get",
            return_value=smoke.HttpResult(status_code=None, body="", error="connection refused"),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("blocked_by_environment", payload["steps"][0]["status"])
        self.assertIn("project_readback:backend_unreachable", payload["failures"])

        with patch.object(
            smoke,
            "_http_get",
            return_value=smoke.HttpResult(status_code=None, body="", error="connection refused"),
        ):
            allow_exit_code, allow_payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, allow_exit_code)
        self.assertEqual("blocked_by_environment", allow_payload["status"])

    def test_workflow_dry_run_without_write_blocking_fails(self) -> None:
        output = self.make_output_path()

        def fake_get(url: str, *, timeout: float) -> object:
            if "/template/versions" in url:
                return self.envelope(
                    {
                        "governance": {"dry_run": True, "will_mutate": False},
                        "items": [],
                        "history": [],
                        "stage_summary": {"has_draft": True, "draft_version": 2},
                    }
                )
            return self.envelope({"items": [{"project_key": "demo_proj", "enabled": True, "schema_ready": True}]})

        def fake_post(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith("/template/diff"):
                return self.envelope(
                    {
                        "current_version": 1,
                        "next_version": 2,
                        "governance": {"dry_run": True, "will_mutate": False, "requires_publish": True},
                        "version_summary": {"will_mutate": False, "requires_publish": True, "stage": "draft_preview"},
                    }
                )
            if url.endswith("/template/stage"):
                return self.envelope(
                    {
                        "stage": "draft",
                        "current_version": 1,
                        "next_version": 2,
                        "governance": {"will_mutate": True, "requires_publish": True},
                        "version_summary": {"requires_publish": True},
                        "stage_record": {"stage": "draft", "version": 2},
                    }
                )
            if url.endswith("/template/promote"):
                to_stage = str(payload["to_stage"])
                next_version = 3 if to_stage == "staging" else 4
                return self.envelope(
                    {
                        "from_stage": payload["from_stage"],
                        "to_stage": payload["to_stage"],
                        "current_version": next_version - 1,
                        "next_version": next_version,
                        "governance": {"will_mutate": True, "requires_publish": to_stage != "active"},
                        "version_summary": {"requires_publish": to_stage != "active"},
                    }
                )
            if "/run?" in url:
                return self.envelope(
                    {
                        "dry_run": True,
                        "governance": {"dry_run": True, "will_mutate": False, "requires_publish": False},
                        "impact_summary": {
                            "writes_blocked": False,
                            "runtime_tasks_blocked": True,
                            "policy_change": {"requires_publish": False},
                        },
                    }
                )
            raise AssertionError(f"unexpected POST {url}")

        with (
            patch.object(smoke, "_http_get", side_effect=fake_get),
            patch.object(smoke, "_http_post_json", side_effect=fake_post),
        ):
            exit_code, payload = self.run_main(["--output", str(output), "--json"])

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual("failed", payload["steps"][6]["status"])
        self.assertIn("workflow_dry_run:writes_blocked", payload["failures"])


if __name__ == "__main__":
    unittest.main()
