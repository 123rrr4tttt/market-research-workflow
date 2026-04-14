from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..llm.config_loader import format_prompt_template, get_llm_config
from ..llm.provider import get_chat_model
from .json_utils import extract_json_payload

logger = logging.getLogger(__name__)


TOPIC_STRUCTURED_TEMPLATE: dict[str, Any] = {
    "entities": [],
    "relations": [],
    "facts": [],
    "topics": [],
    "signals": {},
    "confidence": 0.0,
    "source_excerpt": "",
}


def _safe_topic_payload(data: dict[str, Any] | None) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    out = dict(TOPIC_STRUCTURED_TEMPLATE)
    out["entities"] = data.get("entities") if isinstance(data.get("entities"), list) else []
    out["relations"] = data.get("relations") if isinstance(data.get("relations"), list) else []
    out["facts"] = data.get("facts") if isinstance(data.get("facts"), list) else []
    out["topics"] = data.get("topics") if isinstance(data.get("topics"), list) else []
    out["signals"] = data.get("signals") if isinstance(data.get("signals"), dict) else {}
    try:
        out["confidence"] = float(data.get("confidence") or 0.0)
    except Exception:
        out["confidence"] = 0.0
    out["source_excerpt"] = str(data.get("source_excerpt") or "")[:800]
    # Optional marker for empty result
    if all(not out[k] for k in ("entities", "relations", "facts", "topics")) and not out["signals"]:
        out["_status"] = str(data.get("_status") or "no_topic_signal")
    return out


def _default_topic_prompt(topic: str, text_snippet: str) -> str:
    labels = {
        "company": "company / organization / brand / partner",
        "product": "product / model / category / component / scenario",
        "operation": "ecommerce / operation / business model / operation status / strategy / metric",
    }
    entity_type_hints = {
        "company": ["company", "brand", "business_unit", "partner", "channel"],
        "product": ["product", "model", "category", "brand", "component", "scenario"],
        "operation": ["operation_subject", "platform", "store", "channel", "metric", "strategy", "region", "period"],
    }
    relation_hints = {
        "company": ["depends_on", "partners_with", "supplies", "distributes", "competes_with", "operates_in"],
        "product": ["belongs_to", "uses_component", "targets_scenario", "depends_on", "competes_with"],
        "operation": ["operates_on", "depends_on", "uses_strategy", "reports_metric", "changes_metric", "targets_channel"],
    }
    return (
        f"Extract structured {labels.get(topic, topic)} information from the text below. "
        "Return JSON only with keys: entities, relations, facts, topics, signals, confidence, source_excerpt.\n"
        "entities: array of objects with at least text and type.\n"
        "relations: array of objects with subject, predicate, object; predicate should prefer allowed list.\n"
        "facts: array of typed fact objects (include fact_type).\n"
        "topics: short topic tags.\n"
        "signals: lightweight key-value summary.\n"
        "confidence: 0~1.\n"
        "If no strong signal exists, return empty arrays/objects with low confidence.\n"
        f"Preferred entity types: {entity_type_hints.get(topic, [])}\n"
        f"Preferred relation predicates: {relation_hints.get(topic, [])}\n\n"
        f"Text:\n{text_snippet[:3500]}"
    )


def _extract_topic(topic: str, text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if len(raw) < 20:
        return None
    try:
        config_key = f"{topic}_topic_extraction"
        config = get_llm_config(config_key)
        snippet = raw[:3500]
        if config and config.get("user_prompt_template"):
            prompt = format_prompt_template(config["user_prompt_template"], text=snippet, topic=topic)
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            prompt = _default_topic_prompt(topic, snippet)
            model = get_chat_model()
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        parsed = extract_json_payload(content)
        return _safe_topic_payload(parsed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_topic(%s) failed: %s", topic, exc, exc_info=True)
        return None


def extract_company_info(text: str) -> Optional[Dict[str, Any]]:
    return _extract_topic("company", text)


def extract_product_info(text: str) -> Optional[Dict[str, Any]]:
    return _extract_topic("product", text)


def extract_operation_info(text: str) -> Optional[Dict[str, Any]]:
    return _extract_topic("operation", text)

