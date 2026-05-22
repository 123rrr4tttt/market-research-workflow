from __future__ import annotations

from typing import Any

from .common_view import get_entities, get_extracted_data, get_platform


def get_social_platform(doc: Any) -> str:
    return get_platform(doc) or "generic"


def get_social_platform_label(doc: Any, *, default: str | None = "unknown") -> str | None:
    extracted = get_extracted_data(doc)
    platform = str(extracted.get("platform") or "").strip()
    return platform or default


def get_social_sentiment(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    sentiment = extracted.get("sentiment")
    return dict(sentiment) if isinstance(sentiment, dict) else {}


def get_social_sentiment_orientation(doc: Any, *, default: str | None = None) -> str | None:
    sentiment = get_social_sentiment(doc)
    value = str(sentiment.get("sentiment_orientation") or "").strip()
    return value or default


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


def get_social_sentiment_terms(doc: Any) -> list[str]:
    sentiment = get_social_sentiment(doc)
    terms: list[str] = []

    key_phrases = sentiment.get("key_phrases")
    if isinstance(key_phrases, list):
        terms.extend(_clean_strings(key_phrases))

    topic = str(sentiment.get("topic") or "").strip()
    if topic:
        terms.append(topic)

    sentiment_tags = sentiment.get("sentiment_tags")
    if isinstance(sentiment_tags, list):
        terms.extend(_clean_strings(sentiment_tags))

    return terms


def get_social_entities(doc: Any) -> list[dict[str, Any]]:
    return get_entities(doc)


def build_social_data_item(doc: Any, *, include_extracted_data: bool = True) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    sentiment = get_social_sentiment(doc)
    publish_date = getattr(doc, "publish_date", None)
    created_at = getattr(doc, "created_at", None)

    keywords = extracted.get("keywords")
    item = {
        "id": getattr(doc, "id", None),
        "title": getattr(doc, "title", None),
        "platform": get_social_platform_label(doc, default=None),
        "username": _string_or_none(extracted.get("username")),
        "subreddit": _string_or_none(extracted.get("subreddit")),
        "likes": extracted.get("likes"),
        "comments": extracted.get("comments"),
        "text": get_social_text(doc),
        "sentiment_orientation": get_social_sentiment_orientation(doc),
        "sentiment_tags": _clean_strings(sentiment.get("sentiment_tags")),
        "topic": _string_or_none(sentiment.get("topic")),
        "key_phrases": _clean_strings(sentiment.get("key_phrases")),
        "emotion_words": _clean_strings(sentiment.get("emotion_words")),
        "keywords": _clean_strings(keywords),
        "entities": get_social_entities(doc),
        "uri": getattr(doc, "uri", None),
        "publish_date": publish_date.isoformat() if publish_date else None,
        "created_at": created_at.isoformat() if created_at else None,
    }
    if include_extracted_data:
        item["extracted_data"] = extracted
    return item


def _clean_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
