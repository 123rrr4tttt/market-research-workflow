from __future__ import annotations

from typing import Any

from .common_view import get_entities, get_extracted_data


def get_market_data(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    market = extracted.get("market")
    if isinstance(market, dict) and market:
        return dict(market)

    fallback_state = (
        str(getattr(doc, "state", "") or "").strip()
        or str(extracted.get("state") or "").strip()
        or "NA"
    )
    fallback_game = (
        str(extracted.get("keyword") or "").strip()
        or str(extracted.get("topic") or "").strip()
        or str(extracted.get("source") or "").strip()
        or "general"
    )
    publish_date = getattr(doc, "publish_date", None)
    return {
        "state": fallback_state,
        "game": fallback_game,
        "report_date": publish_date.isoformat() if publish_date else None,
    }


def get_market_entities(doc: Any) -> list[dict[str, Any]]:
    return get_entities(doc)
