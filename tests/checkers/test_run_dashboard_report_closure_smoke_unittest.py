#!/usr/bin/env python3
"""Focused tests for Dashboard -> report closure smoke artifact behavior."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_dashboard_report_closure_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_dashboard_report_closure_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class DashboardReportClosureSmokeTestCase(unittest.TestCase):
    def make_output_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "artifact.json"

    def json_response(self, data: dict[str, object], status_code: int = 200) -> object:
        return smoke.HttpResult(
            status_code=status_code,
            body=json.dumps({"status": "ok", "data": data, "error": None, "meta": {}}).encode("utf-8"),
            headers={},
        )

    def test_passed_flow_writes_dashboard_report_closure_evidence(self) -> None:
        output = self.make_output_path()
        trace_id = "dashboard-report:test-trace"
        report_data = {
            "trace_id": trace_id,
            "document_id": 42,
            "draft_id": 42,
            "source_refs": [{"id": "dashboard.stats.documents"}],
            "report_quality_gate": {"status": "pass"},
            "export_artifact": {
                "artifact_token": "llmrpt-v1.test",
                "artifact_sha256": "a" * 64,
                "trace_id": trace_id,
            },
        }

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith("/api/v1/dashboard/stats"):
                return self.json_response(
                    {
                        "documents": {"source_refs": [{"id": "dashboard.stats.documents"}]},
                        "pending_actions": [],
                        "llm_report_quality": {},
                    }
                )
            if "/api/v1/dashboard/llm-report-detail?" in url:
                return self.json_response(
                    {
                        "found": True,
                        "trace_id": trace_id,
                        "source_refs": [{"id": "dashboard.stats.documents"}],
                        "report_artifact": {"artifact_id": "artifact-1"},
                        "quality_gate": {"status": "pass"},
                        "export_events": [{"trace_id": "export-1", "source_trace_id": trace_id}],
                        "export_events_summary": {"total": 1},
                        "actionability": {"next_action": "review_llm_report_detail"},
                    }
                )
            raise AssertionError(f"unexpected GET {url}")

        def fake_post_json(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith("/api/v1/dashboard/report-from-filter"):
                return self.json_response(report_data)
            raise AssertionError(f"unexpected JSON POST {url}")

        def fake_post_markdown(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith("/api/v1/writing/export/markdown"):
                return smoke.HttpResult(
                    status_code=200,
                    body=b"# Dashboard report draft - Documents\n\nbody",
                    headers={"content-disposition": "attachment; filename=writing-document-42.md"},
                )
            raise AssertionError(f"unexpected markdown POST {url}")

        def fake_post_binary(url: str, payload: dict[str, object], *, timeout: float, accept: str) -> object:
            if url.endswith("/api/v1/llm-report/export/pdf"):
                return smoke.HttpResult(
                    status_code=200,
                    body=b"%PDF-1.4\n",
                    headers={
                        "x-llm-report-export-readiness": "ready",
                        "x-llm-report-export-format": "pdf",
                        "x-llm-report-export-integrity": "artifact_token",
                        "x-llm-report-source-trace-id": trace_id,
                    },
                )
            raise AssertionError(f"unexpected binary POST {url}")

        with (
            patch.object(smoke, "_http_get_json", side_effect=fake_get),
            patch.object(smoke, "_http_post_json", side_effect=fake_post_json),
            patch.object(smoke, "_http_post_markdown", side_effect=fake_post_markdown),
            patch.object(smoke, "_http_post_binary", side_effect=fake_post_binary),
        ):
            artifact = smoke.build_artifact(
                api_base="http://127.0.0.1:8000",
                project_key="demo_proj",
                output=output,
                timeout=5,
            )

        self.assertEqual(smoke.STATUS_PASSED, artifact["status"])
        self.assertEqual([], artifact["failures"])
        self.assertEqual(5, artifact["summary"]["passed_step_count"])
        self.assertEqual(trace_id, artifact["evidence"]["trace_id"])
        self.assertEqual(42, artifact["evidence"]["document_id"])
        self.assertTrue(artifact["evidence"]["detail_found"])
        self.assertEqual(1, artifact["evidence"]["detail_export_event_count"])

    def test_backend_unreachable_is_blocked(self) -> None:
        output = self.make_output_path()
        with patch.object(
            smoke,
            "_http_get_json",
            return_value=smoke.HttpResult(status_code=None, body=b"", headers={}, error="connection refused"),
        ):
            artifact = smoke.build_artifact(
                api_base="http://127.0.0.1:8000",
                project_key="demo_proj",
                output=output,
                timeout=5,
            )

        self.assertEqual(smoke.STATUS_BLOCKED, artifact["status"])
        self.assertIn("dashboard_stats_source_refs:backend_unreachable", artifact["failures"])


if __name__ == "__main__":
    unittest.main()
