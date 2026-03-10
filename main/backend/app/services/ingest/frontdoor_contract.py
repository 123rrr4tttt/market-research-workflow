from __future__ import annotations

from typing import Any, Iterable, Mapping

from .gate_reason_codes import normalize_reason_code, reason_category

FRONTDOOR_STAGES: tuple[str, ...] = (
    "unwrap",
    "gate",
    "fetch",
    "extract",
    "quality",
    "persist",
)


def _normalize_stage(stage: str | None, *, default: str = "unwrap") -> str:
    raw = str(stage or "").strip().lower()
    return raw if raw in FRONTDOOR_STAGES else default


def _normalize_status(status: str | None, *, default: str = "success") -> str:
    raw = str(status or "").strip().lower()
    return raw or default


def _normalize_text(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def _normalize_flags(flags: Iterable[Any] | None) -> list[str]:
    if not flags:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in flags:
        flag = str(item or "").strip()
        if not flag or flag in seen:
            continue
        seen.add(flag)
        normalized.append(flag)
    return normalized


def _normalize_diagnostics(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def build_frontdoor_envelope(
    *,
    status: str = "success",
    reason_code: str = "ok",
    stage: str = "unwrap",
    retryable: bool = False,
    trace_id: str | None = None,
    request_key: str | None = None,
    degradation_flags: Iterable[Any] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_reason = normalize_reason_code(reason_code, default="ok")
    envelope = {
        "status": _normalize_status(status),
        "reason_code": normalized_reason,
        "reason_category": "none" if normalized_reason == "ok" else reason_category(normalized_reason),
        "stage": _normalize_stage(stage),
        "retryable": bool(retryable),
        "trace_id": _normalize_text(trace_id),
        "request_key": _normalize_text(request_key),
        "degradation_flags": _normalize_flags(degradation_flags),
        "diagnostics": _normalize_diagnostics(diagnostics),
    }
    if extra:
        envelope.update(dict(extra))
    return envelope


def apply_stage_update(
    envelope: dict[str, Any],
    *,
    stage: str,
    update: Mapping[str, Any] | None,
) -> dict[str, Any]:
    next_update = dict(update or {})
    current_diag = _normalize_diagnostics(envelope.get("diagnostics"))
    update_diag = _normalize_diagnostics(next_update.get("diagnostics"))
    merged_diag = dict(current_diag)
    merged_diag.update(update_diag)

    current_flags = _normalize_flags(envelope.get("degradation_flags"))
    merged_flags = _normalize_flags([*current_flags, *list(next_update.get("degradation_flags") or [])])

    reason = next_update.get("reason_code", envelope.get("reason_code"))
    normalized_reason = normalize_reason_code(reason, default="ok")

    envelope["status"] = _normalize_status(next_update.get("status", envelope.get("status")))
    envelope["reason_code"] = normalized_reason
    envelope["reason_category"] = "none" if normalized_reason == "ok" else reason_category(normalized_reason)
    envelope["stage"] = _normalize_stage(next_update.get("stage", stage), default=_normalize_stage(stage))
    envelope["retryable"] = bool(next_update.get("retryable", envelope.get("retryable", False)))
    envelope["trace_id"] = _normalize_text(next_update.get("trace_id", envelope.get("trace_id")))
    envelope["request_key"] = _normalize_text(next_update.get("request_key", envelope.get("request_key")))
    envelope["degradation_flags"] = merged_flags
    envelope["diagnostics"] = merged_diag

    for key, value in next_update.items():
        if key in {
            "status",
            "reason_code",
            "reason_category",
            "stage",
            "retryable",
            "trace_id",
            "request_key",
            "degradation_flags",
            "diagnostics",
        }:
            continue
        envelope[key] = value
    return envelope


__all__ = [
    "FRONTDOOR_STAGES",
    "apply_stage_update",
    "build_frontdoor_envelope",
]
