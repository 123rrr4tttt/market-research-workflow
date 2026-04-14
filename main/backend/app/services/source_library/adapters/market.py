"""Market channel adapter: wrap ingest.market_web.collect_market_info."""

from __future__ import annotations

from typing import Any, Dict, List


def handle_market(params: Dict[str, Any], _project_key: str | None) -> Dict[str, Any]:
    """Collect market info by keywords."""
    from ...ingest.market_web import collect_market_info

    keywords = params.get("keywords") or params.get("query_terms") or []
    keywords = [str(x) for x in (keywords if isinstance(keywords, list) else [keywords])]
    limit = int(params.get("max_items") or params.get("limit") or 20)
    enable_extraction = bool(params.get("enable_extraction", True))
    provider = str(params.get("provider") or "auto")
    language = str(params.get("language") or "en")
    start_offset_raw = params.get("start_offset")
    start_offset = int(start_offset_raw) if isinstance(start_offset_raw, int) and start_offset_raw > 0 else None
    days_back_raw = params.get("days_back")
    days_back = int(days_back_raw) if isinstance(days_back_raw, int) and days_back_raw > 0 else None
    return collect_market_info(
        keywords=keywords,
        limit=limit,
        enable_extraction=enable_extraction,
        provider=provider,
        start_offset=start_offset,
        days_back=days_back,
        language=language,
    )
