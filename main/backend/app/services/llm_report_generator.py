from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


DEFAULT_SECTION_TITLES = [
    "执行摘要",
    "研究范围与方法",
    "关键发现",
    "风险与不确定性",
    "行动建议",
]


@dataclass
class ReportSection:
    title: str
    content: str
    citations: list[str]


@dataclass
class StructuredReport:
    topic: str
    generated_at: str
    sections: list[ReportSection]
    sources: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "generated_at": self.generated_at,
            "sections": [
                {
                    "title": section.title,
                    "content": section.content,
                    "citations": section.citations,
                }
                for section in self.sections
            ],
            "sources": self.sources,
        }


def _normalize_sources(raw_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for i, source in enumerate(raw_sources, start=1):
        sid = str(source.get("id") or f"S{i}")
        normalized.append(
            {
                "id": sid,
                "title": str(source.get("title") or f"Source {i}"),
                "url": str(source.get("url") or ""),
                "publisher": str(source.get("publisher") or "unknown"),
                "published_at": source.get("published_at"),
                "retrieved_at": source.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
                "evidence": str(source.get("evidence") or ""),
            }
        )
    return normalized


def build_structured_report(
    topic: str,
    sources: list[dict[str, Any]],
    section_titles: list[str] | None = None,
) -> StructuredReport:
    cleaned_topic = topic.strip()
    if not cleaned_topic:
        raise ValueError("topic cannot be empty")

    normalized_sources = _normalize_sources(sources)
    source_ids = [s["id"] for s in normalized_sources]
    section_titles = section_titles or DEFAULT_SECTION_TITLES

    sections = [
        ReportSection(
            title=title,
            content=(
                f"围绕主题“{cleaned_topic}”，本节由模板生成。"
                f"请在后续流程补充事实推理、数据图表与关键结论。"
            ),
            citations=source_ids[: min(3, len(source_ids))],
        )
        for title in section_titles
    ]

    return StructuredReport(
        topic=cleaned_topic,
        generated_at=datetime.now(timezone.utc).isoformat(),
        sections=sections,
        sources=normalized_sources,
    )


def validate_report_structure(report: StructuredReport) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    topic = str(report.topic or "").strip()
    if not topic:
        errors.append("topic_empty")

    if not report.sections:
        errors.append("sections_empty")
    if len(report.sections) < 3:
        warnings.append("sections_too_few")
    if not report.sources:
        warnings.append("sources_empty")

    source_ids = {str(source.get("id") or "").strip() for source in report.sources}
    source_ids.discard("")

    normalized_titles: list[str] = []

    for idx, section in enumerate(report.sections, start=1):
        title = str(section.title or "").strip()
        content = str(section.content or "").strip()
        if not title:
            errors.append(f"section_{idx}_title_empty")
        else:
            normalized_titles.append(title)
        if not content:
            errors.append(f"section_{idx}_content_empty")
        if len(content) < 20:
            warnings.append(f"section_{idx}_content_too_short")
        for cid in section.citations:
            normalized_cid = str(cid or "").strip()
            if not normalized_cid:
                errors.append(f"section_{idx}_citation_empty")
                continue
            if normalized_cid not in source_ids:
                errors.append(f"section_{idx}_citation_missing_source:{normalized_cid}")

    return {
        "pass": len(errors) == 0,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "rules": {
            "topic_required": True,
            "sections_required": True,
            "section_title_required": True,
            "section_content_required": True,
            "citation_must_exist_in_sources": True,
        },
    }


def evaluate_report_gate(report: StructuredReport) -> dict[str, Any]:
    total_sections = len(report.sections)
    cited_sections = sum(1 for section in report.sections if section.citations)
    citation_coverage = (cited_sections / total_sections) if total_sections else 0.0
    source_count = len(report.sources)
    unique_citations = sorted(
        {cid for section in report.sections for cid in section.citations}
    )
    structure_validation = validate_report_structure(report)
    pass_gate = (
        citation_coverage >= 0.8
        and source_count >= 1
        and len(unique_citations) >= 1
        and bool(structure_validation["pass"])
    )
    return {
        "citation_coverage": round(citation_coverage, 4),
        "source_count": source_count,
        "unique_citations": unique_citations,
        "structure_validation": structure_validation,
        "pass": pass_gate,
        "rules": {
            "citation_coverage_min": 0.8,
            "source_count_min": 1,
            "structure_validation_pass_required": True,
        },
    }


def render_markdown(report: StructuredReport) -> str:
    lines: list[str] = [
        f"# 研究报告：{report.topic}",
        "",
        f"- 生成时间: {report.generated_at}",
        f"- 来源数量: {len(report.sources)}",
        "",
    ]

    for section in report.sections:
        lines.append(f"## {section.title}")
        lines.append(section.content)
        if section.citations:
            lines.append("")
            lines.append("引用: " + ", ".join(f"[{cid}]" for cid in section.citations))
        lines.append("")

    lines.append("## Sources")
    for source in report.sources:
        lines.append(
            f"- [{source['id']}] {source['title']} | {source['publisher']} | {source['url']}"
        )

    return "\n".join(lines).strip() + "\n"
