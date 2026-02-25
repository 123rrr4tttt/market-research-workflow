"""Backward-compatible wrappers for extraction services."""
from __future__ import annotations

from ..extraction.service import (
    extract_batch_sentiment,
    extract_market_info,
    extract_policy_info,
    extract_structured_sentiment,
)

__all__ = [
    "extract_structured_sentiment",
    "extract_policy_info",
    "extract_batch_sentiment",
    "extract_market_info",
]

