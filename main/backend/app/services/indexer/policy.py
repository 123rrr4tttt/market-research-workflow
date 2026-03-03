from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence
from urllib.parse import urlparse

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ...models.base import SessionLocal
from ...models.entities import Document, Embedding
from ...settings.config import settings
from ..llm.provider import get_embeddings
from ..search.es_client import get_es_client
from ..job_logger import start_job, complete_job, fail_job
from ..projects import current_project_key


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


@dataclass
class PolicyChunk:
    document: Document
    text: str
    chunk_index: int


def _as_non_empty_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _infer_source_domain(document: Document, extracted_data: dict) -> str | None:
    direct = _as_non_empty_text(extracted_data.get("source_domain"))
    if direct:
        return direct
    uri = _as_non_empty_text(document.uri)
    if not uri:
        return None
    return _as_non_empty_text(urlparse(uri).netloc)


def _infer_effective_time(document: Document, extracted_data: dict) -> str | None:
    explicit = _as_non_empty_text(extracted_data.get("effective_time"))
    if explicit:
        return explicit
    if document.publish_date:
        return document.publish_date.isoformat()
    if document.created_at:
        return document.created_at.isoformat()
    return None


def _build_vector_contract_payload(document: Document, clean_text: str) -> dict:
    extracted_data = dict(document.extracted_data or {})
    payload = {
        "project_key": _as_non_empty_text(extracted_data.get("project_key") or current_project_key()),
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


def _validate_vector_contract_payload(payload: dict) -> None:
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
        raise ValueError(f"vector_contract_missing_fields: {','.join(sorted(set(missing)))}")
    if payload.get("keep_for_vectorization") is not True:
        raise ValueError("vector_contract_keep_for_vectorization_false")


def index_policy_documents(document_ids: Sequence[int] | None = None, state: str | None = None) -> dict:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置，无法生成嵌入")

    job_params = {}
    if document_ids:
        job_params["document_ids"] = list(document_ids)
    if state:
        job_params["state"] = state
    job_id = start_job("index_policy", job_params)

    with SessionLocal() as session:
        query = session.query(Document).filter(Document.doc_type == "policy")
        if document_ids:
            query = query.filter(Document.id.in_(list(document_ids)))
        if state:
            query = query.filter(Document.state == state)

        documents: List[Document] = query.order_by(Document.id.asc()).all()

        if not documents:
            complete_job(job_id, result={"indexed": 0})
            return {"indexed": 0, "deleted": 0}

        chunks: List[PolicyChunk] = []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP
        )

        for doc in documents:
            content = (doc.content or doc.summary or "").strip()
            if not content:
                continue

            # remove existing embeddings
            session.query(Embedding).filter(
                Embedding.object_type == _EMBEDDING_OBJECT_TYPE,
                Embedding.object_id == doc.id,
            ).delete(synchronize_session=False)

            splits = splitter.split_text(content)
            for idx, chunk_text in enumerate(splits):
                chunks.append(PolicyChunk(document=doc, text=chunk_text, chunk_index=idx))

        if not chunks:
            session.commit()
            return {"indexed": 0, "deleted": 0}

        try:
            embedding_model = get_embeddings()
            vectors = embedding_model.embed_documents([chunk.text for chunk in chunks])

            es = get_es_client()
            _delete_existing_es_docs(es, {chunk.document.id for chunk in chunks})

            es_actions = []
            for chunk, vector in zip(chunks, vectors):
                vector_contract = _build_vector_contract_payload(chunk.document, chunk.text)
                _validate_vector_contract_payload(vector_contract)
                embedding_row = Embedding(
                    object_id=chunk.document.id,
                    object_type=_EMBEDDING_OBJECT_TYPE,
                    modality="text",
                    vector=vector,
                    dim=len(vector),
                    provider=settings.llm_provider,
                    model=settings.embedding_model,
                )
                session.add(embedding_row)
                session.flush()

                es_actions.append(
                    {
                        "_index": _ES_INDEX,
                        "_id": f"policy-{chunk.document.id}-{embedding_row.id}",
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
                        "topic": (chunk.document.extracted_data or {}).get("topic"),
                        "domain": (chunk.document.extracted_data or {}).get("domain"),
                        "document_id": chunk.document.id,
                        "chunk_index": chunk.chunk_index,
                        "state": chunk.document.state,
                        "status": chunk.document.status,
                        "publish_date": chunk.document.publish_date.isoformat()
                        if chunk.document.publish_date
                        else None,
                        "title": chunk.document.title,
                        "summary": chunk.document.summary,
                        "text": chunk.text,
                    }
                )

            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            fail_job(job_id, str(exc))
            raise

        if es_actions:
            bulk(es, es_actions)

        result = {"indexed": len(es_actions), "documents": len({chunk.document.id for chunk in chunks})}
        complete_job(job_id, result=result)
        return result


def _delete_existing_es_docs(es: Elasticsearch, document_ids: Iterable[int]) -> None:
    for doc_id in document_ids:
        es.delete_by_query(
            index=_ES_INDEX,
            body={"query": {"term": {"document_id": doc_id}}},
            ignore=[404],
            refresh=True,
        )

