#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_batch.search_quality_replay import (  # noqa: E402
    QUALITY_PROMOTION_READBACK_SCOPE,
    build_symbolic_quality_promotion_readback_gate,
)
from app.services.agent_batch.task_contract import build_search_policy_contract  # noqa: E402

CONTRACT_VERSION = "agent-symbolic-batch-search.wave20.quality_promotion_readback.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _brief() -> dict[str, Any]:
    return {
        "intent": "market_research_general",
        "goal": "search embodied ai robotics commercialization companies product latest news",
        "coverage_axes": ["products", "companies", "recent_movement"],
        "time_strategy": {"mode": "recent", "days_back": 30},
        "search_strategies": [
            {
                "label": "broad",
                "query_terms": ["embodied ai robotics commercialization companies product latest news"],
            }
        ],
        "source_preferences": {
            "attach_source_library": False,
            "candidate_items": ["robotics.market_watch"],
        },
        "stop_conditions": {
            "min_entity_count": 4,
            "min_source_domains": 2,
            "max_search_rounds": 2,
        },
    }


def _baseline_records() -> list[dict[str, Any]]:
    return [
        {
            "record_id": "baseline-1",
            "title": "Robotics company announces product launch",
            "url": "https://example.com/robotics-launch",
            "channel": "search.market",
            "provider": "replay_fixture",
            "axis_hits": ["products", "companies"],
            "published_days_back": 12,
            "entities": ["Acme Robotics"],
        },
        {
            "record_id": "baseline-2",
            "title": "Old robotics market overview",
            "url": "https://example.org/robotics-overview",
            "channel": "search.market",
            "provider": "replay_fixture",
            "axis_hits": ["companies"],
            "published_days_back": 80,
            "entities": ["General Robotics"],
        },
    ]


def _retry_records() -> list[dict[str, Any]]:
    return [
        {
            "record_id": "retry-1",
            "title": "Robotics Market Watch product and funding scan",
            "url": "https://robotics.example.com/watch/product-funding",
            "channel": "source_library",
            "provider": "replay_fixture",
            "source_library_item_key": "robotics.market_watch",
            "source_tier": "tier_2_directed_high_value",
            "axis_hits": ["products", "companies", "recent_movement"],
            "published_days_back": 5,
            "entities": ["Acme Robotics", "BotWorks"],
        },
        {
            "record_id": "retry-2",
            "title": "Embodied AI company launch briefing",
            "url": "https://venture.example.com/embodied-ai-launch",
            "channel": "search.market",
            "provider": "replay_fixture",
            "axis_hits": ["products", "companies", "recent_movement"],
            "published_days_back": 3,
            "entities": ["MotionAI", "Terminal Robotics"],
        },
    ]


def _fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "robotics-source-gap",
            "category": "company_watchlist",
            "search_brief": _brief(),
            "baseline_records": _baseline_records(),
            "retry_records": _retry_records(),
            "retry_expected": True,
            "search_critic": {
                "score": 0.66,
                "next_action": "retry_with_precision_query",
                "reason_codes": ["entity_coverage_gap", "freshness_gap"],
                "diagnosis": "baseline records miss fresh multi-company coverage",
            },
        },
        {
            "case_id": "robotics-sufficient-stop",
            "category": "company_watchlist",
            "search_brief": _brief(),
            "baseline_records": _retry_records(),
            "retry_records": _retry_records(),
            "retry_expected": False,
            "search_critic": {
                "score": 0.91,
                "next_action": "stop",
                "reason_codes": ["coverage_sufficient"],
                "diagnosis": "fixture already satisfies coverage and freshness",
            },
        },
    ]


def _recorded_provider_statuses() -> dict[str, dict[str, Any]]:
    return {
        "searxng": {
            "live_probe_status": "unavailable",
            "result_count": 0,
            "fallback_reason": "ConnectError",
        },
        "yacy": {
            "live_probe_status": "not_run",
            "result_count": 0,
            "fallback_reason": "live_probe_not_run",
        },
        "web": {
            "live_probe_status": "not_run",
            "result_count": 0,
            "fallback_reason": "live_probe_not_run",
        },
    }


def _check_contract_shape() -> dict[str, Any]:
    policy = build_search_policy_contract()
    promotion = dict(policy.get("quality_promotion_readback") or {})
    _require(
        promotion.get("artifact") == "quality_promotion_readback",
        "quality promotion readback schema missing",
    )
    _require(
        promotion.get("scope") == QUALITY_PROMOTION_READBACK_SCOPE,
        "quality promotion readback scope mismatch",
    )
    required = set(promotion.get("required_keys") or [])
    for key in [
        "fixture_search_brief",
        "critic_score_readback",
        "bounded_retry_readback",
        "quality_threshold_readback",
        "promotion_decision_readback",
    ]:
        _require(key in required, f"promotion readback schema missing {key}")
    _require(
        "decision_digest" in set(promotion.get("promotion_decision_readback_required_keys") or []),
        "promotion decision readback schema missing digest",
    )
    return {
        "policy_contract_version": policy.get("contract_version"),
        "quality_promotion_readback_schema": promotion,
    }


def _policy_approved(payload: dict[str, Any] | None) -> bool:
    policy = dict(payload or {})
    return (
        str(policy.get("approval_status") or "").strip().lower() == "approved"
        and bool(policy.get("approved_providers"))
        and bool(policy.get("rollback_criteria"))
        and bool(policy.get("monitoring_requirements"))
        and bool(policy.get("manual_review_artifact"))
    )


def _check_promotion_gate(
    *,
    live_provider_replay: dict[str, Any] | None = None,
    provider_auto_rollout_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = build_symbolic_quality_promotion_readback_gate(
        fixture_cases=_fixture_cases(),
        provider_statuses=_recorded_provider_statuses(),
        live_provider_replay=live_provider_replay,
        provider_auto_rollout_policy=provider_auto_rollout_policy,
    )
    live_replay_attached = bool(live_provider_replay)
    provider_auto_policy_approved = _policy_approved(provider_auto_rollout_policy)
    provider_auto_promotion_expected = live_replay_attached and provider_auto_policy_approved
    expected_gate_state = (
        "live_provider_quality_promotion_approved"
        if provider_auto_promotion_expected
        else "provider_independent_quality_promotion_held_live_gap_open"
    )
    _require(gate["scope"] == QUALITY_PROMOTION_READBACK_SCOPE, "promotion gate scope mismatch")
    _require(gate["status"] == "passed", "promotion gate did not pass")
    _require(gate["gate_state"] == expected_gate_state, "promotion gate state drifted")

    brief = gate["fixture_search_brief"]
    _require(brief["case_id"] == "robotics-source-gap", "fixture search brief case_id mismatch")
    _require(brief["intent"] == "market_research_general", "fixture search brief intent mismatch")
    _require("recent_movement" in brief["coverage_axes"], "fixture search brief axes missing recent_movement")
    _require(brief["candidate_items"] == ["robotics.market_watch"], "fixture candidate item mismatch")
    _require(brief["time_strategy"]["days_back"] == 30, "fixture days_back mismatch")

    critic = gate["critic_score_readback"]
    _require(critic["score"] == 0.66, "critic score readback mismatch")
    _require(critic["score_threshold"] == 0.72, "critic threshold readback mismatch")
    _require(critic["next_action"] == "retry_with_precision_query", "critic next_action mismatch")
    _require(critic["retry_score_source"] == "search_critic.score", "critic score source mismatch")

    retry = gate["bounded_retry_readback"]
    _require(retry["enabled"] is True, "bounded retry not enabled")
    _require(retry["retry_budget"] == 1, "bounded retry budget drifted")
    _require(retry["max_retry_rounds"] == 1, "bounded retry max rounds drifted")
    _require(retry["retry_allowed_count"] == 1, "expected one retry-allowed readback")
    _require(retry["retry_blocked_count"] == 1, "expected one retry-blocked readback")
    _require(retry["replay_score_is_observational"] is True, "retry replay score must be observational")
    _require(retry["live_provider_quality_claim_allowed"] is False, "retry readback allowed live quality claim")

    threshold = gate["quality_threshold_readback"]
    _require(threshold["fixture_threshold_status"] == "passed", "fixture quality threshold did not pass")
    if live_replay_attached:
        _require(
            threshold["threshold_status"] == "live_quality_thresholds_met",
            "quality threshold readback did not close live replay",
        )
        _require(threshold["live_provider_replay_closed"] is True, "live provider replay did not close")
        _require(threshold["quality_claim_allowed"] is True, "quality claim not allowed after live closure")
    else:
        _require(
            threshold["threshold_status"] == "threshold_contract_ready_live_replay_gap_open",
            "quality threshold readback did not keep live gap open",
        )
        _require(threshold["live_provider_replay_closed"] is False, "live provider replay unexpectedly closed")
        _require(threshold["quality_claim_allowed"] is False, "quality claim unexpectedly allowed")
        _require(threshold["provider_auto_promotion_allowed"] is False, "provider auto promotion unexpectedly allowed")

    decision = gate["promotion_decision"]
    if provider_auto_promotion_expected:
        _require(decision["decision"] == "promote_provider_auto", "promotion decision mismatch")
        _require(decision["promotion_allowed"] is True, "promotion was not allowed")
        _require(decision["provider_auto_promotion_allowed"] is True, "provider auto promotion was not allowed")
        _require(
            "provider_auto_rollout_policy_approved" in decision["reason_codes"],
            "promotion decision missing policy-approved reason",
        )
    elif live_replay_attached:
        _require(decision["decision"] == "hold_provider_auto_promotion", "promotion decision mismatch")
        _require(decision["promotion_allowed"] is False, "promotion unexpectedly allowed")
        _require(decision["provider_auto_promotion_allowed"] is False, "provider auto promotion unexpectedly allowed")
        _require(
            "provider_auto_operator_policy_not_approved" in decision["reason_codes"],
            "promotion decision missing policy-open reason",
        )
    else:
        _require(decision["decision"] == "hold_provider_auto_promotion", "promotion decision mismatch")
        _require(decision["promotion_allowed"] is False, "promotion unexpectedly allowed")
        _require(decision["provider_auto_promotion_allowed"] is False, "provider auto promotion unexpectedly allowed")
        _require(
            "live_quality_threshold_replay_gap_open" in decision["reason_codes"],
            "promotion decision missing threshold-open reason",
        )

    readback = gate["promotion_decision_readback"]
    _require(readback["readback_performed"] is True, "promotion decision readback not performed")
    _require(readback["readback_matches_decision"] is True, "promotion decision readback mismatch")
    _require(readback["decision_digest"] == readback["readback_digest"], "promotion decision digest mismatch")
    _require(readback["promotion_allowed"] is provider_auto_promotion_expected, "promotion readback state mismatch")
    _require(
        readback["provider_auto_promotion_allowed"] is provider_auto_promotion_expected,
        "provider-auto readback state mismatch",
    )

    boundary = gate["provider_independent_boundary"]
    _require(boundary["network_started"] is False, "promotion gate should only read attached evidence")
    _require(
        boundary["live_provider_probe_performed"] is live_replay_attached,
        "live provider probe evidence state mismatch",
    )
    _require(
        boundary["live_provider_quality_open"] is (not live_replay_attached),
        "live provider quality open state mismatch",
    )
    _require(boundary["quality_claim_allowed"] is live_replay_attached, "quality claim state mismatch")
    _require(
        boundary["provider_auto_promotion_allowed"] is provider_auto_promotion_expected,
        "provider-auto promotion boundary state mismatch",
    )

    claim_codes = {item["code"] for item in gate["unsupported_promotion_claims"]}
    if not live_replay_attached:
        _require("fixture_replay_promotes_provider_auto" in claim_codes, "fixture promotion claim boundary missing")
        _require("critic_score_promotes_provider_auto" in claim_codes, "critic promotion claim boundary missing")
        _require(
            "quality_threshold_status_promotes_without_live_replay" in claim_codes,
            "threshold promotion claim boundary missing",
        )
    gap_codes = {item["code"] for item in gate["remaining_live_gaps"]}
    if provider_auto_promotion_expected:
        _require(not gap_codes, "live replay closure should leave no remaining gaps")
    elif live_replay_attached:
        _require(
            "provider_auto_rollout_policy_not_approved" in gap_codes,
            "provider-auto rollout policy gap missing",
        )
        _require("provider_auto_promotion_readback_hold" in gap_codes, "promotion readback hold gap missing")
    else:
        _require("live_provider_replay_not_run" in gap_codes, "live provider replay gap missing")
        _require("operator_review_not_approved" in gap_codes, "operator review gap missing")
        _require("provider_auto_promotion_readback_hold" in gap_codes, "promotion readback hold gap missing")
    return gate


def _check_input_promotion_claim_is_rejected() -> dict[str, Any]:
    gate = build_symbolic_quality_promotion_readback_gate(
        fixture_cases=_fixture_cases(),
        provider_statuses=_recorded_provider_statuses(),
        input_promotion_decision={
            "decision": "promote_provider_auto",
            "promotion_allowed": True,
            "provider_auto_promotion_allowed": True,
        },
    )
    _require(gate["status"] == "passed", "input promotion rejection gate did not pass")
    _require(gate["promotion_decision"]["promotion_allowed"] is False, "input promotion claim was accepted")
    _require(
        gate["promotion_decision_readback"]["input_promotion_claim_rejected"] is True,
        "input promotion claim rejection readback missing",
    )
    _require(
        "input_promotion_decision_claim_rejected"
        in {item["code"] for item in gate["unsupported_promotion_claims"]},
        "input promotion unsupported claim missing",
    )
    return {
        "status": gate["status"],
        "promotion_decision": gate["promotion_decision"],
        "promotion_decision_readback": gate["promotion_decision_readback"],
        "unsupported_promotion_claims": gate["unsupported_promotion_claims"],
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AssertionError(f"expected object JSON: {path}")
    return payload


def build_contract(
    *,
    live_provider_replay: dict[str, Any] | None = None,
    provider_auto_rollout_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    checks = [
        ("contract_shape", _check_contract_shape),
        (
            "promotion_gate",
            lambda: _check_promotion_gate(
                live_provider_replay=live_provider_replay,
                provider_auto_rollout_policy=provider_auto_rollout_policy,
            ),
        ),
        ("input_promotion_claim_rejected", _check_input_promotion_claim_is_rejected),
    ]
    for name, check in checks:
        try:
            evidence[name] = check()
        except Exception as exc:  # noqa: BLE001
            failures.append({"check": name, "error": str(exc)})

    gate = evidence.get("promotion_gate") or {}
    provider_auto_promotion_approved = (
        gate.get("gate_state") == "live_provider_quality_promotion_approved" and not failures
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": (
            "live_provider_agent_batch_quality_promotion_readback"
            if live_provider_replay
            else "provider_independent_agent_batch_quality_promotion_readback_no_network"
        ),
        "status": "passed" if not failures else "failed",
        "closure_claim": (
            "quality_promotion_readback_validated_live_provider_quality_closed"
            if provider_auto_promotion_approved
            else "quality_promotion_readback_validated_live_provider_quality_not_closed"
        ),
        "gate_state": gate.get("gate_state"),
        "fixture_search_brief": gate.get("fixture_search_brief"),
        "critic_score_readback": gate.get("critic_score_readback"),
        "bounded_retry_readback": gate.get("bounded_retry_readback"),
        "quality_threshold_readback": gate.get("quality_threshold_readback"),
        "promotion_decision": gate.get("promotion_decision"),
        "promotion_decision_readback": gate.get("promotion_decision_readback"),
        "provider_independent_boundary": gate.get("provider_independent_boundary"),
        "unsupported_promotion_claims": gate.get("unsupported_promotion_claims", []),
        "remaining_live_gaps": gate.get("remaining_live_gaps", []),
        "evidence": evidence,
        "failures": failures,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate agent-batch quality promotion readback.")
    parser.add_argument("--live-provider-replay-json", default=None)
    parser.add_argument("--provider-auto-policy-json", default=None)
    args = parser.parse_args()

    contract = build_contract(
        live_provider_replay=_load_json(Path(args.live_provider_replay_json))
        if args.live_provider_replay_json
        else None,
        provider_auto_rollout_policy=_load_json(Path(args.provider_auto_policy_json))
        if args.provider_auto_policy_json
        else None,
    )
    print(json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
