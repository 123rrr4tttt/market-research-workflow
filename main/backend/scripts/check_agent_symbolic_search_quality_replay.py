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
    QUALITY_REPLAY_SCOPE,
    evaluate_quality_retry_boundary,
    score_quality_benchmark_replay,
    score_symbolic_search_quality_replay,
)
from app.services.agent_batch.task_contract import build_search_policy_contract  # noqa: E402

CONTRACT_VERSION = "agent-symbolic-batch-search.wave11.quality_replay.v1"


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


def _check_contract_shape() -> dict[str, Any]:
    policy = build_search_policy_contract()
    quality_replay = dict(policy.get("quality_replay") or {})
    _require(quality_replay.get("artifact") == "search_quality_replay", "quality replay schema missing")
    _require(
        "source_quality_signals" in list(quality_replay.get("required_keys") or []),
        "quality replay schema does not require source_quality_signals",
    )
    _require(
        "quality_claim_allowed" in list(quality_replay.get("live_provider_gap_required_keys") or []),
        "quality replay schema does not expose live-provider claim boundary",
    )
    return {
        "policy_contract_version": policy.get("contract_version"),
        "quality_replay_schema": quality_replay,
    }


def _check_source_quality_signals() -> dict[str, Any]:
    replay = score_symbolic_search_quality_replay(search_brief=_brief(), records=_retry_records())
    _require(replay["scope"] == QUALITY_REPLAY_SCOPE, "quality replay scope mismatch")
    _require(replay["score"] >= 0.8, "retry replay quality score too low")
    _require(replay["coverage"]["source_diversity"] == 1.0, "source diversity signal did not saturate")
    _require(
        replay["live_provider_gap_state"]["quality_claim_allowed"] is False,
        "deterministic replay unexpectedly allows live-provider quality claim",
    )
    signals = list(replay.get("source_quality_signals") or [])
    _require(len(signals) == 2, "expected two source quality signals")
    _require(all(signal.get("provider_trace_state") == "deterministic_replay" for signal in signals), "provider trace state drifted")
    _require(all(signal.get("provider_live_verified") is False for signal in signals), "provider live verification must stay false")
    _require(signals[0].get("source_library_item_key") == "robotics.market_watch", "source-library signal missing item key")
    return replay


def _check_retry_boundary() -> dict[str, Any]:
    baseline = score_symbolic_search_quality_replay(search_brief=_brief(), records=_baseline_records())
    stop_boundary = evaluate_quality_retry_boundary(
        search_critic={
            "score": 0.91,
            "next_action": "stop",
            "reason_codes": ["coverage_sufficient"],
        },
        quality_replay=baseline,
    )
    _require(stop_boundary["decision"] == "retry_blocked", "critic stop boundary did not block retry")
    _require(stop_boundary["reason_code"] == "critic_stop", "critic stop boundary reason mismatch")
    _require(stop_boundary["replay_score_is_observational"] is True, "replay score must be observational")

    source_gap_boundary = evaluate_quality_retry_boundary(
        search_critic={
            "score": 0.84,
            "next_action": "retry_with_source_library",
            "reason_codes": ["source_backing_missing"],
        },
        quality_replay=baseline,
    )
    _require(source_gap_boundary["decision"] == "retry_allowed", "source gap retry boundary did not allow retry")
    _require(source_gap_boundary["threshold_bypassed"] is True, "source gap threshold bypass missing")
    _require(
        source_gap_boundary["live_provider_quality_claim_allowed"] is False,
        "retry boundary unexpectedly allows live-provider quality claim",
    )
    return {
        "critic_stop_boundary": stop_boundary,
        "source_gap_boundary": source_gap_boundary,
    }


def _check_benchmark_uplift() -> dict[str, Any]:
    result = score_quality_benchmark_replay(
        cases=[
            {
                "case_id": "robotics-source-gap",
                "category": "company_watchlist",
                "search_brief": _brief(),
                "baseline_records": _baseline_records(),
                "retry_records": _retry_records(),
                "retry_expected": True,
            }
        ]
    )
    _require(result["status"] == "passed", "deterministic benchmark replay did not pass")
    _require(result["average_uplift"] > 0, "deterministic benchmark uplift was not positive")
    _require(result["false_positive_retry_rate"] == 0.0, "false-positive retry rate must be visible and zero")
    _require(
        result["live_provider_gap_state"]["quality_claim_allowed"] is False,
        "benchmark replay unexpectedly allows live-provider quality claim",
    )
    return result


def build_contract() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    checks = [
        ("contract_shape", _check_contract_shape),
        ("source_quality_signals", _check_source_quality_signals),
        ("critic_retry_boundary", _check_retry_boundary),
        ("deterministic_benchmark_uplift", _check_benchmark_uplift),
    ]
    for name, check in checks:
        try:
            evidence[name] = check()
        except Exception as exc:  # noqa: BLE001
            failures.append({"check": name, "error": str(exc)})

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "provider_quality_replay_boundary_and_benchmark_uplift_no_network",
        "status": "passed" if not failures else "failed",
        "closure_claim": "deterministic_quality_replay_closed_not_live_provider_quality",
        "evidence": evidence,
        "failures": failures,
        "remaining_gaps": [
            {
                "code": "live_provider_quality_not_verified",
                "reason": "checker intentionally does not start SearXNG, YaCy, browser, or web providers",
            },
            {
                "code": "production_benchmark_requires_live_provider_replay",
                "reason": "uplift here is fixture replay only and cannot prove live-provider ranking quality",
            },
            {
                "code": "global_topic_closure_requires_index_audit",
                "reason": "worker evidence is topic-local only and does not edit shared CURRENT_DEV indexes",
            },
        ],
    }


def main() -> int:
    contract = build_contract()
    print(json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
