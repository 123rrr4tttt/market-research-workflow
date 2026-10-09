"""Market channel adapter: wrap ingest.market_web.collect_market_info."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard


def _object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _int(value: object, default: int) -> int:
    if not isinstance(value, int | float | str):
        return default
    try:
        return int(value)
    except Exception:
        return default


def handle_market(params: Mapping[object, object], _project_key: str | None) -> dict[str, object]:
    """Collect market info by keywords."""
    from ...ingest.market_web import collect_market_info

    raw_keywords = params.get("keywords") or params.get("query_terms")
    keyword_values = _object_list(raw_keywords) if _is_object_list(raw_keywords) else [raw_keywords]
    keywords = [str(item) for item in keyword_values if item is not None]
    limit = _int(params.get("max_items") or params.get("limit"), 20)
    enable_extraction = bool(params.get("enable_extraction", True))
    provider = str(params.get("provider") or "auto")
    language = str(params.get("language") or "en")
    start_offset_raw = params.get("start_offset")
    start_offset = start_offset_raw if isinstance(start_offset_raw, int) and start_offset_raw > 0 else None
    days_back_raw = params.get("days_back")
    days_back = days_back_raw if isinstance(days_back_raw, int) and days_back_raw > 0 else None
    return collect_market_info(
        keywords=keywords,
        limit=limit,
        enable_extraction=enable_extraction,
        provider=provider,
        start_offset=start_offset,
        days_back=days_back,
        language=language,
    )
