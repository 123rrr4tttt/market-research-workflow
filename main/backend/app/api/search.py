from fastapi import APIRouter, HTTPException, Query
from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..services.search.es_client import get_es_client
from ..services.search.indexes import ensure_indices
from ..services.search.hybrid import hybrid_search, get_last_used_backends
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


@router.get("")
def search(
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

        return ok(
            {
                "query": q,
                "state": state,
                "modality": modality,
                "rank": rank,
                "top_k": top_k,
                "results": results,
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


@router.post("/_init")
def init_search_indices():
    """Create ES indices if not present (idempotent)."""
    es = get_es_client()
    return ok(ensure_indices(es))
