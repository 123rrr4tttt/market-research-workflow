from __future__ import annotations

from contextlib import nullcontext

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
