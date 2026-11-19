from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Iterable, Protocol, runtime_checkable, TypeGuard


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


def _object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _copy_or_empty(value: object) -> object:
    return deepcopy(value) if value else {}


def build_terminal_material_payload(
    *,
    material_candidate: dict[str, object],
    ingress_envelope: dict[str, object],
    extraction_outcome: dict[str, object],
    terminal_context: dict[str, object] | None = None,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=material_candidate+ingress_envelope+extraction_outcome+terminal_context witness=test:test_ingest_ports_declare_sources_and_effect_authority",
]:
    candidate = dict(material_candidate or {})
    ingress = dict(ingress_envelope or {})
    extraction = dict(extraction_outcome or {})
    context = dict(terminal_context or {})

    extracted_data = _object_dict(candidate.get("extracted_data_base"))
    domains = _object_dict(extraction.get("domains"))
    extracted_data.update(domains)

    structured_status = _normalize_extraction_status(
        extraction.get("status")
        or extracted_data.get("structured_extraction_status")
        or extracted_data.get("extraction_status")
    )
    structured_reason = extraction.get("reason") or extracted_data.get("structured_extraction_reason") or extracted_data.get("extraction_reason")
    quality_score = _safe_float(context.get("quality_score"), default=_safe_float(extracted_data.get("quality_score"), default=0.0))
    degradation_flags = _normalize_flags(context.get("degradation_flags") or extracted_data.get("degradation_flags"))

    source_ref = _object_dict(extracted_data.get("source_ref"))
    source_ref.update(_object_dict(ingress.get("source_ref")))
    if candidate.get("uri") and "url" not in source_ref:
        source_ref["url"] = candidate.get("uri")

    extracted_data["schema_version"] = "terminal.ingest.v1.1"
    extracted_data["platform"] = str(context.get("platform") or extracted_data.get("platform") or ingress.get("ingress_type") or "unknown")
    extracted_data["source_ref"] = source_ref
    extracted_data["ingestion_entrypoint"] = str(
        context.get("ingestion_entrypoint") or ingress.get("entrypoint") or extracted_data.get("ingestion_entrypoint") or "unknown"
    )
    extracted_data["source_mode"] = str(context.get("source_mode") or ingress.get("source_mode") or extracted_data.get("source_mode") or "unknown")
    extracted_data["structured_extraction_status"] = structured_status
    if structured_reason:
        extracted_data["structured_extraction_reason"] = str(structured_reason)
    extracted_data["quality_score"] = quality_score
    extracted_data["degradation_flags"] = degradation_flags
    extracted_data["extraction"] = {
        "status": structured_status,
        "reason": str(structured_reason or "").strip() or None,
        "error": extraction.get("error"),
        "extractor_version": str(extraction.get("extractor_version") or "unified.structured.v1"),
        "model_profile": _copy_or_empty(extraction.get("model_profile")),
        "prompt_profile": _copy_or_empty(extraction.get("prompt_profile")),
        "structured_output_mode": str(extraction.get("structured_output_mode") or "unknown"),
        "quality_score": quality_score,
        "degradation_flags": degradation_flags,
        "http_status": _safe_int(context.get("http_status")),
        "capability_profile": _copy_or_empty(context.get("capability_profile")),
        "light_filter": _copy_or_empty(context.get("light_filter")),
        "summary": _copy_or_empty(extraction.get("summary")),
    }
    extracted_data["terminal"] = {
        "ingestion_entrypoint": extracted_data["ingestion_entrypoint"],
        "source_mode": extracted_data["source_mode"],
        "ingress_type": str(ingress.get("ingress_type") or "unknown"),
        "project_key": ingress.get("project_key"),
        "trace_id": _object_dict(ingress.get("meta")).get("trace_id"),
    }
    extracted_data["domains"] = {
        "policy": deepcopy(domains.get("policy") if isinstance(domains.get("policy"), dict) else extracted_data.get("policy")),
        "market": deepcopy(domains.get("market") if isinstance(domains.get("market"), dict) else extracted_data.get("market")),
        "sentiment": deepcopy(domains.get("sentiment") if isinstance(domains.get("sentiment"), dict) else extracted_data.get("sentiment")),
        "entities_relations": deepcopy(
            domains.get("entities_relations") if isinstance(domains.get("entities_relations"), dict) else extracted_data.get("entities_relations")
        ),
        "entities": deepcopy(domains.get("entities") if isinstance(domains.get("entities"), list) else extracted_data.get("entities")),
        "company_structured": deepcopy(
            domains.get("company_structured") if isinstance(domains.get("company_structured"), dict) else extracted_data.get("company_structured")
        ),
        "product_structured": deepcopy(
            domains.get("product_structured") if isinstance(domains.get("product_structured"), dict) else extracted_data.get("product_structured")
        ),
        "operation_structured": deepcopy(
            domains.get("operation_structured") if isinstance(domains.get("operation_structured"), dict) else extracted_data.get("operation_structured")
        ),
    }

    return {
        "source_name": str(candidate.get("source_name") or extracted_data.get("platform") or ingress.get("ingress_type") or "unknown"),
        "source_kind": str(candidate.get("source_kind") or "external"),
        "source_base_url": candidate.get("source_base_url"),
        "material_type": str(candidate.get("material_type") or "unknown"),
        "title": candidate.get("title"),
        "summary": candidate.get("summary"),
        "content": candidate.get("content"),
        "uri": candidate.get("uri"),
        "publish_date": candidate.get("publish_date"),
        "text_hash": candidate.get("text_hash"),
        "state": candidate.get("state"),
        "status": candidate.get("status"),
        "extracted_data": extracted_data,
    }


def _normalize_extraction_status(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"ok", "partial", "failed", "skipped"}:
        return raw
    if raw == "fallback":
        return "partial"
    return "skipped"


def _normalize_flags(value: object) -> list[str]:
    if not value:
        return []
    values = value if _is_object_list(value) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _safe_float(value: object, *, default: float) -> float:
    if not isinstance(value, (str, bytes, int, float)):
        return float(default)
    try:
        return float(value)
    except (OverflowError, TypeError, ValueError):
        return float(default)


def _safe_int(value: object) -> int | None:
    if not isinstance(value, (str, bytes, int, float)):
        return None
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        return None


__all__ = ["build_terminal_material_payload"]
