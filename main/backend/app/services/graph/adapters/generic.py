"""Generic social adapter for docs with sentiment but no platform-specific adapter.

Handles social_sentiment docs from news, market_web, or other non-Reddit sources
that have extracted_data.sentiment and content but lack platform="reddit".
"""
from __future__ import annotations

import logging
from typing import Optional

from ....models.entities import Document
from ..models import NormalizedSocialPost
from ...document_views import (
    get_social_identity,
    get_social_entities,
    get_social_keywords,
    get_social_platform,
    get_social_sentiment,
    get_social_text,
    has_structured_data,
)

logger = logging.getLogger(__name__)


class GenericSocialAdapter:
    """Generic adapter for social docs with sentiment data but no platform-specific format."""

    def to_normalized(self, doc: Document) -> Optional[NormalizedSocialPost]:
        """
        Convert doc with sentiment to NormalizedSocialPost.
        Requires: extracted_data.sentiment and (text or content).
        """
        if not has_structured_data(doc):
            return None

        sentiment = get_social_sentiment(doc)
        if not sentiment:
            return None

        text = get_social_text(doc)
        if not text:
            logger.debug("Document %s has no text content", doc.id)
            return None

        platform = get_social_platform(doc)
        sentiment_orientation = sentiment.get("sentiment_orientation")
        sentiment_tags = sentiment.get("sentiment_tags", [])
        key_phrases = sentiment.get("key_phrases", [])
        emotion_words = sentiment.get("emotion_words", [])
        topic = sentiment.get("topic")
        identity = get_social_identity(doc)

        keywords = get_social_keywords(doc) or key_phrases
        entities = get_social_entities(doc)

        return NormalizedSocialPost(
            doc_id=doc.id,
            uri=doc.uri or "",
            platform=platform,
            text=text,
            username=identity["username"],
            subreddit=identity["subreddit"],
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
