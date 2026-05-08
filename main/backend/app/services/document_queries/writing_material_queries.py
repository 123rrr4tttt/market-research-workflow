from __future__ import annotations

from typing import Any

from ..llm_report_source_enrichment import resolve_report_sources
from ..search.hybrid import hybrid_search
from ..source_library.resolver import list_effective_items


def query_hybrid_document_rows(query: str, *, limit: int) -> list[dict[str, Any]]:
    rows = hybrid_search(query, state=None, top_k=limit, mode="hybrid")
    return [dict(row) for row in rows if isinstance(row, dict)]


def query_report_source_rows(query: str, *, limit: int) -> list[dict[str, Any]]:
    rows = resolve_report_sources(query, None, target_count=limit)
    return [dict(row) for row in rows if isinstance(row, dict)]


def query_source_library_material_rows(project_key: str, *, query: str) -> list[dict[str, Any]]:
    normalized = str(query or "").strip().lower()
    items = list_effective_items(project_key=project_key)
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if normalized:
            blob = " ".join(
                [
                    str(item.get("item_key") or ""),
                    str(item.get("name") or ""),
                    str(item.get("description") or ""),
                ]
            ).lower()
            if normalized not in blob:
                continue
        rows.append(dict(item))
    return rows
