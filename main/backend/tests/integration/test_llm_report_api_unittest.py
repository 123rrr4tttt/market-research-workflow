from __future__ import annotations

import sys
import unittest
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.services.llm_report_export import build_llm_report_export_artifact, reset_llm_report_export_token_state

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _AuthenticatedActorStateApp:
    def __init__(self, app, *, actor_id: str):
        self._app = app
        self._actor_id = actor_id

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            state = scope.setdefault("state", {})
            actor = {
                "actor_id": self._actor_id,
                "source": "test_authenticated_actor_context",
                "auth_type": "codex_test",
            }
            state["authenticated_actor"] = actor
            state["authenticated_actor_id"] = self._actor_id
            state["codex_authenticated_actor"] = actor
        await self._app(scope, receive, send)


class LlmReportApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"llm report integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "llm-report-integration"}

    def setUp(self):
        from app.services import llm_report_export_audit
        from app.services import llm_report_trends

        llm_report_export_audit.clear_llm_report_export_audit_memory()
        llm_report_trends.clear_quality_trend_memory()
        reset_llm_report_export_token_state()

    def _authenticated_client(self, *, actor_id: str):
        return TestClient(_AuthenticatedActorStateApp(backend_app, actor_id=actor_id))

    def _export_artifact(
        self,
        *,
        markdown: str,
        gate: dict,
        gate_mode: str,
        export_id: str = "signed-export",
        actor_id: str | None = None,
        ttl_seconds: int | None = None,
        one_time_use: bool | None = None,
    ) -> dict:
        artifact_kwargs = {}
        if one_time_use is not None:
            artifact_kwargs["one_time_use"] = one_time_use
        unique_export_id = f"{export_id}-{uuid.uuid4().hex[:12]}"
        return build_llm_report_export_artifact(
            markdown=markdown,
            gate={**gate, "gate_version": "test"},
            gate_mode=gate_mode,
            trace_id=f"{unique_export_id}-trace",
            request_id=f"{unique_export_id}-request",
            project_key="demo_proj",
            job_id=9000,
            topic=unique_export_id,
            token_secret="mrw-local-llm-report-export-token-v1",
            actor_id=actor_id,
            ttl_seconds=ttl_seconds,
            **artifact_kwargs,
        )

    def _complex_export_markdown(self) -> str:
        return "\n".join(
            [
                "# Market report",
                "",
                "## Export fidelity",
                "",
                "- Demand signal from channel checks",
                "- Supply risk from vendor concentration",
                "",
                "> Analyst note: preserve block quote treatment.",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
                "| TAM | 42 |",
            ]
        )

    def _reset_telemetry_boundary_context(self) -> dict:
        return {
            "scope": "ui_read_only_evidence_context",
            "source": "business_lines.evidence_matrix.async_task_readback_extension",
            "event_name": "reset_empty_warning_view",
            "not_report_proof": True,
            "not_scheduled_run_evidence_proof": True,
            "scheduled_evidence_write": "none",
            "scheduled_completion_proof": "unchanged",
            "artifact_token": "llmrpt-v1.this-token-must-not-leak.signature",
        }

    def test_generate_topic_only_auto_source_enabled(self):
        payload = {"topic": "market growth", "sources": []}
        auto_sources = [
            {
                "id": "RAG1",
                "title": "Auto Source",
                "url": "https://example.com/auto",
                "publisher": "internal_rag",
                "evidence": "auto evidence",
            }
        ]
        with (
            patch("app.api.llm_report.start_job", return_value=2001),
            patch("app.api.llm_report.complete_job"),
            patch("app.api.llm_report.resolve_report_sources", return_value=auto_sources) as mocked_resolve,
            patch("app.api.llm_report.settings.llm_report_enabled", True),
            patch("app.api.llm_report.settings.llm_report_gate_mode", "warn"),
            patch("app.api.llm_report.settings.llm_report_auto_source_enabled", True),
            patch("app.api.llm_report.settings.llm_report_auto_source_target_count", 6),
        ):
            resp = self.client.post("/api/v1/llm-report/generate", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["report"]["sources"][0]["id"], "RAG1")
        self.assertEqual(body["data"]["capability_truth"]["implementation_kind"], "structured_template_report")
        self.assertTrue(body["data"]["export_contract"]["markdown_exportable"])
        self.assertTrue(body["data"]["export_contract"]["export_allowed"])
        self.assertTrue(body["data"]["export_contract"]["file_exportable"])
        self.assertEqual(body["data"]["export_contract"]["format"], "markdown")
        self.assertEqual(body["data"]["export_artifact"]["contract_version"], "llm_report.export_artifact.v1")
        self.assertTrue(body["data"]["export_artifact"]["artifact_token"].startswith("llmrpt-v1."))
        self.assertEqual(body["data"]["export_artifact"]["actor_id"], "anonymous")
        self.assertIn("expires_at", body["data"]["export_artifact"])
        self.assertTrue(body["data"]["export_artifact"]["one_time_use"])
        self.assertEqual(body["data"]["export_contract"]["artifact"], body["data"]["export_artifact"])
        self.assertEqual(body["data"]["export_readiness"]["quality_gate_mode"], "warn")
        self.assertEqual(body["data"]["export_readiness"]["next_action"], "export_markdown")
        trend = body["data"]["report_quality_trend_metric"]
        self.assertEqual(trend["contract_version"], "llm_report.quality_trend_metric.v1")
        self.assertEqual(trend["decision"], body["data"]["quality_gate"]["decision"])
        self.assertEqual(trend["source_count"], 1)
        self.assertEqual(trend["project_key"], "demo_proj")
        self.assertEqual(trend["hard_failure_count"], 0)
        self.assertEqual(trend["soft_failure_count"], 0)
        self.assertEqual(body["data"]["quality_gate_trend_record"], trend)
        mocked_resolve.assert_called_once()

        trends_resp = self.client.get(
            "/api/v1/llm-report/quality-trends",
            params={"project_key": "demo_proj", "decision": trend["decision"], "limit": 5},
        )
        self.assertEqual(trends_resp.status_code, 200)
        trends = trends_resp.json()["data"]
        self.assertEqual(trends["contract_version"], "llm_report.quality_trends.v1")
        self.assertGreaterEqual(trends["summary"]["total"], 1)
        self.assertEqual(trends["records"][0]["trace_id"], trend["trace_id"])
        self.assertEqual(trends["records"][0]["job_id"], 2001)
        self.assertEqual(trends["records"][0]["job_status"], "completed")
        self.assertEqual(trends["records"][0]["record_source"], "generate")
        self.assertEqual(trends["filters"]["project_key"], "demo_proj")
        self.assertIn("avg_citation_coverage", trends["summary"])

    def test_generate_prefers_authenticated_actor_context_over_spoofed_header_actor(self):
        payload = {"topic": "market growth", "sources": []}
        auto_sources = [
            {
                "id": "RAG1",
                "title": "Auto Source",
                "url": "https://example.com/auto",
                "publisher": "internal_rag",
                "evidence": "auto evidence",
            }
        ]
        with (
            self._authenticated_client(actor_id="auth-session-actor") as client,
            patch("app.api.llm_report.start_job", return_value=2101),
            patch("app.api.llm_report.complete_job"),
            patch("app.api.llm_report.resolve_report_sources", return_value=auto_sources),
            patch("app.api.llm_report.settings.llm_report_enabled", True),
            patch("app.api.llm_report.settings.llm_report_gate_mode", "warn"),
            patch("app.api.llm_report.settings.llm_report_auto_source_enabled", True),
            patch("app.api.llm_report.settings.llm_report_auto_source_target_count", 6),
        ):
            resp = client.post(
                "/api/v1/llm-report/generate",
                json=payload,
                headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["export_artifact"]["actor_id"], "auth-session-actor")
        self.assertEqual(data["export_contract"]["artifact"]["actor_id"], "auth-session-actor")

    def test_generate_uses_header_actor_as_legacy_fallback_without_authenticated_context(self):
        payload = {"topic": "market growth", "sources": []}
        auto_sources = [
            {
                "id": "RAG1",
                "title": "Auto Source",
                "url": "https://example.com/auto",
                "publisher": "internal_rag",
                "evidence": "auto evidence",
            }
        ]
        with (
            patch("app.api.llm_report.start_job", return_value=2102),
            patch("app.api.llm_report.complete_job"),
            patch("app.api.llm_report.resolve_report_sources", return_value=auto_sources),
            patch("app.api.llm_report.settings.llm_report_enabled", True),
            patch("app.api.llm_report.settings.llm_report_gate_mode", "warn"),
            patch("app.api.llm_report.settings.llm_report_auto_source_enabled", True),
            patch("app.api.llm_report.settings.llm_report_auto_source_target_count", 6),
        ):
            resp = self.client.post(
                "/api/v1/llm-report/generate",
                json=payload,
                headers={**self.headers, "X-Actor-Id": "legacy-header-actor"},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["export_artifact"]["actor_id"], "legacy-header-actor")
        self.assertEqual(data["export_contract"]["artifact"]["actor_id"], "legacy-header-actor")

    def test_generate_topic_only_auto_source_disabled_strict_blocks(self):
        payload = {"topic": "market growth", "sources": []}
        with (
            patch("app.api.llm_report.start_job", return_value=2002),
            patch("app.api.llm_report.complete_job"),
            patch("app.api.llm_report.resolve_report_sources") as mocked_resolve,
            patch("app.api.llm_report.settings.llm_report_enabled", True),
            patch("app.api.llm_report.settings.llm_report_gate_mode", "strict"),
            patch("app.api.llm_report.settings.llm_report_auto_source_enabled", False),
        ):
            resp = self.client.post("/api/v1/llm-report/generate", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("quality gate blocked report generation", body["error"]["message"])
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        details = body["error"]["details"]
        self.assertEqual(details["export_readiness"]["readiness"], "blocked")
        self.assertEqual(details["export_readiness"]["quality_gate_mode"], "strict")
        self.assertFalse(details["export_readiness"]["export_allowed"])
        self.assertFalse(details["export_readiness"]["file_exportable"])
        self.assertEqual(details["next_action"], "fix_quality_gate_blockers_before_export")
        self.assertEqual(details["export_contract"]["blocking_next_action"], "fix_quality_gate_blockers_before_export")
        self.assertEqual(details["report_quality_trend_metric"]["decision"], "fail")
        self.assertEqual(details["report_quality_trend_metric"]["project_key"], "demo_proj")
        self.assertGreater(details["report_quality_trend_metric"]["missing_items_count"], 0)
        self.assertGreater(details["report_quality_trend_metric"]["hard_failure_count"], 0)
        self.assertEqual(details["quality_gate_trend_record"], details["report_quality_trend_metric"])
        mocked_resolve.assert_not_called()

        trends_resp = self.client.get(
            "/api/v1/llm-report/quality-trends",
            params={"project_key": "demo_proj", "decision": "fail", "limit": 5},
        )
        self.assertEqual(trends_resp.status_code, 200)
        trends = trends_resp.json()["data"]
        self.assertGreaterEqual(trends["summary"]["decisions"]["fail"], 1)
        self.assertGreaterEqual(trends["summary"]["by_decision"]["fail"], 1)
        self.assertEqual(trends["records"][0]["readiness"], "blocked")
        self.assertEqual(trends["records"][0]["job_id"], 2002)
        self.assertEqual(trends["records"][0]["job_status"], "failed")

    def test_export_markdown_endpoint_returns_download_response_when_gate_allows(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        gate = {"decision": "warn", "hard_failures": [], "soft_failures": ["needs_review"]}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="warn",
            export_id="markdown-warn",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "warn",
            "filename": "market report.md",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/markdown", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "text/markdown; charset=utf-8")
        self.assertIn("attachment; filename=market-report.md", resp.headers.get("content-disposition", ""))
        self.assertEqual(resp.headers.get("x-llm-report-export-readiness"), "review_required")
        self.assertEqual(resp.headers.get("x-llm-report-export-integrity"), "artifact_token")
        self.assertEqual(resp.headers.get("x-quality-gate-decision"), "warn")
        self.assertEqual(resp.text, payload["markdown"])

    def test_export_markdown_endpoint_blocks_strict_failed_gate(self):
        markdown = "# Blocked report\n\nDraft exists but gate failed."
        gate = {
            "decision": "fail",
            "hard_failures": ["citation_coverage_below_threshold"],
            "soft_failures": [],
            "missing_items": ["source_citation"],
        }
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="markdown-fail",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "blocked.md",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/markdown", json=payload)

        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        details = body["error"]["details"]
        self.assertEqual(details["export_readiness"]["readiness"], "blocked")
        self.assertEqual(details["export_integrity"]["mode"], "artifact_token")
        self.assertFalse(details["export_readiness"]["export_allowed"])
        self.assertEqual(details["next_action"], "fix_quality_gate_blockers_before_export")

    def test_export_pdf_endpoint_returns_download_response_when_gate_allows(self):
        markdown = self._complex_export_markdown()
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="pdf-pass",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "market report.md",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertIn("attachment; filename=market-report.pdf", resp.headers.get("content-disposition", ""))
        self.assertEqual(resp.headers.get("x-llm-report-export-readiness"), "ready")
        self.assertEqual(resp.headers.get("x-llm-report-export-format"), "pdf")
        self.assertEqual(resp.headers.get("x-llm-report-export-integrity"), "artifact_token")
        self.assertEqual(resp.headers.get("x-llm-report-source-ref"), artifact["artifact_id"])
        self.assertEqual(resp.headers.get("x-llm-report-source-trace-id"), artifact["trace_id"])
        self.assertEqual(resp.headers.get("x-llm-report-job-id"), "9000")
        self.assertTrue(resp.content.startswith(b"%PDF-"))
        self.assertIn(b"/Type /Catalog", resp.content)
        self.assertIn(b"/Pages", resp.content)
        self.assertIn(b"Market report", resp.content)
        self.assertIn(b"Export fidelity", resp.content)
        fidelity_header = resp.headers.get("x-llm-report-export-fidelity")
        if fidelity_header is not None:
            self.assertIn(fidelity_header, {"template", "high", "structured"})
        trends_resp = self.client.get("/api/v1/llm-report/quality-trends", params={"project_key": "demo_proj"})
        self.assertEqual(trends_resp.status_code, 200)
        export_events = trends_resp.json()["data"]["summary"]["export_events"]
        self.assertGreaterEqual(export_events["success"], 1)
        self.assertGreaterEqual(export_events["by_format"]["pdf"], 1)
        from app.services.llm_report_export_audit import list_recent_llm_report_export_audit_events

        audit_events = list_recent_llm_report_export_audit_events(limit=5, project_key="demo_proj")
        self.assertEqual(audit_events[0]["event_type"], "llm_report_export")
        self.assertEqual(audit_events[0]["record_source"], "export_audit")
        self.assertEqual(audit_events[0]["export_format"], "pdf")
        self.assertEqual(audit_events[0]["outcome"], "success")
        self.assertEqual(audit_events[0]["source_ref"]["id"], artifact["artifact_id"])
        self.assertEqual(audit_events[0]["source_ref"]["source_trace_id"], artifact["trace_id"])
        self.assertEqual(audit_events[0]["header_snapshot"]["format"], resp.headers.get("x-llm-report-export-format"))
        self.assertEqual(
            audit_events[0]["header_snapshot"]["readiness"],
            resp.headers.get("x-llm-report-export-readiness"),
        )
        self.assertEqual(
            audit_events[0]["header_snapshot"]["quality_gate_decision"],
            resp.headers.get("x-quality-gate-decision"),
        )
        self.assertEqual(
            audit_events[0]["header_snapshot"]["quality_gate_mode"],
            resp.headers.get("x-quality-gate-mode"),
        )
        self.assertEqual(audit_events[0]["header_snapshot"]["source_ref"], resp.headers.get("x-llm-report-source-ref"))
        self.assertFalse(audit_events[0]["audit_event"]["strict_gate_blocked"])

    def test_export_docx_endpoint_returns_download_response_when_gate_allows(self):
        markdown = self._complex_export_markdown()
        gate = {"decision": "warn", "hard_failures": [], "soft_failures": ["needs_review"]}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="warn",
            export_id="docx-warn",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "warn",
            "filename": "market report.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/docx", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get("content-type"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("attachment; filename=market-report.docx", resp.headers.get("content-disposition", ""))
        self.assertEqual(resp.headers.get("x-llm-report-export-readiness"), "review_required")
        self.assertEqual(resp.headers.get("x-llm-report-export-format"), "docx")
        self.assertEqual(resp.headers.get("x-llm-report-export-integrity"), "artifact_token")
        self.assertTrue(resp.content.startswith(b"PK"))
        with zipfile.ZipFile(BytesIO(resp.content)) as docx:
            names = set(docx.namelist())
            document_xml = docx.read("word/document.xml").decode("utf-8")
        self.assertIn("word/document.xml", names)
        self.assertIn("docProps/core.xml", names)
        self.assertIn("word/styles.xml", names)
        self.assertIn("Market report", document_xml)
        self.assertIn("Export fidelity", document_xml)
        self.assertIn("<w:tbl>", document_xml)
        self.assertIn("Metric", document_xml)
        self.assertIn("Value", document_xml)
        self.assertIn('w:pStyle w:val="Heading1"', document_xml)
        self.assertIn('w:pStyle w:val="Heading2"', document_xml)
        fidelity_header = resp.headers.get("x-llm-report-export-fidelity")
        if fidelity_header is not None:
            self.assertIn(fidelity_header, {"template", "high", "structured"})

    def test_ui_read_only_context_export_pdf_renders_note_without_changing_gate_outcome(self):
        markdown = self._complex_export_markdown()
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="pdf-reset-telemetry",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "reset telemetry.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
            "reset_telemetry_boundary_context": self._reset_telemetry_boundary_context(),
        }
        resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-quality-gate-decision"), "pass")
        self.assertEqual(resp.headers.get("x-llm-report-export-readiness"), "ready")
        self.assertIn(b"Reset telemetry boundary context", resp.content)
        self.assertIn(b"ui_read_only_evidence_context", resp.content)
        self.assertIn(b"not report proof", resp.content)
        self.assertIn(b"not scheduled_run_evidence proof", resp.content)
        self.assertIn(b"scheduled_evidence_write=none", resp.content)
        self.assertIn(b"scheduled_completion_proof unchanged", resp.content)
        self.assertNotIn(payload["artifact_token"].encode("utf-8"), resp.content)
        self.assertNotIn(b"artifact_token", resp.content)
        from app.services.llm_report_export_audit import list_recent_llm_report_export_audit_events

        audit_events = list_recent_llm_report_export_audit_events(limit=5, project_key="demo_proj")
        self.assertEqual(audit_events[0]["outcome"], "success")
        self.assertEqual(audit_events[0]["readiness"], "ready")
        self.assertEqual(audit_events[0]["quality_gate_decision"], "pass")
        self.assertTrue(audit_events[0]["ui_read_only_context_included"])
        self.assertEqual(audit_events[0]["ui_read_only_context_scope"], "ui_read_only_evidence_context")
        self.assertEqual(
            audit_events[0]["ui_read_only_context_source"],
            "business_lines.evidence_matrix.async_task_readback_extension",
        )
        self.assertEqual(
            audit_events[0]["ui_read_only_context_reason"],
            "reset_telemetry_boundary_context_rendered_as_read_only_export_boundary_note",
        )
        self.assertTrue(audit_events[0]["audit_event"]["ui_read_only_context_included"])
        self.assertFalse(audit_events[0]["audit_event"]["strict_gate_blocked"])
        trends_resp = self.client.get("/api/v1/llm-report/quality-trends", params={"project_key": "demo_proj"})
        self.assertEqual(trends_resp.status_code, 200)
        export_events = trends_resp.json()["data"]["summary"]["export_events"]
        self.assertEqual(export_events["ui_read_only_context_included_count"], 1)
        self.assertEqual(export_events["success"], 1)
        self.assertEqual(export_events["blocked"], 0)
        self.assertEqual(export_events["failed"], 0)
        self.assertEqual(export_events["token_invalid"], 0)

    def test_reset_telemetry_boundary_context_export_docx_renders_note_without_changing_gate_outcome(self):
        markdown = self._complex_export_markdown()
        gate = {"decision": "warn", "hard_failures": [], "soft_failures": ["needs_review"]}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="warn",
            export_id="docx-reset-telemetry",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "warn",
            "filename": "reset telemetry.docx",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
            "reset_telemetry_boundary_context": self._reset_telemetry_boundary_context(),
        }
        resp = self.client.post("/api/v1/llm-report/export/docx", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-quality-gate-decision"), "warn")
        self.assertEqual(resp.headers.get("x-llm-report-export-readiness"), "review_required")
        with zipfile.ZipFile(BytesIO(resp.content)) as docx:
            document_xml = docx.read("word/document.xml").decode("utf-8")
        self.assertIn("Reset telemetry boundary context", document_xml)
        self.assertIn("ui_read_only_evidence_context", document_xml)
        self.assertIn("not report proof", document_xml)
        self.assertIn("not scheduled_run_evidence proof", document_xml)
        self.assertIn("scheduled_evidence_write=none", document_xml)
        self.assertIn("scheduled_completion_proof unchanged", document_xml)
        self.assertNotIn(payload["artifact_token"], document_xml)
        self.assertNotIn("artifact_token", document_xml)
        from app.services.llm_report_export_audit import list_recent_llm_report_export_audit_events

        audit_events = list_recent_llm_report_export_audit_events(limit=5, project_key="demo_proj")
        self.assertEqual(audit_events[0]["outcome"], "success")
        self.assertEqual(audit_events[0]["readiness"], "review_required")
        self.assertEqual(audit_events[0]["quality_gate_decision"], "warn")
        self.assertTrue(audit_events[0]["ui_read_only_context_included"])
        self.assertEqual(audit_events[0]["ui_read_only_context_scope"], "ui_read_only_evidence_context")
        self.assertEqual(
            audit_events[0]["ui_read_only_context_source"],
            "business_lines.evidence_matrix.async_task_readback_extension",
        )
        self.assertEqual(
            audit_events[0]["ui_read_only_context_reason"],
            "reset_telemetry_boundary_context_rendered_as_read_only_export_boundary_note",
        )
        self.assertTrue(audit_events[0]["audit_event"]["ui_read_only_context_included"])
        self.assertFalse(audit_events[0]["audit_event"]["strict_gate_blocked"])

    def test_export_pdf_endpoint_blocks_strict_failed_gate(self):
        markdown = "# Blocked report\n\nDraft exists but gate failed."
        gate = {
            "decision": "fail",
            "hard_failures": ["citation_coverage_below_threshold"],
            "soft_failures": [],
            "missing_items": ["source_citation"],
        }
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="pdf-fail",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "blocked.pdf",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        details = body["error"]["details"]
        self.assertEqual(details["export_readiness"]["format"], "pdf")
        self.assertEqual(details["export_readiness"]["readiness"], "blocked")
        self.assertEqual(details["export_integrity"]["mode"], "artifact_token")
        self.assertFalse(details["export_readiness"]["export_allowed"])
        self.assertEqual(details["next_action"], "fix_quality_gate_blockers_before_export")
        from app.services.llm_report_export_audit import list_recent_llm_report_export_audit_events

        audit_events = list_recent_llm_report_export_audit_events(limit=5, project_key="demo_proj")
        self.assertEqual(audit_events[0]["outcome"], "blocked")
        self.assertEqual(audit_events[0]["export_format"], "pdf")
        self.assertEqual(audit_events[0]["readiness"], "blocked")
        self.assertEqual(audit_events[0]["quality_gate_mode"], "strict")
        self.assertTrue(audit_events[0]["audit_event"]["strict_gate_blocked"])
        self.assertFalse(audit_events[0]["audit_event"]["compatible_quality_gate_path"])

    def test_export_endpoints_require_signed_artifact_token_by_default(self):
        payload = {
            "markdown": "# Market report\n\nEvidence-backed draft.",
            "quality_gate": {"decision": "pass", "hard_failures": [], "soft_failures": []},
            "quality_gate_mode": "strict",
            "filename": "market report.md",
            "project_key": "demo_proj",
        }
        for export_format in ("markdown", "pdf", "docx"):
            with self.subTest(export_format=export_format):
                resp = self.client.post(f"/api/v1/llm-report/export/{export_format}", json=payload)
                self.assertEqual(resp.status_code, 422)
                body = resp.json()
                details = body["error"]["details"]
                self.assertEqual(details["error_code"], "LLM_REPORT_EXPORT_TOKEN_REQUIRED")
                self.assertEqual(details["export_integrity"]["mode"], "legacy_payload_gate_blocked")
                self.assertFalse(details["export_readiness"]["export_allowed"])
                self.assertEqual(details["next_action"], "regenerate_report_to_receive_signed_export_artifact")

        trends_resp = self.client.get("/api/v1/llm-report/quality-trends", params={"project_key": "demo_proj"})
        self.assertEqual(trends_resp.status_code, 200)
        export_events = trends_resp.json()["data"]["summary"]["export_events"]
        self.assertGreaterEqual(export_events["blocked"], 3)

    def test_export_legacy_payload_gate_can_be_enabled_explicitly_for_compatibility(self):
        payload = {
            "markdown": "# Market report\n\nEvidence-backed draft.",
            "quality_gate": {"decision": "pass", "hard_failures": [], "soft_failures": []},
            "quality_gate_mode": "compatible",
            "filename": "market report.md",
            "project_key": "demo_proj",
        }
        with patch("app.api.llm_report.settings.llm_report_export_require_artifact_token", False):
            resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-llm-report-export-integrity"), "legacy_payload_gate")
        self.assertEqual(resp.headers.get("x-llm-report-export-format"), "pdf")
        self.assertEqual(resp.headers.get("x-quality-gate-mode"), "warn")
        trends_resp = self.client.get("/api/v1/llm-report/quality-trends", params={"project_key": "demo_proj"})
        self.assertEqual(trends_resp.status_code, 200)
        export_events = trends_resp.json()["data"]["summary"]["export_events"]
        self.assertGreaterEqual(export_events["legacy"], 1)
        from app.services.llm_report_export_audit import list_recent_llm_report_export_audit_events

        audit_events = list_recent_llm_report_export_audit_events(limit=5, project_key="demo_proj")
        self.assertEqual(audit_events[0]["outcome"], "success")
        self.assertEqual(audit_events[0]["export_integrity_mode"], "legacy_payload_gate")
        self.assertEqual(audit_events[0]["header_snapshot"]["format"], resp.headers.get("x-llm-report-export-format"))
        self.assertEqual(
            audit_events[0]["header_snapshot"]["readiness"],
            resp.headers.get("x-llm-report-export-readiness"),
        )
        self.assertEqual(
            audit_events[0]["header_snapshot"]["quality_gate_mode"],
            resp.headers.get("x-quality-gate-mode"),
        )
        self.assertFalse(audit_events[0]["audit_event"]["strict_gate_blocked"])
        self.assertTrue(audit_events[0]["audit_event"]["compatible_quality_gate_path"])

    def test_export_signed_token_rejects_actor_mismatch(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="actor-bound",
            actor_id="analyst-a",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "actor-bound.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post(
            "/api/v1/llm-report/export/pdf",
            json=payload,
            headers={"X-Actor-Id": "analyst-b"},
        )

        self.assertEqual(resp.status_code, 403)
        details = resp.json()["error"]["details"]
        self.assertEqual(details["error_code"], "LLM_REPORT_EXPORT_TOKEN_INVALID")
        self.assertEqual(details["reason"], "export_token_actor_mismatch")

    def test_export_signed_token_uses_authenticated_actor_context_before_spoofed_header_actor(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="auth-context-export",
            actor_id="authenticated-export-actor",
            one_time_use=False,
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "auth-context-export.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        with self._authenticated_client(actor_id="authenticated-export-actor") as client:
            resp = client.post(
                "/api/v1/llm-report/export/pdf",
                json=payload,
                headers={"X-Actor-Id": "spoofed-header-actor"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-llm-report-export-integrity"), "artifact_token")

    def test_export_signed_token_rejects_authenticated_actor_mismatch_even_when_header_matches_token_actor(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="auth-context-mismatch",
            actor_id="token-owner-actor",
            one_time_use=False,
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "auth-context-mismatch.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        with self._authenticated_client(actor_id="different-authenticated-actor") as client:
            resp = client.post(
                "/api/v1/llm-report/export/pdf",
                json=payload,
                headers={"X-Actor-Id": "token-owner-actor"},
            )

        self.assertEqual(resp.status_code, 403)
        details = resp.json()["error"]["details"]
        self.assertEqual(details["error_code"], "LLM_REPORT_EXPORT_TOKEN_INVALID")
        self.assertEqual(details["reason"], "export_token_actor_mismatch")

    def test_export_signed_token_rejects_expired_token(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="expired",
            ttl_seconds=-1,
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "expired.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(resp.status_code, 403)
        details = resp.json()["error"]["details"]
        self.assertEqual(details["error_code"], "LLM_REPORT_EXPORT_TOKEN_INVALID")
        self.assertEqual(details["reason"], "export_token_expired")

    def test_export_signed_token_is_one_time_use(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        gate = {"decision": "pass", "hard_failures": [], "soft_failures": []}
        artifact = self._export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode="strict",
            export_id="one-time",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": gate,
            "quality_gate_mode": "strict",
            "filename": "one-time.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }

        first_resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)
        second_resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(first_resp.status_code, 200)
        self.assertEqual(second_resp.status_code, 403)
        details = second_resp.json()["error"]["details"]
        self.assertEqual(details["error_code"], "LLM_REPORT_EXPORT_TOKEN_INVALID")
        self.assertEqual(details["reason"], "export_token_already_used")

    def test_export_pdf_endpoint_signed_token_overrides_forged_client_gate(self):
        markdown = "# Blocked report\n\nDraft exists but gate failed."
        artifact = build_llm_report_export_artifact(
            markdown=markdown,
            gate={
                "decision": "fail",
                "gate_version": "test",
                "hard_failures": ["citation_coverage_below_threshold"],
                "soft_failures": [],
                "missing_items": ["source_citation"],
            },
            gate_mode="strict",
            trace_id="signed-strict-trace",
            request_id="signed-strict-request",
            project_key="demo_proj",
            job_id=9001,
            topic="blocked report",
            token_secret="mrw-local-llm-report-export-token-v1",
        )
        payload = {
            "markdown": markdown,
            "quality_gate": {"decision": "pass", "hard_failures": [], "soft_failures": []},
            "quality_gate_mode": "off",
            "filename": "forged.pdf",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/pdf", json=payload)

        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        details = body["error"]["details"]
        self.assertEqual(details["export_integrity"]["mode"], "artifact_token")
        self.assertTrue(details["export_integrity"]["client_gate_ignored"])
        self.assertTrue(details["export_integrity"]["client_gate_mode_ignored"])
        self.assertEqual(details["export_readiness"]["quality_gate_decision"], "fail")
        self.assertEqual(details["export_readiness"]["quality_gate_mode"], "strict")
        self.assertEqual(details["next_action"], "fix_quality_gate_blockers_before_export")
        from app.services.llm_report_export_token_state import is_llm_report_export_token_used

        self.assertFalse(is_llm_report_export_token_used(artifact["artifact_id"]))
        trends_resp = self.client.get("/api/v1/llm-report/quality-trends", params={"project_key": "demo_proj"})
        self.assertEqual(trends_resp.status_code, 200)
        export_events = trends_resp.json()["data"]["summary"]["export_events"]
        self.assertGreaterEqual(export_events["blocked"], 1)
        self.assertGreaterEqual(export_events["trusted"], 1)

    def test_export_docx_endpoint_rejects_tampered_markdown_for_signed_token(self):
        markdown = "# Market report\n\nEvidence-backed draft."
        artifact = build_llm_report_export_artifact(
            markdown=markdown,
            gate={"decision": "pass", "gate_version": "test", "hard_failures": [], "soft_failures": []},
            gate_mode="strict",
            trace_id="signed-pass-trace",
            request_id="signed-pass-request",
            project_key="demo_proj",
            job_id=9002,
            topic="market report",
            token_secret="mrw-local-llm-report-export-token-v1",
        )
        payload = {
            "markdown": f"{markdown}\n\nTampered locally.",
            "quality_gate": {"decision": "pass", "hard_failures": [], "soft_failures": []},
            "quality_gate_mode": "strict",
            "filename": "tampered.docx",
            "project_key": "demo_proj",
            "artifact_token": artifact["artifact_token"],
            "artifact_sha256": artifact["artifact_sha256"],
        }
        resp = self.client.post("/api/v1/llm-report/export/docx", json=payload)

        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["details"]["error_code"], "LLM_REPORT_EXPORT_TOKEN_INVALID")
        self.assertEqual(body["error"]["details"]["reason"], "export_token_markdown_hash_mismatch")
        self.assertEqual(body["error"]["details"]["next_action"], "regenerate_report_before_export")
        trends_resp = self.client.get("/api/v1/llm-report/quality-trends", params={"project_key": "demo_proj"})
        self.assertEqual(trends_resp.status_code, 200)
        export_events = trends_resp.json()["data"]["summary"]["export_events"]
        self.assertGreaterEqual(export_events["token_invalid"], 1)

    def test_generate_feature_flag_disabled_returns_structured_config_error(self):
        payload = {"topic": "market growth", "sources": []}
        with patch("app.api.llm_report.settings.llm_report_enabled", False):
            resp = self.client.post("/api/v1/llm-report/generate", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.CONFIG_ERROR.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.CONFIG_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.CONFIG_ERROR.value)

    def test_generate_internal_error_returns_structured_internal_error(self):
        payload = {"topic": "market growth", "sources": []}
        with (
            patch("app.api.llm_report.start_job", return_value=2003),
            patch("app.api.llm_report.fail_job"),
            patch("app.api.llm_report.resolve_report_sources", return_value=[]),
            patch("app.api.llm_report.build_structured_report", side_effect=RuntimeError("boom")),
            patch("app.api.llm_report.settings.llm_report_enabled", True),
            patch("app.api.llm_report.settings.llm_report_gate_mode", "warn"),
        ):
            resp = self.client.post("/api/v1/llm-report/generate", json=payload, headers=self.headers)

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(
            body["detail"]["error"]["details"]["error_code"],
            "LLM_REPORT_INTERNAL_ERROR",
        )
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
