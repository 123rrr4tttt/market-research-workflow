from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Protocol, Iterable, runtime_checkable, TypeGuard


class StructuredExtractor(Protocol):
    def extract_structured_enriched(
        self,
        text: str,
        *,
        include_market: bool,
        include_policy: bool,
        include_sentiment: bool,
        include_company: bool,
        include_product: bool,
        include_operation: bool,
    ) -> object: ...


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


@dataclass(frozen=True)
class StructuredExtractionResult:
    data: dict[str, object]
    status: str
    reason: str | None
    error: str | None


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


def extract_structured_enriched_safe(
    *,
    extraction_app: StructuredExtractor,
    payload: str,
    include_market: bool = True,
    include_policy: bool = True,
    include_sentiment: bool = True,
    include_company: bool = True,
    include_product: bool = True,
    include_operation: bool = True,
) -> StructuredExtractionResult:
    try:
        enriched = extraction_app.extract_structured_enriched(
            payload,
            include_market=include_market,
            include_policy=include_policy,
            include_sentiment=include_sentiment,
            include_company=include_company,
            include_product=include_product,
            include_operation=include_operation,
        )
    except Exception as exc:  # noqa: BLE001
        return StructuredExtractionResult(data={}, status="failed", reason="extractor_exception", error=str(exc))
    if _is_object_dict(enriched) and enriched:
        return StructuredExtractionResult(data=dict(enriched), status="ok", reason=None, error=None)
    return StructuredExtractionResult(data={}, status="failed", reason="empty_structured_output", error=None)
