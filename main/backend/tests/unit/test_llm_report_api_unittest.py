from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

try:
    from pydantic import ValidationError
    from app.api import llm_report as llm_report_api
except Exception as exc:  # pragma: no cover - dependency/import guard
    ValidationError = Exception  # type: ignore[assignment]
    llm_report_api = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class LlmReportApiUnitTest(unittest.TestCase):
    @staticmethod
    def _mock_request(trace_id: str = "unit-test-trace"):
        return SimpleNamespace(headers={"X-Request-Id": trace_id})

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"llm report api unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_generate_llm_report_returns_quality_gate_envelope(self):
        payload = llm_report_api.GenerateReportRequest(
            topic="北美在线彩票增长",
            sources=[
                llm_report_api.SourceInput(
                    id="S1",
                    title="Example Source",
                    url="https://example.com/report",
                    publisher="Example Org",
                    evidence="market grew 12%",
                )
            ],
        )
        with (
            patch.object(llm_report_api, "start_job", return_value=101) as mocked_start,
            patch.object(llm_report_api, "complete_job") as mocked_complete,
        ):
            resp = llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(resp["status"], "ok")
            self.assertIn("report", resp["data"])
            self.assertIn("quality_gate", resp["data"])
            self.assertIn("quality_gate_metrics", resp["data"])
            self.assertIn("decision", resp["data"]["quality_gate"])
            self.assertIn("decision", resp["data"]["quality_gate_metrics"])
            self.assertEqual(resp["data"]["observability"]["job_id"], 101)
            self.assertIn("decision", mocked_complete.call_args.kwargs["result"])
            self.assertIn("gate_version", mocked_complete.call_args.kwargs["result"])
            mocked_start.assert_called_once()
            mocked_complete.assert_called_once()

    def test_generate_request_rejects_invalid_url(self):
        with self.assertRaises(ValidationError):
            llm_report_api.GenerateReportRequest(
                topic="test",
                sources=[
                    llm_report_api.SourceInput(
                        id="S1",
                        title="x",
                        url="not-a-url",
                    )
                ],
            )

    def test_generate_request_rejects_blank_topic(self):
        with self.assertRaises(ValidationError):
            llm_report_api.GenerateReportRequest(topic="   ", sources=[])

    def test_generate_llm_report_strict_mode_blocks_failed_gate(self):
        payload = llm_report_api.GenerateReportRequest(topic="缺少来源的主题", sources=[])
        with (
            patch.object(llm_report_api, "start_job", return_value=102),
            patch.object(llm_report_api, "complete_job") as mocked_complete,
            patch.object(llm_report_api, "resolve_report_sources", return_value=[]),
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "strict"),
        ):
            with self.assertRaises(HTTPException) as exc_ctx:
                llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(exc_ctx.exception.status_code, 422)
            self.assertIn("quality gate blocked report generation", str(exc_ctx.exception.detail))
            self.assertEqual(exc_ctx.exception.detail["observability"]["job_id"], 102)
            mocked_complete.assert_called_once()

    def test_generate_llm_report_warn_mode_does_not_block_failed_gate(self):
        payload = llm_report_api.GenerateReportRequest(topic="缺少来源的主题", sources=[])
        with (
            patch.object(llm_report_api, "start_job", return_value=103),
            patch.object(llm_report_api, "complete_job") as mocked_complete,
            patch.object(llm_report_api, "resolve_report_sources", return_value=[]),
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "warn"),
        ):
            resp = llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(resp["status"], "ok")
            self.assertEqual(resp["data"]["quality_gate"]["decision"], "fail")
            mocked_complete.assert_called_once()

    def test_generate_llm_report_invalid_gate_mode_falls_back_to_strict(self):
        payload = llm_report_api.GenerateReportRequest(topic="缺少来源的主题", sources=[])
        with (
            patch.object(llm_report_api, "start_job", return_value=104),
            patch.object(llm_report_api, "complete_job") as mocked_complete,
            patch.object(llm_report_api, "resolve_report_sources", return_value=[]),
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "invalid-mode"),
        ):
            with self.assertRaises(HTTPException) as exc_ctx:
                llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(exc_ctx.exception.status_code, 422)
            self.assertEqual(mocked_complete.call_args.kwargs["result"]["gate_mode"], "strict")
            self.assertTrue(mocked_complete.call_args.kwargs["result"]["gate_mode_fallback"])

    def test_generate_llm_report_off_mode_does_not_block_failed_gate(self):
        payload = llm_report_api.GenerateReportRequest(topic="缺少来源的主题", sources=[])
        with (
            patch.object(llm_report_api, "start_job", return_value=106),
            patch.object(llm_report_api, "complete_job") as mocked_complete,
            patch.object(llm_report_api, "resolve_report_sources", return_value=[]),
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "off"),
        ):
            resp = llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(resp["status"], "ok")
            self.assertEqual(resp["data"]["quality_gate"]["decision"], "fail")
            self.assertEqual(resp["data"]["observability"]["gate_mode"], "off")
            mocked_complete.assert_called_once()

    def test_generate_request_rejects_blank_section_title(self):
        with self.assertRaises(ValidationError):
            llm_report_api.GenerateReportRequest(topic="t", section_titles=["  "], sources=[])

    def test_generate_llm_report_wraps_internal_error_and_marks_failed_job(self):
        payload = llm_report_api.GenerateReportRequest(topic="test", sources=[])
        with (
            patch.object(llm_report_api, "start_job", return_value=105),
            patch.object(llm_report_api, "build_structured_report", side_effect=RuntimeError("boom")),
            patch.object(llm_report_api, "fail_job") as mocked_fail,
            patch.object(llm_report_api, "resolve_report_sources", return_value=[]),
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "warn"),
        ):
            with self.assertRaises(HTTPException) as exc_ctx:
                llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(exc_ctx.exception.status_code, 500)
            self.assertIn("LLM_REPORT_INTERNAL_ERROR", str(exc_ctx.exception.detail))
            mocked_fail.assert_called_once()

    def test_generate_llm_report_respects_feature_flag_disable(self):
        payload = llm_report_api.GenerateReportRequest(topic="test", sources=[])
        with (
            patch.object(llm_report_api.settings, "llm_report_enabled", False),
            patch.object(llm_report_api, "start_job") as mocked_start,
        ):
            with self.assertRaises(HTTPException) as exc_ctx:
                llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(exc_ctx.exception.status_code, 503)
            mocked_start.assert_not_called()

    def test_generate_llm_report_auto_resolves_sources_when_topic_only(self):
        payload = llm_report_api.GenerateReportRequest(topic="topic-only", sources=[])
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
            patch.object(llm_report_api, "start_job", return_value=107),
            patch.object(llm_report_api, "complete_job"),
            patch.object(llm_report_api, "resolve_report_sources", return_value=auto_sources) as mocked_resolve,
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "warn"),
        ):
            resp = llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(resp["status"], "ok")
            self.assertEqual(resp["data"]["report"]["sources"][0]["id"], "RAG1")
            mocked_resolve.assert_called_once()

    def test_generate_llm_report_auto_source_disabled_keeps_empty_sources(self):
        payload = llm_report_api.GenerateReportRequest(topic="topic-only", sources=[])
        with (
            patch.object(llm_report_api, "start_job", return_value=108),
            patch.object(llm_report_api, "complete_job"),
            patch.object(llm_report_api, "resolve_report_sources") as mocked_resolve,
            patch.object(llm_report_api.settings, "llm_report_enabled", True),
            patch.object(llm_report_api.settings, "llm_report_gate_mode", "warn"),
            patch.object(llm_report_api.settings, "llm_report_auto_source_enabled", False),
        ):
            resp = llm_report_api.generate_llm_report(payload, self._mock_request())
            self.assertEqual(resp["status"], "ok")
            self.assertEqual(resp["data"]["report"]["sources"], [])
            mocked_resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
