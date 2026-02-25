from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

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


@dataclass
class PolicyChunk:
    document: Document
    text: str
    chunk_index: int


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
                        "project_key": current_project_key(),
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


