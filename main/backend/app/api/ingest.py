from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, DatabaseError
from typing import Any, Literal, Optional
import logging
import hashlib
from functools import lru_cache

from ..project_customization import get_project_customization
from ..services.ingest_config import get_config as get_ingest_config, upsert_config as upsert_ingest_config
from ..services.job_logger import list_jobs
from ..services.projects import bind_project, current_project_key
from ..settings.config import settings
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


def _expand_query_terms_with_topic_focus(
    query_terms: list[str],
    *,
    topic_focus: str | None,
    language: str | None,
) -> tuple[list[str], dict]:
    focus = str(topic_focus or "").strip().lower()
    if focus not in {"company", "product", "operation"}:
        return query_terms, {}
    try:
        from ..services.search.web import generate_topic_keywords
        topic = " ".join(query_terms[:4]).strip() or (query_terms[0] if query_terms else "")
        kw = generate_topic_keywords(
            topic,
            topic_focus=focus,
            language=language or "zh",
            base_keywords=query_terms,
        )
        extra = [str(x).strip() for x in (kw.get("search_keywords") or []) if str(x).strip()]
        merged = list(dict.fromkeys([*query_terms, *extra]))
        return merged, {"topic_focus": focus, "topic_hints": kw.get("topic_hints") or [], "topic_search_keywords": extra}
    except Exception as exc:  # noqa: BLE001
        logger.warning("topic keyword expansion failed focus=%s err=%s", focus, exc)
        return query_terms, {}


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
    topic_focus: str | None = Field(default=None, description="专题焦点 company/product/operation（可选）")


class CaliforniaReportRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=20, description="要保存的 PDF 报告数量上限")


class NewsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="抓取的条数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class RedditRequest(BaseModel):
    subreddit: str = Field(default_factory=lambda: settings.default_reddit_subreddit, description="子论坛名称")
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
    query_terms, topic_meta = _expand_query_terms_with_topic_focus(
        query_terms, topic_focus=payload.topic_focus, language=payload.language or "en"
    )
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
                params={"query_terms": query_terms, "max_items": max_items, **({"topic_focus": payload.topic_focus} if payload.topic_focus else {})},
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
            raw = dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped, "display_meta": cr.display_meta})
            if topic_meta:
                raw["topic_focus"] = topic_meta.get("topic_focus")
                raw["topic_hints"] = topic_meta.get("topic_hints") or []
                raw["topic_search_keywords"] = topic_meta.get("topic_search_keywords") or []
            return success_response(raw)
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
    "google_news": "Google News",
}


def _resource_display_name(resource_id: str) -> str:
    return _NEWS_RESOURCE_DISPLAY_NAMES.get(resource_id) or resource_id.replace("_", " ").title()


class SourceLibraryRunPayload(BaseModel):
    item_key: str | None = Field(default=None, min_length=1)
    handler_key: str | None = Field(default=None, min_length=1, description="Run all items under this handler key (provider/kind)")
    project_key: str | None = Field(default=None)
    async_mode: bool = Field(default=False)
    override_params: dict = Field(default_factory=dict)


class SourceLibrarySyncPayload(BaseModel):
    project_key: str | None = Field(default=None)


def _ensure_handler_cluster_item(*, project_key: str, handler_key: str) -> tuple[str, int]:
    from .source_library import SourceLibraryItemUpsertPayload, upsert_project_item
    from ..services.resource_pool import list_site_entries

    hk = str(handler_key or "").strip().lower()
    if not hk:
        raise HTTPException(status_code=400, detail="handler_key is required")
    if hk == "url_routing":
        raise HTTPException(
            status_code=400,
            detail="handler_key=url_routing is item-level URL routing, not a URL-entry(entry_type) cluster. Use item_key to run url_routing items.",
        )

    page = 1
    page_size = 200
    site_entries: list[str] = []
    while True:
        rows, total = list_site_entries(
            scope="effective",
            project_key=project_key,
            entry_type=hk,
            enabled=True,
            page=page,
            page_size=page_size,
        )
        for r in rows:
            u = str(r.get("site_url") or "").strip()
            if u and u not in site_entries:
                site_entries.append(u)
        if not rows or page * page_size >= int(total or 0):
            break
        page += 1

    if not site_entries:
        raise HTTPException(status_code=404, detail=f"No enabled site_entries found for handler_key={hk}")

    item_key = f"handler.cluster.{hk}"
    payload = SourceLibraryItemUpsertPayload(
        item_key=item_key,
        name=f"Handler Cluster {hk}",
        channel_key="handler.cluster",
        description=f"Stable handler-cluster item generated from resource_pool.site_entries entry_type={hk}",
        params={
            "site_entries": site_entries,
            "expected_entry_type": hk,
        },
        tags=["handler_cluster", hk],
        enabled=True,
        extra={
            "creation_handler": "handler.entry_type",
            "expected_entry_type": hk,
            "stable_handler_cluster": True,
        },
    )
    upsert_project_item(payload, project_key=project_key)
    return item_key, len(site_entries)


@router.post("/source-library/run")
def ingest_source_library_run(payload: SourceLibraryRunPayload):
    """Run a source library item (collection task). Entry point for ingest flow."""
    project_key = _require_project_key(payload.project_key)
    item_key = str(payload.item_key or "").strip()
    handler_key = str(payload.handler_key or "").strip()
    if not item_key and not handler_key:
        raise HTTPException(status_code=400, detail="item_key or handler_key is required.")
    if item_key and handler_key:
        raise HTTPException(status_code=400, detail="item_key and handler_key are mutually exclusive.")

    if handler_key:
        try:
            item_key, site_entry_count = _ensure_handler_cluster_item(project_key=project_key, handler_key=handler_key)
            payload.override_params = dict(payload.override_params or {})
            payload.override_params.setdefault("_handler_key", handler_key)
            payload.override_params.setdefault("_handler_site_entry_count", site_entry_count)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            return _error_500(exc)

    if payload.async_mode:
        task = _tasks_module().task_run_source_library_item.delay(
            item_key,
            project_key,
            payload.override_params or {},
        )
        return success_response(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"item_key": item_key},
            )
        )
    try:
        from ..services.collect_runtime import run_source_library_item_compat
        result = run_source_library_item_compat(
            item_key=item_key,
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


@router.post("/news/resource/{resource_id}")
def ingest_news_resource(resource_id: str, payload: NewsRequest):
    """Generic project news resource entrypoint."""
    return _dispatch_news_resource(resource_id, payload)


@router.post("/subprojects/{subproject_key}/news/{resource_id}")
def ingest_subproject_news_resource(subproject_key: str, resource_id: str, payload: NewsRequest):
    """Subproject-scoped news resource entrypoint."""
    route_project_key = (subproject_key or "").strip()
    if not route_project_key:
        raise HTTPException(status_code=400, detail="subproject_key is required")
    body_project_key = (payload.project_key or "").strip()
    if body_project_key and body_project_key != route_project_key:
        raise HTTPException(status_code=400, detail="project_key in body must match subproject_key in path")
    scoped_payload = payload.model_copy(update={"project_key": route_project_key})
    return _dispatch_news_resource(resource_id, scoped_payload)


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
    topic_focus: str | None = Field(default=None, description="专题焦点 company/product/operation（可选）")


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
    topic_focus: str | None = Field(default=None, description="专题焦点 company/product/operation（可选）")


class GraphStructuredSelectedNode(BaseModel):
    type: str = Field(..., description="节点类型")
    id: str | None = Field(default=None, description="兼容字段：节点ID")
    entry_id: str | None = Field(default=None, description="节点入口ID（优先）")
    label: str = Field(..., description="节点标签")
    topic_focus: str | None = Field(default=None, description="可选专题焦点 company/product/operation/general")


class GraphStructuredDashboardParams(BaseModel):
    language: str | None = Field(default="en", description="语言 en/zh")
    provider: str | None = Field(default="auto", description="搜索服务 serper/google/serpstack/serpapi/ddg/auto")
    max_items: int | None = Field(default=20, ge=1, le=100, description="每批每关键词结果数")
    start_offset: int | None = Field(default=None, ge=1, le=91, description="起始偏移(1=第1条,11=第2页)")
    days_back: int | None = Field(default=None, ge=1, le=365, description="仅搜最近N天")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    async_mode: bool = Field(default=False, description="是否异步执行")
    platforms: list[str] = Field(default=["reddit"], description="社媒平台列表")
    enable_subreddit_discovery: bool = Field(default=True, description="是否启用子论坛发现")
    base_subreddits: Optional[list[str]] = Field(default=None, description="基础子论坛列表")
    project_key: str | None = Field(default=None, description="项目标识")


class GraphStructuredSearchRequest(BaseModel):
    selected_nodes: list[GraphStructuredSelectedNode] = Field(default_factory=list, description="图谱选中节点")
    dashboard: GraphStructuredDashboardParams = Field(default_factory=GraphStructuredDashboardParams, description="采集面板参数")
    llm_assist: bool = Field(default=False, description="是否使用 LLM 扩展关键词")
    flow_type: Literal["collect", "source_collect"] = Field(default="collect", description="执行流类型")
    intent_mode: Literal["keyword", "keyword_llm"] | None = Field(default=None, description="意图模式（未传时兼容 llm_assist）")


_SOCIAL_NODE_TYPES = {"post", "keyword", "topic", "sentimenttag", "user", "subreddit", "social"}
_MARKET_NODE_TYPES = {"market", "marketdata", "segment", "company", "product", "operation"}
_POLICY_NODE_TYPES = {"policy", "policytype", "keypoint"}
_SHARED_NODE_TYPES = {"entity", "state"}
_COMPANY_HINTS = ("company", "enterprise", "organization", "brand", "vendor", "supplier", "corp", "inc", "公司", "企业", "品牌", "厂商", "供应商")
_PRODUCT_HINTS = ("product", "item", "sku", "model", "segment", "game", "产品", "商品", "品类", "型号", "游戏")
_OPERATION_HINTS = ("operation", "operations", "channel", "sales", "logistics", "retail", "market", "region", "state", "运营", "渠道", "销售", "物流", "门店", "市场", "地区", "州")


def _normalize_graph_label(node: GraphStructuredSelectedNode) -> str:
    label = str(node.label or "").strip()
    if label:
        return label
    nid = _entry_id_of(node)
    if nid:
        return nid
    return str(node.type or "").strip()


def _entry_id_of(node: GraphStructuredSelectedNode) -> str:
    entry_id = str(node.entry_id or "").strip()
    if entry_id:
        return entry_id
    return str(node.id or "").strip()


def _classify_node_batch_types(node: GraphStructuredSelectedNode) -> list[str]:
    nt = str(node.type or "").strip().lower()
    if nt in _POLICY_NODE_TYPES:
        return ["policy"]
    if nt in _SOCIAL_NODE_TYPES:
        return ["social"]
    if nt in _MARKET_NODE_TYPES:
        return ["market"]
    if nt in _SHARED_NODE_TYPES:
        return ["policy", "market"]
    return ["market"]


def _infer_market_topic_focus(node: GraphStructuredSelectedNode) -> str:
    explicit = str(node.topic_focus or "").strip().lower()
    if explicit in {"company", "product", "operation", "general"}:
        return explicit
    text = f"{node.type} {node.label}".lower()
    if any(h in text for h in _COMPANY_HINTS):
        return "company"
    if any(h in text for h in _PRODUCT_HINTS):
        return "product"
    if any(h in text for h in _OPERATION_HINTS):
        return "operation"
    return "general"


def _unique_terms(terms: list[str]) -> list[str]:
    return list(dict.fromkeys([str(t).strip() for t in terms if str(t).strip()]))


def _normalize_batch_token(value: str, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    out = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "_" for ch in text)
    out = out.strip("_")
    return out or fallback


def _resolve_intent_mode(payload: GraphStructuredSearchRequest) -> Literal["keyword", "keyword_llm"]:
    mode = str(payload.intent_mode or "").strip().lower()
    if mode == "keyword":
        return "keyword"
    if mode == "keyword_llm":
        return "keyword_llm"
    return "keyword_llm" if payload.llm_assist else "keyword"


def _collect_intents_for_node(node: GraphStructuredSelectedNode) -> list[dict[str, str]]:
    intents: list[dict[str, str]] = []
    for batch_type in _classify_node_batch_types(node):
        if batch_type == "market":
            focus = _infer_market_topic_focus(node)
            intents.append(
                {
                    "batch_type": "market",
                    "intent": f"market_{focus}",
                    "topic_focus": focus,
                }
            )
            continue
        intents.append({"batch_type": batch_type, "intent": batch_type})
    return intents


def _run_policy_batch(
    *,
    project_key: str,
    query_terms: list[str],
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str = "policy",
) -> dict[str, Any]:
    terms = _unique_terms(query_terms)
    topic_meta: dict[str, Any] = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=None,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    if dashboard.async_mode:
        task = _tasks_module().task_collect_policy_regulation.delay(
            terms,
            max_items,
            dashboard.enable_extraction,
            project_key,
            dashboard.start_offset,
            dashboard.days_back,
            dashboard.language,
            dashboard.provider,
        )
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "policy",
            "query_terms": terms,
            "task_id": task.id,
            "async_mode": True,
            **({"topic_meta": topic_meta} if topic_meta else {}),
        }

    with bind_project(project_key):
        from ..services.collect_runtime import collect_request_from_policy_api, run_collect

        req = collect_request_from_policy_api(
            query_terms=terms,
            max_items=max_items,
            project_key=project_key,
            enable_extraction=dashboard.enable_extraction,
            start_offset=dashboard.start_offset,
            days_back=dashboard.days_back,
            language=dashboard.language or "en",
            provider=dashboard.provider or "auto",
        )
        cr = run_collect(req)
        raw = dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped, "display_meta": cr.display_meta})
        if topic_meta:
            raw["topic_meta"] = topic_meta
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "policy",
            "query_terms": terms,
            "async_mode": False,
            "result": raw,
        }


def _run_social_batch(
    *,
    project_key: str,
    query_terms: list[str],
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str = "social",
) -> dict[str, Any]:
    terms = _unique_terms(query_terms)
    topic_meta: dict[str, Any] = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=None,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    if dashboard.async_mode:
        task = _tasks_module().task_collect_social_sentiment.delay(
            terms,
            dashboard.platforms,
            max_items,
            dashboard.enable_extraction,
            dashboard.enable_subreddit_discovery,
            dashboard.base_subreddits,
            project_key,
        )
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "social",
            "query_terms": terms,
            "platforms": dashboard.platforms,
            "task_id": task.id,
            "async_mode": True,
            **({"topic_meta": topic_meta} if topic_meta else {}),
        }

    with bind_project(project_key):
        result = _social_ingest_app().collect_social_sentiment(
            keywords=terms,
            platforms=dashboard.platforms,
            limit=max_items,
            enable_extraction=dashboard.enable_extraction,
            enable_subreddit_discovery=dashboard.enable_subreddit_discovery,
            base_subreddits=dashboard.base_subreddits,
        )
        if isinstance(result, dict) and topic_meta:
            result.setdefault("topic_meta", topic_meta)
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "social",
            "query_terms": terms,
            "platforms": dashboard.platforms,
            "async_mode": False,
            "result": result,
        }


def _run_market_batch(
    *,
    project_key: str,
    query_terms: list[str],
    topic_focus: str,
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str | None = None,
) -> dict[str, Any]:
    terms = _unique_terms(query_terms)
    topic_meta: dict[str, Any] = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=topic_focus,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    final_batch_id = batch_id or f"market:{topic_focus}"
    if dashboard.async_mode:
        task = _tasks_module().task_ingest_market.delay(
            terms,
            max_items,
            dashboard.enable_extraction,
            project_key,
            dashboard.start_offset,
            dashboard.days_back,
            dashboard.language,
            dashboard.provider,
        )
        return {
            "batch_id": final_batch_id,
            "batch_name": final_batch_id,
            "type": "market",
            "topic_focus": topic_focus,
            "query_terms": terms,
            "task_id": task.id,
            "async_mode": True,
            **({"topic_meta": topic_meta} if topic_meta else {}),
        }

    with bind_project(project_key):
        from ..services.collect_runtime import collect_request_from_market_api, run_collect

        req = collect_request_from_market_api(
            query_terms=terms,
            max_items=max_items,
            project_key=project_key,
            enable_extraction=dashboard.enable_extraction,
            start_offset=dashboard.start_offset,
            days_back=dashboard.days_back,
            language=dashboard.language or "en",
            provider=dashboard.provider or "auto",
        )
        cr = run_collect(req)
        raw = dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped, "display_meta": cr.display_meta})
        if topic_meta:
            raw["topic_meta"] = topic_meta
        return {
            "batch_id": final_batch_id,
            "batch_name": final_batch_id,
            "type": "market",
            "topic_focus": topic_focus,
            "query_terms": terms,
            "async_mode": False,
            "result": raw,
        }


def _run_source_collect_batch(
    *,
    project_key: str,
    entry_id: str,
    intent: str,
    query_terms: list[str],
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str,
) -> dict[str, Any]:
    terms = _unique_terms(query_terms)
    topic_meta: dict[str, Any] = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=None,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    normalized_entry_id = _normalize_batch_token(entry_id, fallback="unknown")
    normalized_intent = _normalize_batch_token(intent, fallback="general")
    # Append a short hash to avoid collisions after token normalization.
    fingerprint = hashlib.sha1(f"{entry_id}::{intent}".encode("utf-8")).hexdigest()[:8]
    item_key = f"graph::{normalized_entry_id}::{normalized_intent}::{fingerprint}"

    from .source_library import SourceLibraryItemUpsertPayload, upsert_project_item
    from ..services.source_library import list_effective_items
    from ..services.collect_runtime import run_source_library_item_compat

    with bind_project(project_key):
        existing = list_effective_items(scope="effective", project_key=project_key)
        existed_before = any(str(item.get("item_key") or "").strip() == item_key for item in existing if isinstance(item, dict))
        upsert_project_item(
            SourceLibraryItemUpsertPayload(
                item_key=item_key,
                name=f"Graph Source {normalized_entry_id} {normalized_intent}",
                channel_key="url_pool",
                description="Graph structured-search generated source_collect item.",
                params={
                    "query_terms": terms,
                    "keywords": terms,
                    "limit": max_items,
                    "scope": "effective",
                },
                tags=["graph_structured", normalized_entry_id, normalized_intent],
                enabled=True,
                extra={
                    "generated_by": "graph_structured_search",
                    "entry_id": normalized_entry_id,
                    "intent": normalized_intent,
                    "flow_type": "source_collect",
                },
            ),
            project_key=project_key,
        )
        override_params = {
            "query_terms": terms,
            "keywords": terms,
            "limit": max_items,
            "scope": "effective",
            "provider": dashboard.provider or "auto",
            "language": dashboard.language or "en",
            "enable_extraction": dashboard.enable_extraction,
        }
        if dashboard.async_mode:
            task = _tasks_module().task_run_source_library_item.delay(
                item_key,
                project_key,
                override_params,
            )
            return {
                "batch_id": batch_id,
                "batch_name": batch_id,
                "type": "source_collect",
                "entry_id": entry_id,
                "intent": intent,
                "item_key": item_key,
                "query_terms": terms,
                "task_id": task.id,
                "async_mode": True,
                "result": {
                    "sources_inserted": 0,
                    "sources_updated": 0,
                    "skipped": 0,
                    "errors": [],
                    "item_inserted": 0 if existed_before else 1,
                    "item_updated": 1 if existed_before else 0,
                    "bootstrap_required": False,
                    "warnings": [],
                },
                **({"topic_meta": topic_meta} if topic_meta else {}),
            }

        run_result = run_source_library_item_compat(
            item_key=item_key,
            project_key=project_key,
            override_params=override_params,
        )

    nested = run_result.get("result") if isinstance(run_result, dict) else {}
    errors = nested.get("errors") if isinstance(nested, dict) else []
    sources_inserted = int((nested or {}).get("inserted") or 0)
    sources_updated = int((nested or {}).get("updated") or 0)
    skipped = int((nested or {}).get("skipped") or 0)
    has_errors = isinstance(errors, list) and any(str(e or "").strip() for e in errors)
    bootstrap_required = (sources_inserted + sources_updated == 0) and not has_errors
    warnings: list[str] = []
    if bootstrap_required:
        warnings.append("No source candidates produced. Bootstrap URL pool or source templates, then retry source_collect.")
    return {
        "batch_id": batch_id,
        "batch_name": batch_id,
        "type": "source_collect",
        "entry_id": entry_id,
        "intent": intent,
        "item_key": item_key,
        "query_terms": terms,
        "async_mode": False,
        "result": {
            "sources_inserted": sources_inserted,
            "sources_updated": sources_updated,
            "skipped": skipped,
            "errors": errors if isinstance(errors, list) else [str(errors)],
            "item_inserted": 0 if existed_before else 1,
            "item_updated": 1 if existed_before else 0,
            "bootstrap_required": bootstrap_required,
            "warnings": warnings,
        },
        **({"topic_meta": topic_meta} if topic_meta else {}),
    }


@router.post("/social/sentiment")
def ingest_social_sentiment(payload: SocialSentimentRequest):
    """收集社交媒体情感数据"""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords)
    query_terms, topic_meta = _expand_query_terms_with_topic_focus(
        query_terms, topic_focus=payload.topic_focus, language="en"
    )
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
                params={"query_terms": query_terms, "max_items": max_items, "platforms": payload.platforms, **({"topic_focus": payload.topic_focus} if payload.topic_focus else {})},
            )
        )
    try:
        with bind_project(project_key):
            result = _social_ingest_app().collect_social_sentiment(
                keywords=query_terms,
                platforms=payload.platforms,
                limit=max_items,
                enable_extraction=payload.enable_extraction,
                enable_subreddit_discovery=payload.enable_subreddit_discovery,
                base_subreddits=payload.base_subreddits,
            )
            if isinstance(result, dict) and topic_meta:
                result.setdefault("topic_focus", topic_meta.get("topic_focus"))
                result.setdefault("topic_hints", topic_meta.get("topic_hints") or [])
                result.setdefault("topic_search_keywords", topic_meta.get("topic_search_keywords") or [])
            return success_response(result)
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/graph/structured-search")
def ingest_graph_structured_search(payload: GraphStructuredSearchRequest):
    project_key = _require_project_key(payload.dashboard.project_key)
    if not payload.selected_nodes:
        raise HTTPException(status_code=400, detail="selected_nodes is required and cannot be empty.")
    flow_type = str(payload.flow_type or "collect").strip().lower()
    if flow_type not in {"collect", "source_collect"}:
        raise HTTPException(status_code=400, detail="flow_type must be collect or source_collect.")
    intent_mode = _resolve_intent_mode(payload)
    llm_assist = intent_mode == "keyword_llm"

    grouped_intents: dict[tuple[str, str, str], dict[str, Any]] = {}
    for node in payload.selected_nodes:
        entry_id = _entry_id_of(node)
        if not entry_id:
            continue
        label = _normalize_graph_label(node)
        if not label:
            continue
        for spec in _collect_intents_for_node(node):
            key = (entry_id, str(spec.get("intent") or "").strip(), str(spec.get("batch_type") or "").strip())
            current = grouped_intents.get(key)
            if current is None:
                grouped_intents[key] = {
                    "entry_id": entry_id,
                    "intent": key[1],
                    "batch_type": key[2],
                    "topic_focus": spec.get("topic_focus"),
                    "terms": [label],
                }
            else:
                current["terms"] = _unique_terms([*(current.get("terms") or []), label])

    if not grouped_intents:
        raise HTTPException(status_code=400, detail="selected_nodes does not contain usable labels.")

    batches: list[dict[str, Any]] = []
    batch_seq: dict[tuple[str, str, str], int] = {}
    try:
        ordered_specs = sorted(grouped_intents.values(), key=lambda x: (str(x.get("entry_id")), str(x.get("intent")), str(x.get("batch_type"))))
        for spec in ordered_specs:
            entry_id = str(spec.get("entry_id") or "").strip()
            intent = str(spec.get("intent") or "").strip() or "general"
            batch_type = str(spec.get("batch_type") or "").strip()
            terms = _unique_terms(spec.get("terms") or [])
            if not entry_id or not terms:
                continue
            key = (flow_type, entry_id, intent)
            batch_seq[key] = batch_seq.get(key, 0) + 1
            batch_id = f"{_normalize_batch_token(flow_type, fallback='collect')}:{_normalize_batch_token(entry_id, fallback='unknown')}:{_normalize_batch_token(intent, fallback='general')}:b{batch_seq[key]}"
            if flow_type == "source_collect":
                batches.append(
                    _run_source_collect_batch(
                        project_key=project_key,
                        entry_id=entry_id,
                        intent=intent,
                        query_terms=terms,
                        dashboard=payload.dashboard,
                        llm_assist=llm_assist,
                        batch_id=batch_id,
                    )
                )
                continue
            if batch_type == "policy":
                batches.append(
                    _run_policy_batch(
                        project_key=project_key,
                        query_terms=terms,
                        dashboard=payload.dashboard,
                        llm_assist=llm_assist,
                        batch_id=batch_id,
                    )
                )
            elif batch_type == "social":
                batches.append(
                    _run_social_batch(
                        project_key=project_key,
                        query_terms=terms,
                        dashboard=payload.dashboard,
                        llm_assist=llm_assist,
                        batch_id=batch_id,
                    )
                )
            elif batch_type == "market":
                batches.append(
                    _run_market_batch(
                        project_key=project_key,
                        query_terms=terms,
                        topic_focus=str(spec.get("topic_focus") or "general"),
                        dashboard=payload.dashboard,
                        llm_assist=llm_assist,
                        batch_id=batch_id,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)

    type_counts: dict[str, int] = {"policy": 0, "social": 0, "market": 0, "source_collect": 0}
    for batch in batches:
        bt = str(batch.get("type") or "").strip().lower()
        if bt in type_counts:
            type_counts[bt] += 1

    summary: dict[str, Any] = {
        "selected_node_count": len(payload.selected_nodes),
        "batch_count": len(batches),
        "async_mode": payload.dashboard.async_mode,
        "llm_assist": llm_assist,
        "flow_type": flow_type,
        "intent_mode": intent_mode,
        "types": {
            "policy": type_counts["policy"],
            "social": type_counts["social"],
            "market": type_counts["market"],
            "source_collect": type_counts["source_collect"],
        },
    }
    accepted = len(batches)
    queued = sum(1 for b in batches if b.get("task_id"))
    failed = 0
    for batch in batches:
        result = batch.get("result") if isinstance(batch, dict) else None
        if isinstance(result, dict):
            errs = result.get("errors")
            if isinstance(errs, list) and any(str(e or "").strip() for e in errs):
                failed += 1
    summary["accepted"] = accepted
    summary["queued"] = queued
    summary["failed"] = failed
    if payload.dashboard.async_mode:
        summary["task_count"] = queued

    return success_response(
        {
            "flow_type": flow_type,
            "intent_mode": intent_mode,
            "batches": batches,
            "summary": summary,
        }
    )


@router.post("/policy/regulation")
def ingest_policy_regulation(payload: PolicyRegulationRequest):
    """收集政策法规相关新闻"""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords)
    query_terms, topic_meta = _expand_query_terms_with_topic_focus(
        query_terms, topic_focus=payload.topic_focus, language=payload.language or "en"
    )
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
                params={"query_terms": query_terms, "max_items": max_items, **({"topic_focus": payload.topic_focus} if payload.topic_focus else {})},
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
            raw = dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped, "display_meta": cr.display_meta})
            if topic_meta:
                raw["topic_focus"] = topic_meta.get("topic_focus")
                raw["topic_hints"] = topic_meta.get("topic_hints") or []
                raw["topic_search_keywords"] = topic_meta.get("topic_search_keywords") or []
            return success_response(raw)
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
