from __future__ import annotations

import unittest

import pytest

from app.services.workflow_graph.handoff_store import WorkflowGraphHandoffStore
from app.services.workflow_graph.store import InMemoryRunStore

pytestmark = pytest.mark.unit


class WorkflowGraphHandoffStoreUnitTest(unittest.TestCase):
    def test_persist_list_and_replay(self):
        store = InMemoryRunStore()
        handoff_store = WorkflowGraphHandoffStore(store=store)
        payload = {
            "run_id": "run-h1",
            "contract_version": "graph_handoff.v1",
            "handoff_id": "h1",
            "handoff_mode": "pull_prepared_evidence",
            "producer": "workflow_graph.backend_bridge",
            "consumer": "llm_report.generate",
            "evidence_pack": {"pack_id": "p1"},
        }

        persisted = handoff_store.persist(graph_id="g1", payload=payload)
        self.assertEqual(persisted["handoff_id"], "h1")

        listed = handoff_store.list_handoffs(run_id="run-h1")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["handoff_id"], "h1")

        replayed = handoff_store.replay_handoff(run_id="run-h1", handoff_id="h1")
        self.assertEqual(replayed["handoff_id"], "h1")
        self.assertEqual(replayed["result"]["handoff_id"], "h1")
        self.assertTrue(any(evt.get("type") == "handoff.replayed" for evt in replayed["events"]))

    def test_unknown_handoff_event_fail_closed(self):
        store = InMemoryRunStore()
        store.create_run(run_id="run-h2", topo_order=[])
        store.append_event("run-h2", event_type="handoff.unknown", payload={"handoff_id": "h2"})
        handoff_store = WorkflowGraphHandoffStore(store=store)
        with self.assertRaises(ValueError) as exc:
            handoff_store.list_handoffs(run_id="run-h2")
        self.assertIn("unknown handoff event type", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
