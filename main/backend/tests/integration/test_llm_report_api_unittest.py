from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class LlmReportApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"llm report integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "llm-report-integration"}

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
        mocked_resolve.assert_called_once()

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
        mocked_resolve.assert_not_called()

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
