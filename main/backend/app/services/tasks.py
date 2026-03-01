from __future__ import annotations

from contextlib import nullcontext
from math import ceil

from ..celery_app import celery_app
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
