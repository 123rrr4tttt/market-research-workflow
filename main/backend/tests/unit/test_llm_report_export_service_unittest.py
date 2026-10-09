from __future__ import annotations

from collections.abc import Callable
import sys
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.llm_report_export import (
    LlmReportExportTokenError,
    build_llm_report_export_artifact,
    reset_llm_report_export_token_state,
    revoke_llm_report_export_token,
    mark_llm_report_export_token_used,
    render_markdown_export,
    render_markdown_to_docx_bytes,
    render_markdown_to_pdf_bytes,
    verify_llm_report_export_token,
)


class _TokenStateRowResult:
    def __init__(self, row: Any | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any | None:
        return self._row


class _IsolatedTokenStateSession:
    def __init__(self) -> None:
        self.rows: dict[str, Any] = {}
        self._pending: list[Any] = []

    def execute(self, statement: Any) -> _TokenStateRowResult:
        artifact_id = self._artifact_id_from_statement(statement)
        return _TokenStateRowResult(self.rows.get(artifact_id) if artifact_id else None)

    def add(self, row: Any) -> None:
        self._pending.append(row)

    def flush(self) -> None:
        for row in self._pending:
            self.rows[row.artifact_id] = row
        self._pending.clear()

    @staticmethod
    def _artifact_id_from_statement(statement: Any) -> str | None:
        params: dict[str, Any] = dict(statement.compile().params)
        value = next(
            (value for key, value in params.items() if key.startswith("artifact_id")),
            None,
        )
        return value if isinstance(value, str) else None


class _IsolatedTokenStateStore:
    def __init__(self) -> None:
        self.session = _IsolatedTokenStateSession()

    def run_with_session_retry(
        self,
        operation: Callable[[_IsolatedTokenStateSession], Any],
        **_kwargs: Any,
    ) -> Any:
        return operation(self.session)


class LlmReportExportServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._token_state_store = _IsolatedTokenStateStore()
        self._token_state_store_patch = patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=self._token_state_store.run_with_session_retry,
        )
        self._token_state_store_patch.start()
        self.addCleanup(self._token_state_store_patch.stop)
        self.addCleanup(reset_llm_report_export_token_state)
        reset_llm_report_export_token_state()

    def _artifact(self, **overrides: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "markdown": "# Report\n\nEvidence.",
            "gate": {"decision": "pass", "gate_version": "test", "hard_failures": [], "soft_failures": []},
            "gate_mode": "strict",
            "trace_id": f"trace-{self._testMethodName}",
            "request_id": f"request-{self._testMethodName}",
            "project_key": "demo_proj",
            "job_id": 100,
            "topic": "report",
            "token_secret": "secret-" * 8,
            "actor_id": "analyst",
        }
        params.update(overrides)
        return build_llm_report_export_artifact(**params)

    def _complex_markdown(self) -> str:
        return "\n".join(
            [
                "# Market Report",
                "",
                "## Export Fidelity",
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

    def _reset_telemetry_boundary_context(self) -> dict[str, Any]:
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

    def test_token_verification_enforces_actor_binding(self):
        artifact = self._artifact()

        with self.assertRaisesRegex(LlmReportExportTokenError, "export_token_actor_mismatch"):
            verify_llm_report_export_token(
                artifact["artifact_token"],
                markdown="# Report\n\nEvidence.",
                token_secret="secret-" * 8,
                actor_id="other-analyst",
            )

    def test_token_verification_enforces_expiry(self):
        artifact = self._artifact(ttl_seconds=-1)

        with self.assertRaisesRegex(LlmReportExportTokenError, "export_token_expired"):
            verify_llm_report_export_token(
                artifact["artifact_token"],
                markdown="# Report\n\nEvidence.",
                token_secret="secret-" * 8,
                actor_id="analyst",
            )

    def test_token_verification_enforces_revocation(self):
        artifact = self._artifact()
        revoke_llm_report_export_token(artifact["artifact_id"])

        with self.assertRaisesRegex(LlmReportExportTokenError, "export_token_revoked"):
            verify_llm_report_export_token(
                artifact["artifact_token"],
                markdown="# Report\n\nEvidence.",
                token_secret="secret-" * 8,
                actor_id="analyst",
            )

    def test_token_verification_enforces_persisted_revocation_after_memory_reset(self):
        artifact = self._artifact()
        revoke_llm_report_export_token(artifact["artifact_id"])
        reset_llm_report_export_token_state()

        with self.assertRaisesRegex(LlmReportExportTokenError, "export_token_revoked"):
            verify_llm_report_export_token(
                artifact["artifact_token"],
                markdown="# Report\n\nEvidence.",
                token_secret="secret-" * 8,
                actor_id="analyst",
            )

    def test_token_verification_enforces_persisted_used_state_after_memory_reset(self):
        artifact = self._artifact()
        payload = verify_llm_report_export_token(
            artifact["artifact_token"],
            markdown="# Report\n\nEvidence.",
            token_secret="secret-" * 8,
            actor_id="analyst",
        )
        mark_llm_report_export_token_used(payload)
        reset_llm_report_export_token_state()

        with self.assertRaisesRegex(LlmReportExportTokenError, "export_token_already_used"):
            verify_llm_report_export_token(
                artifact["artifact_token"],
                markdown="# Report\n\nEvidence.",
                token_secret="secret-" * 8,
                actor_id="analyst",
            )

    def test_render_pdf_fidelity_contract_includes_template_metadata_and_export_marker(self):
        pdf_bytes = render_markdown_to_pdf_bytes(self._complex_markdown())

        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertIn(b"/Producer", pdf_bytes)
        self.assertIn(b"market-research-workflow", pdf_bytes)
        self.assertIn(b"LLM Report Export", pdf_bytes)
        self.assertIn(b"llm_report.export", pdf_bytes)

    def test_render_docx_fidelity_contract_preserves_template_parts_and_markdown_structure(self):
        docx_bytes = render_markdown_to_docx_bytes(self._complex_markdown())

        with zipfile.ZipFile(BytesIO(docx_bytes)) as docx:
            names = set(docx.namelist())
            document_xml = docx.read("word/document.xml").decode("utf-8")

        self.assertIn("word/document.xml", names)
        self.assertIn("word/styles.xml", names)
        self.assertIn('w:pStyle w:val="Heading1"', document_xml)
        self.assertIn('w:pStyle w:val="Heading2"', document_xml)
        self.assertIn("<w:numPr>", document_xml)
        self.assertIn("<w:tbl>", document_xml)
        self.assertIn('w:pStyle w:val="Quote"', document_xml)

    def test_render_markdown_export_routes_pdf_and_docx_artifacts(self):
        markdown = self._complex_markdown()

        pdf_artifact = render_markdown_export(markdown, "pdf")
        docx_artifact = render_markdown_export(markdown, "docx")

        self.assertEqual(pdf_artifact.media_type, "application/pdf")
        self.assertEqual(pdf_artifact.extension, "pdf")
        self.assertTrue(pdf_artifact.content.startswith(b"%PDF-"))
        self.assertEqual(
            docx_artifact.media_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(docx_artifact.extension, "docx")
        self.assertTrue(docx_artifact.content.startswith(b"PK"))

    def test_reset_telemetry_boundary_context_renders_pdf_note_without_token_leak(self):
        pdf_bytes = render_markdown_to_pdf_bytes(
            self._complex_markdown(),
            reset_telemetry_boundary_context=self._reset_telemetry_boundary_context(),
        )

        self.assertIn(b"Reset telemetry boundary context", pdf_bytes)
        self.assertIn(b"ui_read_only_evidence_context", pdf_bytes)
        self.assertIn(b"not report proof", pdf_bytes)
        self.assertIn(b"not scheduled_run_evidence proof", pdf_bytes)
        self.assertIn(b"scheduled_evidence_write=none", pdf_bytes)
        self.assertIn(b"scheduled_completion_proof unchanged", pdf_bytes)
        self.assertNotIn(b"llmrpt-v1.this-token-must-not-leak.signature", pdf_bytes)
        self.assertNotIn(b"artifact_token", pdf_bytes)

    def test_reset_telemetry_boundary_context_renders_docx_note_without_token_leak(self):
        docx_bytes = render_markdown_to_docx_bytes(
            self._complex_markdown(),
            reset_telemetry_boundary_context=self._reset_telemetry_boundary_context(),
        )

        with zipfile.ZipFile(BytesIO(docx_bytes)) as docx:
            document_xml = docx.read("word/document.xml").decode("utf-8")

        self.assertIn("Reset telemetry boundary context", document_xml)
        self.assertIn("ui_read_only_evidence_context", document_xml)
        self.assertIn("not report proof", document_xml)
        self.assertIn("not scheduled_run_evidence proof", document_xml)
        self.assertIn("scheduled_evidence_write=none", document_xml)
        self.assertIn("scheduled_completion_proof unchanged", document_xml)
        self.assertNotIn("llmrpt-v1.this-token-must-not-leak.signature", document_xml)
        self.assertNotIn("artifact_token", document_xml)


if __name__ == "__main__":
    unittest.main()
