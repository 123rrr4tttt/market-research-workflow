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
        self.assertEqual(gate["decision"], "pass")
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
        self.assertEqual(gate["decision"], "fail")
        self.assertIn("structure_invalid", gate["hard_failures"])

    def test_empty_topic_raises(self):
        with self.assertRaises(ValueError):
            build_structured_report(topic="   ", sources=[])

    def test_structure_validation_warns_for_duplicate_titles_and_short_sections(self):
        report = StructuredReport(
            topic="test",
            generated_at="2026-03-04T00:00:00Z",
            sections=[
                ReportSection(title="A", content="too short", citations=["S1"]),
                ReportSection(title="A", content="still short", citations=["S1"]),
            ],
            sources=[{"id": "S1", "title": "t", "url": "https://example.com", "publisher": "p"}],
        )
        validation = validate_report_structure(report)
        self.assertTrue(validation["pass"])
        self.assertIn("sections_too_few", validation["warnings"])
        self.assertIn("section_title_duplicate", validation["warnings"])

    def test_gate_soft_degrade_when_evidence_is_missing(self):
        report = StructuredReport(
            topic="test",
            generated_at="2026-03-04T00:00:00Z",
            sections=[
                ReportSection(
                    title="A",
                    content="这是长度足够的内容，用于通过结构校验并触发软降级。",
                    citations=["S1"],
                ),
                ReportSection(
                    title="B",
                    content="这是长度足够的内容，用于通过结构校验并触发软降级。",
                    citations=["S2"],
                ),
                ReportSection(
                    title="C",
                    content="这是长度足够的内容，用于通过结构校验并触发软降级。",
                    citations=["S3"],
                ),
            ],
            sources=[
                {"id": "S1", "title": "t1", "url": "https://example.com/1", "publisher": "p", "evidence": "ok"},
                {"id": "S2", "title": "t2", "url": "https://example.com/2", "publisher": "p", "evidence": ""},
                {"id": "S3", "title": "t3", "url": "https://example.com/3", "publisher": "p", "evidence": ""},
            ],
        )
        gate = evaluate_report_gate(report)
        self.assertFalse(gate["pass"])
        self.assertEqual(gate["decision"], "warn")
        self.assertEqual(gate["hard_failures"], [])
        self.assertIn("evidence_coverage_below_min:0.6", gate["soft_failures"])
        self.assertIn("source_evidence:S2,S3", gate["missing_items"])

    def test_gate_hard_reject_when_sections_below_min(self):
        report = StructuredReport(
            topic="test",
            generated_at="2026-03-04T00:00:00Z",
            sections=[
                ReportSection(
                    title="A",
                    content="这是长度足够的内容，用于结构校验。",
                    citations=["S1"],
                ),
                ReportSection(
                    title="B",
                    content="这是长度足够的内容，用于结构校验。",
                    citations=["S1"],
                ),
            ],
            sources=[{"id": "S1", "title": "t", "url": "https://example.com", "publisher": "p", "evidence": "ok"}],
        )
        gate = evaluate_report_gate(report)
        self.assertFalse(gate["pass"])
        self.assertEqual(gate["decision"], "fail")
        self.assertIn("sections_below_min:3", gate["hard_failures"])

    def test_quality_gate_observability_fields_exist(self):
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
        gate = evaluate_report_gate(report)
        self.assertIn("gate_version", gate)
        self.assertIn("hard_failures", gate)
        self.assertIn("soft_failures", gate)
        self.assertIn("missing_items", gate)
        self.assertIn("observability", gate)
        self.assertIn("generated_at", gate["observability"])
        self.assertIn("citation_coverage_min_hard", gate["rules"])

    def test_validate_report_structure_rejects_source_without_url(self):
        report = StructuredReport(
            topic="test",
            generated_at="2026-03-04T00:00:00Z",
            sections=[
                ReportSection(
                    title="A",
                    content="这是长度足够的内容，用于结构校验。",
                    citations=["S1"],
                ),
                ReportSection(
                    title="B",
                    content="这是长度足够的内容，用于结构校验。",
                    citations=["S1"],
                ),
                ReportSection(
                    title="C",
                    content="这是长度足够的内容，用于结构校验。",
                    citations=["S1"],
                ),
            ],
            sources=[{"id": "S1", "title": "t", "url": "", "publisher": "p", "evidence": "ok"}],
        )
        validation = validate_report_structure(report)
        self.assertFalse(validation["pass"])
        self.assertIn("source_1_url_empty", validation["errors"])


if __name__ == "__main__":
    unittest.main()
