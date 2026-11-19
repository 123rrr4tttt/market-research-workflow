from __future__ import annotations

from typing import Annotated, Protocol, Iterable, runtime_checkable, TypeGuard


def _is_string_key(value: object) -> bool:
    return isinstance(value, str)


@runtime_checkable
class _StringKeyInspectable(Protocol):
    def keys(self) -> Iterable[object]: ...


def _has_only_string_keys(value: object) -> bool:
    if not isinstance(value, _StringKeyInspectable):
        return False
    return all(map(_is_string_key, value.keys()))


def _is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not _has_only_string_keys(value):
        return False
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def build_structured_summary(
    extracted_data: dict[str, object],
    *,
    extraction_enabled: bool,
    chunks_used: int,
    extraction_mode: str,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=extracted_data+extraction_outcome_inputs witness=test:test_ingest_ports_declare_sources_and_effect_authority",
]:
    er = extracted_data.get("entities_relations")
    typed_er = er if _is_object_dict(er) else {}
    entities = typed_er.get("entities")
    relations = typed_er.get("relations")
    return {
        "extraction_enabled": bool(extraction_enabled),
        "extraction_mode": extraction_mode,
        "chunks_used": int(chunks_used),
        "entity_count": len(entities) if _is_object_list(entities) else 0,
        "relation_count": len(relations) if _is_object_list(relations) else 0,
        "has_policy": isinstance(extracted_data.get("policy"), dict),
        "has_market": isinstance(extracted_data.get("market"), dict),
        "has_sentiment": isinstance(extracted_data.get("sentiment"), dict),
        "has_company": isinstance(extracted_data.get("company_structured"), dict),
        "has_product": isinstance(extracted_data.get("product_structured"), dict),
        "has_operation": isinstance(extracted_data.get("operation_structured"), dict),
    }
