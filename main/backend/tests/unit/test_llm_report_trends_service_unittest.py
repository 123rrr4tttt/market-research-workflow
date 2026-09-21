from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.unit, pytest.mark.mocked]

try:
    from app.services import llm_report_trends

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class LlmReportTrendsServiceTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"llm report trends service tests require backend dependencies: {_IMPORT_ERROR}")
        llm_report_trends.clear_quality_trend_memory()

    def tearDown(self):
        if _IMPORT_ERROR is None:
            llm_report_trends.clear_quality_trend_memory()

    def test_record_quality_trend_metric_keeps_memory_when_database_write_degrades(self):
        with patch("app.services.llm_report_trends.run_with_session_retry", side_effect=RuntimeError("db down")):
            recorded = llm_report_trends.record_quality_trend_metric(
                {
                    "contract_version": "llm_report.quality_trend_metric.v1",
                    "trace_id": "trace-degraded",
                    "project_key": "demo_proj",
                    "decision": "warn",
                    "pass": True,
                    "citation_coverage": 0.75,
                    "evidence_coverage": 0.5,
                    "readiness": "review_required",
                    "next_action": "review_sources",
                },
                job_id=7101,
                topic="degraded trend",
                job_status="completed",
            )

        self.assertTrue(recorded["trend_store_degraded"])
        with (
            patch("app.services.llm_report_trends._load_database_quality_trends", return_value=([], True)),
            patch("app.services.llm_report_trends.list_jobs", return_value=[]),
        ):
            records, storage = llm_report_trends.list_quality_trend_records(limit=5, project_key="demo_proj")

        self.assertEqual(records[0]["trace_id"], "trace-degraded")
        self.assertEqual(records[0]["record_source"], "generate")
        self.assertTrue(storage["database_degraded"])
        self.assertFalse(storage["job_log_degraded"])
        self.assertEqual(storage["memory_count"], 1)

    def test_list_quality_trend_records_prefers_database_over_job_log_duplicate(self):
        database_record = {
            "trace_id": "trace-db",
            "project_key": "demo_proj",
            "decision": "fail",
            "recorded_at": "2026-05-24T10:00:00+00:00",
            "record_source": "trend_table",
        }
        duplicate_job_record = {
            "trace_id": "trace-db",
            "project_key": "demo_proj",
            "decision": "fail",
            "recorded_at": "2026-05-24T09:00:00+00:00",
            "record_source": "job_log",
        }
        job_only_record = {
            "trace_id": "trace-job",
            "project_key": "demo_proj",
            "decision": "fail",
            "recorded_at": "2026-05-24T08:00:00+00:00",
            "record_source": "job_log",
        }
        with (
            patch(
                "app.services.llm_report_trends._load_database_quality_trends",
                return_value=([database_record], False),
            ),
            patch(
                "app.services.llm_report_trends._load_persisted_quality_trends",
                return_value=([duplicate_job_record, job_only_record], False),
            ),
        ):
            records, storage = llm_report_trends.list_quality_trend_records(
                limit=5,
                project_key="demo_proj",
                decision="fail",
            )

        self.assertEqual([record["trace_id"] for record in records], ["trace-db", "trace-job"])
        self.assertEqual(records[0]["record_source"], "trend_table")
        self.assertEqual(storage["database_count"], 1)
        self.assertEqual(storage["job_log_count"], 2)
        self.assertEqual(storage["persisted_count"], 3)
        self.assertEqual(storage["merged_count"], 2)

    def test_summarize_quality_trends_counts_export_events(self):
        summary = llm_report_trends.summarize_quality_trends(
            [
                {
                    "trace_id": "trace-generate",
                    "decision": "pass",
                    "readiness": "ready",
                    "project_key": "demo_proj",
                    "citation_coverage": 1.0,
                    "evidence_coverage": 0.8,
                },
                {
                    "contract_version": "llm_report.export_trend_metric.v1",
                    "event_type": "llm_report_export",
                    "record_source": "export",
                    "trace_id": "trace-export-success",
                    "decision": "pass",
                    "readiness": "ready",
                    "project_key": "demo_proj",
                    "export_format": "pdf",
                    "export_outcome": "success",
                    "export_integrity_mode": "artifact_token",
                    "export_integrity_trusted": True,
                    "ui_read_only_context_included": True,
                },
                {
                    "contract_version": "llm_report.export_trend_metric.v1",
                    "event_type": "llm_report_export",
                    "record_source": "export",
                    "trace_id": "trace-export-token-invalid",
                    "decision": "fail",
                    "readiness": "blocked",
                    "project_key": "demo_proj",
                    "export_format": "docx",
                    "export_outcome": "token_invalid",
                    "export_integrity_mode": "artifact_token",
                    "export_integrity_trusted": False,
                    "ui_read_only_context_included": "true",
                },
                {
                    "contract_version": "llm_report.export_trend_metric.v1",
                    "event_type": "llm_report_export",
                    "record_source": "export",
                    "trace_id": "trace-export-legacy",
                    "decision": "warn",
                    "readiness": "review_required",
                    "project_key": "demo_proj",
                    "export_format": "markdown",
                    "export_outcome": "success",
                    "export_integrity_mode": "legacy_payload_gate",
                    "export_integrity_trusted": False,
                    "ui_read_only_context_included": False,
                },
                {
                    "contract_version": "llm_report.export_trend_metric.v1",
                    "event_type": "llm_report_export",
                    "record_source": "export",
                    "trace_id": "trace-export-missing-context",
                    "decision": "fail",
                    "readiness": "blocked",
                    "project_key": "demo_proj",
                    "export_format": "pdf",
                    "export_outcome": "blocked",
                    "export_integrity_mode": "artifact_token",
                    "export_integrity_trusted": True,
                },
            ]
        )

        empty_export_events = llm_report_trends.summarize_quality_trends([])["export_events"]
        self.assertEqual(empty_export_events["ui_read_only_context_included_count"], 0)
        self.assertEqual(summary["export_events"]["total"], 4)
        self.assertEqual(summary["export_events"]["success"], 2)
        self.assertEqual(summary["export_events"]["blocked"], 1)
        self.assertEqual(summary["export_events"]["token_invalid"], 1)
        self.assertEqual(summary["export_events"]["legacy"], 1)
        self.assertEqual(summary["export_events"]["trusted"], 2)
        self.assertEqual(summary["export_events"]["ui_read_only_context_included_count"], 1)
        self.assertEqual(summary["export_events"]["by_format"], {"pdf": 2, "docx": 1, "markdown": 1})
        self.assertEqual(summary["export_events"]["by_integrity_mode"]["artifact_token"], 3)
        self.assertEqual(
            set(summary["export_events"].keys()),
            {
                "total",
                "success",
                "blocked",
                "token_invalid",
                "failed",
                "legacy",
                "trusted",
                "ui_read_only_context_included_count",
                "by_format",
                "by_integrity_mode",
            },
        )

    def test_build_export_trend_metric_distinguishes_strict_blocked_from_compatible_success(self):
        strict_blocked = llm_report_trends.build_export_trend_metric(
            export_format="pdf",
            outcome="blocked",
            gate={
                "decision": "fail",
                "hard_failures": ["citation_coverage_below_threshold"],
                "soft_failures": [],
                "missing_items": ["source_citation"],
            },
            export_readiness={
                "readiness": "blocked",
                "quality_gate_decision": "fail",
                "quality_gate_mode": "strict",
                "quality_gate_mode_raw": "strict",
                "quality_gate_mode_fallback": False,
                "strict_gate_blocks_export": True,
                "next_action": "fix_quality_gate_blockers_before_export",
            },
            integrity={
                "mode": "artifact_token",
                "trusted": True,
                "trace_id": "trace-generate-strict",
                "request_id": "request-strict",
                "project_key": "demo_proj",
                "job_id": 9001,
                "actor_id": "analyst-1",
            },
            project_key="demo_proj",
            request_id="request-strict",
            job_id=9001,
            artifact_id="artifact-strict",
            artifact_sha256="a" * 64,
            filename="blocked.pdf",
            content_type="application/pdf",
            error_code="QUALITY_GATE_BLOCKED",
        )
        compatible_success = llm_report_trends.build_export_trend_metric(
            export_format="pdf",
            outcome="success",
            gate={"decision": "fail", "hard_failures": ["citation_coverage_below_threshold"], "soft_failures": []},
            export_readiness={
                "readiness": "review_required",
                "quality_gate_decision": "fail",
                "quality_gate_mode": "warn",
                "quality_gate_mode_raw": "compatible",
                "quality_gate_mode_fallback": False,
                "strict_gate_blocks_export": False,
                "next_action": "review_quality_gate_failures_before_export",
            },
            integrity={
                "mode": "legacy_payload_gate",
                "trusted": False,
                "project_key": "demo_proj",
                "actor_id": "anonymous",
            },
            project_key="demo_proj",
            request_id=None,
            job_id=None,
            artifact_id=None,
            artifact_sha256=None,
            filename="compatible.pdf",
            content_type="application/pdf",
        )

        self.assertEqual(strict_blocked["audit_event"]["outcome"], "blocked")
        self.assertTrue(strict_blocked["audit_event"]["strict_gate_blocked"])
        self.assertFalse(strict_blocked["audit_event"]["compatible_quality_gate_path"])
        self.assertEqual(strict_blocked["source_ref"]["id"], "artifact-strict")
        self.assertEqual(strict_blocked["header_snapshot"]["format"], "pdf")
        self.assertEqual(strict_blocked["header_snapshot"]["readiness"], "blocked")
        self.assertEqual(strict_blocked["header_snapshot"]["quality_gate_mode"], "strict")

        self.assertEqual(compatible_success["audit_event"]["outcome"], "success")
        self.assertFalse(compatible_success["audit_event"]["strict_gate_blocked"])
        self.assertTrue(compatible_success["audit_event"]["compatible_quality_gate_path"])
        self.assertEqual(compatible_success["export_integrity_mode"], "legacy_payload_gate")
        self.assertEqual(compatible_success["header_snapshot"]["readiness"], "review_required")
        self.assertEqual(compatible_success["header_snapshot"]["quality_gate_mode"], "warn")


if __name__ == "__main__":
    unittest.main()
