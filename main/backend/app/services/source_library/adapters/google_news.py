"""Google News channel adapter: wrap ingest.news.collect_google_news."""

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


def handle_google_news(params: Mapping[object, object], _project_key: str | None) -> dict[str, object]:
    """Collect Google News by keywords."""
    from ...ingest.news import collect_google_news

    raw = params.get("keywords")
    if isinstance(raw, str):
        keywords: list[str] = [raw]
    elif _is_object_list(raw):
        keywords = [str(item) for item in raw]
    else:
        keywords = [str(item) for item in [raw] if raw is not None]
    limit = _int(params.get("limit", 20), 20)
    return collect_google_news(keywords=keywords, limit=limit)
