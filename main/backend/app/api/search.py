from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from ..contracts import ApiEnvelope, ErrorCode, error_response
from ..contracts.responses import ok
from ..services.document_queries import (
    DOCUMENT_QUERY_CONTRACT_VERSION,
    build_search_endpoint_document_query_envelope,
)
from ..services.search.es_client import get_es_client
from ..services.search.indexes import ensure_indices
from ..services.search.hybrid import hybrid_search, get_last_used_backends
from ..services.search.retrieval_runs import persist_search_retrieval_run_record
from ..services.search.vector_contracts import (
    GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
    SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    build_retrieval_run_record,
    build_search_evidence_hits,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def _raise_upstream_error(message: str, *, details: dict | None = None) -> None:
    raise HTTPException(
        status_code=503,
        detail=error_response(
            ErrorCode.UPSTREAM_ERROR,
            message,
            details=details,
        ),
    )


def _raise_internal_error(message: str, *, details: dict | None = None) -> None:
    raise HTTPException(
        status_code=500,
        detail=error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
            details=details,
        ),
    )


SearchEnvelope = ApiEnvelope[dict[str, Any]]


@router.get("", response_model=SearchEnvelope)
def search(
    request: Request,
    q: str = Query("market trend"),
    state: str | None = None,
    modality: str = Query("any"),
    rank: str = Query("hybrid"),
    top_k: int = Query(10, ge=1, le=100),
):
    """Placeholder: 混合检索统一接口（MVP 后续接 ES/pgvector）。"""
    try:
        results = hybrid_search(q, state, top_k, rank)
        # Diagnostics about fallback/backends (contract-safe: added under data)
        fallback_order = [
            "opensearch_lexical",
            "qdrant_vector",
            "pgvector_fallback",
        ]
        used_backends = []
        for b in get_last_used_backends():
            if b == "opensearch":
                used_backends.append("opensearch_lexical")
            elif b == "qdrant":
                used_backends.append("qdrant_vector")
            elif b == "pgvector":
                used_backends.append("pgvector_fallback")
            else:
                used_backends.append(b)

        project_key = getattr(request.state, "project_key_resolved", None)
        query_group_id, evidence_hits = build_search_evidence_hits(
            results,
            query=q,
            project_key=project_key,
            rank_mode=rank,
            state=state,
            modality=modality,
            top_k=top_k,
        )
        retrieval_run = build_retrieval_run_record(
            query=q,
            query_group_id=query_group_id,
            evidence_hits=evidence_hits,
            project_key=project_key,
            rank_mode=rank,
            state=state,
            modality=modality,
            top_k=top_k,
            retrieval_family="main_search",
        )
        retrieval_run_readback = persist_search_retrieval_run_record(retrieval_run)
        document_query_envelope = build_search_endpoint_document_query_envelope(
            query=q,
            state=state,
            modality=modality,
            rank=rank,
            top_k=top_k,
            results=results,
            project_key=project_key,
            used_backends=used_backends,
        )
        document_query_data = document_query_envelope["data"]

        return ok(
            {
                "query": q,
                "state": state,
                "modality": modality,
                "rank": rank,
                "top_k": top_k,
                "results": results,
                "document_query_contract_version": DOCUMENT_QUERY_CONTRACT_VERSION,
                "document_query": document_query_data["query"],
                "document_query_results": document_query_data["results"],
                "document_query_pagination": document_query_data["pagination"],
                "document_query_meta": document_query_envelope["meta"],
                "global_vector_object_contract_version": GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
                "evidence_hit_contract_version": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
                "query_group_id": query_group_id,
                "evidence_hits": evidence_hits,
                "retrieval_run_contract_version": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
                "retrieval_run_id": retrieval_run["run_id"],
                "search_branches": retrieval_run["retrieval_branches"],
                "branch_hit_details": retrieval_run["retrieval_hits"],
                "retrieval_run": retrieval_run,
                "retrieval_run_readback": retrieval_run_readback,
                "search_fallback_order": fallback_order,
                "search_backends_used": used_backends,
            }
        )
    except Exception as e:
        logger.exception("搜索失败")
        error_msg = str(e)
        if "Connection" in error_msg or "es" in error_msg.lower() or "elasticsearch" in error_msg.lower():
            _raise_upstream_error(
                "Elasticsearch服务不可用，请检查ES服务是否已启动。如需跳过ES，请先启动ES服务或修改配置。",
                details={"exception_type": e.__class__.__name__, "category": "search_backend"},
            )
        _raise_internal_error(
            f"搜索失败: {error_msg}",
            details={"exception_type": e.__class__.__name__},
        )


@router.post("/_init", response_model=SearchEnvelope)
def init_search_indices():
    """Create ES indices if not present (idempotent)."""
    es = get_es_client()
    return ok(ensure_indices(es))
