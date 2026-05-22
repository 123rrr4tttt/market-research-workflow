from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import pytest

from app.services.clue_chains import ClueChainClosedError, ClueChainService, InMemoryClueChainStore

pytestmark = pytest.mark.unit


def _fixed_now() -> datetime:
    return datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


class ClueChainServiceUnitTest(unittest.TestCase):
    def _service(self) -> ClueChainService:
        return ClueChainService(store=InMemoryClueChainStore(project_key="demo_proj"), clock=_fixed_now)

    def test_create_record_hop_decision_and_close_chain(self) -> None:
        service = self._service()
        created = service.create_chain(
            {
                "graph_id": "graph-1",
                "title": "EV policy supplier trace",
                "objective": "Trace graph seeds into source evidence.",
                "seed_node_ids": ["graph-node-1"],
                "created_by": "analyst",
            }
        )
        chain_id = created["chain"]["chain_id"]
        self.assertTrue(chain_id.startswith("chain_"))
        self.assertEqual(created["chain"]["status"], "draft")

        hop_result = service.record_hop(
            chain_id,
            {
                "mode": "source_library_search",
                "input_node_id": "graph-node-1",
                "query_json": {"query": "ACME Inc EV policy supplier"},
                "provider": "source_library",
                "evidence": [
                    {
                        "source_kind": "source_library",
                        "source_item_key": "policy-db",
                        "document_id": "doc-1",
                        "chunk_id": "chunk-7",
                        "title": "ACME supplier filing",
                        "snippet": "ACME appears in an EV supplier filing.",
                        "status": "lead",
                    }
                ],
                "candidates": [
                    {
                        "entity_type": "Company",
                        "value": "ACME Inc",
                        "aliases": ["ACME, Inc."],
                        "score": 0.74,
                    }
                ],
                "edges": [
                    {
                        "from_ref": "graph-node-1",
                        "to_ref": "ACME Inc",
                        "relation": "mentions_supplier",
                    }
                ],
            },
        )
        self.assertEqual(hop_result["hop"]["status"], "completed")
        self.assertEqual(hop_result["evidence"][0]["source_ref"]["document_id"], "doc-1")
        candidate = hop_result["candidates"][0]
        evidence_id = hop_result["evidence"][0]["evidence_id"]

        decision_result = service.record_decision(
            chain_id,
            candidate["candidate_id"],
            {
                "decision": "promote",
                "actor": "analyst",
                "reason": "Source-library evidence is enough for graph handoff.",
                "graph_node_id": "graph-node-acme",
                "evidence_ids": [evidence_id],
            },
        )
        self.assertEqual(decision_result["candidate"]["decision_status"], "promoted")
        self.assertEqual(decision_result["candidate"]["graph_node_id"], "graph-node-acme")
        self.assertIn(evidence_id, decision_result["decision"]["evidence_ids"])

        closed = service.close_chain(chain_id, {"reason": "review complete", "actor": "analyst"})
        self.assertEqual(closed["chain"]["status"], "closed")
        self.assertEqual(closed["chain"]["close_reason"], "review complete")
        with self.assertRaises(ClueChainClosedError):
            service.record_hop(chain_id, {"mode": "manual", "input_node_id": "graph-node-1"})

    def test_alias_dedupe_merges_candidates_before_new_node_creation(self) -> None:
        service = self._service()
        chain_id = service.create_chain({"seed_node_ids": ["seed-1"], "title": "Alias test"})["chain"]["chain_id"]
        hop = service.record_hop(
            chain_id,
            {
                "mode": "manual",
                "input_node_id": "seed-1",
                "candidates": [{"entity_type": "Company", "value": "Acme, Inc.", "aliases": ["ACME"]}],
            },
        )["hop"]
        first_candidate = service.get_chain(chain_id)["candidates"][0]
        merged = service.add_candidate(
            chain_id,
            hop["hop_id"],
            {"entity_type": "Company", "value": "ACME", "aliases": ["Acme Inc"], "score": 0.92},
        )
        detail = service.get_chain(chain_id)

        self.assertEqual(first_candidate["candidate_id"], merged["candidate_id"])
        self.assertEqual(len(detail["candidates"]), 1)
        self.assertEqual(detail["candidates"][0]["aliases"], ["Acme, Inc.", "ACME"])
        self.assertEqual(detail["alias_index"]["acme"], merged["candidate_id"])
        self.assertEqual(detail["alias_index"]["acme inc"], merged["candidate_id"])
        self.assertEqual(detail["candidates"][0]["score"], 0.92)

    def test_manual_expansion_provider_hook_records_results_without_network(self) -> None:
        service = self._service()
        chain_id = service.create_chain({"seed_node_ids": ["seed-1"], "title": "Provider hook"})["chain"]["chain_id"]

        def fake_provider(chain: dict, payload: dict) -> dict:
            self.assertEqual(chain["chain"]["chain_id"], chain_id)
            self.assertEqual(payload["mode"], "external_search")
            return {
                "status": "completed",
                "provider": "fixture_external_search",
                "evidence": [{"source_kind": "external_search", "url": "https://example.com/a", "title": "Result A"}],
                "candidates": [{"entity_type": "Company", "value": "Result A Co"}],
            }

        result = service.expand_chain(
            chain_id,
            {"mode": "external_search", "input_node_id": "seed-1", "query": "Result A Co"},
            provider=fake_provider,
        )
        self.assertEqual(result["hop"]["provider"], "fixture_external_search")
        self.assertEqual(result["evidence"][0]["source_kind"], "external_search")
        self.assertEqual(result["candidates"][0]["value"], "Result A Co")

    def test_default_store_is_ingest_config_monkeypatch_isolated(self) -> None:
        store = {"payload": {"contract_version": "clue_chain.state.v1", "base_version": 0, "chains": {}}}

        with patch("app.services.clue_chains.store.current_project_key", return_value="demo_proj"), patch(
            "app.services.clue_chains.store.get_ingest_config",
            side_effect=lambda *_args, **_kwargs: {"payload": store["payload"]},
        ), patch(
            "app.services.clue_chains.store.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: (
                store.update({"payload": kwargs.get("payload")}),
                {"payload": store["payload"]},
            )[1],
        ):
            service = ClueChainService(clock=_fixed_now)
            result = service.create_chain({"seed_node_ids": ["seed-1"], "title": "Ingest config backed"})

        chain_id = result["chain"]["chain_id"]
        self.assertEqual(store["payload"]["base_version"], 1)
        self.assertEqual(store["payload"]["chains"][chain_id]["chain"]["project_key"], "demo_proj")


if __name__ == "__main__":
    unittest.main()
