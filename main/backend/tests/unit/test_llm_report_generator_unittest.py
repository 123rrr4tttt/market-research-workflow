from __future__ import annotations

import unittest

from app.services.llm_report_generator import (
    ReportSection,
    StructuredReport,
    build_structured_report,
    evaluate_report_gate,
    render_markdown,
    validate_report_structure,
)


class LlmReportGeneratorUnitTest(unittest.TestCase):
    def test_generate_structured_report_with_sources(self):
        report = build_structured_report(
            topic="北美在线彩票增长",
            sources=[
                {
                    "id": "S1",
                    "title": "Example Source",
                    "url": "https://example.com/report",
                    "publisher": "Example Org",
                    "evidence": "market grew 12%",
                }
            ],
        )

        data = report.to_dict()
        self.assertEqual(data["topic"], "北美在线彩票增长")
        self.assertGreaterEqual(len(data["sections"]), 3)
        self.assertEqual(data["sources"][0]["id"], "S1")

        md = render_markdown(report)
        self.assertIn("# 研究报告：北美在线彩票增长", md)
        self.assertIn("[S1]", md)
        self.assertIn("## Sources", md)

        gate = evaluate_report_gate(report)
        self.assertTrue(gate["pass"])
        self.assertGreaterEqual(gate["citation_coverage"], 0.8)
        self.assertIn("structure_validation", gate)
        self.assertTrue(gate["structure_validation"]["pass"])

    def test_validate_report_structure_rejects_missing_source_citation(self):
        report = StructuredReport(
            topic="Robotics Market",
            generated_at="2026-03-03T00:00:00+00:00",
            sections=[
                ReportSection(
                    title="执行摘要",
                    content="这是一个长度足够的摘要内容，用于结构校验。",
                    citations=["S1", "S404"],
                )
            ],
            sources=[
                {
                    "id": "S1",
                    "title": "Known Source",
                    "url": "https://example.com/s1",
                    "publisher": "Example",
                    "published_at": None,
                    "retrieved_at": "2026-03-03T00:00:00+00:00",
                    "evidence": "evidence",
                }
            ],
        )

        validation = validate_report_structure(report)
        self.assertFalse(validation["pass"])
        self.assertIn("section_1_citation_missing_source:S404", validation["errors"])

        gate = evaluate_report_gate(report)
        self.assertFalse(gate["pass"])

    def test_empty_topic_raises(self):
        with self.assertRaises(ValueError):
            build_structured_report(topic="   ", sources=[])


if __name__ == "__main__":
    unittest.main()
