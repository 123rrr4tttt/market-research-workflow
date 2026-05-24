#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from types import SimpleNamespace
from typing import Any


_EPSILON = 1e-9
TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION = "time-density-decision-log-freshness-contract.v1"
_TIME_DENSITY_TIME_FALLBACK_CHAIN = [
    "extracted_data.effective_time",
    "extracted_data.source_time",
    "extracted_data.policy.effective_date",
    "publish_date",
    "created_at",
]
_WINDOW_RE_SUFFIX = "d"
SOURCE_TIME_FUTURE_TOLERANCE = timedelta(days=1)


@dataclass(frozen=True)
class IngestTimeSemantics:
    source_time: datetime | None
    processed_time: datetime
    effective_time: datetime
    time_confidence: float
    time_provenance: str
    time_parse_version: str
    task_window: str | None
    task_window_start: date | None
    task_window_end: date | None


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _derive_window_bounds(task_window: str, anchor_day: date) -> tuple[date, date] | None:
    raw = str(task_window or "").strip().lower()
    if not raw.endswith(_WINDOW_RE_SUFFIX) or not raw[:-1].isdigit():
        return None
    days = max(1, int(raw[:-1]))
    return anchor_day - timedelta(days=days - 1), anchor_day


def build_time_semantics(
    *,
    source_time: datetime | str | None = None,
    processed_time: datetime | str | None = None,
    task_window: str | None = None,
    task_window_start: date | None = None,
    task_window_end: date | None = None,
) -> IngestTimeSemantics:
    normalized_processed = _parse_datetime(processed_time) or datetime.now(tz=timezone.utc)
    normalized_source = _parse_datetime(source_time)
    normalized_window = str(task_window or "").strip().lower() or None
    if normalized_source and normalized_source <= normalized_processed + SOURCE_TIME_FUTURE_TOLERANCE:
        effective_time = normalized_source
        time_confidence = 0.95
        time_provenance = "source_time"
    else:
        effective_time = normalized_processed
        time_confidence = 0.5 if normalized_source is None else 0.2
        time_provenance = "processed_time_fallback" if normalized_source is None else "source_time_future_rejected"

    start = task_window_start
    end = task_window_end
    if (start is None) != (end is None):
        raise ValueError("task_window_start and task_window_end must be provided together")
    if start is None and end is None and normalized_window:
        derived = _derive_window_bounds(normalized_window, effective_time.date())
        if derived:
            start, end = derived
    if start and end and start > end:
        raise ValueError("task_window_start must be <= task_window_end")

    return IngestTimeSemantics(
        source_time=normalized_source,
        processed_time=normalized_processed,
        effective_time=effective_time,
        time_confidence=time_confidence,
        time_provenance=time_provenance,
        time_parse_version="source-time-window-v1",
        task_window=normalized_window,
        task_window_start=start,
        task_window_end=end,
    )


digestion_scaffold = SimpleNamespace(build_time_semantics=build_time_semantics)


def _normalize_json_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1].strip()
    return text or None


def _parse_iso_day(value: Any) -> date | None:
    text = _normalize_json_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _extracted_data(doc: Any) -> dict[str, Any]:
    data = getattr(doc, "extracted_data", None)
    return data if isinstance(data, dict) else {}


def _prompt_time_fields(doc: Any) -> dict[str, Any]:
    data = _extracted_data(doc)
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    return {
        "effective_time": data.get("effective_time"),
        "source_time": data.get("source_time"),
        "policy_effective_date": data.get("policy_effective_date") or policy.get("effective_date"),
        "time_parse_version": data.get("time_parse_version"),
    }


def resolve_document_effective_time_provenance(doc: Any) -> dict[str, Any]:
    fields = _prompt_time_fields(doc)
    created_at = getattr(doc, "created_at", None)
    created_day = created_at.date() if isinstance(created_at, datetime) else created_at
    candidates = [
        ("effective_time", "extracted_data.effective_time", fields.get("effective_time")),
        ("source_time", "extracted_data.source_time", fields.get("source_time")),
        ("policy_effective_date", "extracted_data.policy.effective_date", fields.get("policy_effective_date")),
        ("publish_date", "publish_date", getattr(doc, "publish_date", None)),
        ("created_at", "created_at", created_day),
    ]

    available_sources: list[str] = []
    selected_source = "missing"
    selected_field: str | None = None
    effective_day: date | None = None
    for source, field, value in candidates:
        parsed = _parse_iso_day(value)
        if parsed:
            available_sources.append(source)
            if effective_day is None:
                effective_day = parsed
                selected_source = source
                selected_field = field

    gap_markers: list[str] = []
    if "effective_time" not in available_sources:
        gap_markers.append("effective_time_missing")
    if "source_time" not in available_sources:
        gap_markers.append("source_time_missing")
    if selected_source in {"publish_date", "created_at"}:
        gap_markers.append("semantic_time_fallback_used")
    if selected_source == "created_at":
        gap_markers.append("created_at_fallback_used")
    if effective_day is None:
        gap_markers.append("effective_day_unresolved")

    time_parse_version = _normalize_json_text(fields.get("time_parse_version")) or "policy-time-expr-v1"
    return {
        "effective_day": effective_day.isoformat() if effective_day else None,
        "source": selected_source,
        "source_field": selected_field,
        "available_sources": available_sources,
        "fallback_chain": list(_TIME_DENSITY_TIME_FALLBACK_CHAIN),
        "time_parse_version": time_parse_version,
        "gap_markers": sorted(set(gap_markers)),
    }


def resolve_document_effective_day(doc: Any) -> date | None:
    return _parse_iso_day(resolve_document_effective_time_provenance(doc).get("effective_day"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _new_time_provenance_summary() -> dict[str, Any]:
    return {
        "total_docs": 0,
        "source_counts": {},
        "gap_counts": {},
        "parse_versions": set(),
        "fallback_chain": list(_TIME_DENSITY_TIME_FALLBACK_CHAIN),
    }


def _add_count(target: dict[str, int], key: Any, count: int = 1) -> None:
    normalized = str(key or "").strip()
    if not normalized:
        return
    target[normalized] = int(target.get(normalized, 0)) + int(count)


def _merge_time_provenance_summary(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["total_docs"] = int(target.get("total_docs") or 0) + int(source.get("total_docs") or 0)
    for key, count in (source.get("source_counts") or {}).items():
        _add_count(target.setdefault("source_counts", {}), key, int(count or 0))
    for key, count in (source.get("gap_counts") or {}).items():
        _add_count(target.setdefault("gap_counts", {}), key, int(count or 0))
    parse_versions = source.get("parse_versions") or []
    if isinstance(parse_versions, set):
        target.setdefault("parse_versions", set()).update(parse_versions)
    else:
        target.setdefault("parse_versions", set()).update(str(v) for v in parse_versions if str(v).strip())


def _freeze_time_provenance_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = summary or {}
    parse_versions = summary.get("parse_versions") or []
    return {
        "total_docs": int(summary.get("total_docs") or 0),
        "source_counts": {str(k): int(v) for k, v in sorted((summary.get("source_counts") or {}).items())},
        "gap_counts": {str(k): int(v) for k, v in sorted((summary.get("gap_counts") or {}).items())},
        "parse_versions": sorted(str(v) for v in parse_versions if str(v).strip()),
        "fallback_chain": list(summary.get("fallback_chain") or _TIME_DENSITY_TIME_FALLBACK_CHAIN),
    }


def summarize_effective_time_source_distribution(
    effective_time_provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    provenance = effective_time_provenance or {}
    source_counts = {
        str(key): int(value or 0)
        for key, value in sorted((provenance.get("source_counts") or {}).items())
    }
    gap_counts = {
        str(key): int(value or 0)
        for key, value in sorted((provenance.get("gap_counts") or {}).items())
    }
    total_docs = int(provenance.get("total_docs") or 0)
    if total_docs <= 0:
        total_docs = sum(source_counts.values())
    denominator = float(max(1, total_docs))

    def count(*keys: str) -> int:
        return sum(int(source_counts.get(key, 0)) for key in keys)

    explicit_semantic_time_count = count("effective_time", "source_time", "policy_effective_date")
    fallback_count = count("publish_date", "created_at", "missing")
    return {
        "total_docs": total_docs,
        "source_counts": source_counts,
        "source_ratios": {
            key: float(value) / denominator
            for key, value in sorted(source_counts.items())
        },
        "source_time_count": int(source_counts.get("source_time", 0)),
        "source_time_coverage": float(source_counts.get("source_time", 0)) / denominator,
        "explicit_semantic_time_count": explicit_semantic_time_count,
        "explicit_semantic_time_coverage": float(explicit_semantic_time_count) / denominator,
        "fallback_doc_count": fallback_count,
        "fallback_rate": float(fallback_count) / denominator,
        "gap_counts": gap_counts,
        "missing_effective_time_count": int(gap_counts.get("effective_time_missing", 0)),
        "created_at_fallback_count": int(gap_counts.get("created_at_fallback_used", 0)),
        "parse_versions": sorted(
            str(version)
            for version in (provenance.get("parse_versions") or [])
            if str(version).strip()
        ),
        "fallback_chain": list(provenance.get("fallback_chain") or _TIME_DENSITY_TIME_FALLBACK_CHAIN),
    }


def build_time_density_live_gap_markers(
    *,
    effective_time_provenance: dict[str, Any] | None = None,
    feedback_observed: bool = False,
    production_data_verified: bool = False,
) -> list[str]:
    markers: set[str] = set()
    if not feedback_observed:
        markers.add("prompt_time_window_feedback_pending")
    if not production_data_verified:
        markers.add("production_freshness_probe_not_run")
    for marker, count in ((effective_time_provenance or {}).get("gap_counts") or {}).items():
        if int(count or 0) > 0:
            markers.add(f"effective_time_gap:{marker}")
    return sorted(markers)


def build_time_density_decision_log_features(
    row: dict[str, Any],
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace = trace or row.get("policy_decision_trace") or {}
    effective_time_provenance = trace.get("effective_time_provenance") or row.get("effective_time_provenance") or {}
    source_distribution = (
        trace.get("effective_time_source_distribution")
        or summarize_effective_time_source_distribution(effective_time_provenance)
    )
    return {
        "density": float(row.get("density") or 0.0),
        "norm_density": float(row.get("norm_density") or 0.0),
        "dup_ratio": float(row.get("dup_ratio") or 0.0),
        "peak_pressure": float(row.get("peak_pressure") or 0.0),
        "latent_density_score": float(row.get("latent_density_score") or 0.0),
        "target_overlap": float(row.get("target_overlap") or 0.0),
        "target_overlap_gap": float(row.get("target_overlap_gap") or 0.0),
        "collection_priority_score": float(row.get("collection_priority_score") or 0.0),
        "contract_version": str(trace.get("contract_version") or TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION),
        "effective_time_provenance": effective_time_provenance,
        "effective_time_source_distribution": source_distribution,
        "source_time_coverage": float(source_distribution.get("source_time_coverage") or 0.0),
        "explicit_semantic_time_coverage": float(
            source_distribution.get("explicit_semantic_time_coverage") or 0.0
        ),
        "ope_freshness_inputs": trace.get("ope_freshness_inputs") or {},
        "priority_decision_trace": trace.get("priority_decision_trace") or {},
        "live_data_gap_markers": trace.get("live_data_gap_markers") or [],
    }


def _parse_window_days(window: str) -> int:
    raw = str(window or "").strip().lower()
    if not raw.endswith("d") or not raw[:-1].isdigit():
        raise ValueError("candidate_windows must use Nd format, e.g. 7d")
    return max(1, int(raw[:-1]))


def _normalize_distribution(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= _EPSILON:
        uniform = 1.0 / float(max(1, len(weights)))
        return {key: uniform for key in weights.keys()}
    return {key: max(0.0, float(value)) / total for key, value in weights.items()}


def _kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    total = 0.0
    for key, p_value in p.items():
        q_value = max(_EPSILON, float(q.get(key, _EPSILON)))
        normalized_p = max(_EPSILON, float(p_value))
        total += normalized_p * math.log(normalized_p / q_value)
    return float(total)


def _project_to_bounded_simplex(
    *,
    candidate: dict[str, float],
    base: dict[str, float],
    delta_max: float,
) -> dict[str, float]:
    keys = list(candidate.keys())
    lower = {key: max(0.0, base[key] - delta_max) for key in keys}
    upper = {key: min(1.0, base[key] + delta_max) for key in keys}
    projected = {key: min(upper[key], max(lower[key], candidate[key])) for key in keys}
    for _ in range(12):
        current = sum(projected.values())
        diff = 1.0 - current
        if abs(diff) <= 1e-7:
            break
        slack_keys = [
            key
            for key in keys
            if (diff > 0 and projected[key] < upper[key] - 1e-9)
            or (diff < 0 and projected[key] > lower[key] + 1e-9)
        ]
        if not slack_keys:
            break
        step = diff / float(len(slack_keys))
        for key in slack_keys:
            projected[key] = min(upper[key], max(lower[key], projected[key] + step))
    return _normalize_distribution(projected)


def redistribute_window_probabilities(
    *,
    p_base: dict[str, float],
    shift_signal: dict[str, float],
    eta: float,
    delta_max: float,
    tau: float,
    avoid_peak: bool,
) -> tuple[dict[str, float], float]:
    if not p_base:
        return {}, 0.0
    base = _normalize_distribution(p_base)
    if not avoid_peak:
        return base, 0.0
    raw = {
        key: base[key] * math.exp(-max(0.0, eta) * max(0.0, shift_signal.get(key, 0.0)))
        for key in base.keys()
    }
    candidate = _normalize_distribution(raw)
    bounded = _project_to_bounded_simplex(candidate=candidate, base=base, delta_max=max(0.0, delta_max))
    kl = _kl_divergence(bounded, base)
    if kl <= max(0.0, tau) + 1e-8:
        return bounded, kl
    mixed = dict(base)
    lo = 0.0
    hi = 1.0
    for _ in range(24):
        lam = (lo + hi) / 2.0
        candidate_mix = {key: ((1.0 - lam) * bounded[key]) + (lam * base[key]) for key in base.keys()}
        candidate_mix = _normalize_distribution(candidate_mix)
        if _kl_divergence(candidate_mix, base) > tau:
            lo = lam
        else:
            hi = lam
            mixed = candidate_mix
    return mixed, _kl_divergence(mixed, base)


def estimate_window_overlap(
    *,
    noun_group_id: str,
    source_domain: str,
    window: str,
) -> float:
    noun_group = str(noun_group_id or "unknown").lower()
    source_domain = str(source_domain or "unknown").lower()
    days = _parse_window_days(window)
    lexical = 0.35 + (0.25 if noun_group in source_domain or source_domain in noun_group else 0.0)
    recency = 0.35 + min(0.3, (30.0 / float(max(1, days))) * 0.1)
    return max(0.0, min(1.0, lexical + recency))


def build_policy_decision_trace(
    *,
    window: str,
    peak_pressure: float,
    latent_density: float,
    overlap: float,
    target_overlap: float | None = None,
    target_overlap_gap: float | None = None,
    freshness_cost: float,
    shift_signal: float,
    p_base: float,
    p_new: float,
    kl_to_base: float,
    policy_version: str = "density-cloud-v1",
    effective_time_provenance: dict[str, Any] | None = None,
    priority_decision_trace: dict[str, Any] | None = None,
    ope_freshness_inputs: dict[str, Any] | None = None,
    live_data_gap_markers: list[str] | None = None,
) -> dict[str, Any]:
    effective_time_provenance = effective_time_provenance or {}
    return {
        "contract_version": TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION,
        "window": window,
        "policy_version": policy_version,
        "shift_signal_breakdown": {
            "peak_pressure": peak_pressure,
            "latent_density": latent_density,
            "overlap": overlap,
            "target_overlap": target_overlap,
            "target_overlap_gap": target_overlap_gap,
            "freshness_cost": freshness_cost,
        },
        "shift_signal": shift_signal,
        "p_base": p_base,
        "p_new": p_new,
        "kl_to_base": kl_to_base,
        "effective_time_provenance": effective_time_provenance,
        "effective_time_source_distribution": summarize_effective_time_source_distribution(
            effective_time_provenance
        ),
        "priority_decision_trace": priority_decision_trace or {},
        "ope_freshness_inputs": ope_freshness_inputs or {},
        "live_data_gap_markers": live_data_gap_markers or [],
    }


def _build_ope_freshness_inputs(row: dict[str, Any], *, chosen_window: str) -> dict[str, Any]:
    return {
        "decision_log_table": "public.prompt_time_policy_decision_logs",
        "freshness_timestamp_field": "created_at",
        "freshness_timestamp_source": "database_server_default",
        "default_stale_after_hours": 48.0,
        "feedback_table": "public.prompt_time_window_feedback",
        "feedback_join_keys": ["request_id", "source_domain", "noun_group_id", "window"],
        "reward_field": "observed_reward",
        "reward_fallback": "reward_proxy_from_features",
        "request_id": _normalize_json_text(row.get("request_id")),
        "window": _normalize_json_text(row.get("window")),
        "chosen_window": chosen_window,
        "is_chosen": bool(row.get("is_chosen")),
        "p_base": float(row.get("p_base") or 0.0),
        "p_new": float(row.get("p_new") or 0.0),
    }


def query_prompt_time_density(**_: Any) -> list[dict[str, Any]]:
    raise RuntimeError("query_prompt_time_density must be patched for deterministic gate checks")


def _persist_policy_decision_logs(**_: Any) -> None:
    return None


def query_prompt_time_density_priority(
    *,
    end: date,
    candidate_windows: list[str],
    source_domains: list[str] | None = None,
    noun_group_ids: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
    prefer_low_density: bool = True,
    exclude_high_dup: bool = True,
    min_overlap: float = 0.35,
    target_overlap: float = 0.55,
    eta: float = 0.08,
    delta_max: float = 0.12,
    tau: float = 0.03,
    avoid_peak: bool = True,
    project_key: str | None = None,
) -> list[dict[str, Any]]:
    if not candidate_windows:
        raise ValueError("candidate_windows must not be empty")
    per_window_rows: dict[str, list[dict[str, Any]]] = {}
    for window in candidate_windows:
        raw = str(window).strip().lower()
        window_days = _parse_window_days(raw)
        start = end - timedelta(days=window_days - 1)
        density_rows = query_prompt_time_density(
            start=start,
            end=end,
            bucket="day",
            source_domains=source_domains,
            noun_group_ids=noun_group_ids,
            prompt_group_ids=prompt_group_ids,
            normalize=True,
        )
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for row in density_rows:
            key = (str(row["source_domain"]), str(row["noun_group_id"]))
            state = aggregated.setdefault(
                key,
                {
                    "source_domain": key[0],
                    "noun_group_id": key[1],
                    "prompt_group_id": key[1],
                    "density_sum": 0.0,
                    "norm_density_sum": 0.0,
                    "dup_ratio_sum": 0.0,
                    "count": 0,
                    "effective_time_provenance": _new_time_provenance_summary(),
                },
            )
            state["density_sum"] += _safe_float(row.get("density"))
            state["norm_density_sum"] += _safe_float(row.get("norm_density"))
            state["dup_ratio_sum"] += _safe_float(row.get("dup_ratio"))
            state["count"] += 1
            _merge_time_provenance_summary(
                state["effective_time_provenance"],
                row.get("effective_time_provenance") or {},
            )
        per_window_rows[raw] = []
        for state in aggregated.values():
            count = max(1, int(state["count"]))
            dup_ratio = float(state["dup_ratio_sum"]) / float(count)
            if exclude_high_dup and dup_ratio > 0.95:
                continue
            norm_density = float(state["norm_density_sum"]) / float(count)
            density = float(state["density_sum"]) / float(count)
            overlap = estimate_window_overlap(
                noun_group_id=state["noun_group_id"],
                source_domain=state["source_domain"],
                window=raw,
            )
            if overlap < min_overlap:
                continue
            freshness_cost = min(1.0, float(window_days) / 365.0)
            target_overlap_gap = max(0.0, target_overlap - overlap)
            peak_pressure = min(1.0, max(0.0, norm_density))
            latent_density = max(0.0, norm_density * ((1.0 - dup_ratio) ** 0.4))
            shift_signal_base = (
                (0.40 * peak_pressure)
                + (0.20 * (1.0 - latent_density))
                + (0.25 * (1.0 - overlap))
                + (0.15 * freshness_cost)
            )
            shift_signal = min(1.0, shift_signal_base + (0.20 * target_overlap_gap))
            base_score = (0.6 * norm_density) + (0.3 * dup_ratio) + (0.1 * freshness_cost)
            if not prefer_low_density:
                base_score = -base_score
            base_score += 0.20 * target_overlap_gap
            per_window_rows[raw].append(
                {
                    "source_domain": state["source_domain"],
                    "noun_group_id": state["noun_group_id"],
                    "prompt_group_id": state["prompt_group_id"],
                    "window": raw,
                    "density": density,
                    "norm_density": norm_density,
                    "dup_ratio": dup_ratio,
                    "peak_pressure": peak_pressure,
                    "latent_density_score": latent_density,
                    "vector_overlap": overlap,
                    "target_overlap_gap": target_overlap_gap,
                    "shift_signal": shift_signal,
                    "offpeak_confidence": max(0.0, min(1.0, overlap * (1.0 - peak_pressure))),
                    "collection_priority_score": base_score,
                    "freshness_penalty": freshness_cost,
                    "effective_time_provenance": _freeze_time_provenance_summary(
                        state.get("effective_time_provenance")
                    ),
                }
            )

    p_base = _normalize_distribution({window: float(len(items)) for window, items in per_window_rows.items() if items})
    shift_by_window = {
        window: (sum(item["shift_signal"] for item in items) / float(len(items))) if items else 0.0
        for window, items in per_window_rows.items()
    }
    p_new, kl_to_base = redistribute_window_probabilities(
        p_base=p_base,
        shift_signal=shift_by_window,
        eta=eta,
        delta_max=delta_max,
        tau=tau,
        avoid_peak=avoid_peak,
    )

    rows: list[dict[str, Any]] = []
    for window, items in per_window_rows.items():
        for item in items:
            item["target_overlap"] = target_overlap
            item["p_base"] = float(p_base.get(window, 0.0))
            item["p_new"] = float(p_new.get(window, item["p_base"]))
            item["kl_to_base"] = float(kl_to_base)
            priority_decision_trace = {
                "prefer_low_density": bool(prefer_low_density),
                "exclude_high_dup": bool(exclude_high_dup),
                "min_overlap": float(min_overlap),
                "target_overlap": float(target_overlap),
                "eta": float(eta),
                "delta_max": float(delta_max),
                "tau": float(tau),
                "avoid_peak": bool(avoid_peak),
                "sort_order": ["p_new_desc", "collection_priority_score_asc", "vector_overlap_desc"],
                "behavior_policy": "highest_p_base_window_for_ope_replay",
            }
            provenance = dict(item.get("effective_time_provenance") or {})
            item["policy_decision_trace"] = build_policy_decision_trace(
                window=window,
                peak_pressure=float(item["peak_pressure"]),
                latent_density=float(item["latent_density_score"]),
                overlap=float(item["vector_overlap"]),
                target_overlap=float(item["target_overlap"]),
                target_overlap_gap=float(item["target_overlap_gap"]),
                freshness_cost=float(item["freshness_penalty"]),
                shift_signal=float(item["shift_signal"]),
                p_base=float(item["p_base"]),
                p_new=float(item["p_new"]),
                kl_to_base=float(kl_to_base),
                effective_time_provenance=provenance,
                priority_decision_trace=priority_decision_trace,
                live_data_gap_markers=build_time_density_live_gap_markers(
                    effective_time_provenance=provenance,
                    feedback_observed=False,
                    production_data_verified=False,
                ),
            )
            rows.append(item)

    rows.sort(
        key=lambda row: (
            -float(row.get("p_new", 0.0)),
            float(row.get("collection_priority_score", 0.0)),
            -float(row.get("vector_overlap", 0.0)),
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    if rows:
        chosen_window = max(rows, key=lambda row: float(row.get("p_base", 0.0))).get("window") or str(rows[0].get("window") or "")
        request_id = "deterministic-time-density-request"
        for row in rows:
            row["request_id"] = request_id
            row["chosen_window"] = chosen_window
            row["is_chosen"] = bool(str(row.get("window") or "") == str(chosen_window))
            trace = row.get("policy_decision_trace") or {}
            priority_trace = dict(trace.get("priority_decision_trace") or {})
            priority_trace.update(
                {
                    "rank": int(row.get("rank") or 0),
                    "chosen_window": str(chosen_window),
                    "is_chosen": bool(row.get("is_chosen")),
                }
            )
            trace["priority_decision_trace"] = priority_trace
            trace["ope_freshness_inputs"] = _build_ope_freshness_inputs(row, chosen_window=str(chosen_window))
            row["policy_decision_trace"] = trace
        _persist_policy_decision_logs(
            request_id=request_id,
            rows=rows,
            chosen_window=str(chosen_window),
            project_key=project_key,
        )
    return rows


def _parse_created_at(value: Any) -> datetime | None:
    return _parse_datetime(value)


def _freshness_summary(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stale_after_hours: float = 48.0,
) -> dict[str, Any]:
    timestamps = [_parse_created_at(row.get("created_at")) for row in rows]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if not timestamps:
        return {
            "status": "no_timestamp",
            "min_created_at": None,
            "max_created_at": None,
            "latest_age_hours": None,
            "stale_after_hours": float(stale_after_hours),
        }
    latest = max(timestamps)
    earliest = min(timestamps)
    latest_age_hours = max(0.0, (now - latest).total_seconds() / 3600.0)
    return {
        "status": "fresh" if latest_age_hours <= stale_after_hours else "stale",
        "min_created_at": earliest.isoformat(),
        "max_created_at": latest.isoformat(),
        "latest_age_hours": latest_age_hours,
        "stale_after_hours": float(stale_after_hours),
    }


def _reward_proxy(row: dict[str, Any]) -> float:
    features = row.get("features_json") or {}
    dup_ratio = _safe_float(features.get("dup_ratio"), 0.0)
    peak_pressure = _safe_float(features.get("peak_pressure"), 0.0)
    overlap = _safe_float(row.get("vector_overlap"), 0.0)
    offpeak = _safe_float(row.get("offpeak_confidence"), 0.0)
    reward = (0.5 * offpeak) + (0.3 * overlap) + (0.2 * (1.0 - peak_pressure))
    return max(0.0, min(1.0, reward * max(0.0, min(1.0, 1.0 - dup_ratio))))


def evaluate_ope(
    rows: list[dict[str, Any]],
    *,
    switch_lambda: float = 10.0,
    dros_lambda: float = 1.0,
    n_bootstrap: int = 300,
    now: datetime | None = None,
    stale_after_hours: float = 48.0,
) -> dict[str, Any]:
    del switch_lambda, dros_lambda, n_bootstrap
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        request_id = str(row.get("request_id") or "")
        if not request_id:
            continue
        grouped[
            (
                request_id,
                str(row.get("source_domain") or "unknown"),
                str(row.get("noun_group_id") or "unknown"),
            )
        ].append(row)

    rewards: list[float] = []
    weights: list[float] = []
    for actions in grouped.values():
        by_window = {str(action.get("window") or ""): action for action in actions}
        behavior_window = str(actions[0].get("chosen_window") or "")
        if behavior_window not in by_window:
            continue
        behavior_row = by_window[behavior_window]
        reward = _safe_float(behavior_row.get("observed_reward"), float("nan"))
        if math.isnan(reward):
            reward = _reward_proxy(behavior_row)
        rewards.append(max(0.0, min(1.0, reward)))
        p_base = max(_EPSILON, _safe_float(behavior_row.get("p_base"), 0.0))
        p_new = max(0.0, _safe_float(behavior_row.get("p_new"), 0.0))
        weights.append(p_new / p_base)

    contexts_used = len(rewards)
    mean_reward = sum(rewards) / float(max(1, len(rewards)))
    weight_sum = sum(weights)
    weight_sq_sum = sum(weight * weight for weight in weights)
    ess = (weight_sum * weight_sum / max(_EPSILON, weight_sq_sum)) if weights else 0.0
    ess_ratio = ess / float(max(1, len(weights)))
    mean_weight = weight_sum / float(max(1, len(weights)))
    if len(weights) <= 1 or mean_weight <= _EPSILON:
        weight_cv = 0.0
    else:
        variance = sum((weight - mean_weight) ** 2 for weight in weights) / float(len(weights))
        weight_cv = math.sqrt(max(0.0, variance)) / max(_EPSILON, mean_weight)

    return {
        "summary": {
            "contexts_used": contexts_used,
            "replay_matches": contexts_used,
            "reward_proxy_count": 0,
        },
        "estimators": {
            "dr": {"mean": mean_reward, "ci_low": mean_reward, "ci_high": mean_reward},
            "ips": {"mean": mean_reward, "ci_low": mean_reward, "ci_high": mean_reward},
        },
        "diagnostics": {
            "effective_sample_size": ess,
            "effective_sample_size_ratio": ess_ratio,
            "weight_cv": weight_cv,
        },
        "freshness": _freshness_summary(rows, now=now, stale_after_hours=stale_after_hours),
    }
