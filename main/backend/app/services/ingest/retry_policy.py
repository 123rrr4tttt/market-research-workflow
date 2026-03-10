from __future__ import annotations

from typing import Any

from .gate_reason_codes import normalize_reason_code

RETRY_CLASS_TRANSIENT = "transient"
RETRY_CLASS_PERMANENT = "permanent"

_REASON_CLASS_MAP: dict[str, str] = {
    "ok": RETRY_CLASS_PERMANENT,
    "invalid_url": RETRY_CLASS_PERMANENT,
    "domain_blocked": RETRY_CLASS_PERMANENT,
    "robots_disallow": RETRY_CLASS_PERMANENT,
    "url_policy_blocked": RETRY_CLASS_PERMANENT,
    "url_policy_low_value_domain": RETRY_CLASS_PERMANENT,
    "url_policy_low_value_endpoint": RETRY_CLASS_PERMANENT,
    "content_empty": RETRY_CLASS_PERMANENT,
    "content_semantic_too_short": RETRY_CLASS_PERMANENT,
    "content_shell_signature": RETRY_CLASS_PERMANENT,
    "content_js_template_shell": RETRY_CLASS_PERMANENT,
    "content_navigation_shell": RETRY_CLASS_PERMANENT,
    "strict_mode_quality_gate": RETRY_CLASS_PERMANENT,
    "search_template_results_insufficient": RETRY_CLASS_PERMANENT,
    "provenance_untrusted_domain": RETRY_CLASS_PERMANENT,
    "provenance_missing_citation": RETRY_CLASS_PERMANENT,
    "provenance_gate_rejected": RETRY_CLASS_PERMANENT,
    "light_filter_rejected": RETRY_CLASS_PERMANENT,
    "rate_limited": RETRY_CLASS_TRANSIENT,
    "http_429": RETRY_CLASS_TRANSIENT,
    "fetch_failed": RETRY_CLASS_TRANSIENT,
    "unexpected_exception": RETRY_CLASS_TRANSIENT,
    "crawler_pool_dispatch_failed": RETRY_CLASS_TRANSIENT,
    "search_provider_fetch_failed": RETRY_CLASS_TRANSIENT,
    "search_fallback_fetch_failed": RETRY_CLASS_TRANSIENT,
    "crawler_dispatch_retry": RETRY_CLASS_TRANSIENT,
}

_TRANSIENT_MARKERS = (
    "timeout",
    "tempor",
    "transient",
    "connection",
    "network",
    "server_error",
    "http_5",
    "rate_limit",
)


def classify_retry_reason(reason: Any) -> tuple[str, str]:
    normalized = normalize_reason_code(reason, default="unknown_retry_reason")
    mapped = _REASON_CLASS_MAP.get(normalized)
    if mapped:
        return normalized, mapped
    if any(marker in normalized for marker in _TRANSIENT_MARKERS):
        return normalized, RETRY_CLASS_TRANSIENT
    return normalized, RETRY_CLASS_PERMANENT


def build_retry_observability(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    reason_counts: dict[str, int] = {}

    def _add(reason: Any, count: Any = 1) -> None:
        normalized, _ = classify_retry_reason(reason)
        if normalized in {"", "ok", "unknown_retry_reason"}:
            return
        try:
            parsed = int(count)
        except Exception:  # noqa: BLE001
            parsed = 0
        if parsed <= 0:
            return
        reason_counts[normalized] = int(reason_counts.get(normalized, 0)) + parsed

    existing_reason_counts = data.get("retry_count_by_reason")
    if isinstance(existing_reason_counts, dict) and existing_reason_counts:
        for reason, count in existing_reason_counts.items():
            _add(reason, count)
    else:
        retry_reasons = data.get("retry_reasons")
        if isinstance(retry_reasons, dict):
            for reason, count in retry_reasons.items():
                _add(reason, count)
        elif isinstance(retry_reasons, list):
            for reason in retry_reasons:
                _add(reason, 1)

        retry_events = data.get("retry_events")
        if isinstance(retry_events, list):
            for event in retry_events:
                if isinstance(event, dict):
                    _add(event.get("reason"), event.get("count", 1))

        rejection_breakdown = data.get("rejection_breakdown")
        if isinstance(rejection_breakdown, dict):
            for reason, count in rejection_breakdown.items():
                normalized, klass = classify_retry_reason(reason)
                if klass == RETRY_CLASS_TRANSIENT:
                    _add(normalized, count)

        crawler_dispatch = data.get("crawler_dispatch")
        if isinstance(crawler_dispatch, dict):
            attempts = int(crawler_dispatch.get("attempt_count") or 0)
            if attempts > 1:
                _add(crawler_dispatch.get("retry_reason") or "crawler_dispatch_retry", attempts - 1)

    class_counts = {
        RETRY_CLASS_TRANSIENT: 0,
        RETRY_CLASS_PERMANENT: 0,
    }
    for reason, count in reason_counts.items():
        _, klass = classify_retry_reason(reason)
        class_counts[klass] += int(count)

    reason_code = data.get("reason_code")
    _, reason_code_class = classify_retry_reason(reason_code)
    retryable = bool(reason_code_class == RETRY_CLASS_TRANSIENT or class_counts[RETRY_CLASS_TRANSIENT] > 0)

    return {
        "retry_count_by_reason": reason_counts,
        "retry_count_by_class": class_counts,
        "retryable": retryable,
        "reason_code_class": reason_code_class,
    }


__all__ = [
    "RETRY_CLASS_PERMANENT",
    "RETRY_CLASS_TRANSIENT",
    "build_retry_observability",
    "classify_retry_reason",
]
