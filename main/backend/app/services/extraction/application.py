from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .service import (
    extract_entities_relations,
    extract_market_info,
    extract_policy_info,
    extract_structured_sentiment,
)


@dataclass
class ExtractionApplicationService:
    def extract_policy(self, text: str) -> Optional[dict[str, Any]]:
        return extract_policy_info(text)

    def extract_market(self, text: str) -> Optional[dict[str, Any]]:
        return extract_market_info(text)

    def extract_entities(self, text: str) -> Optional[dict[str, Any]]:
        return extract_entities_relations(text)

    def extract_sentiment(self, text: str) -> Optional[dict[str, Any]]:
        return extract_structured_sentiment(text)

    def extract_structured_enriched(
        self,
        text: str,
        *,
        include_policy: bool = False,
        include_market: bool = False,
        include_sentiment: bool = False,
    ) -> Optional[dict[str, Any]]:
        """
        Mainline unified structured extraction:
        - always tries base ER extraction (entities_relations)
        - optionally overlays domain-specific structured fields (policy/market/sentiment)
        Subprojects remain isolated via existing extraction service adapters.
        """
        raw = str(text or "").strip()
        if not raw:
            return None
        out: dict[str, Any] = {}

        # Base graph layer for all content.
        er = extract_entities_relations(raw)
        if er:
            out["entities_relations"] = er
            ents = er.get("entities")
            if isinstance(ents, list) and ents:
                # Backward compatibility for graph adapters that also read extracted_data.entities
                out["entities"] = ents

        # Specialized overlays.
        if include_sentiment:
            sentiment = extract_structured_sentiment(raw)
            if sentiment:
                out["sentiment"] = sentiment
                if sentiment.get("key_phrases") and not out.get("keywords"):
                    out["keywords"] = sentiment["key_phrases"]

        if include_policy:
            policy = extract_policy_info(raw)
            if policy:
                out["policy"] = policy

        if include_market:
            market = extract_market_info(raw)
            if market:
                out["market"] = market

        return out or None

    # Backward-compatible alias during migration; use extract_structured_enriched in new code.
    def extract_graph_enriched(
        self,
        text: str,
        *,
        include_policy: bool = False,
        include_market: bool = False,
        include_sentiment: bool = False,
    ) -> Optional[dict[str, Any]]:
        return self.extract_structured_enriched(
            text,
            include_policy=include_policy,
            include_market=include_market,
            include_sentiment=include_sentiment,
        )
