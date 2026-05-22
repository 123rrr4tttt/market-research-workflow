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
    PROVIDER_QUALITY_READINESS_SCOPE,
    build_symbolic_provider_quality_readiness,
)
from app.services.agent_batch.task_contract import build_search_policy_contract  # noqa: E402

CONTRACT_VERSION = "agent-symbolic-batch-search.wave13.provider_quality_readiness.v1"


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
        }
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
    readiness = dict(policy.get("provider_quality_readiness") or {})
    _require(readiness.get("artifact") == "provider_quality_readiness", "provider quality readiness schema missing")
    _require(readiness.get("scope") == PROVIDER_QUALITY_READINESS_SCOPE, "provider quality readiness scope mismatch")
    _require(
        "unsupported_live_provider_claims" in list(readiness.get("required_keys") or []),
        "readiness schema does not require unsupported live-provider claims",
    )
    _require(
        "remaining_live_gaps" in list(readiness.get("required_keys") or []),
        "readiness schema does not require remaining live gaps",
    )
    return {
        "policy_contract_version": policy.get("contract_version"),
        "provider_quality_readiness_schema": readiness,
    }


def _check_readiness_boundary() -> dict[str, Any]:
    readiness = build_symbolic_provider_quality_readiness(
        fixture_cases=_fixture_cases(),
        provider_statuses=_recorded_provider_statuses(),
    )
    _require(readiness["scope"] == PROVIDER_QUALITY_READINESS_SCOPE, "readiness scope mismatch")
    _require(readiness["status"] == "passed", "readiness gate did not pass")
    _require(
        readiness["readiness_state"] == "fixture_quality_ready_live_provider_gap_open",
        "readiness state should keep live gap open",
    )
    _require(
        readiness["closure_claim"] == "fixture_quality_recorded_live_provider_quality_not_closed",
        "readiness closure claim drifted",
    )

    fixture = readiness["fixture_quality"]
    _require(fixture["status"] == "passed", "fixture quality did not pass")
    _require(fixture["case_count"] == 1, "fixture case count mismatch")
    _require(fixture["average_uplift"] > 0, "fixture uplift must be positive")
    _require(fixture["false_positive_retry_rate"] == 0.0, "false-positive rate must be zero")
    _require(fixture["quality_claim_allowed"] is False, "fixture quality cannot allow live claim")

    provider_readiness = readiness["provider_readiness"]
    _require(provider_readiness["quality_claim_allowed"] is False, "provider readiness allowed quality claim")
    _require(provider_readiness["auto_promotion_allowed"] is False, "provider auto promotion should be blocked")
    providers = provider_readiness["providers"]
    _require(sorted(providers) == ["searxng", "web", "yacy"], "provider set mismatch")
    _require(providers["searxng"]["live_probe_status"] == "unavailable", "searxng status not recorded")
    _require(providers["yacy"]["remaining_gap"] == "live_provider_not_ready", "yacy live gap missing")
    _require(all(row["quality_claim_allowed"] is False for row in providers.values()), "provider row allowed claim")

    claim_codes = {item["code"] for item in readiness["unsupported_live_provider_claims"]}
    _require("fixture_replay_proves_live_provider_quality" in claim_codes, "fixture/live unsupported claim missing")
    _require("provider_auto_promotion_supported" in claim_codes, "provider auto unsupported claim missing")
    _require("live_retry_uplift_closed" in claim_codes, "live uplift unsupported claim missing")

    gap_codes = {item["code"] for item in readiness["remaining_live_gaps"]}
    _require("searxng_live_provider_not_ready" in gap_codes, "searxng live gap missing")
    _require("live_retry_uplift_replay_not_run" in gap_codes, "live retry replay gap missing")
    _require(
        readiness["gate_semantics"]["status_passed_does_not_mean"]
        == "live provider quality, provider=auto promotion, or production ranking quality",
        "gate semantics drifted",
    )
    return readiness


def _check_input_quality_claim_rejected() -> dict[str, Any]:
    readiness = build_symbolic_provider_quality_readiness(
        fixture_cases=_fixture_cases(),
        provider_statuses={
            "searxng": {
                "live_probe_status": "ready",
                "result_count": 3,
                "fallback_reason": None,
                "result_quality_verified": True,
                "quality_claim_allowed": True,
                "trace_failures": [],
            }
        },
        required_live_providers=["searxng"],
    )
    provider = readiness["provider_readiness"]["providers"]["searxng"]
    _require(provider["input_quality_claim_allowed"] is True, "input quality claim was not recorded")
    _require(provider["quality_claim_allowed"] is False, "input quality claim was not rejected")
    _require(
        "input_provider_quality_claim_rejected"
        in {item["code"] for item in readiness["unsupported_live_provider_claims"]},
        "unsupported input quality claim was not recorded",
    )
    _require(
        "searxng_symbolic_live_uplift_not_verified"
        in {item["code"] for item in readiness["remaining_live_gaps"]},
        "symbolic live uplift gap missing for ready provider input",
    )
    return readiness


def build_contract() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    checks = [
        ("contract_shape", _check_contract_shape),
        ("readiness_boundary", _check_readiness_boundary),
        ("input_quality_claim_rejected", _check_input_quality_claim_rejected),
    ]
    for name, check in checks:
        try:
            evidence[name] = check()
        except Exception as exc:  # noqa: BLE001
            failures.append({"check": name, "error": str(exc)})

    readiness = evidence.get("readiness_boundary") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "symbolic_search_provider_quality_readiness_no_network",
        "status": "passed" if not failures else "failed",
        "closure_claim": "fixture_quality_recorded_live_provider_quality_not_closed",
        "fixture_quality": readiness.get("fixture_quality"),
        "unsupported_live_provider_claims": readiness.get("unsupported_live_provider_claims", []),
        "remaining_live_gaps": readiness.get("remaining_live_gaps", []),
        "evidence": evidence,
        "failures": failures,
    }


def main() -> int:
    contract = build_contract()
    print(json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
