from __future__ import annotations

from copy import deepcopy
from typing import Any

SEARCH_POLICY_BENCHMARK_CONTRACT_VERSION = "agent_batch.search_policy_benchmark.v1"

_BENCHMARK_CASES: list[dict[str, Any]] = [
    {
        "case_id": "market_landscape_01",
        "category": "market_landscape",
        "command": "搜集智能终端市场格局、主要厂商和近期动态",
        "expected_coverage_axes": ["products", "companies", "recent_movement"],
        "expected_retry_behavior": "source_or_precision",
    },
    {
        "case_id": "company_watchlist_01",
        "category": "company_watchlist",
        "command": "跟踪 AI 终端公司的发布、融资和合作动态",
        "expected_coverage_axes": ["companies", "recent_movement"],
        "expected_retry_behavior": "source_or_precision",
    },
    {
        "case_id": "product_scan_01",
        "category": "product_scan",
        "command": "搜索最近 30 天的智能终端产品发布和价格变化",
        "expected_coverage_axes": ["products", "pricing", "recent_movement"],
        "expected_retry_behavior": "precision_or_time_shift",
    },
    {
        "case_id": "financing_scan_01",
        "category": "financing_scan",
        "command": "搜索人形机器人和智能终端赛道融资动态",
        "expected_coverage_axes": ["companies", "recent_movement"],
        "expected_retry_behavior": "source_or_precision",
    },
    {
        "case_id": "policy_tracking_01",
        "category": "policy_tracking",
        "command": "跟踪智能终端行业最近 90 天的监管政策和标准变化",
        "expected_coverage_axes": ["policy", "recent_movement"],
        "expected_retry_behavior": "precision_or_time_shift",
    },
]


def build_search_policy_benchmark_pack() -> dict[str, Any]:
    return {
        "contract_version": SEARCH_POLICY_BENCHMARK_CONTRACT_VERSION,
        "cases": deepcopy(_BENCHMARK_CASES),
        "rubric_dimensions": [
            "entity_coverage",
            "source_diversity",
            "freshness_fit",
            "retry_usefulness",
            "latency_cost_visibility",
        ],
    }


def evaluate_search_policy_gate(metrics: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(metrics or {})
    critic_job_count = int(payload.get("critic_job_count") or 0)
    retry_counts = dict(payload.get("retry_outcome_counts") or {})
    average_submit_rounds = payload.get("average_submit_rounds")

    criteria = [
        {
            "name": "benchmark_evidence",
            "status": "pass" if critic_job_count >= 5 else "hold",
            "detail": f"critic_job_count={critic_job_count}",
        },
        {
            "name": "retry_visibility",
            "status": "pass" if int(retry_counts.get("scheduled") or 0) > 0 else "hold",
            "detail": f"scheduled_retries={int(retry_counts.get('scheduled') or 0)}",
        },
        {
            "name": "round_budget",
            "status": "pass" if average_submit_rounds is None or float(average_submit_rounds) <= 2.0 else "fail",
            "detail": f"average_submit_rounds={average_submit_rounds}",
        },
        {
            "name": "retry_uplift",
            "status": "hold",
            "detail": "manual benchmark rubric still required for uplift judgment",
        },
    ]

    if any(item["status"] == "fail" for item in criteria):
        decision = "no_go"
    elif all(item["status"] == "pass" for item in criteria):
        decision = "go"
    else:
        decision = "hold"

    return {
        "contract_version": SEARCH_POLICY_BENCHMARK_CONTRACT_VERSION,
        "decision": decision,
        "criteria": criteria,
    }
