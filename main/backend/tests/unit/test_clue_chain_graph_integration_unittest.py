from __future__ import annotations

import unittest

import pytest

from app.services.clue_chains.graph_integration import (
    ClueChainGraphIntegrationError,
    build_graph_handoff_payload,
    build_graph_mutation_payload,
)

pytestmark = pytest.mark.unit


class ClueChainGraphIntegrationUnitTest(unittest.TestCase):
    def _chain(self) -> dict:
        return {"chain_id": "chain-robotics", "graph_id": "cg-robotics"}

    def test_approved_candidate_builds_mutation_and_handoff_payload(self):
        candidates = [
            {
                "candidate_id": "cand-acme",
                "chain_id": "chain-robotics",
                "hop_id": "hop-source-library-1",
                "evidence_id": "ev-acme",
                "source_node_id": "seed-robotics",
                "edge_type": "SUPPLIES",
                "node": {
                    "node_type": "Company",
                    "title": "Acme Robotics",
                    "summary": "Acme Robotics supplies warehouse robots.",
                    "aliases": ["Acme", "Acme Robotics"],
                    "source_uri": "https://example.test/acme",
                },
                "confidence": 0.82,
            }
        ]
        decisions = [{"decision_id": "dec-acme", "candidate_id": "cand-acme", "decision": "approved"}]
        evidence_items = [
            {
                "evidence_id": "ev-acme",
                "chain_id": "chain-robotics",
                "hop_id": "hop-source-library-1",
                "summary": "Evidence summary",
            }
        ]

        handoff = build_graph_handoff_payload(
            chain=self._chain(),
            candidates=candidates,
            decisions=decisions,
            evidence_items=evidence_items,
        )

        mutation = handoff["graph_mutation"]
        self.assertEqual(handoff["contract_version"], "graph_handoff.v1")
        self.assertEqual(handoff["handoff_mode"], "push_payload")
        self.assertEqual(handoff["producer"], "clue_chain.graph_integration")
        self.assertEqual(handoff["consumer"], "workflow_graph.curated")
        self.assertEqual(mutation["contract_version"], "clue_chain.graph_mutation.v1")
        self.assertEqual(mutation["graph_id"], "cg-robotics")
        self.assertEqual(mutation["chain_id"], "chain-robotics")
        self.assertEqual(len(mutation["nodes"]), 1)
        self.assertEqual(len(mutation["edges"]), 1)
        self.assertEqual(mutation["operations"]["upsert_nodes"], mutation["nodes"])
        self.assertEqual(mutation["operations"]["upsert_edges"], mutation["edges"])

        node = mutation["nodes"][0]
        edge = mutation["edges"][0]
        self.assertEqual(node["node_type"], "Company")
        self.assertEqual(edge["from_node_id"], "seed-robotics")
        self.assertEqual(edge["to_node_id"], node["node_id"])
        for item in (node, edge):
            self.assertEqual(
                item["provenance"],
                {
                    "chain_id": "chain-robotics",
                    "hop_id": "hop-source-library-1",
                    "evidence_id": "ev-acme",
                    "candidate_id": "cand-acme",
                    "decision_id": "dec-acme",
                },
            )

        evidence_pack = handoff["evidence_pack"]
        self.assertEqual(evidence_pack["contract_version"], "graph_evidence_pack.v1")
        self.assertEqual(evidence_pack["selected_nodes"][0]["node_id"], node["node_id"])
        self.assertEqual(evidence_pack["relations"][0]["edge_id"], edge["edge_id"])

        repeated = build_graph_handoff_payload(
            chain=self._chain(),
            candidates=candidates,
            decisions=decisions,
            evidence_items=evidence_items,
        )
        self.assertEqual(repeated["graph_mutation"]["nodes"][0]["node_id"], node["node_id"])
        self.assertEqual(repeated["graph_mutation"]["edges"][0]["edge_id"], edge["edge_id"])

    def test_missing_evidence_is_rejected_before_graph_mutation(self):
        with self.assertRaisesRegex(ClueChainGraphIntegrationError, "missing evidence ev-missing"):
            build_graph_mutation_payload(
                chain=self._chain(),
                candidates=[
                    {
                        "candidate_id": "cand-missing",
                        "chain_id": "chain-robotics",
                        "hop_id": "hop-1",
                        "evidence_id": "ev-missing",
                        "source_node_id": "seed-robotics",
                        "node": {"title": "Missing Evidence Entity"},
                    }
                ],
                decisions=[{"decision_id": "dec-missing", "candidate_id": "cand-missing", "status": "approved"}],
                evidence_items=[],
            )

    def test_duplicate_aliases_merge_to_stable_node_and_edge(self):
        candidates = [
            {
                "candidate_id": "cand-acme-a",
                "chain_id": "chain-robotics",
                "hop_id": "hop-1",
                "evidence_id": "ev-a",
                "source_node_id": "seed-robotics",
                "edge_type": "MENTIONS",
                "node": {"node_type": "Company", "title": "Acme Robotics", "aliases": ["ACME"]},
            },
            {
                "candidate_id": "cand-acme-b",
                "chain_id": "chain-robotics",
                "hop_id": "hop-2",
                "evidence_id": "ev-b",
                "source_node_id": "seed-robotics",
                "edge_type": "MENTIONS",
                "node": {"node_type": "Company", "title": "Acme Robotics", "aliases": ["acme", "Acme Robotics"]},
            },
        ]
        decisions = [
            {"decision_id": "dec-a", "candidate_id": "cand-acme-a", "decision": "approved"},
            {"decision_id": "dec-b", "candidate_id": "cand-acme-b", "decision": "approved"},
        ]
        evidence_items = [
            {"evidence_id": "ev-a", "chain_id": "chain-robotics", "hop_id": "hop-1", "summary": "A"},
            {"evidence_id": "ev-b", "chain_id": "chain-robotics", "hop_id": "hop-2", "summary": "B"},
        ]

        mutation = build_graph_mutation_payload(
            chain=self._chain(),
            candidates=candidates,
            decisions=decisions,
            evidence_items=evidence_items,
        )

        self.assertEqual(len(mutation["nodes"]), 1)
        self.assertEqual(len(mutation["edges"]), 1)
        self.assertEqual(len(mutation["operations"]["merge_aliases"]), 1)
        node = mutation["nodes"][0]
        edge = mutation["edges"][0]
        self.assertEqual(node["node_id"], edge["to_node_id"])
        self.assertEqual(len(node["provenance_items"]), 2)
        self.assertEqual(len(edge["provenance_items"]), 2)
        self.assertEqual(node["provenance"]["merged_count"], 2)
        self.assertEqual(edge["provenance"]["merged_count"], 2)
        self.assertEqual(set(mutation["candidate_ids"]), {"cand-acme-a", "cand-acme-b"})


if __name__ == "__main__":
    unittest.main()
