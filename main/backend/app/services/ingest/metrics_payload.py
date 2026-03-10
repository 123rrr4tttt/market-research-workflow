from __future__ import annotations

from typing import Any

from .gate_reason_codes import normalize_reason_code

_SCHEMA_VERSION = "a9.v1"
_WINDOW = "task_local"
_DEFAULT_TOP_N = 5
_EMPTY_BODY_REASON_CODES = {
    "content_empty",
    "fetch_failed",
    "search_template_results_insufficient",
}


def new_metrics_summary() -> dict[str, Any]:
    return {
        "total_samples": 0,
        "url_only_documents": 0,
        "empty_body_documents": 0,
        "reason_code_counts": {},
        "adapter_hit_counts": {},
    }


def _coerce_non_negative_int(value: Any) -> int:
    try:
        num = int(value)
    except Exception:
        return 0
    return max(0, num)


def _merge_counter(counter: dict[str, int], key: str, delta: int = 1) -> None:
    name = str(key or "").strip()
    if not name:
        return
    counter[name] = _coerce_non_negative_int(counter.get(name)) + max(0, int(delta))


def _primary_reason_code(result: dict[str, Any]) -> str:
    reason = normalize_reason_code(result.get("reason_code"), default="ok")
    if reason and reason != "ok":
        return reason
    breakdown = result.get("rejection_breakdown")
    if isinstance(breakdown, dict) and breakdown:
        top_key = sorted(
            (
                (normalize_reason_code(k, default="unknown_rejection_reason"), _coerce_non_negative_int(v))
                for k, v in breakdown.items()
            ),
            key=lambda item: item[1],
            reverse=True,
        )[0][0]
        return normalize_reason_code(top_key, default="ok")
    return "ok"


def _adapter_name(result: dict[str, Any], *, fallback_adapter: str | None = None) -> str:
    allocation = result.get("handler_allocation")
    if isinstance(allocation, dict):
        handler_used = str(allocation.get("handler_used") or "").strip()
        if handler_used:
            return handler_used
    workflow = str(result.get("single_write_workflow") or "").strip()
    if workflow:
        return workflow
    fallback = str(fallback_adapter or "").strip()
    return fallback or "unknown"


def record_metrics_observation(
    summary: dict[str, Any],
    result: dict[str, Any] | None,
    *,
    fallback_adapter: str | None = None,
) -> None:
    if not isinstance(result, dict):
        return

    summary["total_samples"] = _coerce_non_negative_int(summary.get("total_samples")) + 1

    inserted_valid = _coerce_non_negative_int(result.get("inserted_valid"))
    is_url_only = inserted_valid <= 0
    if is_url_only:
        summary["url_only_documents"] = _coerce_non_negative_int(summary.get("url_only_documents")) + 1

    reason_code = _primary_reason_code(result)
    if reason_code in _EMPTY_BODY_REASON_CODES:
        summary["empty_body_documents"] = _coerce_non_negative_int(summary.get("empty_body_documents")) + 1

    reason_counts = summary.get("reason_code_counts")
    if not isinstance(reason_counts, dict):
        reason_counts = {}
        summary["reason_code_counts"] = reason_counts
    _merge_counter(reason_counts, reason_code, 1)

    adapter_counts = summary.get("adapter_hit_counts")
    if not isinstance(adapter_counts, dict):
        adapter_counts = {}
        summary["adapter_hit_counts"] = adapter_counts
    _merge_counter(adapter_counts, _adapter_name(result, fallback_adapter=fallback_adapter), 1)


def build_metrics_payload_from_summary(
    summary: dict[str, Any] | None,
    *,
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, Any]:
    base = new_metrics_summary()
    if isinstance(summary, dict):
        base["total_samples"] = _coerce_non_negative_int(summary.get("total_samples"))
        base["url_only_documents"] = _coerce_non_negative_int(summary.get("url_only_documents"))
        base["empty_body_documents"] = _coerce_non_negative_int(summary.get("empty_body_documents"))
        base["reason_code_counts"] = dict(summary.get("reason_code_counts") or {})
        base["adapter_hit_counts"] = dict(summary.get("adapter_hit_counts") or {})

    total = _coerce_non_negative_int(base["total_samples"])
    denominator = float(total) if total > 0 else 1.0
    top_limit = max(1, int(top_n))

    reason_top = sorted(
        (
            (normalize_reason_code(k, default="unknown_rejection_reason"), _coerce_non_negative_int(v))
            for k, v in dict(base["reason_code_counts"]).items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:top_limit]
    adapter_top = sorted(
        ((str(k), _coerce_non_negative_int(v)) for k, v in dict(base["adapter_hit_counts"]).items()),
        key=lambda item: item[1],
        reverse=True,
    )[:top_limit]

    return {
        "schema_version": _SCHEMA_VERSION,
        "window": _WINDOW,
        "sample_size": total,
        "url_only_document_rate": round(float(base["url_only_documents"]) / denominator, 6) if total > 0 else 0.0,
        "empty_body_rate": round(float(base["empty_body_documents"]) / denominator, 6) if total > 0 else 0.0,
        "reason_code_top_n": [
            {
                "reason_code": reason_code,
                "count": count,
                "rate": round(float(count) / denominator, 6) if total > 0 else 0.0,
            }
            for reason_code, count in reason_top
        ],
        "adapter_hit_rate": [
            {
                "adapter": adapter,
                "count": count,
                "rate": round(float(count) / denominator, 6) if total > 0 else 0.0,
            }
            for adapter, count in adapter_top
        ],
        "counters": {
            "total_samples": total,
            "url_only_documents": _coerce_non_negative_int(base["url_only_documents"]),
            "empty_body_documents": _coerce_non_negative_int(base["empty_body_documents"]),
        },
    }


def build_metrics_payload_for_result(
    result: dict[str, Any] | None,
    *,
    fallback_adapter: str | None = None,
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, Any]:
    summary = new_metrics_summary()
    record_metrics_observation(summary, result, fallback_adapter=fallback_adapter)
    return build_metrics_payload_from_summary(summary, top_n=top_n)


def attach_metrics_payload(
    result: dict[str, Any] | None,
    payload: dict[str, Any],
) -> None:
    if not isinstance(result, dict):
        return

    meta = result.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        result["meta"] = meta
    meta["metrics_payload"] = payload

    debug = result.get("debug")
    if not isinstance(debug, dict):
        debug = {}
        result["debug"] = debug
    debug["metrics_payload"] = payload
