from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from importlib import import_module
import logging
import os
from typing import Protocol, TypeAlias, TypeGuard, Union, runtime_checkable

import numpy as np
from elasticsearch import Elasticsearch
from sqlalchemy import Float, select
from sqlalchemy.sql.elements import ColumnElement

from ...models.base import SessionLocal
from ...models.entities import Material, Embedding
from ..llm.provider import get_embeddings
from ..projects import bind_project, current_project_key
from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import search_failures
from .es_client import get_es_client

logger = logging.getLogger(__name__)


SearchJsonAtom = str | int | float | bool | None
SearchJsonArray = list["SearchJsonValue"]
SearchJsonObject = dict[str, "SearchJsonValue"]
SearchJsonValue: TypeAlias = Union[
    SearchJsonAtom,
    SearchJsonArray,
    "SearchJsonObject",
]  # noqa: UP007
SearchRow = SearchJsonObject


@runtime_checkable
class _KeywordFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QdrantSearchClient(Protocol):
    def search(
        self,
        *,
        collection_name: str,
        query_vector: Sequence[float],
        query_filter: object,
        limit: int,
    ) -> object: ...


@runtime_checkable
class _QdrantPoint(Protocol):
    @property
    def payload(self) -> object: ...

    @property
    def score(self) -> object: ...


@runtime_checkable
class _EmbeddingRecord(Protocol):
    @property
    def object_id(self) -> object: ...

    @property
    def object_type(self) -> object: ...

    @property
    def vector(self) -> object: ...

    @property
    def dim(self) -> object: ...

    @property
    def provider(self) -> object: ...

    @property
    def model(self) -> object: ...


@runtime_checkable
class _DocumentRecord(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def source_id(self) -> object: ...

    @property
    def title(self) -> object: ...

    @property
    def summary(self) -> object: ...

    @property
    def content(self) -> object: ...

    @property
    def state(self) -> object: ...

    @property
    def publish_date(self) -> object: ...

    @property
    def uri(self) -> object: ...


@runtime_checkable
class _SqlBinaryOperator(Protocol):
    def __call__(self, other: object) -> ColumnElement[float]: ...


@runtime_checkable
class _SqlVectorColumn(Protocol):
    def op(self, operator: str, *, return_type: object) -> object: ...


_ES_INDEX = "policy_docs_es"
_last_used_backends: list[str] = []


def _set_last_used_backends(backends: list[str]) -> None:
    global _last_used_backends
    _last_used_backends = backends[:]


def get_last_used_backends() -> list[str]:
    return list(_last_used_backends)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, (list, tuple))


def _is_object_iterable(value: object) -> TypeGuard[Iterable[object]]:
    return isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping))


def _try_search_json_value(value: object) -> tuple[bool, SearchJsonValue]:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True, value
    if isinstance(value, (date, datetime)):
        return True, value.isoformat()
    if _is_object_sequence(value):
        output: SearchJsonArray = []
        for item in value:
            valid, parsed = _try_search_json_value(item)
            if not valid:
                return False, None
            output.append(parsed)
        return True, output
    if _is_object_mapping(value):
        output_object: SearchJsonObject = {}
        for key, item in value.items():
            if type(key) is not str:
                return False, None
            valid, parsed = _try_search_json_value(item)
            if not valid:
                return False, None
            output_object[key] = parsed
        return True, output_object
    return False, None


def _json_object(value: object) -> SearchJsonObject | None:
    valid, parsed = _try_search_json_value(value)
    if valid and type(parsed) is dict:
        return parsed
    return None


def _shallow_object(value: object) -> dict[str, object] | None:
    if not _is_object_mapping(value):
        return None
    output: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            return None
        output[key] = item
    return output


def _object_field(value: SearchJsonObject, key: str) -> SearchJsonObject | None:
    item = value.get(key)
    return item if type(item) is dict else None


def _array_field(value: SearchJsonObject, key: str) -> SearchJsonArray | None:
    item = value.get(key)
    return item if type(item) is list else None


def _first_present(*values: SearchJsonValue) -> SearchJsonValue:
    for value in values:
        if value:
            return value
    return None


def _float_value(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _float_vector(value: object) -> list[float] | None:
    if not _is_object_sequence(value):
        return None
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        vector.append(float(item))
    return vector


def _provider_json_value(value: object, *, field: str) -> SearchJsonValue:
    valid, parsed = _try_search_json_value(value)
    if valid:
        return parsed
    logger.warning("search provider returned a non-JSON value for %s", field)
    return None


def _project_scope(project_key: str | None) -> str:
    if project_key is not None:
        normalized = str(project_key).strip()
        if normalized:
            return normalized
    return current_project_key()


def bm25_search(
    es: Elasticsearch,
    query: str,
    state: str | None,
    top_k: int,
    project_key: str | None = None,
) -> list[SearchRow]:
    must: SearchJsonArray = [
        {"multi_match": {"query": query, "fields": ["title^3", "summary^2", "text"]}},
        {"term": {"project_key": _project_scope(project_key)}},
    ]
    if state:
        must.append({"term": {"state": state}})

    raw_response: object = es.search(
        index=_ES_INDEX,
        body={
            "size": top_k,
            "query": {"bool": {"must": must}},
            "highlight": {"fields": {"text": {"number_of_fragments": 1}}},
        },
    )
    response = _shallow_object(raw_response)
    hits_block = _shallow_object(response.get("hits")) if response is not None else None
    raw_hits_object = hits_block.get("hits") if hits_block is not None else None
    if not _is_object_sequence(raw_hits_object):
        logger.warning("OpenSearch response has no JSON hits array")
        return []

    hits: list[SearchRow] = []
    for raw_hit in raw_hits_object:
        hit = _json_object(raw_hit)
        source = _object_field(hit, "_source") if hit is not None else None
        if hit is None or source is None:
            logger.warning("OpenSearch returned a non-object search hit")
            continue
        highlight = _object_field(hit, "highlight") or {}
        source_uri = _first_present(
            source.get("source_uri"),
            source.get("url"),
            source.get("uri"),
        )
        hits.append(
            {
                "material_id": source.get("material_id"),
                "project_key": source.get("project_key"),
                "object_type": source.get("object_type"),
                "object_id": source.get("object_id"),
                "chunk_id": source.get("chunk_id"),
                "source_id": source.get("source_id"),
                "vector_version": source.get("vector_version"),
                "embedding_model": source.get("embedding_model"),
                "embedding_dim": source.get("embedding_dim"),
                "score": _float_value(hit.get("_score")),
                "chunk_index": source.get("chunk_index"),
                "title": source.get("title"),
                "summary": source.get("summary"),
                "text": source.get("text"),
                "highlight": _array_field(highlight, "text") or [],
                "state": source.get("state"),
                "publish_date": source.get("publish_date"),
                "source_uri": source_uri,
                "source_domain": source.get("source_domain"),
                "effective_time": source.get("effective_time"),
                "language": source.get("language"),
                "mode": "bm25",
                "backend": "opensearch",
                "tags": ["lexical", "bm25"],
            }
        )
    return hits


def _qdrant_failure(code: str, message: str, exc: Exception) -> Failure:
    return search_failures.fail(
        code,
        message,
        {
            "owner": "search.hybrid.qdrant_port",
            "provider": "qdrant",
            "exception_type": type(exc).__name__,
        },
    )


def _qdrant_component(module_name: str, attribute: str) -> _KeywordFactory | None:
    module = import_module(module_name)
    candidate: object = getattr(module, attribute, None)
    return candidate if isinstance(candidate, _KeywordFactory) else None


def try_qdrant_vector_search(
    query: str,
    state: str | None,
    top_k: int,
    project_key: str | None = None,
) -> list[SearchRow] | Failure:
    """Run the Qdrant port and return its closed provider outcome."""
    try:
        client_factory = _qdrant_component("qdrant_client", "QdrantClient")
        filter_factory = _qdrant_component("qdrant_client.models", "Filter")
        condition_factory = _qdrant_component("qdrant_client.models", "FieldCondition")
        match_factory = _qdrant_component("qdrant_client.models", "MatchValue")
    except Exception as exc:  # noqa: BLE001
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)
    if client_factory is None:
        exc = TypeError("Qdrant client module does not expose QdrantClient")
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)
    if filter_factory is None:
        exc = TypeError("Qdrant client module does not expose Filter")
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)
    if condition_factory is None:
        exc = TypeError("Qdrant client module does not expose FieldCondition")
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)
    if match_factory is None:
        exc = TypeError("Qdrant client module does not expose the required constructors")
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)

    try:
        embedding = get_embeddings().embed_query(query)
    except Exception as exc:  # noqa: BLE001
        return _qdrant_failure("embedding_failed", f"embed_failed: {exc}", exc)

    url = os.getenv("QDRANT_URL")
    host = os.getenv("QDRANT_HOST")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    collection = os.getenv("QDRANT_COLLECTION", "policy_chunks")
    try:
        client_object = (
            client_factory(url=url)
            if url
            else client_factory(host=host or "localhost", port=port)
        )
    except Exception as exc:  # noqa: BLE001
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)
    if not isinstance(client_object, _QdrantSearchClient):
        exc = TypeError("Qdrant client does not expose the search port")
        return _qdrant_failure("backend_unavailable", f"qdrant_unavailable: {exc}", exc)

    scope = _project_scope(project_key)
    conditions: list[object] = [
        condition_factory(
            key="project_key",
            match=match_factory(value=scope),
        )
    ]
    if state:
        conditions.append(condition_factory(key="state", match=match_factory(value=state)))
    query_filter = filter_factory(must=conditions)

    try:
        raw_result: object = client_object.search(
            collection_name=collection,
            query_vector=embedding,
            query_filter=query_filter,
            limit=top_k,
        )
    except Exception as exc:  # noqa: BLE001
        return _qdrant_failure("vector_search_failed", f"qdrant_search_failed: {exc}", exc)
    if not _is_object_iterable(raw_result):
        exc = TypeError("Qdrant search response must be iterable")
        return _qdrant_failure("vector_search_failed", f"qdrant_search_failed: {exc}", exc)

    hits: list[SearchRow] = []
    for raw_point in raw_result:
        if not isinstance(raw_point, _QdrantPoint):
            logger.warning("Qdrant returned a point without payload/score")
            continue
        payload = _json_object(raw_point.payload)
        if payload is None:
            logger.warning("Qdrant returned a non-JSON payload")
            continue
        score = _float_value(raw_point.score)
        existing_provenance = _object_field(payload, "provenance") or {}
        source_uri = _first_present(
            payload.get("source_uri"), payload.get("url"), payload.get("uri")
        )
        source_id = _first_present(
            payload.get("source_id"), payload.get("source"), payload.get("material_id")
        )
        vector_version = _first_present(
            payload.get("vector_version"),
            existing_provenance.get("vector_version"),
            "v1",
        )
        embedding_model = _first_present(
            payload.get("embedding_model"),
            payload.get("model"),
            existing_provenance.get("embedding_model"),
        )
        embedding_model_version = _first_present(
            payload.get("embedding_model_version"),
            payload.get("embedding_version"),
            payload.get("model_version"),
            existing_provenance.get("embedding_model_version"),
            vector_version,
        )
        embedding_provider = _first_present(
            payload.get("embedding_provider"),
            payload.get("provider"),
            existing_provenance.get("provider"),
            "qdrant",
        )
        source_reference = _first_present(
            payload.get("source_reference"),
            payload.get("reference"),
            existing_provenance.get("source_reference"),
            source_uri,
            source_id,
        )
        embedding_dim = _first_present(
            payload.get("embedding_dim"), payload.get("dim")
        )
        provenance: SearchJsonObject = {
            **existing_provenance,
            "provider": embedding_provider,
            "backend": "qdrant_vector",
            "retrieval_mode": "vector",
            "provider_payload_kind": "qdrant_payload",
            "embedding_model": embedding_model,
            "embedding_model_version": embedding_model_version,
            "embedding_dim": embedding_dim,
            "vector_version": vector_version,
            "source": _first_present(payload.get("source"), source_id),
            "source_id": source_id,
            "source_reference": source_reference,
            "reference": source_reference,
            "source_uri": source_uri,
            "source_domain": payload.get("source_domain"),
            "score": score,
            "fallback_reason": None,
        }
        hits.append(
            {
                "material_id": payload.get("material_id"),
                "project_key": payload.get("project_key"),
                "object_type": payload.get("object_type"),
                "object_id": payload.get("object_id"),
                "chunk_id": payload.get("chunk_id"),
                "source_id": source_id,
                "vector_version": vector_version,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
                "embedding_model_version": embedding_model_version,
                "embedding_dim": embedding_dim,
                "score": score,
                "chunk_index": payload.get("chunk_index"),
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "text": payload.get("text"),
                "highlight": [],
                "state": payload.get("state"),
                "publish_date": payload.get("publish_date"),
                "source_uri": source_uri,
                "source_reference": source_reference,
                "source_domain": payload.get("source_domain"),
                "effective_time": payload.get("effective_time"),
                "language": payload.get("language"),
                "mode": "vector",
                "backend": "qdrant",
                "provider_payload_kind": "qdrant_payload",
                "payload_provenance": provenance,
                "provenance": provenance,
                "tags": ["vector", "qdrant"],
            }
        )
    return hits


def qdrant_vector_search(
    query: str,
    state: str | None,
    top_k: int,
    project_key: str | None = None,
) -> list[SearchRow]:
    """Compatibility lift for direct callers that still use RuntimeError."""
    result = try_qdrant_vector_search(query, state, top_k, project_key=project_key)
    if isinstance(result, Failure):
        # kit:boundary owner=search.hybrid.qdrant_compatibility_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_w04_search_qdrant_failure_core
        raise RuntimeError(result.message)  # noqa: TRY004
    return result


def _sql_rows(value: object) -> Iterable[tuple[object, object]]:
    if not _is_object_iterable(value):
        return []
    rows: list[tuple[object, object]] = []
    for raw_row in value:
        if not _is_object_iterable(raw_row):
            logger.warning("pgvector returned a non-row result")
            continue
        values = tuple(raw_row)
        if len(values) != 2:
            logger.warning("pgvector returned a row with unexpected arity")
            continue
        rows.append((values[0], values[1]))
    return rows


def _pgvector_distance(vector: object) -> ColumnElement[float] | None:
    column_object: object = getattr(Embedding, "vector", None)
    if not isinstance(column_object, _SqlVectorColumn):
        return None
    operator_object = column_object.op("OPERATOR(public.<->)", return_type=Float)
    if not isinstance(operator_object, _SqlBinaryOperator):
        return None
    return operator_object(vector)


def vector_search(
    query: str,
    state: str | None,
    top_k: int,
    project_key: str | None = None,
) -> list[SearchRow]:
    scope = _project_scope(project_key)
    used_fallback = False
    fallback_reason: str | None = None
    try:
        qdrant_attempt: list[SearchRow] | Failure = qdrant_vector_search(
            query, state, top_k, project_key=scope
        )
    except RuntimeError as exc:
        qdrant_attempt = _qdrant_failure("vector_search_failed", str(exc), exc)
    if isinstance(qdrant_attempt, Failure):
        logger.info("Qdrant 不可用或查询失败，降级至 pgvector: %s", qdrant_attempt.message)
        used_fallback = True
        fallback_reason = qdrant_attempt.message
    else:
        return qdrant_attempt

    try:
        embedding = get_embeddings().embed_query(query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("无法生成向量嵌入，跳过向量搜索: %s", exc)
        return []

    with bind_project(scope):
        with SessionLocal() as session:
            vector = np.array(embedding)
            distance = _pgvector_distance(vector)
            if distance is None:
                logger.warning("pgvector model does not expose the public distance operator")
                return []
            stmt = (
                select(Embedding, Material)
                .join(Material, Material.id == Embedding.object_id)
                .filter(Embedding.object_type == "policy_chunk")
                .order_by(distance)
            )
            if state:
                stmt = stmt.filter(Material.state == state)
            raw_results: object = session.execute(stmt.limit(top_k)).all()

    hits: list[SearchRow] = []
    for raw_embedding, raw_document in _sql_rows(raw_results):
        if not isinstance(raw_embedding, _EmbeddingRecord) or not isinstance(
            raw_document, _DocumentRecord
        ):
            logger.warning("pgvector returned a row outside the embedding/material boundary")
            continue
        stored_vector = _float_vector(raw_embedding.vector)
        if stored_vector is None:
            logger.warning("pgvector returned an invalid embedding vector")
            continue
        tags: SearchJsonArray = ["vector", "pgvector"]
        if used_fallback:
            tags.append("fallback")
        score = float(np.dot(vector, np.array(stored_vector)))
        material_id = _provider_json_value(raw_document.id, field="material.id")
        raw_source_id = _provider_json_value(raw_document.source_id, field="material.source_id")
        source_id = raw_source_id or material_id
        source_uri = _provider_json_value(raw_document.uri, field="material.uri")
        vector_version = "v1"
        raw_provider = _provider_json_value(raw_embedding.provider, field="embedding.provider")
        embedding_provider = raw_provider or "pgvector"
        embedding_model = _provider_json_value(raw_embedding.model, field="embedding.model")
        source_reference: SearchJsonValue = (
            source_uri if source_uri else f"material:{material_id}"
        )
        object_type = _provider_json_value(raw_embedding.object_type, field="embedding.object_type")
        object_id = _provider_json_value(raw_embedding.object_id, field="embedding.object_id")
        embedding_dim = _provider_json_value(raw_embedding.dim, field="embedding.dim")
        title = _provider_json_value(raw_document.title, field="material.title")
        summary = _provider_json_value(raw_document.summary, field="material.summary")
        text = _provider_json_value(raw_document.content, field="material.content")
        document_state = _provider_json_value(raw_document.state, field="material.state")
        publish_date = _provider_json_value(
            raw_document.publish_date, field="material.publish_date"
        )
        provenance: SearchJsonObject = {
            "provider": embedding_provider,
            "backend": "pgvector_fallback",
            "retrieval_mode": "vector",
            "provider_payload_kind": "pgvector_payload",
            "embedding_model": embedding_model,
            "embedding_model_version": vector_version,
            "embedding_dim": embedding_dim,
            "vector_version": vector_version,
            "source": f"material:{material_id}",
            "source_id": source_id,
            "source_reference": source_reference,
            "reference": source_reference,
            "source_uri": source_uri,
            "score": score,
            "fallback_reason": fallback_reason if used_fallback else None,
        }
        hits.append(
            {
                "material_id": material_id,
                "object_type": object_type,
                "object_id": object_id,
                "source_id": source_id,
                "vector_version": vector_version,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
                "embedding_model_version": vector_version,
                "embedding_dim": embedding_dim,
                "score": score,
                "chunk_index": None,
                "title": title,
                "summary": summary,
                "text": text,
                "highlight": [],
                "state": document_state,
                "publish_date": publish_date,
                "source_uri": source_uri,
                "source_reference": source_reference,
                "mode": "vector",
                "backend": "pgvector",
                "provider_payload_kind": "pgvector_payload",
                "fallback_reason": fallback_reason if used_fallback else None,
                "payload_provenance": provenance,
                "provenance": provenance,
                "tags": tags,
            }
        )
    return hits


def _fusion_identity(hit: SearchRow, rank: int, backend: str) -> str:
    material_id = hit.get("material_id")
    if isinstance(material_id, (str, int, float, bool)):
        return f"{type(material_id).__name__}:{material_id}"
    return f"{backend}:{rank}"


def _fusion_score(hit: SearchRow) -> float:
    return _float_value(hit.get("fusion_score"))


def reciprocal_rank_fusion(
    bm25_hits: list[SearchRow],
    vector_hits: list[SearchRow],
    k: int = 60,
) -> list[SearchRow]:
    fused: dict[str, SearchRow] = {}

    for rank, hit in enumerate(bm25_hits, start=1):
        identity = _fusion_identity(hit, rank, "bm25")
        row = fused.setdefault(identity, hit.copy())
        row["fusion_score"] = _fusion_score(row) + 1.0 / (k + rank)

    for rank, hit in enumerate(vector_hits, start=1):
        identity = _fusion_identity(hit, rank, "vector")
        if identity in fused:
            row = fused[identity]
            row["fusion_score"] = _fusion_score(row) + 1.0 / (k + rank)
        else:
            row = hit.copy()
            row["fusion_score"] = _fusion_score(hit) + 1.0 / (k + rank)
            fused[identity] = row

    combined = list(fused.values())
    combined.sort(key=_fusion_score, reverse=True)
    return combined


def _backend_name(hit: SearchRow, default: str) -> str:
    backend = hit.get("backend")
    return backend if isinstance(backend, str) and backend else default


def hybrid_search(
    query: str,
    state: str | None,
    top_k: int,
    mode: str,
    project_key: str | None = None,
) -> list[SearchRow]:
    es = get_es_client()
    scope = _project_scope(project_key)

    if mode == "bm25":
        hits = bm25_search(es, query, state, top_k, project_key=scope)
        _set_last_used_backends(["opensearch"])
        return hits

    if mode == "vector":
        results = vector_search(query, state, top_k, project_key=scope)
        backend = _backend_name(results[0], "pgvector") if results else "pgvector"
        _set_last_used_backends([backend])
        return results

    bm25_hits = bm25_search(es, query, state, top_k, project_key=scope)
    try:
        vector_hits = vector_search(query, state, top_k, project_key=scope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("向量搜索失败，仅返回BM25搜索结果: %s", exc)
        _set_last_used_backends(["opensearch"])
        return bm25_hits

    used = ["opensearch"]
    if vector_hits:
        used.append(_backend_name(vector_hits[0], "pgvector"))
        fused = reciprocal_rank_fusion(bm25_hits, vector_hits)
        _set_last_used_backends(used)
        return fused

    _set_last_used_backends(used)
    return bm25_hits
