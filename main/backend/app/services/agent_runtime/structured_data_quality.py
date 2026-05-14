from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Text, cast, func, select

from app.models.base import SessionLocal
from app.models.entities import Document, GraphNodeRecord
from app.services.projects import bind_project


_NOISE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("script_branch", re.compile(r"\bif\s*\(\s*typeof\b", re.IGNORECASE)),
    ("javascript_global", re.compile(r"\b(window|document|googletag|adinstance|dataLayer)\s*[\.\[]", re.IGNORECASE)),
    ("html_shell", re.compile(r"<\s*/?\s*(script|style|iframe|noscript|html|body)\b", re.IGNORECASE)),
    ("css_block", re.compile(r"\.[A-Za-z][\w-]*\s*\{")),
    ("css_declaration", re.compile(r"\b(grid-template|font-size|line-height|@media|display\s*:|margin\s*:|padding\s*:)", re.IGNORECASE)),
)
_SCAN_TEXT_LIMIT = 4000


def audit_project_structured_data_quality(
    *,
    project_key: str | None,
    scan_limit: int = 500,
    sample_limit: int = 20,
) -> dict[str, Any]:
    resolved_project_key = str(project_key or "").strip()
    if not resolved_project_key:
        return {
            "contract_version": "project.structured_data.quality_audit.v1",
            "project_key": project_key,
            "status": "failed",
            "error": {"code": "missing_project_key", "message": "project_key is required"},
        }

    capped_scan = max(1, min(5000, int(scan_limit or 500)))
    capped_samples = max(1, min(100, int(sample_limit or 20)))
    findings: list[dict[str, Any]] = []
    scanned = {"documents": 0, "graph_nodes": 0}

    with bind_project(resolved_project_key):
        with SessionLocal() as session:
            doc_rows = session.execute(_document_scan_statement(capped_scan)).all()
            scanned["documents"] = len(doc_rows)
            for row in doc_rows:
                finding = _document_noise_finding(row)
                if finding:
                    findings.append(finding)

            graph_rows = session.execute(_graph_node_scan_statement(capped_scan)).all()
            scanned["graph_nodes"] = len(graph_rows)
            for row in graph_rows:
                finding = _graph_node_noise_finding(row)
                if finding:
                    findings.append(finding)

    by_dataset: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for item in findings:
        dataset = str(item.get("dataset") or "unknown")
        by_dataset[dataset] = by_dataset.get(dataset, 0) + 1
        for reason in item.get("noise_reasons") or []:
            key = str(reason or "unknown")
            by_reason[key] = by_reason.get(key, 0) + 1

    return {
        "contract_version": "project.structured_data.quality_audit.v1",
        "project_key": resolved_project_key,
        "status": "completed",
        "scan_limit": capped_scan,
        "sample_limit": capped_samples,
        "scanned": scanned,
        "noisy_record_count": len(findings),
        "by_dataset": by_dataset,
        "by_reason": by_reason,
        "samples": findings[:capped_samples],
        "recommended_actions": [
            "Keep raw content as evidence; do not delete automatically.",
            "Mark noisy records with quality flags before they are used as representative answer samples.",
            "Prefer re-extraction or article-content parsing for noisy webpage-shell documents.",
            "Regenerate graph nodes whose properties were derived from script/style/nav-heavy records.",
        ],
    }


def _document_scan_statement(scan_limit: int) -> Any:
    return (
        select(
            Document.id,
            Document.title,
            Document.uri,
            func.substr(cast(Document.summary, Text), 1, _SCAN_TEXT_LIMIT).label("summary_sample"),
            func.substr(cast(Document.content, Text), 1, _SCAN_TEXT_LIMIT).label("content_sample"),
        )
        .order_by(Document.updated_at.desc(), Document.created_at.desc())
        .limit(scan_limit)
    )


def _graph_node_scan_statement(scan_limit: int) -> Any:
    return (
        select(
            GraphNodeRecord.id,
            GraphNodeRecord.display_name,
            GraphNodeRecord.canonical_id,
            func.substr(cast(GraphNodeRecord.properties, Text), 1, _SCAN_TEXT_LIMIT).label("properties_sample"),
        )
        .order_by(GraphNodeRecord.updated_at.desc(), GraphNodeRecord.created_at.desc())
        .limit(scan_limit)
    )


def detect_structured_record_noise(value: Any) -> dict[str, Any]:
    text = _stringify(value)
    if not text:
        return {"is_noisy": False, "noise_reasons": [], "punctuation_ratio": 0.0}
    reasons = [name for name, pattern in _NOISE_PATTERNS if pattern.search(text)]
    punctuation_ratio = _punctuation_ratio(text)
    if len(text) > 180 and punctuation_ratio > 0.24:
        reasons.append("punctuation_dense_shell")
    return {
        "is_noisy": bool(reasons),
        "noise_reasons": sorted(set(reasons)),
        "punctuation_ratio": round(punctuation_ratio, 4),
    }


def _document_noise_finding(row: Any) -> dict[str, Any] | None:
    summary = getattr(row, "summary_sample", None)
    content = getattr(row, "content_sample", None)
    summary_noise = detect_structured_record_noise(summary)
    content_noise = detect_structured_record_noise(content)
    reasons = sorted(set(summary_noise["noise_reasons"] + content_noise["noise_reasons"]))
    if not reasons:
        return None
    return {
        "dataset": "documents",
        "record_id": row.id,
        "title": _trim(row.title or row.uri or f"document:{row.id}", 180),
        "source_uri": row.uri,
        "noise_reasons": reasons,
        "summary_noisy": bool(summary_noise["is_noisy"]),
        "content_noisy": bool(content_noise["is_noisy"]),
        "sample": _trim(summary or content or "", 240),
        "recommended_action": "mark_quality_flag_and_reextract_article_content",
    }


def _graph_node_noise_finding(row: Any) -> dict[str, Any] | None:
    properties = getattr(row, "properties_sample", None)
    noise = detect_structured_record_noise(properties)
    if not noise["is_noisy"]:
        return None
    return {
        "dataset": "graph_nodes",
        "record_id": row.id,
        "title": _trim(row.display_name or row.canonical_id, 180),
        "noise_reasons": noise["noise_reasons"],
        "sample": _trim(properties, 240),
        "recommended_action": "mark_quality_flag_and_regenerate_node_projection",
    }


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _trim(value: Any, limit: int) -> str:
    text = _stringify(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _punctuation_ratio(text: str) -> float:
    if not text:
        return 0.0
    punctuation = sum(1 for char in text if not char.isalnum() and not char.isspace())
    return punctuation / max(1, len(text))
