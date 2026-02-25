"""Generic social adapter for docs with sentiment but no platform-specific adapter.

Handles social_sentiment docs from news, market_web, or other non-Reddit sources
that have extracted_data.sentiment and content but lack platform="reddit".
"""
from __future__ import annotations

import logging
from typing import Optional

from ....models.entities import Document
from ..models import NormalizedSocialPost

logger = logging.getLogger(__name__)


class GenericSocialAdapter:
    """Generic adapter for social docs with sentiment data but no platform-specific format."""

    def to_normalized(self, doc: Document) -> Optional[NormalizedSocialPost]:
        """
        Convert doc with sentiment to NormalizedSocialPost.
        Requires: extracted_data.sentiment and (text or content).
        """
        if not doc.extracted_data:
            return None

        extracted = doc.extracted_data
        sentiment = extracted.get("sentiment", {})
        if not sentiment:
            return None

        text = extracted.get("text") or doc.content or doc.title or ""
        if not text:
            logger.debug("Document %s has no text content", doc.id)
            return None

        platform = (extracted.get("platform") or "generic").lower()
        sentiment_orientation = sentiment.get("sentiment_orientation")
        sentiment_tags = sentiment.get("sentiment_tags", [])
        key_phrases = sentiment.get("key_phrases", [])
        emotion_words = sentiment.get("emotion_words", [])
        topic = sentiment.get("topic")

        keywords = extracted.get("keywords", []) or key_phrases
        entities = extracted.get("entities", [])
        if not entities:
            er = extracted.get("entities_relations", {}) or {}
            entities = er.get("entities", [])

        return NormalizedSocialPost(
            doc_id=doc.id,
            uri=doc.uri or "",
            platform=platform,
            text=text,
            username=extracted.get("username"),
            subreddit=extracted.get("subreddit"),
            publish_date=doc.publish_date,
            createdAt=doc.created_at,
            state=doc.state,
            sentiment_orientation=sentiment_orientation,
            sentiment_tags=sentiment_tags or [],
            key_phrases=key_phrases or [],
            emotion_words=emotion_words or [],
            topic=topic,
            entities=entities or [],
            keywords=keywords or [],
        )
