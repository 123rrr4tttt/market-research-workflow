#!/usr/bin/env python3
"""Focused tests for scheduled automation artifact evidence classification."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_scheduled_automation_artifacts.py"
SPEC = importlib.util.spec_from_file_location("check_scheduled_automation_artifacts", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


PERF_DIR = Path("development/latest-dev-docs/automation-runs/performance-capacity-baseline/2026-05-24")
RETENTION_DIR = Path(
    "development/latest-dev-docs/automation-runs/llm-report-token-state-retention/2026-05-24"
)
MATRIX_DIR = Path(
    "development/latest-dev-docs/automation-runs/"
    "business-line-worker-readback-project-matrix/2026-05-24"
)


class ScheduledAutomationArtifactsTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        (root / "development/latest-dev-docs/automation-runs").mkdir(parents=True)
        return root

    def write_json(self, root: Path, rel_path: Path, payload: dict[str, object]) -> None:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    def write_text(self, root: Path, rel_path: Path, content: str) -> None:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def assert_artifact_identity(self, artifact: dict[str, object]) -> None:
        self.assertIn("size_bytes", artifact)
        self.assertIn("sha256", artifact)
        self.assertIsInstance(artifact["size_bytes"], int)
        self.assertGreater(artifact["size_bytes"], 0)
        self.assertIsInstance(artifact["sha256"], str)
        self.assertEqual(64, len(artifact["sha256"]))

    def assert_artifact_freshness(self, artifact: dict[str, object], *, rank: int, latest: bool) -> None:
        self.assertEqual(rank, artifact["freshness_rank"])
        self.assertIsInstance(artifact["freshness_window_size"], int)
        self.assertGreaterEqual(artifact["freshness_window_size"], rank)
        self.assertEqual(latest, artifact["is_latest_for_lane"])
        self.assertIsInstance(artifact["latest_artifact_path"], str)
        self.assertIsInstance(artifact["identity_matches_latest"], bool)
        self.assertIn("identity_status", artifact)
        self.assertIn("identity_warning", artifact)
        self.assertIn("identity_warning_severity", artifact)
        self.assertIn("identity_warning_message", artifact)
        if latest:
            self.assertEqual("latest", artifact["identity_status"])
            self.assertTrue(artifact["identity_matches_latest"])
            self.assertIsNone(artifact["identity_warning"])
            self.assertIsNone(artifact["identity_warning_severity"])
            self.assertIsNone(artifact["identity_warning_message"])

    def test_missing_artifacts_block_without_passing(self) -> None:
        report = checker.build_report(self.make_repo())

        self.assertEqual("blocked", report["status"])
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual(3, report["summary"]["lane_count"])
        self.assertEqual("scheduler_not_observed", report["summary"]["first_blocker_classification"])
        self.assertEqual("no_expected_nightly_artifact_files_found", report["summary"]["first_missing_reason"])
        self.assertEqual(
            {"scheduler_not_observed": 3},
            report["summary"]["blocker_classification_counts"],
        )
        self.assertEqual(
            [
                "scheduler_not_observed",
                "scheduler_configured_pending_run",
                "scheduler_ran_no_artifact",
                "artifact_wrong_path",
                "artifact_present_checker_mismatch",
                "scheduled_run_blocked",
            ],
            report["blocker_classifications"],
        )
        self.assertTrue(
            all(lane["classification"] == "missing" for lane in report["lanes"]),
            report["lanes"],
        )
        for lane in report["lanes"]:
            self.assertEqual("scheduler_not_observed", lane["blocker_classification"])
            self.assertEqual("no_expected_nightly_artifact_files_found", lane["first_missing_reason"])
            self.assertIsInstance(lane["expected_paths"], list)
            self.assertTrue(lane["expected_paths"])
            self.assertEqual(0, lane["identity_warning_count"])
            self.assertEqual([], lane["identity_warning_types"])
            self.assertEqual({}, lane["identity_warning_severity_counts"])
            self.assertEqual([], lane["identity_warning_severity_order"])
            self.assertIsNone(lane["identity_warning_highest_severity"])
            self.assertIsNone(lane["identity_warning_highest_severity_rank"])
            self.assertEqual({}, lane["identity_status_counts"])

    def test_matrix_lane_missing_blocks_without_artifact(self) -> None:
        report = checker.build_report(self.make_repo())
        matrix = next(
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual("missing", matrix["classification"])
        self.assertEqual("scheduler_not_observed", matrix["blocker_classification"])
        self.assertEqual("no_expected_nightly_artifact_files_found", matrix["first_missing_reason"])
        self.assertEqual(
            [
                "development/latest-dev-docs/automation-runs/"
                "business-line-worker-readback-project-matrix/*/nightly-manifest.json",
                "development/latest-dev-docs/automation-runs/"
                "business-line-worker-readback-project-matrix/*/"
                "business-line-worker-readback-project-matrix-report.json",
            ],
            matrix["expected_paths"],
        )
        self.assertEqual(
            "development/latest-dev-docs/automation-runs/"
            "business-line-worker-readback-project-matrix",
            matrix["base_dir"],
        )
        self.assertIsNone(matrix["artifact_path"])
        self.assertEqual(0, matrix["identity_warning_count"])
        self.assertEqual([], matrix["identity_warning_types"])
        self.assertEqual({}, matrix["identity_warning_severity_counts"])
        self.assertEqual([], matrix["identity_warning_severity_order"])
        self.assertIsNone(matrix["identity_warning_highest_severity"])
        self.assertIsNone(matrix["identity_warning_highest_severity_rank"])
        self.assertEqual({}, matrix["identity_status_counts"])
        self.assertIn("matrix nightly scheduler", matrix["recommended_command"])

    def test_matrix_missing_with_active_codex_automation_reports_configured_pending_run(self) -> None:
        root = self.make_repo()
        config_path = root / "codex-automation.toml"
        expected_cwd = str(root)
        config_path.write_text(
            "\n".join(
                [
                    'id = "mrw-business-line-worker-readback-project-matrix-nightly"',
                    'kind = "cron"',
                    'status = "ACTIVE"',
                    'rrule = "FREQ=HOURLY;INTERVAL=24"',
                    'execution_environment = "local"',
                    f'cwds = ["{expected_cwd}"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.write_json(
            root,
            Path(
                "development/latest-dev-docs/automation-runs/"
                "business-line-worker-readback-project-matrix/automation-spec.json"
            ),
            {
                "install_status": "installed_codex_app",
                "codex_app": {
                    "automation_id": "mrw-business-line-worker-readback-project-matrix-nightly",
                    "config_path": str(config_path),
                    "status": "ACTIVE",
                    "rrule": "FREQ=HOURLY;INTERVAL=24",
                    "cwd": expected_cwd,
                },
            },
        )

        report = checker.build_report(root)
        matrix = next(
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual(
            {
                "scheduler_not_observed": 2,
                "scheduler_configured_pending_run": 1,
            },
            report["summary"]["blocker_classification_counts"],
        )
        self.assertEqual(
            "scheduler_configured_pending_run",
            report["summary"]["first_blocker_classification"],
        )
        self.assertEqual("missing", matrix["classification"])
        self.assertEqual("scheduler_configured_pending_run", matrix["blocker_classification"])
        self.assertEqual(
            "scheduler_configured_but_no_expected_nightly_artifact_files_found",
            matrix["first_missing_reason"],
        )
        self.assertIn("scheduler automation is configured", matrix["reason"])
        self.assertIsNone(matrix["artifact_path"])
        self.assertEqual("configured_pending_run", matrix["scheduler_config"]["status"])
        self.assertIs(matrix["scheduler_config"]["configured"], True)
        self.assertEqual([], matrix["scheduler_config"]["problems"])
        self.assertEqual(
            "mrw-business-line-worker-readback-project-matrix-nightly",
            matrix["scheduler_config"]["automation_id"],
        )
        self.assertEqual("ACTIVE", matrix["scheduler_config"]["actual"]["status"])
        self.assertEqual("FREQ=HOURLY;INTERVAL=24", matrix["scheduler_config"]["actual"]["rrule"])
        self.assertIs(matrix["scheduler_config"]["cwd_matches"], True)

    def test_manual_dry_run_artifact_does_not_pass(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            RETENTION_DIR / "nightly-manifest.json",
            {
                "schema_version": "llm_report_token_state_retention_nightly_manifest.v1",
                "lane": "llm_report_token_state_retention_nightly",
                "mode": "dry_run",
                "retention_plan": {"dry_run": True},
            },
        )

        report = checker.build_report(root)
        retention = next(
            lane for lane in report["lanes"] if lane["lane"] == "llm_report_token_state_retention_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual("manual_dry_run", retention["classification"])
        self.assertEqual("artifact_present_checker_mismatch", retention["blocker_classification"])
        self.assertEqual(
            "artifact is marked dry_run and cannot close scheduled evidence",
            retention["first_missing_reason"],
        )
        self.assertEqual((RETENTION_DIR / "nightly-manifest.json").as_posix(), retention["artifact_path"])
        self.assert_artifact_identity(retention["artifacts"][0])
        self.assert_artifact_freshness(retention["artifacts"][0], rank=1, latest=True)
        self.assertIn("recommended_command", retention)

    def test_existing_artifact_without_scheduler_marker_is_manual_not_scheduled(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            PERF_DIR / "nightly-manifest.json",
            {
                "schema_version": "performance_capacity_nightly_manifest.v1",
                "lane": "performance_capacity_baseline_nightly",
                "status": "passed",
            },
        )

        report = checker.build_report(root)
        performance = next(
            lane for lane in report["lanes"] if lane["lane"] == "performance_capacity_baseline_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual("manual_dry_run", performance["classification"])
        self.assertEqual("artifact_present_checker_mismatch", performance["blocker_classification"])
        self.assertEqual(
            "artifact exists but lacks an explicit scheduled-run marker",
            performance["first_missing_reason"],
        )

    def test_matrix_manual_artifact_without_scheduler_marker_remains_blocked(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            MATRIX_DIR / "business-line-worker-readback-project-matrix-report.json",
            {
                "schema_version": "business_line_worker_readback_project_matrix_report.v1",
                "lane": "business_line_worker_readback_project_matrix_nightly",
                "status": "passed",
                "mode": "manual",
            },
        )

        report = checker.build_report(root)
        matrix_lanes = [
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        ]

        self.assertEqual("blocked", report["status"])
        self.assertEqual(1, len(matrix_lanes))
        self.assertEqual("manual_dry_run", matrix_lanes[0]["classification"])
        self.assertEqual("artifact_present_checker_mismatch", matrix_lanes[0]["blocker_classification"])
        self.assertEqual(
            (MATRIX_DIR / "business-line-worker-readback-project-matrix-report.json").as_posix(),
            matrix_lanes[0]["artifact_path"],
        )
        self.assertIn("lacks an explicit scheduled-run marker", matrix_lanes[0]["reason"])

    def test_matrix_scheduled_artifact_requires_payload_evidence(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            MATRIX_DIR / "nightly-manifest.json",
            {
                "schema_version": "business_line_worker_readback_project_matrix_manifest.v1",
                "lane": "business_line_worker_readback_project_matrix_nightly",
                "status": "passed",
                "matrix_report_status": "passed",
                "matrix_exit_code": 0,
                "scheduled_run_evidence": True,
                "run_source": "scheduled",
                "runtime_preflight": {"status": "passed", "start_exit_code": 0},
                "project_selection": {
                    "project_keys": ["demo_proj"],
                    "projects_api_url": "http://127.0.0.1:8000/api/v1/projects",
                },
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "duration_seconds": 1.5,
            },
        )

        report = checker.build_report(root)
        matrix_lanes = [
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        ]

        self.assertEqual("passed", report["status"])
        self.assertEqual(1, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual(1, len(matrix_lanes))
        matrix = matrix_lanes[0]
        self.assertEqual("scheduled_run_evidence", matrix["classification"])
        self.assertIsNone(matrix["blocker_classification"])
        self.assertIsNone(matrix["first_missing_reason"])
        self.assertEqual((MATRIX_DIR / "nightly-manifest.json").as_posix(), matrix["artifact_path"])
        self.assertEqual("passed", matrix["diagnostics"]["matrix_status"])
        self.assertEqual("passed", matrix["diagnostics"]["matrix_report_status"])
        self.assertEqual(0, matrix["diagnostics"]["matrix_exit_code"])
        self.assertEqual("passed", matrix["diagnostics"]["runtime_preflight_status"])
        self.assertEqual(0, matrix["diagnostics"]["runtime_preflight_start_exit_code"])
        self.assertEqual(["demo_proj"], matrix["diagnostics"]["project_keys"])
        self.assertEqual(
            "http://127.0.0.1:8000/api/v1/projects",
            matrix["diagnostics"]["projects_api_url"],
        )
        self.assertEqual(1, matrix["diagnostics"]["summary_total"])
        self.assertEqual(1.5, matrix["diagnostics"]["duration_seconds"])

    def test_matrix_scheduled_marker_without_payload_evidence_does_not_pass(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            MATRIX_DIR / "nightly-manifest.json",
            {
                "schema_version": "business_line_worker_readback_project_matrix_manifest.v1",
                "lane": "business_line_worker_readback_project_matrix_nightly",
                "status": "passed",
                "scheduled_run_evidence": True,
                "run_source": "scheduled",
                "project_selection": {"project_keys": []},
                "summary": {},
            },
        )

        report = checker.build_report(root)
        matrix = next(
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual("manual_dry_run", matrix["classification"])
        self.assertEqual("artifact_present_checker_mismatch", matrix["blocker_classification"])
        self.assertEqual((MATRIX_DIR / "nightly-manifest.json").as_posix(), matrix["artifact_path"])
        self.assertIn("lacks payload evidence", matrix["reason"])
        self.assertIn("non-empty project_selection.project_keys", matrix["reason"])
        self.assertIn("summary.total or total_projects > 0", matrix["reason"])

    def test_matrix_scheduled_artifact_with_blocked_status_is_not_manual_dry_run(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            MATRIX_DIR / "nightly-manifest.json",
            {
                "schema_version": "business_line_worker_readback_project_matrix_manifest.v1",
                "lane": "business_line_worker_readback_project_matrix_nightly",
                "status": "blocked_by_environment",
                "matrix_report_status": "blocked_by_environment",
                "matrix_exit_code": 1,
                "scheduled_run_evidence": True,
                "run_source": "scheduled",
                "runtime_preflight": {"status": "blocked_by_environment", "start_exit_code": 124},
                "project_selection": {
                    "project_keys": ["demo_proj"],
                    "projects_api_url": "http://127.0.0.1:8000/api/v1/projects",
                },
                "summary": {"total": 1, "passed": 0, "failed": 0, "blocked_by_environment": 1},
                "duration_seconds": 3.25,
            },
        )

        report = checker.build_report(root)
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
        self.assertEqual((MATRIX_DIR / "nightly-manifest.json").as_posix(), matrix["artifact_path"])
        self.assertIn("scheduler artifact present", matrix["reason"])
        self.assertIn("status/matrix_report_status is not passed/partial", matrix["reason"])
        self.assertEqual("blocked_by_environment", matrix["diagnostics"]["matrix_status"])
        self.assertEqual("blocked_by_environment", matrix["diagnostics"]["matrix_report_status"])
        self.assertEqual(1, matrix["diagnostics"]["matrix_exit_code"])
        self.assertEqual("blocked_by_environment", matrix["diagnostics"]["runtime_preflight_status"])
        self.assertEqual(124, matrix["diagnostics"]["runtime_preflight_start_exit_code"])
        self.assertEqual(["demo_proj"], matrix["diagnostics"]["project_keys"])
        self.assertEqual(
            "http://127.0.0.1:8000/api/v1/projects",
            matrix["diagnostics"]["projects_api_url"],
        )
        self.assertEqual(1, matrix["diagnostics"]["summary_total"])
        self.assertEqual(3.25, matrix["diagnostics"]["duration_seconds"])
        self.assertEqual(1, matrix["diagnostics"]["blocked_project_count"])
        self.assertEqual(0, matrix["diagnostics"]["failed_project_count"])
        self.assertEqual([], matrix["diagnostics"]["blocked_projects"])
        self.assertEqual([], matrix["diagnostics"]["failed_projects"])
        self.assertEqual({}, matrix["diagnostics"]["stopped_at_counts"])
        self.assertEqual({}, matrix["diagnostics"]["reason_counts"])
        self.assertIsNone(matrix["diagnostics"]["first_blocked_reason"])
        self.assertEqual(matrix["diagnostics"], matrix["artifacts"][0]["diagnostics"])
        json.dumps(report, sort_keys=True)

    def test_matrix_scheduled_blocked_artifact_uses_top_level_matrix_diagnostics(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            MATRIX_DIR / "nightly-manifest.json",
            {
                "schema_version": "business_line_worker_readback_project_matrix_manifest.v1",
                "lane": "business_line_worker_readback_project_matrix_nightly",
                "status": "blocked_by_environment",
                "matrix_report_status": "blocked_by_environment",
                "matrix_exit_code": 99,
                "scheduled_run_evidence": True,
                "run_source": "scheduled",
                "runtime_preflight": {"status": "legacy_blocked", "start_exit_code": 124},
                "project_selection": {
                    "project_keys": ["legacy_proj"],
                    "projects_api_url": "http://legacy.example.test/projects",
                },
                "summary": {"total": 1, "passed": 0, "failed": 0, "blocked": 1},
                "duration_seconds": 3.25,
                "matrix_diagnostics": {
                    "matrix_status": "diagnostic_blocked",
                    "matrix_report_status": "diagnostic_report_blocked",
                    "matrix_exit_code": 7,
                    "runtime_preflight_status": "diagnostic_preflight_blocked",
                    "runtime_preflight_start_exit_code": 125,
                    "project_keys": ["diag_proj", "", 123],
                    "projects_api_url": "http://diagnostic.example.test/projects",
                    "summary_total": 2,
                    "duration_seconds": 4.5,
                    "blocked_project_count": 2,
                    "failed_project_count": 1,
                    "blocked_projects": [
                        {
                            "project_key": "diag_proj",
                            "status": "blocked_by_environment",
                            "reason": "service_unavailable",
                            "stopped_at": "runtime_preflight",
                            "exit_code": 124,
                            "trigger_smoke_status": "skipped",
                        },
                        {
                            "project_key": "blocked_two",
                            "status": "blocked_by_environment",
                            "reason": "service_unavailable",
                            "stopped_at": "runtime_preflight",
                            "exit_code": 125,
                            "trigger_smoke_status": None,
                        },
                    ],
                    "failed_projects": [
                        {
                            "project_key": "failed_one",
                            "status": "failed",
                            "reason": "worker_readback_failed",
                            "stopped_at": "worker_readback",
                            "exit_code": 1,
                            "trigger_smoke_status": "failed",
                        }
                    ],
                    "stopped_at_counts": {"runtime_preflight": 2},
                    "reason_counts": {"service_unavailable": 2},
                    "first_blocked_reason": "service_unavailable",
                },
            },
        )

        report = checker.build_report(root)
        matrix = next(
            lane
            for lane in report["lanes"]
            if lane["lane"] == "business_line_worker_readback_project_matrix_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual("scheduled_run_blocked", matrix["classification"])
        self.assertEqual("scheduled_run_blocked", matrix["blocker_classification"])
        self.assertEqual("diagnostic_blocked", matrix["diagnostics"]["matrix_status"])
        self.assertEqual("diagnostic_report_blocked", matrix["diagnostics"]["matrix_report_status"])
        self.assertEqual(7, matrix["diagnostics"]["matrix_exit_code"])
        self.assertEqual("diagnostic_preflight_blocked", matrix["diagnostics"]["runtime_preflight_status"])
        self.assertEqual(125, matrix["diagnostics"]["runtime_preflight_start_exit_code"])
        self.assertEqual(["diag_proj"], matrix["diagnostics"]["project_keys"])
        self.assertEqual(
            "http://diagnostic.example.test/projects",
            matrix["diagnostics"]["projects_api_url"],
        )
        self.assertEqual(2, matrix["diagnostics"]["summary_total"])
        self.assertEqual(4.5, matrix["diagnostics"]["duration_seconds"])
        self.assertEqual(2, matrix["diagnostics"]["blocked_project_count"])
        self.assertEqual(1, matrix["diagnostics"]["failed_project_count"])
        self.assertEqual(
            [
                {
                    "project_key": "diag_proj",
                    "status": "blocked_by_environment",
                    "reason": "service_unavailable",
                    "stopped_at": "runtime_preflight",
                    "exit_code": 124,
                    "trigger_smoke_status": "skipped",
                },
                {
                    "project_key": "blocked_two",
                    "status": "blocked_by_environment",
                    "reason": "service_unavailable",
                    "stopped_at": "runtime_preflight",
                    "exit_code": 125,
                    "trigger_smoke_status": None,
                },
            ],
            matrix["diagnostics"]["blocked_projects"],
        )
        self.assertEqual(
            [
                {
                    "project_key": "failed_one",
                    "status": "failed",
                    "reason": "worker_readback_failed",
                    "stopped_at": "worker_readback",
                    "exit_code": 1,
                    "trigger_smoke_status": "failed",
                }
            ],
            matrix["diagnostics"]["failed_projects"],
        )
        self.assertEqual({"runtime_preflight": 2}, matrix["diagnostics"]["stopped_at_counts"])
        self.assertEqual({"service_unavailable": 2}, matrix["diagnostics"]["reason_counts"])
        self.assertEqual("service_unavailable", matrix["diagnostics"]["first_blocked_reason"])
        self.assertEqual(matrix["diagnostics"], matrix["artifacts"][0]["diagnostics"])
        json.dumps(report, sort_keys=True)

    def test_scheduled_marker_passes(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            PERF_DIR / "nightly-manifest.json",
            {
                "schema_version": "performance_capacity_nightly_manifest.v1",
                "lane": "performance_capacity_baseline_nightly",
                "status": "passed",
                "scheduled_run_evidence": True,
                "trigger": "codex_app_cron",
            },
        )

        report = checker.build_report(root)
        performance = next(
            lane for lane in report["lanes"] if lane["lane"] == "performance_capacity_baseline_nightly"
        )

        self.assertEqual("passed", report["status"])
        self.assertEqual(1, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual("scheduled_run_evidence", performance["classification"])
        self.assertIsNone(performance["blocker_classification"])
        self.assertIsNone(performance["first_missing_reason"])
        self.assertIsNotNone(performance["mtime"])
        self.assertIsNotNone(performance["observed_at"])
        self.assert_artifact_identity(performance["artifacts"][0])
        self.assert_artifact_freshness(performance["artifacts"][0], rank=1, latest=True)
        self.assertNotIn("diagnostics", performance)
        self.assertNotIn("diagnostics", performance["artifacts"][0])

    def test_artifact_freshness_window_marks_latest_and_stale_artifacts(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            PERF_DIR / "nightly-manifest.json",
            {
                "schema_version": "performance_capacity_nightly_manifest.v1",
                "lane": "performance_capacity_baseline_nightly",
                "status": "passed",
            },
        )
        self.write_json(
            root,
            PERF_DIR / "performance-baseline.json",
            {
                "schema_version": "performance_capacity_baseline.v1",
                "lane": "performance_capacity_baseline_nightly",
                "status": "passed",
            },
        )

        report = checker.build_report(root)
        performance = next(
            lane for lane in report["lanes"] if lane["lane"] == "performance_capacity_baseline_nightly"
        )
        artifacts = performance["artifacts"]

        self.assertEqual(2, len(artifacts))
        self.assert_artifact_freshness(artifacts[0], rank=1, latest=True)
        self.assert_artifact_freshness(artifacts[1], rank=2, latest=False)
        self.assertEqual(2, artifacts[0]["freshness_window_size"])
        self.assertEqual(2, artifacts[1]["freshness_window_size"])
        self.assertEqual(artifacts[0]["artifact_path"], artifacts[1]["latest_artifact_path"])
        self.assertFalse(artifacts[1]["identity_matches_latest"])
        self.assertEqual("differs_from_latest", artifacts[1]["identity_status"])
        self.assertEqual("artifact_identity_differs_from_latest", artifacts[1]["identity_warning"])
        self.assertEqual("warning", artifacts[1]["identity_warning_severity"])
        self.assertEqual(
            "Stale artifact identity differs from the latest artifact.",
            artifacts[1]["identity_warning_message"],
        )
        self.assertEqual(1, performance["identity_warning_count"])
        self.assertEqual(
            ["artifact_identity_differs_from_latest"],
            performance["identity_warning_types"],
        )
        self.assertEqual({"warning": 1}, performance["identity_warning_severity_counts"])
        self.assertEqual(["warning"], performance["identity_warning_severity_order"])
        self.assertEqual("warning", performance["identity_warning_highest_severity"])
        self.assertIsInstance(performance["identity_warning_highest_severity_rank"], int)
        self.assertGreater(performance["identity_warning_highest_severity_rank"], 0)
        self.assertEqual(
            {"latest": 1, "differs_from_latest": 1},
            performance["identity_status_counts"],
        )
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])

    def test_stale_artifact_with_latest_identity_has_no_identity_warning(self) -> None:
        root = self.make_repo()
        payload = {
            "schema_version": "performance_capacity_nightly_manifest.v1",
            "lane": "performance_capacity_baseline_nightly",
            "status": "passed",
        }
        latest_rel = PERF_DIR / "nightly-manifest.json"
        stale_rel = PERF_DIR / "performance-baseline.json"
        self.write_json(root, latest_rel, payload)
        self.write_json(root, stale_rel, payload)
        os.utime(root / stale_rel, (1_700_000_000, 1_700_000_000))
        os.utime(root / latest_rel, (1_700_000_100, 1_700_000_100))

        report = checker.build_report(root)
        performance = next(
            lane for lane in report["lanes"] if lane["lane"] == "performance_capacity_baseline_nightly"
        )
        artifacts = performance["artifacts"]

        self.assertEqual("blocked", report["status"])
        self.assertEqual("manual_dry_run", performance["classification"])
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual(2, len(artifacts))
        self.assertEqual(latest_rel.as_posix(), artifacts[0]["artifact_path"])
        self.assertEqual(stale_rel.as_posix(), artifacts[1]["artifact_path"])
        self.assert_artifact_freshness(artifacts[0], rank=1, latest=True)
        self.assert_artifact_freshness(artifacts[1], rank=2, latest=False)
        self.assertEqual(artifacts[0]["sha256"], artifacts[1]["sha256"])
        self.assertEqual(artifacts[0]["size_bytes"], artifacts[1]["size_bytes"])
        self.assertTrue(artifacts[1]["identity_matches_latest"])
        self.assertEqual("same_as_latest", artifacts[1]["identity_status"])
        self.assertIsNone(artifacts[1]["identity_warning"])
        self.assertIsNone(artifacts[1]["identity_warning_severity"])
        self.assertIsNone(artifacts[1]["identity_warning_message"])
        self.assertEqual(0, performance["identity_warning_count"])
        self.assertEqual([], performance["identity_warning_types"])
        self.assertEqual({}, performance["identity_warning_severity_counts"])
        self.assertEqual([], performance["identity_warning_severity_order"])
        self.assertIsNone(performance["identity_warning_highest_severity"])
        self.assertIsNone(performance["identity_warning_highest_severity_rank"])
        self.assertEqual(
            {"latest": 1, "same_as_latest": 1},
            performance["identity_status_counts"],
        )

    def test_wrapper_scheduler_source_marker_passes(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            RETENTION_DIR / "nightly-manifest.json",
            {
                "schema_version": "llm_report_token_state_retention_nightly_manifest.v1",
                "lane": "llm_report_token_state_retention_nightly",
                "trigger": "codex_app_scheduler",
                "source": "codex_app",
                "run_source": "scheduled",
                "execution_source": "scheduled",
            },
        )

        report = checker.build_report(root)
        retention = next(
            lane for lane in report["lanes"] if lane["lane"] == "llm_report_token_state_retention_nightly"
        )

        self.assertEqual("passed", report["status"])
        self.assertEqual("scheduled_run_evidence", retention["classification"])

    def test_scheduler_marker_with_dry_run_does_not_pass(self) -> None:
        root = self.make_repo()
        self.write_json(
            root,
            RETENTION_DIR / "nightly-manifest.json",
            {
                "schema_version": "llm_report_token_state_retention_nightly_manifest.v1",
                "lane": "llm_report_token_state_retention_nightly",
                "mode": "dry_run",
                "trigger": "codex_app_scheduler",
                "source": "codex_app",
                "run_source": "scheduled",
                "execution_source": "scheduled",
            },
        )

        report = checker.build_report(root)
        retention = next(
            lane for lane in report["lanes"] if lane["lane"] == "llm_report_token_state_retention_nightly"
        )

        self.assertEqual("blocked", report["status"])
        self.assertEqual(0, report["summary"]["scheduled_run_evidence_count"])
        self.assertEqual("manual_dry_run", retention["classification"])
        self.assertIn("dry_run", retention["reason"])


if __name__ == "__main__":
    unittest.main()
