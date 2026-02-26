from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Optional

from ..project_customization.service import get_project_customization
from ..services.search.web import generate_keywords, generate_topic_keywords
from ..services.discovery.application import DiscoveryApplicationService
from ..services.keyword_generation import generate_social_keywords, generate_subreddit_keywords
from ..services.job_logger import start_job, complete_job, fail_job
from fastapi.responses import JSONResponse
from ..contracts import ErrorCode, error_response, map_exception_to_error, success_response


class DiscoveryRequest(BaseModel):
    topic: str = Field(..., description="搜索主题或关键词")
    language: str = Field(default="en", description="关键词语言 zh/en")
    max_results: int = Field(default=10, le=50)
    provider: str = Field(default="auto", description="搜索服务提供商: auto/serper/ddg/google/serpstack/serpapi")
    days_back: Optional[int] = Field(default=None, ge=1, le=365, description="可选，只搜索最近N天的内容")
    exclude_existing: bool = Field(default=True, description="是否排除已入库的文档")
    start_offset: Optional[int] = Field(default=None, ge=1, description="分页起始位置（从1开始），用于分批获取多页结果")


router = APIRouter(prefix="/discovery", tags=["discovery"])
discovery_app = DiscoveryApplicationService.build_default()
DISCOVERY_ERROR_RESPONSES = {
    400: {"description": "Invalid input"},
    404: {"description": "Not found"},
    429: {"description": "Rate limited"},
    500: {"description": "Internal/config error"},
    502: {"description": "Upstream/parse error"},
}


def _error_status_code(code: ErrorCode) -> int:
    mapping = {
        ErrorCode.INVALID_INPUT: 400,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFIG_ERROR: 500,
        ErrorCode.UPSTREAM_ERROR: 502,
        ErrorCode.PARSE_ERROR: 502,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.INTERNAL_ERROR: 500,
    }
    return mapping.get(code, 500)


def _error_json(code: ErrorCode, message: str, details, *, meta: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=_error_status_code(code),
        content=error_response(
            code,
            message,
            details=details,
            meta=meta,
        ),
    )


def _project_unified_discovery_params(topic: str, max_results: int) -> dict:
    """Phase-2 bridge: expose a unified view without changing current API contract.

    This keeps discovery endpoints backward compatible while aligning with
    ingest naming (`query_terms` / `max_items`) for future consolidation.
    """
    normalized_topic = str(topic or "").strip()
    return {
        "query_terms": [normalized_topic] if normalized_topic else [],
        "max_items": int(max_results),
    }


@router.post("/search", responses=DISCOVERY_ERROR_RESPONSES)
def discovery_search(payload: DiscoveryRequest, debug: bool = Query(False), persist: bool = Query(True)):
    unified_params = _project_unified_discovery_params(payload.topic, payload.max_results)
    job_params = {
        "topic": payload.topic,
        "language": payload.language,
        "max_results": payload.max_results,
        "provider": payload.provider,
        "persist": persist,
        "days_back": payload.days_back,
        "exclude_existing": payload.exclude_existing,
        # Internal unified-params bridge (phase 2); external contract unchanged.
        "query_terms": unified_params["query_terms"],
        "max_items": unified_params["max_items"],
    }
    job_id = start_job("discovery_search", job_params)
    try:
        body = discovery_app.run_search(
            topic=payload.topic,
            language=payload.language,
            max_results=payload.max_results,
            provider=payload.provider,
            days_back=payload.days_back,
            exclude_existing=payload.exclude_existing,
            start_offset=payload.start_offset,
            persist=persist,
            job_type="discovery_search",
        )
        results = body.get("results", [])
        if debug:
            body["count"] = len(results)
        complete_job(
            job_id,
            result={
                "results": len(results),
                "stored": body.get("stored", {}),
            },
        )
        return success_response(body)
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details, meta={"keywords": [], "results": []})


class SmartDiscoveryRequest(BaseModel):
    topic: str = Field(..., description="搜索主题或关键词")
    language: str = Field(default="en", description="关键词语言 zh/en")
    max_results: int = Field(default=10, le=50)
    provider: str = Field(default="auto", description="搜索服务提供商: auto/serper/ddg/google/serpstack/serpapi")
    days_back: int = Field(default=30, ge=1, le=365, description="首次搜索时，回溯多少天")


@router.post("/smart", responses=DISCOVERY_ERROR_RESPONSES)
def discovery_smart(payload: SmartDiscoveryRequest, persist: bool = Query(True)):
    """智能搜索：自动增量搜索，只返回新信息"""
    unified_params = _project_unified_discovery_params(payload.topic, payload.max_results)
    job_params = {
        "topic": payload.topic,
        "language": payload.language,
        "max_results": payload.max_results,
        "provider": payload.provider,
        "persist": persist,
        "days_back": payload.days_back,
        # Internal unified-params bridge (phase 2); external contract unchanged.
        "query_terms": unified_params["query_terms"],
        "max_items": unified_params["max_items"],
    }
    job_id = start_job("discovery_smart", job_params)
    try:
        body = discovery_app.run_smart_search(
            topic=payload.topic,
            language=payload.language,
            max_results=payload.max_results,
            provider=payload.provider,
            days_back=payload.days_back,
            persist=persist,
            job_type="discovery_smart",
        )
        results = body.get("results", [])
        complete_job(
            job_id,
            result={
                "results": len(results),
                "stored": body.get("stored", {}),
            },
        )
        return success_response(body)
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details, meta={"topic": payload.topic, "results": []})


class DeepDiscoveryRequest(BaseModel):
    topic: str = Field(..., description="搜索主题或关键词")
    language: str = Field(default="en", description="关键词语言 zh/en")
    iterations: int = Field(default=2, ge=1, le=5)
    breadth: int = Field(default=2, ge=1, le=10)
    max_results: int = Field(default=20, le=100)




@router.post("/deep", responses=DISCOVERY_ERROR_RESPONSES)
def discovery_deep(payload: DeepDiscoveryRequest, persist: bool = Query(True)):
    unified_params = _project_unified_discovery_params(payload.topic, payload.max_results)
    job_params = {
        "topic": payload.topic,
        "language": payload.language,
        "iterations": payload.iterations,
        "breadth": payload.breadth,
        "max_results": payload.max_results,
        "persist": persist,
        # Internal unified-params bridge (phase 2); external contract unchanged.
        "query_terms": unified_params["query_terms"],
        "max_items": unified_params["max_items"],
    }
    job_id = start_job("discovery_deep", job_params)
    try:
        result = discovery_app.run_deep_search(
            topic=payload.topic,
            language=payload.language,
            iterations=payload.iterations,
            breadth=payload.breadth,
            max_results=payload.max_results,
            persist=persist,
            job_type="discovery_deep",
        )
        complete_job(
            job_id,
            result={
                "results": len(result.get("results", [])),
                "stored": result.get("stored", {}),
            },
        )
        return success_response(result)
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details, meta={"topic": payload.topic, "results": []})


class KeywordGenerationRequest(BaseModel):
    topic: str = Field(..., description="主题或关键词")
    language: str = Field(default="zh", description="关键词语言 zh/en")
    platform: Optional[str] = Field(default=None, description="平台名称（如reddit/twitter），用于社交平台关键词生成")
    base_keywords: Optional[list[str]] = Field(default=None, description="基础关键词列表（可选），用于增强生成")
    topic_focus: Optional[str] = Field(default=None, description="专题焦点 company/product/operation（可选）")


@router.post("/generate-keywords", responses=DISCOVERY_ERROR_RESPONSES)
def generate_keywords_api(payload: KeywordGenerationRequest):
    """Keyword suggestion for collection workflow.

    Uses project customization suggest_keywords when available; otherwise falls back
    to trunk LLM-based generation (social or general).
    """
    import logging
    from ..services.projects.context import current_project_key

    logger = logging.getLogger(__name__)
    project_key = current_project_key()
    logger.info(
        "Keyword suggestion request: project_key=%s, topic=%s, language=%s, platform=%s, base_keywords=%s",
        project_key, payload.topic, payload.language, payload.platform, payload.base_keywords,
    )

    try:
        customization = get_project_customization()
        logger.info(
            "Keyword suggestion: trunk-owned generation (project_key=%s). "
            "Project customization only contributes prompt/guidelines, not generation routing.",
            customization.project_key,
        )
        if payload.platform and payload.platform.strip():
            logger.info("Keyword suggestion: trunk path=social, calling generate_social_keywords")
            keyword_result = generate_social_keywords(
                payload.topic,
                payload.language,
                payload.platform,
                base_keywords=payload.base_keywords,
                return_combined=True,
            )
            if isinstance(keyword_result, dict):
                sw = list(keyword_result.get("search_keywords", []) or [])
                sr = keyword_result.get("subreddit_keywords", [])
                if payload.topic_focus:
                    try:
                        tkw = generate_topic_keywords(
                            payload.topic,
                            topic_focus=payload.topic_focus,
                            language=payload.language,
                            base_keywords=payload.base_keywords or [],
                        ) or {}
                        extra = [str(x).strip() for x in (tkw.get("search_keywords") or []) if str(x).strip()]
                        sw = list(dict.fromkeys([*sw, *extra]))
                    except Exception as topic_exc:  # noqa: BLE001
                        logger.warning("Keyword suggestion topic_focus augment (social) failed: %s", topic_exc)
                logger.info("Keyword suggestion: trunk social result search_keywords=%s subreddit_keywords=%s", sw, sr)
                return success_response({
                    "topic": payload.topic,
                    "language": payload.language,
                    "platform": payload.platform,
                    "topic_focus": payload.topic_focus,
                    "search_keywords": sw,
                    "subreddit_keywords": sr,
                })
            logger.info("Keyword suggestion: trunk social result (list) keywords=%s", keyword_result)
            return success_response({
                "topic": payload.topic,
                "language": payload.language,
                "platform": payload.platform,
                "keywords": keyword_result,
            })

        logger.info("Keyword suggestion: trunk path=general, calling generate_keywords")
        keywords = list(generate_keywords(payload.topic, payload.language) or [])
        if payload.topic_focus:
            try:
                tkw = generate_topic_keywords(
                    payload.topic,
                    topic_focus=payload.topic_focus,
                    language=payload.language,
                    base_keywords=payload.base_keywords or [],
                ) or {}
                extra = [str(x).strip() for x in (tkw.get("search_keywords") or []) if str(x).strip()]
                keywords = list(dict.fromkeys([*keywords, *extra]))
            except Exception as topic_exc:  # noqa: BLE001
                logger.warning("Keyword suggestion topic_focus augment (general) failed: %s", topic_exc)
        logger.info("Keyword suggestion: trunk general result keywords=%s", keywords)
        return success_response({
            "topic": payload.topic,
            "language": payload.language,
            "platform": payload.platform,
            "topic_focus": payload.topic_focus,
            "keywords": keywords,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("Keyword suggestion failed: %s", exc, exc_info=True)
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details, meta={"topic": payload.topic, "keywords": []})


class SubredditKeywordGenerationRequest(BaseModel):
    topic: str = Field(..., description="主题或关键词")
    language: str = Field(default="en", description="关键词语言 zh/en（Reddit子论坛通常使用英文）")
    base_keywords: Optional[list[str]] = Field(default=None, description="基础关键词列表（可选），用于生成更多相关关键词")


@router.post("/generate-subreddit-keywords", responses=DISCOVERY_ERROR_RESPONSES)
def generate_subreddit_keywords_api(payload: SubredditKeywordGenerationRequest):
    """生成Reddit子论坛关键词：基于主题使用LLM生成专门用于发现Reddit子论坛的关键词
    
    这些关键词专门针对Reddit子论坛命名规则优化，适合用于子论坛发现功能。
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Subreddit keyword generation request: topic={payload.topic}, language={payload.language}, base_keywords={payload.base_keywords}")
    
    try:
        keywords = generate_subreddit_keywords(
            topic=payload.topic,
            language=payload.language,
            base_keywords=payload.base_keywords,
        )
        logger.info(f"Subreddit keyword generation result: {len(keywords)} keywords")
        return success_response({
            "topic": payload.topic,
            "language": payload.language,
            "base_keywords": payload.base_keywords,
            "keywords": keywords,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Subreddit keyword generation failed: {exc}", exc_info=True)
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details, meta={"topic": payload.topic, "keywords": []})
