from __future__ import annotations

from collections.abc import Mapping
from math import ceil
from typing import Annotated, Iterable, Protocol, runtime_checkable, TypeGuard

from .gate_reason_codes import normalize_reason_code
from .retry_policy import RETRY_CLASS_PERMANENT, RETRY_CLASS_TRANSIENT


CONTRACT_VERSION = "ingest.frontdoor_slo.v1"
TRI_STATE_STATUSES: tuple[str, ...] = ("success", "degraded_success", "failed")


def _is_string_key(value: object) -> bool:
    return isinstance(value, str)


@runtime_checkable
class _StringKeyInspectable(Protocol):
    def keys(self) -> Iterable[object]: ...


def _has_only_string_keys(value: object) -> bool:
    if not isinstance(value, _StringKeyInspectable):
        return False
    return all(map(_is_string_key, value.keys()))


def _is_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not _has_only_string_keys(value):
        return False
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_mapping(value: object) -> Mapping[str, object]:
    return value if _is_object_mapping(value) else {}


def _int_counter(value: object) -> dict[str, int]:
    return {key: _as_non_negative_int(item) for key, item in _object_mapping(value).items()}


def new_frontdoor_slo_summary() -> dict[str, object]:
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


def _as_non_negative_int(value: object) -> int:
    try:
        parsed = int(value) if isinstance(value, (str, bytes, int, float)) else 0
    except Exception:  # noqa: BLE001
        return 0
    return max(0, parsed)


def _as_non_negative_float(value: object) -> float | None:
    try:
        parsed = float(value) if isinstance(value, (str, bytes, int, float)) else -1.0
    except Exception:  # noqa: BLE001
        return None
    if parsed < 0:
        return None
    return parsed


def _normalize_dashboard_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in TRI_STATE_STATUSES:
        return status
    return "failed"


def _merge_counter(target: dict[str, int], key: object, value: object) -> None:
    normalized_key = normalize_reason_code(key, default="")
    if not normalized_key:
        return
    target[normalized_key] = _as_non_negative_int(target.get(normalized_key)) + _as_non_negative_int(value)


def _merge_retry_observability(summary: dict[str, object], retry_observability: Mapping[str, object]) -> None:
    reason_counts = _object_mapping(retry_observability.get("retry_count_by_reason"))
    if reason_counts:
        target_reason_counts = _int_counter(summary.get("retry_count_by_reason"))
        summary["retry_count_by_reason"] = target_reason_counts
        for reason, count in reason_counts.items():
            _merge_counter(target_reason_counts, reason, count)

    class_counts = retry_observability.get("retry_count_by_class")
    if _is_object_mapping(class_counts):
        target_class_counts = _int_counter(summary.get("retry_count_by_class"))
        summary["retry_count_by_class"] = target_class_counts
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
    summary: dict[str, object],
    projection: Mapping[str, object] | None,
) -> None:
    if projection is None:
        return

    status = _normalize_dashboard_status(projection.get("dashboard_status"))
    summary["sample_size"] = _as_non_negative_int(summary.get("sample_size")) + 1

    status_counts = _int_counter(summary.get("dashboard_status_counts"))
    summary["dashboard_status_counts"] = status_counts
    for allowed in TRI_STATE_STATUSES:
        status_counts.setdefault(allowed, 0)
    status_counts[status] = _as_non_negative_int(status_counts.get(status)) + 1

    latency_ms = _as_non_negative_float(projection.get("latency_ms"))
    if latency_ms is not None:
        raw_samples = summary.get("latency_ms_samples")
        samples = [float(item) for item in raw_samples if isinstance(item, (int, float))] if _is_object_list(raw_samples) else []
        samples.append(latency_ms)
        summary["latency_ms_samples"] = samples

    retry_observability = projection.get("retry_observability")
    if _is_object_mapping(retry_observability):
        _merge_retry_observability(summary, retry_observability)

    if bool(projection.get("retryable")):
        summary["retryable_samples"] = _as_non_negative_int(summary.get("retryable_samples")) + 1
        if not _is_object_mapping(retry_observability):
            retry_counts = _int_counter(summary.get("retry_count_by_reason"))
            summary["retry_count_by_reason"] = retry_counts
            _merge_counter(retry_counts, projection.get("reason_code") or "retryable", 1)


def build_frontdoor_slo_payload(summary: Mapping[str, object] | None) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=summary+tri_state_contract+latency_samples witness=test:test_ingest_ports_declare_sources_and_effect_authority",
]:
    raw = summary or {}
    sample_size = _as_non_negative_int(raw.get("sample_size"))
    denominator = float(sample_size) if sample_size > 0 else 1.0
    raw_status_counts = _object_mapping(raw.get("dashboard_status_counts"))
    status_counts = {
        status: _as_non_negative_int(raw_status_counts.get(status))
        for status in TRI_STATE_STATUSES
    }
    raw_latency_samples = raw.get("latency_ms_samples")
    latency_items = raw_latency_samples if _is_object_list(raw_latency_samples) else []
    latency_samples = [
        sample
        for sample in (
            _as_non_negative_float(item)
            for item in latency_items
        )
        if sample is not None
    ]
    p95_latency_ms = _percentile_nearest_rank(latency_samples, 95.0)
    retryable_samples = _as_non_negative_int(raw.get("retryable_samples"))
    retry_reason_counts = _int_counter(raw.get("retry_count_by_reason"))
    retry_class_counts = _int_counter(raw.get("retry_count_by_class"))

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
