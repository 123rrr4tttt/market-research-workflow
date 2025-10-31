from fastapi import APIRouter, Query
from ..services.search.es_client import get_es_client
from ..services.search.indexes import ensure_indices
from ..services.search.hybrid import hybrid_search


router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str = Query("lottery"),
    state: str | None = None,
    modality: str = Query("any"),
    rank: str = Query("hybrid"),
    top_k: int = Query(10, ge=1, le=100),
):
    """Placeholder: 混合检索统一接口（MVP 后续接 ES/pgvector）。"""
    results = hybrid_search(q, state, top_k, rank)
    return {
        "query": q,
        "state": state,
        "modality": modality,
        "rank": rank,
        "top_k": top_k,
        "results": results,
    }


@router.post("/_init")
def init_search_indices():
    """Create ES indices if not present (idempotent)."""
    es = get_es_client()
    return ensure_indices(es)


