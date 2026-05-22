from __future__ import annotations

from typing import Any

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


def new_metrics_summary() -> dict[str, Any]:
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


def _counter_rows(counter: dict[str, Any], *, denominator: float, top_n: int) -> list[dict[str, Any]]:
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


def _extract_guardrail_rollout(result: dict[str, Any]) -> dict[str, Any]:
    direct = result.get("guardrail_rollout")
    if isinstance(direct, dict) and direct:
        return dict(direct)

    postprocess = result.get("postprocess_frontdoor")
    if isinstance(postprocess, dict):
        data = postprocess.get("data") if isinstance(postprocess.get("data"), dict) else {}
        quality_gates = data.get("quality_gates") if isinstance(data.get("quality_gates"), dict) else {}
        gate_config = quality_gates.get("gate_config") if isinstance(quality_gates.get("gate_config"), dict) else {}
        rollout = gate_config.get("guardrail_rollout")
        if isinstance(rollout, dict) and rollout:
            return dict(rollout)

    quality_gates = result.get("quality_gates") if isinstance(result.get("quality_gates"), dict) else {}
    gate_config = quality_gates.get("gate_config") if isinstance(quality_gates.get("gate_config"), dict) else {}
    rollout = gate_config.get("guardrail_rollout")
    if isinstance(rollout, dict) and rollout:
        return dict(rollout)
    return {}


def _record_guardrail_rollout_observation(summary: dict[str, Any], result: dict[str, Any]) -> None:
    rollout = _extract_guardrail_rollout(result)
    if not rollout:
        return
    bucket = summary.get("guardrail_rollout")
    if not isinstance(bucket, dict):
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
    if not isinstance(mode_counts, dict):
        mode_counts = {}
        bucket["rollout_mode_counts"] = mode_counts
    _merge_counter(mode_counts, str(rollout.get("rollout_mode") or "unknown"), 1)

    source_counts = bucket.get("strict_gate_source_counts")
    if not isinstance(source_counts, dict):
        source_counts = {}
        bucket["strict_gate_source_counts"] = source_counts
    _merge_counter(source_counts, str(rollout.get("strict_gate_source") or "unknown"), 1)


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
    _record_guardrail_rollout_observation(summary, result)


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
        if isinstance(summary.get("guardrail_rollout"), dict):
            raw_guardrail = summary.get("guardrail_rollout") or {}
            base["guardrail_rollout"] = {
                "samples": _coerce_non_negative_int(raw_guardrail.get("samples")),
                "strict_enabled_samples": _coerce_non_negative_int(raw_guardrail.get("strict_enabled_samples")),
                "canary_matched_samples": _coerce_non_negative_int(raw_guardrail.get("canary_matched_samples")),
                "global_default_samples": _coerce_non_negative_int(raw_guardrail.get("global_default_samples")),
                "rollout_mode_counts": dict(raw_guardrail.get("rollout_mode_counts") or {}),
                "strict_gate_source_counts": dict(raw_guardrail.get("strict_gate_source_counts") or {}),
            }

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
    guardrail = base.get("guardrail_rollout") if isinstance(base.get("guardrail_rollout"), dict) else {}
    guardrail_samples = _coerce_non_negative_int(guardrail.get("samples"))
    guardrail_denominator = float(guardrail_samples) if guardrail_samples > 0 else 1.0

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
                dict(guardrail.get("rollout_mode_counts") or {}),
                denominator=guardrail_denominator,
                top_n=top_limit,
            ),
            "strict_gate_source_counts": _counter_rows(
                dict(guardrail.get("strict_gate_source_counts") or {}),
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
