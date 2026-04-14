"""Reddit平台适配器"""
from __future__ import annotations

import logging
from typing import Optional

from ....models.entities import Document
from ..models import NormalizedSocialPost
from ...document_views import (
    get_social_entities,
    get_social_keywords,
    get_social_platform,
    get_social_sentiment,
    get_social_text,
)

logger = logging.getLogger(__name__)


class RedditAdapter:
    """Reddit平台数据适配器"""
    
    def to_normalized(self, doc: Document) -> Optional[NormalizedSocialPost]:
        """
        将Reddit文档转换为规范化格式
        
        字段映射规则：
        - platform: extracted_data.platform (应为"reddit")
        - text: extracted_data.text
        - username: extracted_data.username
        - subreddit: extracted_data.subreddit
        - keywords: extracted_data.keywords (可选)
        - entities: extracted_data.entities (可选)
        - sentiment: extracted_data.sentiment (包含sentiment_orientation, sentiment_tags, key_phrases, emotion_words, topic)
        """
        if not doc.extracted_data:
            return None

        extracted = doc.extracted_data

        # 平台检查
        platform = get_social_platform(doc)
        if platform != "reddit":
            logger.warning(f"Document {doc.id} platform is '{platform}', expected 'reddit'")
            return None

        # 提取基础字段
        text = get_social_text(doc)
        if not text:
            logger.debug(f"Document {doc.id} has no text content")
            return None

        # 提取用户和子论坛信息
        username = extracted.get("username")
        subreddit = extracted.get("subreddit")

        # 提取情感信息
        sentiment = get_social_sentiment(doc)
        sentiment_orientation = sentiment.get("sentiment_orientation")
        sentiment_tags = sentiment.get("sentiment_tags", [])
        key_phrases = sentiment.get("key_phrases", [])
        emotion_words = sentiment.get("emotion_words", [])
        topic = sentiment.get("topic")

        # 提取关键词和实体
        keywords = get_social_keywords(doc)
        entities = get_social_entities(doc)

        # 处理日期
        publish_date = doc.publish_date
        createdAt = doc.created_at

        return NormalizedSocialPost(
            doc_id=doc.id,
            uri=doc.uri or "",
            platform=platform,
            text=text,
            username=username,
            subreddit=subreddit,
            publish_date=publish_date,
            createdAt=createdAt,
            state=doc.state,
            sentiment_orientation=sentiment_orientation,
            sentiment_tags=sentiment_tags or [],
            key_phrases=key_phrases or [],
            emotion_words=emotion_words or [],
            topic=topic,
            entities=entities or [],
            keywords=keywords or [],
        )
