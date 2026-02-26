"""Market channel adapter: wrap ingest.market_web.collect_market_info."""

from __future__ import annotations

from typing import Any, Dict, List


def handle_market(params: Dict[str, Any], _project_key: str | None) -> Dict[str, Any]:
    """Collect market info by keywords."""
    from ...ingest.market_web import collect_market_info

    keywords = params.get("keywords") or params.get("query_terms") or []
    keywords = [str(x) for x in (keywords if isinstance(keywords, list) else [keywords])]
    limit = int(params.get("limit", 20))
    enable_extraction = bool(params.get("enable_extraction", True))
    return collect_market_info(
        keywords=keywords,
        limit=limit,
        enable_extraction=enable_extraction,
    )
