from __future__ import annotations

from ..llm_report_source_enrichment import resolve_report_sources
from ..search.hybrid import SearchInvocationObservation, observe_hybrid_search, search_failure_payload
from ..source_library.resolver import list_effective_items
from .contracts import (
    MaterialQueryResultEnvelope,
    MaterialQueryRow,
    build_material_query,
    build_material_query_result_envelope,
    coerce_material_query_result_row,
    rows_for_material_views,
)


def query_hybrid_material_observation(
    query: str, *, limit: int
) -> tuple[MaterialQueryResultEnvelope, SearchInvocationObservation]:
    query_object = build_material_query(
        query,
        consumer="writing.keyword_cards",
        sources=("material",),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )
    observation = observe_hybrid_search(query, state=None, top_k=limit, mode="hybrid")
    rows = [coerce_material_query_result_row(row) for row in observation.hits]
    envelope = build_material_query_result_envelope(
        query_object,
        rows,
        source="search.hybrid",
        result_source_type="material",
        meta={
            "search_backends_used": list(observation.used_backends),
            "search_failures": [
                search_failure_payload(failure) for failure in observation.failures
            ],
        },
    )
    return envelope, observation


def query_report_source_envelope(query: str, *, limit: int) -> MaterialQueryResultEnvelope:
    query_object = build_material_query(
        query,
        consumer="writing.keyword_cards",
        sources=("resource",),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )
    resolution = resolve_report_sources(query, None, target_count=limit)
    rows = [coerce_material_query_result_row(row) for row in resolution.sources]
    return build_material_query_result_envelope(
        query_object,
        rows,
        source="llm_report_source_enrichment",
        result_source_type="resource",
        meta={
            "source_resolution_kind": resolution.kind,
            "search_failures": [failure.to_payload() for failure in resolution.failures],
        },
    )


def query_source_library_material_envelope(project_key: str, *, query: str, limit: int | None = None) -> MaterialQueryResultEnvelope:
    normalized = str(query or "").strip().lower()
    items = list_effective_items(project_key=project_key)
    rows: list[MaterialQueryRow] = []
    for item in items:
        row = coerce_material_query_result_row(item)
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
        rows.append(row)
    query_object = build_material_query(
        query,
        project_key=project_key,
        consumer="writing.keyword_cards",
        sources=("source_library",),
        filters=({"field": "project_key", "op": "eq", "value": project_key},),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit if limit is not None else max(1, len(rows) or 1),
    )
    return build_material_query_result_envelope(
        query_object,
        rows[: query_object.limit],
        source="source_library.resolver",
        result_source_type="resource",
        total=len(rows),
    )


def query_source_library_material_rows(project_key: str, *, query: str) -> list[MaterialQueryRow]:
    return rows_for_material_views(query_source_library_material_envelope(project_key, query=query))
