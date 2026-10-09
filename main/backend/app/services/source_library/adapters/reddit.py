"""Reddit channel adapter: wrap ingest.news.collect_reddit_discussions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _int(value: object, default: int) -> int:
    if not isinstance(value, int | float | str):
        return default
    try:
        return int(value)
    except Exception:
        return default


def handle_reddit(params: Mapping[object, object], _project_key: str | None) -> dict[str, object]:
    """Collect Reddit discussions from subreddit(s)."""
    from ...ingest.news import collect_reddit_discussions

    subreddit = str(params.get("subreddit") or "news")
    limit = _int(params.get("limit", 20), 20)
    raw_keywords = params.get("keywords")
    if isinstance(raw_keywords, str):
        keywords: list[str] | None = [raw_keywords]
    elif _is_object_list(raw_keywords):
        keywords = [str(item) for item in raw_keywords]
    else:
        keywords = None
    subreddits = params.get("subreddits") or params.get("base_subreddits")
    if _is_object_list(subreddits):
        return collect_reddit_discussions(
            subreddit=subreddit,
            limit=limit,
            keywords=keywords,
            subreddits=[str(item) for item in subreddits],
        )
    return collect_reddit_discussions(
        subreddit=subreddit,
        limit=limit,
        keywords=keywords,
    )
