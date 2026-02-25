from __future__ import annotations

from ....services.ingest.news import (
    collect_calottery_news,
    collect_calottery_retailer_updates,
    collect_reddit_discussions,
)
from ..domain.news import DEFAULT_REDDIT_SUBREDDIT


def collect_calottery_news_for_project(limit: int = 10) -> dict:
    return collect_calottery_news(limit=limit)


def collect_calottery_retailer_updates_for_project(limit: int = 10) -> dict:
    return collect_calottery_retailer_updates(limit=limit)


def collect_reddit_discussions_for_project(subreddit: str | None = None, limit: int = 20) -> dict:
    return collect_reddit_discussions(subreddit=subreddit or DEFAULT_REDDIT_SUBREDDIT, limit=limit)
