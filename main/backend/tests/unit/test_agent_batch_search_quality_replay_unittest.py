from __future__ import annotations

import unittest

import pytest

pytestmark = pytest.mark.unit

try:
    from app.services.agent_batch.search_quality_replay import (
        build_live_provider_gap_state,
        build_source_quality_signals,
        build_symbolic_provider_quality_readiness,
        evaluate_quality_retry_boundary,
        score_quality_benchmark_replay,
        score_symbolic_search_quality_replay,
    )
except Exception as exc:  # pragma: no cover - dependency/import guard
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


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


class AgentBatchSearchQualityReplayUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"search quality replay tests require backend dependencies: {_IMPORT_ERROR}")

    def test_quality_replay_scores_source_signals_without_live_provider_claim(self) -> None:
        replay = score_symbolic_search_quality_replay(search_brief=_brief(), records=_retry_records())

        self.assertEqual(replay["contract_version"], "agent_batch.search_quality_replay.v1")
        self.assertEqual(replay["scope"], "deterministic_no_network_symbolic_search_quality_replay")
        self.assertGreaterEqual(replay["score"], 0.8)
        self.assertEqual(replay["coverage"]["source_diversity"], 1.0)
        self.assertFalse(replay["live_provider_gap_state"]["quality_claim_allowed"])
        self.assertFalse(replay["live_provider_gap_state"]["live_provider_probe_performed"])
        self.assertEqual(replay["live_provider_gap_state"]["providers_not_started"], ["searxng", "yacy", "web"])

        signals = build_source_quality_signals(search_brief=_brief(), records=_retry_records())
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["provider_trace_state"], "deterministic_replay")
        self.assertFalse(signals[0]["provider_live_verified"])
        self.assertEqual(signals[0]["source_library_item_key"], "robotics.market_watch")
        self.assertEqual(signals[0]["axis_hits"], ["products", "companies", "recent_movement"])

    def test_retry_boundary_does_not_let_replay_score_override_critic_stop(self) -> None:
        low_quality_replay = score_symbolic_search_quality_replay(search_brief=_brief(), records=_baseline_records())
        boundary = evaluate_quality_retry_boundary(
            search_critic={
                "score": 0.91,
                "next_action": "stop",
                "reason_codes": ["coverage_sufficient"],
            },
            quality_replay=low_quality_replay,
        )

        self.assertEqual(boundary["decision"], "retry_blocked")
        self.assertEqual(boundary["reason_code"], "critic_stop")
        self.assertTrue(boundary["replay_score_is_observational"])
        self.assertEqual(boundary["retry_score_source"], "search_critic.score")

    def test_retry_boundary_allows_source_gap_threshold_bypass(self) -> None:
        replay = score_symbolic_search_quality_replay(search_brief=_brief(), records=_baseline_records())
        boundary = evaluate_quality_retry_boundary(
            search_critic={
                "score": 0.84,
                "next_action": "retry_with_source_library",
                "reason_codes": ["source_backing_missing"],
            },
            quality_replay=replay,
        )

        self.assertEqual(boundary["decision"], "retry_allowed")
        self.assertEqual(boundary["reason_code"], "source_gap_threshold_bypass")
        self.assertTrue(boundary["threshold_bypassed"])
        self.assertFalse(boundary["live_provider_quality_claim_allowed"])

    def test_benchmark_replay_reports_positive_uplift_and_live_gap(self) -> None:
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

        self.assertEqual(result["contract_version"], "agent_batch.search_quality_replay.v1")
        self.assertEqual(result["status"], "passed")
        self.assertGreater(result["average_uplift"], 0.0)
        self.assertEqual(result["false_positive_retry_rate"], 0.0)
        self.assertEqual(result["quality_claim"], "deterministic_replay_only_not_live_provider_quality")
        self.assertEqual(result["live_provider_gap_state"], build_live_provider_gap_state())

    def test_provider_quality_readiness_records_fixture_quality_and_live_gaps(self) -> None:
        readiness = build_symbolic_provider_quality_readiness(
            fixture_cases=[
                {
                    "case_id": "robotics-source-gap",
                    "category": "company_watchlist",
                    "search_brief": _brief(),
                    "baseline_records": _baseline_records(),
                    "retry_records": _retry_records(),
                    "retry_expected": True,
                }
            ],
            provider_statuses={
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
            },
        )

        self.assertEqual(readiness["contract_version"], "agent_batch.provider_quality_readiness.v1")
        self.assertEqual(
            readiness["readiness_state"],
            "fixture_quality_ready_live_provider_gap_open",
        )
        self.assertEqual(readiness["fixture_quality"]["status"], "passed")
        self.assertGreater(readiness["fixture_quality"]["average_uplift"], 0.0)
        self.assertFalse(readiness["fixture_quality"]["quality_claim_allowed"])
        self.assertFalse(readiness["provider_readiness"]["quality_claim_allowed"])
        self.assertFalse(readiness["provider_readiness"]["auto_promotion_allowed"])
        self.assertEqual(
            readiness["provider_readiness"]["providers"]["searxng"]["remaining_gap"],
            "live_provider_not_ready",
        )
        self.assertIn(
            "fixture_replay_proves_live_provider_quality",
            {item["code"] for item in readiness["unsupported_live_provider_claims"]},
        )
        self.assertIn(
            "live_retry_uplift_replay_not_run",
            {item["code"] for item in readiness["remaining_live_gaps"]},
        )


if __name__ == "__main__":
    unittest.main()
