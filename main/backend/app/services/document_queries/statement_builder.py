from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Annotated, TypeGuard

from functorial_kit import Failure

from sqlalchemy import SQLColumnExpression, Select, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import ColumnElement

from ...models.entities import Material
from .contracts import (
    MaterialQuery,
    MaterialQueryFilter,
    MaterialQueryFilterInput,
    MaterialQueryInput,
    MaterialQueryJsonValue,
    MaterialQuerySort,
    MaterialQuerySortInput,
    material_query_failure,
    raise_material_query_legacy,
    try_build_material_query,
)


MATERIAL_QUERY_STATEMENT_BUILDER_VERSION = "material_query_statement_builder.v1"

_TEXT_SEARCH_FIELDS = ("title", "summary", "content", "uri")
_MATERIAL_SOURCE_ALIASES = frozenset(
    {
        "material",
        "materials",
        "project.material",
        "project.materials",
        "project.structured_data",
    }
)
_FIELD_MAP = {
    "id": Material.id,
    "material_id": Material.id,
    "source_id": Material.source_id,
    "state": Material.state,
    "material_type": Material.material_type,
    "title": Material.title,
    "status": Material.status,
    "publish_date": Material.publish_date,
    "published_at": Material.publish_date,
    "content": Material.content,
    "summary": Material.summary,
    "uri": Material.uri,
    "url": Material.uri,
    "created_at": Material.created_at,
    "updated_at": Material.updated_at,
}
_SORT_MAP = {
    **_FIELD_MAP,
    "relevance": Material.publish_date,
}

FieldExpression = (
    SQLColumnExpression[int]
    | SQLColumnExpression[int | None]
    | SQLColumnExpression[str]
    | SQLColumnExpression[str | None]
    | SQLColumnExpression[date | None]
    | SQLColumnExpression[datetime | None]
    | SQLColumnExpression[dict[str, object] | None]
    | ColumnElement[object]
)


def _is_str_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if _is_str_object_mapping(value) else {}


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _coerce_query(value: MaterialQueryInput) -> MaterialQuery | Failure:
    if isinstance(value, MaterialQuery):
        return value
    payload = _as_mapping(value)
    limit_value = payload.get("limit")
    offset_value = payload.get("offset")
    project_key = payload.get("project_key")
    consumer = payload.get("consumer")
    sources = _coerce_source_sequence(payload.get("sources"))
    filters = _coerce_filter_sequence(payload.get("filters"))
    sort = _coerce_sort_sequence(payload.get("sort"))
    if isinstance(sources, Failure):
        return sources
    if isinstance(filters, Failure):
        return filters
    if isinstance(sort, Failure):
        return sort
    if not isinstance(limit_value, (str, int)) or not isinstance(offset_value, (str, int)):
        return material_query_failure("statement_invalid", "material query pagination must be integers", owner="material_queries.statement_builder.query")
    try:
        limit = int(limit_value)
        offset = int(offset_value)
    except (TypeError, ValueError):
        return material_query_failure("statement_invalid", "material query pagination must be integers", owner="material_queries.statement_builder.query")
    if project_key is not None and not isinstance(project_key, str):
        return material_query_failure("statement_invalid", "material query project_key must be a string", owner="material_queries.statement_builder.query")
    if consumer is not None and not isinstance(consumer, str):
        return material_query_failure("statement_invalid", "material query consumer must be a string", owner="material_queries.statement_builder.query")
    return try_build_material_query(
        str(payload.get("query") or ""),
        project_key=project_key,
        consumer=consumer,
        sources=sources,
        filters=filters,
        sort=sort,
        limit=limit,
        offset=offset,
    )


def _coerce_source_sequence(value: object) -> tuple[str, ...] | Failure:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not _is_object_sequence(value):
        return material_query_failure("statement_invalid", "material query sources must be a sequence", owner="material_queries.statement_builder.query.sources")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return material_query_failure("statement_invalid", "material query source must be a string", owner="material_queries.statement_builder.query.sources")
        output.append(item)
    return tuple(output)


def _coerce_filter_sequence(value: object) -> tuple[MaterialQueryFilterInput, ...] | Failure:
    if value is None:
        return ()
    if _is_str_object_mapping(value):
        return (value,)
    if not _is_object_sequence(value):
        return material_query_failure("statement_invalid", "material query filters must be a sequence", owner="material_queries.statement_builder.query.filters")
    output: list[MaterialQueryFilterInput] = []
    for item in value:
        if isinstance(item, MaterialQueryFilter) or _is_str_object_mapping(item):
            output.append(item)
        else:
            return material_query_failure("statement_invalid", "material query filter must be an object", owner="material_queries.statement_builder.query.filters")
    return tuple(output)


def _coerce_sort_sequence(value: object) -> tuple[MaterialQuerySortInput, ...] | Failure:
    if value is None:
        return ()
    if _is_str_object_mapping(value):
        return (value,)
    if not _is_object_sequence(value):
        return material_query_failure("statement_invalid", "material query sort must be a sequence", owner="material_queries.statement_builder.query.sort")
    output: list[MaterialQuerySortInput] = []
    for item in value:
        if isinstance(item, MaterialQuerySort) or _is_str_object_mapping(item):
            output.append(item)
        else:
            return material_query_failure("statement_invalid", "material query sort must be an object", owner="material_queries.statement_builder.query.sort")
    return tuple(output)


def _field_expression(field: str) -> FieldExpression | Failure:
    cleaned = _clean_text(field)
    if cleaned in _FIELD_MAP:
        return _FIELD_MAP[cleaned]
    if cleaned.startswith("extracted_data."):
        path = [part for part in cleaned.split(".")[1:] if part]
        if not path:
            return material_query_failure("statement_invalid", "extracted_data filter path is required", owner="material_queries.statement_builder.field")
        expr: FieldExpression = Material.extracted_data
        for part in path:
            expr = expr[part]
        return expr.astext
    return material_query_failure("statement_invalid", f"unsupported material query field for SQL statement builder: {cleaned}", owner="material_queries.statement_builder.field")


def _sort_expression(sort: MaterialQuerySort) -> FieldExpression | Failure:
    field = _clean_text(sort.field)
    if field in _SORT_MAP:
        return _SORT_MAP[field]
    if field.startswith("extracted_data."):
        return _field_expression(field)
    return material_query_failure("sort_invalid", f"unsupported material query sort field for SQL statement builder: {field}", owner="material_queries.statement_builder.sort")


def _value_sequence(value: MaterialQueryJsonValue) -> tuple[MaterialQueryJsonValue, ...]:
    if isinstance(value, str) or not isinstance(value, list):
        return (value,)
    return tuple(value)


def _filter_condition(filter_: MaterialQueryFilter) -> ColumnElement[bool] | Failure:
    field = _field_expression(filter_.field)
    if isinstance(field, Failure):
        return field
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
    return material_query_failure("filter_invalid", f"unsupported material query filter operator for SQL statement builder: {op}", owner="material_queries.statement_builder.filter")


def _query_text_condition(query: MaterialQuery) -> ColumnElement[bool] | None:
    term = _clean_text(query.query)
    if not term:
        return None
    pattern = f"%{term}%"
    return or_(*(_FIELD_MAP[field].ilike(pattern) for field in _TEXT_SEARCH_FIELDS))


def _source_condition(query: MaterialQuery) -> ColumnElement[bool] | None:
    material_types = sorted(
        {
            source
            for source in query.sources
            if source and source not in _MATERIAL_SOURCE_ALIASES
        }
    )
    if not material_types:
        return None
    return Material.material_type.in_(material_types)


def apply_material_query_to_statement(
    query: MaterialQueryInput,
    statement: Select[tuple[Material]] | None = None,
) -> Select[tuple[Material]]:
    result = try_apply_material_query_to_statement(query, statement)
    if isinstance(result, Failure):
        raise_material_query_legacy(result)
    return result


def try_apply_material_query_to_statement(
    query: MaterialQueryInput,
    statement: Select[tuple[Material]] | None = None,
) -> Select[tuple[Material]] | Failure:
    query_object = _coerce_query(query)
    if isinstance(query_object, Failure):
        return query_object
    stmt = statement if statement is not None else select(Material)

    query_condition = _query_text_condition(query_object)
    if query_condition is not None:
        stmt = stmt.where(query_condition)
    source_condition = _source_condition(query_object)
    if source_condition is not None:
        stmt = stmt.where(source_condition)
    if query_object.project_key:
        stmt = stmt.where(Material.extracted_data["project_key"].astext == query_object.project_key)
    for filter_ in query_object.filters:
        condition = _filter_condition(filter_)
        if isinstance(condition, Failure):
            return condition
        stmt = stmt.where(condition)

    for sort in query_object.sort:
        sort_expr = _sort_expression(sort)
        if isinstance(sort_expr, Failure):
            return sort_expr
        ordered = sort_expr.asc() if sort.direction == "asc" else sort_expr.desc()
        stmt = stmt.order_by(ordered.nullslast())
    stmt = stmt.order_by(Material.id.desc()).limit(query_object.limit).offset(query_object.offset)
    return stmt


def build_material_query_statement(
    query: MaterialQueryInput,
) -> Annotated[
    Select[tuple[Material]],
    "kit:prepared-command effect_boundary=material_query_statement "
    "witness=test:test_service_results_declare_sources_and_effect_authority",
]:
    return apply_material_query_to_statement(query)


def try_build_material_query_statement(query: MaterialQueryInput) -> Select[tuple[Material]] | Failure:
    return try_apply_material_query_to_statement(query)


def material_query_to_statement(query: MaterialQueryInput) -> Select[tuple[Material]]:
    return build_material_query_statement(query)


def compile_material_query_statement(query: MaterialQueryInput | Select[tuple[Material]]) -> str:
    statement = query if isinstance(query, Select) else build_material_query_statement(query)
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
