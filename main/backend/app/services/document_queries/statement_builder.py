from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import ColumnElement

from ...models.entities import Document
from .contracts import DocumentQuery, DocumentQueryFilter, DocumentQuerySort, build_document_query


DOCUMENT_QUERY_STATEMENT_BUILDER_VERSION = "document_query_statement_builder.v1"

_TEXT_SEARCH_FIELDS = ("title", "summary", "content", "uri")
_DOCUMENT_SOURCE_ALIASES = frozenset(
    {
        "document",
        "documents",
        "project.document",
        "project.documents",
        "project.structured_data",
    }
)
_FIELD_MAP = {
    "id": Document.id,
    "document_id": Document.id,
    "source_id": Document.source_id,
    "state": Document.state,
    "doc_type": Document.doc_type,
    "title": Document.title,
    "status": Document.status,
    "publish_date": Document.publish_date,
    "published_at": Document.publish_date,
    "content": Document.content,
    "summary": Document.summary,
    "uri": Document.uri,
    "url": Document.uri,
    "created_at": Document.created_at,
    "updated_at": Document.updated_at,
}
_SORT_MAP = {
    **_FIELD_MAP,
    "relevance": Document.publish_date,
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _coerce_sequence(value: Any, *, allow_string: bool = False) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if allow_string else ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return ()


def _coerce_query(value: DocumentQuery | Mapping[str, Any]) -> DocumentQuery:
    if isinstance(value, DocumentQuery):
        return value
    payload = value if isinstance(value, Mapping) else {}
    return build_document_query(
        str(payload.get("query") or ""),
        project_key=payload.get("project_key"),
        consumer=payload.get("consumer"),
        sources=_coerce_sequence(payload.get("sources"), allow_string=True),
        filters=_coerce_sequence(payload.get("filters")),
        sort=_coerce_sequence(payload.get("sort")),
        limit=int(payload.get("limit") or 20),
        offset=int(payload.get("offset") or 0),
    )


def _field_expression(field: str) -> ColumnElement[Any]:
    cleaned = _clean_text(field)
    if cleaned in _FIELD_MAP:
        return _FIELD_MAP[cleaned]
    if cleaned.startswith("extracted_data."):
        path = [part for part in cleaned.split(".")[1:] if part]
        if not path:
            raise ValueError("extracted_data filter path is required")
        expr: Any = Document.extracted_data
        for part in path:
            expr = expr[part]
        return expr.astext
    raise ValueError(f"unsupported document query field for SQL statement builder: {cleaned}")


def _sort_expression(sort: DocumentQuerySort) -> ColumnElement[Any]:
    field = _clean_text(sort.field)
    if field in _SORT_MAP:
        return _SORT_MAP[field]
    if field.startswith("extracted_data."):
        return _field_expression(field)
    raise ValueError(f"unsupported document query sort field for SQL statement builder: {field}")


def _value_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        return (value,)
    return tuple(value)


def _filter_condition(filter_: DocumentQueryFilter) -> ColumnElement[bool]:
    field = _field_expression(filter_.field)
    op = filter_.op
    value = filter_.value

    if op == "eq":
        return field == value
    if op == "in":
        return field.in_(_value_sequence(value))
    if op == "contains":
        return field.ilike(f"%{_clean_text(value)}%")
    if op == "gte":
        return field >= value
    if op == "lte":
        return field <= value
    if op == "exists":
        return field.isnot(None) if bool(value) else field.is_(None)
    raise ValueError(f"unsupported document query filter operator for SQL statement builder: {op}")


def _query_text_condition(query: DocumentQuery) -> ColumnElement[bool] | None:
    term = _clean_text(query.query)
    if not term:
        return None
    pattern = f"%{term}%"
    return or_(*(_FIELD_MAP[field].ilike(pattern) for field in _TEXT_SEARCH_FIELDS))


def _source_condition(query: DocumentQuery) -> ColumnElement[bool] | None:
    doc_types = sorted(
        {
            source
            for source in query.sources
            if source and source not in _DOCUMENT_SOURCE_ALIASES
        }
    )
    if not doc_types:
        return None
    return Document.doc_type.in_(doc_types)


def apply_document_query_to_statement(
    query: DocumentQuery | Mapping[str, Any],
    statement: Select[tuple[Document]] | None = None,
) -> Select[tuple[Document]]:
    query_object = _coerce_query(query)
    stmt = statement if statement is not None else select(Document)

    query_condition = _query_text_condition(query_object)
    if query_condition is not None:
        stmt = stmt.where(query_condition)
    source_condition = _source_condition(query_object)
    if source_condition is not None:
        stmt = stmt.where(source_condition)
    if query_object.project_key:
        stmt = stmt.where(Document.extracted_data["project_key"].astext == query_object.project_key)
    for filter_ in query_object.filters:
        stmt = stmt.where(_filter_condition(filter_))

    for sort in query_object.sort:
        sort_expr = _sort_expression(sort)
        ordered = sort_expr.asc() if sort.direction == "asc" else sort_expr.desc()
        stmt = stmt.order_by(ordered.nullslast())
    stmt = stmt.order_by(Document.id.desc()).limit(query_object.limit).offset(query_object.offset)
    return stmt


def build_document_query_statement(query: DocumentQuery | Mapping[str, Any]) -> Select[tuple[Document]]:
    return apply_document_query_to_statement(query)


def document_query_to_statement(query: DocumentQuery | Mapping[str, Any]) -> Select[tuple[Document]]:
    return build_document_query_statement(query)


def compile_document_query_statement(query: DocumentQuery | Mapping[str, Any] | Select[Any]) -> str:
    statement = query if isinstance(query, Select) else build_document_query_statement(query)
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
