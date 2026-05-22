from __future__ import annotations

from typing import Any, Iterable, Mapping

from .contracts import (
    DOCUMENT_QUERY_CONTRACT_VERSION,
    DocumentQuery,
    build_document_query,
    build_document_query_result_envelope,
    validate_document_query_result_envelope,
)


STRUCTURED_DATA_SEARCH_CONSUMER = "project.structured_data.search"
STRUCTURED_DATA_SEARCH_SOURCE = "agent_runtime.structured_data_search"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_optional_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _clean_sequence(values: Iterable[Any] | None) -> tuple[str, ...]:
    out: list[str] = []
    for value in values or ():
        cleaned = _clean_text(value)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return tuple(out)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_structured_data_search_document_query(
    *,
    project_key: str | None,
    query: str | None,
    datasets_requested: Iterable[str] = (),
    limit: int,
) -> DocumentQuery:
    datasets = _clean_sequence(datasets_requested)
    filters: list[dict[str, Any]] = []
    if datasets:
        filters.append({"field": "dataset", "op": "in", "value": list(datasets)})

    return build_document_query(
        query or "",
        project_key=_clean_optional_text(project_key),
        consumer=STRUCTURED_DATA_SEARCH_CONSUMER,
        sources=("project.structured_data",),
        filters=filters,
        sort=({"field": "relevance", "direction": "desc"},),
        limit=limit,
    )


def build_structured_data_search_document_query_envelope(
    *,
    project_key: str | None,
    query: str | None,
    datasets_requested: Iterable[str] = (),
    limit: int,
    items: Iterable[Mapping[str, Any]] = (),
    query_mode: str = "search",
    total_matches: int | None = None,
    total_stored_rows: int | None = None,
    fallback_used: bool = False,
) -> dict[str, Any]:
    query_object = build_structured_data_search_document_query(
        project_key=project_key,
        query=query,
        datasets_requested=datasets_requested,
        limit=limit,
    )
    rows = [_structured_item_to_document_query_row(item) for item in items if isinstance(item, Mapping)]
    envelope_total = len(rows) if fallback_used or total_matches is None else max(0, int(total_matches or 0))
    envelope = build_document_query_result_envelope(
        query_object,
        rows,
        source=STRUCTURED_DATA_SEARCH_SOURCE,
        result_source_type="structured_record",
        total=envelope_total,
        meta={
            "contract_version": DOCUMENT_QUERY_CONTRACT_VERSION,
            "service": STRUCTURED_DATA_SEARCH_SOURCE,
            "query_mode": _clean_text(query_mode) or "search",
            "datasets_requested": list(_clean_sequence(datasets_requested)),
            "total_matches": max(0, int(total_matches or 0)),
            "total_stored_rows": max(0, int(total_stored_rows or 0)),
            "fallback_used": bool(fallback_used),
        },
    )
    validate_document_query_result_envelope(envelope)
    return envelope


def _structured_item_to_document_query_row(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(item)
    fields = _as_mapping(raw.get("fields"))
    dataset = _clean_text(raw.get("dataset")) or "structured_data"
    record_id = _clean_text(raw.get("record_id") or raw.get("id"))
    row_id = f"{dataset}:{record_id}" if record_id else dataset
    source_uri = _clean_optional_text(
        raw.get("source_uri")
        or raw.get("uri")
        or fields.get("source_uri")
        or fields.get("uri")
        or fields.get("source_ref")
    )
    return {
        **raw,
        "id": row_id,
        "document_id": record_id if dataset == "documents" and record_id else None,
        "title": _clean_text(raw.get("title") or record_id or dataset) or "Structured record",
        "summary": _clean_text(raw.get("summary") or fields.get("summary") or fields.get("description")),
        "url": source_uri,
        "publisher": _clean_optional_text(raw.get("publisher") or fields.get("source_name") or fields.get("source")),
        "backend": dataset,
        "score": raw.get("score", 0.0),
    }
