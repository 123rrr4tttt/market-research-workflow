from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredExtractionResult:
    data: dict[str, Any]
    status: str
    reason: str | None
    error: str | None


def build_structured_summary(
    extracted_data: dict[str, Any],
    *,
    extraction_enabled: bool,
    chunks_used: int,
    extraction_mode: str,
) -> dict[str, Any]:
    er = extracted_data.get("entities_relations")
    entities = er.get("entities") if isinstance(er, dict) else []
    relations = er.get("relations") if isinstance(er, dict) else []
    return {
        "extraction_enabled": bool(extraction_enabled),
        "extraction_mode": extraction_mode,
        "chunks_used": int(chunks_used),
        "entity_count": len(entities) if isinstance(entities, list) else 0,
        "relation_count": len(relations) if isinstance(relations, list) else 0,
        "has_policy": isinstance(extracted_data.get("policy"), dict),
        "has_market": isinstance(extracted_data.get("market"), dict),
        "has_sentiment": isinstance(extracted_data.get("sentiment"), dict),
        "has_company": isinstance(extracted_data.get("company_structured"), dict),
        "has_product": isinstance(extracted_data.get("product_structured"), dict),
        "has_operation": isinstance(extracted_data.get("operation_structured"), dict),
    }


def extract_structured_enriched_safe(
    *,
    extraction_app: Any,
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
    if isinstance(enriched, dict) and enriched:
        return StructuredExtractionResult(data=dict(enriched), status="ok", reason=None, error=None)
    return StructuredExtractionResult(data={}, status="failed", reason="empty_structured_output", error=None)

