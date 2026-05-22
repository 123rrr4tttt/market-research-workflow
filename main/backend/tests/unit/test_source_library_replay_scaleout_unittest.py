from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.source_library_replay_scaleout import DEFAULT_HISTORICAL_TARGETS
from scripts.source_library_replay_scaleout import run_replay
from scripts.source_library_replay_scaleout import validate_manifest_targets


class SourceLibraryReplayScaleoutUnitTestCase(unittest.TestCase):
    def test_default_manifest_covers_historical_45_site_set(self) -> None:
        validation = validate_manifest_targets(DEFAULT_HISTORICAL_TARGETS)

        self.assertTrue(validation["passed"], validation["errors"])
        self.assertEqual(validation["target_count"], 45)
        self.assertEqual(validation["enabled_target_count"], 40)
        self.assertEqual(validation["policy_skipped_target_count"], 5)

    def test_replay_gate_is_skip_safe_by_default(self) -> None:
        result = run_replay(allow_public_network=False)

        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertTrue(result["validation"]["skipped"])
        self.assertTrue(result["validation"]["full_historical_manifest"])
        self.assertFalse(result["validation"]["live_evidence_sufficient"])
        self.assertEqual(result["outputs"]["status_counts"], {"skipped_public_network_disabled": 45})
        self.assertEqual(result["outputs"]["public_targets_attempted"], 0)

    def test_public_replay_separates_policy_skip_antibot_and_term_fallback_review(self) -> None:
        manifest = {
            "query_terms": ["openai api pricing"],
            "targets": [
                {
                    "target_id": "disabled-platform",
                    "domain": "x.com",
                    "template": "https://x.com/search?q={{q}}",
                    "enabled": False,
                    "skip_public_execution": True,
                },
                {
                    "target_id": "fallback-review",
                    "domain": "example.com",
                    "template": "https://example.com/search?q={{q}}",
                    "enabled": True,
                },
                {
                    "target_id": "anti-bot",
                    "domain": "blocked.example",
                    "template": "https://blocked.example/search?q={{q}}",
                    "enabled": True,
                },
            ],
        }

        def _fake_runner(target: dict) -> dict:
            if target["target_id"] == "fallback-review":
                return {
                    "target": {
                        "target_id": "fallback-review",
                        "domain": "example.com",
                        "template": target["template"],
                        "query_terms": target["query_terms"],
                    },
                    "entry_domain": "example.com",
                    "elapsed_ms": 4,
                    "classification": {
                        "status": "candidate_ready_with_term_fallback",
                        "blocker_type": "relevance_review",
                        "reason": "fixture fallback review",
                    },
                    "adapter_result": {
                        "candidate_count": 1,
                        "candidates": ["https://example.com/article"],
                        "errors": [],
                    },
                }
            return {
                "target": {
                    "target_id": "anti-bot",
                    "domain": "blocked.example",
                    "template": target["template"],
                    "query_terms": target["query_terms"],
                },
                "entry_domain": "blocked.example",
                "elapsed_ms": 3,
                "classification": {
                    "status": "anti_bot_or_transport_blocked",
                    "blocker_type": "public_network_or_anti_bot",
                    "reason": "fixture anti-bot",
                },
                "adapter_result": {
                    "candidate_count": 0,
                    "candidates": [],
                    "errors": [{"error": "429"}],
                },
            }

        result = run_replay(
            manifest=manifest,
            allow_public_network=True,
            target_runner=_fake_runner,
        )

        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["skipped"])
        self.assertEqual(result["outputs"]["public_targets_attempted"], 2)
        self.assertEqual(
            result["outputs"]["status_counts"],
            {
                "anti_bot_or_transport_blocked": 1,
                "candidate_ready_with_term_fallback": 1,
                "skipped_policy_disabled_platform_entry": 1,
            },
        )
        self.assertEqual(result["outputs"]["blocker_type_counts"]["policy_or_platform_required"], 1)
        self.assertEqual(result["outputs"]["blocker_type_counts"]["public_network_or_anti_bot"], 1)
        self.assertEqual(result["outputs"]["blocker_type_counts"]["relevance_review"], 1)
        self.assertEqual(result["outputs"]["term_fallback_relevance_review"][0]["target_id"], "fallback-review")

    def test_manifest_validation_rejects_missing_query_placeholder(self) -> None:
        validation = validate_manifest_targets(
            [
                {
                    "target_id": "bad",
                    "template": "https://example.com/search",
                    "query_terms": ["openai"],
                }
            ]
        )

        self.assertFalse(validation["passed"])
        self.assertIn("bad template must contain {q}", validation["errors"])


if __name__ == "__main__":
    unittest.main()
