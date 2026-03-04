from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.api.llm_report import GenerateReportRequest, SourceInput, generate_llm_report


class LlmReportApiUnitTest(unittest.TestCase):
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
