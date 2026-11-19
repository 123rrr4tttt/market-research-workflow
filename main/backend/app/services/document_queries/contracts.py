from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Annotated, Iterable, Literal, Mapping, NoReturn, NotRequired, TypeAlias, TypeGuard, TypedDict, Union

from functorial_kit import Failure
from mrw_functorial_kit.core.service_failure_semantics import material_query_failures
from ...contracts.materials import normalize_material_source_type


MATERIAL_QUERY_CONTRACT_VERSION = "material_queries.v2"
SUPPORTED_MATERIAL_QUERY_CONTRACT_VERSIONS = {MATERIAL_QUERY_CONTRACT_VERSION}

FILTER_OPERATORS = frozenset({"eq", "in", "contains", "gte", "lte", "exists"})
SORT_DIRECTIONS = frozenset({"asc", "desc"})
DEFAULT_QUERY_LIMIT = 20
MAX_QUERY_LIMIT = 100


MaterialQueryJsonAtom = str | int | float | bool | None
MaterialQueryJsonArray = list["MaterialQueryJsonValue"]
MaterialQueryJsonValue: TypeAlias = Union[
    MaterialQueryJsonAtom,
    MaterialQueryJsonArray,
    "MaterialQueryJsonObject",
]  # noqa: UP007
MaterialQueryJsonObject = dict[str, "MaterialQueryJsonValue"]
MaterialQueryRow = MaterialQueryJsonObject


class MaterialQueryFilterPayload(TypedDict):
    field: str
    op: str
    value: MaterialQueryJsonValue


class MaterialQuerySortPayload(TypedDict):
    field: str
    direction: str


class MaterialQueryPayload(TypedDict):
    contract_version: str
    query: str
    normalized_query: str
    project_key: str | None
    consumer: str | None
    sources: list[str]
    filters: list[MaterialQueryFilterPayload]
    sort: list[MaterialQuerySortPayload]
    limit: int
    offset: int
    query_id: NotRequired[str]


class MaterialQueryPaginationPayload(TypedDict):
    limit: int
    offset: int
    result_count: int
    total: int


class MaterialQueryResultData(TypedDict):
    contract_version: str
    query: MaterialQueryPayload
    results: list[MaterialQueryRow]
    pagination: MaterialQueryPaginationPayload


class MaterialQueryResultEnvelope(TypedDict):
    status: Literal["ok"]
    data: MaterialQueryResultData
    error: None
    meta: MaterialQueryJsonObject


MaterialQueryFilterInput: TypeAlias = "MaterialQueryFilter | Mapping[str, object]"
MaterialQuerySortInput: TypeAlias = "MaterialQuerySort | Mapping[str, object]"

def material_query_failure(
    code: str,
    message: str,
    *,
    owner: str,
    public_exception: type[Exception] | str = ValueError,
    public_message: str | None = None,
    **details: object,
) -> Failure:
    return material_query_failures.fail(
        code,
        message,
        {
            "owner": owner,
            "public_exception": public_exception.__name__ if isinstance(public_exception, type) else str(public_exception),
            "public_message": str(public_message if public_message is not None else message),
            **details,
        },
    )


def raise_material_query_legacy(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    context = failure.context or {}
    if (
        not material_query_failures.matches(failure)
        or "public_exception" not in context
        or "public_message" not in context
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=material_queries.contracts.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_material_query_failure_lift_covers_programmer_defect_and_cause
        raise TypeError("material query failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if cause is None:
        # kit:boundary owner=material_queries.contracts.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=material_query.failure witness=test:test_material_query_failure_lift_covers_programmer_defect_and_cause
        raise exception_type(message)
    # kit:boundary owner=material_queries.contracts.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=material_query.failure witness=test:test_material_query_failure_lift_covers_programmer_defect_and_cause
    raise exception_type(message) from cause


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_optional_text(value: object) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _is_str_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if _is_str_object_mapping(value) else {}


def _lookup(row: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _try_json_value(value: object) -> MaterialQueryJsonValue | Failure:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _is_object_sequence(value):
        values: MaterialQueryJsonArray = []
        for item in value:
            converted = _try_json_value(item)
            if isinstance(converted, Failure):
                return converted
            values.append(converted)
        return values
    if _is_str_object_mapping(value):
        return _try_json_object(value)
    return material_query_failure(
        "filter_invalid",
        "material query JSON value must be str, int, float, bool, null, array, or object",
        owner="material_queries.contracts.json",
    )


def _try_json_object(value: object) -> MaterialQueryJsonObject | Failure:
    if not _is_str_object_mapping(value):
        return material_query_failure(
            "result_row_invalid",
            "material query JSON object is required",
            owner="material_queries.contracts.json",
        )
    output: MaterialQueryJsonObject = {}
    for key, item in value.items():
        if type(key) is not str:
            return material_query_failure(
                "result_row_invalid",
                "material query JSON object keys must be strings",
                owner="material_queries.contracts.json",
            )
        converted = _try_json_value(item)
        if isinstance(converted, Failure):
            return converted
        output[key] = converted
    return output


def _json_object(value: object) -> MaterialQueryJsonObject:
    result = _try_json_object(value)
    if isinstance(result, Failure):
        raise_material_query_legacy(result)
    return result


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if isinstance(value, (str, int, float)):
            return float(value)
    except (TypeError, ValueError):
        pass
    return default


def _coerce_int(value: object, default: int) -> int:
    try:
        if isinstance(value, (str, int)):
            return int(value)
    except (TypeError, ValueError):
        pass
    return default


def _normalize_material_source_type(value: object) -> str:
    return normalize_material_source_type(value)


def _reject_legacy_material_fields(row: MaterialQueryJsonObject) -> None:
    legacy_fields = ("document_id", "doc_id", "doc_type", "document_title", "source_doc_id")
    present = [field for field in legacy_fields if field in row]
    if present:
        raise_material_query_legacy(
            material_query_failure(
                "result_row_invalid",
                f"material query result uses legacy document fields: {', '.join(present)}",
                owner="material_queries.contracts.result_row",
            )
        )


def _json_lookup(row: MaterialQueryJsonObject, *keys: str) -> MaterialQueryJsonValue:
    result = _try_json_value(_lookup(row, *keys))
    if isinstance(result, Failure):
        raise_material_query_legacy(result)
    return result


@dataclass(frozen=True)
class MaterialQueryFilter:
    field: str
    op: str = "eq"
    value: MaterialQueryJsonValue = None

    def __post_init__(self) -> None:
        field = _clean_text(self.field)
        op = _clean_text(self.op).lower() or "eq"
        if not field:
            raise_material_query_legacy(material_query_failure("filter_invalid", "material query filter field is required", owner="material_queries.contracts.filter"))
        if op not in FILTER_OPERATORS:
            message = f"unsupported material query filter operator: {op}"
            raise_material_query_legacy(material_query_failure("filter_invalid", message, owner="material_queries.contracts.filter"))
        value = _try_json_value(self.value)
        if isinstance(value, Failure):
            raise_material_query_legacy(value)
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "value", value)

    def to_dict(self) -> MaterialQueryFilterPayload:
        return {"field": self.field, "op": self.op, "value": self.value}


@dataclass(frozen=True)
class MaterialQuerySort:
    field: str = "relevance"
    direction: str = "desc"

    def __post_init__(self) -> None:
        field = _clean_text(self.field) or "relevance"
        direction = _clean_text(self.direction).lower() or "desc"
        if direction not in SORT_DIRECTIONS:
            message = f"unsupported material query sort direction: {direction}"
            raise_material_query_legacy(material_query_failure("sort_invalid", message, owner="material_queries.contracts.sort"))
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "direction", direction)

    def to_dict(self) -> MaterialQuerySortPayload:
        return {"field": self.field, "direction": self.direction}


@dataclass(frozen=True)
class MaterialQuery:
    query: str
    project_key: str | None = None
    consumer: str | None = None
    sources: tuple[str, ...] = ()
    filters: tuple[MaterialQueryFilter, ...] = ()
    sort: tuple[MaterialQuerySort, ...] = field(default_factory=lambda: (MaterialQuerySort(),))
    limit: int = DEFAULT_QUERY_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _clean_text(self.query))
        object.__setattr__(self, "project_key", _clean_optional_text(self.project_key))
        object.__setattr__(self, "consumer", _clean_optional_text(self.consumer))
        object.__setattr__(self, "sources", tuple(dict.fromkeys(normalize_material_source_type(item) for item in self.sources if _clean_text(item))))
        object.__setattr__(self, "filters", tuple(coerce_material_query_filter(item) for item in self.filters))
        sort = tuple(coerce_material_query_sort(item) for item in self.sort)
        object.__setattr__(self, "sort", sort or (MaterialQuerySort(),))
        limit = max(1, min(_coerce_int(self.limit, DEFAULT_QUERY_LIMIT), MAX_QUERY_LIMIT))
        offset = max(0, _coerce_int(self.offset, 0))
        object.__setattr__(self, "limit", limit)
        object.__setattr__(self, "offset", offset)

    @property
    def normalized_query(self) -> str:
        return self.query.lower()

    @property
    def query_id(self) -> str:
        payload = json.dumps(self.to_dict(include_query_id=False), ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(
            payload.encode("utf-8", errors="ignore"),
            usedforsecurity=False,
        ).hexdigest()[:16]

    def to_dict(self, *, include_query_id: bool = True) -> MaterialQueryPayload:
        payload: MaterialQueryPayload = {
            "contract_version": MATERIAL_QUERY_CONTRACT_VERSION,
            "query": self.query,
            "normalized_query": self.normalized_query,
            "project_key": self.project_key,
            "consumer": self.consumer,
            "sources": list(self.sources),
            "filters": [item.to_dict() for item in self.filters],
            "sort": [item.to_dict() for item in self.sort],
            "limit": self.limit,
            "offset": self.offset,
        }
        if include_query_id:
            payload["query_id"] = self.query_id
        return payload


MaterialQueryInput: TypeAlias = MaterialQuery | Mapping[str, object]


def coerce_material_query_filter(value: MaterialQueryFilterInput) -> MaterialQueryFilter:
    if isinstance(value, MaterialQueryFilter):
        return value
    payload = _as_mapping(value)
    converted_value = _try_json_value(payload.get("value"))
    if isinstance(converted_value, Failure):
        raise_material_query_legacy(converted_value)
    return MaterialQueryFilter(
        field=str(payload.get("field") or ""),
        op=str(payload.get("op") or "eq"),
        value=converted_value,
    )


def coerce_material_query_sort(value: MaterialQuerySortInput) -> MaterialQuerySort:
    if isinstance(value, MaterialQuerySort):
        return value
    payload = _as_mapping(value)
    return MaterialQuerySort(
        field=str(payload.get("field") or "relevance"),
        direction=str(payload.get("direction") or "desc"),
    )


def build_material_query(
    query: str,
    *,
    project_key: str | None = None,
    consumer: str | None = None,
    sources: Iterable[str] = (),
    filters: Iterable[MaterialQueryFilterInput] = (),
    sort: Iterable[MaterialQuerySortInput] = (),
    limit: int = DEFAULT_QUERY_LIMIT,
    offset: int = 0,
) -> Annotated[
    MaterialQuery,
    "kit:prepared-command effect_boundary=app.services.material_queries.statement_builder "
    "witness=test:test_query_object_normalizes_filter_sort_and_bounds",
]:
    result = try_build_material_query(
        query,
        project_key=project_key,
        consumer=consumer,
        sources=sources,
        filters=filters,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    if isinstance(result, Failure):
        raise_material_query_legacy(result)
    return result


def try_build_material_query(
    query: str,
    *,
    project_key: str | None = None,
    consumer: str | None = None,
    sources: Iterable[str] = (),
    filters: Iterable[MaterialQueryFilterInput] = (),
    sort: Iterable[MaterialQuerySortInput] = (),
    limit: int = DEFAULT_QUERY_LIMIT,
    offset: int = 0,
) -> MaterialQuery | Failure:
    filter_values = tuple(filters)
    sort_values = tuple(sort) or (MaterialQuerySort(),)
    for item in filter_values:
        payload = item.to_dict() if isinstance(item, MaterialQueryFilter) else _as_mapping(item)
        field = _clean_text(payload.get("field"))
        op = _clean_text(payload.get("op")).lower() or "eq"
        if not field:
            return material_query_failure("filter_invalid", "material query filter field is required", owner="material_queries.contracts.filter")
        if op not in FILTER_OPERATORS:
            return material_query_failure("filter_invalid", f"unsupported material query filter operator: {op}", owner="material_queries.contracts.filter")
        value = _try_json_value(payload.get("value"))
        if isinstance(value, Failure):
            return value
    for item in sort_values:
        payload = item.to_dict() if isinstance(item, MaterialQuerySort) else _as_mapping(item)
        direction = _clean_text(payload.get("direction")).lower() or "desc"
        if direction not in SORT_DIRECTIONS:
            return material_query_failure("sort_invalid", f"unsupported material query sort direction: {direction}", owner="material_queries.contracts.sort")
    try:
        filter_objects = tuple(coerce_material_query_filter(item) for item in filter_values)
        sort_objects = tuple(coerce_material_query_sort(item) for item in sort_values)
        return MaterialQuery(
            query=query,
            project_key=project_key,
            consumer=consumer,
            sources=tuple(sources),
            filters=filter_objects,
            sort=sort_objects,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        return material_query_failure("filter_invalid", str(exc), owner="material_queries.contracts.query")


def build_material_query_result_item(
    row: Mapping[str, object],
    *,
    source_type: str,
    rank: int,
) -> Annotated[
    MaterialQueryRow,
    "kit:non-authoritative derived_as=view "
    "fact_source=repository_row+source_type+rank "
    "witness=test:test_service_results_declare_sources_and_effect_authority",
]:
    raw = _json_object(row)
    _reject_legacy_material_fields(raw)
    title = _clean_text(_json_lookup(raw, "title", "name")) or "Material"
    snippet = _clean_text(_json_lookup(raw, "snippet", "summary", "description", "content", "evidence"))
    url = _clean_optional_text(_json_lookup(raw, "url", "uri", "source_uri"))
    publisher = _clean_optional_text(_json_lookup(raw, "publisher", "source", "channel_key"))
    published_at = _clean_optional_text(_json_lookup(raw, "published_at", "publish_date", "date"))
    material_id = _json_lookup(raw, "material_id")
    backend = _clean_optional_text(_json_lookup(raw, "backend", "provider", "source_type"))
    normalized_source_type = _normalize_material_source_type(source_type) or "material"
    canonical_raw = {key: value for key, value in raw.items() if key != "id"}
    return {
        **canonical_raw,
        "material_id": material_id,
        "title": title,
        "snippet": snippet,
        "summary": snippet,
        "url": url,
        "uri": url,
        "score": _coerce_float(_json_lookup(raw, "score", "_score", "rank_score"), default=0.0),
        "source_type": normalized_source_type,
        "publisher": publisher,
        "published_at": published_at,
        "backend": backend,
        "rank": max(1, int(rank)),
        "raw": canonical_raw,
    }


def coerce_material_query_result_row(value: object) -> MaterialQueryRow:
    return _json_object(value)


def build_material_query_result_envelope(
    query: MaterialQuery,
    rows: Iterable[Mapping[str, object]],
    *,
    source: str,
    result_source_type: str = "material",
    total: int | None = None,
    meta: Mapping[str, object] | None = None,
) -> Annotated[
    MaterialQueryResultEnvelope,
    "kit:non-authoritative derived_as=view "
    "fact_source=material_query+rows+source+meta "
    "witness=test:test_service_results_declare_sources_and_effect_authority",
]:
    results = [
        build_material_query_result_item(row, source_type=result_source_type, rank=index)
        for index, row in enumerate(rows, start=1)
    ]
    result_count = len(results)
    total_count = total if total is not None else result_count
    merged_meta: MaterialQueryJsonObject = {
        "contract_version": MATERIAL_QUERY_CONTRACT_VERSION,
        "query_id": query.query_id,
        "consumer": query.consumer,
        "source": _clean_text(source),
        "result_count": result_count,
    }
    merged_meta.update(_json_object(meta or {}))
    envelope: MaterialQueryResultEnvelope = {
        "status": "ok",
        "data": {
            "contract_version": MATERIAL_QUERY_CONTRACT_VERSION,
            "query": query.to_dict(),
            "results": results,
            "pagination": {
                "limit": query.limit,
                "offset": query.offset,
                "result_count": result_count,
                "total": total_count,
            },
        },
        "error": None,
        "meta": merged_meta,
    }
    return envelope


def try_validate_material_query_result_envelope(envelope: Mapping[str, object]) -> None | Failure:
    converted_envelope = _try_json_object(envelope)
    if isinstance(converted_envelope, Failure):
        return converted_envelope
    if envelope.get("status") != "ok":
        return material_query_failure("result_envelope_invalid", "material query result envelope status must be ok", owner="material_queries.contracts.result_envelope")
    data = converted_envelope.get("data")
    if not _is_str_object_mapping(data):
        return material_query_failure("result_envelope_invalid", "material query result envelope data must be an object", owner="material_queries.contracts.result_envelope")
    if data.get("contract_version") not in SUPPORTED_MATERIAL_QUERY_CONTRACT_VERSIONS:
        return material_query_failure("result_envelope_invalid", "unsupported material query result envelope contract_version", owner="material_queries.contracts.result_envelope")
    query = data.get("query")
    if not _is_str_object_mapping(query) or query.get("contract_version") not in SUPPORTED_MATERIAL_QUERY_CONTRACT_VERSIONS:
        return material_query_failure("result_envelope_invalid", "material query result envelope query contract is missing", owner="material_queries.contracts.result_envelope")
    results = data.get("results")
    if not _is_object_list(results):
        return material_query_failure("result_envelope_invalid", "material query result envelope results must be a list", owner="material_queries.contracts.result_envelope")
    for item in results:
        if not _is_str_object_mapping(item):
            return material_query_failure("result_envelope_invalid", "material query result item must be an object", owner="material_queries.contracts.result_envelope")
        raw = item.get("raw")
        raw_mapping: Mapping[str, object] = raw if _is_str_object_mapping(raw) else {}
        identity_aliases = [
            field
            for field in ("id", "document_id", "doc_id", "source_doc_id")
            if field in item or field in raw_mapping
        ]
        if identity_aliases:
            return material_query_failure(
                "result_envelope_invalid",
                f"material query result item uses identity aliases: {', '.join(identity_aliases)}",
                owner="material_queries.contracts.result_envelope",
            )
        for key in ("title", "snippet", "source_type", "rank"):
            if key not in item:
                return material_query_failure("result_envelope_invalid", f"material query result item missing key: {key}", owner="material_queries.contracts.result_envelope")


def validate_material_query_result_envelope(envelope: Mapping[str, object]) -> None:
    result = try_validate_material_query_result_envelope(envelope)
    if isinstance(result, Failure):
        raise_material_query_legacy(result)


def rows_for_material_views(envelope: Mapping[str, object]) -> list[MaterialQueryRow]:
    validate_material_query_result_envelope(envelope)
    envelope_object = _json_object(envelope)
    data_value = envelope_object.get("data")
    if not _is_str_object_mapping(data_value):
        raise_material_query_legacy(
            material_query_failure(
                "result_envelope_invalid",
                "validated material query envelope data must be an object",
                owner="material_queries.contracts.rows_for_material_views",
                public_exception=TypeError,
            ),
            TypeError,
        )
    data = _json_object(data_value)
    results_value = data.get("results")
    if not isinstance(results_value, list):
        raise_material_query_legacy(
            material_query_failure(
                "result_envelope_invalid",
                "validated material query envelope results must be a list",
                owner="material_queries.contracts.rows_for_material_views",
                public_exception=TypeError,
            ),
            TypeError,
        )
    output: list[MaterialQueryRow] = []
    for item in results_value:
        row = _json_object(item)
        output.append(
            {
                **row,
                "source_type": _normalize_material_source_type(_json_lookup(row, "source_type")),
                "material_id": _json_lookup(row, "material_id"),
            }
        )
    return output
