from __future__ import annotations

from typing import Any, Dict

from ..base import SubprojectExtractionAdapter


class OnlineLotteryExtractionAdapter(SubprojectExtractionAdapter):
    """Keep lottery extraction behavior explicit in subproject layer."""

    def augment_market(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "domain": "online_lottery",
            "region": data.get("state"),
            "segment": data.get("game"),
            "market_size": data.get("revenue"),
            "financing_or_order_amount": data.get("jackpot"),
        }
        return {**data, "domain_payload": payload}
