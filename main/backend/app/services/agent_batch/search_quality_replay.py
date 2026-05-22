from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from statistics import mean
from typing import Any
from urllib.parse import urlparse

from .task_contract import (
    AGENT_BATCH_LIVE_QUALITY_THRESHOLD_CONTRACT_VERSION,
    AGENT_BATCH_QUALITY_PROMOTION_READBACK_CONTRACT_VERSION,
    AGENT_BATCH_PROVIDER_QUALITY_READINESS_CONTRACT_VERSION,
    AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION,
    get_search_policy_defaults,
)

QUALITY_REPLAY_SCOPE = "deterministic_no_network_symbolic_search_quality_replay"
PROVIDER_QUALITY_READINESS_SCOPE = (
    "symbolic_search_provider_quality_readiness_fixture_quality_and_live_gap_boundary"
)
LIVE_QUALITY_THRESHOLD_SCOPE = "symbolic_search_live_provider_quality_threshold_contract"
QUALITY_REGRESSION_EVALUATOR_SCOPE = (
    "symbolic_search_quality_regression_fixture_threshold_live_gap_boundary"
)
QUALITY_PROMOTION_READBACK_SCOPE = (
    "provider_independent_symbolic_quality_promotion_readback"
)
_DEFAULT_LIVE_PROVIDER_KEYS = ["searxng", "yacy", "web"]
_DEFAULT_LIVE_QUALITY_THRESHOLDS: dict[str, Any] = {
    "threshold_version": "symbolic_live_quality_thresholds.v1",
    "min_case_count": 1,
    "min_results_per_provider": 3,
    "min_source_domains": 2,
    "min_relevance_score": 0.72,
    "min_freshness_score": 0.65,
    "max_duplicate_rate": 0.25,
    "max_timeout_rate": 0.10,
    "max_p95_latency_ms": 4000,
    "min_review_sample_count": 3,
    "require_trace_success": True,
}
_DEFAULT_QUALITY_REGRESSION_THRESHOLDS: dict[str, Any] = {
    "threshold_version": "symbolic_quality_regression_thresholds.v1",
    "min_fixture_case_count": 1,
    "min_average_uplift": 0.0,
    "max_false_positive_retry_rate": 0.25,
    "require_retry_allowed_trace": True,
    "require_retry_blocked_trace": True,
    "require_live_provider_quality_open": True,
}

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


def build_symbolic_live_quality_threshold_contract(
    *,
    fixture_quality: dict[str, Any] | None = None,
    live_provider_replay: dict[str, Any] | None = None,
    required_live_providers: list[str] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    threshold_config = _merge_live_quality_thresholds(
        thresholds=thresholds,
        required_live_providers=required_live_providers,
    )
    providers = list(threshold_config["required_providers"])
    replay_payload = dict(live_provider_replay or {})
    replay_type = str(replay_payload.get("replay_type") or "not_run").strip() or "not_run"
    live_replay_performed = (
        bool(replay_payload.get("live_replay_performed"))
        or replay_type == "live_provider_quality_replay"
    )
    provider_inputs = dict(replay_payload.get("providers") or {})
    provider_rows = {
        provider: _evaluate_live_provider_thresholds(
            provider=provider,
            payload=dict(provider_inputs.get(provider) or {}),
            thresholds=threshold_config,
            replay_type=replay_type,
            live_replay_performed=live_replay_performed,
        )
        for provider in providers
    }
    operator_review_status = str(replay_payload.get("operator_review_status") or "not_run").strip() or "not_run"
    all_provider_thresholds_met = bool(provider_rows) and all(
        bool(row.get("thresholds_met")) for row in provider_rows.values()
    )
    live_provider_replay_closed = (
        live_replay_performed
        and replay_type == "live_provider_quality_replay"
        and all_provider_thresholds_met
        and operator_review_status == "approved"
    )
    fixture_boundary = _build_fixture_quality_boundary(fixture_quality or {})
    unsupported_claims = _build_live_threshold_unsupported_claims(
        fixture_quality_boundary=fixture_boundary,
        replay_payload=replay_payload,
    )
    remaining_gaps = _build_live_threshold_remaining_gaps(
        provider_rows=provider_rows,
        live_replay_performed=live_replay_performed,
        operator_review_status=operator_review_status,
    )

    failures: list[str] = []
    if fixture_boundary["quality_claim_allowed"]:
        failures.append("fixture quality boundary unexpectedly allowed live-provider quality claim")
    if not providers:
        failures.append("live quality threshold has no required providers")
    if not threshold_config.get("threshold_version"):
        failures.append("live quality threshold version missing")

    if live_provider_replay_closed:
        threshold_status = "live_quality_thresholds_met"
    elif live_replay_performed:
        threshold_status = "live_replay_present_thresholds_unmet"
    else:
        threshold_status = "threshold_contract_ready_live_replay_gap_open"

    return {
        "contract_version": AGENT_BATCH_LIVE_QUALITY_THRESHOLD_CONTRACT_VERSION,
        "scope": LIVE_QUALITY_THRESHOLD_SCOPE,
        "status": "passed" if not failures else "failed",
        "threshold_version": str(threshold_config["threshold_version"]),
        "threshold_status": threshold_status,
        "closure_claim": "live_quality_threshold_defined_provider_replay_not_closed",
        "fixture_quality_boundary": fixture_boundary,
        "quality_thresholds": threshold_config,
        "replay_evaluation": {
            "replay_type": replay_type,
            "live_replay_performed": live_replay_performed,
            "operator_review_status": operator_review_status,
            "providers": provider_rows,
        },
        "live_provider_replay_closed": live_provider_replay_closed,
        "quality_claim_allowed": live_provider_replay_closed,
        "provider_auto_promotion_allowed": False,
        "unsupported_live_provider_claims": unsupported_claims,
        "remaining_live_gaps": remaining_gaps,
        "failures": failures,
    }


def build_symbolic_quality_regression_evaluator(
    *,
    fixture_cases: list[dict[str, Any]],
    provider_statuses: dict[str, dict[str, Any]] | None = None,
    live_provider_replay: dict[str, Any] | None = None,
    required_live_providers: list[str] | None = None,
    live_quality_thresholds: dict[str, Any] | None = None,
    regression_thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = [dict(case or {}) for case in list(fixture_cases or [])]
    provider_inputs = {
        str(provider): dict(status or {})
        for provider, status in dict(provider_statuses or {}).items()
    }
    regression_config = _merge_quality_regression_thresholds(
        thresholds=regression_thresholds,
    )
    provider_readiness = build_symbolic_provider_quality_readiness(
        fixture_cases=cases,
        provider_statuses=provider_inputs,
        required_live_providers=required_live_providers,
    )
    fixture_quality = dict(provider_readiness.get("fixture_quality") or {})
    replay_payload = dict(
        live_provider_replay
        if live_provider_replay is not None
        else {"replay_type": "not_run", "providers": provider_inputs}
    )
    if provider_inputs and not replay_payload.get("providers"):
        replay_payload["providers"] = provider_inputs
    live_threshold = build_symbolic_live_quality_threshold_contract(
        fixture_quality=fixture_quality,
        live_provider_replay=replay_payload,
        required_live_providers=required_live_providers,
        thresholds=live_quality_thresholds,
    )
    fixture_quality_threshold = _evaluate_fixture_quality_regression_threshold(
        fixture_quality=fixture_quality,
        thresholds=regression_config,
        live_provider_quality_open=True,
    )
    critic_retry_trace = _build_quality_regression_retry_trace(
        cases=cases,
        thresholds=regression_config,
    )

    threshold_status = str(live_threshold.get("threshold_status") or "missing")
    live_provider_quality_open = True
    failures: list[str] = []
    if provider_readiness.get("status") != "passed":
        failures.append("provider quality readiness input did not pass")
    if fixture_quality_threshold.get("status") != "passed":
        failures.append("fixture quality regression threshold did not pass")
    if critic_retry_trace.get("status") != "passed":
        failures.append("critic bounded-retry trace did not pass")
    if live_threshold.get("status") != "passed":
        failures.append("live quality threshold contract did not pass")
    if threshold_status != "threshold_contract_ready_live_replay_gap_open":
        failures.append("live quality threshold status did not preserve replay gap")
    if bool(live_threshold.get("live_provider_replay_closed")) is True:
        failures.append("live provider replay unexpectedly closed")
    if bool(live_threshold.get("quality_claim_allowed")) is True:
        failures.append("live quality threshold unexpectedly allowed quality claim")
    if bool(provider_readiness.get("provider_readiness", {}).get("quality_claim_allowed")) is True:
        failures.append("provider readiness unexpectedly allowed quality claim")
    if bool(regression_config.get("require_live_provider_quality_open")) and not live_provider_quality_open:
        failures.append("live provider quality was not kept open")

    return {
        "contract_version": "agent_batch.symbolic_quality_regression_evaluator.v1",
        "scope": QUALITY_REGRESSION_EVALUATOR_SCOPE,
        "status": "passed" if not failures else "failed",
        "regression_state": "fixture_quality_regression_passed_live_provider_quality_open"
        if not failures
        else "fixture_quality_regression_failed",
        "closure_claim": "provider_independent_quality_regression_passed_live_provider_quality_not_closed",
        "live_provider_quality_open": live_provider_quality_open,
        "live_provider_quality_closed_by_evaluator": False,
        "quality_claim_allowed": False,
        "provider_auto_promotion_allowed": False,
        "threshold_status": threshold_status,
        "regression_thresholds": regression_config,
        "fixture_quality_threshold": fixture_quality_threshold,
        "critic_bounded_retry_trace": critic_retry_trace,
        "provider_readiness": provider_readiness,
        "live_quality_threshold": live_threshold,
        "unsupported_live_provider_claims": _merge_code_rows(
            provider_readiness.get("unsupported_live_provider_claims", []),
            live_threshold.get("unsupported_live_provider_claims", []),
        ),
        "remaining_live_gaps": _merge_code_rows(
            provider_readiness.get("remaining_live_gaps", []),
            live_threshold.get("remaining_live_gaps", []),
        ),
        "failures": failures,
    }


def build_symbolic_quality_promotion_readback_gate(
    *,
    fixture_cases: list[dict[str, Any]],
    provider_statuses: dict[str, dict[str, Any]] | None = None,
    live_provider_replay: dict[str, Any] | None = None,
    required_live_providers: list[str] | None = None,
    live_quality_thresholds: dict[str, Any] | None = None,
    regression_thresholds: dict[str, Any] | None = None,
    input_promotion_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = [dict(case or {}) for case in list(fixture_cases or [])]
    evaluator = build_symbolic_quality_regression_evaluator(
        fixture_cases=cases,
        provider_statuses=provider_statuses,
        live_provider_replay=live_provider_replay,
        required_live_providers=required_live_providers,
        live_quality_thresholds=live_quality_thresholds,
        regression_thresholds=regression_thresholds,
    )
    first_case = cases[0] if cases else {}
    fixture_search_brief = _summarize_fixture_search_brief(payload=first_case)
    critic_score_readback = _summarize_critic_score_readback(
        payload=first_case,
        evaluator=evaluator,
    )
    bounded_retry_readback = _summarize_bounded_retry_readback(evaluator=evaluator)
    quality_threshold_readback = _summarize_quality_threshold_readback(evaluator=evaluator)
    promotion_decision = _build_provider_independent_promotion_decision(
        quality_threshold_readback=quality_threshold_readback,
        bounded_retry_readback=bounded_retry_readback,
    )
    promotion_decision_readback = _build_promotion_decision_readback(
        promotion_decision=promotion_decision,
        input_promotion_decision=input_promotion_decision,
    )
    provider_independent_boundary = _build_provider_independent_boundary(
        evaluator=evaluator,
        promotion_decision=promotion_decision,
    )
    unsupported_promotion_claims = _merge_code_rows(
        _build_promotion_unsupported_claims(
            critic_score_readback=critic_score_readback,
            quality_threshold_readback=quality_threshold_readback,
            input_promotion_decision=input_promotion_decision,
        ),
        evaluator.get("unsupported_live_provider_claims", []),
    )
    remaining_live_gaps = _merge_code_rows(
        evaluator.get("remaining_live_gaps", []),
        [
            {
                "code": "provider_auto_promotion_readback_hold",
                "status": "open",
                "reason": "Promotion decision readback is validated, but live provider quality remains open.",
                "required_next_evidence": "Live provider replay, threshold pass rows, and operator approval before provider=auto promotion.",
            }
        ],
    )

    failures: list[str] = []
    if not cases:
        failures.append("fixture_cases_missing")
    if evaluator.get("status") != "passed":
        failures.append("quality_regression_evaluator_failed")
    if not fixture_search_brief.get("goal"):
        failures.append("fixture_search_brief_missing_goal")
    if critic_score_readback.get("retry_score_source") != "search_critic.score":
        failures.append("critic_score_source_drifted")
    if bool(bounded_retry_readback.get("replay_score_is_observational")) is not True:
        failures.append("bounded_retry_replay_score_not_observational")
    if quality_threshold_readback.get("threshold_status") != "threshold_contract_ready_live_replay_gap_open":
        failures.append("quality_threshold_did_not_preserve_live_gap")
    if bool(promotion_decision.get("promotion_allowed")) is True:
        failures.append("promotion_allowed_unexpectedly_true")
    if bool(promotion_decision_readback.get("readback_matches_decision")) is not True:
        failures.append("promotion_decision_readback_mismatch")
    if bool(provider_independent_boundary.get("quality_claim_allowed")) is True:
        failures.append("provider_independent_boundary_allowed_quality_claim")
    if bool(provider_independent_boundary.get("provider_auto_promotion_allowed")) is True:
        failures.append("provider_independent_boundary_allowed_auto_promotion")

    return {
        "contract_version": AGENT_BATCH_QUALITY_PROMOTION_READBACK_CONTRACT_VERSION,
        "scope": QUALITY_PROMOTION_READBACK_SCOPE,
        "status": "passed" if not failures else "failed",
        "gate_state": "provider_independent_quality_promotion_held_live_gap_open"
        if not failures
        else "provider_independent_quality_promotion_readback_failed",
        "closure_claim": "promotion_decision_readback_validated_live_provider_quality_not_closed",
        "fixture_search_brief": fixture_search_brief,
        "critic_score_readback": critic_score_readback,
        "bounded_retry_readback": bounded_retry_readback,
        "quality_threshold_readback": quality_threshold_readback,
        "promotion_decision": promotion_decision,
        "promotion_decision_readback": promotion_decision_readback,
        "provider_independent_boundary": provider_independent_boundary,
        "quality_regression_evaluator": evaluator,
        "unsupported_promotion_claims": unsupported_promotion_claims,
        "remaining_live_gaps": remaining_live_gaps,
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


def _merge_quality_regression_thresholds(
    *,
    thresholds: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(_DEFAULT_QUALITY_REGRESSION_THRESHOLDS)
    for key, value in dict(thresholds or {}).items():
        if key in merged and value is not None:
            merged[key] = value
    merged["min_fixture_case_count"] = max(1, int(merged["min_fixture_case_count"]))
    merged["min_average_uplift"] = float(merged["min_average_uplift"])
    merged["max_false_positive_retry_rate"] = float(merged["max_false_positive_retry_rate"])
    merged["require_retry_allowed_trace"] = bool(merged["require_retry_allowed_trace"]) is True
    merged["require_retry_blocked_trace"] = bool(merged["require_retry_blocked_trace"]) is True
    merged["require_live_provider_quality_open"] = bool(merged["require_live_provider_quality_open"]) is True
    return merged


def _evaluate_fixture_quality_regression_threshold(
    *,
    fixture_quality: dict[str, Any],
    thresholds: dict[str, Any],
    live_provider_quality_open: bool,
) -> dict[str, Any]:
    case_count = int(fixture_quality.get("case_count") or 0)
    average_uplift = float(fixture_quality.get("average_uplift") or 0.0)
    false_positive_retry_rate = float(fixture_quality.get("false_positive_retry_rate") or 0.0)
    checks = {
        "fixture_status_passed": str(fixture_quality.get("status") or "") == "passed",
        "case_count": case_count >= int(thresholds["min_fixture_case_count"]),
        "average_uplift": average_uplift >= float(thresholds["min_average_uplift"]),
        "false_positive_retry_rate": false_positive_retry_rate
        <= float(thresholds["max_false_positive_retry_rate"]),
        "fixture_quality_claim_blocked": bool(fixture_quality.get("quality_claim_allowed")) is False,
        "live_provider_quality_open": live_provider_quality_open
        if bool(thresholds["require_live_provider_quality_open"])
        else True,
    }
    threshold_failures = [name for name, passed in checks.items() if not passed]
    return {
        "threshold_version": str(thresholds["threshold_version"]),
        "status": "passed" if not threshold_failures else "failed",
        "case_count": case_count,
        "average_uplift": average_uplift,
        "false_positive_retry_rate": false_positive_retry_rate,
        "threshold_checks": checks,
        "threshold_failures": threshold_failures,
    }


def _build_quality_regression_retry_trace(
    *,
    cases: list[dict[str, Any]],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []
    allowed_count = 0
    blocked_count = 0
    for index, case in enumerate(cases, start=1):
        payload = dict(case or {})
        search_brief = dict(payload.get("search_brief") or {})
        baseline = score_symbolic_search_quality_replay(
            search_brief=search_brief,
            records=[dict(record or {}) for record in list(payload.get("baseline_records") or [])],
        )
        retry = score_symbolic_search_quality_replay(
            search_brief=search_brief,
            records=[dict(record or {}) for record in list(payload.get("retry_records") or [])],
        )
        critic = _case_search_critic(payload=payload)
        boundary = evaluate_quality_retry_boundary(
            search_critic=critic,
            quality_replay=baseline,
            enable_bounded_retry=bool(payload.get("enable_bounded_retry", True)),
        )
        decision = str(boundary.get("decision") or "")
        if decision == "retry_allowed":
            allowed_count += 1
        if decision == "retry_blocked":
            blocked_count += 1
        retry_expected = bool(payload.get("retry_expected", True))
        expected_decision = "retry_allowed" if retry_expected else "retry_blocked"
        uplift = round(float(retry.get("score") or 0.0) - float(baseline.get("score") or 0.0), 2)
        trace_failures: list[str] = []
        if decision != expected_decision:
            trace_failures.append("critic_boundary_decision_mismatch")
        if retry_expected and uplift < 0.0:
            trace_failures.append("retry_quality_regressed")
        if bool(boundary.get("replay_score_is_observational")) is not True:
            trace_failures.append("replay_score_not_observational")
        if bool(boundary.get("live_provider_quality_claim_allowed")) is True:
            trace_failures.append("live_provider_quality_claim_allowed")
        traces.append(
            {
                "case_id": str(payload.get("case_id") or f"case_{index}"),
                "retry_expected": retry_expected,
                "expected_decision": expected_decision,
                "status": "passed" if not trace_failures else "failed",
                "baseline_score": baseline.get("score"),
                "retry_score": retry.get("score"),
                "uplift": uplift,
                "search_critic": critic,
                "boundary": boundary,
                "failures": trace_failures,
            }
        )

    aggregate_failures: list[str] = []
    if not traces:
        aggregate_failures.append("retry_trace_cases_missing")
    if any(trace.get("status") != "passed" for trace in traces):
        aggregate_failures.append("retry_trace_case_failed")
    if bool(thresholds["require_retry_allowed_trace"]) and allowed_count < 1:
        aggregate_failures.append("retry_allowed_trace_missing")
    if bool(thresholds["require_retry_blocked_trace"]) and blocked_count < 1:
        aggregate_failures.append("retry_blocked_trace_missing")
    return {
        "status": "passed" if not aggregate_failures else "failed",
        "trace_count": len(traces),
        "retry_allowed_count": allowed_count,
        "retry_blocked_count": blocked_count,
        "traces": traces,
        "failures": aggregate_failures,
    }


def _case_search_critic(*, payload: dict[str, Any]) -> dict[str, Any]:
    explicit = dict(payload.get("search_critic") or {})
    if explicit:
        return {
            "score": float(explicit.get("score") or 0.0),
            "next_action": str(explicit.get("next_action") or "stop").strip() or "stop",
            "reason_codes": _normalize_string_list(explicit.get("reason_codes")),
            "diagnosis": str(explicit.get("diagnosis") or "fixture supplied critic").strip()
            or "fixture supplied critic",
        }
    if bool(payload.get("retry_expected", True)):
        return {
            "score": 0.64,
            "next_action": "retry_with_precision_query",
            "reason_codes": ["coverage_gap"],
            "diagnosis": "fixture baseline is below bounded retry quality threshold",
        }
    return {
        "score": 0.91,
        "next_action": "stop",
        "reason_codes": ["coverage_sufficient"],
        "diagnosis": "fixture baseline is sufficient; bounded retry should stop",
    }


def _merge_code_rows(*row_groups: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in row_groups:
        for row in list(group or []):
            payload = dict(row or {})
            code = str(payload.get("code") or f"row_{len(merged) + 1}").strip()
            if code in seen:
                continue
            seen.add(code)
            merged.append(payload)
    return merged


def _summarize_fixture_search_brief(*, payload: dict[str, Any]) -> dict[str, Any]:
    brief = dict(payload.get("search_brief") or {})
    source_preferences = dict(brief.get("source_preferences") or {})
    strategies = [dict(strategy or {}) for strategy in list(brief.get("search_strategies") or [])]
    return {
        "case_id": str(payload.get("case_id") or ""),
        "intent": str(brief.get("intent") or ""),
        "goal": str(brief.get("goal") or ""),
        "coverage_axes": _normalize_string_list(brief.get("coverage_axes")),
        "time_strategy": dict(brief.get("time_strategy") or {}),
        "search_strategy_count": len(strategies),
        "first_query_terms": _normalize_string_list(strategies[0].get("query_terms")) if strategies else [],
        "attach_source_library": bool(source_preferences.get("attach_source_library")) is True,
        "candidate_items": _normalize_string_list(source_preferences.get("candidate_items")),
        "stop_conditions": dict(brief.get("stop_conditions") or {}),
    }


def _summarize_critic_score_readback(
    *,
    payload: dict[str, Any],
    evaluator: dict[str, Any],
) -> dict[str, Any]:
    critic = _case_search_critic(payload=payload)
    traces = list((evaluator.get("critic_bounded_retry_trace") or {}).get("traces") or [])
    first_boundary = dict((traces[0] or {}).get("boundary") or {}) if traces else {}
    defaults = get_search_policy_defaults()
    return {
        "case_id": str(payload.get("case_id") or ""),
        "score": round(float(critic.get("score") or 0.0), 2),
        "score_threshold": float(first_boundary.get("score_threshold") or defaults.get("retry_score_threshold") or 0.72),
        "next_action": str(critic.get("next_action") or "stop"),
        "reason_codes": _normalize_string_list(critic.get("reason_codes")),
        "diagnosis": str(critic.get("diagnosis") or ""),
        "retry_score_source": str(first_boundary.get("retry_score_source") or "search_critic.score"),
    }


def _summarize_bounded_retry_readback(*, evaluator: dict[str, Any]) -> dict[str, Any]:
    trace = dict(evaluator.get("critic_bounded_retry_trace") or {})
    traces = [dict(item or {}) for item in list(trace.get("traces") or [])]
    defaults = get_search_policy_defaults()
    return {
        "enabled": True,
        "retry_budget": int(defaults.get("retry_budget") or 0),
        "max_retry_rounds": int(defaults.get("max_retry_rounds") or 0),
        "retry_allowed_count": int(trace.get("retry_allowed_count") or 0),
        "retry_blocked_count": int(trace.get("retry_blocked_count") or 0),
        "trace_count": int(trace.get("trace_count") or len(traces)),
        "decisions": [
            {
                "case_id": str(item.get("case_id") or ""),
                "expected_decision": str(item.get("expected_decision") or ""),
                "decision": str((item.get("boundary") or {}).get("decision") or ""),
                "critic_score": float((item.get("boundary") or {}).get("critic_score") or 0.0),
                "replay_score_is_observational": bool(
                    (item.get("boundary") or {}).get("replay_score_is_observational")
                )
                is True,
            }
            for item in traces
        ],
        "replay_score_is_observational": all(
            bool((item.get("boundary") or {}).get("replay_score_is_observational")) is True
            for item in traces
        )
        if traces
        else False,
        "live_provider_quality_claim_allowed": any(
            bool((item.get("boundary") or {}).get("live_provider_quality_claim_allowed")) is True
            for item in traces
        ),
    }


def _summarize_quality_threshold_readback(*, evaluator: dict[str, Any]) -> dict[str, Any]:
    fixture_threshold = dict(evaluator.get("fixture_quality_threshold") or {})
    live_threshold = dict(evaluator.get("live_quality_threshold") or {})
    quality_thresholds = dict(live_threshold.get("quality_thresholds") or {})
    return {
        "threshold_version": str(live_threshold.get("threshold_version") or ""),
        "regression_threshold_version": str(fixture_threshold.get("threshold_version") or ""),
        "threshold_status": str(evaluator.get("threshold_status") or live_threshold.get("threshold_status") or ""),
        "fixture_threshold_status": str(fixture_threshold.get("status") or ""),
        "fixture_case_count": int(fixture_threshold.get("case_count") or 0),
        "fixture_average_uplift": float(fixture_threshold.get("average_uplift") or 0.0),
        "false_positive_retry_rate": float(fixture_threshold.get("false_positive_retry_rate") or 0.0),
        "live_provider_replay_closed": bool(live_threshold.get("live_provider_replay_closed")) is True,
        "quality_claim_allowed": bool(live_threshold.get("quality_claim_allowed")) is True,
        "provider_auto_promotion_allowed": bool(live_threshold.get("provider_auto_promotion_allowed")) is True,
        "required_providers": _normalize_string_list(quality_thresholds.get("required_providers")),
    }


def _build_provider_independent_promotion_decision(
    *,
    quality_threshold_readback: dict[str, Any],
    bounded_retry_readback: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_id": "agent_batch_quality_promotion_readback:provider_auto:hold",
        "decision": "hold_provider_auto_promotion",
        "promotion_allowed": False,
        "provider_auto_promotion_allowed": False,
        "decision_source": "provider_independent_quality_promotion_readback_gate",
        "quality_promotion_state": "fixture_quality_passed_live_provider_gap_open",
        "reason_codes": [
            "fixture_quality_replay_only",
            "live_quality_threshold_replay_gap_open",
            "provider_auto_operator_policy_not_approved",
        ],
        "required_next_evidence": [
            "live_provider_quality_replay",
            "all_provider_threshold_rows_passed",
            "operator_review_approved",
            "provider_auto_rollout_policy_approved",
        ],
        "quality_threshold_status": str(quality_threshold_readback.get("threshold_status") or ""),
        "bounded_retry_trace_count": int(bounded_retry_readback.get("trace_count") or 0),
    }


def _build_promotion_decision_readback(
    *,
    promotion_decision: dict[str, Any],
    input_promotion_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    decision_digest = _stable_digest(promotion_decision)
    readback = deepcopy(promotion_decision)
    input_payload = dict(input_promotion_decision or {})
    input_claimed_promotion = (
        bool(input_payload.get("promotion_allowed")) is True
        or bool(input_payload.get("provider_auto_promotion_allowed")) is True
        or str(input_payload.get("decision") or "").strip().lower().startswith("promote")
    )
    return {
        "readback_performed": True,
        "readback_matches_decision": readback == promotion_decision,
        "decision_digest": decision_digest,
        "readback_digest": _stable_digest(readback),
        "promotion_allowed": bool(readback.get("promotion_allowed")) is True,
        "provider_auto_promotion_allowed": bool(readback.get("provider_auto_promotion_allowed")) is True,
        "input_promotion_claim_rejected": input_claimed_promotion,
        "input_decision": str(input_payload.get("decision") or "") or None,
    }


def _build_provider_independent_boundary(
    *,
    evaluator: dict[str, Any],
    promotion_decision: dict[str, Any],
) -> dict[str, Any]:
    provider_readiness = dict((evaluator.get("provider_readiness") or {}).get("provider_readiness") or {})
    return {
        "network_started": False,
        "live_provider_probe_performed": False,
        "provider_readiness_probe_type": str(provider_readiness.get("probe_type") or ""),
        "live_provider_quality_open": bool(evaluator.get("live_provider_quality_open")) is True,
        "live_provider_quality_closed_by_gate": False,
        "quality_claim_allowed": bool(evaluator.get("quality_claim_allowed")) is True,
        "provider_auto_promotion_allowed": bool(promotion_decision.get("provider_auto_promotion_allowed")) is True,
        "status_passed_means": "fixture search brief, critic score, bounded retry, threshold, and promotion decision readback are internally consistent",
        "status_passed_does_not_mean": "live provider quality or provider=auto promotion is closed",
    }


def _build_promotion_unsupported_claims(
    *,
    critic_score_readback: dict[str, Any],
    quality_threshold_readback: dict[str, Any],
    input_promotion_decision: dict[str, Any] | None,
) -> list[dict[str, str]]:
    claims = [
        {
            "code": "fixture_replay_promotes_provider_auto",
            "claim": "Fixture replay quality can promote live providers into provider=auto.",
            "reason": "Fixture replay is provider-independent and does not start live providers.",
            "required_next_evidence": "Live provider replay with threshold pass rows and operator approval.",
        },
        {
            "code": "critic_score_promotes_provider_auto",
            "claim": "A search critic score can promote provider routing.",
            "reason": (
                "critic_score="
                f"{critic_score_readback.get('score')} only controls bounded retry decisions."
            ),
            "required_next_evidence": "Separate provider-auto rollout policy and live provider quality gate.",
        },
        {
            "code": "quality_threshold_status_promotes_without_live_replay",
            "claim": "A threshold contract can promote providers without a live replay.",
            "reason": (
                "threshold_status="
                f"{quality_threshold_readback.get('threshold_status')} and "
                f"quality_claim_allowed={quality_threshold_readback.get('quality_claim_allowed')}."
            ),
            "required_next_evidence": "Replay status live_provider_quality_replay with all thresholds met.",
        },
    ]
    input_payload = dict(input_promotion_decision or {})
    if (
        bool(input_payload.get("promotion_allowed")) is True
        or bool(input_payload.get("provider_auto_promotion_allowed")) is True
        or str(input_payload.get("decision") or "").strip().lower().startswith("promote")
    ):
        claims.append(
            {
                "code": "input_promotion_decision_claim_rejected",
                "claim": "Caller-supplied promotion decision can mark provider=auto as allowed.",
                "reason": "The gate recomputes promotion and keeps provider-auto promotion held.",
                "required_next_evidence": "Attach a live provider quality replay and operator-approved promotion policy.",
            }
        )
    return claims


def _stable_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _merge_live_quality_thresholds(
    *,
    thresholds: dict[str, Any] | None,
    required_live_providers: list[str] | None,
) -> dict[str, Any]:
    merged = dict(_DEFAULT_LIVE_QUALITY_THRESHOLDS)
    for key, value in dict(thresholds or {}).items():
        if key in merged and value is not None:
            merged[key] = value
    providers = (
        _normalize_string_list(required_live_providers)
        or _normalize_string_list((thresholds or {}).get("required_providers"))
        or list(_DEFAULT_LIVE_PROVIDER_KEYS)
    )
    merged["required_providers"] = providers
    merged["min_case_count"] = max(1, int(merged["min_case_count"]))
    merged["min_results_per_provider"] = max(1, int(merged["min_results_per_provider"]))
    merged["min_source_domains"] = max(1, int(merged["min_source_domains"]))
    merged["min_review_sample_count"] = max(0, int(merged["min_review_sample_count"]))
    merged["max_p95_latency_ms"] = max(1, int(merged["max_p95_latency_ms"]))
    merged["min_relevance_score"] = float(merged["min_relevance_score"])
    merged["min_freshness_score"] = float(merged["min_freshness_score"])
    merged["max_duplicate_rate"] = float(merged["max_duplicate_rate"])
    merged["max_timeout_rate"] = float(merged["max_timeout_rate"])
    merged["require_trace_success"] = bool(merged["require_trace_success"]) is True
    return merged


def _build_fixture_quality_boundary(fixture_quality: dict[str, Any]) -> dict[str, Any]:
    live_gap = dict(fixture_quality.get("live_provider_gap_state") or build_live_provider_gap_state())
    return {
        "source": str(fixture_quality.get("source") or "fixture_quality_missing"),
        "status": str(fixture_quality.get("status") or "missing"),
        "case_count": int(fixture_quality.get("case_count") or 0),
        "average_uplift": float(fixture_quality.get("average_uplift") or 0.0),
        "false_positive_retry_rate": float(fixture_quality.get("false_positive_retry_rate") or 0.0),
        "quality_claim": str(
            fixture_quality.get("quality_claim")
            or "fixture_quality_uplift_is_not_live_provider_quality"
        ),
        "quality_claim_allowed": bool(fixture_quality.get("quality_claim_allowed")) is True,
        "live_provider_quality_equivalent": False,
        "live_provider_gap_state": live_gap,
    }


def _evaluate_live_provider_thresholds(
    *,
    provider: str,
    payload: dict[str, Any],
    thresholds: dict[str, Any],
    replay_type: str,
    live_replay_performed: bool,
) -> dict[str, Any]:
    samples = [dict(item or {}) for item in list(payload.get("result_samples") or payload.get("samples") or [])]
    replay_status = str(payload.get("replay_status") or payload.get("live_probe_status") or "not_run").strip() or "not_run"
    case_count = _optional_int(payload.get("case_count"))
    if case_count is None:
        case_count = len(_normalize_string_list(payload.get("case_ids"))) or (1 if samples else 0)
    result_count = _optional_int(payload.get("result_count"))
    if result_count is None:
        result_count = len(samples)
    source_domains = _normalize_string_list(payload.get("source_domains")) or _sample_domains(samples)
    relevance_score = _metric_float(payload=payload, samples=samples, key="relevance_score")
    freshness_score = _metric_float(payload=payload, samples=samples, key="freshness_score")
    duplicate_rate = _metric_float(payload=payload, samples=samples, key="duplicate_rate")
    if duplicate_rate is None:
        duplicate_rate = _sample_duplicate_rate(samples)
    timeout_rate = _metric_float(payload=payload, samples=samples, key="timeout_rate")
    if timeout_rate is None:
        timeout_rate = 0.0 if payload.get("timeout_count") in (0, "0") else 1.0
    p95_latency_ms = _metric_float(payload=payload, samples=samples, key="p95_latency_ms")
    if p95_latency_ms is None:
        p95_latency_ms = _sample_p95_latency(samples)
    review_sample_count = _optional_int(payload.get("review_sample_count"))
    if review_sample_count is None:
        review_sample_count = sum(1 for sample in samples if bool(sample.get("review_visible")) is True)
    trace_failures = _normalize_string_list(payload.get("trace_failures"))
    trace_success = bool(payload.get("trace_success")) is True or (
        not trace_failures
        and bool(payload.get("provider_live_verified")) is True
        and replay_status in {"ready", "passed", "available"}
    )
    live_replay_attached = (
        live_replay_performed
        and replay_type == "live_provider_quality_replay"
        and bool(payload.get("provider_live_verified")) is True
    )
    checks = {
        "live_replay_attached": live_replay_attached,
        "case_count": case_count >= int(thresholds["min_case_count"]),
        "result_count": result_count >= int(thresholds["min_results_per_provider"]),
        "source_domain_count": len(source_domains) >= int(thresholds["min_source_domains"]),
        "relevance_score": relevance_score is not None
        and relevance_score >= float(thresholds["min_relevance_score"]),
        "freshness_score": freshness_score is not None
        and freshness_score >= float(thresholds["min_freshness_score"]),
        "duplicate_rate": duplicate_rate <= float(thresholds["max_duplicate_rate"]),
        "timeout_rate": timeout_rate <= float(thresholds["max_timeout_rate"]),
        "p95_latency_ms": p95_latency_ms is not None
        and p95_latency_ms <= float(thresholds["max_p95_latency_ms"]),
        "review_sample_count": review_sample_count >= int(thresholds["min_review_sample_count"]),
        "trace_success": trace_success if bool(thresholds["require_trace_success"]) else True,
    }
    threshold_failures = [name for name, passed in checks.items() if not passed]
    if not live_replay_attached:
        remaining_gap = "live_provider_replay_not_attached"
    elif threshold_failures:
        remaining_gap = "live_quality_threshold_not_met"
    else:
        remaining_gap = None
    return {
        "provider": provider,
        "replay_status": replay_status,
        "case_count": case_count,
        "result_count": result_count,
        "source_domain_count": len(source_domains),
        "source_domains": source_domains,
        "relevance_score": relevance_score,
        "freshness_score": freshness_score,
        "duplicate_rate": duplicate_rate,
        "timeout_rate": timeout_rate,
        "p95_latency_ms": p95_latency_ms,
        "review_sample_count": review_sample_count,
        "trace_success": trace_success,
        "threshold_checks": checks,
        "threshold_failures": threshold_failures,
        "thresholds_met": not threshold_failures,
        "quality_claim_allowed": False,
        "input_quality_claim_allowed": bool(payload.get("quality_claim_allowed")) is True,
        "remaining_gap": remaining_gap,
    }


def _build_live_threshold_unsupported_claims(
    *,
    fixture_quality_boundary: dict[str, Any],
    replay_payload: dict[str, Any],
) -> list[dict[str, str]]:
    claims = [
        {
            "code": "fixture_quality_uplift_meets_live_quality_threshold",
            "claim": "Fixture replay uplift can satisfy the live provider quality threshold.",
            "reason": (
                "Fixture uplift is deterministic replay only: "
                f"average_uplift={fixture_quality_boundary.get('average_uplift')} "
                f"quality_claim_allowed={fixture_quality_boundary.get('quality_claim_allowed')}."
            ),
            "required_next_evidence": "Attach a live provider replay artifact evaluated against this threshold contract.",
        },
        {
            "code": "provider_availability_meets_live_quality_threshold",
            "claim": "Provider availability or result count alone proves live symbolic search quality.",
            "reason": "The threshold requires relevance, freshness, source diversity, latency, timeout, trace, and review samples.",
            "required_next_evidence": "Per-provider threshold rows with reviewer-visible samples and trace success.",
        },
        {
            "code": "live_quality_closed_without_threshold_replay",
            "claim": "Live provider quality can be closed without a threshold replay artifact.",
            "reason": "No quality claim is allowed until replay_type=live_provider_quality_replay passes all thresholds.",
            "required_next_evidence": "Run the real provider replay and record threshold pass/fail rows.",
        },
        {
            "code": "provider_auto_promotion_supported_by_threshold",
            "claim": "Passing this threshold contract automatically promotes providers into provider=auto.",
            "reason": "Provider auto-promotion remains blocked by a separate operator rollout policy.",
            "required_next_evidence": "Provider=auto rollout gate with approval, rollback, and production monitoring policy.",
        },
    ]
    if (
        bool(replay_payload.get("quality_claim_allowed")) is True
        or bool(replay_payload.get("live_provider_replay_closed")) is True
    ):
        claims.append(
            {
                "code": "input_live_provider_quality_claim_rejected",
                "claim": "Caller-supplied replay payload may mark live provider quality as closed.",
                "reason": "The threshold contract recomputes closure and ignores input quality claims.",
                "required_next_evidence": "Use computed threshold output instead of caller-owned closure flags.",
            }
        )
    return claims


def _build_live_threshold_remaining_gaps(
    *,
    provider_rows: dict[str, dict[str, Any]],
    live_replay_performed: bool,
    operator_review_status: str,
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not live_replay_performed:
        gaps.append(
            {
                "code": "live_provider_replay_not_run",
                "status": "open",
                "reason": "This contract defines thresholds but does not start SearXNG, YaCy, browser, or web providers.",
                "required_next_evidence": "Run real provider replay and attach threshold-evaluated provider rows.",
            }
        )
    for provider, row in provider_rows.items():
        remaining_gap = row.get("remaining_gap")
        if remaining_gap:
            gaps.append(
                {
                    "code": f"{provider}_{remaining_gap}",
                    "status": "open",
                    "reason": (
                        f"{provider} replay_status={row.get('replay_status')} "
                        f"threshold_failures={row.get('threshold_failures')}"
                    ),
                    "required_next_evidence": "Provider-specific live replay meeting all quality thresholds.",
                }
            )
    if operator_review_status != "approved":
        gaps.append(
            {
                "code": "operator_review_not_approved",
                "status": "open",
                "reason": f"operator_review_status={operator_review_status}",
                "required_next_evidence": "Reviewer-visible result samples and explicit operator approval for live quality closure.",
            }
        )
    return gaps


def _metric_float(*, payload: dict[str, Any], samples: list[dict[str, Any]], key: str) -> float | None:
    metrics = dict(payload.get("metrics") or {})
    value = payload.get(key, metrics.get(key))
    try:
        return float(value)
    except Exception:
        pass
    sample_values: list[float] = []
    for sample in samples:
        try:
            sample_values.append(float(sample.get(key)))
        except Exception:
            continue
    return round(mean(sample_values), 2) if sample_values else None


def _sample_domains(samples: list[dict[str, Any]]) -> list[str]:
    domains: list[str] = []
    for sample in samples:
        domain = str(sample.get("domain") or "").strip().lower()
        if not domain:
            domain = _domain_from_url(str(sample.get("url") or ""))
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def _sample_duplicate_rate(samples: list[dict[str, Any]]) -> float:
    if not samples:
        return 0.0
    duplicate_count = sum(1 for sample in samples if bool(sample.get("duplicate") or sample.get("is_duplicate")))
    return round(_ratio(duplicate_count, len(samples)), 2)


def _sample_p95_latency(samples: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for sample in samples:
        try:
            values.append(float(sample.get("latency_ms")))
        except Exception:
            continue
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return round(ordered[index], 2)


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
