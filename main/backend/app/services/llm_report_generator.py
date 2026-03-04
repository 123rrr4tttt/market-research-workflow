from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


GATE_VERSION = "r2.1"
MIN_SECTION_COUNT_HARD = 3
MIN_CITATION_COVERAGE_HARD = 0.8
MIN_SOURCE_COUNT_HARD = 1
MIN_UNIQUE_CITATIONS_HARD = 1
MIN_EVIDENCE_COVERAGE_SOFT = 0.6
SHORT_SECTION_LEN_SOFT = 20


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
    sources_missing_evidence: list[str] = []

    for idx, source in enumerate(report.sources, start=1):
        source_id = str(source.get("id") or "").strip()
        title = str(source.get("title") or "").strip()
        url = str(source.get("url") or "").strip()
        evidence = str(source.get("evidence") or "").strip()
        if not source_id:
            errors.append(f"source_{idx}_id_empty")
        if not title:
            errors.append(f"source_{idx}_title_empty")
        if not url:
            errors.append(f"source_{idx}_url_empty")
        if not evidence:
            warnings.append(f"source_{idx}_evidence_missing")
            if source_id:
                sources_missing_evidence.append(source_id)

    normalized_titles: list[str] = []
    sections_without_citations: list[int] = []

    for idx, section in enumerate(report.sections, start=1):
        title = str(section.title or "").strip()
        content = str(section.content or "").strip()
        citation_ids_in_section: list[str] = []
        if not title:
            errors.append(f"section_{idx}_title_empty")
        else:
            normalized_titles.append(title)
        if not content:
            errors.append(f"section_{idx}_content_empty")
        if len(content) < 20:
            warnings.append(f"section_{idx}_content_too_short")
        if not section.citations:
            sections_without_citations.append(idx)
            warnings.append(f"section_{idx}_citations_missing")
        for cid in section.citations:
            normalized_cid = str(cid or "").strip()
            if not normalized_cid:
                errors.append(f"section_{idx}_citation_empty")
                continue
            citation_ids_in_section.append(normalized_cid)
            if normalized_cid not in source_ids:
                errors.append(f"section_{idx}_citation_missing_source:{normalized_cid}")
        if len(set(citation_ids_in_section)) != len(citation_ids_in_section):
            warnings.append(f"section_{idx}_citation_duplicate")

    if len(set(normalized_titles)) != len(normalized_titles):
        warnings.append("section_title_duplicate")

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
            "source_title_required": True,
            "source_url_required": True,
            "source_evidence_recommended": True,
        },
        "observability": {
            "total_sections": len(report.sections),
            "sections_without_citations": sections_without_citations,
            "sources_missing_evidence": sources_missing_evidence,
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
    sections_without_citations = [
        idx
        for idx, section in enumerate(report.sections, start=1)
        if not section.citations
    ]
    sources_missing_evidence = [
        str(source.get("id") or f"S{idx}")
        for idx, source in enumerate(report.sources, start=1)
        if not str(source.get("evidence") or "").strip()
    ]
    evidence_coverage = (
        (source_count - len(sources_missing_evidence)) / source_count
        if source_count
        else 0.0
    )
    short_section_count = sum(
        1
        for section in report.sections
        if len(str(section.content or "").strip()) < SHORT_SECTION_LEN_SOFT
    )

    hard_failures: list[str] = []
    soft_failures: list[str] = []
    missing_items: list[str] = []

    if not bool(structure_validation["pass"]):
        hard_failures.append("structure_invalid")
    if total_sections < MIN_SECTION_COUNT_HARD:
        hard_failures.append(f"sections_below_min:{MIN_SECTION_COUNT_HARD}")
    if citation_coverage < MIN_CITATION_COVERAGE_HARD:
        hard_failures.append(f"citation_coverage_below_min:{MIN_CITATION_COVERAGE_HARD}")
    if source_count < MIN_SOURCE_COUNT_HARD:
        hard_failures.append(f"source_count_below_min:{MIN_SOURCE_COUNT_HARD}")
        missing_items.append("sources")
    if len(unique_citations) < MIN_UNIQUE_CITATIONS_HARD:
        hard_failures.append(f"unique_citations_below_min:{MIN_UNIQUE_CITATIONS_HARD}")
        missing_items.append("citations")

    if evidence_coverage < MIN_EVIDENCE_COVERAGE_SOFT:
        soft_failures.append(
            f"evidence_coverage_below_min:{round(MIN_EVIDENCE_COVERAGE_SOFT, 4)}"
        )
    if short_section_count > 0:
        soft_failures.append("sections_with_short_content")
    if sections_without_citations:
        soft_failures.append("sections_without_citations")
        missing_items.append(f"section_citations:{','.join(map(str, sections_without_citations))}")
    if sources_missing_evidence:
        missing_items.append(f"source_evidence:{','.join(sorted(set(sources_missing_evidence)))}")

    hard_failures = sorted(set(hard_failures))
    soft_failures = sorted(set(soft_failures))
    missing_items = sorted(set(missing_items))

    decision = "pass"
    if hard_failures:
        decision = "fail"
    elif soft_failures:
        decision = "warn"

    confidence_score = max(
        0.0,
        1.0 - (0.25 * len(hard_failures)) - (0.08 * len(soft_failures)),
    )

    return {
        "gate_version": GATE_VERSION,
        "citation_coverage": round(citation_coverage, 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "source_count": source_count,
        "unique_citations": unique_citations,
        "structure_validation": structure_validation,
        "hard_failures": hard_failures,
        "soft_failures": soft_failures,
        "missing_items": missing_items,
        "decision": decision,
        "confidence_score": round(confidence_score, 4),
        "pass": decision == "pass",
        "rules": {
            "min_sections_hard": MIN_SECTION_COUNT_HARD,
            "citation_coverage_min_hard": MIN_CITATION_COVERAGE_HARD,
            "source_count_min_hard": MIN_SOURCE_COUNT_HARD,
            "unique_citations_min_hard": MIN_UNIQUE_CITATIONS_HARD,
            "evidence_coverage_min_soft": MIN_EVIDENCE_COVERAGE_SOFT,
            "structure_validation_pass_required": True,
        },
        "observability": {
            "total_sections": total_sections,
            "cited_sections": cited_sections,
            "sections_without_citations": sections_without_citations,
            "sources_missing_evidence": sources_missing_evidence,
            "short_section_count": short_section_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
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
