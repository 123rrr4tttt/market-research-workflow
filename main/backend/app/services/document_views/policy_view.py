from __future__ import annotations

from typing import Any

from .common_view import get_entities, get_extracted_data, get_relations


def get_policy_data(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    policy = extracted.get("policy")
    return dict(policy) if isinstance(policy, dict) else {}


def get_policy_state(doc: Any) -> str | None:
    policy = get_policy_data(doc)
    state = str(policy.get("state") or getattr(doc, "state", "") or "").strip()
    return state or None


def get_policy_type(doc: Any) -> str | None:
    policy = get_policy_data(doc)
    policy_type = str(policy.get("policy_type") or "").strip()
    return policy_type or None


def get_policy_key_points(doc: Any) -> list[str]:
    policy = get_policy_data(doc)
    raw_value = policy.get("key_points")
    if not isinstance(raw_value, list):
        return []
    return [item.strip() for item in raw_value if isinstance(item, str) and item.strip()]


def get_policy_summary_text(doc: Any) -> str | None:
    summary = str(getattr(doc, "summary", "") or "").strip()
    if summary:
        return summary
    extracted = get_extracted_data(doc)
    fallback = str(extracted.get("summary") or "").strip()
    return fallback or None


def get_policy_entities(doc: Any) -> list[dict[str, Any]]:
    return get_entities(doc)


def get_policy_relations(doc: Any) -> list[dict[str, Any]]:
    return get_relations(doc)


def build_policy_summary(doc: Any) -> dict[str, Any]:
    policy = get_policy_data(doc)
    publish_date = getattr(doc, "publish_date", None)
    created_at = getattr(doc, "created_at", None)
    return {
        "id": getattr(doc, "id"),
        "title": getattr(doc, "title", None),
        "state": get_policy_state(doc),
        "status": getattr(doc, "status", None),
        "publish_date": publish_date.isoformat() if publish_date else None,
        "effective_date": policy.get("effective_date"),
        "policy_type": get_policy_type(doc),
        "key_points": get_policy_key_points(doc),
        "summary": get_policy_summary_text(doc),
        "uri": getattr(doc, "uri", None),
        "created_at": created_at.isoformat() if created_at else None,
    }


def build_policy_detail(doc: Any) -> dict[str, Any]:
    updated_at = getattr(doc, "updated_at", None)
    return {
        **build_policy_summary(doc),
        "content": getattr(doc, "content", None),
        "source_id": getattr(doc, "source_id", None),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "entities": get_policy_entities(doc),
        "relations": get_policy_relations(doc),
    }
