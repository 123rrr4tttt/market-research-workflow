"""Typed administration service for authoritative Document-backed resources.

This module owns the transaction boundary that historically lived in ``api.admin``.
The ORM entities remain the facts; returned dictionaries are read-only wire projections.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Literal, Protocol, TypeGuard

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError
from sqlalchemy import and_, func, nullslast, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from typing_extensions import TypedDict

from ..models.base import SessionLocal
from ..models.entities import Document, SearchHistory, Source
from .extraction.topic_workflow import (
    TOPIC_FIELDS,
    empty_topic_structured,
    merge_topic_structured,
    topic_has_data,
)
from .graph.models import Graph, GraphEdge, GraphNode
from .graph.relation_ontology import relation_annotation
from .projects import bind_project
from .document_views import (
    get_market_data,
    get_policy_data,
    get_social_platform_label,
    get_social_sentiment,
)


JsonObject = dict[str, JsonValue]
_JSON_OBJECT_ADAPTER = TypeAdapter(JsonObject)
logger = logging.getLogger(__name__)


def parse_json_object(value: object, *, field: str) -> JsonObject:
    try:
        return _JSON_OBJECT_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError(f"{field} must be a JSON object") from exc


def optional_json_object(value: object, *, field: str) -> JsonObject | None:
    if value is None:
        return None
    return parse_json_object(value, field=field)


class _DocumentEntityRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None = None
    doc_type: str | None = None
    state: str | None = None
    status: str | None = None
    publish_date: date | datetime | None = None
    content: str | None = None
    summary: str | None = None
    uri: str | None = None
    extracted_data: JsonValue = None
    source_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class _SourceEntityRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str | None = None
    base_url: str | None = None
    enabled: bool
    created_at: datetime | None = None


class _SearchHistoryEntityRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    last_search_time: datetime | None = None


class MutableDocumentEntity(Protocol):
    id: int
    extracted_data: JsonValue


class MutableContentDocumentEntity(MutableDocumentEntity, Protocol):
    content: str | None


class AdminDocumentSnapshot(TypedDict):
    id: int
    material_id: int
    title: str | None
    doc_type: str | None
    state: str | None
    status: str | None
    publish_date: str | None
    content: str | None
    summary: str | None
    uri: str | None
    extracted_data: JsonValue
    source_id: int | None
    created_at: str | None
    updated_at: str | None


class AdminDocumentListItem(TypedDict):
    id: int
    material_id: int
    title: str | None
    doc_type: str | None
    state: str | None
    source_id: int | None
    uri: str | None
    source_kind: Literal["material"]
    readonly: Literal[False]
    created_at: str | None
    updated_at: str | None
    publish_date: str | None
    has_extracted_data: bool


class AdminDocumentPage(TypedDict):
    items: list[AdminDocumentListItem]
    total: int
    page: int
    page_size: int


class AdminExtractedDataResult(TypedDict):
    id: int
    material_id: int
    extracted_data: JsonValue


class AdminMutationError(TypedDict):
    id: int
    error: str


class AdminBulkExtractedDataResult(TypedDict):
    requested: int
    updated: int
    skipped: int
    missing: list[int]
    errors: list[AdminMutationError]
    readback: list[AdminDocumentSnapshot]  # Compatibility key: pre-mutation selection snapshot.


class AdminDeleteDocumentsResult(TypedDict):
    deleted: int
    missing: list[int]
    readback: list[AdminDocumentSnapshot]  # Compatibility key: pre-mutation selection snapshot.


class AdminReextractResult(TypedDict):
    total: int
    success: int
    error: int
    skipped: int
    fetch_missing_content: bool
    batch_size: int
    treat_empty_er_as_missing: bool
    missing: list[int]
    readback: list[AdminDocumentSnapshot]  # Compatibility key: pre-mutation selection snapshot.


TopicName = Literal["company", "product", "operation"]


class AdminTopicExtractResult(TypedDict):
    project_key: str
    total: int
    processed: int
    success: int
    skipped: int
    error: int
    topics: list[TopicName]
    topic_hits: dict[TopicName, int]
    topic_fallback_hits: dict[TopicName, int]
    topic_avg_coverage: dict[TopicName, float]
    batch_size: int
    candidate_mode: Literal["rules_then_llm"]
    fetch_missing_content: bool


class AdminStatsCount(TypedDict):
    total: int


class AdminRecentStatsCount(AdminStatsCount):
    recent_today: int


class AdminDocumentStatsCount(AdminRecentStatsCount):
    table_total: int
    topology_material_total: int


class AdminStatsResult(TypedDict):
    documents: AdminDocumentStatsCount
    social_data: AdminRecentStatsCount
    sources: AdminStatsCount
    search_history: AdminStatsCount


class AdminSourceItem(TypedDict):
    id: int
    name: str
    kind: str | None
    base_url: str | None
    enabled: bool
    document_count: int
    created_at: str | None


class AdminSourcePage(TypedDict):
    items: list[AdminSourceItem]
    total: int
    page: int
    page_size: int


class AdminSocialDataPage(TypedDict):
    items: list[JsonObject]
    total: int
    page: int
    page_size: int


class AdminSearchHistoryItem(TypedDict):
    id: int
    topic: str
    last_search_time: str | None


class AdminSearchHistoryPage(TypedDict):
    items: list[AdminSearchHistoryItem]
    total: int
    page: int
    page_size: int


class AdminGraphResult(TypedDict):
    graph_schema_version: str
    nodes: list[JsonObject]
    edges: list[JsonObject]


class AdminDocumentNotFoundError(LookupError):
    pass


class AdminDocumentInputError(ValueError):
    pass


class AdminGraphNotFoundError(LookupError):
    pass


class AdminGraphInputError(ValueError):
    pass


class AdminGraphBuildError(RuntimeError):
    @property
    def source_exception_type(self) -> str:
        source = self.__cause__
        return source.__class__.__name__ if source is not None else self.__class__.__name__


@dataclass(frozen=True)
class AdminDocumentListQuery:
    page: int
    page_size: int
    state: str | None = None
    doc_type: str | None = None
    has_extracted_data: bool | None = None
    search: str | None = None
    sort_by: Literal["created_at", "publish_date", "id"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


@dataclass(frozen=True)
class AdminSourceListQuery:
    page: int
    page_size: int
    kind: str | None = None
    enabled: bool | None = None
    sort_by: Literal["created_at", "id", "name", "document_count"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


@dataclass(frozen=True)
class AdminSocialDataListQuery:
    page: int
    page_size: int
    platform: str | None = None
    search: str | None = None
    sentiment_orientation: Literal["positive", "negative", "neutral"] | None = None
    sort_by: Literal["created_at", "publish_date", "id"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


@dataclass(frozen=True)
class AdminExtractedDataCommand:
    mode: Literal["replace", "merge"]
    extracted_data: JsonValue


@dataclass(frozen=True)
class AdminReextractCommand:
    doc_ids: list[int] | None
    force: bool
    fetch_missing_content: bool
    batch_size: int
    limit: int | None
    treat_empty_er_as_missing: bool


@dataclass(frozen=True)
class AdminTopicExtractCommand:
    project_key: str
    topics: list[TopicName]
    doc_ids: list[int] | None
    doc_types: list[str] | None
    force: bool
    fetch_missing_content: bool
    batch_size: int
    limit: int | None
    candidate_mode: Literal["rules_then_llm"]


class AdminExtractionRunner(Protocol):
    def __call__(
        self,
        *,
        title: str | None,
        content: str | None,
        extraction_plan: JsonObject | None = None,
    ) -> object: ...


class AdminHtmlFetcher(Protocol):
    def __call__(self, url: str, *, timeout: float, retries: int) -> tuple[str, object]: ...


class AdminTopicWorkflowRunner(Protocol):
    def __call__(
        self,
        *,
        extraction_app: object | None,
        text: str,
        topics: list[str],
        extracted_data: JsonObject,
        dictionaries: JsonObject,
        max_selected_chunks: int,
        fallback_max_chunks: int,
    ) -> object: ...


class AdminExtractedDataReader(Protocol):
    def __call__(self, document: object) -> object: ...


class AdminMarketGraphAugmenter(Protocol):
    def __call__(
        self,
        graph: Graph,
        documents: Iterable[object],
        topic_scope: TopicName | Literal[""] | None = None,
    ) -> None: ...


def _document_record(value: object) -> _DocumentEntityRecord:
    return _DocumentEntityRecord.model_validate(value, from_attributes=True)


def _is_mutable_document(value: object) -> TypeGuard[MutableDocumentEntity]:
    try:
        _document_record(value)
    except ValidationError:
        return False
    return hasattr(value, "extracted_data")


def _mutable_document(value: object) -> MutableDocumentEntity:
    if not _is_mutable_document(value):
        raise TypeError("document admin writer received an incompatible Document entity")
    return value


def _is_mutable_content_document(value: object) -> TypeGuard[MutableContentDocumentEntity]:
    return _is_mutable_document(value) and hasattr(value, "content")


def _mutable_content_document(value: object) -> MutableContentDocumentEntity:
    if not _is_mutable_content_document(value):
        raise TypeError("document admin writer received an entity without mutable content")
    return value


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def document_snapshot(value: object) -> AdminDocumentSnapshot:
    doc = _document_record(value)
    return {
        "id": doc.id,
        "material_id": doc.id,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "state": doc.state,
        "status": doc.status,
        "publish_date": _iso(doc.publish_date),
        "content": doc.content,
        "summary": doc.summary,
        "uri": doc.uri,
        "extracted_data": doc.extracted_data,
        "source_id": doc.source_id,
        "created_at": _iso(doc.created_at),
        "updated_at": _iso(doc.updated_at),
    }


def document_snapshots(values: Iterable[object]) -> list[AdminDocumentSnapshot]:
    return [document_snapshot(value) for value in values]


def _list_item(value: object) -> AdminDocumentListItem:
    doc = _document_record(value)
    return {
        "id": doc.id,
        "material_id": doc.id,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "state": doc.state,
        "source_id": doc.source_id,
        "uri": doc.uri,
        "source_kind": "material",
        "readonly": False,
        "created_at": _iso(doc.created_at),
        "updated_at": _iso(doc.updated_at),
        "publish_date": _iso(doc.publish_date),
        "has_extracted_data": doc.extracted_data is not None,
    }


def deep_merge_json(base: JsonValue, incoming: JsonValue) -> JsonValue:
    if isinstance(base, dict) and isinstance(incoming, dict):
        output: JsonObject = dict(base)
        for key, value in incoming.items():
            output[key] = deep_merge_json(output[key], value) if key in output else value
        return output
    return incoming


def get_admin_stats(project_key: str) -> AdminStatsResult:
    with bind_project(project_key):
        with SessionLocal() as session:
            today = datetime.now().date()
            doc_total = int(session.execute(select(func.count(Document.id))).scalar() or 0)
            doc_recent = int(
                session.execute(select(func.count(Document.id)).where(func.date(Document.created_at) == today)).scalar()
                or 0
            )
            social_total = int(
                session.execute(select(func.count(Document.id)).where(Document.doc_type == "social_sentiment")).scalar()
                or 0
            )
            social_recent = int(
                session.execute(
                    select(func.count(Document.id)).where(
                        and_(Document.doc_type == "social_sentiment", func.date(Document.created_at) == today)
                    )
                ).scalar()
                or 0
            )
            source_total = int(session.execute(select(func.count(Source.id))).scalar() or 0)
            history_total = int(session.execute(select(func.count(SearchHistory.id))).scalar() or 0)
    return {
        "documents": {
            "total": doc_total,
            "table_total": doc_total,
            "topology_material_total": 0,
            "recent_today": doc_recent,
        },
        "social_data": {"total": social_total, "recent_today": social_recent},
        "sources": {"total": source_total},
        "search_history": {"total": history_total},
    }


def list_admin_documents(project_key: str, query_spec: AdminDocumentListQuery) -> AdminDocumentPage:
    from .document_queries import consumer_predicates as document_queries

    with bind_project(project_key):
        with SessionLocal() as session:
            conditions: list[ColumnElement[bool]] = []
            if query_spec.state:
                conditions.append(Document.state == query_spec.state.upper())
            if query_spec.doc_type:
                conditions.append(Document.doc_type == query_spec.doc_type)
            if query_spec.has_extracted_data is True:
                conditions.append(document_queries.document_has_extracted_data_condition())
            elif query_spec.has_extracted_data is False:
                conditions.append(document_queries.document_missing_extracted_data_condition())
            if query_spec.search:
                search_term = f"%{query_spec.search}%"
                conditions.append(
                    or_(
                        Document.title.ilike(search_term),
                        Document.summary.ilike(search_term),
                        Document.uri.ilike(search_term),
                    )
                )

            total_stmt = select(func.count()).select_from(Document)
            document_stmt = select(Document)
            if conditions:
                predicate = and_(*conditions)
                total_stmt = total_stmt.where(predicate)
                document_stmt = document_stmt.where(predicate)
            total = int(session.execute(total_stmt).scalar() or 0)

            descending = query_spec.sort_order == "desc"
            if query_spec.sort_by == "publish_date":
                primary = Document.publish_date.desc() if descending else Document.publish_date.asc()
                secondary = Document.id.desc() if descending else Document.id.asc()
                document_stmt = document_stmt.order_by(nullslast(primary), secondary)
            elif query_spec.sort_by == "id":
                document_stmt = document_stmt.order_by(Document.id.desc() if descending else Document.id.asc())
            else:
                primary = Document.created_at.desc() if descending else Document.created_at.asc()
                secondary = Document.id.desc() if descending else Document.id.asc()
                document_stmt = document_stmt.order_by(primary, secondary)

            offset = (query_spec.page - 1) * query_spec.page_size
            rows = session.execute(document_stmt.offset(offset).limit(query_spec.page_size)).scalars().all()
            items = [_list_item(row) for row in rows]
    return {"items": items, "total": total, "page": query_spec.page, "page_size": query_spec.page_size}


def get_admin_document(doc_id: int) -> AdminDocumentSnapshot | None:
    with SessionLocal() as session:
        row = session.execute(select(Document).where(Document.id == doc_id)).scalar_one_or_none()
        return document_snapshot(row) if row is not None else None


def update_admin_document_extracted_data(
    doc_id: int,
    command: AdminExtractedDataCommand,
) -> AdminExtractedDataResult:
    with SessionLocal() as session:
        row = session.execute(select(Document).where(Document.id == doc_id)).scalar_one_or_none()
        if row is None:
            raise AdminDocumentNotFoundError(str(doc_id))
        doc = _mutable_document(row)
        if command.extracted_data is None:
            doc.extracted_data = None
        elif command.mode == "merge":
            base = doc.extracted_data or {}
            if not isinstance(base, dict) or not isinstance(command.extracted_data, dict):
                raise AdminDocumentInputError("merge 模式要求 extracted_data 为 JSON 对象(dict)")
            doc.extracted_data = deep_merge_json(base, command.extracted_data)
        else:
            doc.extracted_data = command.extracted_data
        session.commit()
        return {"id": doc.id, "material_id": doc.id, "extracted_data": doc.extracted_data}


def bulk_update_admin_document_extracted_data(
    doc_ids: list[int],
    command: AdminExtractedDataCommand,
) -> AdminBulkExtractedDataResult:
    updated = 0
    skipped = 0
    errors: list[AdminMutationError] = []
    with SessionLocal() as session:
        rows = session.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        pre_mutation_docs = document_snapshots(rows)
        found_ids = {item["id"] for item in pre_mutation_docs}
        missing = [doc_id for doc_id in doc_ids if doc_id not in found_ids]
        for row in rows:
            doc = _mutable_document(row)
            try:
                if command.extracted_data is None:
                    doc.extracted_data = None
                elif command.mode == "merge":
                    base = doc.extracted_data or {}
                    if not isinstance(base, dict) or not isinstance(command.extracted_data, dict):
                        skipped += 1
                        errors.append({"id": doc.id, "error": "merge 模式要求 extracted_data 为 JSON 对象(dict)"})
                        continue
                    doc.extracted_data = deep_merge_json(base, command.extracted_data)
                else:
                    doc.extracted_data = command.extracted_data
                updated += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                errors.append({"id": doc.id, "error": str(exc)})
        session.commit()
    return {
        "requested": len(doc_ids),
        "updated": updated,
        "skipped": skipped,
        "missing": missing,
        "errors": errors,
        "readback": pre_mutation_docs,
    }


def preview_admin_documents(doc_ids: list[int]) -> list[AdminDocumentSnapshot]:
    with SessionLocal() as session:
        rows = session.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        return document_snapshots(rows)


def delete_admin_documents(doc_ids: list[int]) -> AdminDeleteDocumentsResult:
    with SessionLocal() as session:
        rows = session.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        pre_mutation_docs = document_snapshots(rows)
        found_ids = {item["id"] for item in pre_mutation_docs}
        missing = [doc_id for doc_id in doc_ids if doc_id not in found_ids]
        for row in rows:
            session.delete(row)
        session.commit()
    return {"deleted": len(rows), "missing": missing, "readback": pre_mutation_docs}


def _reextract_plan(doc_type: str) -> JsonObject:
    normalized = doc_type.strip().lower()
    return {
        "enabled": True,
        "mode": "admin_reextract",
        "include_policy": normalized in {"policy", "policy_regulation"},
        "include_market": normalized in {"market", "market_info"},
        "include_sentiment": normalized in {"social_sentiment", "social_feed"},
        "include_company": False,
        "include_product": False,
        "include_operation": False,
    }


def _has_entities_relations(extracted_data: JsonObject) -> bool:
    raw_entities_relations = extracted_data.get("entities_relations")
    if not isinstance(raw_entities_relations, dict):
        return False
    entities = raw_entities_relations.get("entities")
    relations = raw_entities_relations.get("relations")
    return bool(entities or relations)


def _select_reextract_rows(session: Session, command: AdminReextractCommand) -> list[Document]:
    conditions: list[ColumnElement[bool]] = []
    if command.doc_ids:
        conditions.append(Document.id.in_(command.doc_ids))
    if not command.fetch_missing_content:
        conditions.append(Document.content.isnot(None))
    stmt = select(Document)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    if command.limit:
        stmt = stmt.limit(command.limit)
    rows = list(session.execute(stmt).scalars().all())
    if command.force:
        return rows
    filtered: list[Document] = []
    for row in rows:
        snapshot = document_snapshot(row)
        raw_extracted = snapshot["extracted_data"]
        extracted = raw_extracted if isinstance(raw_extracted, dict) else {}
        if not extracted or (command.treat_empty_er_as_missing and not _has_entities_relations(extracted)):
            filtered.append(row)
    return filtered


def preview_admin_reextract(command: AdminReextractCommand) -> list[AdminDocumentSnapshot]:
    with SessionLocal() as session:
        return document_snapshots(_select_reextract_rows(session, command))


def reextract_admin_documents(
    command: AdminReextractCommand,
    *,
    extraction_runner: AdminExtractionRunner,
    fetch_html: AdminHtmlFetcher,
    extract_text_from_html: Callable[[str], str],
) -> AdminReextractResult:
    success_count = 0
    error_count = 0
    skipped_count = 0
    with SessionLocal() as session:
        rows = _select_reextract_rows(session, command)
        pre_mutation_docs = document_snapshots(rows)
        selected_ids = {snapshot["id"] for snapshot in pre_mutation_docs}
        pending = 0
        for row in rows:
            doc = _mutable_content_document(row)
            record = _document_record(row)
            try:
                content_text = (record.content or "").strip()
                if not content_text and command.fetch_missing_content:
                    uri = (record.uri or "").strip()
                    if uri:
                        try:
                            html, _response = fetch_html(uri, timeout=12.0, retries=1)
                            fetched = extract_text_from_html(html).strip()
                            if fetched:
                                doc.content = fetched
                                content_text = fetched
                        except Exception as fetch_error:  # noqa: BLE001
                            logger.warning(
                                "re_extract fetch_content failed doc_id=%s url=%s err=%s",
                                record.id,
                                record.uri,
                                fetch_error,
                            )
                title_text = (record.title or "").strip()
                summary_text = (record.summary or "").strip()
                text_for_extract = "\n\n".join(
                    part for part in (title_text, summary_text, content_text) if part
                )
                outcome_value = extraction_runner(
                    title=title_text,
                    content=text_for_extract,
                    extraction_plan=_reextract_plan(record.doc_type or ""),
                )
                try:
                    outcome = parse_json_object(outcome_value, field="frontdoor_extraction_result")
                except ValueError:
                    skipped_count += 1
                    continue
                domains_value = outcome.get("domains")
                if not isinstance(domains_value, dict) or not domains_value:
                    skipped_count += 1
                    continue
                domains = parse_json_object(domains_value, field="frontdoor_extraction_result.domains")
                existing = record.extracted_data if isinstance(record.extracted_data, dict) else {}
                merged_value = deep_merge_json(existing, domains)
                if not isinstance(merged_value, dict):
                    raise TypeError("merged extracted data must be a JSON object")
                merged = merged_value
                merged["structured_extraction_status"] = str(outcome.get("status") or "failed")
                reason = outcome.get("reason")
                error = outcome.get("error")
                if reason:
                    merged["structured_extraction_reason"] = str(reason)
                else:
                    merged.pop("structured_extraction_reason", None)
                if error:
                    merged["structured_extraction_error"] = str(error)
                else:
                    merged.pop("structured_extraction_error", None)
                summary_value = outcome.get("summary")
                if isinstance(summary_value, dict):
                    merged["_structured_summary"] = parse_json_object(
                        summary_value,
                        field="frontdoor_extraction_result.summary",
                    )
                doc.extracted_data = merged
                success_count += 1
                pending += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("re_extract failed doc_id=%s err=%s", record.id, exc)
                error_count += 1
            if pending >= command.batch_size:
                session.commit()
                pending = 0
        session.commit()
    requested = command.doc_ids or list(selected_ids)
    missing = [doc_id for doc_id in requested if doc_id not in selected_ids]
    return {
        "total": len(pre_mutation_docs),
        "success": success_count,
        "error": error_count,
        "skipped": skipped_count,
        "fetch_missing_content": command.fetch_missing_content,
        "batch_size": command.batch_size,
        "treat_empty_er_as_missing": command.treat_empty_er_as_missing,
        "missing": missing,
        "readback": pre_mutation_docs,
    }


_TOPIC_FIELDS_ADAPTER = TypeAdapter(dict[TopicName, str])
_TOPIC_FIELDS = _TOPIC_FIELDS_ADAPTER.validate_python(TOPIC_FIELDS, strict=True)
_DEFAULT_TOPIC_DOC_TYPES = [
    "market",
    "market_info",
    "policy",
    "policy_regulation",
    "social_sentiment",
    "social_feed",
    "news",
    "raw_note",
]


def _json_object_or_empty(value: JsonValue) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _json_object_items(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_items(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _topic_has_data(value: JsonValue) -> bool:
    return topic_has_data(value)


def _empty_topic_structured() -> JsonObject:
    value: object = empty_topic_structured()
    return parse_json_object(value, field="empty_topic_structured")


def _merge_topic_structured(existing: JsonValue, incoming: JsonValue) -> JsonObject:
    base = _json_object_or_empty(existing)
    nxt = _json_object_or_empty(incoming)
    value: object = merge_topic_structured(base, nxt)
    return parse_json_object(value, field="merged_topic_structured")


def _topic_rule_score(
    topic: TopicName,
    text: str,
    extracted_data: JsonObject,
    dictionaries: JsonObject,
) -> int:
    lowered_text = text.lower()
    score = 0
    predicates = [value.lower() for value in _string_items(dictionaries.get("predicates"))]
    modifiers = [value.lower() for value in _string_items(dictionaries.get("modifiers"))]
    topic_nouns = [value.lower() for value in _string_items(dictionaries.get(f"{topic}_nouns"))]
    components = [value.lower() for value in _string_items(dictionaries.get("components"))]
    if any(token in lowered_text for token in predicates):
        score += 1
    if any(token in lowered_text for token in modifiers):
        score += 1
    if any(token in lowered_text for token in topic_nouns):
        score += 2
    if topic == "product" and any(token in lowered_text for token in components):
        score += 1
    if topic == "operation" and (
        isinstance(extracted_data.get("market"), dict)
        or isinstance(extracted_data.get("sentiment"), dict)
    ):
        score += 1
    entities_relations = _json_object_or_empty(extracted_data.get("entities_relations"))
    if topic == "company" and any(
        str(entity.get("type") or "").upper() == "ORG"
        for entity in _json_object_items(entities_relations.get("entities"))
    ):
        score += 2
    if topic == "product":
        keywords = [value.lower() for value in _string_items(extracted_data.get("keywords"))]
        if topic_nouns and any(any(noun in keyword for noun in topic_nouns[:50]) for keyword in keywords):
            score += 1
        market = _json_object_or_empty(extracted_data.get("market"))
        if any(str(market.get(key) or "").strip() for key in ("product", "segment", "category", "game")):
            score += 2
        if any(
            token in lowered_text
            for token in ("robot", "机器人", "sku", "型号", "产品", "component", "传感器", "电机")
        ):
            score += 1
    if topic == "operation":
        market = _json_object_or_empty(extracted_data.get("market"))
        if any(str(market.get(key) or "").strip() for key in ("platform", "channel", "price", "revenue")):
            score += 1
    return score


def _select_topic_rows(session: Session, command: AdminTopicExtractCommand) -> list[Document]:
    if command.doc_ids:
        stmt = select(Document).where(Document.id.in_(command.doc_ids))
    else:
        stmt = select(Document).where(Document.doc_type.in_(command.doc_types or _DEFAULT_TOPIC_DOC_TYPES))
    if command.limit:
        stmt = stmt.limit(command.limit)
    rows = list(session.execute(stmt).scalars().all())
    if command.force:
        return rows
    selected: list[Document] = []
    for row in rows:
        extracted = _json_object_or_empty(_document_record(row).extracted_data)
        if any(not _topic_has_data(extracted.get(_TOPIC_FIELDS[topic])) for topic in command.topics):
            selected.append(row)
    return selected


def topic_extract_admin_documents(
    command: AdminTopicExtractCommand,
    *,
    dictionaries: JsonObject,
    workflow_runner: AdminTopicWorkflowRunner,
    fetch_html: AdminHtmlFetcher,
    extract_text_from_html: Callable[[str], str],
) -> AdminTopicExtractResult:
    processed = 0
    success_count = 0
    skipped_count = 0
    error_count = 0
    topic_hits: dict[TopicName, int] = {topic: 0 for topic in command.topics}
    topic_fallback_hits: dict[TopicName, int] = {topic: 0 for topic in command.topics}
    topic_coverages: dict[TopicName, list[float]] = {topic: [] for topic in command.topics}
    with bind_project(command.project_key):
        with SessionLocal() as session:
            rows = _select_topic_rows(session, command)
            total = len(rows)
            pending = 0
            for row in rows:
                processed += 1
                doc = _mutable_content_document(row)
                record = _document_record(row)
                try:
                    content_text = (record.content or "").strip()
                    if not content_text and command.fetch_missing_content:
                        uri = (record.uri or "").strip()
                        if uri:
                            try:
                                html, _response = fetch_html(uri, timeout=12.0, retries=1)
                                fetched = extract_text_from_html(html).strip()
                                if fetched:
                                    doc.content = fetched
                                    content_text = fetched
                            except Exception as fetch_error:  # noqa: BLE001
                                logger.warning(
                                    "topic_extract fetch_content failed doc_id=%s err=%s",
                                    record.id,
                                    fetch_error,
                                )
                    text_for_extract = "\n\n".join(
                        part
                        for part in ((record.title or "").strip(), (record.summary or "").strip(), content_text)
                        if part
                    ).strip()
                    if len(text_for_extract) < 20:
                        skipped_count += 1
                        continue

                    extracted = _json_object_or_empty(record.extracted_data)
                    wrote_any = False
                    selected_topics: list[TopicName] = []
                    for topic in command.topics:
                        if _topic_rule_score(topic, text_for_extract, extracted, dictionaries) <= 0 and not command.force:
                            field = _TOPIC_FIELDS[topic]
                            extracted[field] = _merge_topic_structured(
                                extracted.get(field),
                                _empty_topic_structured(),
                            )
                            continue
                        selected_topics.append(topic)

                    workflow_diagnostics: JsonObject = {}
                    if selected_topics:
                        workflow_value = workflow_runner(
                            extraction_app=None,
                            text=text_for_extract,
                            topics=list(selected_topics),
                            extracted_data=extracted,
                            dictionaries=dictionaries,
                            max_selected_chunks=6,
                            fallback_max_chunks=8,
                        )
                        workflow = parse_json_object(workflow_value, field="topic_workflow_result")
                        topic_results = _json_object_or_empty(workflow.get("results"))
                        workflow_diagnostics = _json_object_or_empty(workflow.get("diagnostics"))
                        diagnostic_topics = _json_object_or_empty(workflow_diagnostics.get("topics"))
                        for topic in selected_topics:
                            field = _TOPIC_FIELDS[topic]
                            incoming = topic_results.get(topic)
                            extracted[field] = _merge_topic_structured(
                                extracted.get(field),
                                incoming if isinstance(incoming, dict) else _empty_topic_structured(),
                            )
                            if _topic_has_data(extracted[field]):
                                topic_hits[topic] += 1
                                wrote_any = True
                            topic_diagnostics = diagnostic_topics.get(topic)
                            if isinstance(topic_diagnostics, dict):
                                coverage = topic_diagnostics.get("coverage_ratio")
                                if isinstance(coverage, (int, float)):
                                    topic_coverages[topic].append(float(coverage))
                                if bool(topic_diagnostics.get("fallback_used")):
                                    topic_fallback_hits[topic] += 1

                    extracted["_topic_extract_workflow"] = {
                        "version": 1,
                        "candidate_mode": command.candidate_mode,
                        "doc_topics_selected": list(selected_topics),
                        "diagnostics": workflow_diagnostics,
                    }
                    doc.extracted_data = extracted
                    success_count += 1 if wrote_any else 0
                    if not wrote_any:
                        skipped_count += 1
                    pending += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("topic_extract failed doc_id=%s err=%s", record.id, exc)
                    error_count += 1
                if pending >= command.batch_size:
                    session.commit()
                    pending = 0
            session.commit()
    topic_avg_coverage: dict[TopicName, float] = {
        topic: round(sum(values) / len(values), 4) if values else 0.0
        for topic, values in topic_coverages.items()
    }
    return {
        "project_key": command.project_key,
        "total": total,
        "processed": processed,
        "success": success_count,
        "skipped": skipped_count,
        "error": error_count,
        "topics": list(command.topics),
        "topic_hits": topic_hits,
        "topic_fallback_hits": topic_fallback_hits,
        "topic_avg_coverage": topic_avg_coverage,
        "batch_size": command.batch_size,
        "candidate_mode": command.candidate_mode,
        "fetch_missing_content": command.fetch_missing_content,
    }


def augment_market_graph_with_topic_structured(
    graph: Graph,
    documents: Iterable[object],
    *,
    extracted_data_reader: AdminExtractedDataReader,
    topic_scope: TopicName | Literal[""] | None = None,
) -> None:
    def topic_entity_node_type(topic_field: str, entity_type: str) -> str:
        mappings: dict[str, dict[str, str]] = {
            "company_structured": {
                "company": "CompanyEntity",
                "brand": "CompanyBrand",
                "business_unit": "CompanyUnit",
                "partner": "CompanyPartner",
                "channel": "CompanyChannel",
            },
            "product_structured": {
                "product": "ProductEntity",
                "model": "ProductModel",
                "category": "ProductCategory",
                "brand": "ProductBrand",
                "component": "ProductComponent",
                "scenario": "ProductScenario",
            },
            "operation_structured": {
                "operation_subject": "OperationEntity",
                "platform": "OperationPlatform",
                "store": "OperationStore",
                "channel": "OperationChannel",
                "metric": "OperationMetric",
                "strategy": "OperationStrategy",
                "region": "OperationRegion",
                "period": "OperationPeriod",
            },
        }
        defaults = {
            "company_structured": "CompanyEntity",
            "product_structured": "ProductEntity",
            "operation_structured": "OperationEntity",
        }
        return mappings.get(topic_field, {}).get(entity_type, defaults.get(topic_field, "Entity"))

    def relation_type_for_topic(topic_field: str) -> str:
        return {
            "company_structured": "HAS_COMPANY_ENTITY",
            "product_structured": "HAS_PRODUCT_ENTITY",
            "operation_structured": "HAS_OPERATION_ENTITY",
        }.get(topic_field, "HAS_TOPIC_ENTITY")

    def topic_group(topic_field: str) -> str:
        return {
            "company_structured": "company",
            "product_structured": "product",
            "operation_structured": "operation",
        }.get(topic_field, "generic")

    def normalize_entity_text(text: str) -> str:
        return " ".join(text.strip().lower().split())

    def ensure_node(node_type: str, node_id: str, properties: JsonObject) -> GraphNode:
        key = f"{node_type}:{node_id}"
        current = graph.nodes.get(key)
        if current is None:
            current = GraphNode(type=node_type, id=node_id, properties=properties)
            graph.nodes[key] = current
            return current
        current_properties_value: object = current.properties
        current_properties = parse_json_object(current_properties_value, field="graph_node.properties")
        for property_name, property_value in properties.items():
            if property_name not in current_properties or current_properties.get(property_name) in (None, "", []):
                current_properties[property_name] = property_value
        current.properties = current_properties
        return current

    def edge_key(
        edge_type: str,
        from_node: GraphNode,
        to_node: GraphNode,
        properties: JsonObject | None,
    ) -> tuple[str, str, str, str, str, str]:
        predicate = str((properties or {}).get("predicate") or "").strip().lower()
        return edge_type, from_node.type, from_node.id, to_node.type, to_node.id, predicate

    edge_keys: set[tuple[str, str, str, str, str, str]] = set()
    for edge in graph.edges:
        edge_properties_value: object = edge.properties
        edge_properties = parse_json_object(edge_properties_value, field="graph_edge.properties")
        edge_keys.add(edge_key(edge.type, edge.from_node, edge.to_node, edge_properties))

    def append_edge_once(
        edge_type: str,
        from_node: GraphNode,
        to_node: GraphNode,
        properties: JsonObject | None = None,
    ) -> None:
        key = edge_key(edge_type, from_node, to_node, properties)
        if key in edge_keys:
            return
        edge_keys.add(key)
        graph.edges.append(
            GraphEdge(type=edge_type, from_node=from_node, to_node=to_node, properties=properties or {})
        )

    scope_to_field = {
        "company": "company_structured",
        "product": "product_structured",
        "operation": "operation_structured",
    }
    normalized_scope = str(topic_scope or "").strip().lower()
    only_field = scope_to_field.get(normalized_scope)
    topic_fields = (
        [only_field]
        if only_field is not None
        else ["company_structured", "product_structured", "operation_structured"]
    )

    for document in documents:
        record = _document_record(document)
        market_node = graph.nodes.get(f"MarketData:{record.id}")
        if market_node is None:
            continue
        market_backbone: GraphNode = market_node
        extracted_value = extracted_data_reader(document)
        extracted = parse_json_object(extracted_value, field="document.extracted_data")
        entity_registry: dict[tuple[str, str], tuple[str, str]] = {}

        def ensure_unified_topic_entity(
            topic_field: str,
            text: str,
            entity_type: str | None,
        ) -> GraphNode | None:
            normalized_text = normalize_entity_text(text)
            if not normalized_text:
                return None
            group = topic_group(topic_field)
            registry_key = (group, normalized_text)
            registered = entity_registry.get(registry_key)
            normalized_type = str(entity_type or "").strip().lower()
            properties: JsonObject = {
                "text": text.strip(),
                "entity_group": group,
                "entity_type": normalized_type or None,
            }
            if registered is not None:
                node_type, node_id = registered
                return ensure_node(node_type, node_id, properties)
            node_type = topic_entity_node_type(topic_field, normalized_type)
            node_id = f"{group}:{normalized_text}"
            entity_registry[registry_key] = (node_type, node_id)
            return ensure_node(node_type, node_id, properties)

        def attach_market_topic_entity(topic_field: str, node: GraphNode | None) -> None:
            if node is not None:
                append_edge_once(relation_type_for_topic(topic_field), market_backbone, node, {"weight": 1.0})

        for field in topic_fields:
            topic_data = _json_object_or_empty(extracted.get(field))
            if not topic_data:
                continue
            for topic in _string_items(topic_data.get("topics")):
                topic_node = ensure_node("TopicTag", topic.lower(), {"label": topic})
                append_edge_once("HAS_TOPIC_TAG", market_backbone, topic_node, {})
            for entity in _json_object_items(topic_data.get("entities")):
                text = str(entity.get("text") or "").strip()
                if not text:
                    continue
                node = ensure_unified_topic_entity(field, text, str(entity.get("type") or ""))
                attach_market_topic_entity(field, node)
            for relation in _json_object_items(topic_data.get("relations")):
                subject = str(relation.get("subject") or "").strip()
                target = str(relation.get("object") or "").strip()
                predicate = str(relation.get("predicate") or "").strip()
                if not subject or not target:
                    continue
                subject_node = ensure_unified_topic_entity(
                    field,
                    subject,
                    str(relation.get("subject_type") or ""),
                )
                target_node = ensure_unified_topic_entity(
                    field,
                    target,
                    str(relation.get("object_type") or ""),
                )
                attach_market_topic_entity(field, subject_node)
                attach_market_topic_entity(field, target_node)
                if subject_node is not None and target_node is not None:
                    annotation = relation_annotation(predicate)
                    append_edge_once(
                        "TOPIC_RELATION",
                        subject_node,
                        target_node,
                        {
                            "predicate": annotation["predicate_norm"],
                            "predicate_raw": annotation["predicate_raw"],
                            "relation_class": annotation["relation_class"],
                        },
                    )

    if normalized_scope in ("company", "product", "operation"):
        scope_prefix = {
            "company": "Company",
            "product": "Product",
            "operation": "Operation",
        }[normalized_scope]
        seed_keys = [key for key, node in graph.nodes.items() if node.type.startswith(scope_prefix)]
        if seed_keys:
            adjacency: dict[str, set[str]] = {}
            for edge in graph.edges:
                from_key = f"{edge.from_node.type}:{edge.from_node.id}"
                to_key = f"{edge.to_node.type}:{edge.to_node.id}"
                adjacency.setdefault(from_key, set()).add(to_key)
                adjacency.setdefault(to_key, set()).add(from_key)
            keep_keys: set[str] = set()
            queue = list(seed_keys)
            while queue:
                current = queue.pop(0)
                if current in keep_keys:
                    continue
                keep_keys.add(current)
                queue.extend(next_key for next_key in adjacency.get(current, set()) if next_key not in keep_keys)
            graph.nodes = {key: node for key, node in graph.nodes.items() if key in keep_keys}
            graph.edges = [
                edge
                for edge in graph.edges
                if f"{edge.from_node.type}:{edge.from_node.id}" in keep_keys
                and f"{edge.to_node.type}:{edge.to_node.id}" in keep_keys
            ]


def _rollback_graph_session(session: Session, *, context: str) -> None:
    try:
        session.rollback()
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s rollback_failed err=%s", context, exc)


def _export_graph(graph: Graph) -> AdminGraphResult:
    from .graph.exporter import export_to_json

    exported: object = export_to_json(graph)
    parsed = parse_json_object(exported, field="admin_graph")
    graph_schema_version = parsed.get("graph_schema_version")
    nodes = parsed.get("nodes")
    edges = parsed.get("edges")
    if not isinstance(graph_schema_version, str) or not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("admin_graph must contain graph_schema_version, nodes, and edges")
    return {
        "graph_schema_version": graph_schema_version,
        "nodes": [parse_json_object(node, field="admin_graph.nodes[]") for node in nodes],
        "edges": [parse_json_object(edge, field="admin_graph.edges[]") for edge in edges],
    }


def _finalize_admin_graph(
    graph: Graph,
    *,
    graph_kind: Literal["social", "market", "policy"],
    project_key: str,
    session: Session,
    documents: list[Document] | None = None,
    market_deep_view: bool = False,
    topic_scope: TopicName | None = None,
    market_graph_augmenter: AdminMarketGraphAugmenter | None = None,
) -> AdminGraphResult:
    from .graph.compat import compare_graphs
    from .graph.doc_types import resolve_graph_node_combo, resolve_graph_topic_scope_entities
    from .graph.persistence import GraphNodeReader, GraphNodeWriter
    from .graph.projection import project_graph_by_node_types
    from ..settings.config import settings

    canary_raw = str(getattr(settings, "graph_node_projection_canary_projects", "") or "")
    canary_projects = {value.strip() for value in canary_raw.split(",") if value.strip()}
    read_mode = str(getattr(settings, "graph_node_projection_read_mode", "a_only") or "a_only").strip().lower()
    write_mode = str(getattr(settings, "graph_node_projection_write_mode", "shadow") or "shadow").strip().lower()
    use_b_read = read_mode == "b_primary" or (read_mode == "b_canary" and project_key in canary_projects)

    if graph_kind == "market" and market_deep_view and market_graph_augmenter is not None:
        try:
            market_graph_augmenter(
                graph,
                documents or [],
                topic_scope,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("扩展专题图谱节点失败: %s", exc)

    combo = list(resolve_graph_node_combo(graph_kind, project_key))
    if graph_kind == "market" and market_deep_view:
        deep_types: list[str] = ["TopicTag"]
        scoped_entities = resolve_graph_topic_scope_entities(project_key)
        if topic_scope:
            deep_types.extend(scoped_entities.get(topic_scope, []))
        else:
            for scope in ("company", "product", "operation"):
                deep_types.extend(scoped_entities.get(scope, []))
        seen: set[str] = set()
        merged_combo: list[str] = []
        for node_type in [*combo, *deep_types]:
            key = str(node_type or "").strip()
            if key and key not in seen:
                seen.add(key)
                merged_combo.append(key)
        combo = merged_combo

    primary_graph = project_graph_by_node_types(graph, combo)
    finalized_graph = primary_graph
    if write_mode in {"shadow", "on"}:
        try:
            summary = GraphNodeWriter(
                session,
                schema_version=str(primary_graph.schema_version or "v1"),
            ).persist_graph_nodes(primary_graph)
            session.commit()
            logger.info(
                "graph_b_write project=%s kind=%s mode=%s attempted=%s written=%s aliases=%s edges=%s skipped=%s",
                project_key,
                graph_kind,
                write_mode,
                summary.attempted,
                summary.inserted_or_updated,
                summary.aliases_written,
                summary.edges_written,
                summary.skipped,
            )
        except Exception as exc:  # noqa: BLE001
            _rollback_graph_session(session, context="graph_b_write")
            logger.warning(
                "graph_b_write_failed project=%s kind=%s mode=%s err=%s",
                project_key,
                graph_kind,
                write_mode,
                exc,
            )

    if use_b_read:
        try:
            persisted_graph = GraphNodeReader(session).load_graph(limit=10000)
            if persisted_graph.nodes:
                persisted_graph = project_graph_by_node_types(persisted_graph, combo)
                diff = compare_graphs(primary_graph, persisted_graph)
                logger.info(
                    "graph_b_read_enabled project=%s kind=%s node_count_diff=%s edge_count_diff=%s type_overlap=%.4f",
                    project_key,
                    graph_kind,
                    diff.node_count_diff,
                    diff.edge_count_diff,
                    diff.node_type_overlap_ratio,
                )
                finalized_graph = persisted_graph
        except Exception as exc:  # noqa: BLE001
            _rollback_graph_session(session, context="graph_b_read")
            logger.warning("graph_b_read_fallback_to_a project=%s kind=%s err=%s", project_key, graph_kind, exc)
    return _export_graph(finalized_graph)


def export_admin_graph(doc_ids: list[int]) -> AdminGraphResult:
    from .graph.adapters import normalize_document
    from .graph.builder import build_graph
    from .graph.models import NormalizedSocialPost

    with SessionLocal() as session:
        rows = list(
            session.execute(
                select(Document).where(
                    and_(Document.doc_type == "social_sentiment", Document.id.in_(doc_ids))
                )
            ).scalars().all()
        )
        if not rows:
            raise AdminGraphNotFoundError("未找到指定的文档")
        posts: list[NormalizedSocialPost] = []
        for row in rows:
            normalized = normalize_document(row)
            if normalized is not None:
                posts.append(normalized)
        if not posts:
            raise AdminGraphInputError("无法规范化文档数据")
        return _export_graph(build_graph(posts))


def get_admin_content_graph(
    project_key: str,
    *,
    start_date: date | None,
    end_date: date | None,
    platform: str | None,
    topic: str | None,
    limit: int,
) -> AdminGraphResult:
    from .document_queries import consumer_predicates as document_queries
    from .graph.adapters import normalize_document
    from .graph.builder import build_graph, build_topic_subgraph
    from .graph.models import NormalizedSocialPost

    with bind_project(project_key):
        with SessionLocal() as session:
            conditions: list[ColumnElement[bool]] = [document_queries.content_graph_structured_condition()]
            if start_date is not None:
                conditions.append(document_queries.document_publish_or_created_on_or_after_condition(start_date))
            if end_date is not None:
                conditions.append(document_queries.document_publish_or_created_on_or_before_condition(end_date))
            rows = list(
                session.execute(select(Document).where(and_(*conditions)).limit(limit)).scalars().all()
            )
            logger.info("查询到 %s 条文档", len(rows))
            posts: list[NormalizedSocialPost] = []
            skipped_count = 0
            for row in rows:
                if platform:
                    platform_value = get_social_platform_label(row, default="")
                    if str(platform_value or "").lower() != platform.lower():
                        skipped_count += 1
                        continue
                if topic:
                    sentiment_value = get_social_sentiment(row)
                    sentiment = parse_json_object(sentiment_value, field="document.social_sentiment")
                    if topic.lower() not in str(sentiment.get("topic") or "").lower():
                        skipped_count += 1
                        continue
                try:
                    normalized = normalize_document(row)
                    if normalized is None:
                        skipped_count += 1
                    else:
                        posts.append(normalized)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("规范化文档 %s 失败: %s", _document_record(row).id, exc)
                    skipped_count += 1
            logger.info("规范化成功: %s, 跳过: %s", len(posts), skipped_count)
            if not posts:
                return _export_graph(Graph())
            try:
                graph = build_graph(posts)
            except Exception as exc:  # noqa: BLE001
                raise AdminGraphBuildError("构建内容图谱失败") from exc
            if topic:
                try:
                    graph = build_topic_subgraph(graph, topic)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("构建主题子图失败: %s", exc)
                    return _export_graph(Graph())
            return _finalize_admin_graph(
                graph,
                graph_kind="social",
                project_key=project_key,
                session=session,
            )


def get_admin_market_graph(
    project_key: str,
    *,
    start_date: date | None,
    end_date: date | None,
    state: str | None,
    game: str | None,
    deep_view: bool,
    topic_scope: TopicName | None,
    limit: int,
    market_graph_augmenter: AdminMarketGraphAugmenter,
) -> AdminGraphResult:
    from .document_queries import consumer_predicates as document_queries
    from .graph.adapters.market import MarketAdapter
    from .graph.builder import build_market_graph
    from .graph.models import NormalizedMarketData

    with bind_project(project_key):
        with SessionLocal() as session:
            conditions: list[ColumnElement[bool]] = [
                document_queries.market_graph_structured_condition(
                    deep_view=deep_view,
                    topic_scope=topic_scope,
                )
            ]
            if state:
                conditions.append(document_queries.market_state_condition(state))
            if game:
                conditions.append(document_queries.market_game_condition(game))
            if start_date is not None:
                conditions.append(
                    document_queries.market_publish_created_or_report_on_or_after_condition(start_date)
                )
            if end_date is not None:
                conditions.append(
                    document_queries.market_publish_created_or_report_on_or_before_condition(end_date)
                )
            stmt = (
                select(Document)
                .where(and_(*conditions))
                .order_by(Document.publish_date.desc().nullslast(), Document.created_at.desc())
                .limit(limit)
            )
            rows = list(session.execute(stmt).scalars().all())
            logger.info("查询到 %s 条市场文档", len(rows))
            adapter = MarketAdapter()
            normalized_rows: list[NormalizedMarketData] = []
            skipped_count = 0
            for row in rows:
                if game:
                    market_value = get_market_data(row)
                    market = parse_json_object(market_value, field="document.market")
                    if game.lower() not in str(market.get("game") or "").lower():
                        skipped_count += 1
                        continue
                try:
                    normalized = adapter.to_normalized(row)
                    if normalized is None:
                        skipped_count += 1
                    else:
                        normalized_rows.append(normalized)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("规范化文档 %s 失败: %s", _document_record(row).id, exc)
                    skipped_count += 1
            logger.info("规范化成功: %s, 跳过: %s", len(normalized_rows), skipped_count)
            if not normalized_rows:
                return _export_graph(Graph())
            try:
                graph = build_market_graph(normalized_rows)
            except Exception as exc:  # noqa: BLE001
                raise AdminGraphBuildError("构建市场图谱失败") from exc
            return _finalize_admin_graph(
                graph,
                graph_kind="market",
                project_key=project_key,
                session=session,
                documents=rows,
                market_deep_view=deep_view,
                topic_scope=topic_scope,
                market_graph_augmenter=market_graph_augmenter,
            )


def _record_dates(record: _DocumentEntityRecord, policy_data: JsonObject) -> list[date]:
    dates: list[date] = []
    if record.publish_date is not None:
        dates.append(record.publish_date.date() if isinstance(record.publish_date, datetime) else record.publish_date)
    if record.created_at is not None:
        dates.append(record.created_at.date())
    effective = policy_data.get("effective_date")
    if isinstance(effective, str) and effective:
        try:
            dates.append(datetime.fromisoformat(effective.replace("Z", "+00:00")).date())
        except ValueError:
            logger.warning("解析日期失败 field=effective_date value=%s", effective)
    return dates


def get_admin_policy_graph(
    project_key: str,
    *,
    start_date: date | None,
    end_date: date | None,
    state: str | None,
    policy_type: str | None,
    limit: int,
) -> AdminGraphResult:
    from .document_queries import consumer_predicates as document_queries
    from .graph.adapters.policy import PolicyAdapter
    from .graph.builder import build_policy_graph
    from .graph.models import NormalizedPolicyData

    with bind_project(project_key):
        with SessionLocal() as session:
            conditions: list[ColumnElement[bool]] = [document_queries.policy_graph_has_data_condition()]
            if state:
                conditions.append(document_queries.policy_graph_state_condition(state))
            if policy_type:
                conditions.append(document_queries.policy_graph_type_ilike_condition(policy_type))
            stmt = (
                select(Document)
                .where(and_(*conditions))
                .order_by(Document.publish_date.desc().nullslast(), Document.created_at.desc())
                .limit(min(limit * 3, 6000))
            )
            rows = list(session.execute(stmt).scalars().all())
            logger.info("查询到 %s 条政策文档", len(rows))
            adapter = PolicyAdapter()
            normalized_rows: list[NormalizedPolicyData] = []
            skipped_count = 0
            for row in rows:
                record = _document_record(row)
                policy_value = get_policy_data(row)
                policy_data = parse_json_object(policy_value, field="document.policy")
                candidate_dates = _record_dates(record, policy_data)
                if start_date is not None and not any(value >= start_date for value in candidate_dates):
                    skipped_count += 1
                    continue
                if end_date is not None and not any(value <= end_date for value in candidate_dates):
                    skipped_count += 1
                    continue
                try:
                    normalized = adapter.to_normalized(row)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("规范化政策文档 %s 失败: %s", record.id, exc)
                    skipped_count += 1
                    continue
                if normalized is None:
                    skipped_count += 1
                    continue
                if policy_type and normalized.policy_type and policy_type.lower() not in normalized.policy_type.lower():
                    skipped_count += 1
                    continue
                normalized_rows.append(normalized)
                if len(normalized_rows) >= limit:
                    break
            logger.info("规范化成功 %s 条，跳过 %s 条", len(normalized_rows), skipped_count)
            if not normalized_rows:
                return _export_graph(Graph())
            try:
                graph = build_policy_graph(normalized_rows)
            except Exception as exc:  # noqa: BLE001
                raise AdminGraphBuildError("构建政策图谱失败") from exc
            return _finalize_admin_graph(
                graph,
                graph_kind="policy",
                project_key=project_key,
                session=session,
            )


def list_admin_sources(query_spec: AdminSourceListQuery) -> AdminSourcePage:
    with SessionLocal() as session:
        conditions: list[ColumnElement[bool]] = []
        if query_spec.kind:
            conditions.append(Source.kind == query_spec.kind)
        if query_spec.enabled is not None:
            conditions.append(Source.enabled == query_spec.enabled)
        source_stmt = select(Source)
        total_stmt = select(func.count()).select_from(Source)
        if conditions:
            predicate = and_(*conditions)
            source_stmt = source_stmt.where(predicate)
            total_stmt = total_stmt.where(predicate)
        total = int(session.execute(total_stmt).scalar() or 0)
        descending = query_spec.sort_order == "desc"
        if query_spec.sort_by == "id":
            source_stmt = source_stmt.order_by(Source.id.desc() if descending else Source.id.asc())
        elif query_spec.sort_by == "name":
            source_stmt = source_stmt.order_by(Source.name.desc() if descending else Source.name.asc())
        else:
            source_stmt = source_stmt.order_by(Source.created_at.desc() if descending else Source.created_at.asc())

        rows = session.execute(source_stmt).scalars().all()
        records = [_SourceEntityRecord.model_validate(row, from_attributes=True) for row in rows]
        counts: dict[int, int] = {}
        for record in records:
            counts[record.id] = int(
                session.execute(select(func.count(Document.id)).where(Document.source_id == record.id)).scalar() or 0
            )
        if query_spec.sort_by == "document_count":
            records.sort(key=lambda source: counts.get(source.id, 0), reverse=descending)
        offset = (query_spec.page - 1) * query_spec.page_size
        selected = records[offset : offset + query_spec.page_size]
        items: list[AdminSourceItem] = [
            {
                "id": source.id,
                "name": source.name,
                "kind": source.kind,
                "base_url": source.base_url,
                "enabled": source.enabled,
                "document_count": counts.get(source.id, 0),
                "created_at": _iso(source.created_at),
            }
            for source in selected
        ]
    return {"items": items, "total": total, "page": query_spec.page, "page_size": query_spec.page_size}


def list_admin_social_data(
    query_spec: AdminSocialDataListQuery,
    *,
    projector: Callable[[object], object],
) -> AdminSocialDataPage:
    from .document_queries import consumer_predicates as document_queries

    with SessionLocal() as session:
        conditions: list[ColumnElement[bool]] = [Document.doc_type == "social_sentiment"]
        if query_spec.platform:
            conditions.append(document_queries.social_platform_condition(query_spec.platform))
        if query_spec.sentiment_orientation:
            conditions.append(
                document_queries.social_sentiment_orientation_condition(query_spec.sentiment_orientation)
            )
        if query_spec.search:
            search_term = f"%{query_spec.search}%"
            conditions.append(
                or_(
                    Document.title.ilike(search_term),
                    Document.summary.ilike(search_term),
                    Document.content.ilike(search_term),
                    Document.uri.ilike(search_term),
                )
            )
        predicate = and_(*conditions)
        total = int(session.execute(select(func.count()).select_from(Document).where(predicate)).scalar() or 0)
        document_stmt = select(Document).where(predicate)
        descending = query_spec.sort_order == "desc"
        if query_spec.sort_by == "publish_date":
            primary = Document.publish_date.desc() if descending else Document.publish_date.asc()
            secondary = Document.id.desc() if descending else Document.id.asc()
            document_stmt = document_stmt.order_by(nullslast(primary), secondary)
        elif query_spec.sort_by == "id":
            document_stmt = document_stmt.order_by(Document.id.desc() if descending else Document.id.asc())
        else:
            primary = Document.created_at.desc() if descending else Document.created_at.asc()
            secondary = Document.id.desc() if descending else Document.id.asc()
            document_stmt = document_stmt.order_by(primary, secondary)
        offset = (query_spec.page - 1) * query_spec.page_size
        rows = session.execute(document_stmt.offset(offset).limit(query_spec.page_size)).scalars().all()
        items = [parse_json_object(projector(row), field="social_data_item") for row in rows]
    return {"items": items, "total": total, "page": query_spec.page, "page_size": query_spec.page_size}


def list_admin_search_history(project_key: str, *, page: int, page_size: int) -> AdminSearchHistoryPage:
    with bind_project(project_key):
        with SessionLocal() as session:
            total = int(session.execute(select(func.count()).select_from(SearchHistory)).scalar() or 0)
            stmt = (
                select(SearchHistory)
                .order_by(SearchHistory.last_search_time.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = session.execute(stmt).scalars().all()
            records = [_SearchHistoryEntityRecord.model_validate(row, from_attributes=True) for row in rows]
            items: list[AdminSearchHistoryItem] = [
                {"id": record.id, "topic": record.topic, "last_search_time": _iso(record.last_search_time)}
                for record in records
            ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


__all__ = [
    "AdminBulkExtractedDataResult",
    "AdminDeleteDocumentsResult",
    "AdminDocumentInputError",
    "AdminDocumentPage",
    "AdminDocumentListQuery",
    "AdminDocumentNotFoundError",
    "AdminDocumentSnapshot",
    "AdminExtractedDataCommand",
    "AdminExtractedDataResult",
    "AdminGraphBuildError",
    "AdminGraphResult",
    "AdminGraphInputError",
    "AdminGraphNotFoundError",
    "AdminReextractCommand",
    "AdminReextractResult",
    "AdminSearchHistoryPage",
    "AdminSocialDataPage",
    "AdminSocialDataListQuery",
    "AdminSourceListQuery",
    "AdminSourcePage",
    "AdminStatsResult",
    "AdminTopicExtractCommand",
    "AdminTopicExtractResult",
    "JsonObject",
    "TopicName",
    "augment_market_graph_with_topic_structured",
    "bulk_update_admin_document_extracted_data",
    "deep_merge_json",
    "delete_admin_documents",
    "document_snapshot",
    "document_snapshots",
    "export_admin_graph",
    "get_admin_content_graph",
    "get_admin_document",
    "get_admin_market_graph",
    "get_admin_policy_graph",
    "get_admin_stats",
    "list_admin_documents",
    "list_admin_search_history",
    "list_admin_social_data",
    "list_admin_sources",
    "optional_json_object",
    "parse_json_object",
    "preview_admin_documents",
    "preview_admin_reextract",
    "reextract_admin_documents",
    "topic_extract_admin_documents",
    "update_admin_document_extracted_data",
]
