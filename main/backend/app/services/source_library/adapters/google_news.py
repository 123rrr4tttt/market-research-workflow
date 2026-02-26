"""Google News channel adapter: wrap ingest.news.collect_google_news."""

from __future__ import annotations

from typing import Any, Dict, List


def handle_google_news(params: Dict[str, Any], _project_key: str | None) -> Dict[str, Any]:
    """Collect Google News by keywords."""
    from ...ingest.news import collect_google_news

    raw = params.get("keywords")
    if isinstance(raw, str):
        keywords: List[str] = [raw]
    else:
        keywords = [str(x) for x in (raw or [])]
    limit = int(params.get("limit", 20))
    return collect_google_news(keywords=keywords, limit=limit)
