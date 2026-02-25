from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, DatabaseError
from typing import Optional
import logging
from functools import lru_cache

from ..subprojects.online_lottery.domain.news import DEFAULT_REDDIT_SUBREDDIT
from ..services.job_logger import list_jobs
from ..services.projects import bind_project, current_project_key
from ..contracts import (
    error_response,
    map_exception_to_error,
    success_response,
    task_result_response,
)

logger = logging.getLogger(__name__)
from fastapi.responses import JSONResponse


@lru_cache(maxsize=1)
def _tasks_module():
    from ..services import tasks as tasks_module
    return tasks_module


@lru_cache(maxsize=1)
def _social_ingest_app():
    from ..services.ingest.social_application import SocialIngestApplicationService
    return SocialIngestApplicationService()


def _error_500(exc: Exception) -> JSONResponse:
    code, message, details = map_exception_to_error(exc)
    return JSONResponse(
        status_code=500,
        content=error_response(code, message, details=details),
    )


def _require_project_key(project_key: str | None) -> str:
    # Prefer explicit payload project_key, fallback to request-scoped context
    # injected by middleware from query/header (X-Project-Key / project_key).
    key = (project_key or "").strip()
    if not key:
        key = (current_project_key() or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="project_key is required. Please select a project first.")
    return key


def _normalize_query_terms(
    query_terms: list[str] | None,
    legacy_keywords: list[str] | None,
    *,
    field_name: str = "query_terms",
) -> list[str]:
    raw_terms = query_terms if query_terms is not None else legacy_keywords
    terms = [str(item).strip() for item in (raw_terms or []) if str(item).strip()]
    if not terms:
        raise HTTPException(status_code=400, detail=f"{field_name} is required and cannot be empty.")
    # Preserve order while deduplicating.
    return list(dict.fromkeys(terms))


def _normalize_max_items(
    max_items: int | None,
    legacy_limit: int | None,
    *,
    default_value: int = 20,
    min_value: int = 1,
    max_value: int = 100,
) -> int:
    value = max_items if max_items is not None else legacy_limit
    if value is None:
        value = default_value
    value = int(value)
    return max(min_value, min(max_value, value))


class PolicyIngestRequest(BaseModel):
    state: str = Field(..., description="州，例如 CA")
    source_hint: str | None = Field(default=None, description="可选源标识")
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")
    project_key: str | None = Field(default=None, description="项目标识")


router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/policy")
def ingest_policy(payload: PolicyIngestRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_ingest_policy.delay(payload.state, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"state": payload.state},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.policy import ingest_policy_documents
            return success_response(ingest_policy_documents(payload.state, payload.source_hint))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


class MarketIngestRequest(BaseModel):
    """Generic market info (web search). Project-specific fixed sources use source library."""
    query_terms: list[str] | None = Field(default=None, description="查询词列表")
    keywords: list[str] | None = Field(default=None, description="兼容字段：搜索关键词")
    max_items: int | None = Field(default=None, ge=1, le=100, description="每查询词结果数")
    limit: int | None = Field(default=None, ge=1, le=100, description="兼容字段")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")
    project_key: str | None = Field(default=None, description="项目标识")
    start_offset: int | None = Field(default=None, ge=1, le=91, description="起始偏移(Google CSE: 1=第1条,11=第2页)")
    days_back: int | None = Field(default=None, ge=1, le=365, description="仅搜最近N天")
    language: str | None = Field(default=None, description="语言 en/zh")
    provider: str | None = Field(default=None, description="搜索服务 serper/google/serpstack/serpapi/ddg/auto")


class CaliforniaReportRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=20, description="要保存的 PDF 报告数量上限")


class NewsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="抓取的条数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class RedditRequest(BaseModel):
    subreddit: str = Field(default=DEFAULT_REDDIT_SUBREDDIT, description="子论坛名称")
    limit: int = Field(default=20, ge=1, le=100, description="抓取贴文数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class CommodityRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=365, description="每个指标抓取的历史天数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class EcomPriceRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500, description="最大商品数量")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


@router.post("/market")
def ingest_market(payload: MarketIngestRequest):
    """Generic market info (web search). Project-specific fixed sources use source library."""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords, field_name="query_terms")
    max_items = _normalize_max_items(payload.max_items, payload.limit)
    if payload.async_mode:
        task = _tasks_module().task_ingest_market.delay(
            query_terms,
            max_items,
            payload.enable_extraction,
            project_key,
            payload.start_offset,
            payload.days_back,
            payload.language,
            payload.provider,
        )
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"query_terms": query_terms, "max_items": max_items},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.market_web import collect_market_info
            return success_response(collect_market_info(
                keywords=query_terms,
                limit=max_items,
                enable_extraction=payload.enable_extraction,
                start_offset=payload.start_offset,
                days_back=payload.days_back,
                language=payload.language or "en",
                provider=payload.provider or "auto",
            ))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.get("/history")
def ingest_history(limit: int = 20):
    try:
        return success_response(list_jobs(limit=limit))
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        raise HTTPException(
            status_code=503,
            detail="数据库服务不可用，请检查数据库服务是否已启动。"
        )
    except Exception as e:
        logger.exception("获取历史记录失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="数据库服务不可用，请检查数据库服务是否已启动。"
            )
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {error_msg}")


@router.post("/reports/california")
def ingest_california_reports(payload: CaliforniaReportRequest):
    try:
        from ..services.ingest.reports.california import collect_california_sales_reports
        return success_response(collect_california_sales_reports(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/news/calottery")
def ingest_calottery_news(payload: NewsRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_collect_calottery_news.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..subprojects.online_lottery.services import collect_calottery_news_for_project
            return success_response(collect_calottery_news_for_project(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/news/calottery/retailer")
def ingest_calottery_retailer(payload: NewsRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_collect_calottery_retailer.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..subprojects.online_lottery.services import collect_calottery_retailer_updates_for_project
            return success_response(collect_calottery_retailer_updates_for_project(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/social/reddit")
def ingest_reddit(payload: RedditRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_collect_reddit.delay(payload.subreddit, payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"subreddit": payload.subreddit, "limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.news import collect_reddit_discussions
            return success_response(collect_reddit_discussions(subreddit=payload.subreddit, limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/reports/weekly")
def ingest_weekly_reports(payload: NewsRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_collect_weekly_reports.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.reports.general import collect_weekly_market_reports
            return success_response(collect_weekly_market_reports(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/reports/monthly")
def ingest_monthly_reports(payload: NewsRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_collect_monthly_reports.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.reports.general import collect_monthly_financial_reports
            return success_response(collect_monthly_financial_reports(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


class SocialSentimentRequest(BaseModel):
    query_terms: list[str] | None = Field(default=None, description="统一查询词列表（推荐）")
    keywords: list[str] | None = Field(default=None, description="兼容字段：搜索关键词列表")
    platforms: list[str] = Field(default=["reddit"], description="平台列表（目前支持reddit）")
    max_items: int | None = Field(default=None, ge=1, le=100, description="统一字段：每个查询词的结果数量限制")
    limit: int | None = Field(default=None, ge=1, le=100, description="兼容字段：每个关键词的结果数量限制")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    enable_subreddit_discovery: bool = Field(default=True, description="是否启用子论坛发现功能（自动发现相关子论坛）")
    base_subreddits: Optional[list[str]] = Field(default=None, description="基础子论坛列表（如果为None，使用默认列表）")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class PolicyRegulationRequest(BaseModel):
    query_terms: list[str] | None = Field(default=None, description="统一查询词列表（推荐）")
    keywords: list[str] | None = Field(default=None, description="兼容字段：搜索关键词列表")
    max_items: int | None = Field(default=None, ge=1, le=100, description="统一字段：每个查询词的结果数量限制")
    limit: int | None = Field(default=None, ge=1, le=100, description="兼容字段：每个关键词的结果数量限制")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")
    start_offset: int | None = Field(default=None, ge=1, le=91, description="起始偏移(1=第1条,11=第2页)")
    days_back: int | None = Field(default=None, ge=1, le=365, description="仅搜最近N天")
    language: str | None = Field(default=None, description="语言 en/zh")
    provider: str | None = Field(default=None, description="搜索服务 serper/google/serpstack/serpapi/ddg/auto")


@router.post("/social/sentiment")
def ingest_social_sentiment(payload: SocialSentimentRequest):
    """收集社交媒体情感数据"""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords)
    max_items = _normalize_max_items(payload.max_items, payload.limit)
    if payload.async_mode:
        task = _tasks_module().task_collect_social_sentiment.delay(
            query_terms,
            payload.platforms,
            max_items,
            payload.enable_extraction,
            payload.enable_subreddit_discovery,
            payload.base_subreddits,
            project_key,
        )
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"query_terms": query_terms, "max_items": max_items, "platforms": payload.platforms},
            )
        )
    try:
        with bind_project(project_key):
            return success_response(_social_ingest_app().collect_social_sentiment(
                keywords=query_terms,
                platforms=payload.platforms,
                limit=max_items,
                enable_extraction=payload.enable_extraction,
                enable_subreddit_discovery=payload.enable_subreddit_discovery,
                base_subreddits=payload.base_subreddits,
            ))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/policy/regulation")
def ingest_policy_regulation(payload: PolicyRegulationRequest):
    """收集政策法规相关新闻"""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords)
    max_items = _normalize_max_items(payload.max_items, payload.limit)
    if payload.async_mode:
        task = _tasks_module().task_collect_policy_regulation.delay(
            query_terms,
            max_items,
            payload.enable_extraction,
            project_key,
            payload.start_offset,
            payload.days_back,
            payload.language,
            payload.provider,
        )
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"query_terms": query_terms, "max_items": max_items},
            )
        )
    try:
        with bind_project(project_key):
            return success_response(_social_ingest_app().collect_policy_regulation(
                keywords=query_terms,
                limit=max_items,
                enable_extraction=payload.enable_extraction,
                start_offset=payload.start_offset,
                days_back=payload.days_back,
                language=payload.language or "en",
                provider=payload.provider or "auto",
            ))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/commodity/metrics")
def ingest_commodity(payload: CommodityRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_ingest_commodity_metrics.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.commodity import ingest_commodity_metrics
            return success_response(ingest_commodity_metrics(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/ecom/prices")
def ingest_ecom_prices(payload: EcomPriceRequest):
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_collect_ecom_prices.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.ecom import collect_ecom_price_observations
            return success_response(collect_ecom_price_observations(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


