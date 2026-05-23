from __future__ import annotations

from math import ceil
from typing import Any, Mapping

from .gate_reason_codes import normalize_reason_code
from .retry_policy import RETRY_CLASS_PERMANENT, RETRY_CLASS_TRANSIENT


CONTRACT_VERSION = "ingest.frontdoor_slo.v1"
TRI_STATE_STATUSES: tuple[str, ...] = ("success", "degraded_success", "failed")


def new_frontdoor_slo_summary() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "dashboard_status_counts": {status: 0 for status in TRI_STATE_STATUSES},
        "latency_ms_samples": [],
        "retryable_samples": 0,
        "retry_count_by_reason": {},
        "retry_count_by_class": {
            RETRY_CLASS_TRANSIENT: 0,
            RETRY_CLASS_PERMANENT: 0,
        },
    }


def _as_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:  # noqa: BLE001
        return 0
    return max(0, parsed)


def _as_non_negative_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:  # noqa: BLE001
        return None
    if parsed < 0:
        return None
    return parsed


def _normalize_dashboard_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in TRI_STATE_STATUSES:
        return status
    return "failed"


def _merge_counter(target: dict[str, int], key: Any, value: Any) -> None:
    normalized_key = normalize_reason_code(key, default="")
    if not normalized_key:
        return
    target[normalized_key] = _as_non_negative_int(target.get(normalized_key)) + _as_non_negative_int(value)


def _merge_retry_observability(summary: dict[str, Any], retry_observability: Mapping[str, Any]) -> None:
    reason_counts = retry_observability.get("retry_count_by_reason")
    if isinstance(reason_counts, Mapping):
        target_reason_counts = summary.setdefault("retry_count_by_reason", {})
        for reason, count in reason_counts.items():
            _merge_counter(target_reason_counts, reason, count)

    class_counts = retry_observability.get("retry_count_by_class")
    if isinstance(class_counts, Mapping):
        target_class_counts = summary.setdefault("retry_count_by_class", {})
        for klass in (RETRY_CLASS_TRANSIENT, RETRY_CLASS_PERMANENT):
            target_class_counts[klass] = _as_non_negative_int(target_class_counts.get(klass)) + _as_non_negative_int(
                class_counts.get(klass)
            )


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, ceil((float(percentile) / 100.0) * len(ordered)))
    return ordered[min(len(ordered) - 1, rank - 1)]


def record_frontdoor_slo_observation(
    summary: dict[str, Any],
    projection: Mapping[str, Any] | None,
) -> None:
    if not isinstance(summary, dict) or not isinstance(projection, Mapping):
        return

    status = _normalize_dashboard_status(projection.get("dashboard_status"))
    summary["sample_size"] = _as_non_negative_int(summary.get("sample_size")) + 1

    status_counts = summary.setdefault("dashboard_status_counts", {})
    if not isinstance(status_counts, dict):
        status_counts = {}
        summary["dashboard_status_counts"] = status_counts
    for allowed in TRI_STATE_STATUSES:
        status_counts.setdefault(allowed, 0)
    status_counts[status] = _as_non_negative_int(status_counts.get(status)) + 1

    latency_ms = _as_non_negative_float(projection.get("latency_ms"))
    if latency_ms is not None:
        samples = summary.setdefault("latency_ms_samples", [])
        if isinstance(samples, list):
            samples.append(latency_ms)

    retry_observability = projection.get("retry_observability")
    if isinstance(retry_observability, Mapping):
        _merge_retry_observability(summary, retry_observability)

    if bool(projection.get("retryable")):
        summary["retryable_samples"] = _as_non_negative_int(summary.get("retryable_samples")) + 1
        if not isinstance(retry_observability, Mapping):
            retry_counts = summary.setdefault("retry_count_by_reason", {})
            if isinstance(retry_counts, dict):
                _merge_counter(retry_counts, projection.get("reason_code") or "retryable", 1)


def build_frontdoor_slo_payload(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = summary if isinstance(summary, Mapping) else {}
    sample_size = _as_non_negative_int(raw.get("sample_size"))
    denominator = float(sample_size) if sample_size > 0 else 1.0
    raw_status_counts = raw.get("dashboard_status_counts") if isinstance(raw.get("dashboard_status_counts"), Mapping) else {}
    status_counts = {
        status: _as_non_negative_int(raw_status_counts.get(status))
        for status in TRI_STATE_STATUSES
    }
    latency_samples = [
        sample
        for sample in (_as_non_negative_float(item) for item in list(raw.get("latency_ms_samples") or []))
        if sample is not None
    ]
    p95_latency_ms = _percentile_nearest_rank(latency_samples, 95.0)
    retryable_samples = _as_non_negative_int(raw.get("retryable_samples"))
    retry_reason_counts = dict(raw.get("retry_count_by_reason") or {})
    retry_class_counts = dict(raw.get("retry_count_by_class") or {})

    return {
        "contract_version": CONTRACT_VERSION,
        "sample_size": sample_size,
        "dashboard_status_counts": status_counts,
        "success_or_degraded_rate": round(
            float(status_counts["success"] + status_counts["degraded_success"]) / denominator,
            6,
        )
        if sample_size > 0
        else 0.0,
        "failure_rate": round(float(status_counts["failed"]) / denominator, 6) if sample_size > 0 else 0.0,
        "latency_sample_size": len(latency_samples),
        "p95_latency_ms": round(float(p95_latency_ms), 3) if p95_latency_ms is not None else None,
        "retryable_samples": retryable_samples,
        "retryable_rate": round(float(retryable_samples) / denominator, 6) if sample_size > 0 else 0.0,
        "retry_count_by_reason": {
            normalize_reason_code(reason, default="unknown_retry_reason"): _as_non_negative_int(count)
            for reason, count in retry_reason_counts.items()
            if _as_non_negative_int(count) > 0
        },
        "retry_count_by_class": {
            RETRY_CLASS_TRANSIENT: _as_non_negative_int(retry_class_counts.get(RETRY_CLASS_TRANSIENT)),
            RETRY_CLASS_PERMANENT: _as_non_negative_int(retry_class_counts.get(RETRY_CLASS_PERMANENT)),
        },
        "live_24h_claim": False,
        "closure_claim": False,
    }


__all__ = [
    "CONTRACT_VERSION",
    "TRI_STATE_STATUSES",
    "build_frontdoor_slo_payload",
    "new_frontdoor_slo_summary",
    "record_frontdoor_slo_observation",
]
