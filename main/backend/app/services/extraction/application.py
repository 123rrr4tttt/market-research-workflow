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
