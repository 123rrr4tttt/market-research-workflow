from __future__ import annotations

from contextlib import nullcontext

from .ingest.policy import ingest_policy_documents
from .ingest.market_web import collect_market_info
from .ingest.commodity import ingest_commodity_metrics
from .ingest.ecom import collect_ecom_price_observations
from .aggregator import sync_project_data_to_aggregator
from .source_library.resolver import run_item_by_key
from .ingest.news import (
    collect_google_news,
)
from ..subprojects.online_lottery.services import (
    collect_calottery_news_for_project,
    collect_calottery_retailer_updates_for_project,
    collect_reddit_discussions_for_project,
)
from .ingest.social import (
    collect_user_social_sentiment,
    collect_policy_and_regulation,
)
from .ingest.reports.general import (
    collect_weekly_market_reports,
    collect_monthly_financial_reports,
)
from .indexer import index_policy_documents
from ..celery_app import celery_app
from .projects import bind_project
from .ingest.social_application import SocialIngestApplicationService
from .indexer.application import IndexingApplicationService

social_ingest_app = SocialIngestApplicationService()
indexing_app = IndexingApplicationService()


@celery_app.task
def task_ingest_policy(state: str, project_key: str | None = None) -> dict:
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
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_market_info(
            keywords=query_terms,
            limit=max_items,
            enable_extraction=enable_extraction,
            start_offset=start_offset,
            days_back=days_back,
            language=language or "en",
            provider=provider or "auto",
        )


@celery_app.task
def task_index_policy(document_ids: list[int], project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return indexing_app.index_policy(document_ids=document_ids)


@celery_app.task
def task_collect_calottery_news(limit: int = 10, project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_calottery_news_for_project(limit=limit)


@celery_app.task
def task_collect_calottery_retailer(limit: int = 10, project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_calottery_retailer_updates_for_project(limit=limit)


@celery_app.task
def task_collect_reddit(subreddit: str = "Lottery", limit: int = 20, project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_reddit_discussions_for_project(subreddit=subreddit, limit=limit)


@celery_app.task
def task_collect_weekly_reports(limit: int = 10, project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_weekly_market_reports(limit=limit)


@celery_app.task
def task_collect_monthly_reports(limit: int = 8, project_key: str | None = None) -> dict:
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
        return social_ingest_app.collect_social_sentiment(
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
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return social_ingest_app.collect_policy_regulation(
            keywords=keywords,
            limit=limit,
            enable_extraction=enable_extraction,
            start_offset=start_offset,
            days_back=days_back,
            language=language or "en",
            provider=provider or "auto",
        )


@celery_app.task
def task_ingest_commodity_metrics(limit: int = 30, project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return ingest_commodity_metrics(limit=limit)


@celery_app.task
def task_collect_ecom_prices(limit: int = 100, project_key: str | None = None) -> dict:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return collect_ecom_price_observations(limit=limit)


@celery_app.task
def task_sync_aggregator() -> dict:
    # Aggregator reads from public + all project schemas.
    return sync_project_data_to_aggregator()


@celery_app.task
def task_run_source_library_item(
    item_key: str,
    project_key: str | None = None,
    override_params: dict | None = None,
) -> dict:
    return run_item_by_key(
        item_key=item_key,
        project_key=project_key,
        override_params=override_params or {},
    )


