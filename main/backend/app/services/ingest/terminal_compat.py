from __future__ import annotations

from typing import Any


def apply_terminal_compat(extracted_data: dict[str, Any]) -> dict[str, Any]:
    out = dict(extracted_data or {})
    extraction = out.get("extraction") if isinstance(out.get("extraction"), dict) else {}
    domains = out.get("domains") if isinstance(out.get("domains"), dict) else {}

    for field in ("policy", "market", "sentiment", "entities_relations", "entities", "company_structured", "product_structured", "operation_structured"):
        value = domains.get(field)
        if value is None and field in out:
            continue
        if value is not None:
            out[field] = value

    if "structured_extraction_status" not in out:
        out["structured_extraction_status"] = str(extraction.get("status") or "skipped").strip().lower() or "skipped"
    if extraction.get("reason") and "structured_extraction_reason" not in out:
        out["structured_extraction_reason"] = extraction.get("reason")
    if "quality_score" not in out:
        out["quality_score"] = float(extraction.get("quality_score") or 0.0)
    if "degradation_flags" not in out:
        out["degradation_flags"] = list(extraction.get("degradation_flags") or [])
    if "platform" not in out:
        out["platform"] = str(out.get("platform") or "unknown")
    return out


__all__ = ["apply_terminal_compat"]
