from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.unit, pytest.mark.mocked]

try:
    from app.services import llm_report_export_audit

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    llm_report_export_audit = None
    _IMPORT_ERROR = exc


def _event(**overrides):
    record = {
        "trace_id": "trace-export-success",
        "source_trace_id": "trace-generate-1",
        "request_id": "request-1",
        "project_key": "demo_proj",
        "actor_id": "analyst-1",
        "job_id": 1001,
        "artifact_id": "artifact-1",
        "artifact_sha256": "a" * 64,
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "content_size_bytes": 4096,
        "export_format": "pdf",
        "outcome": "success",
        "readiness": "ready",
        "quality_gate_decision": "pass",
        "quality_gate_mode": "strict",
        "integrity_mode": "artifact_token",
        "integrity_trusted": True,
        "error_code": None,
    }
    record.update(overrides)
    return record


def _clear_audit_state():
    if llm_report_export_audit is None:
        return
    clear_fn = getattr(llm_report_export_audit, "clear_llm_report_export_audit_memory", None)
    if callable(clear_fn):
        clear_fn()
    memory = getattr(llm_report_export_audit, "_LLM_REPORT_EXPORT_AUDIT_EVENTS", None)
    if isinstance(memory, list):
        memory.clear()


class LlmReportExportAuditServiceTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(
                f"llm report export audit service tests require service implementation: {_IMPORT_ERROR}"
            )
        _clear_audit_state()

    def tearDown(self):
        _clear_audit_state()

    def test_record_export_audit_event_returns_structured_fields(self):
        with patch(
            "app.services.llm_report_export_audit.run_with_session_retry",
            return_value=True,
            create=True,
        ):
            recorded = llm_report_export_audit.record_llm_report_export_audit_event(_event())

        self.assertEqual(recorded["contract_version"], "llm_report.export_audit_event.v1")
        self.assertEqual(recorded["event_type"], "llm_report_export")
        self.assertEqual(recorded["record_source"], "export_audit")
        self.assertEqual(recorded["trace_id"], "trace-export-success")
        self.assertEqual(recorded["source_trace_id"], "trace-generate-1")
        self.assertEqual(recorded["request_id"], "request-1")
        self.assertEqual(recorded["project_key"], "demo_proj")
        self.assertEqual(recorded["actor_id"], "analyst-1")
        self.assertEqual(recorded["job_id"], 1001)
        self.assertEqual(recorded["artifact_id"], "artifact-1")
        self.assertEqual(recorded["export_format"], "pdf")
        self.assertEqual(recorded["outcome"], "success")
        self.assertEqual(recorded["integrity_mode"], "artifact_token")
        self.assertTrue(recorded["integrity_trusted"])
        self.assertEqual(recorded["content_size_bytes"], 4096)
        self.assertEqual(recorded["readiness"], "ready")
        self.assertEqual(recorded["quality_gate_decision"], "pass")
        self.assertEqual(recorded["quality_gate_mode"], "strict")
        self.assertEqual(recorded["source_ref"]["id"], "artifact-1")
        self.assertEqual(recorded["source_ref"]["source_trace_id"], "trace-generate-1")
        self.assertEqual(recorded["governance"]["format"], "pdf")
        self.assertEqual(recorded["governance"]["readiness"], "ready")
        self.assertEqual(recorded["governance"]["quality_gate"]["decision"], "pass")
        self.assertEqual(recorded["audit_event"]["outcome"], "success")
        self.assertFalse(recorded["audit_event"]["strict_gate_blocked"])
        self.assertEqual(recorded["header_snapshot"]["format"], "pdf")
        self.assertEqual(recorded["header_snapshot"]["readiness"], "ready")
        self.assertEqual(recorded["header_snapshot"]["quality_gate_decision"], "pass")
        self.assertEqual(recorded["header_snapshot"]["quality_gate_mode"], "strict")
        self.assertEqual(recorded["header_snapshot"]["source_ref"], "artifact-1")
        self.assertIn("recorded_at", recorded)
        self.assertFalse(recorded.get("export_audit_store_degraded", False))

    def test_record_blocked_export_marks_strict_governance_event(self):
        with patch(
            "app.services.llm_report_export_audit.run_with_session_retry",
            return_value=True,
            create=True,
        ):
            recorded = llm_report_export_audit.record_llm_report_export_audit_event(
                _event(
                    trace_id="trace-export-blocked",
                    outcome="blocked",
                    readiness="blocked",
                    quality_gate_decision="fail",
                    quality_gate_mode="strict",
                    strict_gate_blocks_export=True,
                    error_code="QUALITY_GATE_BLOCKED",
                )
            )

        self.assertEqual(recorded["outcome"], "blocked")
        self.assertEqual(recorded["audit_event"]["outcome"], "blocked")
        self.assertTrue(recorded["audit_event"]["strict_gate_blocked"])
        self.assertFalse(recorded["audit_event"]["compatible_quality_gate_path"])
        self.assertEqual(recorded["governance"]["quality_gate"]["mode"], "strict")
        self.assertEqual(recorded["header_snapshot"]["readiness"], "blocked")

    def test_ui_read_only_context_trace_is_normalized_persisted_and_listed_without_rollup_failure(self):
        with patch(
            "app.services.llm_report_export_audit.run_with_session_retry",
            return_value=True,
            create=True,
        ):
            recorded = llm_report_export_audit.record_llm_report_export_audit_event(
                _event(
                    trace_id="trace-ui-read-only-context",
                    ui_read_only_context_included="true",
                    ui_read_only_context_scope="ui_read_only_evidence_context",
                    ui_read_only_context_source="business_lines.evidence_matrix.async_task_readback_extension",
                )
            )

        self.assertTrue(recorded["ui_read_only_context_included"])
        self.assertEqual(recorded["ui_read_only_context_scope"], "ui_read_only_evidence_context")
        self.assertEqual(
            recorded["ui_read_only_context_source"],
            "business_lines.evidence_matrix.async_task_readback_extension",
        )
        self.assertEqual(
            recorded["ui_read_only_context_reason"],
            "reset_telemetry_boundary_context_rendered_as_read_only_export_boundary_note",
        )
        self.assertTrue(recorded["audit_event"]["ui_read_only_context_included"])
        self.assertEqual(
            recorded["governance"]["ui_read_only_context"]["ui_read_only_context_scope"],
            "ui_read_only_evidence_context",
        )
        self.assertEqual(recorded["outcome"], "success")
        self.assertEqual(recorded["quality_gate_decision"], "pass")
        self.assertFalse(recorded["audit_event"]["strict_gate_blocked"])

        row = llm_report_export_audit.LlmReportExportAuditEvent()
        llm_report_export_audit._apply_record_to_row(row, recorded)
        persisted = llm_report_export_audit._row_to_record(row)
        self.assertTrue(persisted["ui_read_only_context_included"])
        self.assertEqual(persisted["ui_read_only_context_scope"], "ui_read_only_evidence_context")

        with patch(
            "app.services.llm_report_export_audit._load_database_export_audit_events",
            return_value=([], False),
        ):
            records = llm_report_export_audit.list_recent_llm_report_export_audit_events(
                limit=5,
                project_key="demo_proj",
            )
        self.assertEqual(records[0]["trace_id"], "trace-ui-read-only-context")
        self.assertTrue(records[0]["ui_read_only_context_included"])

        summary = llm_report_export_audit.summarize_llm_report_export_audit_events(
            [
                recorded,
                _event(trace_id="trace-raw-string-context", ui_read_only_context_included="true"),
                _event(trace_id="trace-false-context", ui_read_only_context_included=False),
            ]
        )
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["success"], 3)
        self.assertEqual(summary["blocked"], 0)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["ui_read_only_context_included_count"], 1)

    def test_summarize_export_audit_events_counts_required_rollups(self):
        summary = llm_report_export_audit.summarize_llm_report_export_audit_events(
            [
                _event(
                    trace_id="trace-success-pdf",
                    export_format="pdf",
                    outcome="success",
                    ui_read_only_context_included=True,
                ),
                _event(
                    trace_id="trace-blocked-docx",
                    export_format="docx",
                    outcome="blocked",
                    readiness="blocked",
                    quality_gate_decision="fail",
                    integrity_mode="artifact_token",
                    integrity_trusted=False,
                    error_code="QUALITY_GATE_BLOCKED",
                    ui_read_only_context_included="true",
                ),
                _event(
                    trace_id="trace-failed-markdown",
                    export_format="markdown",
                    outcome="failed",
                    integrity_mode="legacy_payload_gate",
                    integrity_trusted=False,
                    error_code="EXPORT_RENDER_FAILED",
                ),
                _event(
                    trace_id="trace-token-invalid",
                    export_format="pdf",
                    outcome="token_invalid",
                    integrity_mode="artifact_token",
                    integrity_trusted=False,
                    error_code="EXPORT_TOKEN_INVALID",
                ),
            ]
        )

        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["success"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["token_invalid"], 1)
        self.assertEqual(summary["trusted"], 1)
        self.assertEqual(summary["legacy"], 1)
        self.assertEqual(summary["ui_read_only_context_included_count"], 1)
        self.assertEqual(summary["by_format"], {"pdf": 2, "docx": 1, "markdown": 1})
        self.assertEqual(
            summary["by_outcome"],
            {"success": 1, "blocked": 1, "failed": 1, "token_invalid": 1},
        )
        self.assertEqual(summary["by_integrity_mode"], {"artifact_token": 3, "legacy_payload_gate": 1})

    def test_list_recent_export_audit_events_supports_service_filters(self):
        events = [
            _event(
                trace_id="trace-target",
                recorded_at="2026-05-24T12:00:00+00:00",
                project_key="demo_proj",
                actor_id="analyst-1",
                export_format="pdf",
                outcome="success",
            ),
            _event(
                trace_id="trace-other-project",
                recorded_at="2026-05-24T11:00:00+00:00",
                project_key="other_proj",
                actor_id="analyst-1",
                export_format="pdf",
                outcome="success",
            ),
            _event(
                trace_id="trace-other-actor",
                recorded_at="2026-05-24T10:00:00+00:00",
                project_key="demo_proj",
                actor_id="analyst-2",
                export_format="docx",
                outcome="blocked",
            ),
        ]

        loader_name = "_load_database_export_audit_events"
        if hasattr(llm_report_export_audit, loader_name):
            with patch(
                f"app.services.llm_report_export_audit.{loader_name}",
                return_value=(events, False),
            ):
                records = llm_report_export_audit.list_recent_llm_report_export_audit_events(
                    limit=10,
                    project_key="demo_proj",
                    actor_id="analyst-1",
                    export_format="pdf",
                    outcome="success",
                )
        else:
            with patch(
                "app.services.llm_report_export_audit.run_with_session_retry",
                side_effect=RuntimeError("db down"),
                create=True,
            ):
                for event in events:
                    llm_report_export_audit.record_llm_report_export_audit_event(event)
                records = llm_report_export_audit.list_recent_llm_report_export_audit_events(
                    limit=10,
                    project_key="demo_proj",
                    actor_id="analyst-1",
                    export_format="pdf",
                    outcome="success",
                )

        self.assertEqual([record["trace_id"] for record in records], ["trace-target"])
        self.assertEqual(records[0]["project_key"], "demo_proj")
        self.assertEqual(records[0]["actor_id"], "analyst-1")
        self.assertEqual(records[0]["export_format"], "pdf")
        self.assertEqual(records[0]["outcome"], "success")

    def test_database_unavailable_degrades_without_raising(self):
        with patch(
            "app.services.llm_report_export_audit.run_with_session_retry",
            side_effect=RuntimeError("db down"),
            create=True,
        ):
            recorded = llm_report_export_audit.record_llm_report_export_audit_event(
                _event(trace_id="trace-db-down")
            )
            records = llm_report_export_audit.list_recent_llm_report_export_audit_events(
                limit=5,
                project_key="demo_proj",
            )

        self.assertEqual(recorded["trace_id"], "trace-db-down")
        self.assertTrue(recorded["export_audit_store_degraded"])
        self.assertIn("trace-db-down", [record["trace_id"] for record in records])


if __name__ == "__main__":
    unittest.main()
