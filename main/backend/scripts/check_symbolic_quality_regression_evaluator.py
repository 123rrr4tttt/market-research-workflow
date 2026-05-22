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
    QUALITY_REGRESSION_EVALUATOR_SCOPE,
    build_symbolic_quality_regression_evaluator,
)
from app.services.agent_batch.task_contract import build_search_policy_contract  # noqa: E402

CONTRACT_VERSION = "agent-symbolic-batch-search.wave18.quality_regression.v1"


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


def _check_input_contracts() -> dict[str, Any]:
    policy = build_search_policy_contract()
    required_artifacts = {
        "search_brief",
        "search_critic",
        "retry_action",
        "quality_replay",
        "provider_quality_readiness",
        "live_quality_threshold",
    }
    missing = sorted(name for name in required_artifacts if name not in policy)
    _require(not missing, f"missing Wave9/11/13/15 policy inputs: {missing}")
    _require(policy["quality_replay"]["artifact"] == "search_quality_replay", "Wave11 quality replay input drifted")
    _require(
        policy["provider_quality_readiness"]["artifact"] == "provider_quality_readiness",
        "Wave13 provider readiness input drifted",
    )
    _require(
        policy["live_quality_threshold"]["artifact"] == "live_quality_threshold",
        "Wave15 live threshold input drifted",
    )
    return {
        "policy_contract_version": policy.get("contract_version"),
        "input_artifacts": sorted(required_artifacts),
    }


def _check_quality_regression_evaluator() -> dict[str, Any]:
    evaluation = build_symbolic_quality_regression_evaluator(
        fixture_cases=_fixture_cases(),
        provider_statuses=_recorded_provider_statuses(),
    )
    _require(evaluation["scope"] == QUALITY_REGRESSION_EVALUATOR_SCOPE, "Wave18 evaluator scope mismatch")
    _require(evaluation["status"] == "passed", "Wave18 evaluator did not pass")
    _require(evaluation["live_provider_quality_open"] is True, "live provider quality must remain open")
    _require(evaluation["live_provider_quality_closed_by_evaluator"] is False, "evaluator cannot close live quality")
    _require(evaluation["quality_claim_allowed"] is False, "evaluator unexpectedly allowed quality claim")
    _require(
        evaluation["threshold_status"] == "threshold_contract_ready_live_replay_gap_open",
        "live threshold status did not preserve open replay gap",
    )

    fixture_threshold = evaluation["fixture_quality_threshold"]
    _require(fixture_threshold["status"] == "passed", "fixture result quality threshold did not pass")
    _require(fixture_threshold["case_count"] == 2, "fixture case count mismatch")
    _require(fixture_threshold["average_uplift"] > 0, "fixture average uplift was not positive")
    _require(
        fixture_threshold["false_positive_retry_rate"] == 0.0,
        "fixture false-positive retry rate should be zero",
    )

    trace = evaluation["critic_bounded_retry_trace"]
    _require(trace["status"] == "passed", "critic bounded retry trace did not pass")
    _require(trace["retry_allowed_count"] == 1, "expected one retry-allowed trace")
    _require(trace["retry_blocked_count"] == 1, "expected one retry-blocked trace")
    _require(
        all(item["boundary"]["replay_score_is_observational"] is True for item in trace["traces"]),
        "replay score must remain observational in retry trace",
    )
    _require(
        all(item["boundary"]["live_provider_quality_claim_allowed"] is False for item in trace["traces"]),
        "retry trace unexpectedly allowed live provider quality claim",
    )

    claim_codes = {item["code"] for item in evaluation["unsupported_live_provider_claims"]}
    _require("fixture_replay_proves_live_provider_quality" in claim_codes, "fixture/live claim boundary missing")
    _require(
        "live_quality_closed_without_threshold_replay" in claim_codes,
        "live quality closure claim boundary missing",
    )
    gap_codes = {item["code"] for item in evaluation["remaining_live_gaps"]}
    _require("live_provider_replay_not_run" in gap_codes, "live replay open gap missing")
    _require("operator_review_not_approved" in gap_codes, "operator review gap missing")
    return evaluation


def _check_input_live_claim_is_rejected() -> dict[str, Any]:
    evaluation = build_symbolic_quality_regression_evaluator(
        fixture_cases=_fixture_cases(),
        provider_statuses=_recorded_provider_statuses(),
        live_provider_replay={
            "replay_type": "not_run",
            "quality_claim_allowed": True,
            "live_provider_replay_closed": True,
            "providers": _recorded_provider_statuses(),
        },
    )
    _require(evaluation["status"] == "passed", "input claim rejection evaluator did not pass")
    _require(evaluation["live_provider_quality_open"] is True, "input claim must not close live quality")
    _require(evaluation["quality_claim_allowed"] is False, "input quality claim was not rejected")
    _require(
        "input_live_provider_quality_claim_rejected"
        in {item["code"] for item in evaluation["unsupported_live_provider_claims"]},
        "input live quality claim rejection missing",
    )
    return {
        "status": evaluation["status"],
        "live_provider_quality_open": evaluation["live_provider_quality_open"],
        "threshold_status": evaluation["threshold_status"],
        "quality_claim_allowed": evaluation["quality_claim_allowed"],
    }


def build_contract() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    checks = [
        ("input_contracts", _check_input_contracts),
        ("quality_regression_evaluator", _check_quality_regression_evaluator),
        ("input_live_claim_rejected", _check_input_live_claim_is_rejected),
    ]
    for name, check in checks:
        try:
            evidence[name] = check()
        except Exception as exc:  # noqa: BLE001
            failures.append({"check": name, "error": str(exc)})

    evaluation = evidence.get("quality_regression_evaluator") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "provider_independent_symbolic_quality_regression_no_network",
        "status": "passed" if not failures else "failed",
        "closure_claim": "fixture_quality_regression_passed_live_provider_quality_not_closed",
        "live_provider_quality_open": evaluation.get("live_provider_quality_open", True),
        "threshold_status": evaluation.get("threshold_status"),
        "fixture_quality_threshold": evaluation.get("fixture_quality_threshold"),
        "critic_bounded_retry_trace": evaluation.get("critic_bounded_retry_trace"),
        "unsupported_live_provider_claims": evaluation.get("unsupported_live_provider_claims", []),
        "remaining_live_gaps": evaluation.get("remaining_live_gaps", []),
        "evidence": evidence,
        "failures": failures,
    }


def main() -> int:
    contract = build_contract()
    print(json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
