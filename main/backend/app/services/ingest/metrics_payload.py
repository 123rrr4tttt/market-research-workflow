from __future__ import annotations

from typing import Annotated, Iterable, Protocol, runtime_checkable, TypeGuard

from .gate_reason_codes import normalize_reason_code
from .guardrail_rollout import ROLLOUT_CONTRACT_VERSION

_SCHEMA_VERSION = "a9.v1"
_GUARDRAIL_METRICS_CONTRACT_VERSION = "ingest.guardrail_rollout.metrics.v1"
_WINDOW = "task_local"
_DEFAULT_TOP_N = 5
_EMPTY_BODY_REASON_CODES = {
    "content_empty",
    "fetch_failed",
    "search_template_results_insufficient",
}


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


def _int_counter(value: object) -> dict[str, int]:
    return {key: _coerce_non_negative_int(item) for key, item in _object_dict(value).items()}


def new_metrics_summary() -> dict[str, object]:
    return {
        "total_samples": 0,
        "url_only_documents": 0,
        "empty_body_documents": 0,
        "reason_code_counts": {},
        "adapter_hit_counts": {},
        "guardrail_rollout": {
            "samples": 0,
            "strict_enabled_samples": 0,
            "canary_matched_samples": 0,
            "global_default_samples": 0,
            "rollout_mode_counts": {},
            "strict_gate_source_counts": {},
        },
    }


def _coerce_non_negative_int(value: object) -> int:
    if not isinstance(value, (str, bytes, int, float)):
        return 0
    try:
        num = int(value)
    except (OverflowError, TypeError, ValueError):
        return 0
    return max(0, num)


def _merge_counter(counter: dict[str, int], key: str, delta: int = 1) -> None:
    name = str(key or "").strip()
    if not name:
        return
    counter[name] = _coerce_non_negative_int(counter.get(name)) + max(0, int(delta))


def _primary_reason_code(result: dict[str, object]) -> str:
    reason = normalize_reason_code(result.get("reason_code"), default="ok")
    if reason and reason != "ok":
        return reason
    breakdown = result.get("rejection_breakdown")
    if _is_object_dict(breakdown) and breakdown:
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


def _adapter_name(result: dict[str, object], *, fallback_adapter: str | None = None) -> str:
    allocation = result.get("handler_allocation")
    if _is_object_dict(allocation):
        handler_used = str(allocation.get("handler_used") or "").strip()
        if handler_used:
            return handler_used
    workflow = str(result.get("single_write_workflow") or "").strip()
    if workflow:
        return workflow
    fallback = str(fallback_adapter or "").strip()
    return fallback or "unknown"


def _counter_rows(counter: dict[str, int], *, denominator: float, top_n: int) -> list[dict[str, object]]:
    rows = sorted(
        ((str(key), _coerce_non_negative_int(value)) for key, value in dict(counter or {}).items()),
        key=lambda item: item[1],
        reverse=True,
    )[: max(1, int(top_n))]
    return [
        {
            "key": key,
            "count": count,
            "rate": round(float(count) / denominator, 6) if denominator > 0 else 0.0,
        }
        for key, count in rows
    ]


def _extract_guardrail_rollout(result: dict[str, object]) -> dict[str, object]:
    direct = result.get("guardrail_rollout")
    if _is_object_dict(direct) and direct:
        return dict(direct)

    postprocess = result.get("postprocess_frontdoor")
    if _is_object_dict(postprocess):
        data = _object_dict(postprocess.get("data"))
        quality_gates = _object_dict(data.get("quality_gates"))
        gate_config = _object_dict(quality_gates.get("gate_config"))
        rollout = gate_config.get("guardrail_rollout")
        if _is_object_dict(rollout) and rollout:
            return dict(rollout)

    quality_gates = _object_dict(result.get("quality_gates"))
    gate_config = _object_dict(quality_gates.get("gate_config"))
    rollout = gate_config.get("guardrail_rollout")
    if _is_object_dict(rollout) and rollout:
        return dict(rollout)
    return {}


def _record_guardrail_rollout_observation(summary: dict[str, object], result: dict[str, object]) -> None:
    rollout = _extract_guardrail_rollout(result)
    if not rollout:
        return
    bucket = summary.get("guardrail_rollout")
    if not _is_object_dict(bucket):
        bucket = {}
        summary["guardrail_rollout"] = bucket

    bucket["samples"] = _coerce_non_negative_int(bucket.get("samples")) + 1
    if bool(rollout.get("enable_strict_gate")):
        bucket["strict_enabled_samples"] = _coerce_non_negative_int(bucket.get("strict_enabled_samples")) + 1
    if bool(rollout.get("canary_matched")):
        bucket["canary_matched_samples"] = _coerce_non_negative_int(bucket.get("canary_matched_samples")) + 1
    if bool(rollout.get("global_default_enabled")):
        bucket["global_default_samples"] = _coerce_non_negative_int(bucket.get("global_default_samples")) + 1

    mode_counts = bucket.get("rollout_mode_counts")
    if not _is_object_dict(mode_counts):
        mode_counts = {}
        bucket["rollout_mode_counts"] = mode_counts
    normalized_mode_counts = _int_counter(mode_counts)
    bucket["rollout_mode_counts"] = normalized_mode_counts
    _merge_counter(normalized_mode_counts, str(rollout.get("rollout_mode") or "unknown"), 1)

    source_counts = bucket.get("strict_gate_source_counts")
    if not _is_object_dict(source_counts):
        source_counts = {}
        bucket["strict_gate_source_counts"] = source_counts
    normalized_source_counts = _int_counter(source_counts)
    bucket["strict_gate_source_counts"] = normalized_source_counts
    _merge_counter(normalized_source_counts, str(rollout.get("strict_gate_source") or "unknown"), 1)


def record_metrics_observation(
    summary: dict[str, object],
    result: dict[str, object] | None,
    *,
    fallback_adapter: str | None = None,
) -> None:
    if result is None:
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
    if not _is_object_dict(reason_counts):
        reason_counts = {}
        summary["reason_code_counts"] = reason_counts
    normalized_reason_counts = _int_counter(reason_counts)
    summary["reason_code_counts"] = normalized_reason_counts
    _merge_counter(normalized_reason_counts, reason_code, 1)

    adapter_counts = summary.get("adapter_hit_counts")
    if not _is_object_dict(adapter_counts):
        adapter_counts = {}
        summary["adapter_hit_counts"] = adapter_counts
    normalized_adapter_counts = _int_counter(adapter_counts)
    summary["adapter_hit_counts"] = normalized_adapter_counts
    _merge_counter(normalized_adapter_counts, _adapter_name(result, fallback_adapter=fallback_adapter), 1)
    _record_guardrail_rollout_observation(summary, result)


def build_metrics_payload_from_summary(
    summary: dict[str, object] | None,
    *,
    top_n: int = _DEFAULT_TOP_N,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=metrics_summary witness=test:test_w03_ingest_ports_authority_metadata",
]:
    base = new_metrics_summary()
    if summary is not None:
        base["total_samples"] = _coerce_non_negative_int(summary.get("total_samples"))
        base["url_only_documents"] = _coerce_non_negative_int(summary.get("url_only_documents"))
        base["empty_body_documents"] = _coerce_non_negative_int(summary.get("empty_body_documents"))
        base["reason_code_counts"] = _int_counter(summary.get("reason_code_counts"))
        base["adapter_hit_counts"] = _int_counter(summary.get("adapter_hit_counts"))
        if _is_object_dict(summary.get("guardrail_rollout")):
            raw_guardrail = _object_dict(summary.get("guardrail_rollout"))
            base["guardrail_rollout"] = {
                "samples": _coerce_non_negative_int(raw_guardrail.get("samples")),
                "strict_enabled_samples": _coerce_non_negative_int(raw_guardrail.get("strict_enabled_samples")),
                "canary_matched_samples": _coerce_non_negative_int(raw_guardrail.get("canary_matched_samples")),
                "global_default_samples": _coerce_non_negative_int(raw_guardrail.get("global_default_samples")),
                "rollout_mode_counts": _int_counter(raw_guardrail.get("rollout_mode_counts")),
                "strict_gate_source_counts": _int_counter(raw_guardrail.get("strict_gate_source_counts")),
            }

    total = _coerce_non_negative_int(base["total_samples"])
    denominator = float(total) if total > 0 else 1.0
    top_limit = max(1, int(top_n))

    reason_top = sorted(
        (
            (normalize_reason_code(k, default="unknown_rejection_reason"), _coerce_non_negative_int(v))
            for k, v in _int_counter(base["reason_code_counts"]).items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:top_limit]
    adapter_top = sorted(
        ((str(k), _coerce_non_negative_int(v)) for k, v in _int_counter(base["adapter_hit_counts"]).items()),
        key=lambda item: item[1],
        reverse=True,
    )[:top_limit]
    guardrail = _object_dict(base.get("guardrail_rollout"))
    guardrail_samples = _coerce_non_negative_int(guardrail.get("samples"))
    guardrail_denominator = float(guardrail_samples) if guardrail_samples > 0 else 1.0

    return {
        "schema_version": _SCHEMA_VERSION,
        "window": _WINDOW,
        "sample_size": total,
        "url_only_document_rate": round(float(_coerce_non_negative_int(base["url_only_documents"])) / denominator, 6)
        if total > 0
        else 0.0,
        "empty_body_rate": round(float(_coerce_non_negative_int(base["empty_body_documents"])) / denominator, 6)
        if total > 0
        else 0.0,
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
        "guardrail_rollout": {
            "contract_version": _GUARDRAIL_METRICS_CONTRACT_VERSION,
            "decision_contract_version": ROLLOUT_CONTRACT_VERSION,
            "sample_size": guardrail_samples,
            "strict_enabled_samples": _coerce_non_negative_int(guardrail.get("strict_enabled_samples")),
            "canary_matched_samples": _coerce_non_negative_int(guardrail.get("canary_matched_samples")),
            "global_default_samples": _coerce_non_negative_int(guardrail.get("global_default_samples")),
            "strict_enabled_rate": round(
                float(_coerce_non_negative_int(guardrail.get("strict_enabled_samples"))) / guardrail_denominator,
                6,
            )
            if guardrail_samples > 0
            else 0.0,
            "canary_matched_rate": round(
                float(_coerce_non_negative_int(guardrail.get("canary_matched_samples"))) / guardrail_denominator,
                6,
            )
            if guardrail_samples > 0
            else 0.0,
            "rollout_mode_counts": _counter_rows(
                _int_counter(guardrail.get("rollout_mode_counts")),
                denominator=guardrail_denominator,
                top_n=top_limit,
            ),
            "strict_gate_source_counts": _counter_rows(
                _int_counter(guardrail.get("strict_gate_source_counts")),
                denominator=guardrail_denominator,
                top_n=top_limit,
            ),
            "live_canary_validated": False,
            "closure_claim": False,
        },
        "counters": {
            "total_samples": total,
            "url_only_documents": _coerce_non_negative_int(base["url_only_documents"]),
            "empty_body_documents": _coerce_non_negative_int(base["empty_body_documents"]),
        },
    }


def build_metrics_payload_for_result(
    result: dict[str, object] | None,
    *,
    fallback_adapter: str | None = None,
    top_n: int = _DEFAULT_TOP_N,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=collect_result+job_meta witness=test:test_w03_ingest_ports_authority_metadata",
]:
    summary = new_metrics_summary()
    record_metrics_observation(summary, result, fallback_adapter=fallback_adapter)
    return build_metrics_payload_from_summary(summary, top_n=top_n)


def attach_metrics_payload(
    result: dict[str, object] | None,
    payload: dict[str, object],
) -> None:
    if result is None:
        return

    meta = result.get("meta")
    if not _is_object_dict(meta):
        meta = {}
        result["meta"] = meta
    meta["metrics_payload"] = payload

    debug = result.get("debug")
    if not _is_object_dict(debug):
        debug = {}
        result["debug"] = debug
    debug["metrics_payload"] = payload
