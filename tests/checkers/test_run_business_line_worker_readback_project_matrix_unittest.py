#!/usr/bin/env python3
"""Unit tests for multi-project worker readback matrix orchestration."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_business_line_worker_readback_project_matrix.py"
)
CHAIN_SCRIPT = "scripts/run_business_line_worker_readback_evidence_chain.py"


def load_runner() -> Any:
    if not SCRIPT_PATH.exists():
        raise unittest.SkipTest(f"{SCRIPT_PATH} is not implemented yet")
    spec = importlib.util.spec_from_file_location("run_business_line_worker_readback_project_matrix", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    return runner


class BusinessLineWorkerReadbackProjectMatrixTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def make_artifact_dir(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def base_argv(self, artifact_dir: Path, *extra: str) -> list[str]:
        return [
            "--api-base",
            "http://127.0.0.1:8000",
            "--project-key",
            "alpha",
            "--project-key",
            "beta",
            "--artifact-dir",
            str(artifact_dir),
            "--timeout",
            "2",
            "--json",
            *extra,
        ]

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, Any], str]:
        exit_code, stdout, _ = self.run_main_raw(argv)
        return exit_code, json.loads(stdout), stdout

    def run_main_raw(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                result = self.runner.main(argv)
                exit_code = int(result or 0)
            except SystemExit as exc:
                exit_code = int(exc.code or 0)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def command_arg(self, command: list[str], option: str) -> str:
        self.assertIn(option, command)
        return command[command.index(option) + 1]

    def command_result(self, *, exit_code: int, stdout: str, stderr: str = "") -> object:
        result_cls = getattr(self.runner, "CommandResult", None)
        if result_cls is not None:
            return result_cls(exit_code=exit_code, stdout=stdout, stderr=stderr)
        return types.SimpleNamespace(exit_code=exit_code, returncode=exit_code, stdout=stdout, stderr=stderr)

    def chain_payload(self, *, project_key: str, status: str) -> dict[str, Any]:
        return {
            "schema_version": "business_line_worker_readback_evidence_chain.v1",
            "status": status,
            "project_key": project_key,
            "reason": "backend unavailable" if status == "blocked_by_environment" else None,
            "stopped_at": "worker_readback" if status != "passed" else None,
            "trigger_smoke_status": "not_requested",
            "summary": {
                "passed": 1 if status == "passed" else 0,
                "blocked": 1 if status == "blocked_by_environment" else 0,
                "failed": 1 if status == "failed" else 0,
            },
            "steps": [],
        }

    def fake_chain_runner(
        self,
        statuses: dict[str, str],
        *,
        root_artifact_dir: Path | None = None,
        commands: list[list[str]] | None = None,
    ) -> object:
        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            command = [str(part) for part in command]
            if commands is not None:
                commands.append(command)
            self.assertTrue(any(part.endswith(CHAIN_SCRIPT) for part in command), command)
            self.assertNotIn("--allow-blocked", command)
            self.assertEqual("http://127.0.0.1:8000", self.command_arg(command, "--api-base"))
            self.assertEqual(2.0, float(self.command_arg(command, "--timeout")))

            project_key = self.command_arg(command, "--project-key")
            artifact_dir = Path(self.command_arg(command, "--artifact-dir"))
            if root_artifact_dir is not None:
                relative = artifact_dir.resolve().relative_to(root_artifact_dir.resolve())
                self.assertEqual(1, len(relative.parts), f"unsafe project artifact path: {artifact_dir}")
                self.assertNotIn("..", relative.parts)
                self.assertNotIn("/", relative.parts[0])

            status = statuses[project_key]
            payload = self.chain_payload(project_key=project_key, status=status)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "business-line-worker-readback-evidence-chain-report.json").write_text(
                json.dumps(payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            exit_code = 0 if status == "passed" else 1
            return self.command_result(
                exit_code=exit_code,
                stdout=f"child stdout for {project_key}: {json.dumps(payload, sort_keys=True)}",
                stderr=f"child stderr for {project_key}",
            )

        return fake_run_command

    def projects_by_key(self, report: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(project["project_key"]): project for project in report["projects"]}

    def write_projects_list(self, artifact_dir: Path, payload: Any) -> Path:
        path = artifact_dir / "projects-list.json"
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_two_projects_all_passed(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "passed", "beta": "passed"}, commands=commands),
        ):
            exit_code, report, _ = self.run_main(self.base_argv(artifact_dir))

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", report["status"])
        self.assertEqual(
            {"passed": 2, "blocked_by_environment": 0, "failed": 0, "total": 2},
            report["summary"],
        )
        self.assertEqual(["alpha", "beta"], [project["project_key"] for project in report["projects"]])
        self.assertTrue(all(project["status"] == "passed" for project in report["projects"]))
        self.assertEqual(2, len(commands))

    def test_projects_list_json_selects_enabled_projects_from_envelope(self) -> None:
        artifact_dir = self.make_artifact_dir()
        projects_list = self.write_projects_list(
            artifact_dir,
            {
                "status": "success",
                "data": {
                    "items": [
                        {"project_key": "alpha", "enabled": True},
                        {"project_key": "disabled-project", "enabled": False},
                        {"project_key": "gamma", "enabled": True},
                    ]
                },
            },
        )
        commands: list[list[str]] = []

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "passed", "gamma": "passed"}, commands=commands),
        ):
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--projects-list-json",
                    str(projects_list),
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(["alpha", "gamma"], [project["project_key"] for project in report["projects"]])
        self.assertEqual(["alpha", "gamma"], [self.command_arg(command, "--project-key") for command in commands])

    def test_projects_api_url_selects_enabled_projects_from_envelope(self) -> None:
        artifact_dir = self.make_artifact_dir()
        api_payload = {
            "status": "success",
            "data": {
                "items": [
                    {"project_key": "alpha", "enabled": True},
                    {"project_key": "disabled-project", "enabled": False},
                    {"project_key": "archived-project", "enabled": True, "archived": True},
                    {"project_key": "schema-missing", "enabled": True, "schema_ready": False},
                    {"project_key": "fixture-missing", "enabled": True, "has_worker_fixture": False},
                    {"project_key": "not-eligible", "enabled": True, "nightly_matrix_eligible": False},
                    {"project_key": "  ", "enabled": True},
                    "bare-string-is-ignored-for-api",
                    {"project_key": "gamma", "enabled": True},
                ]
            },
        }
        commands: list[list[str]] = []

        with (
            patch.object(self.runner, "fetch_json_url", return_value=api_payload) as fetch_json_url,
            patch.object(
                self.runner,
                "run_command",
                side_effect=self.fake_chain_runner({"alpha": "passed", "gamma": "passed"}, commands=commands),
            ),
        ):
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--projects-api-url",
                    "http://127.0.0.1:8000/api/v1/projects",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        fetch_json_url.assert_called_once_with("http://127.0.0.1:8000/api/v1/projects", timeout=2.0)
        self.assertEqual(["alpha", "gamma"], [project["project_key"] for project in report["projects"]])
        self.assertEqual(["alpha", "gamma"], [self.command_arg(command, "--project-key") for command in commands])
        self.assertEqual(["alpha", "gamma"], report["project_selection"]["api_project_keys"])
        self.assertEqual(["alpha", "gamma"], report["project_selection"]["project_keys"])
        excluded = {
            item["project_key"]: item["reason"]
            for item in report["project_selection"]["api_excluded_projects"]
            if item.get("project_key")
        }
        self.assertEqual("disabled", excluded["disabled-project"])
        self.assertEqual("archived", excluded["archived-project"])
        self.assertEqual("schema_not_ready", excluded["schema-missing"])
        self.assertEqual("worker_fixture_missing", excluded["fixture-missing"])
        self.assertEqual("nightly_matrix_not_eligible", excluded["not-eligible"])

    def test_project_key_and_projects_list_json_are_merged_and_deduped(self) -> None:
        artifact_dir = self.make_artifact_dir()
        projects_list = self.write_projects_list(
            artifact_dir,
            [
                {"project_key": "alpha", "enabled": True},
                {"project_key": "beta", "enabled": True},
                {"project_key": "gamma", "enabled": False},
            ],
        )
        commands: list[list[str]] = []

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "passed", "beta": "passed"}, commands=commands),
        ):
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "alpha",
                    "--projects-list-json",
                    str(projects_list),
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(["alpha", "beta"], [project["project_key"] for project in report["projects"]])
        self.assertEqual(["alpha", "beta"], [self.command_arg(command, "--project-key") for command in commands])

    def test_project_key_projects_list_json_and_api_are_merged_and_deduped(self) -> None:
        artifact_dir = self.make_artifact_dir()
        projects_list = self.write_projects_list(
            artifact_dir,
            [
                {"project_key": "alpha", "enabled": True},
                {"project_key": "beta", "enabled": True},
            ],
        )
        api_payload = {
            "data": {
                "items": [
                    {"project_key": "beta", "enabled": True},
                    {"project_key": "gamma", "enabled": True},
                ]
            }
        }
        commands: list[list[str]] = []

        with (
            patch.object(self.runner, "fetch_json_url", return_value=api_payload),
            patch.object(
                self.runner,
                "run_command",
                side_effect=self.fake_chain_runner(
                    {"alpha": "passed", "beta": "passed", "gamma": "passed"},
                    commands=commands,
                ),
            ),
        ):
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "alpha",
                    "--projects-list-json",
                    str(projects_list),
                    "--projects-api-url",
                    "http://127.0.0.1:8000/api/v1/projects",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(["alpha", "beta", "gamma"], [project["project_key"] for project in report["projects"]])
        self.assertEqual(["alpha", "beta", "gamma"], [self.command_arg(command, "--project-key") for command in commands])
        self.assertEqual(["alpha", "beta", "gamma"], report["project_selection"]["merged_project_keys"])
        self.assertEqual(["alpha", "beta", "gamma"], report["project_selection"]["project_keys"])

    def test_regex_exclude_and_max_filter_after_merge(self) -> None:
        artifact_dir = self.make_artifact_dir()
        projects_list = self.write_projects_list(
            artifact_dir,
            [
                {"project_key": "demo-beta", "enabled": True},
                {"project_key": "other", "enabled": True},
            ],
        )
        api_payload = {
            "data": {
                "items": [
                    {"project_key": "demo-gamma", "enabled": True},
                    {"project_key": "demo-delta", "enabled": True},
                ]
            }
        }
        commands: list[list[str]] = []

        with (
            patch.object(self.runner, "fetch_json_url", return_value=api_payload),
            patch.object(
                self.runner,
                "run_command",
                side_effect=self.fake_chain_runner(
                    {"demo-alpha": "passed", "demo-gamma": "passed"},
                    commands=commands,
                ),
            ),
        ):
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo-alpha",
                    "--projects-list-json",
                    str(projects_list),
                    "--projects-api-url",
                    "http://127.0.0.1:8000/api/v1/projects",
                    "--project-key-regex",
                    "^demo-",
                    "--exclude-project-key",
                    "demo-beta",
                    "--max-projects",
                    "2",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(["demo-alpha", "demo-gamma"], [project["project_key"] for project in report["projects"]])
        self.assertEqual(["demo-alpha", "demo-gamma"], [self.command_arg(command, "--project-key") for command in commands])
        self.assertEqual(
            ["demo-alpha", "demo-beta", "other", "demo-gamma", "demo-delta"],
            report["project_selection"]["merged_project_keys"],
        )
        self.assertEqual(["demo-alpha", "demo-gamma"], report["project_selection"]["project_keys"])
        recommended = report["recommended_next_commands"][0]
        self.assertIn("--projects-api-url http://127.0.0.1:8000/api/v1/projects", recommended)
        self.assertIn("--project-key-regex '^demo-'", recommended)
        self.assertIn("--exclude-project-key demo-beta", recommended)
        self.assertIn("--max-projects 2", recommended)

    def test_invalid_project_key_regex_fails_without_running_child(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with (
            patch.object(self.runner, "fetch_json_url") as fetch_json_url,
            patch.object(self.runner, "run_command") as run_command,
        ):
            exit_code, stdout, stderr = self.run_main_raw(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--projects-api-url",
                    "http://127.0.0.1:8000/api/v1/projects",
                    "--project-key-regex",
                    "[",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("invalid --project-key-regex", stderr)
        fetch_json_url.assert_not_called()
        run_command.assert_not_called()

    def test_invalid_max_projects_fails_without_running_child(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with (
            patch.object(self.runner, "fetch_json_url") as fetch_json_url,
            patch.object(self.runner, "run_command") as run_command,
        ):
            exit_code, stdout, stderr = self.run_main_raw(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--projects-api-url",
                    "http://127.0.0.1:8000/api/v1/projects",
                    "--max-projects",
                    "0",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("--max-projects must be greater than 0", stderr)
        fetch_json_url.assert_not_called()
        run_command.assert_not_called()

    def test_one_blocked_with_allow_blocked_exits_zero_but_reports_blocked(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "passed", "beta": "blocked_by_environment"}),
        ):
            exit_code, report, _ = self.run_main(self.base_argv(artifact_dir, "--allow-blocked"))

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(1, report["summary"]["passed"])
        self.assertEqual(1, report["summary"]["blocked_by_environment"])
        self.assertEqual(0, report["summary"]["failed"])
        projects = self.projects_by_key(report)
        self.assertEqual("passed", projects["alpha"]["status"])
        self.assertEqual("blocked_by_environment", projects["beta"]["status"])
        self.assertEqual("backend unavailable", projects["beta"]["reason"])
        self.assertEqual("worker_readback", projects["beta"]["stopped_at"])

    def test_failed_status_takes_priority_over_blocked_even_when_blocked_is_allowed(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "blocked_by_environment", "beta": "failed"}),
        ):
            exit_code, report, _ = self.run_main(self.base_argv(artifact_dir, "--allow-blocked"))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual(0, report["summary"]["passed"])
        self.assertEqual(1, report["summary"]["blocked_by_environment"])
        self.assertEqual(1, report["summary"]["failed"])
        projects = self.projects_by_key(report)
        self.assertEqual("blocked_by_environment", projects["alpha"]["status"])
        self.assertEqual("failed", projects["beta"]["status"])

    def test_default_report_keeps_child_summary_without_full_stdout_or_chain_report(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "passed", "beta": "passed"}),
        ):
            exit_code, report, _ = self.run_main(self.base_argv(artifact_dir))

        self.assertEqual(0, exit_code)
        for project in report["projects"]:
            self.assertNotIn("stdout", project)
            self.assertNotIn("stderr", project)
            self.assertNotIn("chain_report", project)
            self.assertEqual({"blocked": 0, "failed": 0, "passed": 1}, project["chain_summary"])
            self.assertEqual("not_requested", project["trigger_smoke_status"])
            self.assertTrue(project["chain_report_path"].endswith("business-line-worker-readback-evidence-chain-report.json"))

    def test_include_child_reports_embeds_full_stdout_stderr_and_chain_report(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner({"alpha": "passed", "beta": "passed"}),
        ):
            exit_code, report, _ = self.run_main(self.base_argv(artifact_dir, "--include-child-reports"))

        self.assertEqual(0, exit_code)
        projects = self.projects_by_key(report)
        self.assertIn("child stdout for alpha", projects["alpha"]["stdout"])
        self.assertEqual("child stderr for alpha", projects["alpha"]["stderr"])
        self.assertEqual("alpha", projects["alpha"]["chain_report"]["project_key"])

    def test_project_key_directory_is_safely_normalized(self) -> None:
        artifact_dir = self.make_artifact_dir()
        unsafe_key = "../tenant/demo project"
        commands: list[list[str]] = []

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner(
                {unsafe_key: "passed"},
                root_artifact_dir=artifact_dir,
                commands=commands,
            ),
        ):
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    unsafe_key,
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", report["status"])
        self.assertEqual(unsafe_key, report["projects"][0]["project_key"])
        child_artifact_dir = Path(self.command_arg(commands[0], "--artifact-dir"))
        self.assertNotEqual(artifact_dir / unsafe_key, child_artifact_dir)

    def test_trigger_smoke_is_forwarded_but_allow_blocked_is_not_forwarded(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        with patch.object(
            self.runner,
            "run_command",
            side_effect=self.fake_chain_runner(
                {"alpha": "blocked_by_environment", "beta": "blocked_by_environment"},
                commands=commands,
            ),
        ):
            exit_code, report, _ = self.run_main(
                self.base_argv(artifact_dir, "--trigger-smoke", "--allow-blocked")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(2, report["summary"]["blocked_by_environment"])
        self.assertTrue(commands)
        for command in commands:
            self.assertIn("--trigger-smoke", command)
            self.assertNotIn("--allow-blocked", command)

    def test_no_project_keys_fails_without_running_empty_matrix(self) -> None:
        artifact_dir = self.make_artifact_dir()

        with patch.object(self.runner, "run_command") as run_command:
            exit_code, report, _ = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--timeout",
                    "2",
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual({"blocked_by_environment": 0, "failed": 0, "passed": 0, "total": 0}, report["summary"])
        self.assertEqual("no project keys were provided", report["error"])
        run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
