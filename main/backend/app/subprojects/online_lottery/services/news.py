from __future__ import annotations

from ..domain.news import CALOTTERY_NEWS_URL, CALOTTERY_RETAILER_URL, DEFAULT_REDDIT_SUBREDDIT


def collect_calottery_news_for_project(limit: int = 10) -> dict:
    from ....services.ingest.news import collect_official_news_updates

    return collect_official_news_updates(
        url=CALOTTERY_NEWS_URL,
        source_name="California Lottery News",
        base_url="calottery.com",
        doc_type="official_update",
        default_state="CA",
        job_type="calottery_news",
        title_fallback="California Lottery Update",
        limit=limit,
    )


def collect_calottery_retailer_updates_for_project(limit: int = 10) -> dict:
    from ....services.ingest.news import collect_official_news_updates

    return collect_official_news_updates(
        url=CALOTTERY_RETAILER_URL,
        source_name="California Lottery Retailer News",
        base_url="calottery.com",
        doc_type="retailer_update",
        default_state="CA",
        job_type="calottery_retailer_news",
        title_fallback="California Lottery Retailer Update",
        limit=limit,
    )


def collect_reddit_discussions_for_project(subreddit: str | None = None, limit: int = 20) -> dict:
    from ....services.ingest.news import collect_reddit_discussions

    return collect_reddit_discussions(subreddit=subreddit or DEFAULT_REDDIT_SUBREDDIT, limit=limit)
