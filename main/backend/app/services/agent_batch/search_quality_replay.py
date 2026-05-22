from __future__ import annotations

import re
from copy import deepcopy
from statistics import mean
from typing import Any
from urllib.parse import urlparse

from .task_contract import (
    AGENT_BATCH_PROVIDER_QUALITY_READINESS_CONTRACT_VERSION,
    AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION,
    get_search_policy_defaults,
)

QUALITY_REPLAY_SCOPE = "deterministic_no_network_symbolic_search_quality_replay"
PROVIDER_QUALITY_READINESS_SCOPE = (
    "symbolic_search_provider_quality_readiness_fixture_quality_and_live_gap_boundary"
)
_DEFAULT_LIVE_PROVIDER_KEYS = ["searxng", "yacy", "web"]

_AXIS_HINTS = {
    "products": ("product", "products", "device", "devices", "terminal", "sku", "launch", "产品", "终端", "发布"),
    "companies": ("company", "companies", "vendor", "vendors", "startup", "maker", "厂商", "公司", "企业"),
    "recent_movement": ("latest", "recent", "news", "launch", "funding", "融资", "动态", "最近", "新闻"),
    "policy": ("policy", "regulation", "standard", "compliance", "监管", "政策", "标准"),
    "pricing": ("pricing", "price", "cost", "报价", "价格"),
}


def build_live_provider_gap_state(
    *,
    providers_not_started: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    providers = _normalize_string_list(providers_not_started) or list(_DEFAULT_LIVE_PROVIDER_KEYS)
    return {
        "status": "not_run",
        "live_provider_probe_performed": False,
        "providers_not_started": providers,
        "quality_claim_allowed": False,
        "reason": reason
        or "deterministic replay does not start SearXNG, YaCy, browser, or external web providers",
        "unsupported_claims": [
            f"{provider}_live_quality_verified" for provider in providers
        ],
    }


def build_symbolic_provider_quality_readiness(
    *,
    fixture_cases: list[dict[str, Any]],
    provider_statuses: dict[str, dict[str, Any]] | None = None,
    required_live_providers: list[str] | None = None,
) -> dict[str, Any]:
    providers = _normalize_string_list(required_live_providers) or list(_DEFAULT_LIVE_PROVIDER_KEYS)
    benchmark = score_quality_benchmark_replay(cases=fixture_cases)
    fixture_quality = _summarize_fixture_quality(benchmark)
    provider_readiness = _build_provider_quality_rows(
        provider_statuses=provider_statuses or {},
        providers=providers,
    )
    unsupported_claims = _build_unsupported_live_provider_claims(
        fixture_quality=fixture_quality,
        provider_readiness=provider_readiness,
    )
    remaining_gaps = _build_remaining_live_gaps(
        fixture_quality=fixture_quality,
        provider_readiness=provider_readiness,
    )

    failures: list[str] = []
    if benchmark.get("status") != "passed":
        failures.append("fixture quality benchmark did not pass")
    if fixture_quality.get("quality_claim_allowed") is not False:
        failures.append("fixture quality unexpectedly allowed live provider claim")
    if not unsupported_claims:
        failures.append("unsupported live-provider claims were not recorded")
    if not remaining_gaps:
        failures.append("remaining live provider gaps were not recorded")

    return {
        "contract_version": AGENT_BATCH_PROVIDER_QUALITY_READINESS_CONTRACT_VERSION,
        "scope": PROVIDER_QUALITY_READINESS_SCOPE,
        "status": "passed" if not failures else "failed",
        "readiness_state": "fixture_quality_ready_live_provider_gap_open"
        if not failures
        else "fixture_quality_or_boundary_failed",
        "closure_claim": "fixture_quality_recorded_live_provider_quality_not_closed",
        "fixture_quality": fixture_quality,
        "provider_readiness": provider_readiness,
        "unsupported_live_provider_claims": unsupported_claims,
        "remaining_live_gaps": remaining_gaps,
        "gate_semantics": {
            "status_passed_means": "fixture quality and live-gap boundary are valid",
            "status_passed_does_not_mean": "live provider quality, provider=auto promotion, or production ranking quality",
            "live_provider_claims_are": "reported as unsupported until a separate live quality replay supplies result quality, latency, timeout, and review evidence",
        },
        "failures": failures,
    }


def build_source_quality_signals(
    *,
    search_brief: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    coverage_axes = _normalize_string_list(search_brief.get("coverage_axes"))
    days_back_limit = _resolve_days_back_limit(search_brief)
    seen_fingerprints: set[str] = set()
    signals: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        payload = dict(record or {})
        url = str(payload.get("url") or "").strip()
        domain = _domain_from_url(url)
        axis_hits = _resolve_axis_hits(record=payload, coverage_axes=coverage_axes)
        goal_alignment = _ratio(len(axis_hits), max(1, len(coverage_axes)))
        freshness_days = _optional_int(payload.get("published_days_back") or payload.get("days_back"))
        freshness_fit = _score_freshness(days=freshness_days, limit=days_back_limit)
        domain_relevance = _score_domain_relevance(payload=payload, domain=domain)
        fingerprint = _record_fingerprint(payload=payload, domain=domain)
        duplicate = bool(payload.get("is_duplicate")) or fingerprint in seen_fingerprints
        if fingerprint:
            seen_fingerprints.add(fingerprint)
        source_quality_score = round(
            0.4 * goal_alignment
            + 0.25 * freshness_fit
            + 0.25 * domain_relevance
            + 0.1 * (0.0 if duplicate else 1.0),
            2,
        )
        signals.append(
            {
                "record_id": str(payload.get("record_id") or f"record_{index}"),
                "domain": domain,
                "channel": str(payload.get("channel") or "search.market").strip() or "search.market",
                "provider": str(payload.get("provider") or "replay_fixture").strip() or "replay_fixture",
                "source_mode": str(payload.get("source_mode") or "deterministic_replay").strip()
                or "deterministic_replay",
                "provider_trace_state": str(payload.get("provider_trace_state") or "deterministic_replay").strip()
                or "deterministic_replay",
                "provider_live_verified": False,
                "source_library_item_key": str(payload.get("source_library_item_key") or payload.get("item_key") or "").strip()
                or None,
                "axis_hits": axis_hits,
                "axis_hit_count": len(axis_hits),
                "freshness_days": freshness_days,
                "freshness_fit": freshness_fit,
                "domain_relevance": domain_relevance,
                "duplicate": duplicate,
                "source_quality_score": source_quality_score,
            }
        )
    return signals


def score_symbolic_search_quality_replay(
    *,
    search_brief: dict[str, Any],
    records: list[dict[str, Any]],
    live_provider_gap_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    brief = dict(search_brief or {})
    replay_records = [dict(record or {}) for record in list(records or [])]
    signals = build_source_quality_signals(search_brief=brief, records=replay_records)
    coverage_axes = _normalize_string_list(brief.get("coverage_axes"))
    stop_conditions = dict(brief.get("stop_conditions") or {})
    min_entity_count = max(1, int(stop_conditions.get("min_entity_count") or 8))
    min_source_domains = max(1, int(stop_conditions.get("min_source_domains") or 4))

    unique_entities = _unique_entities(replay_records)
    unique_domains = sorted({signal["domain"] for signal in signals if signal.get("domain")})
    duplicate_count = sum(1 for signal in signals if bool(signal.get("duplicate")))

    coverage = {
        "entity_coverage": round(min(1.0, len(unique_entities) / min_entity_count), 2),
        "source_diversity": round(min(1.0, len(unique_domains) / min_source_domains), 2),
        "freshness_fit": _mean_signal(signals, "freshness_fit"),
        "goal_alignment": _mean_axis_alignment(signals=signals, axis_count=max(1, len(coverage_axes))),
        "novelty_gain": round(1.0 - _ratio(duplicate_count, max(1, len(signals))), 2) if signals else 0.0,
        "source_quality": _mean_signal(signals, "source_quality_score"),
    }
    score = round(mean(coverage.values()), 2) if coverage else 0.0
    return {
        "contract_version": AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION,
        "scope": QUALITY_REPLAY_SCOPE,
        "score": score,
        "coverage": coverage,
        "coverage_axes": coverage_axes,
        "record_count": len(replay_records),
        "source_quality_signals": signals,
        "live_provider_gap_state": deepcopy(live_provider_gap_state or build_live_provider_gap_state()),
    }


def evaluate_quality_retry_boundary(
    *,
    search_critic: dict[str, Any],
    quality_replay: dict[str, Any],
    enable_bounded_retry: bool = True,
) -> dict[str, Any]:
    critic = dict(search_critic or {})
    replay = dict(quality_replay or {})
    defaults = get_search_policy_defaults()
    retry_budget = max(0, int(defaults.get("retry_budget") or 0))
    max_retry_rounds = max(0, int(defaults.get("max_retry_rounds") or 0))
    score_threshold = float(defaults.get("retry_score_threshold") or 0.72)
    critic_score = float(critic.get("score") or 0.0)
    next_action = str(critic.get("next_action") or "stop").strip().lower()
    reason_codes = _normalize_string_list(critic.get("reason_codes"))
    source_gap = next_action == "retry_with_source_library" and "source_backing_missing" in reason_codes

    decision = "retry_blocked"
    reason_code = "critic_stop"
    threshold_bypassed = False
    if not enable_bounded_retry:
        reason_code = "bounded_retry_disabled"
    elif retry_budget <= 0 or max_retry_rounds <= 0:
        reason_code = "retry_budget_exhausted"
    elif next_action == "stop":
        reason_code = "critic_stop"
    elif critic_score >= score_threshold and not source_gap:
        reason_code = "score_above_threshold"
    else:
        decision = "retry_allowed"
        reason_code = "source_gap_threshold_bypass" if source_gap and critic_score >= score_threshold else "critic_requested_retry"
        threshold_bypassed = source_gap and critic_score >= score_threshold

    live_gap = dict(replay.get("live_provider_gap_state") or build_live_provider_gap_state())
    return {
        "contract_version": AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION,
        "decision": decision,
        "reason_code": reason_code,
        "critic_next_action": next_action,
        "critic_score": round(critic_score, 2),
        "replay_score": float(replay.get("score") or 0.0),
        "replay_score_is_observational": True,
        "retry_score_source": "search_critic.score",
        "score_threshold": score_threshold,
        "retry_budget": retry_budget,
        "max_retry_rounds": max_retry_rounds,
        "threshold_bypassed": threshold_bypassed,
        "live_provider_quality_claim_allowed": bool(live_gap.get("quality_claim_allowed")) is True,
    }


def score_quality_benchmark_replay(*, cases: list[dict[str, Any]]) -> dict[str, Any]:
    scored_cases: list[dict[str, Any]] = []
    false_positive_count = 0
    for case in list(cases or []):
        payload = dict(case or {})
        brief = dict(payload.get("search_brief") or {})
        baseline = score_symbolic_search_quality_replay(
            search_brief=brief,
            records=[dict(record or {}) for record in list(payload.get("baseline_records") or [])],
        )
        retry = score_symbolic_search_quality_replay(
            search_brief=brief,
            records=[dict(record or {}) for record in list(payload.get("retry_records") or [])],
        )
        uplift = round(float(retry.get("score") or 0.0) - float(baseline.get("score") or 0.0), 2)
        retry_expected = bool(payload.get("retry_expected", True))
        false_positive = retry_expected and uplift < 0.0
        if false_positive:
            false_positive_count += 1
        scored_cases.append(
            {
                "case_id": str(payload.get("case_id") or f"case_{len(scored_cases) + 1}"),
                "category": str(payload.get("category") or "deterministic_fixture"),
                "baseline_score": baseline["score"],
                "retry_score": retry["score"],
                "uplift": uplift,
                "retry_expected": retry_expected,
                "false_positive_retry": false_positive,
                "baseline_live_provider_gap_state": baseline["live_provider_gap_state"],
                "retry_live_provider_gap_state": retry["live_provider_gap_state"],
            }
        )

    average_baseline = _mean_value(scored_cases, "baseline_score")
    average_retry = _mean_value(scored_cases, "retry_score")
    average_uplift = round(average_retry - average_baseline, 2)
    false_positive_rate = round(_ratio(false_positive_count, max(1, len(scored_cases))), 2)
    status = "passed" if scored_cases and average_uplift >= 0.0 and false_positive_rate <= 0.25 else "hold"
    return {
        "contract_version": AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION,
        "scope": QUALITY_REPLAY_SCOPE,
        "status": status,
        "cases": scored_cases,
        "average_baseline_score": average_baseline,
        "average_retry_score": average_retry,
        "average_uplift": average_uplift,
        "false_positive_retry_rate": false_positive_rate,
        "live_provider_gap_state": build_live_provider_gap_state(),
        "quality_claim": "deterministic_replay_only_not_live_provider_quality",
    }


def _summarize_fixture_quality(benchmark: dict[str, Any]) -> dict[str, Any]:
    live_gap = dict(benchmark.get("live_provider_gap_state") or build_live_provider_gap_state())
    return {
        "source": "score_quality_benchmark_replay",
        "status": str(benchmark.get("status") or "missing"),
        "case_count": len(list(benchmark.get("cases") or [])),
        "average_baseline_score": float(benchmark.get("average_baseline_score") or 0.0),
        "average_retry_score": float(benchmark.get("average_retry_score") or 0.0),
        "average_uplift": float(benchmark.get("average_uplift") or 0.0),
        "false_positive_retry_rate": float(benchmark.get("false_positive_retry_rate") or 0.0),
        "quality_claim": str(benchmark.get("quality_claim") or "deterministic_replay_only_not_live_provider_quality"),
        "quality_claim_allowed": bool(live_gap.get("quality_claim_allowed")) is True,
        "live_provider_gap_state": live_gap,
    }


def _build_provider_quality_rows(
    *,
    provider_statuses: dict[str, dict[str, Any]],
    providers: list[str],
) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for provider in providers:
        live = dict(provider_statuses.get(provider) or {})
        live_status = str(live.get("live_probe_status") or "not_run").strip() or "not_run"
        result_quality_verified = bool(live.get("result_quality_verified")) is True
        result_count = _optional_int(live.get("result_count"))
        if live_status == "ready" and result_quality_verified:
            availability_state = "live_available_quality_recorded"
            remaining_gap = "symbolic_live_uplift_not_verified"
        elif live_status == "ready":
            availability_state = "live_available_quality_unverified"
            remaining_gap = "result_quality_not_verified"
        else:
            availability_state = "live_gap"
            remaining_gap = "live_provider_not_ready"
        fallback_reason = live.get("fallback_reason")
        if fallback_reason in (None, "") and live_status != "ready":
            fallback_reason = "live_probe_not_run"
        rows[provider] = {
            "provider": provider,
            "live_probe_status": live_status,
            "availability_state": availability_state,
            "result_count": result_count,
            "result_quality_verified": result_quality_verified,
            "quality_claim_allowed": False,
            "input_quality_claim_allowed": bool(live.get("quality_claim_allowed")) is True,
            "fallback_reason": fallback_reason,
            "trace_failures": _normalize_string_list(live.get("trace_failures")),
            "remaining_gap": remaining_gap,
        }
    return {
        "probe_type": "recorded_provider_status_no_network_no_container_start",
        "providers": rows,
        "quality_claim_allowed": False,
        "auto_promotion_allowed": False,
    }


def _build_unsupported_live_provider_claims(
    *,
    fixture_quality: dict[str, Any],
    provider_readiness: dict[str, Any],
) -> list[dict[str, str]]:
    provider_statuses = {
        name: row.get("live_probe_status")
        for name, row in (provider_readiness.get("providers") or {}).items()
    }
    claims = [
        {
            "code": "fixture_replay_proves_live_provider_quality",
            "claim": "Deterministic symbolic search fixture replay proves live provider quality.",
            "reason": (
                "Fixture quality only records deterministic source signals and uplift; "
                f"quality_claim_allowed={fixture_quality.get('quality_claim_allowed')}."
            ),
            "required_next_evidence": "Live provider replay with result quality assertions and reviewer-visible samples.",
        },
        {
            "code": "live_provider_availability_proves_symbolic_quality",
            "claim": "Provider availability alone proves symbolic search provider quality.",
            "reason": f"Current provider statuses are recorded only: {provider_statuses}.",
            "required_next_evidence": "Per-provider success, latency, timeout, trace, and relevance thresholds on symbolic search cases.",
        },
        {
            "code": "provider_auto_promotion_supported",
            "claim": "SearXNG, YaCy, or web providers can be promoted into provider=auto.",
            "reason": "The readiness contract keeps live providers explicit-only until quality and operator policy gates exist.",
            "required_next_evidence": "Provider=auto rollout gate with live success rate, bounded timeouts, approval policy, and rollback criteria.",
        },
        {
            "code": "live_retry_uplift_closed",
            "claim": "Bounded retry uplift is proven against live providers.",
            "reason": "The current uplift is fixture replay only and does not exercise live provider ranking behavior.",
            "required_next_evidence": "Live baseline-vs-retry replay across provider-backed cases with false-positive retry tracking.",
        },
    ]
    if any(row.get("input_quality_claim_allowed") for row in (provider_readiness.get("providers") or {}).values()):
        claims.append(
            {
                "code": "input_provider_quality_claim_rejected",
                "claim": "Caller-supplied provider status may mark live quality as closed.",
                "reason": "The symbolic readiness gate rejects input quality claims unless this contract owns the live quality replay evidence.",
                "required_next_evidence": "Attach the live quality replay artifact and threshold summary to this gate.",
            }
        )
    return claims


def _build_remaining_live_gaps(
    *,
    fixture_quality: dict[str, Any],
    provider_readiness: dict[str, Any],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for provider, row in (provider_readiness.get("providers") or {}).items():
        gap = str(row.get("remaining_gap") or "live_provider_quality_not_verified")
        gaps.append(
            {
                "code": f"{provider}_{gap}",
                "status": "open",
                "reason": (
                    f"{provider} live_probe_status={row.get('live_probe_status')} "
                    f"result_quality_verified={row.get('result_quality_verified')}"
                ),
                "required_next_evidence": "Provider-specific live replay with quality thresholds and reviewer-visible result samples.",
            }
        )
    gaps.extend(
        [
            {
                "code": "live_result_quality_threshold_not_defined",
                "status": "open",
                "reason": "No symbolic provider-quality threshold is attached to a live provider replay artifact.",
                "required_next_evidence": "Define minimum result count, source diversity, relevance, freshness, latency, and timeout thresholds.",
            },
            {
                "code": "live_retry_uplift_replay_not_run",
                "status": "open",
                "reason": (
                    "Fixture average_uplift="
                    f"{fixture_quality.get('average_uplift')} is not production provider evidence."
                ),
                "required_next_evidence": "Run live baseline-vs-retry replay and record uplift plus false-positive retry rate.",
            },
            {
                "code": "provider_auto_operator_policy_not_approved",
                "status": "open",
                "reason": "Provider auto-routing remains unsafe without quality, timeout, and human-review policy.",
                "required_next_evidence": "Operator-approved provider=auto policy with rollback and manual review boundaries.",
            },
        ]
    )
    return gaps


def _resolve_days_back_limit(search_brief: dict[str, Any]) -> int | None:
    time_strategy = dict(search_brief.get("time_strategy") or {})
    parsed = _optional_int(time_strategy.get("days_back"))
    return parsed if parsed and parsed > 0 else None


def _resolve_axis_hits(*, record: dict[str, Any], coverage_axes: list[str]) -> list[str]:
    explicit = _normalize_string_list(record.get("axis_hits") or record.get("matched_axes"))
    if explicit:
        allowed = set(coverage_axes or explicit)
        return [axis for axis in explicit if axis in allowed]
    text = " ".join(
        str(record.get(key) or "")
        for key in ("title", "snippet", "summary", "description")
    ).lower()
    hits: list[str] = []
    for axis in coverage_axes:
        hints = _AXIS_HINTS.get(axis, ())
        if any(hint.lower() in text for hint in hints):
            hits.append(axis)
    return hits


def _domain_from_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _score_freshness(*, days: int | None, limit: int | None) -> float:
    if days is None:
        return 0.55
    if limit is None or days <= limit:
        return 1.0
    if limit <= 0:
        return 0.55
    return round(max(0.2, 1.0 - ((days - limit) / max(1, limit * 2))), 2)


def _score_domain_relevance(*, payload: dict[str, Any], domain: str) -> float:
    source_tier = str(payload.get("source_tier") or "").strip().lower()
    if bool(payload.get("official_access")):
        return 0.95
    if "tier_1" in source_tier:
        return 0.92
    if str(payload.get("source_library_item_key") or payload.get("item_key") or "").strip():
        return 0.86
    if "tier_2" in source_tier:
        return 0.84
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 0.82
    if domain.endswith(".org"):
        return 0.74
    if domain:
        return 0.66
    return 0.45


def _record_fingerprint(*, payload: dict[str, Any], domain: str) -> str:
    url = str(payload.get("url") or "").strip().lower()
    if url:
        return url
    title = re.sub(r"\s+", " ", str(payload.get("title") or "").strip().lower())
    return f"{domain}:{title}" if title else ""


def _unique_entities(records: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for record in records:
        for value in _normalize_string_list(record.get("entities") or record.get("matched_entities")):
            if value not in out:
                out.append(value)
    return out


def _mean_signal(signals: list[dict[str, Any]], key: str) -> float:
    return _mean_value(signals, key)


def _mean_axis_alignment(*, signals: list[dict[str, Any]], axis_count: int) -> float:
    if not signals:
        return 0.0
    return round(mean(_ratio(int(signal.get("axis_hit_count") or 0), axis_count) for signal in signals), 2)


def _mean_value(items: list[dict[str, Any]], key: str) -> float:
    values: list[float] = []
    for item in items:
        try:
            values.append(float(item.get(key)))
        except Exception:
            continue
    return round(mean(values), 2) if values else 0.0


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return max(0.0, min(1.0, float(numerator) / float(denominator)))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _normalize_string_list(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [] if value is None else [value]
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out
