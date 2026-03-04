from __future__ import annotations

import unittest

import pytest

from app.services.llm_report_generator import (
    ReportSection,
    StructuredReport,
    build_structured_report,
    evaluate_report_gate,
    render_markdown,
    validate_report_structure,
)

pytestmark = pytest.mark.unit


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
            template_version="v1.1",
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
            template_version="v1.1",
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
            template_version="v1.1",
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
            template_version="v1.1",
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
        self.assertIn("gate_started_at", gate["observability"])
        self.assertIn("gate_finished_at", gate["observability"])
        self.assertIn("gate_duration_ms", gate["observability"])
        self.assertIn("citation_coverage_min_hard", gate["rules"])

    def test_quality_gate_must_minset_baseline(self):
        pass_report = build_structured_report(
            topic="北美在线彩票增长",
            sources=[
                {
                    "id": "S1",
                    "title": "Source 1",
                    "url": "https://example.com/1",
                    "publisher": "Example",
                    "evidence": "evidence",
                }
            ],
        )
        pass_gate = evaluate_report_gate(pass_report)
        self.assertEqual(pass_gate["decision"], "pass")

        warn_report = StructuredReport(
            topic="warn-case",
            generated_at="2026-03-04T00:00:00Z",
            template_version="v1.1",
            sections=[
                ReportSection(title="A", content="这是长度足够的内容，用于触发软门禁。", citations=["S1"]),
                ReportSection(title="B", content="这是长度足够的内容，用于触发软门禁。", citations=["S2"]),
                ReportSection(title="C", content="这是长度足够的内容，用于触发软门禁。", citations=["S3"]),
            ],
            sources=[
                {"id": "S1", "title": "t1", "url": "https://example.com/1", "publisher": "p", "evidence": "ok"},
                {"id": "S2", "title": "t2", "url": "https://example.com/2", "publisher": "p", "evidence": ""},
                {"id": "S3", "title": "t3", "url": "https://example.com/3", "publisher": "p", "evidence": ""},
            ],
        )
        warn_gate = evaluate_report_gate(warn_report)
        self.assertEqual(warn_gate["decision"], "warn")

        fail_report = StructuredReport(
            topic="fail-case",
            generated_at="2026-03-04T00:00:00Z",
            template_version="v1.1",
            sections=[
                ReportSection(title="A", content="这是长度足够的内容。", citations=["S1"]),
                ReportSection(title="B", content="这是长度足够的内容。", citations=["S1"]),
            ],
            sources=[{"id": "S1", "title": "t1", "url": "https://example.com/1", "publisher": "p", "evidence": "ok"}],
        )
        fail_gate = evaluate_report_gate(fail_report)
        self.assertEqual(fail_gate["decision"], "fail")

    def test_validate_report_structure_rejects_source_without_url(self):
        report = StructuredReport(
            topic="test",
            generated_at="2026-03-04T00:00:00Z",
            template_version="v1.1",
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

    def test_markdown_renderer_escapes_user_controlled_tokens(self):
        report = StructuredReport(
            topic="#topic [x] <img src=x onerror=alert(1)>",
            generated_at="2026-03-04T00:00:00Z",
            template_version="v1.1",
            sections=[
                ReportSection(
                    title="sec*1",
                    content="payload [link](javascript:alert(1)) <script>alert(1)</script>",
                    citations=["S1"],
                )
            ],
            sources=[
                {
                    "id": "S1",
                    "title": "src](1)",
                    "url": "https://example.com/a(b)",
                    "publisher": "p#1",
                    "evidence": "ok",
                }
            ],
        )
        markdown = render_markdown(report)
        self.assertIn("# 研究报告：\\#topic \\[x\\] &lt;img src=x onerror=alert\\(1\\)&gt;", markdown)
        self.assertIn("payload \\[link\\]\\(javascript:alert\\(1\\)\\)", markdown)
        self.assertIn("&lt;script&gt;alert\\(1\\)&lt;/script&gt;", markdown)
        self.assertIn("引用: \\[S1\\]", markdown)

    def test_validate_report_structure_rejects_duplicate_source_ids(self):
        report = StructuredReport(
            topic="duplicate-source-id",
            generated_at="2026-03-04T00:00:00Z",
            template_version="v1.1",
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
            sources=[
                {"id": "S1", "title": "t1", "url": "https://example.com/1", "publisher": "p", "evidence": "ok"},
                {"id": "S1", "title": "t2", "url": "https://example.com/2", "publisher": "p", "evidence": "ok"},
            ],
        )
        validation = validate_report_structure(report)
        self.assertFalse(validation["pass"])
        self.assertIn("source_id_duplicate", validation["errors"])


if __name__ == "__main__":
    unittest.main()
