from __future__ import annotations

from typing import Any, TypeGuard


def is_payload_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def payload_dict_or_empty(value: object) -> dict[str, object]:
    return dict(value) if is_payload_dict(value) else {}


def get_extracted_data(doc: Any) -> dict[str, Any]:
    extracted = getattr(doc, "extracted_data", None)
    return payload_dict_or_empty(extracted)


def get_entities_relations(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    value = extracted.get("entities_relations")
    return payload_dict_or_empty(value)


def get_entities(doc: Any) -> list[dict[str, Any]]:
    entities_relations = get_entities_relations(doc)
    entities = entities_relations.get("entities")
    if is_object_list(entities):
        return [item for item in entities if is_payload_dict(item)]

    extracted = get_extracted_data(doc)
    legacy_entities = extracted.get("entities")
    if is_object_list(legacy_entities):
        return [item for item in legacy_entities if is_payload_dict(item)]
    return []


def get_relations(doc: Any) -> list[dict[str, Any]]:
    entities_relations = get_entities_relations(doc)
    relations = entities_relations.get("relations")
    if is_object_list(relations):
        return [item for item in relations if is_payload_dict(item)]
    return []


def get_platform(doc: Any) -> str | None:
    extracted = get_extracted_data(doc)
    platform = str(extracted.get("platform") or "").strip().lower()
    return platform or None
