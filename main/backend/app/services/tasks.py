from __future__ import annotations

from importlib import import_module
from contextlib import nullcontext
from math import ceil
from typing import Any

from ..celery_app import celery_app
from ..models.base import SessionLocal
from ..models.entities import EtlJobRun
from .projects import bind_project

_social_ingest_app = None
_indexing_app = None


def _get_social_ingest_app():
    global _social_ingest_app
    if _social_ingest_app is None:
        from .ingest.social_application import SocialIngestApplicationService

        _social_ingest_app = SocialIngestApplicationService()
    return _social_ingest_app


def _get_indexing_app():
    global _indexing_app
    if _indexing_app is None:
        from .indexer.application import IndexingApplicationService

        _indexing_app = IndexingApplicationService()
    return _indexing_app


def _normalize_crawler_response(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "__dict__"):
        return {k: v for k, v in vars(payload).items() if not k.startswith("_")}
    return {"raw": payload}


def _map_provider_status(status: str | None, default: str = "running") -> str:
    value = str(status or "").strip().lower()
    if value in {"queued", "accepted", "running", "started", "processing", "retry"}:
        return "running"
    if value in {"completed", "finished", "success", "successful", "done"}:
        return "completed"
    if value in {"failed", "failure", "error", "cancelled", "canceled"}:
        return "failed"
    return default


def _map_control_status(status: str | None, default: str = "running") -> str:
    value = str(status or "").strip().lower()
    if value in {"ok", "completed", "finished", "done", "success", "successful"}:
        return "completed"
    if value in {"queued", "accepted", "running", "started", "processing", "retry"}:
        return "running"
    if value in {"failed", "failure", "error", "cancelled", "canceled"}:
        return "failed"
    return default


def _load_crawlers_bridge_api():
    try:
        module = import_module(".crawlers.bridge", package=__package__)
    except Exception:
        module = None

    submit_fn = getattr(module, "submit_crawler_job", None) if module else None
    poll_fn = getattr(module, "poll_crawler_job", None) if module else None
    if callable(submit_fn) and callable(poll_fn):
        return submit_fn, poll_fn

    from .crawlers.base import CrawlerDispatchRequest
    from .crawlers.registry import get_provider

    def _fallback_submit(**payload: Any) -> dict[str, Any]:
        provider_key = str(payload.get("provider") or payload.get("external_provider") or "").strip()
        provider = get_provider(provider_key)
        if not provider:
            raise ValueError(f"crawler provider is not registered: {provider_key}")
        request = CrawlerDispatchRequest(
            provider=provider_key,
            project=str(payload.get("project") or ""),
            spider=str(payload.get("spider") or ""),
            arguments=dict(payload.get("arguments") or {}),
            settings=dict(payload.get("settings") or {}),
            version=payload.get("version"),
            priority=payload.get("priority"),
            job_id=payload.get("external_job_id"),
        )
        result = provider.dispatch(request)
        return {
            "provider_status": result.provider_status,
            "provider_job_id": result.provider_job_id,
            "provider_type": result.provider_type,
            "attempt_count": result.attempt_count,
            "raw": result.raw,
        }

    def _fallback_poll(**payload: Any) -> dict[str, Any]:
        provider_key = str(payload.get("external_provider") or payload.get("provider") or "").strip()
        provider = get_provider(provider_key)
        if not provider:
            raise ValueError(f"crawler provider is not registered: {provider_key}")
        poll_fn_local = getattr(provider, "poll", None)
        if not callable(poll_fn_local):
            raise ValueError(f"crawler provider does not support poll(): {provider_key}")
        result = poll_fn_local(
            external_job_id=payload.get("external_job_id"),
            project=payload.get("project"),
            spider=payload.get("spider"),
            options=dict(payload.get("options") or {}),
        )
        return _normalize_crawler_response(result)

    return _fallback_submit, _fallback_poll


def _load_db_job_tracking(job_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(EtlJobRun, int(job_id))
        if not row:
            return {}
        return {
            "external_provider": row.external_provider,
            "external_job_id": row.external_job_id,
            "retry_count": row.retry_count,
            "status": row.status,
            "params": dict(row.params or {}),
        }


@celery_app.task
def task_ingest_policy(state: str, project_key: str | None = None) -> dict:
    from .ingest.policy import ingest_policy_documents

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return ingest_policy_documents(state=state)


@celery_app.task
def task_ingest_market(
    query_terms: list[str],
    max_items: int = 20,
    enable_extraction: bool = True,
    project_key: str | None = None,
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str | None = None,
    provider: str | None = None,
) -> dict:
    from .collect_runtime import collect_request_from_market_api, run_collect

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        req = collect_request_from_market_api(
            query_terms=query_terms,
            max_items=max_items,
            project_key=project_key,
            start_offset=start_offset,
            days_back=days_back,
            language=language or "en",
            provider=provider or "auto",
            enable_extraction=enable_extraction,
        )
        cr = run_collect(req)
        return dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped})


@celery_app.task
def task_index_policy(document_ids: list[int], project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _get_indexing_app().index_policy(document_ids=document_ids)


@celery_app.task
def task_collect_calottery_news(limit: int = 10, project_key: str | None = None) -> dict:
    from ..subprojects.online_lottery.services import collect_calottery_news_for_project

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_calottery_news_for_project(limit=limit)


@celery_app.task
def task_collect_calottery_retailer(limit: int = 10, project_key: str | None = None) -> dict:
    from ..subprojects.online_lottery.services import collect_calottery_retailer_updates_for_project

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_calottery_retailer_updates_for_project(limit=limit)


@celery_app.task
def task_collect_news_resource(
    resource_id: str,
    limit: int = 10,
    project_key: str | None = None,
) -> dict:
    """Dispatch to news resource handler. Effective = shared (总库) + project (子项目库), project overrides."""
    from ..project_customization import get_project_customization

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        customization = get_project_customization(project_key)
        shared = customization.get_shared_news_resource_handlers()
        project_handlers = customization.get_news_resource_handlers()
        handlers = {**shared, **project_handlers}
        handler = handlers.get(resource_id)
        if not handler:
            raise ValueError(f"Project '{project_key}' does not support news resource '{resource_id}'")
        return handler(limit=limit)


@celery_app.task
def task_extract_resource_pool_from_documents(
    project_key: str,
    scope: str = "project",
    doc_type: list[str] | None = None,
    state: list[str] | None = None,
    document_ids: list[int] | None = None,
    limit: int = 500,
) -> dict:
    """Extract URLs from documents into resource pool."""
    from .resource_pool import extract_from_documents

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return extract_from_documents(
            project_key=project_key,
            scope=scope,
            doc_type=doc_type,
            state=state,
            document_ids=document_ids,
            limit=limit,
        )


@celery_app.task
def task_extract_resource_pool_from_tasks(
    project_key: str,
    scope: str = "project",
    task_ids: list[int] | None = None,
    job_type: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> dict:
    """Extract URLs from EtlJobRun params into resource pool."""
    from .resource_pool import extract_from_tasks

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return extract_from_tasks(
            project_key=project_key,
            scope=scope,
            task_ids=task_ids,
            job_type=job_type,
            since=since,
            limit=limit,
        )


@celery_app.task(bind=True)
def task_discover_site_entries_batched(
    self,
    project_key: str,
    url_scope: str = "effective",
    target_scope: str = "project",
    domain: str | None = None,
    limit_domains: int = 50,
    probe_timeout: float = 8.0,
    include_link_alternate: bool = True,
    sitemap_paths: list[str] | None = None,
    rss_paths: list[str] | None = None,
    allow_domains: list[str] | None = None,
    deny_domains: list[str] | None = None,
    run_auto_classify: bool = False,
    use_llm: bool = False,
    write: bool = True,
    batch_size: int = 20,
    simplify_pool_first: bool = True,
) -> dict:
    from .resource_pool import (
        discover_site_entries_from_urls,
        list_discovery_domains,
        simplify_site_entries,
        write_discovered_site_entries,
    )

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        domains = list_discovery_domains(
            project_key=project_key,
            url_scope=url_scope,
            domain=domain,
            limit_domains=limit_domains,
            allow_domains=allow_domains,
            deny_domains=deny_domains,
        )
        batch_size = max(1, min(100, int(batch_size or 20)))
        totals = {
            "domains_scanned": 0,
            "candidates_count": 0,
            "probe_stats": {},
            "errors": [],
            "write_result": {"upserted": 0, "skipped": 0, "errors": []},
            "batches_total": ceil(len(domains) / batch_size) if domains else 0,
            "batches_completed": 0,
            "pre_simplify": None,
        }
        if simplify_pool_first and write and target_scope in {"project", "shared"}:
            try:
                totals["pre_simplify"] = simplify_site_entries(
                    scope=target_scope,
                    project_key=project_key if target_scope == "project" else None,
                    dry_run=False,
                )
            except Exception as exc:
                totals["pre_simplify"] = {"error": str(exc)}
        self.update_state(
            state="STARTED",
            meta={
                "phase": "prepared",
                "batches_total": totals["batches_total"],
                "batches_completed": totals["batches_completed"],
                "pre_simplify": totals["pre_simplify"],
            },
        )
        for i in range(0, len(domains), batch_size):
            batch_domains = domains[i : i + batch_size]
            result = discover_site_entries_from_urls(
                project_key=project_key,
                url_scope=url_scope,
                target_scope=target_scope,
                domain=None,
                limit_domains=max(len(batch_domains), 1),
                probe_timeout=probe_timeout,
                include_link_alternate=include_link_alternate,
                sitemap_paths=sitemap_paths,
                rss_paths=rss_paths,
                allow_domains=batch_domains,
                deny_domains=deny_domains,
                run_auto_classify=run_auto_classify,
                use_llm=use_llm,
            )
            totals["domains_scanned"] += int(result.domains_scanned or 0)
            totals["candidates_count"] += len(result.candidates or [])
            totals["errors"].extend(result.errors or [])
            for k, v in (result.probe_stats or {}).items():
                totals["probe_stats"][k] = int(totals["probe_stats"].get(k, 0)) + int(v or 0)
            if write:
                wr = write_discovered_site_entries(
                    project_key=project_key,
                    candidates=result.candidates,
                    target_scope=target_scope,
                    dry_run=False,
                )
                totals["write_result"]["upserted"] += int(wr.upserted or 0)
                totals["write_result"]["skipped"] += int(wr.skipped or 0)
                totals["write_result"]["errors"].extend(wr.errors or [])
            totals["batches_completed"] += 1
            self.update_state(
                state="STARTED",
                meta={
                    "phase": "discovering",
                    "batches_total": totals["batches_total"],
                    "batches_completed": totals["batches_completed"],
                    "domains_scanned": totals["domains_scanned"],
                    "candidates_count": totals["candidates_count"],
                    "probe_stats": totals["probe_stats"],
                    "write_result": totals["write_result"],
                    "pre_simplify": totals["pre_simplify"],
                },
            )
        return totals


@celery_app.task
def task_collect_reddit(subreddit: str = "Lottery", limit: int = 20, project_key: str | None = None) -> dict:
    from ..subprojects.online_lottery.services import collect_reddit_discussions_for_project

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_reddit_discussions_for_project(subreddit=subreddit, limit=limit)


@celery_app.task
def task_collect_weekly_reports(limit: int = 10, project_key: str | None = None) -> dict:
    from .ingest.reports.general import collect_weekly_market_reports

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_weekly_market_reports(limit=limit)


@celery_app.task
def task_collect_monthly_reports(limit: int = 8, project_key: str | None = None) -> dict:
    from .ingest.reports.general import collect_monthly_financial_reports

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_monthly_financial_reports(limit=limit)


@celery_app.task
def task_collect_social_sentiment(
    keywords: list[str],
    platforms: list[str] | None = None,
    limit: int = 20,
    enable_extraction: bool = True,
    enable_subreddit_discovery: bool = True,
    base_subreddits: list[str] | None = None,
    project_key: str | None = None,
) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _get_social_ingest_app().collect_social_sentiment(
            keywords=keywords,
            platforms=platforms,
            limit=limit,
            enable_extraction=enable_extraction,
            enable_subreddit_discovery=enable_subreddit_discovery,
            base_subreddits=base_subreddits,
        )


@celery_app.task
def task_collect_policy_regulation(
    keywords: list[str],
    limit: int = 20,
    enable_extraction: bool = True,
    project_key: str | None = None,
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str | None = None,
    provider: str | None = None,
) -> dict:
    from .collect_runtime import collect_request_from_policy_api, run_collect

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        req = collect_request_from_policy_api(
            query_terms=keywords,
            max_items=limit,
            project_key=project_key,
            start_offset=start_offset,
            days_back=days_back,
            language=language or "en",
            provider=provider or "auto",
            enable_extraction=enable_extraction,
        )
        cr = run_collect(req)
        return dict((cr.meta or {}).get("raw") or {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped})


@celery_app.task
def task_ingest_commodity_metrics(limit: int = 30, project_key: str | None = None) -> dict:
    from .ingest.commodity import ingest_commodity_metrics

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return ingest_commodity_metrics(limit=limit)


@celery_app.task
def task_collect_ecom_prices(limit: int = 100, project_key: str | None = None) -> dict:
    from .ingest.ecom import collect_ecom_price_observations

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_ecom_price_observations(limit=limit)


@celery_app.task
def task_sync_aggregator() -> dict:
    # Aggregator reads from public + all project schemas.
    from .aggregator import sync_project_data_to_aggregator

    return sync_project_data_to_aggregator()


@celery_app.task
def task_raw_import_documents(payload: dict, project_key: str | None = None) -> dict:
    from .ingest.raw_import import run_raw_import_documents

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return run_raw_import_documents(payload=payload or {}, project_key=project_key or "")


@celery_app.task
def task_run_source_library_item(
    item_key: str,
    project_key: str | None = None,
    override_params: dict | None = None,
) -> dict:
    from .collect_runtime import run_source_library_item_compat

    return run_source_library_item_compat(
        item_key=item_key,
        project_key=project_key,
        override_params=override_params or {},
    )


@celery_app.task
def task_submit_crawler_job(
    job_id: int,
    provider: str,
    project: str,
    spider: str,
    arguments: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    version: str | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    from .job_logger import fail_job, update_job_tracking

    submit_fn, _ = _load_crawlers_bridge_api()
    try:
        submitted = _normalize_crawler_response(
            submit_fn(
                provider=provider,
                project=project,
                spider=spider,
                arguments=arguments or {},
                settings=settings or {},
                version=version,
                priority=priority,
            )
        )
        external_job_id = str(
            submitted.get("external_job_id")
            or submitted.get("provider_job_id")
            or ""
        ).strip() or None
        external_provider = str(
            submitted.get("external_provider")
            or submitted.get("provider_type")
            or provider
            or ""
        ).strip() or None
        retry_count = submitted.get("retry_count")
        if retry_count is None:
            retry_count = submitted.get("attempt_count")
        update_job_tracking(
            int(job_id),
            external_job_id=external_job_id,
            external_provider=external_provider,
            retry_count=int(retry_count) if retry_count is not None else None,
            status=_map_provider_status(submitted.get("provider_status"), default="running"),
            result={"crawler_submit": submitted},
        )
        return {
            "job_id": int(job_id),
            "external_provider": external_provider,
            "external_job_id": external_job_id,
            "status": _map_provider_status(submitted.get("provider_status"), default="running"),
            "raw": submitted,
        }
    except Exception as exc:
        fail_job(int(job_id), str(exc))
        raise


@celery_app.task
def task_poll_crawler_job(
    job_id: int,
    external_provider: str | None = None,
    external_job_id: str | None = None,
    project: str | None = None,
    spider: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .job_logger import fail_job, update_job_tracking

    _, poll_fn = _load_crawlers_bridge_api()
    tracked = _load_db_job_tracking(int(job_id))
    provider = external_provider or tracked.get("external_provider")
    provider_job_id = external_job_id or tracked.get("external_job_id")
    if not provider or not provider_job_id:
        raise ValueError(
            f"missing crawler tracking fields for job_id={job_id}: "
            f"external_provider={provider!r}, external_job_id={provider_job_id!r}"
        )

    try:
        polled = _normalize_crawler_response(
            poll_fn(
                external_provider=provider,
                external_job_id=provider_job_id,
                provider=provider,
                project=project,
                spider=spider,
                options=options or {},
            )
        )
        provider_status = polled.get("provider_status") or polled.get("status")
        retry_count = polled.get("retry_count")
        if retry_count is None:
            retry_count = polled.get("attempt_count")
        mapped_status = _map_provider_status(provider_status, default=str(tracked.get("status") or "running"))
        update_job_tracking(
            int(job_id),
            external_job_id=str(polled.get("external_job_id") or provider_job_id),
            external_provider=str(polled.get("external_provider") or provider),
            retry_count=int(retry_count) if retry_count is not None else None,
            status=mapped_status,
            result={"crawler_poll": polled},
            error=str(polled.get("error") or "") or None,
        )
        return {
            "job_id": int(job_id),
            "external_provider": str(polled.get("external_provider") or provider),
            "external_job_id": str(polled.get("external_job_id") or provider_job_id),
            "status": mapped_status,
            "raw": polled,
        }
    except Exception as exc:
        fail_job(int(job_id), str(exc), external_provider=str(provider), external_job_id=str(provider_job_id))
        raise


@celery_app.task
def task_crawler_deploy_version(
    project: str,
    version: str,
    egg_file_path: str | None = None,
    egg_content_b64: str | None = None,
    base_url: str | None = None,
    metadata: dict[str, Any] | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    from .crawlers_mgmt import deploy_scrapy_project_version
    from .job_logger import fail_job, update_job_tracking

    try:
        result = deploy_scrapy_project_version(
            project=project,
            version=version,
            egg_file_path=egg_file_path,
            egg_content_b64=egg_content_b64,
            base_url=base_url,
            metadata=metadata or {},
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status=_map_control_status(result.get("provider_status")),
                result={"crawler_deploy": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_register_source_library_scrapy_binding(
    project_key: str,
    channel_key: str,
    item_key: str,
    spider: str,
    scrapy_project: str,
    channel_name: str | None = None,
    item_name: str | None = None,
    description: str | None = None,
    arguments: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    item_params_patch: dict[str, Any] | None = None,
    channel_extra_patch: dict[str, Any] | None = None,
    item_extra_patch: dict[str, Any] | None = None,
    enabled: bool = True,
    job_id: int | None = None,
) -> dict[str, Any]:
    from .crawlers_mgmt import register_or_update_source_library_scrapy_binding
    from .job_logger import fail_job, update_job_tracking

    try:
        result = register_or_update_source_library_scrapy_binding(
            project_key=project_key,
            channel_key=channel_key,
            item_key=item_key,
            spider=spider,
            scrapy_project=scrapy_project,
            channel_name=channel_name,
            item_name=item_name,
            description=description,
            arguments=arguments or {},
            settings=settings or {},
            item_params_patch=item_params_patch or {},
            channel_extra_patch=channel_extra_patch or {},
            item_extra_patch=item_extra_patch or {},
            enabled=enabled,
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="running",
                result={"crawler_auto_register": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_orchestrate_crawler_deploy(
    project_key: str,
    scrapy_project: str,
    spider: str,
    channel_key: str,
    item_key: str,
    version: str,
    egg_file_path: str | None = None,
    egg_content_b64: str | None = None,
    base_url: str | None = None,
    metadata: dict[str, Any] | None = None,
    channel_name: str | None = None,
    item_name: str | None = None,
    description: str | None = None,
    arguments: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    item_params_patch: dict[str, Any] | None = None,
    channel_extra_patch: dict[str, Any] | None = None,
    item_extra_patch: dict[str, Any] | None = None,
    enabled: bool = True,
    job_id: int | None = None,
) -> dict[str, Any]:
    from .job_logger import fail_job, update_job_tracking

    try:
        if egg_file_path or egg_content_b64:
            deploy_result = task_crawler_deploy_version.run(
                project=scrapy_project,
                version=version,
                egg_file_path=egg_file_path,
                egg_content_b64=egg_content_b64,
                base_url=base_url,
                metadata=metadata or {},
                job_id=job_id,
            )
        else:
            deploy_result = {
                "provider_type": "scrapy",
                "provider_status": "skipped_no_artifact",
                "project": scrapy_project,
                "version": version,
                "raw": {"reason": "egg artifact not provided; registration-only mode"},
            }
        register_result = task_register_source_library_scrapy_binding.run(
            project_key=project_key,
            channel_key=channel_key,
            item_key=item_key,
            spider=spider,
            scrapy_project=scrapy_project,
            channel_name=channel_name,
            item_name=item_name,
            description=description,
            arguments=arguments or {},
            settings=settings or {},
            item_params_patch=item_params_patch or {},
            channel_extra_patch=channel_extra_patch or {},
            item_extra_patch=item_extra_patch or {},
            enabled=enabled,
            job_id=job_id,
        )
        orchestrated = {
            "project_key": project_key,
            "channel_key": channel_key,
            "item_key": item_key,
            "provider_type": "scrapy",
            "deploy": deploy_result,
            "register": register_result,
        }
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="completed",
                result={"crawler_deploy_orchestration": orchestrated},
            )
        return orchestrated
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_crawler_rollback_version(
    project: str,
    version: str,
    base_url: str | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    from .crawlers_mgmt import rollback_scrapy_project_version
    from .job_logger import fail_job, update_job_tracking

    try:
        result = rollback_scrapy_project_version(
            project=project,
            version=version,
            base_url=base_url,
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status=_map_control_status(result.get("provider_status")),
                result={"crawler_rollback": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_disable_source_library_channel_provider_native(
    project_key: str,
    channel_key: str,
    item_key: str | None = None,
    keep_item_enabled: bool = True,
    job_id: int | None = None,
) -> dict[str, Any]:
    from .crawlers_mgmt import apply_source_library_native_rollback
    from .job_logger import fail_job, update_job_tracking

    try:
        result = apply_source_library_native_rollback(
            project_key=project_key,
            channel_key=channel_key,
            item_key=item_key,
            keep_item_enabled=keep_item_enabled,
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="running",
                result={"crawler_provider_native_rollback": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_orchestrate_crawler_rollback(
    project_key: str,
    scrapy_project: str,
    channel_key: str,
    item_key: str | None = None,
    version: str | None = None,
    base_url: str | None = None,
    disable_provider_type_to_native: bool = True,
    keep_item_enabled: bool = True,
    job_id: int | None = None,
) -> dict[str, Any]:
    from .job_logger import fail_job, update_job_tracking

    try:
        rollback_result: dict[str, Any] | None = None
        if version:
            rollback_result = task_crawler_rollback_version.run(
                project=scrapy_project,
                version=version,
                base_url=base_url,
                job_id=job_id,
            )

        native_result: dict[str, Any] | None = None
        if disable_provider_type_to_native:
            native_result = task_disable_source_library_channel_provider_native.run(
                project_key=project_key,
                channel_key=channel_key,
                item_key=item_key,
                keep_item_enabled=keep_item_enabled,
                job_id=job_id,
            )

        orchestrated = {
            "project_key": project_key,
            "channel_key": channel_key,
            "item_key": item_key,
            "provider_type": "native" if disable_provider_type_to_native else "scrapy",
            "rollback": rollback_result,
            "provider_toggle": native_result,
        }
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="completed",
                result={"crawler_rollback_orchestration": orchestrated},
            )
        return orchestrated
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise
