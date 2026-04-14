from __future__ import annotations

from typing import Any, Dict

from ..base import SubprojectExtractionAdapter


class DemoProjExtractionAdapter(SubprojectExtractionAdapter):
    """Embodied AI adaptation for demo_proj."""

    def augment_policy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "domain": "embodied_ai",
            "region": data.get("state"),
            "policy_category": data.get("policy_type"),
            "effective_date": data.get("effective_date"),
            "highlights": data.get("key_points", []),
        }
        return {**data, "domain_payload": payload}

    def augment_market(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Map from MarketExtracted fields (game, jackpot, ticket_price, draw_number)
        # to embodied AI domain terms (segment, funding_amount, unit_price, version)
        payload = {
            "domain": "embodied_ai",
            "region": data.get("state"),
            "segment": data.get("segment") or data.get("game"),
            "report_date": data.get("report_date"),
            "deployment_volume": data.get("sales_volume"),
            "market_size": data.get("revenue"),
            "financing_or_order_amount": data.get("funding_amount") or data.get("jackpot"),
            "asp": data.get("unit_price") or data.get("ticket_price"),
            "model_or_version": data.get("version") or data.get("draw_number"),
            "yoy_growth": data.get("yoy_change"),
            "mom_growth": data.get("mom_change"),
            "highlights": data.get("key_findings", []),
        }
        return {**data, "domain_payload": payload}

    def augment_sentiment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "domain": "embodied_ai",
            "signal_type": "community_sentiment",
            "topic_cluster": data.get("topic"),
            "risk_or_opportunity_tags": data.get("sentiment_tags", []),
        }
        return {**data, "domain_payload": payload}

    def augment_policy_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "domain": "embodied_ai",
            "affected_regions": data.get("affected_states", []),
            "regulation_type": data.get("policy_type"),
            "direction": data.get("policy_direction"),
            "highlights": data.get("key_points", []),
        }
        return {**data, "domain_payload": payload}
