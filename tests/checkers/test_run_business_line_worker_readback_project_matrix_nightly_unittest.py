#!/usr/bin/env python3
"""Unit tests for the business-line worker readback project matrix nightly wrapper."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER_PATH = REPO_ROOT / "scripts" / "run_business_line_worker_readback_project_matrix_nightly.sh"
MATRIX_REPORT_NAME = "business-line-worker-readback-project-matrix-report.json"


class BusinessLineWorkerReadbackProjectMatrixNightlyTestCase(unittest.TestCase):
    def make_temp_dir(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def clean_env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        for key in ("CODEX_AUTOMATION_ID", "CODEX_AUTOMATION_RUN_ID", "MRW_SCHEDULED_RUN_EVIDENCE"):
            env.pop(key, None)
        env.update(extra)
        return env

    def run_wrapper(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["bash", str(WRAPPER_PATH), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            env=env or self.clean_env(),
            check=False,
        )
        if check and completed.returncode != 0:
            self.fail(
                f"wrapper exited {completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return completed

    def dry_run_markers(self, output: str) -> dict[str, str]:
        markers: dict[str, str] = {}
        for line in output.splitlines():
            if not line.startswith("DRY-RUN "):
                continue
            key, value = line[len("DRY-RUN ") :].split("=", 1)
            markers[key] = value
        return markers

    def make_fake_runner(self, temp_dir: Path) -> Path:
        fake_runner = temp_dir / "fake_matrix_runner.py"
        fake_runner.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                from __future__ import annotations

                import argparse
                import json
                import os
                from pathlib import Path


                parser = argparse.ArgumentParser()
                parser.add_argument("--api-base", required=True)
                parser.add_argument("--projects-api-url", required=True)
                parser.add_argument("--project-key-regex")
                parser.add_argument("--artifact-dir", required=True)
                parser.add_argument("--timeout", required=True)
                parser.add_argument("--json", action="store_true")
                parser.add_argument("--exclude-project-key", action="append", default=[])
                parser.add_argument("--max-projects", type=int)
                parser.add_argument("--trigger-smoke", action="store_true")
                parser.add_argument("--allow-blocked", action="store_true")
                args = parser.parse_args()

                status = os.environ.get("FAKE_MATRIX_STATUS", "passed")
                if status == "failed":
                    projects = [
                        {{
                            "project_key": "demo_proj",
                            "status": "failed",
                            "reason": "worker_readback_failed",
                            "stopped_at": "worker_readback",
                            "exit_code": 1,
                            "trigger_smoke_status": "failed",
                        }},
                        {{
                            "project_key": "blocked_proj",
                            "status": "blocked_by_environment",
                            "reason": "backend_unavailable",
                            "stopped_at": "runtime_preflight",
                            "exit_code": 124,
                            "trigger_smoke_status": "skipped",
                        }},
                    ]
                elif status == "blocked_by_environment":
                    projects = [
                        {{
                            "project_key": "demo_proj",
                            "status": "blocked_by_environment",
                            "reason": "backend_unavailable",
                            "stopped_at": "runtime_preflight",
                            "exit_code": 124,
                            "trigger_smoke_status": "skipped",
                        }}
                    ]
                else:
                    projects = [
                        {{
                            "project_key": "demo_proj",
                            "status": "passed",
                            "reason": None,
                            "stopped_at": None,
                            "exit_code": 0,
                            "trigger_smoke_status": "passed" if args.trigger_smoke else None,
                        }}
                    ]
                summary = {{
                    "total": len(projects),
                    "passed": sum(1 for project in projects if project["status"] == "passed"),
                    "failed": sum(1 for project in projects if project["status"] == "failed"),
                    "blocked_by_environment": sum(
                        1 for project in projects if project["status"] == "blocked_by_environment"
                    ),
                }}
                artifact_dir = Path(args.artifact_dir)
                artifact_dir.mkdir(parents=True, exist_ok=True)
                report = {{
                    "schema_version": "business_line_worker_readback_project_matrix.v1",
                    "status": status,
                    "api_base": args.api_base.rstrip("/"),
                    "artifact_dir": str(artifact_dir),
                    "allow_blocked": args.allow_blocked,
                    "trigger_smoke": args.trigger_smoke,
                    "project_selection": {{
                        "projects_api_url": args.projects_api_url,
                        "project_key_regex": args.project_key_regex,
                        "exclude_project_keys": args.exclude_project_key,
                        "max_projects": args.max_projects,
                        "project_keys": [project["project_key"] for project in projects],
                    }},
                    "projects": projects,
                    "summary": summary,
                }}
                report_path = artifact_dir / "{MATRIX_REPORT_NAME}"
                report_mode = os.environ.get("FAKE_MATRIX_REPORT_MODE", "valid")
                if report_mode == "invalid":
                    report_path.write_text("{{not-json}}\\n", encoding="utf-8")
                elif report_mode != "missing":
                    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
                if args.json:
                    print(json.dumps(report, indent=2, sort_keys=True))
                if "FAKE_MATRIX_EXIT_CODE" in os.environ:
                    raise SystemExit(int(os.environ["FAKE_MATRIX_EXIT_CODE"]))
                if status == "passed":
                    raise SystemExit(0)
                if status == "blocked_by_environment" and args.allow_blocked:
                    raise SystemExit(0)
                raise SystemExit(1)
                """
            ),
            encoding="utf-8",
        )
        return fake_runner

    def make_fake_local_deploy(self, temp_dir: Path, log_path: Path) -> Path:
        fake_deploy = temp_dir / "fake_local_deploy.sh"
        fake_deploy.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -euo pipefail
                echo "$*" >> {shlex.quote(str(log_path))}
                echo "fake local deploy $*"
                """
            ),
            encoding="utf-8",
        )
        fake_deploy.chmod(0o755)
        return fake_deploy

    def load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def load_history_rows(self, path: Path) -> list[dict[str, Any]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_dry_run_prints_markers_and_safe_project_defaults(self) -> None:
        completed = self.run_wrapper("--date", "2026-05-25", "--dry-run")

        markers = self.dry_run_markers(completed.stdout)
        for key in (
            "repo_root",
            "run_date",
            "output_dir",
            "matrix_report",
            "manifest",
            "history",
            "matrix_cmd",
            "ensure_local_runtime",
            "runtime_preflight_timeout",
        ):
            self.assertIn(key, markers)

        self.assertEqual(str(REPO_ROOT), markers["repo_root"])
        self.assertEqual("2026-05-25", markers["run_date"])
        self.assertEqual(
            str(
                REPO_ROOT
                / "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/2026-05-25"
            ),
            markers["output_dir"],
        )
        self.assertEqual(str(Path(markers["output_dir"]) / MATRIX_REPORT_NAME), markers["matrix_report"])
        self.assertEqual(str(Path(markers["output_dir"]) / "nightly-manifest.json"), markers["manifest"])
        self.assertEqual(
            str(
                REPO_ROOT
                / "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/trend-history.jsonl"
            ),
            markers["history"],
        )

        matrix_cmd = shlex.split(markers["matrix_cmd"])
        self.assertIn("--projects-api-url", matrix_cmd)
        self.assertEqual(
            "http://127.0.0.1:8000/api/v1/projects",
            matrix_cmd[matrix_cmd.index("--projects-api-url") + 1],
        )
        self.assertIn("--project-key-regex", matrix_cmd)
        self.assertEqual("^demo_proj$", matrix_cmd[matrix_cmd.index("--project-key-regex") + 1])
        self.assertNotIn("--allow-blocked", matrix_cmd)
        self.assertEqual("0", markers["ensure_local_runtime"])
        self.assertEqual("8", markers["runtime_preflight_timeout"])

    def test_non_dry_run_writes_manifest_and_history_without_scheduled_marker_for_manual_run(self) -> None:
        temp_dir = self.make_temp_dir()
        fake_runner = self.make_fake_runner(temp_dir)
        output_dir = temp_dir / "run"
        env = self.clean_env(MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner))

        self.run_wrapper(
            "--date",
            "2026-05-25",
            "--output-dir",
            str(output_dir),
            "--exclude-project-key",
            "archived",
            "--max-projects",
            "1",
            env=env,
        )

        manifest = self.load_json(output_dir / "nightly-manifest.json")
        history_rows = self.load_history_rows(output_dir / "trend-history.jsonl")

        self.assertEqual("passed", manifest["status"])
        self.assertEqual(0, manifest["matrix_exit_code"])
        self.assertEqual(str(output_dir / MATRIX_REPORT_NAME), manifest["matrix_report"])
        self.assertEqual(str(output_dir / "trend-history.jsonl"), manifest["history_path"])
        self.assertEqual("http://127.0.0.1:8000/api/v1/projects", manifest["project_selection"]["projects_api_url"])
        self.assertEqual("^demo_proj$", manifest["project_selection"]["project_key_regex"])
        self.assertEqual(["archived"], manifest["project_selection"]["exclude_project_keys"])
        self.assertEqual(1, manifest["project_selection"]["max_projects"])
        self.assertEqual("skipped", manifest["runtime_preflight"]["status"])
        self.assertGreaterEqual(manifest["duration_seconds"], 0)
        diagnostics = manifest["matrix_diagnostics"]
        self.assertEqual("passed", diagnostics["matrix_status"])
        self.assertEqual("passed", diagnostics["matrix_report_status"])
        self.assertEqual(0, diagnostics["matrix_exit_code"])
        self.assertEqual("skipped", diagnostics["runtime_preflight_status"])
        self.assertIsNone(diagnostics["runtime_preflight_start_exit_code"])
        self.assertEqual(["demo_proj"], diagnostics["project_keys"])
        self.assertEqual("http://127.0.0.1:8000/api/v1/projects", diagnostics["projects_api_url"])
        self.assertEqual(1, diagnostics["summary_total"])
        self.assertGreaterEqual(diagnostics["duration_seconds"], 0)
        self.assertEqual(0, diagnostics["blocked_project_count"])
        self.assertEqual(0, diagnostics["failed_project_count"])
        self.assertEqual([], diagnostics["blocked_projects"])
        self.assertEqual([], diagnostics["failed_projects"])
        self.assertEqual({}, diagnostics["stopped_at_counts"])
        self.assertEqual({}, diagnostics["reason_counts"])
        self.assertIsNone(diagnostics["first_blocked_reason"])
        self.assertNotIn("scheduled_run_evidence", manifest)
        self.assertNotIn("trigger", manifest)
        self.assertEqual(1, len(history_rows))
        self.assertEqual("passed", history_rows[0]["status"])
        self.assertEqual(diagnostics, history_rows[0]["matrix_diagnostics"])
        self.assertEqual("skipped", history_rows[0]["runtime_preflight_status"])
        self.assertGreaterEqual(history_rows[0]["duration_seconds"], 0)
        self.assertNotIn("scheduled_run_evidence", history_rows[0])
        self.assertNotIn("execution_source", history_rows[0])

    def test_manifest_matrix_diagnostics_summarizes_blocked_and_failed_project_rows(self) -> None:
        temp_dir = self.make_temp_dir()
        fake_runner = self.make_fake_runner(temp_dir)
        output_dir = temp_dir / "failed-run"
        env = self.clean_env(
            MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner),
            FAKE_MATRIX_STATUS="failed",
        )

        completed = self.run_wrapper("--date", "2026-05-25", "--output-dir", str(output_dir), env=env, check=False)

        manifest = self.load_json(output_dir / "nightly-manifest.json")
        history_rows = self.load_history_rows(output_dir / "trend-history.jsonl")
        diagnostics = manifest["matrix_diagnostics"]

        self.assertEqual(1, completed.returncode)
        self.assertEqual("failed", manifest["status"])
        self.assertEqual("failed", diagnostics["matrix_status"])
        self.assertEqual("failed", diagnostics["matrix_report_status"])
        self.assertEqual(1, diagnostics["matrix_exit_code"])
        self.assertEqual("skipped", diagnostics["runtime_preflight_status"])
        self.assertEqual(["demo_proj", "blocked_proj"], diagnostics["project_keys"])
        self.assertEqual("http://127.0.0.1:8000/api/v1/projects", diagnostics["projects_api_url"])
        self.assertEqual(2, diagnostics["summary_total"])
        self.assertEqual(1, diagnostics["blocked_project_count"])
        self.assertEqual(1, diagnostics["failed_project_count"])
        self.assertEqual(
            [
                {
                    "project_key": "blocked_proj",
                    "status": "blocked_by_environment",
                    "reason": "backend_unavailable",
                    "stopped_at": "runtime_preflight",
                    "exit_code": 124,
                    "trigger_smoke_status": "skipped",
                }
            ],
            diagnostics["blocked_projects"],
        )
        self.assertEqual(
            [
                {
                    "project_key": "demo_proj",
                    "status": "failed",
                    "reason": "worker_readback_failed",
                    "stopped_at": "worker_readback",
                    "exit_code": 1,
                    "trigger_smoke_status": "failed",
                }
            ],
            diagnostics["failed_projects"],
        )
        self.assertEqual({"runtime_preflight": 1, "worker_readback": 1}, diagnostics["stopped_at_counts"])
        self.assertEqual({"backend_unavailable": 1, "worker_readback_failed": 1}, diagnostics["reason_counts"])
        self.assertEqual("backend_unavailable", diagnostics["first_blocked_reason"])
        self.assertEqual(diagnostics, history_rows[-1]["matrix_diagnostics"])

    def test_manifest_matrix_diagnostics_uses_defaults_when_report_is_missing_or_invalid(self) -> None:
        for report_mode in ("missing", "invalid"):
            with self.subTest(report_mode=report_mode):
                temp_dir = self.make_temp_dir()
                fake_runner = self.make_fake_runner(temp_dir)
                output_dir = temp_dir / f"{report_mode}-report-run"
                env = self.clean_env(
                    MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner),
                    FAKE_MATRIX_EXIT_CODE="1",
                    FAKE_MATRIX_REPORT_MODE=report_mode,
                )

                completed = self.run_wrapper(
                    "--date", "2026-05-25", "--output-dir", str(output_dir), env=env, check=False
                )

                manifest = self.load_json(output_dir / "nightly-manifest.json")
                diagnostics = manifest["matrix_diagnostics"]

                self.assertEqual(1, completed.returncode)
                self.assertEqual("failed", manifest["status"])
                self.assertIs(manifest["matrix_report_loaded"], False)
                self.assertEqual("failed", diagnostics["matrix_status"])
                self.assertIsNone(diagnostics["matrix_report_status"])
                self.assertEqual(1, diagnostics["matrix_exit_code"])
                self.assertEqual("skipped", diagnostics["runtime_preflight_status"])
                self.assertIsNone(diagnostics["runtime_preflight_start_exit_code"])
                self.assertEqual([], diagnostics["project_keys"])
                self.assertEqual("http://127.0.0.1:8000/api/v1/projects", diagnostics["projects_api_url"])
                self.assertEqual(0, diagnostics["summary_total"])
                self.assertEqual(0, diagnostics["blocked_project_count"])
                self.assertEqual(0, diagnostics["failed_project_count"])
                self.assertEqual([], diagnostics["blocked_projects"])
                self.assertEqual([], diagnostics["failed_projects"])
                self.assertEqual({}, diagnostics["stopped_at_counts"])
                self.assertEqual({}, diagnostics["reason_counts"])
                self.assertIsNone(diagnostics["first_blocked_reason"])

    def test_ensure_local_runtime_attempts_start_when_health_is_unavailable(self) -> None:
        temp_dir = self.make_temp_dir()
        fake_runner = self.make_fake_runner(temp_dir)
        deploy_log = temp_dir / "local-deploy.log"
        fake_deploy = self.make_fake_local_deploy(temp_dir, deploy_log)
        output_dir = temp_dir / "runtime-preflight"
        env = self.clean_env(
            MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner),
            MRW_LOCAL_DEPLOY_SCRIPT=str(fake_deploy),
        )

        self.run_wrapper(
            "--date",
            "2026-05-25",
            "--output-dir",
            str(output_dir),
            "--api-base",
            "http://127.0.0.1:9",
            "--ensure-local-runtime",
            "--runtime-preflight-timeout",
            "0.1",
            env=env,
        )

        manifest = self.load_json(output_dir / "nightly-manifest.json")
        self.assertEqual("passed", manifest["status"])
        self.assertTrue(manifest["runtime_preflight"]["attempted_start"])
        self.assertEqual(0, manifest["runtime_preflight"]["start_exit_code"])
        self.assertEqual("blocked_by_environment", manifest["runtime_preflight"]["status"])
        self.assertEqual("start", deploy_log.read_text(encoding="utf-8").strip())

    def test_scheduled_environment_writes_marker_to_manifest_and_history(self) -> None:
        temp_dir = self.make_temp_dir()
        fake_runner = self.make_fake_runner(temp_dir)
        output_dir = temp_dir / "scheduled-run"
        env = self.clean_env(
            MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner),
            MRW_SCHEDULED_RUN_EVIDENCE="true",
        )

        self.run_wrapper("--date", "2026-05-25", "--output-dir", str(output_dir), env=env)

        manifest = self.load_json(output_dir / "nightly-manifest.json")
        history_rows = self.load_history_rows(output_dir / "trend-history.jsonl")

        self.assertIs(manifest["scheduled_run_evidence"], True)
        self.assertEqual("codex_app_scheduler", manifest["trigger"])
        self.assertEqual("mrw_scheduled_run_evidence", manifest["source"])
        self.assertEqual("scheduled", manifest["run_source"])
        self.assertEqual("scheduled", manifest["execution_source"])
        self.assertIs(history_rows[-1]["scheduled_run_evidence"], True)
        self.assertEqual("scheduled", history_rows[-1]["execution_source"])

    def test_allow_blocked_is_explicit_and_manifest_preserves_blocked_report_status(self) -> None:
        temp_dir = self.make_temp_dir()
        fake_runner = self.make_fake_runner(temp_dir)
        output_dir = temp_dir / "blocked-run"
        env = self.clean_env(
            MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner),
            FAKE_MATRIX_STATUS="blocked_by_environment",
        )

        completed = self.run_wrapper(
            "--date",
            "2026-05-25",
            "--output-dir",
            str(output_dir),
            "--allow-blocked",
            env=env,
        )

        manifest = self.load_json(output_dir / "nightly-manifest.json")
        history_rows = self.load_history_rows(output_dir / "trend-history.jsonl")
        report = self.load_json(output_dir / MATRIX_REPORT_NAME)

        self.assertEqual(0, completed.returncode)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertIs(report["allow_blocked"], True)
        self.assertEqual("blocked_by_environment", manifest["status"])
        self.assertEqual(0, manifest["matrix_exit_code"])
        self.assertIs(manifest["allow_blocked"], True)
        self.assertEqual("blocked_by_environment", history_rows[-1]["status"])

    def test_scheduled_blocked_manifest_is_recognized_by_scheduled_artifact_checker(self) -> None:
        temp_dir = self.make_temp_dir()
        fake_runner = self.make_fake_runner(temp_dir)
        checker_root = temp_dir / "checker-root"
        output_dir = (
            checker_root
            / "development/latest-dev-docs/automation-runs/"
            "business-line-worker-readback-project-matrix/2026-05-25"
        )
        env = self.clean_env(
            MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER=str(fake_runner),
            MRW_SCHEDULED_RUN_EVIDENCE="true",
            FAKE_MATRIX_STATUS="blocked_by_environment",
        )

        completed = self.run_wrapper(
            "--date",
            "2026-05-25",
            "--output-dir",
            str(output_dir),
            env=env,
            check=False,
        )

        manifest = self.load_json(output_dir / "nightly-manifest.json")
        self.assertEqual(1, completed.returncode)
        self.assertIs(manifest["scheduled_run_evidence"], True)
        self.assertEqual("codex_app_scheduler", manifest["trigger"])
        self.assertEqual("scheduled", manifest["execution_source"])
        self.assertEqual("blocked_by_environment", manifest["status"])
        self.assertEqual(1, manifest["matrix_exit_code"])
        self.assertNotIn("dry_run", manifest)

        checker = subprocess.run(
            [
                os.environ.get("PYTHON", "/Users/wangyiliang/.local/bin/python3.11"),
                str(REPO_ROOT / "scripts/check_scheduled_automation_artifacts.py"),
                "--root",
                str(checker_root),
                "--json",
                "--allow-missing",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, checker.returncode, checker.stderr)
        report = json.loads(checker.stdout)
        matrix = next(
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        )
        self.assertEqual("blocked", report["status"])
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual(1, report["summary"]["scheduled_run_blocked_count"])
        self.assertEqual("scheduled_run_blocked", report["summary"]["first_blocker_classification"])
        self.assertEqual("scheduled_run_blocked", matrix["classification"])
        self.assertEqual("scheduled_run_blocked", matrix["blocker_classification"])
        self.assertEqual(
            "development/latest-dev-docs/automation-runs/"
            "business-line-worker-readback-project-matrix/2026-05-25/nightly-manifest.json",
            matrix["artifact_path"],
        )
        self.assertEqual("blocked_by_environment", matrix["diagnostics"]["matrix_status"])
        self.assertEqual(["demo_proj"], matrix["diagnostics"]["project_keys"])


if __name__ == "__main__":
    unittest.main()
