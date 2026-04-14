"""Reddit channel adapter: wrap ingest.news.collect_reddit_discussions."""

from __future__ import annotations

from typing import Any, Dict, List


def handle_reddit(params: Dict[str, Any], _project_key: str | None) -> Dict[str, Any]:
    """Collect Reddit discussions from subreddit(s)."""
    from ...ingest.news import collect_reddit_discussions

    subreddit = str(params.get("subreddit") or "Lottery")
    limit = int(params.get("limit", 20))
    keywords = params.get("keywords")
    if isinstance(keywords, str):
        keywords = [keywords]
    subreddits = params.get("subreddits") or params.get("base_subreddits")
    if isinstance(subreddits, list):
        return collect_reddit_discussions(
            subreddit=subreddit,
            limit=limit,
            keywords=keywords,
            subreddits=subreddits,
        )
    return collect_reddit_discussions(
        subreddit=subreddit,
        limit=limit,
        keywords=keywords,
    )
