from __future__ import annotations

from .ingest.policy import ingest_policy_documents
from .ingest.market import ingest_market_data
from .ingest.news import (
    collect_calottery_news,
    collect_calottery_retailer_updates,
    collect_reddit_discussions,
)
from .ingest.reports.general import (
    collect_weekly_market_reports,
    collect_monthly_financial_reports,
)
from .indexer import index_policy_documents
from ..celery_app import celery_app


@celery_app.task
def task_ingest_policy(state: str) -> dict:
    return ingest_policy_documents(state=state)


@celery_app.task
def task_ingest_market(
    state: str,
    source_hint: str | None = None,
    game: str | None = None,
    limit: int | None = None,
) -> dict:
    return ingest_market_data(state=state, source_hint=source_hint, game=game, limit=limit)


@celery_app.task
def task_index_policy(document_ids: list[int]) -> dict:
    return index_policy_documents(document_ids=document_ids)


@celery_app.task
def task_collect_calottery_news(limit: int = 10) -> dict:
    return collect_calottery_news(limit=limit)


@celery_app.task
def task_collect_calottery_retailer(limit: int = 10) -> dict:
    return collect_calottery_retailer_updates(limit=limit)


@celery_app.task
def task_collect_reddit(subreddit: str = "Lottery", limit: int = 20) -> dict:
    return collect_reddit_discussions(subreddit=subreddit, limit=limit)


@celery_app.task
def task_collect_weekly_reports(limit: int = 10) -> dict:
    return collect_weekly_market_reports(limit=limit)


@celery_app.task
def task_collect_monthly_reports(limit: int = 8) -> dict:
    return collect_monthly_financial_reports(limit=limit)


