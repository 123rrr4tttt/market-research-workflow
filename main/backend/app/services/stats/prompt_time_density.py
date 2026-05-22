from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import logging
import math
import statistics
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import func, select

from ...models.base import SessionLocal
from ...models.entities import Document, PromptTimePolicyDecisionLog
from ..document_queries import policy_effective_date_expr

_EPSILON = 1e-9
_DEFAULT_WINDOWS = ["7d", "30d", "90d"]
_LOG = logging.getLogger(__name__)


def _effective_date_expr():
    return func.coalesce(policy_effective_date_expr(), Document.publish_date, func.date(Document.created_at))


def _normalize_json_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1].strip()
    return s or None


def _prompt_group_of(doc: Document) -> str:
    extracted = doc.extracted_data or {}
    return (
        _normalize_json_text(extracted.get("prompt_group_id"))
        or _normalize_json_text(extracted.get("topic_cluster"))
        or _normalize_json_text(extracted.get("topic"))
        or _normalize_json_text((extracted.get("policy") or {}).get("policy_type"))
        or "unknown"
    )


def _source_domain_of(doc: Document) -> str:
    extracted = doc.extracted_data or {}
    source_domain = _normalize_json_text(extracted.get("source_domain"))
    if source_domain:
        return source_domain.lower()
    uri = str(doc.uri or "").strip()
    if not uri:
        return "unknown"
    host = urlparse(uri).netloc.strip().lower()
    return host or "unknown"


def _bucket_of(day: date, bucket: str) -> date:
    if bucket == "day":
        return day
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    if bucket == "month":
        return date(day.year, day.month, 1)
    raise ValueError("bucket must be one of: day, week, month")


def _window_days(start: date, end: date) -> int:
    return max(1, (end - start).days + 1)


def _parse_window_days(window: str) -> int:
    raw = str(window or "").strip().lower()
    if not raw.endswith("d") or not raw[:-1].isdigit():
        raise ValueError("candidate_windows must use Nd format, e.g. 7d")
    return max(1, int(raw[:-1]))


def _resolve_group_filters(
    *,
    noun_group_ids: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
) -> set[str]:
    raw = noun_group_ids if noun_group_ids is not None else prompt_group_ids
    return {str(x).strip() for x in (raw or []) if str(x).strip()}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_distribution(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= _EPSILON:
        n = max(1, len(weights))
        uniform = 1.0 / float(n)
        return {k: uniform for k in weights.keys()}
    return {k: max(0.0, float(v)) / total for k, v in weights.items()}


def _kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    kl = 0.0
    for key, pv in p.items():
        qv = max(_EPSILON, float(q.get(key, _EPSILON)))
        pp = max(_EPSILON, float(pv))
        kl += pp * math.log(pp / qv)
    return float(kl)


def _project_to_bounded_simplex(
    *,
    candidate: dict[str, float],
    base: dict[str, float],
    delta_max: float,
) -> dict[str, float]:
    keys = list(candidate.keys())
    lower = {k: max(0.0, base[k] - delta_max) for k in keys}
    upper = {k: min(1.0, base[k] + delta_max) for k in keys}
    projected = {k: min(upper[k], max(lower[k], candidate[k])) for k in keys}

    # Iteratively push remaining mass while honoring [lower, upper] constraints.
    target = 1.0
    for _ in range(12):
        current = sum(projected.values())
        diff = target - current
        if abs(diff) <= 1e-7:
            break
        if diff > 0:
            slack_keys = [k for k in keys if projected[k] < upper[k] - 1e-9]
        else:
            slack_keys = [k for k in keys if projected[k] > lower[k] + 1e-9]
        if not slack_keys:
            break
        step = diff / float(len(slack_keys))
        for k in slack_keys:
            projected[k] = min(upper[k], max(lower[k], projected[k] + step))

    return _normalize_distribution(projected)


def _smooth(values: list[float], method: str) -> list[float]:
    if len(values) <= 2 or method == "none":
        return values
    if method == "ema":
        alpha = 0.35
        out = [values[0]]
        for v in values[1:]:
            out.append(alpha * v + (1.0 - alpha) * out[-1])
        return out
    if method == "gaussian":
        kernel = [0.25, 0.5, 0.25]
        out: list[float] = []
        for i in range(len(values)):
            left = values[max(0, i - 1)]
            mid = values[i]
            right = values[min(len(values) - 1, i + 1)]
            out.append((left * kernel[0]) + (mid * kernel[1]) + (right * kernel[2]))
        return out
    raise ValueError("smoothing must be one of: ema, gaussian, none")


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    q = min(1.0, max(0.0, q))
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    rank = q * (len(sorted_vals) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(sorted_vals[low])
    frac = rank - low
    return float(sorted_vals[low] * (1.0 - frac) + sorted_vals[high] * frac)


def _persist_policy_decision_logs(
    *,
    request_id: str,
    rows: list[dict[str, Any]],
    chosen_window: str,
    project_key: str | None = None,
) -> None:
    if not rows:
        return
    to_insert: list[PromptTimePolicyDecisionLog] = []
    for row in rows:
        trace = row.get("policy_decision_trace") or {}
        to_insert.append(
            PromptTimePolicyDecisionLog(
                request_id=request_id,
                project_key=str(project_key or "").strip() or None,
                source_domain=str(row.get("source_domain") or "unknown"),
                noun_group_id=str(row.get("noun_group_id") or "unknown"),
                window=str(row.get("window") or ""),
                chosen_window=chosen_window,
                is_chosen=bool(str(row.get("window") or "") == chosen_window),
                vector_overlap=float(row.get("vector_overlap") or 0.0),
                shift_signal=float(row.get("shift_signal") or 0.0),
                p_base=float(row.get("p_base") or 0.0),
                p_new=float(row.get("p_new") or 0.0),
                kl_to_base=float(row.get("kl_to_base") or 0.0),
                offpeak_confidence=float(row.get("offpeak_confidence") or 0.0),
                policy_version=str(trace.get("policy_version") or "density-cloud-v1"),
                shift_signal_breakdown=(trace.get("shift_signal_breakdown") or {}),
                features_json={
                    "density": float(row.get("density") or 0.0),
                    "norm_density": float(row.get("norm_density") or 0.0),
                    "dup_ratio": float(row.get("dup_ratio") or 0.0),
                    "peak_pressure": float(row.get("peak_pressure") or 0.0),
                    "latent_density_score": float(row.get("latent_density_score") or 0.0),
                    "target_overlap": float(row.get("target_overlap") or 0.0),
                    "target_overlap_gap": float(row.get("target_overlap_gap") or 0.0),
                    "collection_priority_score": float(row.get("collection_priority_score") or 0.0),
                },
            )
        )

    with SessionLocal() as session:
        session.add_all(to_insert)
        session.commit()


def estimate_window_overlap(
    *,
    noun_group_id: str,
    source_domain: str,
    window: str,
) -> float:
    # V1 heuristic overlap: noun/source lexical signal + window recency prior.
    ng = str(noun_group_id or "unknown").lower()
    sd = str(source_domain or "unknown").lower()
    days = _parse_window_days(window)
    lexical = 0.35 + (0.25 if ng in sd or sd in ng else 0.0)
    recency = 0.35 + min(0.3, (30.0 / float(max(1, days))) * 0.1)
    overlap = lexical + recency
    return max(0.0, min(1.0, overlap))


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

    raw = {k: base[k] * math.exp(-max(0.0, eta) * max(0.0, shift_signal.get(k, 0.0))) for k in base.keys()}
    candidate = _normalize_distribution(raw)
    bounded = _project_to_bounded_simplex(candidate=candidate, base=base, delta_max=max(0.0, delta_max))

    kl = _kl_divergence(bounded, base)
    if kl <= max(0.0, tau) + 1e-8:
        return bounded, kl

    # Mix back towards base until KL budget is satisfied.
    lo, hi = 0.0, 1.0
    mixed = dict(base)
    for _ in range(24):
        lam = (lo + hi) / 2.0
        candidate_mix = {k: ((1.0 - lam) * bounded[k]) + (lam * base[k]) for k in base.keys()}
        candidate_mix = _normalize_distribution(candidate_mix)
        kl_mix = _kl_divergence(candidate_mix, base)
        if kl_mix > tau:
            lo = lam
        else:
            hi = lam
            mixed = candidate_mix
    return mixed, _kl_divergence(mixed, base)


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
) -> dict[str, Any]:
    return {
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
    }


def query_prompt_time_density(
    *,
    start: date,
    end: date,
    bucket: str = "day",
    source_domains: list[str] | None = None,
    noun_group_ids: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
    normalize: bool = True,
) -> list[dict[str, Any]]:
    if start > end:
        raise ValueError("start must be <= end")
    if bucket not in {"day", "week", "month"}:
        raise ValueError("bucket must be one of: day, week, month")

    normalized_domains = {x.strip().lower() for x in (source_domains or []) if str(x).strip()}
    normalized_groups = _resolve_group_filters(noun_group_ids=noun_group_ids, prompt_group_ids=prompt_group_ids)
    policy_time = _effective_date_expr()

    with SessionLocal() as session:
        docs = session.execute(
            select(Document).where(
                Document.doc_type.in_(["policy", "policy_regulation", "news", "social"]),
                policy_time >= start,
                policy_time <= end,
            )
        ).scalars().all()

        # Baseline window defaults to 90d ending at current query end.
        baseline_start = end - timedelta(days=89)
        baseline_docs = session.execute(
            select(Document).where(
                Document.doc_type.in_(["policy", "policy_regulation", "news", "social"]),
                policy_time >= baseline_start,
                policy_time <= end,
            )
        ).scalars().all()

    grouped_doc_ids: dict[tuple[str, str, date], set[int]] = defaultdict(set)
    grouped_hashes: dict[tuple[str, str, date], list[str]] = defaultdict(list)

    for doc in docs:
        day = doc.publish_date or (doc.created_at.date() if doc.created_at else None)
        extracted = doc.extracted_data or {}
        eff = (
            _normalize_json_text((extracted.get("policy") or {}).get("effective_date"))
            or (day.isoformat() if day else None)
        )
        if not eff:
            continue
        try:
            effective_day = datetime.strptime(eff[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        domain = _source_domain_of(doc)
        prompt_group = _prompt_group_of(doc)
        if normalized_domains and domain not in normalized_domains:
            continue
        if normalized_groups and prompt_group not in normalized_groups:
            continue
        bucket_time = _bucket_of(effective_day, bucket)
        key = (domain, prompt_group, bucket_time)
        grouped_doc_ids[key].add(int(doc.id))
        dedup_key = str(doc.text_hash or "").strip() or str(doc.uri or "").strip().lower()
        if dedup_key:
            grouped_hashes[key].append(dedup_key)

    baseline_group_counts: dict[str, int] = defaultdict(int)
    for doc in baseline_docs:
        prompt_group = _prompt_group_of(doc)
        if normalized_groups and prompt_group not in normalized_groups:
            continue
        baseline_group_counts[prompt_group] += 1

    window_days = _window_days(start, end)
    baseline_days = _window_days(baseline_start, end)
    out: list[dict[str, Any]] = []
    for (domain, prompt_group, bucket_time), doc_ids in sorted(grouped_doc_ids.items(), key=lambda x: x[0]):
        hashes = grouped_hashes[(domain, prompt_group, bucket_time)]
        hash_counts: dict[str, int] = defaultdict(int)
        for h in hashes:
            hash_counts[h] += 1
        duplicates = sum(max(0, c - 1) for c in hash_counts.values())
        total_docs = len(doc_ids)
        effective_new_docs = max(0, total_docs - duplicates)
        density = float(effective_new_docs) / float(window_days)
        baseline_density = float(baseline_group_counts.get(prompt_group, 0)) / float(baseline_days)
        norm_density = density / max(baseline_density, _EPSILON) if normalize else density
        dup_ratio = float(duplicates) / float(max(1, total_docs))
        out.append(
            {
                "source_domain": domain,
                "noun_group_id": prompt_group,
                "prompt_group_id": prompt_group,
                "bucket_time": bucket_time.isoformat(),
                "effective_new_docs": int(effective_new_docs),
                "density": density,
                "baseline_density": baseline_density,
                "norm_density": norm_density,
                "dup_ratio": dup_ratio,
            }
        )
    return out


def query_prompt_time_density_cloud(
    *,
    keyword: str,
    start: date,
    end: date,
    bucket: str = "day",
    source_domains: list[str] | None = None,
    noun_group_ids: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
    smoothing: str = "ema",
    peak_percentile: float = 0.85,
    uncertainty: float = 0.2,
    normalize: bool = True,
) -> dict[str, Any]:
    keyword_norm = str(keyword or "").strip().lower()
    if not keyword_norm:
        raise ValueError("keyword is required")
    if not (0.0 <= peak_percentile <= 1.0):
        raise ValueError("peak_percentile must be in [0, 1]")
    if not (0.0 <= uncertainty <= 1.0):
        raise ValueError("uncertainty must be in [0, 1]")

    rows = query_prompt_time_density(
        start=start,
        end=end,
        bucket=bucket,
        source_domains=source_domains,
        noun_group_ids=noun_group_ids,
        prompt_group_ids=prompt_group_ids,
        normalize=normalize,
    )
    filtered = [
        r
        for r in rows
        if keyword_norm in str(r.get("noun_group_id", "")).lower()
        or keyword_norm in str(r.get("source_domain", "")).lower()
    ]
    if not filtered:
        filtered = rows

    by_bucket: dict[str, dict[str, Any]] = {}
    for row in filtered:
        b = str(row["bucket_time"])
        e = by_bucket.setdefault(
            b,
            {
                "bucket_time": b,
                "density": 0.0,
                "norm_density_sum": 0.0,
                "dup_ratio_sum": 0.0,
                "samples": 0,
                "effective_new_docs": 0,
            },
        )
        e["density"] += _safe_float(row.get("density"))
        e["norm_density_sum"] += _safe_float(row.get("norm_density"))
        e["dup_ratio_sum"] += _safe_float(row.get("dup_ratio"))
        e["effective_new_docs"] += int(row.get("effective_new_docs") or 0)
        e["samples"] += 1

    points = [by_bucket[k] for k in sorted(by_bucket.keys())]
    raw_density = [float(p["density"]) for p in points]
    smoothed_density = _smooth(raw_density, smoothing)
    peak_threshold = _percentile(smoothed_density, peak_percentile)
    sigma = statistics.pstdev(smoothed_density) if len(smoothed_density) > 1 else 0.0

    cloud_points: list[dict[str, Any]] = []
    for i, p in enumerate(points):
        sample_count = max(1, int(p["samples"]))
        norm_density = float(p["norm_density_sum"]) / float(sample_count)
        dup_ratio = float(p["dup_ratio_sum"]) / float(sample_count)
        value = float(smoothed_density[i])
        spread = uncertainty * (sigma + abs(value) * 0.25)
        cloud_points.append(
            {
                "bucket_time": p["bucket_time"],
                "density": float(p["density"]),
                "smoothed_density": value,
                "norm_density": norm_density,
                "dup_ratio": dup_ratio,
                "effective_new_docs": int(p["effective_new_docs"]),
                "is_peak": value >= peak_threshold,
                "uncertainty_lower": max(0.0, value - spread),
                "uncertainty_upper": value + spread,
            }
        )

    cold_start_proxy: dict[str, Any] | None = None
    if len(cloud_points) < 3:
        cold_start_proxy = {
            "reason": "sparse_history",
            "recommended_windows": list(_DEFAULT_WINDOWS),
            "sample_size": len(cloud_points),
        }

    return {
        "cloud_points": cloud_points,
        "cloud_summary": {
            "keyword": keyword_norm,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "bucket": bucket,
            "peak_percentile": peak_percentile,
            "peak_threshold": peak_threshold,
            "point_count": len(cloud_points),
        },
        "uncertainty_band": {
            "method": smoothing,
            "uncertainty": uncertainty,
            "stddev": sigma,
        },
        "cold_start_proxy": cold_start_proxy,
    }


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
    if eta < 0:
        raise ValueError("eta must be >= 0")
    if not (0 <= delta_max <= 1):
        raise ValueError("delta_max must be in [0, 1]")
    if tau < 0:
        raise ValueError("tau must be >= 0")
    if not (0 <= min_overlap <= 1):
        raise ValueError("min_overlap must be in [0, 1]")
    if not (0 <= target_overlap <= 1):
        raise ValueError("target_overlap must be in [0, 1]")

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
                },
            )
            state["density_sum"] += _safe_float(row.get("density"))
            state["norm_density_sum"] += _safe_float(row.get("norm_density"))
            state["dup_ratio_sum"] += _safe_float(row.get("dup_ratio"))
            state["count"] += 1
        per_window_rows[raw] = []
        for state in aggregated.values():
            count = max(1, int(state["count"]))
            dup_ratio = state["dup_ratio_sum"] / float(count)
            if exclude_high_dup and dup_ratio > 0.95:
                continue
            norm_density = state["norm_density_sum"] / float(count)
            density = state["density_sum"] / float(count)
            peak_pressure = min(1.0, max(0.0, norm_density))
            latent_density = max(0.0, norm_density * ((1.0 - dup_ratio) ** 0.4))
            overlap = estimate_window_overlap(
                noun_group_id=state["noun_group_id"],
                source_domain=state["source_domain"],
                window=raw,
            )
            if overlap < min_overlap:
                continue
            freshness_cost = min(1.0, float(window_days) / 365.0)
            target_overlap_gap = max(0.0, target_overlap - overlap)
            shift_signal_base = (0.40 * peak_pressure) + (0.20 * (1.0 - latent_density)) + (0.25 * (1.0 - overlap)) + (
                0.15 * freshness_cost
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
                }
            )

    p_base = _normalize_distribution({w: float(len(items)) for w, items in per_window_rows.items() if items})
    shift_by_window = {
        w: (sum(item["shift_signal"] for item in items) / float(len(items))) if items else 0.0
        for w, items in per_window_rows.items()
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
            trace = build_policy_decision_trace(
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
            )
            item["policy_decision_trace"] = trace
            rows.append(item)

    rows.sort(
        key=lambda x: (
            -float(x.get("p_new", 0.0)),
            float(x.get("collection_priority_score", 0.0)),
            -float(x.get("vector_overlap", 0.0)),
        )
    )
    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    if rows:
        # Log behavior action as the highest base probability window for OPE replay.
        chosen_window = max(
            rows,
            key=lambda x: float(x.get("p_base", 0.0)),
        ).get("window") or str(rows[0].get("window") or "")
        request_id = uuid4().hex
        for row in rows:
            row["request_id"] = request_id
            row["chosen_window"] = chosen_window
            row["is_chosen"] = bool(str(row.get("window") or "") == str(chosen_window))
        try:
            _persist_policy_decision_logs(
                request_id=request_id,
                rows=rows,
                chosen_window=str(chosen_window),
                project_key=project_key,
            )
        except Exception:
            # Logging failure should not break online ranking.
            _LOG.exception("failed to persist prompt-time policy decision logs")
    return rows


def select_priority_windows(
    rows: list[dict[str, Any]],
    *,
    max_windows: int = 3,
) -> list[dict[str, Any]]:
    if max_windows <= 0:
        raise ValueError("max_windows must be > 0")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        window = str(row.get("window") or "").strip()
        if not window or window in seen:
            continue
        seen.add(window)
        selected.append(row)
        if len(selected) >= max_windows:
            break
    return selected
