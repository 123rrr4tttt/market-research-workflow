#!/usr/bin/env python3
"""Focused tests for Dashboard -> report closure artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_dashboard_report_closure_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_dashboard_report_closure_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class DashboardReportClosureArtifactTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, payload: object) -> Path:
        path = root / "dashboard-report-closure.json"
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def step(self, name: str, evidence: dict[str, object]) -> dict[str, object]:
        return {
            "name": name,
            "path": f"/api/v1/{name}",
            "http_status": 200,
            "status": checker.STATUS_PASSED,
            "evidence": evidence,
        }

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        trace_id = "dashboard-report:test-trace"
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "generated_at": "2026-05-25T00:00:00Z",
            "steps": [
                self.step("dashboard_stats_source_refs", {"documents_source_ref_count": 1}),
                self.step(
                    "dashboard_report_from_filter",
                    {
                        "trace_id": trace_id,
                        "document_id": 42,
                        "source_ref_count": 1,
                        "artifact_token_present": True,
                        "artifact_trace_id": trace_id,
                    },
                ),
                self.step(
                    "writing_markdown_export",
                    {"markdown_size_bytes": 128, "contains_dashboard_title": True},
                ),
                self.step(
                    "llm_report_pdf_export",
                    {"source_trace_id": trace_id, "readiness": "ready", "export_size_bytes": 1024},
                ),
                self.step(
                    "dashboard_llm_report_detail",
                    {
                        "found": True,
                        "source_ref_count": 1,
                        "artifact_present": True,
                        "quality_gate_status": "pass",
                        "export_event_count": 1,
                    },
                ),
            ],
            "failures": [],
            "evidence": {"trace_id": trace_id, "detail_found": True},
            "summary": {"passed_step_count": 5},
        }

    def test_passed_artifact_with_required_evidence_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, self.payload())

        report = checker.build_check(artifact)

        self.assertEqual(checker.CHECK_SCHEMA_VERSION, report["schema_version"])
        self.assertEqual(checker.STATUS_PASSED, report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual(18, report["summary"]["check_count"])
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_detail_without_export_events_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][4]["evidence"]["export_event_count"] = 0  # type: ignore[index]
        artifact = self.write_json(root, payload)

        report = checker.build_check(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertIn("detail.export_events", report["failures"])

    def test_artifact_trace_mismatch_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][1]["evidence"]["artifact_trace_id"] = "other-trace"  # type: ignore[index]
        artifact = self.write_json(root, payload)

        report = checker.build_check(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertIn("report.export_artifact_trace", report["failures"])

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["steps"] = [
            {
                "name": "dashboard_stats_source_refs",
                "status": checker.STATUS_BLOCKED,
                "http_status": None,
                "reason": "backend_unreachable",
                "evidence": {},
            }
        ]
        payload["failures"] = ["dashboard_stats_source_refs:backend_unreachable"]
        artifact = self.write_json(root, payload)

        self.assertEqual(checker.STATUS_BLOCKED, checker.build_check(artifact, allow_blocked=True)["status"])
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))


if __name__ == "__main__":
    unittest.main()
