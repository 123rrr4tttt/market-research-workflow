from __future__ import annotations

from typing import Any, Dict


class SubprojectExtractionAdapter:
    """Project-specific extraction adapter hooks."""

    def augment_policy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data

    def augment_market(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data

    def augment_sentiment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data

    def augment_policy_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data
