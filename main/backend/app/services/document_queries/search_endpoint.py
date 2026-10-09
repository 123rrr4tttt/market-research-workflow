from __future__ import annotations

from typing import Annotated, Iterable

from .contracts import (
    MATERIAL_QUERY_CONTRACT_VERSION,
    MaterialQuery,
    MaterialQueryFilterInput,
    MaterialQueryResultEnvelope,
    MaterialQueryRow,
    build_material_query,
    build_material_query_result_envelope,
    coerce_material_query_result_row,
    validate_material_query_result_envelope,
)

SEARCH_ENDPOINT_CONSUMER = "api.search"
SEARCH_ENDPOINT_SOURCE = "api.search.hybrid"


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_optional_text(value: object) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _mapping_rows(rows: Iterable[object]) -> list[MaterialQueryRow]:
    return [coerce_material_query_result_row(row) for row in rows]


def build_search_endpoint_material_query(
    *,
    query: str,
    state: str | None = None,
    project_key: str | None = None,
    limit: int,
) -> Annotated[
    MaterialQuery,
    "kit:prepared-command effect_boundary=app.services.material_queries.statement_builder "
    "witness=test:test_w04_authority_metadata",
]:
    filters: list[MaterialQueryFilterInput] = []
    state_filter = _clean_optional_text(state)
    if state_filter:
        filters.append({"field": "state", "op": "eq", "value": state_filter})

    return build_material_query(
        query,
        project_key=_clean_optional_text(project_key),
        consumer=SEARCH_ENDPOINT_CONSUMER,
        sources=("material",),
        filters=filters,
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )


def build_search_endpoint_material_query_envelope(
    *,
    query: str,
    state: str | None = None,
    modality: str = "any",
    rank: str = "hybrid",
    top_k: int,
    results: Iterable[object],
    project_key: str | None = None,
    used_backends: Iterable[str] = (),
) -> Annotated[
    MaterialQueryResultEnvelope,
    "kit:non-authoritative derived_as=view fact_source=api.search.hybrid "
    "witness=test:test_search_material_query_envelope_exposes_only_material_identity",
]:
    query_object = build_search_endpoint_material_query(
        query=query,
        state=state,
        project_key=project_key,
        limit=top_k,
    )
    envelope = build_material_query_result_envelope(
        query_object,
        _mapping_rows(results),
        source=SEARCH_ENDPOINT_SOURCE,
        result_source_type="material",
        meta={
            "contract_version": MATERIAL_QUERY_CONTRACT_VERSION,
            "endpoint": "/api/v1/search",
            "rank_mode": _clean_text(rank) or "hybrid",
            "modality": _clean_text(modality) or "any",
            "top_k": query_object.limit,
            "search_backends_used": [_clean_text(item) for item in used_backends if _clean_text(item)],
        },
    )
    validate_material_query_result_envelope(envelope)
    return envelope
