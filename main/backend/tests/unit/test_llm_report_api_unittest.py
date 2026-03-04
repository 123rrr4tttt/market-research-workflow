from __future__ import annotations

import unittest

try:
    from pydantic import ValidationError
    from app.api.llm_report import GenerateReportRequest, SourceInput, generate_llm_report
except Exception as exc:  # pragma: no cover - dependency/import guard
    ValidationError = Exception  # type: ignore[assignment]
    GenerateReportRequest = None  # type: ignore[assignment]
    SourceInput = None  # type: ignore[assignment]
    generate_llm_report = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class LlmReportApiUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"llm report api unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_generate_llm_report_returns_quality_gate_envelope(self):
        payload = GenerateReportRequest(
            topic="北美在线彩票增长",
            sources=[
                SourceInput(
                    id="S1",
                    title="Example Source",
                    url="https://example.com/report",
                    publisher="Example Org",
                    evidence="market grew 12%",
                )
            ],
        )
        resp = generate_llm_report(payload)
        self.assertEqual(resp["status"], "ok")
        self.assertIn("report", resp["data"])
        self.assertIn("quality_gate", resp["data"])
        self.assertIn("decision", resp["data"]["quality_gate"])

    def test_generate_request_rejects_invalid_url(self):
        with self.assertRaises(ValidationError):
            GenerateReportRequest(
                topic="test",
                sources=[
                    SourceInput(
                        id="S1",
                        title="x",
                        url="not-a-url",
                    )
                ],
            )


if __name__ == "__main__":
    unittest.main()
