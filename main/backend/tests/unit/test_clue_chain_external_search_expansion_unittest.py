from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import Mock

import pytest

from app.services.clue_chains.external_search_expansion import (
    ExternalSearchExpansionRequest,
    expand_external_search,
    normalize_external_search_url,
)

pytestmark = pytest.mark.unit


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "clue_chains" / "external_search_results.json"


class ClueChainExternalSearchExpansionTest(unittest.TestCase):
    def test_default_provider_is_fixture_gated_and_never_calls_live_searcher(self) -> None:
        live_searcher = Mock(return_value=[{"title": "Should not run", "url": "https://live.example"}])

        payload = expand_external_search(
            ExternalSearchExpansionRequest(
                chain_id="chain-default",
                focus_node_id="node-a",
                query="robotics policy",
                provider_name="serper",
            ),
            live_searcher=live_searcher,
        )

        live_searcher.assert_not_called()
        self.assertEqual(payload["hop"]["status"], "blocked")
        self.assertEqual(payload["hop"]["blocked_reason"], "fixture_gate")
        self.assertTrue(payload["hop"]["fixture_gate"])
        self.assertEqual(payload["trace"]["network_allowed"], False)
        self.assertEqual(payload["trace"]["provider_name"], "serper")
        self.assertEqual(payload["evidence"], [])
        self.assertEqual(payload["candidates"], [])
        self.assertEqual(payload["replay"]["mode"], "blocked")

    def test_fixture_replay_is_deterministic_and_shapes_hop_evidence_candidates(self) -> None:
        request = ExternalSearchExpansionRequest(
            chain_id="chain-fixture",
            focus_node_id="node-policy",
            query="robotics policy breadcrumbs",
            provider_name="fixture_web",
            fixture_path=FIXTURE_PATH,
        )

        first = expand_external_search(request)
        second = expand_external_search(request)

        self.assertEqual(first, second)
        self.assertEqual(first["hop"]["status"], "completed")
        self.assertEqual(first["hop"]["provider_name"], "fixture_web")
        self.assertEqual(first["hop"]["query"], "robotics policy breadcrumbs")
        self.assertTrue(first["hop"]["fixture_gate"])
        self.assertEqual(first["trace"]["raw_result_count"], 3)
        self.assertEqual(first["trace"]["duplicate_count"], 1)
        self.assertEqual(first["hop"]["candidate_count"], 2)
        self.assertEqual(first["hop"]["evidence_count"], 2)
        self.assertEqual(first["replay"]["mode"], "fixture")
        self.assertEqual(first["replay"]["fixture_path"], str(FIXTURE_PATH))

        first_candidate = first["candidates"][0]
        first_evidence = first["evidence"][0]
        self.assertEqual(first_candidate["provider_name"], "fixture_web")
        self.assertEqual(first_candidate["query"], "robotics policy breadcrumbs")
        self.assertEqual(first_candidate["normalized_url"], "https://example.org/registry?keep=1")
        self.assertEqual(first_candidate["dedupe_key"], "url:https://example.org/registry?keep=1")
        self.assertEqual(first_candidate["evidence_refs"], [first_evidence["evidence_id"]])
        self.assertFalse(first_candidate["promotion_allowed"])
        self.assertTrue(first_candidate["requires_decision"])
        self.assertIsNone(first_candidate["blocked_reason"])
        self.assertEqual(first_evidence["title"], "Robotics Policy Registry")
        self.assertEqual(first_evidence["snippet"], "Registry entry with policy breadcrumbs.")
        self.assertEqual(first_evidence["merged_count"], 2)
        self.assertIn("Policy Registry Duplicate", first_evidence["aliases"])

    def test_injected_results_merge_duplicate_urls_and_alias_only_candidates(self) -> None:
        payload = expand_external_search(
            ExternalSearchExpansionRequest(
                chain_id="chain-merge",
                query="market alias",
                provider_name="fixture_injected",
                injected_results=[
                    {
                        "title": "Market Report",
                        "url": "https://Example.com/report?utm_source=x&id=1#section",
                        "snippet": "Primary result.",
                        "aliases": ["Annual Robotics"],
                    },
                    {
                        "title": "Market Report 2026",
                        "link": "https://example.com/report?id=1",
                        "snippet": "Duplicate URL.",
                        "aliases": ["Annual Robotics 2026"],
                    },
                    {
                        "title": "Alias Only",
                        "snippet": "No URL result.",
                        "aliases": ["Alias Only Inc."],
                    },
                    {
                        "title": "alias only",
                        "snippet": "Duplicate alias with different case.",
                    },
                ],
            )
        )

        self.assertEqual(payload["hop"]["status"], "completed")
        self.assertEqual(payload["trace"]["raw_result_count"], 4)
        self.assertEqual(payload["trace"]["duplicate_count"], 2)
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertEqual(len(payload["evidence"]), 2)

        url_candidate = payload["candidates"][0]
        self.assertEqual(url_candidate["normalized_url"], "https://example.com/report?id=1")
        self.assertEqual(url_candidate["dedupe_key"], "url:https://example.com/report?id=1")
        self.assertEqual(url_candidate["merged_count"], 2)
        self.assertIn("Annual Robotics", url_candidate["aliases"])
        self.assertIn("Annual Robotics 2026", url_candidate["aliases"])

        alias_candidate = payload["candidates"][1]
        self.assertEqual(alias_candidate["candidate_type"], "external_alias")
        self.assertEqual(alias_candidate["normalized_url"], "")
        self.assertEqual(alias_candidate["dedupe_key"], "alias:alias-only")
        self.assertEqual(alias_candidate["merged_count"], 2)
        self.assertIn("Alias Only Inc.", alias_candidate["aliases"])

    def test_live_hook_runs_only_when_live_enabled_is_explicit(self) -> None:
        live_searcher = Mock(
            return_value=[
                {
                    "title": "Live Hook Result",
                    "url": "https://live.example/result",
                    "snippet": "Injected live hook response.",
                }
            ]
        )

        payload = expand_external_search(
            ExternalSearchExpansionRequest(
                chain_id="chain-live",
                query="approved live query",
                provider_name="live_stub",
                live_enabled=True,
            ),
            live_searcher=live_searcher,
        )

        live_searcher.assert_called_once_with(
            query="approved live query",
            limit=10,
            provider_name="live_stub",
        )
        self.assertEqual(payload["hop"]["status"], "completed")
        self.assertFalse(payload["hop"]["fixture_gate"])
        self.assertTrue(payload["trace"]["network_allowed"])
        self.assertEqual(payload["replay"]["mode"], "live_hook")
        self.assertEqual(payload["candidates"][0]["normalized_url"], "https://live.example/result")

    def test_url_normalization_removes_tracking_fragment_and_default_ports(self) -> None:
        self.assertEqual(
            normalize_external_search_url("HTTPS://Example.com:443/path/?utm_campaign=x&b=2&a=1#frag"),
            "https://example.com/path?a=1&b=2",
        )


if __name__ == "__main__":
    unittest.main()
