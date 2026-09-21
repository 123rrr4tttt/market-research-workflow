#!/usr/bin/env python3
"""Unit tests for the business-line worker readback project matrix automation spec checker."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "check_business_line_worker_readback_project_matrix_automation_spec.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_business_line_worker_readback_project_matrix_automation_spec",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


RUN_DATE = "2026-05-25"


class BusinessLineWorkerReadbackProjectMatrixAutomationSpecTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        (root / checker.EXPECTED_OWNER_SURFACE).mkdir(parents=True)
        (root / "scripts").mkdir()
        self.write_executable(
            root / checker.EXPECTED_WRAPPER,
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -e",
                    "echo 'DRY-RUN repo_root='\"$(pwd)\"",
                    "echo 'DRY-RUN matrix_report=artifact.json'",
                    "echo 'DRY-RUN manifest=nightly-manifest.json'",
                    "echo 'DRY-RUN history=trend-history.jsonl'",
                    "echo 'DRY-RUN matrix_cmd=python3 scripts/run_business_line_worker_readback_project_matrix.py'",
                    "echo 'DRY-RUN ensure_local_runtime=1'",
                    "echo 'DRY-RUN runtime_preflight_timeout=8'",
                ]
            )
            + "\n",
        )
        (root / checker.EXPECTED_RUNNER).write_text("# runner placeholder\n", encoding="utf-8")
        (root / checker.EXPECTED_SCHEDULED_CHECKER).write_text("# scheduled checker placeholder\n", encoding="utf-8")
        (root / checker.EXPECTED_CHECKER).write_text("# automation checker placeholder\n", encoding="utf-8")
        return root

    def write_executable(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def base_spec(self) -> dict[str, Any]:
        return {
            "schema_version": checker.EXPECTED_SCHEMA,
            "automation_id": checker.EXPECTED_AUTOMATION_ID,
            "name": "Business Line Worker Readback Project Matrix Nightly",
            "install_status": "repo_spec_only_not_installed",
            "owner_surface": checker.EXPECTED_OWNER_SURFACE,
            "schedule": {
                "timezone": "UTC",
                "rrule": "FREQ=HOURLY;INTERVAL=24",
                "cron": "codex_app_interval_24h",
                "cadence": "daily_via_24h_interval",
            },
            "cwd": ".",
            "command": {
                "shell": "bash",
                "env": {"MRW_SCHEDULED_RUN_EVIDENCE": "true"},
                "args": [checker.EXPECTED_WRAPPER, "--trigger-smoke", "--ensure-local-runtime"],
            },
            "dry_run": {
                "shell": "bash",
                "args": [checker.EXPECTED_WRAPPER, "--date", "{run_date}", "--dry-run"],
                "expected_stdout_markers": sorted(checker.DRY_RUN_REQUIRED_MARKERS),
            },
            "outputs": {
                "base_dir": checker.EXPECTED_OWNER_SURFACE,
                "dated_dir": f"{checker.EXPECTED_OWNER_SURFACE}/{{run_date}}",
                "artifact": f"{checker.EXPECTED_OWNER_SURFACE}/{{run_date}}/{checker.EXPECTED_ARTIFACT_NAME}",
                "manifest": f"{checker.EXPECTED_OWNER_SURFACE}/{{run_date}}/nightly-manifest.json",
                "history": f"{checker.EXPECTED_OWNER_SURFACE}/trend-history.jsonl",
            },
            "artifact_paths": [
                f"{checker.EXPECTED_OWNER_SURFACE}/{{run_date}}/{checker.EXPECTED_ARTIFACT_NAME}",
                f"{checker.EXPECTED_OWNER_SURFACE}/{{run_date}}/nightly-manifest.json",
                f"{checker.EXPECTED_OWNER_SURFACE}/trend-history.jsonl",
            ],
            "success_gates": [
                {"name": "wrapper_syntax", "command": f"bash -n {checker.EXPECTED_WRAPPER}"},
                {
                    "name": "wrapper_dry_run_plan",
                    "command": f"bash {checker.EXPECTED_WRAPPER} --date {{run_date}} --dry-run",
                },
                {
                    "name": "runtime_preflight_contract",
                    "command": f"bash {checker.EXPECTED_WRAPPER} --date {{run_date}} --dry-run --ensure-local-runtime",
                },
                {"name": "runner_syntax", "command": f"python3 -m py_compile {checker.EXPECTED_RUNNER}"},
                {
                    "name": "scheduled_evidence_boundary",
                    "command": f"python3 {checker.EXPECTED_SCHEDULED_CHECKER} --json --allow-missing",
                },
                {
                    "name": "automation_spec",
                    "command": (
                        f"python3 {checker.EXPECTED_CHECKER} "
                        "development/latest-dev-docs/automation-runs/"
                        "business-line-worker-readback-project-matrix/automation-spec.json "
                        "--run-date {run_date}"
                    ),
                },
            ],
            "failure_policy": {
                "wrapper_failure": "fail_run",
                "runner_failure": "fail_run",
                "manifest_failure": "fail_run",
                "retry": {"max_attempts": 1},
            },
        }

    def validate_in_repo(
        self,
        root: Path,
        spec: dict[str, Any],
        *,
        execute: bool = False,
    ) -> list[str]:
        with patch.object(checker, "repo_root", return_value=root):
            return checker.validate(copy.deepcopy(spec), RUN_DATE, execute=execute)

    def test_valid_repo_spec_passes(self) -> None:
        root = self.make_repo()

        problems = self.validate_in_repo(root, self.base_spec(), execute=True)

        self.assertEqual([], problems)

    def test_missing_wrapper_and_dry_run_marker_fail(self) -> None:
        root = self.make_repo()
        os.remove(root / checker.EXPECTED_WRAPPER)
        spec = self.base_spec()
        spec["dry_run"]["expected_stdout_markers"].remove("DRY-RUN matrix_cmd=")

        problems = self.validate_in_repo(root, spec)

        self.assertTrue(any("script does not exist" in problem for problem in problems), problems)
        self.assertTrue(any("DRY-RUN matrix_cmd=" in problem for problem in problems), problems)

    def test_installed_codex_app_config_mismatch_fails(self) -> None:
        root = self.make_repo()
        config_path = root / "automation.toml"
        config_path.write_text(
            "\n".join(
                [
                    'id = "wrong-id"',
                    'status = "PAUSED"',
                    'rrule = "FREQ=DAILY"',
                    'cwds = ["/tmp/not-this-repo"]',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        spec = self.base_spec()
        spec["install_status"] = "installed_codex_app"
        spec["codex_app"] = {
            "automation_id": "mrw-business-line-worker-readback-project-matrix-nightly",
            "config_path": str(config_path),
            "status": "ACTIVE",
            "rrule": "FREQ=HOURLY;INTERVAL=24",
            "cwd": str(root),
        }

        problems = self.validate_in_repo(root, spec)

        self.assertTrue(any("automation id mismatch" in problem for problem in problems), problems)
        self.assertTrue(any("status mismatch" in problem for problem in problems), problems)
        self.assertTrue(any("rrule mismatch" in problem for problem in problems), problems)
        self.assertTrue(any("cwd missing" in problem for problem in problems), problems)

    def test_installed_codex_app_config_valid_passes(self) -> None:
        root = self.make_repo()
        config_path = root / "automation.toml"
        automation_id = "mrw-business-line-worker-readback-project-matrix-nightly"
        config_path.write_text(
            "\n".join(
                [
                    f'id = "{automation_id}"',
                    'status = "ACTIVE"',
                    'rrule = "FREQ=HOURLY;INTERVAL=24"',
                    f'cwds = ["{root}"]',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        spec = self.base_spec()
        spec["install_status"] = "installed_codex_app"
        spec["codex_app"] = {
            "automation_id": automation_id,
            "config_path": str(config_path),
            "status": "ACTIVE",
            "rrule": "FREQ=HOURLY;INTERVAL=24",
            "cwd": str(root),
        }

        problems = self.validate_in_repo(root, spec)

        self.assertEqual([], problems)


if __name__ == "__main__":
    unittest.main()
