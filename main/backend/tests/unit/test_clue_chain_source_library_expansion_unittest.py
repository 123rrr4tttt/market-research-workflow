from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.clue_chains.source_library_expansion import (  # noqa: E402
    CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION,
    expand_source_library_hop,
    merge_candidate_aliases,
)

pytestmark = pytest.mark.unit


def _source_items() -> list[dict[str, object]]:
    return [
        {
            "item_key": "generic_web.robot_rss",
            "name": "Robot RSS",
            "channel_key": "generic_web",
            "description": "robot funding news from example.com",
            "tags": ["robotics"],
            "params": {"site_url": "https://example.com/feed.xml"},
            "enabled": True,
            "extra": {"expected_entry_type": "rss"},
            "scope": "project",
        },
        {
            "item_key": "handler.cluster.search_template",
            "name": "Search Template Cluster",
            "channel_key": "handler.cluster",
            "description": "robot commercialization funding news search templates",
            "tags": ["handler_cluster", "search_template"],
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
                "expected_entry_type": "search_template",
            },
            "enabled": True,
            "extra": {
                "expected_entry_type": "search_template",
                "stable_handler_cluster": True,
                "item_type": "service_aggregated",
                "managed_by": "system",
            },
            "scope": "project",
        },
    ]


class ClueChainSourceLibraryExpansionUnitTest(unittest.TestCase):
    def test_expansion_from_fixtures_is_deterministic_and_read_only(self) -> None:
        with patch("socket.getaddrinfo", side_effect=AssertionError("network must not be used")):
            first = expand_source_library_hop(
                chain_id="chain-demo",
                project_key="demo_proj",
                frontier={"node_id": "node-1", "label": "Robot funding"},
                source_library_items=_source_items(),
                domains=["https://example.com"],
                max_candidates=5,
            )
            second = expand_source_library_hop(
                chain_id="chain-demo",
                project_key="demo_proj",
                frontier={"node_id": "node-1", "label": "Robot funding"},
                source_library_items=_source_items(),
                domains=["https://example.com"],
                max_candidates=5,
            )

        self.assertEqual(first, second)
        self.assertEqual(first["contract_version"], CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION)
        self.assertEqual(first["hop"]["expansion_mode"], "source_library_search")
        self.assertEqual(first["hop"]["frontier"]["node_id"], "node-1")
        self.assertEqual(first["hop"]["query"], "Robot funding")
        self.assertFalse(first["replay_manifest"]["network_fetch_performed"])
        self.assertFalse(first["replay_manifest"]["external_write_performed"])
        self.assertTrue(first["replay_manifest"]["fixture_required"])
        self.assertIn("site:example.com Robot funding", first["replay_manifest"]["search_queries"])
        self.assertEqual(first["trace"]["source_items_loaded"], 2)
        self.assertEqual(first["trace"]["candidate_count"], 2)

        candidate = first["candidates"][0]
        self.assertEqual(candidate["source_ref"]["tool"], "clue_chain.source_library_search")
        self.assertEqual(candidate["source_ref"]["source_mode"], "source_library_search")
        self.assertEqual(candidate["source_ref"]["project_key"], "demo_proj")
        self.assertEqual(candidate["source_ref"]["item_key"], "handler.cluster.search_template")
        self.assertEqual(candidate["query"], "Robot funding")
        self.assertEqual(candidate["rank"], 1)
        self.assertIsInstance(candidate["score"], float)
        self.assertTrue(candidate["dedupe_key"].startswith("source_library:demo_proj:"))
        self.assertTrue(candidate["evidence_id"].startswith("ev_src_"))
        self.assertEqual(candidate["decision_status"], "pending_review")
        self.assertEqual(candidate["promote_guard"], "requires_chain_decision")

        evidence_by_id = {row["evidence_id"]: row for row in first["evidence"]}
        self.assertIn(candidate["evidence_id"], evidence_by_id)
        self.assertEqual(evidence_by_id[candidate["evidence_id"]]["source_ref"], candidate["source_ref"])
        self.assertFalse(evidence_by_id[candidate["evidence_id"]]["trace"]["network_fetch_performed"])

    def test_source_item_loader_can_supply_replayable_rows_without_fixtures(self) -> None:
        calls: list[tuple[str, str]] = []

        def _loader(project_key: str, query: str) -> list[dict[str, object]]:
            calls.append((project_key, query))
            return _source_items()

        result = expand_source_library_hop(
            chain_id="chain-loader",
            project_key="demo_proj",
            frontier_query="robot funding",
            source_item_loader=_loader,
            max_candidates=1,
        )

        self.assertEqual(calls, [("demo_proj", "robot funding")])
        self.assertFalse(result["replay_manifest"]["fixture_required"])
        self.assertEqual(result["replay_manifest"]["source_item_keys"], ["generic_web.robot_rss", "handler.cluster.search_template"])
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["source_ref"]["item_key"], "handler.cluster.search_template")

    def test_alias_merge_keeps_trace_to_all_evidence_rows(self) -> None:
        items = [
            {
                "item_key": "source.alpha",
                "name": "Acme Robotics Reports",
                "channel_key": "generic_web",
                "description": "robot funding report",
                "tags": ["acme-robotics"],
                "enabled": True,
            },
            {
                "item_key": "source.beta",
                "name": "Acme Robotics Reports",
                "channel_key": "generic_web",
                "description": "robot funding report mirror",
                "tags": ["acme-robotics"],
                "enabled": True,
            },
        ]

        result = expand_source_library_hop(
            chain_id="chain-alias",
            project_key="demo_proj",
            frontier_query="robot funding",
            source_library_items=items,
            max_candidates=10,
        )

        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(len(candidate["merged_from"]), 1)
        self.assertEqual(result["trace"]["merged_alias_count"], 1)
        evidence_ids = {row["evidence_id"] for row in result["evidence"]}
        self.assertIn(candidate["evidence_id"], evidence_ids)
        self.assertIn(candidate["merged_from"][0]["evidence_id"], evidence_ids)

    def test_merge_candidate_aliases_handles_duplicate_aliases_without_item_context(self) -> None:
        merged = merge_candidate_aliases(
            [
                {
                    "candidate_id": "cand-1",
                    "dedupe_key": "source_library:demo:alpha",
                    "evidence_id": "ev-1",
                    "aliases": ["Alpha Source", "alpha"],
                    "rank": 2,
                    "score": 20.0,
                },
                {
                    "candidate_id": "cand-2",
                    "dedupe_key": "source_library:demo:beta",
                    "evidence_id": "ev-2",
                    "aliases": ["alpha source"],
                    "rank": 1,
                    "score": 30.0,
                },
            ]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["rank"], 1)
        self.assertEqual(merged[0]["score"], 30.0)
        self.assertEqual(merged[0]["merged_from"][0]["candidate_id"], "cand-2")


if __name__ == "__main__":
    unittest.main()
