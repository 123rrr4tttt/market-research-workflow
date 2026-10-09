from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from importlib import import_module
import logging
import os
from typing import NoReturn, Protocol, TypeGuard, TypedDict, runtime_checkable
from urllib.parse import urlparse

from elasticsearch.helpers import bulk
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ...models.base import SessionLocal
from ...models.entities import Material, Embedding
from ...settings.config import settings
from ..llm.provider import get_embeddings
from ..search.es_client import get_es_client
from ..job_logger import start_job, complete_job, fail_job
from ..projects import current_project_key
from ..document_views import get_extracted_data
from mrw_functorial_kit.core.provider_port_failures import (
    IndexerPolicyFailureCode,
    indexer_policy_failures,
)
from functorial_kit import Failure


_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 120
_EMBEDDING_OBJECT_TYPE = "policy_chunk"
_ES_INDEX = "policy_docs_es"
_VECTOR_VERSION = "v1"
_REQUIRED_VECTOR_FIELDS = (
    "project_key",
    "object_type",
    "object_id",
    "vector_version",
    "clean_text",
    "language",
    "source_domain",
    "effective_time",
    "keep_for_vectorization",
)

logger = logging.getLogger(__name__)


@runtime_checkable
class _VectorContractDocument(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def uri(self) -> str | None: ...

    @property
    def publish_date(self) -> date | None: ...

    @property
    def created_at(self) -> datetime | None: ...


@runtime_checkable
class _PolicyDocument(_VectorContractDocument, Protocol):
    @property
    def content(self) -> str | None: ...

    @property
    def summary(self) -> str | None: ...


@runtime_checkable
class _IndexedDocument(_PolicyDocument, Protocol):

    @property
    def state(self) -> str | None: ...

    @property
    def status(self) -> str | None: ...

    @property
    def title(self) -> str | None: ...


@runtime_checkable
class _MutableEmbedding(Protocol):
    id: int
    object_id: int
    object_type: str
    modality: str
    vector: list[float]
    dim: int
    provider: str
    model: str


@runtime_checkable
class _ElasticsearchDeletePort(Protocol):
    def delete_by_query(
        self,
        *,
        index: str,
        body: Mapping[str, object],
        ignore: list[int],
        refresh: bool,
    ) -> object: ...


@runtime_checkable
class _QdrantClientPort(Protocol):
    def get_collection(self, collection_name: str) -> object: ...

    def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: Mapping[str, object],
    ) -> object: ...

    def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[object],
        wait: bool,
    ) -> object: ...


@runtime_checkable
class _QdrantClientFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QdrantClientModule(Protocol):
    @property
    def QdrantClient(self) -> _QdrantClientFactory: ...


@runtime_checkable
class _QdrantPointFactory(Protocol):
    def __call__(
        self,
        *,
        id: int,
        vector: list[float],
        payload: dict[str, object],
    ) -> object: ...


@runtime_checkable
class _QdrantModelsModule(Protocol):
    @property
    def PointStruct(self) -> _QdrantPointFactory: ...


class VectorContractPayload(TypedDict):
    project_key: str
    object_type: str
    object_id: int
    vector_version: str | None
    clean_text: str | None
    language: str | None
    source_domain: str | None
    effective_time: str | None
    keep_for_vectorization: object


@dataclass
class PolicyChunk:
    document: _PolicyDocument
    text: str
    chunk_index: int


def _is_policy_document(value: object) -> TypeGuard[_PolicyDocument]:
    return isinstance(value, _PolicyDocument)


def _is_indexed_document(value: object) -> TypeGuard[_IndexedDocument]:
    return isinstance(value, _IndexedDocument)


def _is_mutable_embedding(value: object) -> TypeGuard[_MutableEmbedding]:
    return isinstance(value, Embedding)


def _extracted_data(document: object) -> dict[str, object]:
    raw: Mapping[str, object] = get_extracted_data(document)
    return dict(raw)


def _as_non_empty_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _infer_source_domain(
    document: _VectorContractDocument,
    extracted_data: Mapping[str, object],
) -> str | None:
    direct = _as_non_empty_text(extracted_data.get("source_domain"))
    if direct:
        return direct
    uri = _as_non_empty_text(document.uri)
    if not uri:
        return None
    return _as_non_empty_text(urlparse(uri).netloc)


def _infer_effective_time(
    document: _VectorContractDocument,
    extracted_data: Mapping[str, object],
) -> str | None:
    explicit = _as_non_empty_text(extracted_data.get("effective_time"))
    if explicit:
        return explicit
    if document.publish_date is not None:
        return document.publish_date.isoformat()
    if document.created_at is not None:
        return document.created_at.isoformat()
    return None


def _required_project_key(extracted_data: Mapping[str, object]) -> str:
    bound_project_key = _as_non_empty_text(current_project_key())
    declared_project_key = _as_non_empty_text(extracted_data.get("project_key"))
    if not bound_project_key:
        _raise_indexer_failure(
            _indexer_failure(
                "vector_contract_missing_fields",
                "project_scope_required",
                site="vector_contract.project_key",
            )
        )
    if declared_project_key is not None and declared_project_key != bound_project_key:
        _raise_indexer_failure(
            _indexer_failure(
                "vector_contract_missing_fields",
                "project_scope_conflict",
                site="vector_contract.project_key",
            )
        )
    return bound_project_key


def _build_vector_contract_payload(
    document: _VectorContractDocument,
    clean_text: str,
) -> VectorContractPayload:
    extracted_data = _extracted_data(document)
    payload: VectorContractPayload = {
        "project_key": _required_project_key(extracted_data),
        "object_type": _EMBEDDING_OBJECT_TYPE,
        "object_id": int(document.id),
        "vector_version": _as_non_empty_text(extracted_data.get("vector_version") or _VECTOR_VERSION),
        "clean_text": _as_non_empty_text(clean_text),
        "language": _as_non_empty_text(extracted_data.get("language") or "unknown"),
        "source_domain": _infer_source_domain(document, extracted_data),
        "effective_time": _infer_effective_time(document, extracted_data),
        "keep_for_vectorization": extracted_data.get("keep_for_vectorization", True),
    }
    return payload


def _indexer_failure(
    code: IndexerPolicyFailureCode,
    message: str,
    *,
    site: str,
) -> Failure:
    return indexer_policy_failures.fail(
        code,
        message,
        {"operation": "index_policy_documents", "site": site},
    )


def _raise_indexer_failure(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    # kit:boundary owner=indexer.policy.contract_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=indexer.policy.failure witness=test:test_w03_indexer_contract_failures
    raise exception_type(failure.message)


def _validate_vector_contract_payload(
    payload: Mapping[str, object],
) -> Failure | None:
    missing: list[str] = []
    for field in _REQUIRED_VECTOR_FIELDS:
        value = payload.get(field)
        if field == "keep_for_vectorization":
            if not isinstance(value, bool):
                missing.append(field)
            continue
        if isinstance(value, str):
            if not value.strip():
                missing.append(field)
            continue
        if value is None:
            missing.append(field)
    if missing:
        return _indexer_failure(
            "vector_contract_missing_fields",
            f"vector_contract_missing_fields: {','.join(sorted(set(missing)))}",
            site="vector_contract.required_fields",
        )
    if payload.get("keep_for_vectorization") is not True:
        return _indexer_failure(
            "vector_contract_not_vectorizable",
            "vector_contract_keep_for_vectorization_false",
            site="vector_contract.keep_for_vectorization",
        )
    return None


def index_policy_documents(
    material_ids: Sequence[int] | None = None,
    state: str | None = None,
) -> dict[str, int]:
    if not settings.openai_api_key:
        _raise_indexer_failure(
            _indexer_failure(
                "embedding_provider_not_configured",
                "OPENAI_API_KEY 未配置，无法生成嵌入",
                site="embedding_provider.configuration",
            ),
            RuntimeError,
        )

    job_params: dict[str, object] = {}
    if material_ids:
        job_params["material_ids"] = list(material_ids)
    if state:
        job_params["state"] = state
    job_id = start_job("index_policy", job_params)

    with SessionLocal() as session:
        query = session.query(Material).filter(Material.material_type == "policy")
        if material_ids:
            query = query.filter(Material.id.in_(list(material_ids)))
        if state:
            query = query.filter(Material.state == state)

        document_rows: Sequence[object] = query.order_by(Material.id.asc()).all()
        documents: list[_PolicyDocument] = []
        for row in document_rows:
            if not _is_policy_document(row):
                _raise_indexer_failure(
                    _indexer_failure(
                        "index_execution_failed",
                        "policy_document_shape_invalid",
                        site="policy_document.query_result",
                    ),
                    TypeError,
                )
            documents.append(row)

        if not documents:
            complete_job(job_id, result={"indexed": 0})
            return {"indexed": 0, "deleted": 0}

        chunks: list[PolicyChunk] = []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP
        )

        for doc in documents:
            content = (doc.content or doc.summary or "").strip()
            if not content:
                continue

            splits = splitter.split_text(content)
            for idx, chunk_text in enumerate(splits):
                chunks.append(PolicyChunk(document=doc, text=chunk_text, chunk_index=idx))

        if not chunks:
            session.commit()
            return {"indexed": 0, "deleted": 0}

        prepared_chunks: list[tuple[PolicyChunk, VectorContractPayload]] = []
        try:
            for chunk in chunks:
                vector_contract = _build_vector_contract_payload(chunk.document, chunk.text)
                vector_contract_failure = _validate_vector_contract_payload(vector_contract)
                if vector_contract_failure is not None:
                    _raise_indexer_failure(vector_contract_failure)
                prepared_chunks.append((chunk, vector_contract))

            indexed_material_ids = {
                chunk.document.id for chunk, _ in prepared_chunks
            }
            for material_id in sorted(indexed_material_ids):
                session.query(Embedding).filter(
                    Embedding.object_type == _EMBEDDING_OBJECT_TYPE,
                    Embedding.object_id == material_id,
                ).delete(synchronize_session=False)

            embedding_model = get_embeddings()
            vectors = embedding_model.embed_documents([chunk.text for chunk in chunks])

            es = get_es_client()
            _delete_existing_es_docs(
                es,
                indexed_material_ids,
                prepared_chunks[0][1]["project_key"],
            )

            es_actions: list[dict[str, object]] = []
            # Collect Qdrant points opportunistically (id, vector, payload)
            qdrant_points: list[tuple[int, list[float], dict[str, object]]] = []
            qdrant_collection = os.environ.get("QDRANT_COLLECTION", "policy_chunks")
            for (chunk, vector_contract), vector in zip(prepared_chunks, vectors):
                if not _is_indexed_document(chunk.document):
                    _raise_indexer_failure(
                        _indexer_failure(
                            "index_execution_failed",
                            "indexed_policy_document_shape_invalid",
                            site="policy_document.index_projection",
                        ),
                        TypeError,
                    )
                document = chunk.document
                raw_embedding: object = Embedding()
                if not _is_mutable_embedding(raw_embedding):
                    _raise_indexer_failure(
                        _indexer_failure(
                            "index_execution_failed",
                            "embedding_record_shape_invalid",
                            site="embedding.persistence_record",
                        ),
                        TypeError,
                    )
                embedding_row = raw_embedding
                embedding_row.object_id = document.id
                embedding_row.object_type = _EMBEDDING_OBJECT_TYPE
                embedding_row.modality = "text"
                embedding_row.vector = vector
                embedding_row.dim = len(vector)
                embedding_row.provider = settings.llm_provider
                embedding_row.model = settings.embedding_model
                session.add(embedding_row)
                session.flush()

                es_actions.append(
                    {
                        "_index": _ES_INDEX,
                        "_id": _es_material_id(
                            vector_contract["project_key"], document.id, chunk.chunk_index
                        ),
                        "embedding_id": embedding_row.id,
                        "project_key": vector_contract["project_key"],
                        "object_type": vector_contract["object_type"],
                        "object_id": vector_contract["object_id"],
                        "vector_version": vector_contract["vector_version"],
                        "clean_text": vector_contract["clean_text"],
                        "language": vector_contract["language"],
                        "source_domain": vector_contract["source_domain"],
                        "effective_time": vector_contract["effective_time"],
                        "keep_for_vectorization": vector_contract["keep_for_vectorization"],
                        "topic": _extracted_data(document).get("topic"),
                        "domain": _extracted_data(document).get("domain"),
                        "material_id": document.id,
                        "material_type": "policy",
                        "chunk_index": chunk.chunk_index,
                        "state": document.state,
                        "status": document.status,
                        "publish_date": document.publish_date.isoformat()
                        if document.publish_date is not None
                        else None,
                        "title": document.title,
                        "summary": document.summary,
                        "text": chunk.text,
                    }
                )

                # Prepare Qdrant payload/point (optional)
                try:
                    payload: dict[str, object] = {
                        "project_key": vector_contract["project_key"],
                        "object_type": vector_contract["object_type"],
                        "object_id": vector_contract["object_id"],
                        "vector_version": vector_contract["vector_version"],
                        "material_id": document.id,
                        "material_type": "policy",
                        "chunk_index": chunk.chunk_index,
                        "state": document.state,
                        "status": document.status,
                        "publish_date": document.publish_date.isoformat()
                        if document.publish_date is not None
                        else None,
                        "title": document.title,
                        "language": vector_contract["language"],
                        "source_domain": vector_contract["source_domain"],
                        "effective_time": vector_contract["effective_time"],
                        "summary": document.summary,
                        "text": chunk.text,
                    }
                    qdrant_points.append((int(embedding_row.id), list(vector), payload))
                except Exception:
                    # Collecting payload should never break indexing
                    pass

            session.commit()
            if es_actions:
                # Committed DB state remains committed if ES bulk fails.
                bulk(es, es_actions)
        except Exception as exc:
            session.rollback()
            fail_job(job_id, str(exc))
            # kit:boundary owner=indexer.policy.execution class=SHELL_BOUNDARY_EXCEPTION failure_family=indexer.policy.failure witness=test:test_w03_effect_boundaries
            raise

        result = {"indexed": len(es_actions), "materials": len({chunk.document.id for chunk in chunks})}
        complete_job(job_id, result=result)
        # Optional Qdrant upsert (best-effort, out of main transaction)
        try:
            client = _get_qdrant_client()
            if client is not None and _ensure_qdrant_collection(client, qdrant_collection, settings.embedding_dim):
                point_factory = _get_qdrant_point_factory()
                if point_factory is not None:
                    points: list[object] = [
                        point_factory(id=pid, vector=vec, payload=payload)
                        for pid, vec, payload in qdrant_points
                    ]
                    if points:
                        client.upsert(collection_name=qdrant_collection, points=points, wait=False)
                        logger.info("Qdrant upsert completed: %d points", len(points))
            else:
                logger.info("Qdrant not configured, skip upsert")
        except Exception as qx:
            logger.warning("Qdrant upsert skipped due to error: %s", qx)
        return result


def _delete_existing_es_docs(
    es: object,
    material_ids: Iterable[int],
    project_key: str,
) -> None:
    ids = list(material_ids)
    if not ids:
        return
    if not isinstance(es, _ElasticsearchDeletePort):
        _raise_indexer_failure(
            _indexer_failure(
                "index_execution_failed",
                "elasticsearch_delete_port_invalid",
                site="elasticsearch.delete_by_query",
            ),
            TypeError,
        )
    es.delete_by_query(
        index=_ES_INDEX,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"project_key": project_key}},
                        {"terms": {"material_id": ids}},
                    ]
                }
            }
        },
        ignore=[404],
        refresh=True,
    )


def _es_material_id(project_key: str, material_id: int, chunk_index: int) -> str:
    return f"policy-{project_key}-{material_id}-{chunk_index}"


def _get_qdrant_client() -> _QdrantClientPort | None:
    """Create qdrant client if environment/config present, else None.

    Import inside function to avoid hard dependency at import time.
    """
    url = os.environ.get("QDRANT_URL")
    host = os.environ.get("QDRANT_HOST")
    port = os.environ.get("QDRANT_PORT")
    try:
        module = import_module("qdrant_client")
    except Exception:
        logger.info("qdrant-client not installed, skip Qdrant integration")
        return None
    if not isinstance(module, _QdrantClientModule):
        logger.warning("qdrant-client module has no compatible QdrantClient factory")
        return None
    try:
        candidate: object | None = None
        if url:
            candidate = module.QdrantClient(url=url)
        elif host and port:
            candidate = module.QdrantClient(host=host, port=int(port))
        if candidate is None:
            return None
        if not isinstance(candidate, _QdrantClientPort):
            logger.warning("Qdrant client does not implement the indexing port")
            return None
        return candidate
    except Exception as exc:
        logger.warning("Qdrant client init failed: %s", exc)
        return None


def _get_qdrant_point_factory() -> _QdrantPointFactory | None:
    try:
        module = import_module("qdrant_client.models")
    except Exception as exc:
        logger.warning("Qdrant point model unavailable: %s", exc)
        return None
    if not isinstance(module, _QdrantModelsModule):
        logger.warning("Qdrant models module has no compatible PointStruct factory")
        return None
    return module.PointStruct


def _ensure_qdrant_collection(
    client: _QdrantClientPort,
    collection_name: str,
    dim: int,
) -> bool:
    try:
        client.get_collection(collection_name)
        return True
    except Exception:
        try:
            client.create_collection(
                collection_name=collection_name,
                vectors_config={"size": dim, "distance": "Cosine"},
            )
            return True
        except Exception as exc:
            logger.warning("Create Qdrant collection failed: %s", exc)
            return False
