"""Resource pool extraction API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..contracts import fail, ok, ok_page, task_result_response
from ..contracts.errors import ErrorCode
from ..services.projects import current_project_key
from ..services.ingest_config import get_config as get_ingest_config
from ..services.resource_pool import (
    classify_site_entry,
    classify_site_entries_batch,
    discover_site_entries_from_urls,
    extract_from_documents,
    extract_from_tasks,
    list_urls,
    list_site_entries,
    simplify_site_entries,
    unified_search_by_item,
    upsert_site_entry,
    upsert_capture_config,
    write_discovered_site_entries,
)

ScopeType = Literal["shared", "project", "effective"]

router = APIRouter(prefix="/resource_pool", tags=["resource_pool"])


def _get_project_key_or_error(project_key: str | None) -> tuple[str | None, JSONResponse | None]:
    key = (project_key or "").strip()
    if not key:
        key = (current_project_key() or "").strip()
    if not key:
        return (
            None,
            JSONResponse(
                status_code=400,
                content=fail(ErrorCode.INVALID_INPUT, "project_key is required. Please select a project first."),
            ),
        )
    return key, None


class ExtractFromDocumentsPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    scope: Literal["project", "shared"] = Field(default="project", description="Write to project or shared pool")
    filters: dict[str, Any] = Field(default_factory=dict)
    async_mode: bool = Field(default=False, description="Run via Celery")


@router.post("/extract/from-documents")
def extract_from_documents_api(payload: ExtractFromDocumentsPayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    filters = payload.filters or {}
    doc_type = filters.get("doc_type")
    state = filters.get("state")
    document_ids = filters.get("document_ids")
    limit = filters.get("limit", 500)
    limit = min(max(1, int(limit)), 5000)

    if payload.async_mode:
        task = _get_tasks_module().task_extract_resource_pool_from_documents.delay(
            project_key=project_key,
            scope=payload.scope,
            doc_type=doc_type,
            state=state,
            document_ids=document_ids,
            limit=limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=task.id,
                    async_mode=True,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    try:
        result = extract_from_documents(
            project_key=project_key,
            scope=payload.scope,
            doc_type=doc_type,
            state=state,
            document_ids=document_ids,
            limit=limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=None,
                    async_mode=False,
                    result=result,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.get("/urls")
def list_urls_api(
    project_key: str | None = Query(default=None),
    scope: ScopeType = Query(default="effective"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: str | None = Query(default=None),
    domain: str | None = Query(default=None),
):
    project_key, error = _get_project_key_or_error(project_key)
    if error:
        return error
    try:
        items, total = list_urls(
            scope=scope,
            project_key=project_key,
            source=source,
            domain=domain,
            page=page,
            page_size=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return JSONResponse(
            status_code=200,
            content=ok_page(
                {"items": items},
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


class CaptureEnablePayload(BaseModel):
    project_key: str | None = Field(default=None)
    scope: Literal["project", "shared"] = Field(default="project")
    job_types: list[str] = Field(..., min_length=1)
    enabled: bool = Field(default=True)


class CaptureFromTasksPayload(BaseModel):
    project_key: str | None = Field(default=None)
    scope: Literal["project", "shared"] = Field(default="project")
    task_ids: list[int] | None = Field(default=None)
    job_type: str | None = Field(default=None)
    since: str | None = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)
    async_mode: bool = Field(default=False)


@router.post("/capture/enable")
def capture_enable_api(payload: CaptureEnablePayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    try:
        result = upsert_capture_config(
            project_key=project_key,
            job_types=payload.job_types,
            scope=payload.scope,
            enabled=payload.enabled,
        )
        return JSONResponse(status_code=200, content=ok(result))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.post("/capture/from-tasks")
def capture_from_tasks_api(payload: CaptureFromTasksPayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    if payload.async_mode:
        task = _get_tasks_module().task_extract_resource_pool_from_tasks.delay(
            project_key=project_key,
            scope=payload.scope,
            task_ids=payload.task_ids,
            job_type=payload.job_type,
            since=payload.since,
            limit=payload.limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=task.id,
                    async_mode=True,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    try:
        result = extract_from_tasks(
            project_key=project_key,
            scope=payload.scope,
            task_ids=payload.task_ids,
            job_type=payload.job_type,
            since=payload.since,
            limit=payload.limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=None,
                    async_mode=False,
                    result=result,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


class UpsertSiteEntryPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier (required for project scope)")
    scope: Literal["project", "shared"] = Field(default="project", description="Write to project or shared pool")
    site_url: str = Field(..., min_length=1, description="Site entry URL (domain_root/rss/sitemap/search template root)")
    entry_type: str = Field(default="domain_root", description="domain_root|rss|sitemap|search_template|official_api")
    template: str | None = Field(default=None, description="Optional template for search_template etc.")
    name: str | None = Field(default=None)
    domain: str | None = Field(default=None)
    capabilities: dict[str, Any] | None = Field(default=None)
    source: str = Field(default="manual")
    source_ref: dict[str, Any] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    enabled: bool = Field(default=True)
    extra: dict[str, Any] | None = Field(default=None)


@router.get("/site_entries", operation_id="resource_pool_list_site_entries")
@router.get("/site-entries", operation_id="resource_pool_list_site_entries_dash")
def list_site_entries_api(
    project_key: str | None = Query(default=None),
    scope: ScopeType = Query(default="effective"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    domain: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
):
    project_key, error = _get_project_key_or_error(project_key)
    if error:
        return error
    try:
        items, total = list_site_entries(
            scope=scope,
            project_key=project_key,
            domain=domain,
            entry_type=entry_type,
            enabled=enabled,
            page=page,
            page_size=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return JSONResponse(
            status_code=200,
            content=ok_page(
                {"items": items},
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


@router.get("/site_entries/grouped", operation_id="resource_pool_group_site_entries")
@router.get("/site-entries/grouped", operation_id="resource_pool_group_site_entries_dash")
def group_site_entries_api(
    project_key: str | None = Query(default=None),
    scope: ScopeType = Query(default="effective"),
    enabled: bool | None = Query(default=True),
):
    project_key, error = _get_project_key_or_error(project_key)
    if error:
        return error
    try:
        page = 1
        page_size = 100
        by_entry_type: dict[str, dict[str, Any]] = {}
        while True:
            items, total = list_site_entries(
                scope=scope,
                project_key=project_key,
                enabled=enabled,
                page=page,
                page_size=page_size,
            )
            for row in items:
                et = str(row.get("entry_type") or "domain_root").strip().lower() or "domain_root"
                bucket = by_entry_type.setdefault(et, {"count": 0, "sample_urls": []})
                bucket["count"] += 1
                su = str(row.get("site_url") or "").strip()
                if su and len(bucket["sample_urls"]) < 5:
                    bucket["sample_urls"].append(su)
            if not items or page * page_size >= int(total or 0):
                break
            page += 1
        return JSONResponse(status_code=200, content=ok({"by_entry_type": by_entry_type, "scope": scope, "project_key": project_key}))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


@router.post("/site_entries", operation_id="resource_pool_upsert_site_entry")
@router.post("/site-entries", operation_id="resource_pool_upsert_site_entry_dash")
def upsert_site_entry_api(payload: UpsertSiteEntryPayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error and payload.scope == "project":
        return error
    try:
        item = upsert_site_entry(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            site_url=payload.site_url,
            entry_type=payload.entry_type,
            template=payload.template,
            name=payload.name,
            domain=payload.domain,
            capabilities=payload.capabilities,
            source=payload.source,
            source_ref=payload.source_ref,
            tags=payload.tags,
            enabled=payload.enabled,
            extra=payload.extra,
        )
        return JSONResponse(status_code=200, content=ok(item))
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


class DiscoverSiteEntriesPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    url_scope: ScopeType = Field(default="effective", description="shared|project|effective, read urls from")
    target_scope: Literal["shared", "project"] = Field(default="project", description="write target scope for site entries")
    domain: str | None = Field(default=None)
    limit_domains: int = Field(default=50, ge=1, le=500)
    probe_timeout: float = Field(default=8.0, ge=1.0, le=60.0)
    include_link_alternate: bool = Field(default=True)
    sitemap_paths: list[str] | None = Field(default=None, description="Optional override paths for sitemap probing")
    rss_paths: list[str] | None = Field(default=None, description="Optional override paths for rss probing")
    allow_domains: list[str] | None = Field(default=None, description="Optional allowlist of domains")
    deny_domains: list[str] | None = Field(default=None, description="Optional denylist of domains")
    dry_run: bool = Field(default=True, description="If true, do not write")
    write: bool = Field(default=False, description="If true, persist discovered candidates")
    run_auto_classify: bool = Field(default=False, description="If true, run classify on domain_root without sitemap/rss")
    use_llm: bool = Field(default=False, description="If true and run_auto_classify, use LLM for classification")
    async_mode: bool = Field(default=False, description="Run discovery in background (Celery)")
    batch_size: int = Field(default=20, ge=1, le=100, description="Domains per batch when async_mode=true")
    simplify_pool_first: bool = Field(default=True, description="Simplify duplicate site entries before async batched discovery")


class SimplifySiteEntriesPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    scope: Literal["project", "shared"] = Field(default="project")
    domain: str | None = Field(default=None, description="Optional domain filter")
    dry_run: bool = Field(default=True, description="Preview only; do not delete duplicates")


@router.post("/discover/site-entries", operation_id="resource_pool_discover_site_entries")
def discover_site_entries_api(payload: DiscoverSiteEntriesPayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    try:
        # Optional: merge ingest_config policy (payload wins)
        policy = (get_ingest_config(project_key, "site_entry_discovery_policy") or {}).get("payload") or {}
        url_scope = payload.url_scope or policy.get("url_scope") or "effective"
        target_scope = payload.target_scope or policy.get("target_scope") or "project"
        limit_domains = payload.limit_domains if payload.limit_domains is not None else int(policy.get("limit_domains") or 50)
        probe_timeout = payload.probe_timeout if payload.probe_timeout is not None else float(policy.get("probe_timeout") or 8.0)
        include_link_alternate = (
            payload.include_link_alternate
            if payload.include_link_alternate is not None
            else bool(policy.get("include_link_alternate", True))
        )
        sitemap_paths = payload.sitemap_paths if payload.sitemap_paths is not None else policy.get("sitemap_paths")
        rss_paths = payload.rss_paths if payload.rss_paths is not None else policy.get("rss_paths")
        allow_domains = payload.allow_domains if payload.allow_domains is not None else policy.get("allow_domains")
        deny_domains = payload.deny_domains if payload.deny_domains is not None else policy.get("deny_domains")
        run_auto_classify = payload.run_auto_classify if payload.run_auto_classify is not None else bool(policy.get("run_auto_classify", False))
        use_llm = payload.use_llm if payload.use_llm is not None else bool(policy.get("use_llm", False))

        if payload.async_mode:
            task = _get_tasks_module().task_discover_site_entries_batched.delay(
                project_key=project_key,
                url_scope=url_scope,
                target_scope=target_scope,
                domain=payload.domain,
                limit_domains=limit_domains,
                probe_timeout=probe_timeout,
                include_link_alternate=include_link_alternate,
                sitemap_paths=sitemap_paths,
                rss_paths=rss_paths,
                allow_domains=allow_domains,
                deny_domains=deny_domains,
                run_auto_classify=run_auto_classify,
                use_llm=use_llm,
                write=bool(payload.write) and not bool(payload.dry_run),
                batch_size=payload.batch_size,
                simplify_pool_first=bool(payload.simplify_pool_first),
            )
            return JSONResponse(
                status_code=200,
                content=ok(
                    task_result_response(
                        task_id=task.id,
                        async_mode=True,
                        params={
                            "project_key": project_key,
                            "url_scope": url_scope,
                            "target_scope": target_scope,
                            "limit_domains": limit_domains,
                            "run_auto_classify": run_auto_classify,
                            "use_llm": use_llm,
                            "batch_size": payload.batch_size,
                            "simplify_pool_first": bool(payload.simplify_pool_first),
                        },
                    )
                ),
            )

        result = discover_site_entries_from_urls(
            project_key=project_key,
            url_scope=url_scope,
            target_scope=target_scope,
            domain=payload.domain,
            limit_domains=limit_domains,
            probe_timeout=probe_timeout,
            include_link_alternate=include_link_alternate,
            sitemap_paths=sitemap_paths,
            rss_paths=rss_paths,
            allow_domains=allow_domains,
            deny_domains=deny_domains,
            run_auto_classify=run_auto_classify,
            use_llm=use_llm,
        )
        write_result = None
        do_write = bool(payload.write) and not bool(payload.dry_run)
        if do_write:
            wr = write_discovered_site_entries(
                project_key=project_key,
                candidates=result.candidates,
                target_scope=target_scope,
                dry_run=False,
            )
            write_result = {
                "upserted": wr.upserted,
                "skipped": wr.skipped,
                "errors": wr.errors,
            }
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "domains_scanned": result.domains_scanned,
                    "candidates_count": len(result.candidates),
                    "probe_stats": result.probe_stats,
                    "errors": result.errors,
                    "write_result": write_result,
                    "candidates": result.candidates,
                }
            ),
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))


@router.post("/site_entries/simplify", operation_id="resource_pool_simplify_site_entries")
def simplify_site_entries_api(payload: SimplifySiteEntriesPayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error and payload.scope == "project":
        return error
    try:
        result = simplify_site_entries(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            domain=payload.domain,
            dry_run=payload.dry_run,
        )
        return JSONResponse(status_code=200, content=ok(result))
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


class RecommendSiteEntryPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    site_url: str = Field(..., min_length=1, description="Site entry URL to classify")
    entry_type: str | None = Field(default=None, description="Optional known entry_type")
    template: str | None = Field(default=None, description="Optional template for search_template")
    use_llm: bool = Field(default=False, description="Whether to call LLM when rules cannot determine")


class BatchRecommendSiteEntriesPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    entries: list[dict[str, Any]] = Field(default_factory=list, description="Rows: {site_url, entry_type?, template?}")
    use_llm: bool = Field(default=True, description="Whether to use LLM for unresolved rows")
    llm_batch_size: int = Field(default=20, ge=1, le=100, description="Batch size for one LLM request")


@router.post("/site_entries/recommend", operation_id="resource_pool_recommend_site_entry")
def recommend_site_entry_api(payload: RecommendSiteEntryPayload):
    """Recommend channel_key and entry_type for a site entry. Rule-first, LLM fallback when use_llm=True."""
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    try:
        rec = classify_site_entry(
            site_url=payload.site_url,
            entry_type=payload.entry_type,
            template=payload.template,
            use_llm=payload.use_llm,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "channel_key": rec.channel_key,
                    "entry_type": rec.entry_type,
                    "template": rec.template,
                    "validated": rec.validated,
                    "source": rec.source,
                    "capabilities": rec.capabilities or {},
                }
            ),
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


@router.post("/site_entries/recommend-batch", operation_id="resource_pool_recommend_site_entries_batch")
def recommend_site_entries_batch_api(payload: BatchRecommendSiteEntriesPayload):
    """Batch recommend channel/entry_type/template (+ capability/symbol-ready hints) for site entries."""
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    try:
        rows = []
        for i, row in enumerate(payload.entries or []):
            if not isinstance(row, dict):
                continue
            site_url = str(row.get("site_url") or "").strip()
            if not site_url:
                continue
            rows.append(
                {
                    "index": i,
                    "site_url": site_url,
                    "entry_type": row.get("entry_type"),
                    "template": row.get("template"),
                }
            )
        result = classify_site_entries_batch(rows, use_llm=payload.use_llm, llm_batch_size=payload.llm_batch_size)
        normalized = [
            {
                "index": item.get("index"),
                "site_url": item.get("site_url"),
                "entry_type": item.get("entry_type"),
                "channel_key": item.get("channel_key"),
                "template": item.get("template"),
                "validated": item.get("validated"),
                "source": item.get("source"),
                "capabilities": item.get("capabilities") or {},
                "symbol_suggestion": item.get("symbol_suggestion"),
            }
            for item in result
        ]
        return JSONResponse(status_code=200, content=ok({"items": normalized, "count": len(normalized)}))
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


class UnifiedSearchPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    item_key: str = Field(..., min_length=1, max_length=128)
    query_terms: list[str] = Field(default_factory=list, description="Search terms (merged into {{q}})")
    max_candidates: int = Field(default=200, ge=1, le=2000)
    probe_timeout: float = Field(default=10.0, ge=1.0, le=60.0)
    write_to_pool: bool = Field(default=False)
    pool_scope: Literal["project", "shared"] = Field(default="project")
    auto_ingest: bool = Field(default=False, description="After write_to_pool, fetch URLs and store as Documents")
    ingest_limit: int = Field(default=10, ge=1, le=50)


@router.post("/unified-search", operation_id="resource_pool_unified_search")
def unified_search_api(payload: UnifiedSearchPayload):
    project_key, error = _get_project_key_or_error(payload.project_key)
    if error:
        return error
    try:
        result = unified_search_by_item(
            project_key=project_key,
            item_key=payload.item_key,
            query_terms=payload.query_terms or [],
            max_candidates=payload.max_candidates,
            write_to_pool=bool(payload.write_to_pool),
            pool_scope=payload.pool_scope,
            probe_timeout=payload.probe_timeout,
            auto_ingest=bool(payload.auto_ingest),
            ingest_limit=payload.ingest_limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "item_key": result.item_key,
                    "query_terms": result.query_terms,
                    "site_entries_used": result.site_entries_used,
                    "candidates": result.candidates,
                    "written": result.written,
                    "ingest_result": result.ingest_result,
                    "errors": result.errors,
                }
            ),
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))


def _get_tasks_module():
    from ..services import tasks as m
    return m
