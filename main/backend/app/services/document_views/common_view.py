from __future__ import annotations

from typing import Any


def get_extracted_data(doc: Any) -> dict[str, Any]:
    extracted = getattr(doc, "extracted_data", None)
    return dict(extracted) if isinstance(extracted, dict) else {}


def get_entities_relations(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    value = extracted.get("entities_relations")
    return dict(value) if isinstance(value, dict) else {}


def get_entities(doc: Any) -> list[dict[str, Any]]:
    entities_relations = get_entities_relations(doc)
    entities = entities_relations.get("entities")
    if isinstance(entities, list):
        return [item for item in entities if isinstance(item, dict)]

    extracted = get_extracted_data(doc)
    legacy_entities = extracted.get("entities")
    if isinstance(legacy_entities, list):
        return [item for item in legacy_entities if isinstance(item, dict)]
    return []


def get_relations(doc: Any) -> list[dict[str, Any]]:
    entities_relations = get_entities_relations(doc)
    relations = entities_relations.get("relations")
    if isinstance(relations, list):
        return [item for item in relations if isinstance(item, dict)]
    return []


def get_platform(doc: Any) -> str | None:
    extracted = get_extracted_data(doc)
    platform = str(extracted.get("platform") or "").strip().lower()
    return platform or None
