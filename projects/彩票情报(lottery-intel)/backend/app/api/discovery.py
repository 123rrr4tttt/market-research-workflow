from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..services.search.web import search_sources
from ..services.discovery.store import store_results
from ..services.discovery.deep_search import deep_search
from fastapi.responses import JSONResponse


class DiscoveryRequest(BaseModel):
    topic: str = Field(..., description="搜索主题或关键词")
    language: str = Field(default="en", description="关键词语言 zh/en")
    max_results: int = Field(default=10, le=50)
    provider: str = Field(default="auto", description="搜索服务提供商: auto/ddg/google/serpstack/serpapi")


router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/search")
def discovery_search(payload: DiscoveryRequest, debug: bool = Query(False), persist: bool = Query(True)):
    try:
        results = search_sources(
            payload.topic, 
            payload.language, 
            payload.max_results,
            provider=payload.provider
        )
        body = {"keywords": [r["keyword"] for r in results], "results": results, "provider_used": results[0].get("source", "unknown") if results else "none"}
        if persist and results:
            stats = store_results(results)
            body["stored"] = stats
        if debug:
            body["count"] = len(results)
        return body
    except Exception as exc:  # noqa: BLE001
        # 避免 500，前端将看到空结果并提示
        return JSONResponse(status_code=200, content={"keywords": [], "results": [], "error": str(exc)})


class DeepDiscoveryRequest(BaseModel):
    topic: str = Field(..., description="搜索主题或关键词")
    language: str = Field(default="en", description="关键词语言 zh/en")
    iterations: int = Field(default=2, ge=1, le=5)
    breadth: int = Field(default=2, ge=1, le=10)
    max_results: int = Field(default=20, le=100)




@router.post("/deep")
def discovery_deep(payload: DeepDiscoveryRequest, persist: bool = Query(True)):
    try:
        result = deep_search(
            payload.topic,
            payload.language,
            payload.iterations,
            payload.breadth,
            payload.max_results,
        )
        if persist and result.get("results"):
            stats = store_results(result["results"])
            result["stored"] = stats
        return result
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=200, content={"topic": payload.topic, "results": [], "error": str(exc)})

