from __future__ import annotations

from typing import Any

from .common_view import get_entities, get_extracted_data, get_platform


def get_social_platform(doc: Any) -> str:
    return get_platform(doc) or "generic"


def get_social_sentiment(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    sentiment = extracted.get("sentiment")
    return dict(sentiment) if isinstance(sentiment, dict) else {}


def get_social_text(doc: Any) -> str:
    extracted = get_extracted_data(doc)
    return str(extracted.get("text") or getattr(doc, "content", None) or getattr(doc, "title", None) or "")


def get_social_keywords(doc: Any) -> list[str]:
    extracted = get_extracted_data(doc)
    keywords = extracted.get("keywords")
    if isinstance(keywords, list):
        return [item for item in keywords if isinstance(item, str) and item.strip()]
    sentiment = get_social_sentiment(doc)
    key_phrases = sentiment.get("key_phrases")
    if isinstance(key_phrases, list):
        return [item for item in key_phrases if isinstance(item, str) and item.strip()]
    return []


def get_social_entities(doc: Any) -> list[dict[str, Any]]:
    return get_entities(doc)
