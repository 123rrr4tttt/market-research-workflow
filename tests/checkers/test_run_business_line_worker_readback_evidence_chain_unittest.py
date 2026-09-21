#!/usr/bin/env python3
"""Unit tests for worker readback evidence chain orchestration."""

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


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_business_line_worker_readback_evidence_chain.py"
SPEC = importlib.util.spec_from_file_location("run_business_line_worker_readback_evidence_chain", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
chain = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = chain
SPEC.loader.exec_module(chain)


class BusinessLineWorkerReadbackEvidenceChainTestCase(unittest.TestCase):
    def make_artifact_dir(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(
        self,
        path: Path,
        status: str,
        *,
        schema_version: str = "test.schema.v1",
        **extra: object,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": schema_version, "status": status, **extra}, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def command_step(self, command: list[str]) -> str:
        if len(command) > 1 and command[1].startswith("scripts/"):
            return command[1]
        return " ".join(command)

    def command_output_path(self, command: list[str]) -> Path:
        return Path(command[command.index("--output") + 1])

    def assert_async_checker_uses_candidate_manifest(self, commands: list[list[str]], artifact_dir: Path) -> None:
        checker_commands = [
            command
            for command in commands
            if self.command_step(command) == "scripts/check_business_line_async_task_readback_artifact.py"
        ]
        self.assertEqual(1, len(checker_commands))
        checker_command = checker_commands[0]
        self.assertNotIn("--allow-blocked", checker_command)
        self.assertIn("--task-readback-manifest", checker_command)
        manifest_arg = checker_command[checker_command.index("--task-readback-manifest") + 1]
        self.assertEqual(str(artifact_dir / "business-line-task-readback-manifest-candidate.json"), manifest_arg)

    def assert_command_project_key(self, command: list[str], project_key: str) -> None:
        self.assertIn("--project-key", command)
        self.assertEqual(project_key, command[command.index("--project-key") + 1])

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        artifact_dir = Path(argv[argv.index("--artifact-dir") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = chain.main(argv)
        report_path = artifact_dir / "business-line-worker-readback-evidence-chain-report.json"
        return exit_code, json.loads(report_path.read_text(encoding="utf-8"))

    def base_argv(self, artifact_dir: Path, *extra: str) -> list[str]:
        return [
            "--api-base",
            "http://127.0.0.1:8000",
            "--artifact-dir",
            str(artifact_dir),
            "--timeout",
            "2",
            "--json",
            *extra,
        ]

    def test_candidate_blocked_stops_before_runner(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.write_json(self.command_output_path(command), "blocked_by_environment")
            return chain.CommandResult(exit_code=1, stdout="", stderr="connection refused")

        with patch.object(chain, "run_command", side_effect=fake_run_command):
            exit_code, report = self.run_main(self.base_argv(artifact_dir))

        self.assertEqual(1, exit_code)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual("batch75_candidate_builder", report["stopped_at"])
        self.assertEqual(["scripts/build_business_line_task_readback_manifest_from_runtime.py"], [self.command_step(cmd) for cmd in commands])
        self.assertFalse((artifact_dir / "business-line-async-task-readback-live-samples.json").exists())

    def test_project_key_passed_to_runtime_commands_and_report(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            step = self.command_step(command)
            if step == "scripts/check_business_line_worker_project_schema_preflight.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/build_business_line_task_readback_manifest_from_runtime.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_task_readback_manifest.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            if step == "scripts/run_business_line_async_task_readback_live_samples.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            self.fail(f"unexpected command: {command}")

        with (
            patch.object(chain, "run_command", side_effect=fake_run_command),
            patch.object(chain.request, "urlopen", side_effect=chain.error.URLError("offline")),
        ):
            exit_code, report = self.run_main(
                self.base_argv(artifact_dir, "--project-key", "demo_proj", "--allow-blocked")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual("demo_proj", report["project_key"])
        self.assertEqual("batch71_async_task_readback_builder", report["stopped_at"])
        command_by_step = {self.command_step(command): command for command in commands}
        self.assert_command_project_key(
            command_by_step["scripts/check_business_line_worker_project_schema_preflight.py"],
            "demo_proj",
        )
        self.assert_command_project_key(
            command_by_step["scripts/build_business_line_task_readback_manifest_from_runtime.py"],
            "demo_proj",
        )
        self.assert_command_project_key(
            command_by_step["scripts/run_business_line_async_task_readback_live_samples.py"],
            "demo_proj",
        )
        self.assertNotIn("--project-key", command_by_step["scripts/check_business_line_task_readback_manifest.py"])
        self.assertEqual("evidence_matrix_fetch", report["steps"][-1]["step"])
        self.assertEqual(
            "http://127.0.0.1:8000/api/v1/business-lines/evidence-matrix?project_key=demo_proj",
            report["steps"][-1]["command"][1],
        )

    def test_project_schema_preflight_failed_stops_before_candidate_builder(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.write_json(self.command_output_path(command), "failed", reason="schema_missing_marker")
            return chain.CommandResult(exit_code=1, stdout='{"status": "failed"}', stderr="schema missing")

        with patch.object(chain, "run_command", side_effect=fake_run_command):
            exit_code, report = self.run_main(self.base_argv(artifact_dir, "--project-key", "demo_proj"))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual("batch82_project_schema_preflight", report["stopped_at"])
        self.assertEqual("project_schema_preflight_not_passed", report["reason"])
        self.assertEqual(
            ["scripts/check_business_line_worker_project_schema_preflight.py"],
            [self.command_step(command) for command in commands],
        )

    def test_trigger_smoke_requires_project_key(self) -> None:
        artifact_dir = self.make_artifact_dir()

        exit_code, report = self.run_main(self.base_argv(artifact_dir, "--trigger-smoke"))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertTrue(report["trigger_smoke"])
        self.assertEqual("failed", report["trigger_smoke_status"])
        self.assertEqual("batch83_trigger_smoke", report["stopped_at"])
        self.assertEqual("trigger_smoke_requires_project_key", report["reason"])
        self.assertEqual("trigger_smoke_requires_project_key", report["steps"][0]["error"])
        self.assertEqual(
            str(artifact_dir / "business-line-worker-trigger-smoke-artifact.json"),
            report["trigger_smoke_artifact_path"],
        )
        self.assertFalse((artifact_dir / "business-line-task-readback-manifest-candidate.json").exists())

    def test_trigger_smoke_failed_stops_before_candidate_builder(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            step = self.command_step(command)
            if step == "scripts/check_business_line_worker_project_schema_preflight.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/run_business_line_worker_readback_smoke_triggers.py":
                self.write_json(self.command_output_path(command), "failed", reason="trigger_smoke_timeout")
                return chain.CommandResult(exit_code=1, stdout='{"status": "failed"}', stderr="trigger timed out")
            self.fail(f"unexpected command: {command}")

        with patch.object(chain, "run_command", side_effect=fake_run_command):
            exit_code, report = self.run_main(
                self.base_argv(artifact_dir, "--project-key", "demo_proj", "--trigger-smoke")
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertTrue(report["trigger_smoke"])
        self.assertEqual("failed", report["trigger_smoke_status"])
        self.assertEqual("batch83_trigger_smoke", report["stopped_at"])
        self.assertEqual("trigger_smoke_not_passed", report["reason"])
        self.assertEqual("batch83_trigger_smoke", report["steps"][-1]["step"])
        self.assert_command_project_key(commands[-1], "demo_proj")
        self.assertEqual(
            [
                "scripts/check_business_line_worker_project_schema_preflight.py",
                "scripts/run_business_line_worker_readback_smoke_triggers.py",
            ],
            [self.command_step(command) for command in commands],
        )
        self.assertFalse((artifact_dir / "business-line-task-readback-manifest-candidate.json").exists())

    def test_trigger_smoke_success_records_artifact_and_continues_chain(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.assertNotIn("--allow-blocked", command)
            step = self.command_step(command)
            if step == "scripts/check_business_line_worker_project_schema_preflight.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/run_business_line_worker_readback_smoke_triggers.py":
                self.write_json(
                    self.command_output_path(command),
                    "passed",
                    worker_required_line_keys=[
                        "ingest",
                        "search_discovery_index",
                        "resource_source_library",
                        "writing_knowledge_graph_agent",
                    ],
                )
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/build_business_line_task_readback_manifest_from_runtime.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_task_readback_manifest.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            if step == "scripts/run_business_line_async_task_readback_live_samples.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/build_business_line_async_task_readback_artifact.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_async_task_readback_artifact.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            self.fail(f"unexpected command: {command}")

        with (
            patch.object(chain, "run_command", side_effect=fake_run_command),
            patch.object(
                chain,
                "fetch_evidence_matrix",
                return_value=chain.FetchResult(
                    status="passed",
                    payload={"schema_version": "business_line.evidence_matrix.v1", "lines": []},
                    http_status=200,
                    error=None,
                ),
            ),
        ):
            exit_code, report = self.run_main(
                self.base_argv(artifact_dir, "--project-key", "demo_proj", "--trigger-smoke")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", report["status"])
        self.assertTrue(report["trigger_smoke"])
        self.assertEqual("passed", report["trigger_smoke_status"])
        self.assertEqual(
            str(artifact_dir / "business-line-worker-trigger-smoke-artifact.json"),
            report["trigger_smoke_artifact_path"],
        )
        self.assertIsNone(report["stopped_at"])
        self.assertEqual(report["chain_step_order"], [step["step"] for step in report["steps"]])
        self.assertEqual(
            [
                "scripts/check_business_line_worker_project_schema_preflight.py",
                "scripts/run_business_line_worker_readback_smoke_triggers.py",
                "scripts/build_business_line_task_readback_manifest_from_runtime.py",
                "scripts/check_business_line_task_readback_manifest.py",
                "scripts/run_business_line_async_task_readback_live_samples.py",
                "scripts/build_business_line_async_task_readback_artifact.py",
                "scripts/check_business_line_async_task_readback_artifact.py",
            ],
            [self.command_step(command) for command in commands],
        )
        trigger_command = commands[1]
        self.assert_command_project_key(trigger_command, "demo_proj")
        self.assertEqual(
            str(artifact_dir / "business-line-worker-trigger-smoke-artifact.json"),
            trigger_command[trigger_command.index("--output") + 1],
        )
        trigger_artifact = json.loads(
            (artifact_dir / "business-line-worker-trigger-smoke-artifact.json").read_text(encoding="utf-8")
        )
        self.assertEqual("passed", trigger_artifact["status"])
        self.assertEqual(4, len(trigger_artifact["worker_required_line_keys"]))

    def test_checker_failed_stops_before_runner(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            step = self.command_step(command)
            if step == "scripts/build_business_line_task_readback_manifest_from_runtime.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_task_readback_manifest.py":
                return chain.CommandResult(
                    exit_code=1,
                    stdout=json.dumps({"schema_version": "business_line_task_readback_manifest_check.v1", "status": "failed"}),
                    stderr="",
                )
            self.fail(f"unexpected command: {command}")

        with patch.object(chain, "run_command", side_effect=fake_run_command):
            exit_code, report = self.run_main(self.base_argv(artifact_dir))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual("batch74_manifest_checker", report["stopped_at"])
        self.assertEqual(
            [
                "scripts/build_business_line_task_readback_manifest_from_runtime.py",
                "scripts/check_business_line_task_readback_manifest.py",
            ],
            [self.command_step(cmd) for cmd in commands],
        )
        self.assertTrue((artifact_dir / "business-line-task-readback-manifest-check.json").exists())
        self.assertFalse((artifact_dir / "business-line-async-task-readback-live-samples.json").exists())

    def test_full_fake_command_path_passed_writes_all_steps(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.assertNotIn("--allow-blocked", command)
            step = self.command_step(command)
            if step == "scripts/build_business_line_task_readback_manifest_from_runtime.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_task_readback_manifest.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            if step == "scripts/run_business_line_async_task_readback_live_samples.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/build_business_line_async_task_readback_artifact.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_async_task_readback_artifact.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            self.fail(f"unexpected command: {command}")

        with (
            patch.object(chain, "run_command", side_effect=fake_run_command),
            patch.object(
                chain,
                "fetch_evidence_matrix",
                return_value=chain.FetchResult(
                    status="passed",
                    payload={"schema_version": "business_line.evidence_matrix.v1", "lines": []},
                    http_status=200,
                    error=None,
                ),
            ),
        ):
            exit_code, report = self.run_main(self.base_argv(artifact_dir, "--allow-blocked"))

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", report["status"])
        self.assertTrue(report["allow_blocked"])
        self.assertIsNone(report["stopped_at"])
        self.assertEqual(report["chain_step_order"], [step["step"] for step in report["steps"]])
        self.assertEqual(
            [
                "scripts/build_business_line_task_readback_manifest_from_runtime.py",
                "scripts/check_business_line_task_readback_manifest.py",
                "scripts/run_business_line_async_task_readback_live_samples.py",
                "scripts/build_business_line_async_task_readback_artifact.py",
                "scripts/check_business_line_async_task_readback_artifact.py",
            ],
            [self.command_step(cmd) for cmd in commands],
        )
        self.assert_async_checker_uses_candidate_manifest(commands, artifact_dir)
        for filename in (
            "business-line-task-readback-manifest-candidate.json",
            "business-line-task-readback-manifest-check.json",
            "business-line-async-task-readback-live-samples.json",
            "business-line-evidence-matrix.json",
            "business-line-async-task-readback-artifact.json",
            "business-line-async-task-readback-check.json",
        ):
            with self.subTest(filename=filename):
                self.assertTrue((artifact_dir / filename).exists())

    def test_strict_failed_runner_stops_before_batch71_artifacts(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.assertNotIn("--allow-blocked", command)
            step = self.command_step(command)
            if step == "scripts/build_business_line_task_readback_manifest_from_runtime.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_task_readback_manifest.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            if step == "scripts/run_business_line_async_task_readback_live_samples.py":
                self.write_json(
                    self.command_output_path(command),
                    "failed",
                    reason="strict_live_readback_semantics_failed",
                )
                return chain.CommandResult(
                    exit_code=1,
                    stdout='{"status": "failed", "reason": "strict_live_readback_semantics_failed"}',
                    stderr="runner failed",
                )
            self.fail(f"unexpected command: {command}")

        with (
            patch.object(chain, "run_command", side_effect=fake_run_command),
            patch.object(chain, "fetch_evidence_matrix", side_effect=AssertionError("batch71 fetch should not run")),
        ):
            exit_code, report = self.run_main(self.base_argv(artifact_dir))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual("batch73_live_sample_runner", report["stopped_at"])
        self.assertEqual("live_sample_runner_not_passed", report["reason"])
        self.assertEqual("batch73_live_sample_runner", report["steps"][-1]["step"])
        self.assertEqual("failed", report["steps"][-1]["status"])
        self.assertEqual(
            [
                "scripts/build_business_line_task_readback_manifest_from_runtime.py",
                "scripts/check_business_line_task_readback_manifest.py",
                "scripts/run_business_line_async_task_readback_live_samples.py",
            ],
            [self.command_step(cmd) for cmd in commands],
        )
        live_samples = json.loads((artifact_dir / "business-line-async-task-readback-live-samples.json").read_text(encoding="utf-8"))
        self.assertEqual("strict_live_readback_semantics_failed", live_samples["reason"])
        self.assertFalse((artifact_dir / "business-line-evidence-matrix.json").exists())
        self.assertFalse((artifact_dir / "business-line-async-task-readback-artifact.json").exists())
        self.assertFalse((artifact_dir / "business-line-async-task-readback-check.json").exists())

    def test_async_task_checker_failed_stops_chain_at_batch71_checker(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.assertNotIn("--allow-blocked", command)
            step = self.command_step(command)
            if step == "scripts/build_business_line_task_readback_manifest_from_runtime.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_task_readback_manifest.py":
                return chain.CommandResult(exit_code=0, stdout=json.dumps({"status": "passed"}), stderr="")
            if step == "scripts/run_business_line_async_task_readback_live_samples.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/build_business_line_async_task_readback_artifact.py":
                self.write_json(self.command_output_path(command), "passed")
                return chain.CommandResult(exit_code=0, stdout='{"status": "passed"}', stderr="")
            if step == "scripts/check_business_line_async_task_readback_artifact.py":
                return chain.CommandResult(
                    exit_code=1,
                    stdout=json.dumps(
                        {
                            "schema_version": "business_line_async_task_readback_check.v1",
                            "status": "failed",
                            "artifact": {
                                "summary": {
                                    "worker_trace_missing_line_keys": ["ingest"],
                                },
                                "structural_failures": ["worker_trace_missing"],
                            },
                        }
                    ),
                    stderr="checker failed",
                )
            self.fail(f"unexpected command: {command}")

        with (
            patch.object(chain, "run_command", side_effect=fake_run_command),
            patch.object(
                chain,
                "fetch_evidence_matrix",
                return_value=chain.FetchResult(
                    status="passed",
                    payload={"schema_version": "business_line.evidence_matrix.v1", "lines": []},
                    http_status=200,
                    error=None,
                ),
            ),
        ):
            exit_code, report = self.run_main(self.base_argv(artifact_dir, "--allow-blocked"))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual("batch71_async_task_readback_checker", report["stopped_at"])
        self.assertEqual("async_task_checker_not_passed", report["reason"])
        self.assertEqual("batch71_async_task_readback_checker", report["steps"][-1]["step"])
        self.assertEqual("failed", report["steps"][-1]["status"])
        self.assertTrue((artifact_dir / "business-line-async-task-readback-check.json").exists())
        check_report = json.loads(
            (artifact_dir / "business-line-async-task-readback-check.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["ingest"], check_report["artifact"]["summary"]["worker_trace_missing_line_keys"])
        self.assertEqual(
            [
                "scripts/build_business_line_task_readback_manifest_from_runtime.py",
                "scripts/check_business_line_task_readback_manifest.py",
                "scripts/run_business_line_async_task_readback_live_samples.py",
                "scripts/build_business_line_async_task_readback_artifact.py",
                "scripts/check_business_line_async_task_readback_artifact.py",
            ],
            [self.command_step(cmd) for cmd in commands],
        )
        self.assert_async_checker_uses_candidate_manifest(commands, artifact_dir)

    def test_allow_blocked_returns_zero_but_status_not_passed(self) -> None:
        artifact_dir = self.make_artifact_dir()
        commands: list[list[str]] = []

        def fake_run_command(command: list[str], *, cwd: Path, timeout: float) -> object:
            commands.append(command)
            self.assertNotIn("--allow-blocked", command)
            self.write_json(self.command_output_path(command), "blocked_by_environment")
            return chain.CommandResult(exit_code=0, stdout='{"status": "blocked_by_environment"}', stderr="")

        with patch.object(chain, "run_command", side_effect=fake_run_command):
            exit_code, report = self.run_main(self.base_argv(artifact_dir, "--allow-blocked"))

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertNotEqual("passed", report["status"])
        self.assertEqual("batch75_candidate_builder", report["stopped_at"])
        self.assertEqual(["scripts/build_business_line_task_readback_manifest_from_runtime.py"], [self.command_step(cmd) for cmd in commands])


if __name__ == "__main__":
    unittest.main()
