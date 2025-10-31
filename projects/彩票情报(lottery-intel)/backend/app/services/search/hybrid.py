from __future__ import annotations

from typing import List

import numpy as np
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import Document, Embedding
from ...settings.config import settings
from ..llm.provider import get_embeddings
from .es_client import get_es_client


_ES_INDEX = "policy_docs_es"


def bm25_search(es: Elasticsearch, query: str, state: str | None, top_k: int) -> List[dict]:
    must = [{"multi_match": {"query": query, "fields": ["title^3", "summary^2", "text"]}}]
    if state:
        must.append({"term": {"state": state}})

    response = es.search(
        index=_ES_INDEX,
        body={
            "size": top_k,
            "query": {"bool": {"must": must}},
            "highlight": {"fields": {"text": {"number_of_fragments": 1}}},
        },
    )

    hits = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        hits.append(
            {
                "document_id": source.get("document_id"),
                "score": hit.get("_score", 0.0),
                "chunk_index": source.get("chunk_index"),
                "title": source.get("title"),
                "summary": source.get("summary"),
                "text": source.get("text"),
                "highlight": hit.get("highlight", {}).get("text", []),
                "state": source.get("state"),
                "publish_date": source.get("publish_date"),
                "mode": "bm25",
            }
        )
    return hits


def vector_search(query: str, state: str | None, top_k: int) -> List[dict]:
    with SessionLocal() as session:
        embedding = get_embeddings().embed_query(query)
        vector = np.array(embedding)

        stmt = (
            select(Embedding, Document)
            .join(Document, Document.id == Embedding.object_id)
            .filter(Embedding.object_type == "policy_chunk")
            .order_by(Embedding.vector.l2_distance(vector))
        )
        if state:
            stmt = stmt.filter(Document.state == state)

        results = session.execute(stmt.limit(top_k)).all()

        hits = []
        for embedding_row, document in results:
            hits.append(
                {
                    "document_id": document.id,
                    "score": float(np.dot(vector, np.array(embedding_row.vector))),
                    "chunk_index": None,
                    "title": document.title,
                    "summary": document.summary,
                    "text": document.content,
                    "highlight": [],
                    "state": document.state,
                    "publish_date": document.publish_date.isoformat()
                    if document.publish_date
                    else None,
                    "mode": "vector",
                }
            )
        return hits


def reciprocal_rank_fusion(bm25_hits: List[dict], vector_hits: List[dict], k: int = 60) -> List[dict]:
    fused: dict[int, dict] = {}

    for rank, hit in enumerate(bm25_hits, start=1):
        doc_id = hit["document_id"]
        fused.setdefault(doc_id, hit.copy())
        fused[doc_id]["fusion_score"] = fused[doc_id].get("fusion_score", 0.0) + 1.0 / (k + rank)

    for rank, hit in enumerate(vector_hits, start=1):
        doc_id = hit["document_id"]
        if doc_id in fused:
            fused[doc_id]["fusion_score"] += 1.0 / (k + rank)
        else:
            fused[doc_id] = hit.copy()
            fused[doc_id]["fusion_score"] = hit.get("fusion_score", 0.0) + 1.0 / (k + rank)

    combined = list(fused.values())
    combined.sort(key=lambda h: h.get("fusion_score", 0.0), reverse=True)
    return combined


def hybrid_search(query: str, state: str | None, top_k: int, mode: str) -> List[dict]:
    es = get_es_client()

    if mode == "bm25":
        return bm25_search(es, query, state, top_k)

    if mode == "vector":
        return vector_search(query, state, top_k)

    bm25_hits = bm25_search(es, query, state, top_k)
    vector_hits = vector_search(query, state, top_k)
    return reciprocal_rank_fusion(bm25_hits, vector_hits)


