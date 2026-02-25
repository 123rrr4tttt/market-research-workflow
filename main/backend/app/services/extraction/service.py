"""Extraction application facade with unified JSON fallback."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..llm.config_loader import format_prompt_template, get_llm_config
from ..llm.provider import get_chat_model
from ...subprojects import get_extraction_adapter
from .extract import extract_entities_relations, extract_market_info
from .json_utils import extract_json_payload

logger = logging.getLogger(__name__)


def extract_structured_sentiment(text: str) -> Optional[Dict[str, Any]]:
    if not text or len(text.strip()) < 20:
        return None
    try:
        config = get_llm_config("sentiment_extraction")
        text_snippet = text[:2000]
        if config and config.get("user_prompt_template"):
            prompt = format_prompt_template(config["user_prompt_template"], text=text_snippet)
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            prompt = (
                "从以下文本中提取结构化的情感和信息：\n\n"
                f"文本：\n{text_snippet}\n\n"
                "请提取并返回JSON（只返回JSON）："
                '{"sentiment_tags":[],"sentiment_orientation":"positive|negative|neutral",'
                '"key_phrases":[],"emotion_words":[],"topic":""}'
            )
            model = get_chat_model()
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        data = extract_json_payload(content)
        if not data:
            return None
        result = {
            "sentiment_tags": data.get("sentiment_tags", []),
            "sentiment_orientation": data.get("sentiment_orientation", "neutral"),
            "key_phrases": data.get("key_phrases", []),
            "emotion_words": data.get("emotion_words", []),
            "topic": data.get("topic", ""),
        }
        return get_extraction_adapter().augment_sentiment(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_structured_sentiment failed: %s", exc, exc_info=True)
        return None


def extract_policy_info(text: str) -> Optional[Dict[str, Any]]:
    if not text or len(text.strip()) < 50:
        return None
    try:
        config = get_llm_config("policy_info_extraction")
        text_snippet = text[:2000]
        if config and config.get("user_prompt_template"):
            prompt = format_prompt_template(config["user_prompt_template"], text=text_snippet)
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            prompt = (
                "从以下文本中提取政策相关信息，返回JSON：\n\n"
                f"{text_snippet}\n\n"
                '{"affected_states":[],"policy_direction":"","policy_type":"",'
                '"key_points":[],"effective_date":null}'
            )
            model = get_chat_model()
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        data = extract_json_payload(content)
        if not data:
            return None
        result = {
            "affected_states": data.get("affected_states", []),
            "policy_direction": data.get("policy_direction", ""),
            "policy_type": data.get("policy_type", ""),
            "key_points": data.get("key_points", []),
            "effective_date": data.get("effective_date"),
        }
        return get_extraction_adapter().augment_policy_info(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_policy_info(service facade) failed: %s", exc, exc_info=True)
        return None


def extract_batch_sentiment(texts: List[str]) -> List[Optional[Dict[str, Any]]]:
    return [extract_structured_sentiment(text) for text in texts]


__all__ = [
    "extract_batch_sentiment",
    "extract_entities_relations",
    "extract_market_info",
    "extract_policy_info",
    "extract_structured_sentiment",
]
