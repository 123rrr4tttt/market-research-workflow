from __future__ import annotations

from typing import Any, Iterable, Mapping

from .contracts import (
    DOCUMENT_QUERY_CONTRACT_VERSION,
    DocumentQuery,
    build_document_query,
    build_document_query_result_envelope,
    validate_document_query_result_envelope,
)


SEARCH_ENDPOINT_CONSUMER = "api.search"
SEARCH_ENDPOINT_SOURCE = "api.search.hybrid"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_optional_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _mapping_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_search_endpoint_document_query(
    *,
    query: str,
    state: str | None = None,
    project_key: str | None = None,
    limit: int,
) -> DocumentQuery:
    filters: list[dict[str, Any]] = []
    state_filter = _clean_optional_text(state)
    if state_filter:
        filters.append({"field": "state", "op": "eq", "value": state_filter})

    return build_document_query(
        query,
        project_key=_clean_optional_text(project_key),
        consumer=SEARCH_ENDPOINT_CONSUMER,
        sources=("document",),
        filters=filters,
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )


def build_search_endpoint_document_query_envelope(
    *,
    query: str,
    state: str | None = None,
    modality: str = "any",
    rank: str = "hybrid",
    top_k: int,
    results: Iterable[Any],
    project_key: str | None = None,
    used_backends: Iterable[str] = (),
) -> dict[str, Any]:
    query_object = build_search_endpoint_document_query(
        query=query,
        state=state,
        project_key=project_key,
        limit=top_k,
    )
    envelope = build_document_query_result_envelope(
        query_object,
        _mapping_rows(results),
        source=SEARCH_ENDPOINT_SOURCE,
        result_source_type="document",
        meta={
            "contract_version": DOCUMENT_QUERY_CONTRACT_VERSION,
            "endpoint": "/api/v1/search",
            "rank_mode": _clean_text(rank) or "hybrid",
            "modality": _clean_text(modality) or "any",
            "top_k": query_object.limit,
            "search_backends_used": [_clean_text(item) for item in used_backends if _clean_text(item)],
        },
    )
    validate_document_query_result_envelope(envelope)
    return envelope
