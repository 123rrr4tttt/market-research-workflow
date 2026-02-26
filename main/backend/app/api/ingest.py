from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, DatabaseError
from typing import Optional
import logging
from functools import lru_cache

from ..project_customization import get_project_customization
from ..services.ingest_config import get_config as get_ingest_config, upsert_config as upsert_ingest_config
from ..subprojects.online_lottery.domain.news import DEFAULT_REDDIT_SUBREDDIT
from ..services.job_logger import list_jobs
from ..services.projects import bind_project, current_project_key
from ..contracts import (
    ErrorCode,
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


class IngestConfigUpsertPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project key (optional, fallback to context)")
    config_key: str = Field(..., min_length=1, description="Config key, e.g. social_forum")
    config_type: str = Field(..., min_length=1, description="Config type")
    payload: dict | None = Field(default=None, description="Config payload (JSON)")


@router.get("/config")
def get_ingest_config_endpoint(
    project_key: str | None = Query(default=None),
    config_key: str = Query(..., description="Config key, e.g. social_forum"),
):
    """Get ingest config by project_key and config_key."""
    pk = _require_project_key(project_key)
    data = get_ingest_config(pk, config_key)
    if data is None:
        return JSONResponse(
            status_code=404,
            content=error_response(ErrorCode.NOT_FOUND, f"Config not found: {config_key}"),
        )
    return success_response(data)


@router.post("/config")
def post_ingest_config_endpoint(body: IngestConfigUpsertPayload):
    """Upsert ingest config."""
    pk = (body.project_key or "").strip()
    if not pk:
        pk = (current_project_key() or "").strip()
    if not pk:
        return JSONResponse(
            status_code=400,
            content=error_response(ErrorCode.INVALID_INPUT, "project_key is required"),
        )
    try:
        data = upsert_ingest_config(
            project_key=pk,
            config_key=body.config_key,
            config_type=body.config_type,
            payload=body.payload,
        )
        return success_response(data)
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


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
            from ..services.collect_runtime import collect_request_from_market_api, run_collect
            req = collect_request_from_market_api(
                query_terms=query_terms,
                max_items=max_items,
                project_key=project_key,
                enable_extraction=payload.enable_extraction,
                start_offset=payload.start_offset,
                days_back=payload.days_back,
                language=payload.language or "en",
                provider=payload.provider or "auto",
            )
            cr = run_collect(req)
            return success_response(dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped, "display_meta": cr.display_meta}))
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


def _dispatch_news_resource(resource_id: str, payload: NewsRequest):
    """Dispatch to news resource handler. Effective = shared (总库) + project (子项目库), project overrides."""
    project_key = _require_project_key(payload.project_key)
    customization = get_project_customization(project_key)
    shared = customization.get_shared_news_resource_handlers()
    project_handlers = customization.get_news_resource_handlers()
    handlers = {**shared, **project_handlers}
    handler = handlers.get(resource_id)
    if not handler:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_key}' does not support news resource '{resource_id}'.",
        )
    if payload.async_mode:
        task = _tasks_module().task_collect_news_resource.delay(resource_id, payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"resource_id": resource_id, "limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            return success_response(handler(limit=payload.limit))
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


_NEWS_RESOURCE_DISPLAY_NAMES: dict[str, str] = {
    "calottery": "CA Lottery News",
    "calottery_retailer": "CA Lottery Retailer News",
    "google_news": "Google News",
}


def _resource_display_name(resource_id: str) -> str:
    return _NEWS_RESOURCE_DISPLAY_NAMES.get(resource_id) or resource_id.replace("_", " ").title()


class SourceLibraryRunPayload(BaseModel):
    item_key: str = Field(..., min_length=1)
    project_key: str | None = Field(default=None)
    async_mode: bool = Field(default=False)
    override_params: dict = Field(default_factory=dict)


class SourceLibrarySyncPayload(BaseModel):
    project_key: str | None = Field(default=None)


@router.post("/source-library/run")
def ingest_source_library_run(payload: SourceLibraryRunPayload):
    """Run a source library item (collection task). Entry point for ingest flow."""
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task = _tasks_module().task_run_source_library_item.delay(
            payload.item_key,
            project_key,
            payload.override_params or {},
        )
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"item_key": payload.item_key},
            )
        )
    try:
        from ..services.collect_runtime import run_source_library_item_compat
        result = run_source_library_item_compat(
            item_key=payload.item_key,
            project_key=project_key,
            override_params=payload.override_params or {},
        )
        return success_response(result)
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/source-library/sync")
def ingest_source_library_sync(payload: SourceLibrarySyncPayload):
    """Sync shared source library from files to DB. Entry point for ingest flow."""
    try:
        from ..services.source_library import sync_shared_library_from_files
        result = sync_shared_library_from_files()
        return success_response({"ok": True, **result})
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.get("/news-resources")
def list_news_resources(
    project_key: str | None = Query(default=None),
    scope: str = Query(default="effective", description="shared | project | effective"),
):
    """List available news ingest resources for the project. Effective = shared + project merged."""
    pk = _require_project_key(project_key)
    if scope not in ("shared", "project", "effective"):
        scope = "effective"
    customization = get_project_customization(pk)
    shared = customization.get_shared_news_resource_handlers()
    project_handlers = customization.get_news_resource_handlers()
    items: list[dict] = []
    if scope == "shared":
        for rid in shared:
            items.append({"resource_id": rid, "name": _resource_display_name(rid), "scope": "shared"})
    elif scope == "project":
        for rid in project_handlers:
            items.append({"resource_id": rid, "name": _resource_display_name(rid), "scope": "project"})
    else:
        merged: dict[str, dict] = {}
        for rid in shared:
            merged[rid] = {"resource_id": rid, "name": _resource_display_name(rid), "scope": "shared"}
        for rid in project_handlers:
            merged[rid] = {"resource_id": rid, "name": _resource_display_name(rid), "scope": "project"}
        items = list(merged.values())
    return success_response({"items": items, "scope": scope})


@router.post("/news/calottery")
def ingest_calottery_news(payload: NewsRequest):
    return _dispatch_news_resource("calottery", payload)


@router.post("/news/calottery/retailer")
def ingest_calottery_retailer(payload: NewsRequest):
    return _dispatch_news_resource("calottery_retailer", payload)


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
            from ..services.collect_runtime import collect_request_from_policy_api, run_collect
            req = collect_request_from_policy_api(
                query_terms=query_terms,
                max_items=max_items,
                project_key=project_key,
                enable_extraction=payload.enable_extraction,
                start_offset=payload.start_offset,
                days_back=payload.days_back,
                language=payload.language or "en",
                provider=payload.provider or "auto",
            )
            cr = run_collect(req)
            return success_response(dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped, "display_meta": cr.display_meta}))
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

