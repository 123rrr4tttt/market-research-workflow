from fastapi import APIRouter, Query, HTTPException
from ..services.search.es_client import get_es_client
from ..services.search.indexes import ensure_indices
from ..services.search.hybrid import hybrid_search
import logging

logger = logging.getLogger(__name__)

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
    try:
        results = hybrid_search(q, state, top_k, rank)
        return {
            "query": q,
            "state": state,
            "modality": modality,
            "rank": rank,
            "top_k": top_k,
            "results": results,
        }
    except Exception as e:
        logger.exception("搜索失败")
        error_msg = str(e)
        if "Connection" in error_msg or "es" in error_msg.lower() or "elasticsearch" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="Elasticsearch服务不可用，请检查ES服务是否已启动。如需跳过ES，请先启动ES服务或修改配置。"
            )
        raise HTTPException(status_code=500, detail=f"搜索失败: {error_msg}")


@router.post("/_init")
def init_search_indices():
    """Create ES indices if not present (idempotent)."""
    es = get_es_client()
    return ensure_indices(es)


