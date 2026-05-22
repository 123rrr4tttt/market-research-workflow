from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest

pytestmark = pytest.mark.unit

try:
    from app.services.agent_batch.search_quality_replay import (
        build_symbolic_quality_promotion_readback_gate,
    )
except Exception as exc:  # pragma: no cover - dependency/import guard
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _load_checker_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_agent_batch_quality_promotion_readback.py"
    )
    spec = importlib.util.spec_from_file_location("check_agent_batch_quality_promotion_readback", module_path)
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
            "category": "company_watchlist",
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
            "category": "company_watchlist",
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


class AgentBatchQualityPromotionReadbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"quality promotion readback tests require backend dependencies: {_IMPORT_ERROR}")

    def test_checker_validates_fixture_critic_retry_threshold_and_promotion_readback(self) -> None:
        checker = _load_checker_module()
        contract = checker.build_contract()

        self.assertEqual(
            contract["contract_version"],
            "agent-symbolic-batch-search.wave20.quality_promotion_readback.v1",
        )
        self.assertEqual(contract["scope"], "provider_independent_agent_batch_quality_promotion_readback_no_network")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertEqual(contract["gate_state"], "provider_independent_quality_promotion_held_live_gap_open")

        brief = contract["fixture_search_brief"]
        self.assertEqual(brief["case_id"], "robotics-source-gap")
        self.assertEqual(brief["candidate_items"], ["robotics.market_watch"])
        self.assertEqual(brief["time_strategy"]["days_back"], 30)

        critic = contract["critic_score_readback"]
        self.assertEqual(critic["score"], 0.66)
        self.assertEqual(critic["score_threshold"], 0.72)
        self.assertEqual(critic["retry_score_source"], "search_critic.score")

        retry = contract["bounded_retry_readback"]
        self.assertTrue(retry["enabled"])
        self.assertEqual(retry["retry_budget"], 1)
        self.assertEqual(retry["max_retry_rounds"], 1)
        self.assertEqual(retry["retry_allowed_count"], 1)
        self.assertEqual(retry["retry_blocked_count"], 1)
        self.assertTrue(retry["replay_score_is_observational"])

        threshold = contract["quality_threshold_readback"]
        self.assertEqual(threshold["fixture_threshold_status"], "passed")
        self.assertEqual(threshold["threshold_status"], "threshold_contract_ready_live_replay_gap_open")
        self.assertFalse(threshold["live_provider_replay_closed"])
        self.assertFalse(threshold["quality_claim_allowed"])

        decision = contract["promotion_decision"]
        self.assertEqual(decision["decision"], "hold_provider_auto_promotion")
        self.assertFalse(decision["promotion_allowed"])
        self.assertFalse(decision["provider_auto_promotion_allowed"])

        readback = contract["promotion_decision_readback"]
        self.assertTrue(readback["readback_performed"])
        self.assertTrue(readback["readback_matches_decision"])
        self.assertEqual(readback["decision_digest"], readback["readback_digest"])
        self.assertFalse(readback["promotion_allowed"])
        self.assertFalse(readback["provider_auto_promotion_allowed"])

        boundary = contract["provider_independent_boundary"]
        self.assertFalse(boundary["network_started"])
        self.assertFalse(boundary["live_provider_probe_performed"])
        self.assertTrue(boundary["live_provider_quality_open"])
        self.assertFalse(boundary["provider_auto_promotion_allowed"])

    def test_provider_independent_gate_rejects_input_promotion_claims(self) -> None:
        gate = build_symbolic_quality_promotion_readback_gate(
            fixture_cases=_fixture_cases(),
            provider_statuses=_provider_statuses(),
            input_promotion_decision={
                "decision": "promote_provider_auto",
                "promotion_allowed": True,
                "provider_auto_promotion_allowed": True,
            },
        )

        self.assertEqual(gate["status"], "passed")
        self.assertEqual(gate["promotion_decision"]["decision"], "hold_provider_auto_promotion")
        self.assertFalse(gate["promotion_decision"]["promotion_allowed"])
        self.assertTrue(gate["promotion_decision_readback"]["input_promotion_claim_rejected"])
        self.assertIn(
            "input_promotion_decision_claim_rejected",
            {item["code"] for item in gate["unsupported_promotion_claims"]},
        )
        self.assertIn(
            "live_provider_replay_not_run",
            {item["code"] for item in gate["remaining_live_gaps"]},
        )


if __name__ == "__main__":
    unittest.main()
