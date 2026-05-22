from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

pytestmark = pytest.mark.unit

try:
    from app.services.agent_batch.search_quality_replay import (
        build_symbolic_quality_regression_evaluator,
    )
except Exception as exc:  # pragma: no cover - dependency/import guard
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _load_checker_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_symbolic_quality_regression_evaluator.py"
    )
    spec = importlib.util.spec_from_file_location("check_symbolic_quality_regression_evaluator", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _brief() -> dict:
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
        "source_preferences": {"attach_source_library": False, "candidate_items": ["robotics.market_watch"]},
        "stop_conditions": {"min_entity_count": 4, "min_source_domains": 2, "max_search_rounds": 2},
    }


def _baseline_records() -> list[dict]:
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


def _retry_records() -> list[dict]:
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


def _fixture_cases() -> list[dict]:
    return [
        {
            "case_id": "robotics-source-gap",
            "search_brief": _brief(),
            "baseline_records": _baseline_records(),
            "retry_records": _retry_records(),
            "retry_expected": True,
            "search_critic": {
                "score": 0.66,
                "next_action": "retry_with_precision_query",
                "reason_codes": ["entity_coverage_gap", "freshness_gap"],
            },
        },
        {
            "case_id": "robotics-sufficient-stop",
            "search_brief": _brief(),
            "baseline_records": _retry_records(),
            "retry_records": _retry_records(),
            "retry_expected": False,
            "search_critic": {
                "score": 0.91,
                "next_action": "stop",
                "reason_codes": ["coverage_sufficient"],
            },
        },
    ]


def _provider_statuses() -> dict[str, dict]:
    return {
        "searxng": {"live_probe_status": "unavailable", "result_count": 0, "fallback_reason": "ConnectError"},
        "yacy": {"live_probe_status": "not_run", "result_count": 0, "fallback_reason": "live_probe_not_run"},
        "web": {"live_probe_status": "not_run", "result_count": 0, "fallback_reason": "live_probe_not_run"},
    }


class SymbolicQualityRegressionEvaluatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"quality regression evaluator tests require backend dependencies: {_IMPORT_ERROR}")

    def test_checker_passes_without_closing_live_provider_quality(self) -> None:
        checker = _load_checker_module()
        contract = checker.build_contract()

        self.assertEqual(contract["contract_version"], "agent-symbolic-batch-search.wave18.quality_regression.v1")
        self.assertEqual(contract["scope"], "provider_independent_symbolic_quality_regression_no_network")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertTrue(contract["live_provider_quality_open"])
        self.assertEqual(contract["threshold_status"], "threshold_contract_ready_live_replay_gap_open")

        fixture_threshold = contract["fixture_quality_threshold"]
        self.assertEqual(fixture_threshold["status"], "passed")
        self.assertEqual(fixture_threshold["case_count"], 2)
        self.assertGreater(fixture_threshold["average_uplift"], 0.0)

        trace = contract["critic_bounded_retry_trace"]
        self.assertEqual(trace["status"], "passed")
        self.assertEqual(trace["retry_allowed_count"], 1)
        self.assertEqual(trace["retry_blocked_count"], 1)
        self.assertTrue(all(item["boundary"]["replay_score_is_observational"] for item in trace["traces"]))

    def test_provider_independent_evaluator_rejects_input_live_quality_claims(self) -> None:
        evaluation = build_symbolic_quality_regression_evaluator(
            fixture_cases=_fixture_cases(),
            provider_statuses=_provider_statuses(),
            live_provider_replay={
                "replay_type": "not_run",
                "quality_claim_allowed": True,
                "live_provider_replay_closed": True,
                "providers": _provider_statuses(),
            },
        )

        self.assertEqual(evaluation["status"], "passed")
        self.assertTrue(evaluation["live_provider_quality_open"])
        self.assertFalse(evaluation["live_provider_quality_closed_by_evaluator"])
        self.assertFalse(evaluation["quality_claim_allowed"])
        self.assertEqual(evaluation["threshold_status"], "threshold_contract_ready_live_replay_gap_open")
        self.assertIn(
            "input_live_provider_quality_claim_rejected",
            {item["code"] for item in evaluation["unsupported_live_provider_claims"]},
        )
        self.assertIn(
            "live_provider_replay_not_run",
            {item["code"] for item in evaluation["remaining_live_gaps"]},
        )


if __name__ == "__main__":
    unittest.main()
