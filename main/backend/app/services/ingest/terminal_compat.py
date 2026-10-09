from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable, TypeGuard


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


def _safe_float(value: object) -> float:
    try:
        return float(value) if isinstance(value, (str, bytes, int, float)) else 0.0
    except (TypeError, ValueError):
        return 0.0


def apply_terminal_compat(extracted_data: dict[str, object]) -> dict[str, object]:
    out = dict(extracted_data or {})
    extraction = _object_dict(out.get("extraction"))
    domains = _object_dict(out.get("domains"))

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
        out["quality_score"] = _safe_float(extraction.get("quality_score"))
    if "degradation_flags" not in out:
        flags = extraction.get("degradation_flags")
        out["degradation_flags"] = list(flags) if _is_object_list(flags) else []
    if "platform" not in out:
        out["platform"] = str(out.get("platform") or "unknown")
    return out


__all__ = ["apply_terminal_compat"]
