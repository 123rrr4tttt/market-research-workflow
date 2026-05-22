from __future__ import annotations

from typing import Any

from ..llm_report_source_enrichment import resolve_report_sources
from ..search.hybrid import hybrid_search
from ..source_library.resolver import list_effective_items
from .contracts import (
    build_document_query,
    build_document_query_result_envelope,
    rows_for_document_views,
)


def query_hybrid_document_envelope(query: str, *, limit: int) -> dict[str, Any]:
    query_object = build_document_query(
        query,
        consumer="writing.keyword_cards",
        sources=("document",),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )
    rows = hybrid_search(query, state=None, top_k=limit, mode="hybrid")
    return build_document_query_result_envelope(
        query_object,
        [dict(row) for row in rows if isinstance(row, dict)],
        source="search.hybrid",
        result_source_type="document",
    )


def query_hybrid_document_rows(query: str, *, limit: int) -> list[dict[str, Any]]:
    return rows_for_document_views(query_hybrid_document_envelope(query, limit=limit))


def query_report_source_envelope(query: str, *, limit: int) -> dict[str, Any]:
    query_object = build_document_query(
        query,
        consumer="writing.keyword_cards",
        sources=("resource",),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )
    rows = resolve_report_sources(query, None, target_count=limit)
    return build_document_query_result_envelope(
        query_object,
        [dict(row) for row in rows if isinstance(row, dict)],
        source="llm_report_source_enrichment",
        result_source_type="resource",
    )


def query_report_source_rows(query: str, *, limit: int) -> list[dict[str, Any]]:
    return rows_for_document_views(query_report_source_envelope(query, limit=limit))


def query_source_library_material_envelope(project_key: str, *, query: str, limit: int | None = None) -> dict[str, Any]:
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
    query_object = build_document_query(
        query,
        project_key=project_key,
        consumer="writing.keyword_cards",
        sources=("source_library",),
        filters=({"field": "project_key", "op": "eq", "value": project_key},),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit if limit is not None else max(1, len(rows) or 1),
    )
    return build_document_query_result_envelope(
        query_object,
        rows[: query_object.limit],
        source="source_library.resolver",
        result_source_type="resource",
        total=len(rows),
    )


def query_source_library_material_rows(project_key: str, *, query: str) -> list[dict[str, Any]]:
    return rows_for_document_views(query_source_library_material_envelope(project_key, query=query))
